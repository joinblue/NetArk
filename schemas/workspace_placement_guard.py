#!/usr/bin/env python3
"""NetArk Workspace Placement & SSRF/IPI Guard (workspace_placement_guard.py).
Governing Node: 100.ARCH-RULES.v1 (SEC-CODE-PLACEMENT, SEC-SSRF, SEC-XPIA-WEB) & 100.SHARD-AST-DLP-GUARD.v1.
Enforces multi-project placement, SSRF/IPI web guards, and AST P3/P4 static checks (pure Python stdlib)."""

from __future__ import annotations

import ast, fnmatch, json, re, shlex, sys, time, urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas.ribc_gate import consume_readonly_subagent_lease, load_read_guard_state, save_read_guard_state  # noqa: E402

CODE_FILE_EXTS = (".py", ".ts", ".js", ".mjs", ".sh")
SCRATCH_PREFIXES = ("test_", "probe_", "debug_", "tmp_", "scratch_")
PROJECT_SUBDIRS = {"src", "scripts", "tests", "configs"}
APPROVED_CODE_ROOTS = {"projects", "scratch", "schemas", "scripts", "dashboard", "templates", "src", "tests", ".netark", ".agents", ".claude"}
WEB_TOOLS = {"web_fetch", "search_web", "read_url_content", "http_request", "web_research"}
READ_TOOLS_E1, SHELL_TOOLS_E1 = {"read_file", "view_file", "read"}, {"bash", "run_command", "shell", "exec_command"}
PRIVATE_HOST_RE = re.compile(r"^(?:localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[0-1])\.\d+\.\d+|169\.254\.\d+\.\d+|0\.0\.0\.0|\[?::1\]?|\[?fe80:[^\]]*\]?|\[?fc00:[^\]]*\]?|\[?fd[0-9a-f]{2}:[^\]]*\]?)$", re.I)
SECRET_QUERY_RE = re.compile(r"(?:[?&](?:api[_-]?key|token|secret|password|access[_-]?token|auth)=[^&\s]{8,}|://[^:]+:[^@]+@|nvapi-[a-zA-Z0-9_-]{16,}|sk-(?:proj-|svcacct-|ant-)?[a-zA-Z0-9_-]{16,}|AIza[0-9A-Za-z-_]{25,}|ghp_[0-9A-Za-z]{20,}|BEGIN\s+(?:RSA|OPENSSH|EC)\s+PRIVATE\s+KEY)", re.I)
IPI_DETERMINISTIC_RE = re.compile(r"(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|system\s+prompt\s+override|you\s+are\s+now\s+in\s+developer\s+mode|<\s*system\s*>|\[system\s*instruction\]|curl\s+[^\n]*\|\s*(?:sh|bash)|rm\s+-rf\s+\/)", re.I)
SPEC_FILENAME_RE = re.compile(r"^(\d{3})_(\d{2})_((?!\d+_)[A-Z0-9_]+)\.md$")
WIKI_FILENAME_RE = re.compile(r"^(\d{3})_(\d{2}(?:_\d+)?)_([A-Z0-9_]+)\.md$")
SLICE_ROW_RE = re.compile(r"(?m)^\|\s*\*{0,2}(?:S[1-9]|A[1-9]|M[1-9]|H[1-9]|P[0-9]|Slice\s*[1-9]|切片\s*[1-9一二三四])")
GOVERNED_PY_RE = re.compile(r"^(?:schemas/.+|scripts/.+|dashboard/backend/.+|projects/[^/]+/(?:src|scripts)/.+)\.py$")


def check_web_and_ssrf_guard(tool_name: str, args: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    tool, safe_args = (tool_name or "").lower(), (args if isinstance(args, dict) else {})
    pol = policy if isinstance(policy, dict) else {}
    raw_hosts = pol.get("ssrf_allowed_hosts")
    allowed_hosts = {str(h).strip().lower() for h in raw_hosts if isinstance(h, str) and str(h).strip()} if isinstance(raw_hosts, (list, tuple, set)) else set()
    url_val = next((str(safe_args[k]) for k in ("url", "Url", "uri", "Uri", "endpoint") if safe_args.get(k)), "")
    if url_val:
        if SECRET_QUERY_RE.search(url_val):
            return {"allowed": False, "code": "SEC-WEB-SECRET-QUERY", "reason": "Outbound URL contains sensitive secret or token parameter."}
        try: parsed = urllib.parse.urlparse(url_val)
        except ValueError: return {"allowed": False, "code": "SEC-SSRF", "reason": f"Malformed URL syntax: '{url_val}'."}
        if parsed.scheme.lower() not in ("http", "https"):
            return {"allowed": False, "code": "SEC-SSRF", "reason": f"Disallowed URL scheme '{parsed.scheme}'. Only http and https are permitted."}
        host = (parsed.hostname or "").lower()
        is_private = bool(PRIVATE_HOST_RE.match(host) or host.endswith((".local", ".internal")))
        if is_private and (host.startswith("169.254.") or "::ffff:169.254." in host or host not in allowed_hosts):
            return {"allowed": False, "code": "SEC-SSRF", "reason": f"SSRF Protection: access to private/loopback/internal host '{host}' is forbidden."}
    if tool in WEB_TOOLS:
        for qk in ("query", "untrusted_input"):
            qv = str(safe_args.get(qk) or "")
            if qv and SECRET_QUERY_RE.search(qv):
                return {"allowed": False, "code": "SEC-WEB-SECRET-QUERY", "reason": f"Web parameter '{qk}' contains sensitive secret or token."}
            if qv and IPI_DETERMINISTIC_RE.search(qv):
                return {"allowed": False, "code": "SEC-XPIA-WEB", "reason": f"Web parameter '{qk}' matched deterministic Indirect Prompt Injection (IPI) pattern."}
    return None


def check_code_placement(rel_path: str, cwd: str, policy: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    rel = (rel_path or "").replace("\\", "/").lstrip("./")
    if not rel or not rel.lower().endswith(CODE_FILE_EXTS): return None
    pol = policy if isinstance(policy, dict) else {}
    raw_roots, raw_subs = pol.get("approved_code_roots"), pol.get("project_subdirs")
    roots = {str(r).strip().strip("/") for r in raw_roots if str(r).strip()} if isinstance(raw_roots, (list, tuple, set)) else APPROVED_CODE_ROOTS
    subdirs = {str(s).strip().strip("/") for s in raw_subs if str(s).strip()} if isinstance(raw_subs, (list, tuple, set)) else PROJECT_SUBDIRS
    root = Path(cwd or ".").resolve()
    existing_projects = [p.name for p in sorted((root / "projects").iterdir()) if p.is_dir() and not p.name.startswith(".")] if (root / "projects").is_dir() else []
    proj_hint = f" Existing projects: {existing_projects}." if existing_projects else ""
    if "/" not in rel:
        return {"allowed": False, "code": "SEC-CODE-PLACEMENT", "reason": f"Writing code directly in workspace root ('{rel}') is prohibited. Place code under 'projects/<project_id>/{{src,scripts,tests,configs}}/' or scratch tests under 'scratch/test_<name>.py'.{proj_hint}"}
    parts = rel.split("/")
    if rel.startswith("scratch/"):
        fname = Path(rel).name
        if not fname.startswith(SCRATCH_PREFIXES):
            return {"allowed": False, "code": "SEC-CODE-PLACEMENT", "reason": f"Code files in scratch/ must start with one of {SCRATCH_PREFIXES} (got '{fname}'). For business code, place under 'projects/<project_id>/{{src,scripts,tests,configs}}/'.{proj_hint}"}
        return None
    if rel.startswith("projects/"):
        if len(parts) < 3 or parts[2] not in subdirs:
            return {"allowed": False, "code": "SEC-CODE-PLACEMENT", "reason": f"Project code '{rel}' must reside within a valid project subdirectory {sorted(subdirs)} (e.g. 'projects/<project_id>/src/...').{proj_hint}"}
        return None
    if parts[0] not in roots and (root / "memory" / "codex").exists():
        return {"allowed": False, "code": "SEC-CODE-PLACEMENT", "reason": f"Root folder '{parts[0]}' is not an approved code root in NetArk. Approved roots: {sorted(roots)}.{proj_hint}"}
    return None


def check_spec_filename_format(rel_path: str, cwd: str) -> Optional[Dict[str, Any]]:
    """Enforce <domain>_<2-digit-seq>_<UPPER_SLUG>.md naming & unique seq in specs/."""
    rel = rel_path.replace("\\", "/").lstrip("./")
    if not rel.endswith(".md"):
        return None
    parts = rel.split("/")
    in_mem = len(parts) == 3 and parts[0] == "memory" and parts[1] in {"specs", "audits", "wiki"}
    in_proj = len(parts) == 4 and parts[0] == "projects" and bool(parts[1]) and parts[2] in {"specs", "audits", "wiki"}
    if not (in_mem or in_proj) or parts[-1] in {"README.md", "INDEX.md"}:
        return None
    fname, parent_rel = parts[-1], "/".join(parts[:-1])
    pat = WIKI_FILENAME_RE if parts[-2] == "wiki" else SPEC_FILENAME_RE
    m = pat.match(fname)
    if m:
        dom, seq, slug = m.group(1), m.group(2), m.group(3)
    else:
        m_dom = re.match(r"^(\d{3})(?:[_-]+(.*)|$)", Path(fname).stem)
        dom = m_dom.group(1) if m_dom else "500"
        raw_slug = re.sub(r"^\d{2}(?:_\d+)?[_-]+", "", m_dom.group(2) or "") if m_dom else Path(fname).stem
        slug = re.sub(r"[^A-Z0-9]+", "_", raw_slug.upper()).strip("_") or "SPEC"
        seq = ""
    specs_dir = Path(cwd).resolve() / parent_rel
    existing = [p for p in sorted(specs_dir.glob(f"{dom}_*.md")) if p.is_file()] if specs_dir.is_dir() else []
    has_dup = bool(seq) and any(p.name != fname and p.name.startswith(f"{dom}_{seq}_") for p in existing)
    if m and not has_dup:
        return None
    max_seq = max((int(pm.group(1)) for p in existing if (pm := re.match(rf"^{dom}_(\d{{2}})_", p.name))), default=0)
    next_name = f"{dom}_{max_seq + 1:02d}_{slug}.md"
    issue = f"Duplicate spec sequence '{dom}_{seq}_' in '{parent_rel}/'" if has_dup else f"Invalid spec filename '{fname}'"
    return {"allowed": False, "code": "SPEC-FILENAME-FORMAT", "reason": f"{issue}. Must match '<domain>_<2-digit-seq>_<UPPER_SLUG>.md'. Suggested next filename: '{parent_rel}/{next_name}'"}


def _iter_child_stmts(stmt: ast.AST) -> List[ast.stmt]:
    res: List[ast.stmt] = []
    for child in ast.iter_child_nodes(stmt):
        if isinstance(child, ast.stmt): res.append(child)
        elif isinstance(child, list): res.extend(c for c in child if isinstance(c, ast.stmt))
        elif isinstance(child, ast.ExceptHandler): res.extend(child.body)
        elif hasattr(ast, "match_case") and isinstance(child, ast.match_case): res.extend(child.body)
    return res


def _max_loop_depth(stmts: List[ast.stmt], current_depth: int = 0) -> int:
    best = current_depth
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): continue
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            d = current_depth + 1
            best = max(best, d)
            for attr in ("body", "orelse"):
                best = max(best, _max_loop_depth(getattr(stmt, attr, []) or [], d))
        elif (child_stmts := _iter_child_stmts(stmt)):
            best = max(best, _max_loop_depth(child_stmts, current_depth))
    return best


def _effective_func_lines(node: ast.AST, lines: List[str]) -> int:
    """Count effective function lines excluding docstrings, comments, and blank lines."""
    start_ln, end_ln = max(1, getattr(node, "lineno", 1)), getattr(node, "end_lineno", None) or max(1, getattr(node, "lineno", 1))
    doc_lines: Set[int] = set()
    for sub in ast.walk(node):
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and sub.body:
            first = sub.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                doc_lines.update(range(first.lineno, (getattr(first, "end_lineno", None) or first.lineno) + 1))
    return sum(1 for idx in range(start_ln, min(end_ln, len(lines)) + 1) if idx not in doc_lines and (st := lines[idx - 1].strip()) and not st.startswith("#"))


def check_ast_p3_p4(tree: ast.AST, lines: List[str], rel_path: str, max_loop_depth: int = 2, max_func_lines: int = 70) -> Optional[Dict[str, Any]]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ln = getattr(node, "lineno", 1)
            def_line = lines[ln - 1] if 1 <= ln <= len(lines) else ""
            loop_depth = _max_loop_depth(node.body, 0)
            if loop_depth > max_loop_depth and "noqa: nested-loops" not in def_line.lower():
                return {"allowed": False, "code": "CODE-NESTED-LOOPS", "function": node.name, "depth": loop_depth, "line": ln, "reason": f"[P3 CODE-NESTED-LOOPS] Function '{node.name}' in '{rel_path}' reaches loop nesting depth {loop_depth} (> {max_loop_depth} max allowed, line {ln}). Flatten loops or use vectorization/lookup tables."}
            span = _effective_func_lines(node, lines)
            if span > max_func_lines and "noqa: god-function" not in def_line.lower():
                return {"allowed": False, "code": "CODE-GOD-FUNCTION", "function": node.name, "lines": span, "line": ln, "reason": f"[P4 CODE-GOD-FUNCTION] Function '{node.name}' in '{rel_path}' is {span} effective lines long (> {max_func_lines} max allowed, line {ln}). Refactor into smaller helper functions."}
    return None


def _parse_read_span(args: Dict[str, Any], total_lines: int) -> Tuple[int, bool]:
    def _num(keys: Tuple[str, ...]) -> Optional[int]:
        for k in keys:
            if args.get(k) not in (None, ""):
                try: return int(args[k])
                except (TypeError, ValueError): pass  # noqa: silent-except
        return None
    s_ln, e_ln = _num(("StartLine", "start_line")), _num(("EndLine", "end_line"))
    if s_ln is not None or e_ln is not None:
        return max(1, (min(total_lines, e_ln) if e_ln is not None else total_lines) - max(1, s_ln or 1) + 1), True
    offset, limit = _num(("offset", "Offset")), _num(("limit", "Limit"))
    if limit is not None: return max(1, limit), True
    if offset is not None: return max(1, total_lines - max(1, offset) + 1), True
    return total_lines, False


def _split_shell_segments(cmd_str: str) -> List[str]:
    segs, cur, q, i, n = [], [], "", 0, len(cmd_str)
    while i < n:
        ch = cmd_str[i]
        if q:
            cur.append(ch)
            if ch == "\\" and q != "'" and i + 1 < n: cur.append(cmd_str[i + 1]); i += 1
            elif ch == q: q = ""
        elif ch in ("'", '"'): q = ch; cur.append(ch)
        elif cmd_str[i:i + 2] in ("&&", "||") or ch in (";", "|", "\n"):
            if (s := "".join(cur).strip()): segs.append(s)
            cur, i = [], i + (1 if cmd_str[i:i + 2] in ("&&", "||") else 0)
        else: cur.append(ch)
        i += 1
    return segs + ([s] if (s := "".join(cur).strip()) else [])


def _resolve_in_root(raw: str, root: Path) -> Optional[Path]:
    if not raw: return None
    try:
        p = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        return p if p.is_file() and p.is_relative_to(root) else None
    except (OSError, ValueError): return None


def _extract_shell_dump_targets(cmd_str: str, root: Path) -> List[Path]:
    root_p, targets = Path(root).resolve(), []
    for seg in _split_shell_segments(cmd_str):
        try: tokens = shlex.split(seg, posix=True)
        except ValueError: tokens = seg.split()
        while tokens and (("=" in tokens[0] and not tokens[0].startswith("-")) or tokens[0] in {"sudo", "env", "command", "nohup"}):
            tokens.pop(0)
        if not tokens: continue
        cmd, args, cands = Path(tokens[0]).name.lower(), tokens[1:], []
        if cmd in {"cat", "head", "tail", "sed", "awk"}:
            cands = [a.lstrip("<") for a in args if not a.startswith("-") and a != "<"]
        elif cmd in {"python", "python3"} and any(fn in seg for fn in ("open(", "read_text(", "readlines(")):
            for a in args:
                cands.extend(m[0] or m[1] for m in re.findall(r"'([^'\n]+)'|\"([^\"\n]+)\"", a))
                if not a.startswith("-"): cands.append(a)
        for raw in cands:
            if (rp := _resolve_in_root(raw, root_p)): targets.append(rp)
    return targets


def _check_large_rel(target: Path, root: Path, exempt: Set[str], max_lines: int) -> Tuple[Optional[str], int]:
    try: rel = str(target.relative_to(root)).replace("\\", "/")
    except ValueError: return None, 0
    if rel in exempt or any(fnmatch.fnmatch(rel, pat) for pat in exempt): return None, 0
    try: total = len(target.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError: return None, 0
    return (rel, total) if total > max_lines else (None, 0)


def check_direct_read_guard(tool_name: str, args: Dict[str, Any], cwd: str, policy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Block unleased large-file direct reads, salami-slicing, and shell read dumps (SIDECAR-GATE)."""
    tool = (tool_name or "").lower()
    max_lines = 300 if policy.get("max_direct_read_lines") is None else int(policy["max_direct_read_lines"])
    if max_lines <= 0 or tool not in (READ_TOOLS_E1 | SHELL_TOOLS_E1): return None
    max_slices = 2 if policy.get("max_salami_slices_per_file") is None else int(policy["max_salami_slices_per_file"])
    exempt = set(policy.get("read_guard_exempt_paths") if policy.get("read_guard_exempt_paths") is not None else ["memory/codex/CONTEXT_MAP.md"])
    root = Path(cwd).resolve()
    if tool in SHELL_TOOLS_E1:
        cmd_str = str(args.get("command") or args.get("CommandLine") or "")
        large = [rel for p in _extract_shell_dump_targets(cmd_str, root) if (rel := _check_large_rel(p, root, exempt, max_lines)[0])]
        if large and not consume_readonly_subagent_lease(cwd):
            return {"allowed": False, "code": "SIDECAR-GATE", "reason": f"Direct shell read of large file '{large[0]}' (> {max_lines} lines) is blocked. Delegate to invoke_subagent(TypeName='research') / Task(subagent_type='Explore')."}
        return None
    raw_path = str(args.get("path") or args.get("Path") or args.get("file_path") or args.get("TargetFile") or args.get("file") or "")
    if not raw_path or not (target := _resolve_in_root(raw_path, root)): return None
    rel, total = _check_large_rel(target, root, exempt, max_lines)
    if not rel: return None
    span, _ = _parse_read_span(args, total)
    if consume_readonly_subagent_lease(cwd):
        return None if span <= max_lines else {"allowed": False, "code": "SIDECAR-GATE", "reason": f"Subagent read span {span} lines on '{rel}' exceeds {max_lines}. Chunk reads <= {max_lines} lines."}
    if span > max_lines:
        return {"allowed": False, "code": "SIDECAR-GATE", "reason": f"Direct read of '{rel}' ({span}/{total} lines > {max_lines}) is blocked. Delegate to invoke_subagent(TypeName='research') / Task(subagent_type='Explore')."}
    state, now = load_read_guard_state(cwd), time.time()
    raw_sl = state.get("slices") if isinstance(state.get("slices"), dict) else {}
    slices = {k: r for k, v in raw_sl.items() if isinstance(v, list) and (r := [float(t) for t in v if now - float(t) < 120.0])}
    slices.setdefault(rel, []).append(now)
    state["slices"] = slices
    save_read_guard_state(cwd, state)
    if len(slices[rel]) > max_slices or len(slices) >= 2:
        return {"allowed": False, "code": "SIDECAR-GATE", "reason": f"Blocked salami-slicing on '{rel}' ({total} lines > {max_lines}). Delegate to invoke_subagent(TypeName='research') / Task(subagent_type='Explore')."}
    return None


def parse_frontmatter_text(raw_text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Parse YAML or JSON frontmatter and body from an in-memory Markdown string."""
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n([\s\S]*))?$", raw_text.lstrip("\ufeff"))
    if not m: return None, raw_text
    raw_fm, body = m.group(1), m.group(2) or ""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw_fm)
    except ImportError:
        from schemas.yaml_lite import _parse_simple_yaml
        try: data = _parse_simple_yaml(raw_fm)
        except (ValueError, TypeError): return None, body
    except Exception: return None, body
    return (data if isinstance(data, dict) else None), body


def _safe_int(val: Any) -> int:
    try: return int(val or 0)
    except (TypeError, ValueError): return 0


def check_spec_blueprint_required(fm: Any, body: str, rel_path: str = "") -> Optional[Dict[str, Any]]:
    """Block composite specs that omit topology.parent_blueprint (SPEC-BLUEPRINT-REQUIRED)."""
    if not isinstance(fm, dict) or fm.get("artifact_type") != "spec": return None
    ctx = fm.get("context_index") if isinstance(fm.get("context_index"), dict) else {}
    if Path(rel_path).name == "LEDGER.md" or str(ctx.get("node_key") or "") == "300.LEDGER.v1": return None
    scope = fm.get("scope_profile") if isinstance(fm.get("scope_profile"), dict) else {}
    topo = fm.get("topology") if isinstance(fm.get("topology"), dict) else {}
    aff = topo.get("affected_paths") if isinstance(topo.get("affected_paths"), list) else []
    stubs = topo.get("stub_paths") if isinstance(topo.get("stub_paths"), list) else []
    code_paths = {str(p).strip().replace("\\", "/").lstrip("./") for p in (*aff, *stubs) if isinstance(p, str) and str(p).strip().lower().endswith(CODE_FILE_EXTS)}
    is_composite = (
        scope.get("complexity_tier") == "composite" or _safe_int(scope.get("new_modules_count")) >= 1 or _safe_int(scope.get("target_files_count")) >= 3
        or bool(scope.get("requires_new_algorithm")) or len(code_paths) >= 3 or len(SLICE_ROW_RE.findall(body or "")) >= 2
    )
    if not is_composite or str(topo.get("parent_blueprint") or "").strip(): return None
    return {"allowed": False, "code": "SPEC-BLUEPRINT-REQUIRED", "reason": "[SPEC-BLUEPRINT-REQUIRED] Composite spec requires a valid 'topology.parent_blueprint' before writing. Create a Master Blueprint first, then bind this shard spec via parent_blueprint."}


def _top_level_defs(source: str) -> Set[str]:
    """Extract top-level function and class names from Python source."""
    if not source.strip(): return set()
    try:
        tree = ast.parse(source)
        return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    except SyntaxError:
        return set(re.findall(r"(?m)^(?:async\s+def|def|class)\s+([A-Za-z_]\w*)", source))


def _scan_stub_bindings(rel: str, cwd: str) -> Tuple[bool, bool]:
    """Return (has_active_work_auth, has_any_valid_binding) for rel across memory/*.md."""
    mem_dir = Path(cwd).resolve() / "memory"
    if not mem_dir.is_dir(): return False, False
    from schemas.topology_graph import parse_markdown_frontmatter
    has_active, has_any = False, False
    for md_path in sorted(mem_dir.rglob("*.md")):
        if md_path.name == "CONTEXT_MAP.md": continue
        try: fm, _ = parse_markdown_frontmatter(md_path)
        except Exception: continue
        topo = fm.get("topology") if isinstance(fm.get("topology"), dict) else {}
        bound = {str(p).strip().replace("\\", "/").lstrip("./") for k in ("affected_paths", "stub_paths", "verified_by") for p in (topo.get(k) if isinstance(topo.get(k), list) else []) if isinstance(p, str) and p.strip()}
        if rel not in bound: continue
        art, status = str(fm.get("artifact_type") or ""), str(fm.get("status") or "")
        if (art in ("spec", "blueprint") and status == "stub_ready") or (art == "audit" and status in ("draft", "reviewing", "verified")): has_active = True
        if (art in ("spec", "blueprint") and status in ("stub_ready", "verified")) or (art in ("constitution", "rule", "adr") and status == "verified"): has_any = True
        if has_active and has_any: return True, True
    return has_active, has_any


def check_stub_first_gate(rel_path: str, old_text: str, new_text: str, existed: bool, cwd: str, policy: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Enforce STUB-FIRST-GATE on governed .py modules before creation or major edits."""
    pol = policy if isinstance(policy, dict) else {}
    if pol.get("enforce_stub_first_for_new_modules") is False: return None
    rel = (rel_path or "").replace("\\", "/").lstrip("./")
    fname = Path(rel).name
    if rel.startswith("scratch/") or fname == "__init__.py" or fname.startswith("test_") or fname.endswith("_test.py") or not GOVERNED_PY_RE.match(rel): return None
    has_active, has_any = _scan_stub_bindings(rel, cwd or ".")
    if not existed:
        if has_any: return None
        return {"allowed": False, "code": "STUB-FIRST-GATE", "reason": f"[STUB-FIRST-GATE] Creating new governed module '{rel}' is blocked because no 'stub_ready' or 'verified' Spec binds it in stub_paths/affected_paths. Follow: note -> blueprint -> shard spec (stub_ready) -> code."}
    if has_active: return None
    from schemas.code_hygiene_ast import count_effective_code_lines
    old_s, new_s = old_text or "", new_text or ""
    delta_eff = count_effective_code_lines(new_s, ".py") - count_effective_code_lines(old_s, ".py")
    added_defs = _top_level_defs(new_s) - _top_level_defs(old_s)
    try:
        raw_d = pol.get("stub_first_edit_delta_lines")
        delta_limit = int(25 if raw_d is None else raw_d)
    except (TypeError, ValueError):
        delta_limit = 25
    if delta_limit <= 0: delta_limit = 25
    if delta_eff >= delta_limit or added_defs:
        return {"allowed": False, "ask_confirmation": True, "code": "STUB-FIRST-GATE", "reason": f"[STUB-FIRST-GATE] Modifying existing module '{rel}' (+{delta_eff} effective lines or new top-level symbols {sorted(added_defs)[:4]}) without an active 'stub_ready' Spec or Audit requires confirmation."}
    return None
