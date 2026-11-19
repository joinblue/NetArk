#!/usr/bin/env python3
"""NetArk AST Code Hygiene Engine & Single-Pass Code Intelligence Scanner (code_hygiene_ast.py).
Governing Node: 100.ARCH-RULES.v1 & 100.SHARD-AST-DLP-GUARD.v1. Enforces P1-P4 and AST scanning."""

from __future__ import annotations

import ast, os, re, sys, textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas.topology_graph import is_gitignored_path  # noqa: E402
from schemas.workspace_placement_guard import check_ast_p3_p4  # noqa: E402

EXCLUDED_SCAN_DIRS = {"node_modules", ".git", "venv", ".venv", "dist", "build", "scratch", ".staging", "dashboard", "templates", "__pycache__", ".pytest_cache", ".agents", ".claude", ".github", "memory"}
TS_IMPORT_PATTERN = re.compile(r"""(?m)^\s*import\s+(?:type\s+)?(?:[^"']+from\s+)?["']([^"']+)["']""")
TS_EXPORT_SYMBOL_RE = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|const|interface|type)\s+([A-Za-z0-9_]+)")
TS_REGISTER_COMMAND_RE = re.compile(r"""pi\.registerCommand\(\s*["']([^"']+)["']""")
TS_REGISTER_TOOL_RE = re.compile(r"""pi\.registerTool\(\s*\{[\s\S]*?name\s*:\s*["']([^"']+)["']""")
TS_ON_HOOK_RE = re.compile(r"""pi\.on\(\s*["']([^"']+)["']""")
_CF_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith) + ((ast.TryStar,) if hasattr(ast, "TryStar") else ())


def get_brain_rel_dir(project_root: Path) -> str:
    env_dir = os.environ.get("PI_CODING_AGENT_DIR")
    if env_dir:
        try: return str(Path(env_dir).resolve().relative_to(project_root.resolve())).replace("\\", "/")
        except Exception: pass  # noqa: silent-except
    return ".agents" if (project_root / ".agents").exists() and not (project_root / ".netark").exists() else ".netark"


def _max_cf_depth(stmts: List[ast.stmt], current_depth: int = 0) -> int:
    best = current_depth
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, ast.If):
            d = current_depth + 1
            best = max(best, d, _max_cf_depth(stmt.body, d))
            if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                best = max(best, _max_cf_depth(stmt.orelse, current_depth))
            elif stmt.orelse:
                best = max(best, _max_cf_depth(stmt.orelse, d))
        elif isinstance(stmt, _CF_NODES):
            d = current_depth + 1
            best = max(best, d)
            for attr in ("body", "orelse", "finalbody"):
                best = max(best, _max_cf_depth(getattr(stmt, attr, []) or [], d))
            for handler in getattr(stmt, "handlers", []) or []:
                best = max(best, _max_cf_depth(handler.body, d))
    return best


def _is_silent_except_body(body: List[ast.stmt]) -> bool:
    return bool(body) and all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant) and s.value.value is Ellipsis) for s in body)


def _collect_docstring_lines(tree: ast.AST) -> Set[int]:
    """Collect 1-based line numbers belonging to module, class, and function docstrings."""
    doc_lines: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
            end_ln = getattr(first, "end_lineno", None) or first.lineno
            doc_lines.update(range(first.lineno, end_ln + 1))
    return doc_lines


def count_effective_code_lines(source: str, ext: str = ".py") -> int:
    """Count effective code lines excluding blank lines, comments, and Python docstrings."""
    if not source or not source.strip():
        return 0
    ext_l = ext.lower()
    if ext_l == ".py":
        doc_lines: Set[int] = set()
        for cand in (source, textwrap.dedent(source)):
            try:
                doc_lines = _collect_docstring_lines(ast.parse(cand))
                break
            except SyntaxError:
                continue
        return sum(1 for idx, ln in enumerate(source.splitlines(), 1) if idx not in doc_lines and ln.strip() and not ln.strip().startswith("#"))
    if ext_l in {".ts", ".tsx", ".js", ".jsx", ".mjs"}:
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", source)
        return sum(1 for ln in cleaned.splitlines() if ln.strip() and not ln.strip().startswith("//"))
    return len(source.splitlines())


def check_python_ast_hygiene(content: str, rel_path: str = "") -> Optional[Dict[str, Any]]:
    """Pre-Write AST hygiene check: P1 (CODE-ARROW-NESTING > 4), P2 (CODE-SILENT-EXCEPT), P3/P4."""
    if not content or not content.strip() or (rel_path and not rel_path.endswith(".py")):
        return None
    try:
        tree = ast.parse(content, filename=rel_path or "<memory>")
    except (SyntaxError, IndentationError):
        try:
            tree = ast.parse(textwrap.dedent(content), filename=rel_path or "<memory>")
        except Exception:
            return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth = _max_cf_depth(node.body, 0)
            if depth > 4:
                ln = getattr(node, "lineno", 1)
                return {
                    "allowed": False, "code": "CODE-ARROW-NESTING", "function": node.name, "depth": depth, "line": ln,
                    "reason": f"[P1 CODE-ARROW-NESTING] Function '{node.name}' in '{rel_path}' reaches control-flow nesting depth {depth} (> 4 max allowed, line {ln}). Flatten using Early-Return guard clauses (`if not cond: return/continue`) or extract a helper.",
                }
    lines = content.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_silent_except_body(node.body):
            s_ln, e_ln = max(0, getattr(node, "lineno", 1) - 1), min(len(lines), getattr(node, "end_lineno", getattr(node, "lineno", 1)))
            if "noqa: silent-except" not in "\n".join(lines[s_ln:e_ln]).lower():
                ln = getattr(node, "lineno", 1)
                return {
                    "allowed": False, "code": "CODE-SILENT-EXCEPT", "line": ln,
                    "reason": f"[P2 CODE-SILENT-EXCEPT] Silent exception block (`except ...: pass`) in '{rel_path}' at line {ln} without '# noqa: silent-except'. Handle/log the exception explicitly, or append '# noqa: silent-except'.",
                }
    if (p34 := check_ast_p3_p4(tree, lines, rel_path)):
        return p34
    return None


def discover_workspace_code_files(project_root: Path) -> Tuple[List[Path], List[Path]]:
    brain_rel = get_brain_rel_dir(project_root)
    py_files, ts_js_files = [], []
    for root, dirs, files in os.walk(project_root):
        rel_root = Path(root).resolve().relative_to(project_root.resolve())
        rel_root_str = "" if str(rel_root) == "." else str(rel_root).replace("\\", "/")
        filtered_dirs: List[str] = []
        for d in sorted(dirs):
            cand = f"{rel_root_str}/{d}".lstrip("/")
            if d in EXCLUDED_SCAN_DIRS or (d.startswith(".") and cand != brain_rel and not cand.startswith(f"{brain_rel}/")):
                continue
            if cand.startswith(f"{brain_rel}/") and cand != f"{brain_rel}/extensions" and not cand.startswith(f"{brain_rel}/extensions/"):
                continue
            if not is_gitignored_path(cand + "/", project_root) and not is_gitignored_path(cand, project_root):
                filtered_dirs.append(d)
        dirs[:] = filtered_dirs
        for fname in sorted(files):
            file_rel = f"{rel_root_str}/{fname}".lstrip("/")
            if not fname.startswith(".") and not is_gitignored_path(file_rel, project_root):
                if fname.endswith(".py"):
                    py_files.append(Path(root) / fname)
                elif fname.endswith((".ts", ".js", ".mjs")) and not fname.endswith(".d.ts"):
                    ts_js_files.append(Path(root) / fname)
    return py_files, ts_js_files


def _add_py_edge(mod_name: str, src_rel: str, py_module_map: Dict[str, str], seen_targets: Set[str], edges: List[Dict[str, str]], edge_type: str) -> None:
    proj_prefix = f"projects/{src_rel.split('/')[1]}/" if (src_rel.startswith("projects/") and len(src_rel.split("/")) >= 3) else ""
    for mod_cand in (mod_name.split(".")[0], mod_name.split(".")[-1]):
        target = None
        if proj_prefix:
            for p in py_module_map.values():
                if p.startswith(proj_prefix) and (Path(p).stem == mod_cand or p.endswith(f"/{mod_cand}.py")):
                    target = p
                    break
        target = target or py_module_map.get(mod_cand)
        if target and target != src_rel and target not in seen_targets:
            seen_targets.add(target)
            edges.append({"from": src_rel, "to": target, "type": edge_type})


def _analyze_python_ast_single_pass(
    source: str, src_rel: str, py_module_map: Dict[str, str]
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], int, List[str]]:
    edges, symbols, seen_targets, used_names, imported_bindings = [], [], set(), set(), {}
    tree, src_lines = ast.parse(source, filename=src_rel), source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({"name": node.name, "kind": "class" if isinstance(node, ast.ClassDef) else "function", "line_start": getattr(node, "lineno", 1), "line_end": getattr(node, "end_lineno", getattr(node, "lineno", 1))})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            ln = getattr(node, "lineno", 1)
            noqa = 1 <= ln <= len(src_lines) and "noqa" in src_lines[ln - 1].lower()
            for alias in node.names:
                if not noqa: imported_bindings.setdefault(alias.asname or alias.name.split(".")[0], ln)
                _add_py_edge(alias.name, src_rel, py_module_map, seen_targets, edges, "py_import")
        elif isinstance(node, ast.ImportFrom) and node.module:
            ln = getattr(node, "lineno", 1)
            noqa = node.module == "__future__" or (1 <= ln <= len(src_lines) and "noqa" in src_lines[ln - 1].lower())
            for alias in node.names:
                if alias.name != "*" and not noqa: imported_bindings.setdefault(alias.asname or alias.name, ln)
            _add_py_edge(node.module, src_rel, py_module_map, seen_targets, edges, "py_from_import")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used_names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value))
    max_depth = max((_max_cf_depth(n.body, 0) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), default=0)
    unused = sorted(name for name in imported_bindings if name not in used_names and not name.startswith("_"))
    return edges, symbols, max_depth, unused


def _scan_ts_file_single_pass(
    ts_file: Path, src_rel: str, project_root: Path, brain_rel: str, prompt_commands: Set[str]
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    edges, symbols, pi_regs, conflicts, total_lines = [], [], [], [], 1
    try:
        source = ts_file.read_text(encoding="utf-8")
        lines = source.splitlines()
        total_lines, seen_targets = max(1, len(lines)), set()
        for m in TS_IMPORT_PATTERN.finditer(source):
            spec = m.group(1)
            if spec.startswith("."):
                cand = (ts_file.parent / spec).resolve()
                if (cand.suffix in (".js", ".mjs") or not cand.suffix) and cand.with_suffix(".ts").exists():
                    cand = cand.with_suffix(".ts")
                if cand.exists() and cand.is_relative_to(project_root) and (target := str(cand.relative_to(project_root)).replace("\\", "/")) not in seen_targets:
                    seen_targets.add(target)
                    edges.append({"from": src_rel, "to": target, "type": "ts_local_import"})
            elif (spec.startswith("@earendil-works/") or spec.startswith("@sinclair/")) and spec not in seen_targets:
                seen_targets.add(spec)
                edges.append({"from": src_rel, "to": spec, "type": "ts_sdk_import"})
        for idx, line in enumerate(lines, start=1):
            if line.lstrip().startswith("//"): continue
            if (m_sym := TS_EXPORT_SYMBOL_RE.match(line)):
                symbols.append({"name": m_sym.group(2), "kind": m_sym.group(1), "line_start": idx, "line_end": idx})
            for m_cmd in TS_REGISTER_COMMAND_RE.finditer(line):
                cmd = m_cmd.group(1)
                pi_regs.append({"kind": "command", "name": f"/{cmd}", "line": idx})
                if cmd in prompt_commands: conflicts.append(f"/{cmd} shadows {brain_rel}/prompts/{cmd}.md (L{idx})")
            for m_hook in TS_ON_HOOK_RE.finditer(line): pi_regs.append({"kind": "hook", "name": m_hook.group(1), "line": idx})
        for m_tool in TS_REGISTER_TOOL_RE.finditer(source):
            pi_regs.append({"kind": "tool", "name": m_tool.group(1), "line": source[: m_tool.start()].count("\n") + 1})
    except Exception:  # noqa: silent-except
        pass
    return edges, {
        "file_path": src_rel, "language": "typescript" if src_rel.endswith(".ts") else "javascript",
        "total_lines": total_lines, "symbols": symbols, "pi_registrations": sorted(pi_regs, key=lambda x: (x["line"], x["name"])),
        "command_conflicts": conflicts, "imports": [], "imported_by": [], "governing_specs": [],
    }


def _bind_entry_specs(entry: Dict[str, Any], intel_map: Dict[str, Dict[str, Any]]) -> None:
    spec_ref = {"node_id": str(entry.get("node_id") or entry.get("id") or ""), "node_key": str(entry.get("node_key") or ""), "summary_1line": str(entry.get("summary_1line") or entry.get("title") or ""), "path": str(entry.get("path") or entry.get("file_path") or "")}
    for aff in (str(a).strip() for a in list(entry.get("affected_paths", []) or []) + list(entry.get("stub_paths", []) or []) if str(a).strip()):
        prefix = aff.rstrip("/") + "/"
        for code_path, info in intel_map.items():
            if (code_path == aff or code_path.startswith(prefix)) and spec_ref not in info["governing_specs"]:
                info["governing_specs"].append(spec_ref)


def _bind_governing_specs(entries: Optional[List[Dict[str, Any]]], intel_map: Dict[str, Dict[str, Any]]) -> None:
    for entry in entries or []: _bind_entry_specs(entry, intel_map)


def scan_code_intelligence_single_pass(
    project_root: Path, entries: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, str]], Dict[str, Dict[str, Any]]]:
    """Single-Pass AST & regex scanner returning (code_dependency_edges, code_intelligence_map)."""
    code_edges, intel_map = [], {}
    brain_rel = get_brain_rel_dir(project_root)
    prompts_dir = project_root / brain_rel / "prompts"
    prompt_commands = {p.stem for p in prompts_dir.glob("*.md")} if prompts_dir.exists() else set()
    py_files, ts_js_files = discover_workspace_code_files(project_root)
    py_module_map = {p.stem: str(p.relative_to(project_root)).replace("\\", "/") for p in py_files}
    for py_file in py_files:
        src_rel = str(py_file.relative_to(project_root)).replace("\\", "/")
        symbols, total_lines, max_depth, unused_imports = [], 1, 0, []
        try:
            source = py_file.read_text(encoding="utf-8")
            total_lines = max(1, len(source.splitlines()))
            py_edges, symbols, max_depth, unused_imports = _analyze_python_ast_single_pass(source, src_rel, py_module_map)
            code_edges.extend(py_edges)
        except Exception:  # noqa: silent-except
            pass
        intel_map[src_rel] = {
            "file_path": src_rel, "language": "python", "total_lines": total_lines, "symbols": symbols, "pi_registrations": [],
            "command_conflicts": [], "imports": [], "imported_by": [], "governing_specs": [], "max_nesting_depth": max_depth, "unused_imports": unused_imports,
        }
    for ts_file in ts_js_files:
        src_rel = str(ts_file.relative_to(project_root)).replace("\\", "/")
        ts_edges, ts_info = _scan_ts_file_single_pass(ts_file, src_rel, project_root, brain_rel, prompt_commands)
        code_edges.extend(ts_edges)
        intel_map[src_rel] = ts_info
    for edge in code_edges:
        src, dst = edge.get("from", ""), edge.get("to", "")
        if src in intel_map and dst and dst not in intel_map[src]["imports"]: intel_map[src]["imports"].append(dst)
        if dst in intel_map and src and src not in intel_map[dst]["imported_by"]: intel_map[dst]["imported_by"].append(src)
    _bind_governing_specs(entries, intel_map)
    return code_edges, intel_map


def _extract_file_symbols(fp: Path) -> Set[str]:
    """Extract defined Python symbols (defs/classes/top-level vars) or exported TS/JS symbols."""
    try: src = fp.read_text(encoding="utf-8")
    except Exception: return set()  # noqa: silent-except
    if fp.suffix == ".py":
        try: tree = ast.parse(src)
        except Exception: return set()  # noqa: silent-except
        syms = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for node in tree.body:
            if isinstance(node, ast.Assign): syms.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name): syms.add(node.target.id)
        return syms
    if fp.suffix in {".ts", ".tsx", ".js", ".jsx"}: return {m.group(2) for ln in src.splitlines() if (m := TS_EXPORT_SYMBOL_RE.match(ln))}
    return set()


def _filter_code_paths(paths: List[str], project_root: Path) -> List[str]:
    return [norm for p in (paths if isinstance(paths, list) else []) if isinstance(p, str) and (norm := p.strip().replace("\\", "/")).endswith((".py", ".ts")) and not Path(norm).name.startswith("test_") and (project_root / norm).is_file()]


def verify_spec_ast_symbols(body: str, affected_paths: List[str], stub_paths: List[str], project_root: Path) -> List[str]:
    """Verify spec/blueprint mentions real AST symbols in bound affected_paths/stub_paths unless declaring new symbols."""
    code_affected, code_stubs = _filter_code_paths(affected_paths, project_root), _filter_code_paths(stub_paths, project_root)
    if not code_affected and not code_stubs: return []
    errors: List[str] = []
    has_new_intent = bool(re.search(r"(?:新增|新建|預計新增|\bnew\s+(?:function|class|symbol|helper|method)\b|\bstub\b)", body, re.I))
    path_syms = {rel: _extract_file_symbols(project_root / rel) for rel in dict.fromkeys(code_affected + code_stubs)}
    if not has_new_intent:
        for m in re.finditer(r"([A-Za-z0-9_./-]+\.(?:py|ts)):([A-Za-z_][A-Za-z0-9_]*)", body):
            if path_syms.get(m.group(1)) and m.group(2) not in path_syms[m.group(1)]:
                errors.append(f"[SPEC-AST-SYNC-GATE] `{m.group(1)}:{m.group(2)}` 不存在於 AST；實際符號: {', '.join(sorted(path_syms[m.group(1)])[:10])}")
    for rel in code_stubs:
        if path_syms.get(rel) and not any(s in body for s in path_syms[rel]):
            errors.append(f"[SPEC-AST-SYNC-GATE] stub `{rel}` 未於內文對齊任何既有 AST 符號；實際符號: {', '.join(sorted(path_syms[rel])[:10])}")
    all_aff = {s for rel in code_affected for s in path_syms.get(rel, set())}
    if all_aff and not has_new_intent and not any(s in body for s in all_aff):
        errors.append(f"[SPEC-AST-SYNC-GATE] 規格綁定之程式碼 ({', '.join(code_affected[:3])}) 未於內文對齊任何既有 AST 符號；實際符號包含: {', '.join(sorted(all_aff)[:10])}。請對齊真實符號名稱或標註『新增』。")
    return errors


scan_workspace_code_single_pass = scan_code_intelligence_single_pass
