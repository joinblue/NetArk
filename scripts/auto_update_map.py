#!/usr/bin/env python3
"""
NetArk Context Index, Code Intelligence & @D/@C/@G Codebook Map Compiler (auto_update_map.py)
=============================================================================================
Scans all governed memory nodes in `memory/` and workspace source code (excluding `.gitignore`):
1. Automatically heals broken relative Markdown links (`heal_dead_links`),
2. Dynamically discovers workspace `.py`/`.ts`/`.js` files and dependencies (`scan_code_dependencies`),
3. Enforces G-05 plaintext secret pre-index guard (`scan_plaintext_secrets`),
4. Compiles `memory/index/CONTEXT_INDEX.json` including Turn-1 Frozen `@D/@C/@G` `codebook_map` (L1/L2/L3),
5. Renders `memory/codex/CONTEXT_MAP.md` for Agentic Context Engineering.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schemas"))
from netark_guard_core import scan_plaintext_secrets  # type: ignore
from schema_validator import (  # type: ignore
    detect_unlinked_topology_references,
    is_gitignored_path,
    parse_markdown_frontmatter,
)

DEFAULT_DOMAIN_LAYERS = {
    "000": "000 核心憲法與認知規範 (Core Constitution & Epistemic Rules)",
    "100": "100 安全邊界與工作區護欄 (Workspace Boundary & Security Guard)",
    "200": "200 架構決策與跨模型審查 (Architecture Decisions & Cross-Review)",
    "300": "300 核心領域邏輯與模組 (Core Domain Modules)",
    "310": "310 知識庫 Wiki 與圖譜筆記 (Library Wiki & Knowledge Graph Notes)",
    "320": "320 領域工作流程與標準作業程序 (Domain Workflows & SOPs)",
    "330": "330 領域詞彙表與本體庫 (Domain Glossaries & Ontologies)",
    "400": "400 工具鏈、Hooks 與擴充套件 (Tools, Hooks & Extensions)",
    "500": "500 動態模型路由與子代理編排 (Model Routing & Subagents)",
    "510": "510 模型池與路由策略 (Model Pool & Routing Strategy)",
    "600": "600 驗證斷言、測試與安全稽核 (Verification Oracles & Audits)",
    "700": "700 可攜式部署與容器封裝 (Portable Brain & Containerization)",
    "800": "800 外部規格與參考文獻 (External Specs & References)",
    "900": "900 歷史封存與交接節點 (Episodic Handover & Archived Nodes)",
    "910": "910 情節交接與會話狀態 (Episodic Handover & Session State)",
}

EXCLUDED_SCAN_DIRS = {
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "dist",
    "build",
    "scratch",
    ".staging",
    "dashboard",
    "templates",
    "__pycache__",
    ".pytest_cache",
    ".agents",
    ".claude",
    ".github",
    "memory",
}

OFFICIAL_TYPES = {"constitution", "rule", "adr", "blueprint", "spec", "audit"}
WIKI_TYPES = {"wiki", "note", "sop", "glossary", "digest"}
WIKILINK_RE = re.compile(r"\[\[([A-Za-z0-9_.-]+)(?:\|[^\]]+)?\]\]")
MD_LINK_PATTERN = re.compile(r"(\[[^\]]+\]\()([^)\s]+)(\))")
TS_IMPORT_PATTERN = re.compile(r"""(?m)^\s*import\s+(?:type\s+)?(?:[^"']+from\s+)?["']([^"']+)["']""")
TS_EXPORT_SYMBOL_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|const|interface|type)\s+([A-Za-z0-9_]+)"
)
TS_REGISTER_COMMAND_RE = re.compile(r"""pi\.registerCommand\(\s*["']([^"']+)["']""")
TS_REGISTER_TOOL_RE = re.compile(r"""pi\.registerTool\(\s*\{[\s\S]*?name\s*:\s*["']([^"']+)["']""")
TS_ON_HOOK_RE = re.compile(r"""pi\.on\(\s*["']([^"']+)["']""")


def get_brain_rel_dir(project_root: Path) -> str:
    env_dir = os.environ.get("PI_CODING_AGENT_DIR")
    if env_dir:
        try:
            rel = Path(env_dir).resolve().relative_to(project_root.resolve())
            return str(rel).replace("\\", "/")
        except Exception:
            pass
    return ".netark"


def load_domain_layers(project_root: Path) -> Dict[str, str]:
    tax_path = project_root / "memory" / "index" / "TAXONOMY.json"
    if tax_path.exists():
        try:
            data = json.loads(tax_path.read_text(encoding="utf-8"))
            domains = data.get("domains", {})
            layers: Dict[str, str] = {}
            for k, v in domains.items():
                title = v.get("title", k) if isinstance(v, dict) else str(v)
                layers[str(k)] = f"{k} {title}"
                if isinstance(v, dict):
                    subs = v.get("subdomains", {})
                    if isinstance(subs, dict):
                        for sk, sv_obj in subs.items():
                            stitle = sv_obj.get("title", sk) if isinstance(sv_obj, dict) else str(sv_obj)
                            layers[str(sk)] = f"{sk} {stitle}"
            for k, v in DEFAULT_DOMAIN_LAYERS.items():
                if k not in layers:
                    layers[k] = v
            return layers
        except Exception:
            pass
    return dict(DEFAULT_DOMAIN_LAYERS)


def extract_wikilinks_outside_fenced_blocks(body: str) -> List[str]:
    links: List[str] = []
    in_fence = False
    for line in body.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in WIKILINK_RE.finditer(line):
            links.append(match.group(1))
    return sorted(list(set(links)))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def discover_workspace_code_files(project_root: Path) -> Tuple[List[Path], List[Path]]:
    """D-07 & G-05: Dynamically discover all business .py/.ts/.js files while respecting .gitignore and exclusions."""
    brain_rel = get_brain_rel_dir(project_root)
    py_files: List[Path] = []
    ts_js_files: List[Path] = []

    for root, dirs, files in os.walk(project_root):
        rel_root = Path(root).resolve().relative_to(project_root.resolve())
        rel_root_str = "" if str(rel_root) == "." else str(rel_root).replace("\\", "/")

        filtered_dirs: List[str] = []
        for d in sorted(dirs):
            cand_rel = f"{rel_root_str}/{d}".lstrip("/")
            if d in EXCLUDED_SCAN_DIRS:
                continue
            if d.startswith(".") and cand_rel != brain_rel and not cand_rel.startswith(f"{brain_rel}/"):
                continue
            if cand_rel.startswith(f"{brain_rel}/") and cand_rel != f"{brain_rel}/extensions" and not cand_rel.startswith(f"{brain_rel}/extensions/"):
                continue
            if is_gitignored_path(cand_rel + "/", project_root) or is_gitignored_path(cand_rel, project_root):
                continue
            filtered_dirs.append(d)
        dirs[:] = filtered_dirs

        for fname in sorted(files):
            if fname.startswith("."):
                continue
            file_rel = f"{rel_root_str}/{fname}".lstrip("/")
            if is_gitignored_path(file_rel, project_root):
                continue
            fpath = Path(root) / fname
            if fname.endswith(".py"):
                py_files.append(fpath)
            elif fname.endswith((".ts", ".js", ".mjs")) and not fname.endswith(".d.ts"):
                ts_js_files.append(fpath)

    return py_files, ts_js_files


def heal_dead_links(project_root: Path, md_files: List[Path]) -> List[Dict[str, str]]:
    healed_records: List[Dict[str, str]] = []
    brain_rel = get_brain_rel_dir(project_root)
    basename_map: Dict[str, List[Path]] = {}
    for root_sub in ("memory", brain_rel, "schemas", "scripts"):
        sub_dir = project_root / root_sub
        if not sub_dir.exists():
            continue
        for p in sub_dir.rglob("*"):
            if p.is_file():
                rel_p = str(p.relative_to(project_root)).replace("\\", "/")
                if not is_gitignored_path(rel_p, project_root):
                    basename_map.setdefault(p.name, []).append(p)

    for md_path in md_files:
        raw_text = md_path.read_text(encoding="utf-8")
        lines = raw_text.splitlines(keepends=True)
        in_fence = False
        modified = False
        new_lines: List[str] = []

        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                new_lines.append(line)
                continue
            if in_fence:
                new_lines.append(line)
                continue

            def _replace_link(match: re.Match[str]) -> str:
                nonlocal modified
                prefix, raw_target, suffix = match.group(1), match.group(2), match.group(3)
                if raw_target.startswith(("http://", "https://", "mailto:", "#", "file://")):
                    return match.group(0)
                target_no_anchor = raw_target.split("#", 1)[0]
                anchor = ("#" + raw_target.split("#", 1)[1]) if "#" in raw_target else ""
                if not target_no_anchor:
                    return match.group(0)

                resolved = (md_path.parent / target_no_anchor).resolve()
                if resolved.exists():
                    return match.group(0)

                base_name = Path(target_no_anchor).name
                candidates = basename_map.get(base_name, [])
                if len(candidates) == 1:
                    found_path = candidates[0]
                    healed_rel = os.path.relpath(found_path, md_path.parent).replace("\\", "/") + anchor
                    modified = True
                    healed_records.append(
                        {
                            "file": str(md_path.relative_to(project_root)),
                            "old_target": raw_target,
                            "new_target": healed_rel,
                        }
                    )
                    return f"{prefix}{healed_rel}{suffix}"
                return match.group(0)

            new_lines.append(MD_LINK_PATTERN.sub(_replace_link, line))

        if modified:
            md_path.write_text("".join(new_lines), encoding="utf-8")

    return healed_records


def scan_code_dependencies(project_root: Path) -> List[Dict[str, str]]:
    """Dynamically parses Python files via `ast.parse` and TS/JS files via import regex across the workspace."""
    code_edges: List[Dict[str, str]] = []
    py_files, ts_js_files = discover_workspace_code_files(project_root)
    py_module_map: Dict[str, str] = {}

    for py_file in py_files:
        py_module_map[py_file.stem] = str(py_file.relative_to(project_root)).replace("\\", "/")

    for py_file in py_files:
        src_rel = str(py_file.relative_to(project_root)).replace("\\", "/")
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=src_rel)
        except Exception:
            continue
        seen_targets = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for mod_cand in (alias.name.split(".")[0], alias.name.split(".")[-1]):
                        if mod_cand in py_module_map and py_module_map[mod_cand] != src_rel:
                            target = py_module_map[mod_cand]
                            if target not in seen_targets:
                                seen_targets.add(target)
                                code_edges.append({"from": src_rel, "to": target, "type": "py_import"})
            elif isinstance(node, ast.ImportFrom) and node.module:
                for mod_cand in (node.module.split(".")[0], node.module.split(".")[-1]):
                    if mod_cand in py_module_map and py_module_map[mod_cand] != src_rel:
                        target = py_module_map[mod_cand]
                        if target not in seen_targets:
                            seen_targets.add(target)
                            code_edges.append({"from": src_rel, "to": target, "type": "py_from_import"})

    for ts_file in ts_js_files:
        src_rel = str(ts_file.relative_to(project_root)).replace("\\", "/")
        try:
            raw_ts = ts_file.read_text(encoding="utf-8")
        except Exception:
            continue
        seen_targets = set()
        for m in TS_IMPORT_PATTERN.finditer(raw_ts):
            spec = m.group(1)
            if spec.startswith("."):
                candidate = (ts_file.parent / spec).resolve()
                if candidate.suffix in (".js", ".mjs"):
                    ts_cand = candidate.with_suffix(".ts")
                    if ts_cand.exists():
                        candidate = ts_cand
                elif not candidate.suffix and candidate.with_suffix(".ts").exists():
                    candidate = candidate.with_suffix(".ts")
                if candidate.exists() and candidate.is_relative_to(project_root):
                    target = str(candidate.relative_to(project_root)).replace("\\", "/")
                    if target not in seen_targets:
                        seen_targets.add(target)
                        code_edges.append({"from": src_rel, "to": target, "type": "ts_local_import"})
            elif spec.startswith("@earendil-works/") or spec.startswith("@sinclair/"):
                if spec not in seen_targets:
                    seen_targets.add(spec)
                    code_edges.append({"from": src_rel, "to": spec, "type": "ts_sdk_import"})

    return code_edges


def build_code_intelligence_map(
    project_root: Path,
    entries: List[Dict[str, Any]],
    code_dependency_edges: List[Dict[str, str]],
) -> Dict[str, Dict[str, Any]]:
    """Build AST symbol coordinates, line counts, Pi hook/command/tool registrations, impact circles, and governing specs."""
    intel_map: Dict[str, Dict[str, Any]] = {}
    brain_rel = get_brain_rel_dir(project_root)
    prompts_dir = project_root / brain_rel / "prompts"
    prompt_commands = {p.stem for p in prompts_dir.glob("*.md")} if prompts_dir.exists() else set()

    py_files, ts_js_files = discover_workspace_code_files(project_root)

    for py_file in py_files:
        rel_path = str(py_file.relative_to(project_root)).replace("\\", "/")
        symbols: List[Dict[str, Any]] = []
        total_lines = 1
        try:
            source = py_file.read_text(encoding="utf-8")
            total_lines = max(1, len(source.splitlines()))
            tree = ast.parse(source, filename=str(py_file))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append({
                        "name": node.name,
                        "kind": "function",
                        "line_start": getattr(node, "lineno", 1),
                        "line_end": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                    })
                elif isinstance(node, ast.ClassDef):
                    symbols.append({
                        "name": node.name,
                        "kind": "class",
                        "line_start": getattr(node, "lineno", 1),
                        "line_end": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                    })
        except Exception:
            pass
        intel_map[rel_path] = {
            "file_path": rel_path,
            "language": "python",
            "total_lines": total_lines,
            "symbols": symbols,
            "pi_registrations": [],
            "command_conflicts": [],
            "imports": [],
            "imported_by": [],
            "governing_specs": [],
        }

    for ts_file in ts_js_files:
        rel_path = str(ts_file.relative_to(project_root)).replace("\\", "/")
        symbols = []
        pi_registrations: List[Dict[str, Any]] = []
        command_conflicts: List[str] = []
        total_lines = 1
        try:
            source = ts_file.read_text(encoding="utf-8")
            lines = source.splitlines()
            total_lines = max(1, len(lines))
            for idx, line in enumerate(lines, start=1):
                if line.lstrip().startswith("//"):
                    continue
                m_sym = TS_EXPORT_SYMBOL_RE.match(line)
                if m_sym:
                    symbols.append({
                        "name": m_sym.group(2),
                        "kind": m_sym.group(1),
                        "line_start": idx,
                        "line_end": idx,
                    })
                for m_cmd in TS_REGISTER_COMMAND_RE.finditer(line):
                    cmd_name = m_cmd.group(1)
                    pi_registrations.append({
                        "kind": "command",
                        "name": f"/{cmd_name}",
                        "line": idx,
                    })
                    if cmd_name in prompt_commands:
                        command_conflicts.append(
                            f"/{cmd_name} shadows {brain_rel}/prompts/{cmd_name}.md (L{idx})"
                        )
                for m_hook in TS_ON_HOOK_RE.finditer(line):
                    pi_registrations.append({
                        "kind": "hook",
                        "name": m_hook.group(1),
                        "line": idx,
                    })
            for m_tool in TS_REGISTER_TOOL_RE.finditer(source):
                tool_line = source[: m_tool.start()].count("\n") + 1
                pi_registrations.append({
                    "kind": "tool",
                    "name": m_tool.group(1),
                    "line": tool_line,
                })
        except Exception:
            pass
        intel_map[rel_path] = {
            "file_path": rel_path,
            "language": "typescript" if rel_path.endswith(".ts") else "javascript",
            "total_lines": total_lines,
            "symbols": symbols,
            "pi_registrations": sorted(pi_registrations, key=lambda x: (x["line"], x["name"])),
            "command_conflicts": command_conflicts,
            "imports": [],
            "imported_by": [],
            "governing_specs": [],
        }

    for edge in code_dependency_edges:
        src = edge.get("from", "")
        dst = edge.get("to", "")
        if src in intel_map and dst and dst not in intel_map[src]["imports"]:
            intel_map[src]["imports"].append(dst)
        if dst in intel_map and src and src not in intel_map[dst]["imported_by"]:
            intel_map[dst]["imported_by"].append(src)

    for entry in entries:
        node_id = str(entry.get("node_id") or entry.get("id") or "")
        node_key = str(entry.get("node_key") or "")
        node_title = str(entry.get("summary_1line") or entry.get("title") or "")
        node_path = str(entry.get("path") or entry.get("file_path") or "")
        combined_paths = list(entry.get("affected_paths", []) or []) + list(entry.get("stub_paths", []) or [])
        for aff in combined_paths:
            aff_str = str(aff).strip()
            if not aff_str:
                continue
            for code_path, info in intel_map.items():
                if (
                    code_path == aff_str
                    or code_path.startswith(aff_str.rstrip("/") + "/")
                    or aff_str == code_path
                ):
                    spec_ref = {
                        "node_id": node_id,
                        "node_key": node_key,
                        "summary_1line": node_title,
                        "path": node_path,
                    }
                    if spec_ref not in info["governing_specs"]:
                        info["governing_specs"].append(spec_ref)

    return intel_map


def build_codebook_map(
    project_root: Path,
    entries: List[Dict[str, Any]],
    intel_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """D-05: Compile Turn-1 Frozen @D/@C/@G Codebook Map with L1/L2/L3 scale tiering and reverse_lookup dictionary."""
    brain_rel = get_brain_rel_dir(project_root)
    active_entries = sorted(
        [e for e in entries if e.get("status") not in ("archived", "deprecated")],
        key=lambda e: (str(e.get("domain_code") or "999"), str(e.get("node_key") or ""), str(e.get("node_id") or "")),
    )
    total_scripts = len(intel_map)
    total_nodes = len(active_entries)

    if total_scripts <= 150 and total_nodes <= 80:
        tier = "L1-Full"
    elif total_scripts <= 1500:
        tier = "L2-Cluster"
    else:
        tier = "L3-ActiveCone"

    canonical_dirs = [
        ("M", "memory/"),
        ("C", "memory/codex/"),
        ("E", "memory/episodic/"),
        ("P", "memory/specs/"),
        ("W", "memory/wiki/"),
        ("A", "memory/audits/"),
        ("H", "schemas/"),
        ("S", "scripts/"),
        ("X", f"{brain_rel}/extensions/"),
        ("XS", f"{brain_rel}/extensions/subagent/"),
    ]
    dir_to_code: Dict[str, str] = {path: code for code, path in canonical_dirs}
    code_to_dir: Dict[str, str] = {code: path for code, path in canonical_dirs}
    used_dir_codes: List[str] = []
    dyn_dir_counter = 0

    def _register_dir(file_rel: str) -> Tuple[str, str]:
        nonlocal dyn_dir_counter
        parent = str(Path(file_rel).parent).replace("\\", "/")
        dir_prefix = "" if parent in ("", ".") else (parent.rstrip("/") + "/")
        if not dir_prefix:
            dir_prefix = "./"
        if dir_prefix not in dir_to_code:
            while f"D{dyn_dir_counter}" in code_to_dir:
                dyn_dir_counter += 1
            dcode = f"D{dyn_dir_counter}"
            dyn_dir_counter += 1
            dir_to_code[dir_prefix] = dcode
            code_to_dir[dcode] = dir_prefix
        dcode = dir_to_code[dir_prefix]
        if dcode not in used_dir_codes:
            used_dir_codes.append(dcode)
        return dcode, Path(file_rel).name

    # Prioritize core scripts in deterministic order
    priority_order = [
        "schemas/schema_validator.py",
        "schemas/netark_guard_core.py",
        "scripts/auto_update_map.py",
        "scripts/netark_guard_daemon.py",
        "scripts/netark_init.py",
        "scripts/sync_doc_metadata.py",
        f"{brain_rel}/extensions/epistemic-gate.ts",
        f"{brain_rel}/extensions/workspace-guard.ts",
        f"{brain_rel}/extensions/model-router.ts",
        f"{brain_rel}/extensions/session-handover.ts",
        f"{brain_rel}/extensions/web-research.ts",
    ]
    governed_set = set()
    for e in active_entries:
        for aff in (e.get("affected_paths") or []) + (e.get("stub_paths") or []):
            if isinstance(aff, str) and aff.strip():
                governed_set.add(aff.strip().replace("\\", "/"))

    all_script_paths = list(intel_map.keys())
    ordered_scripts: List[str] = []
    for p in priority_order:
        if p in intel_map and p not in ordered_scripts:
            ordered_scripts.append(p)
    for p in sorted(all_script_paths):
        if p not in ordered_scripts:
            ordered_scripts.append(p)

    selected_scripts: List[str] = []
    cluster_entries: List[str] = []
    if tier == "L1-Full":
        selected_scripts = ordered_scripts
    elif tier == "L2-Cluster":
        dir_groups: Dict[str, List[str]] = {}
        for p in ordered_scripts:
            if p in governed_set or p in priority_order:
                selected_scripts.append(p)
            else:
                dparent = str(Path(p).parent).replace("\\", "/")
                dir_groups.setdefault(dparent, []).append(p)
        for dparent, group_files in sorted(dir_groups.items()):
            if len(group_files) <= 2:
                selected_scripts.extend(group_files)
            else:
                tag = "M_" + re.sub(r"[^A-Za-z0-9]", "_", dparent).upper().strip("_")[:12]
                cluster_entries.append(f"{tag}={dparent}/*({len(group_files)} files)")
    else:
        # L3-ActiveCone: Core L1/L2 codex governed scripts + HANDOVER active cone
        for p in ordered_scripts:
            if p in governed_set or p in priority_order[:8]:
                selected_scripts.append(p)
        selected_scripts = selected_scripts[:40]

    # Pre-register directories used by active nodes and selected scripts
    for e in active_entries:
        _register_dir(str(e.get("path") or ""))
    for sp in selected_scripts:
        _register_dir(sp)

    script_to_code: Dict[str, str] = {}
    reverse_lookup: Dict[str, Dict[str, Any]] = {}
    c_tokens: List[str] = []

    for idx, sp in enumerate(selected_scripts):
        ccode = f"C{idx}"
        script_to_code[sp] = ccode
        dcode, fname = _register_dir(sp)
        info = intel_map.get(sp, {})
        total_lines = info.get("total_lines", 1)
        c_tokens.append(f"{ccode}={dcode}:{fname}(L1-{total_lines})")
        reverse_lookup[ccode] = {
            "kind": "script",
            "code": ccode,
            "path": sp,
            "dir_code": dcode,
            "line_range": f"L1-{total_lines}",
            "total_lines": total_lines,
            "language": info.get("language", "unknown"),
            "symbols": info.get("symbols", []),
            "pi_registrations": info.get("pi_registrations", []),
            "governing_specs": info.get("governing_specs", []),
        }

    for c_cluster in cluster_entries:
        c_tokens.append(c_cluster)

    # Order used_dir_codes by canonical order first, then dynamic
    canonical_order_keys = [c for c, _ in canonical_dirs]
    sorted_dir_codes = [c for c in canonical_order_keys if c in used_dir_codes] + [
        c for c in used_dir_codes if c not in canonical_order_keys
    ]
    for dcode in sorted_dir_codes:
        reverse_lookup[dcode] = {
            "kind": "dir",
            "code": dcode,
            "path": code_to_dir[dcode],
        }

    # Build node short codes for @G
    domain_counts: Dict[str, int] = {}
    for e in active_entries:
        dc = str(e.get("domain_code") or "000")
        domain_counts[dc] = domain_counts.get(dc, 0) + 1

    domain_seen: Dict[str, int] = {}
    node_short_map: Dict[str, str] = {}
    for e in active_entries:
        nid = str(e.get("node_id") or "")
        nkey = str(e.get("node_key") or "")
        dc = str(e.get("domain_code") or "000")
        if domain_counts.get(dc, 0) == 1:
            ncode = dc
        else:
            seen_idx = domain_seen.get(dc, 0) + 1
            domain_seen[dc] = seen_idx
            ncode = dc if seen_idx == 1 else f"{dc}.{seen_idx}"
        node_short_map[nid] = ncode
        if nkey:
            node_short_map[nkey] = ncode

    m_tokens: List[str] = []
    dag_edges: List[str] = []
    syn_edges: List[str] = []
    for e in active_entries:
        nid = str(e.get("node_id") or "")
        nkey = str(e.get("node_key") or nid)
        status = str(e.get("status") or "draft")
        summary = str(e.get("summary_1line") or "").replace('"', "'")
        npath = str(e.get("path") or "")
        ncode = node_short_map.get(nid, str(e.get("domain_code") or "000"))
        dcode, fname = _register_dir(npath)
        m_tokens.append(f"{ncode}={dcode}:{fname}[{nkey}|{status}]")

        dep_codes: List[str] = []
        for dep in e.get("depends_on") or []:
            dep_c = node_short_map.get(str(dep), str(dep))
            if dep_c and dep_c not in dep_codes:
                dep_codes.append(dep_c)
        if dep_codes:
            dag_edges.append(f"{ncode} < {','.join(dep_codes)}")

        gov_c_codes: List[str] = []
        for aff in (e.get("affected_paths") or []) + (e.get("stub_paths") or []):
            aff_norm = str(aff).strip().replace("\\", "/")
            if aff_norm in script_to_code:
                sc = script_to_code[aff_norm]
                if sc not in gov_c_codes:
                    gov_c_codes.append(sc)
            else:
                for sp, sc in script_to_code.items():
                    if sp.startswith(aff_norm.rstrip("/") + "/") and sc not in gov_c_codes:
                        gov_c_codes.append(sc)
        if gov_c_codes:
            syn_edges.append(f"{ncode} => {','.join(gov_c_codes)}")

        node_meta = {
            "kind": "node",
            "code": ncode,
            "node_id": nid,
            "node_key": nkey,
            "status": status,
            "path": npath,
            "summary_1line": summary,
            "depends_on": e.get("depends_on") or [],
            "governed_scripts": gov_c_codes,
            "affected_paths": e.get("affected_paths") or [],
        }
        reverse_lookup[ncode] = node_meta
        reverse_lookup[nkey] = node_meta
        if nid:
            reverse_lookup[nid] = node_meta

    ast_edges: List[str] = []
    for sp in selected_scripts:
        src_code = script_to_code.get(sp)
        if not src_code:
            continue
        info = intel_map.get(sp, {})
        dst_codes: List[str] = []
        for imp in info.get("imports", []):
            imp_code = script_to_code.get(str(imp))
            if imp_code and imp_code != src_code and imp_code not in dst_codes:
                dst_codes.append(imp_code)
        if dst_codes:
            ast_edges.append(f"{src_code} -> {','.join(dst_codes)}")

    d_line_tokens = [f"{dcode}={code_to_dir[dcode]}" for dcode in sorted_dir_codes]
    m_rows: List[str] = []
    for i in range(0, len(m_tokens), 3):
        m_rows.append("  " + " | ".join(m_tokens[i : i + 3]))
    c_rows: List[str] = []
    for i in range(0, len(c_tokens), 3):
        c_rows.append("  " + " | ".join(c_tokens[i : i + 3]))

    g_lines = [
        f"  [DAG] {' | '.join(dag_edges) if dag_edges else '(none)'}",
        f"  [SYN] {' | '.join(syn_edges) if syn_edges else '(none)'}",
        f"  [AST] {' | '.join(ast_edges) if ast_edges else '(none)'}",
    ]

    compact_lines = [
        f"## 🧭 [{project_root.name} Turn-1 Frozen Codebook Map] (Nodes: {total_nodes} | Scripts: {len(selected_scripts)} | Tier: {tier})",
        f"@D (Dirs): {' '.join(d_line_tokens)}",
        "@M (Nodes):",
        *(m_rows if m_rows else ["  (none)"]),
        "@C (Scripts):",
        *(c_rows if c_rows else ["  (none)"]),
        "@G (Topology Graph — DAG / Governance Synapses / Code AST Imports):",
        *g_lines,
        '💡 [Lookup Rule]: `<` 表示 depends_on，`=>` 表示記憶管轄腳本，`->` 表示程式碼 AST 引用；可直接用 `@D`+`@M`/`@C` 還原路徑，或呼叫 `query_library(query="200"|"C1")` 查閱完整中文摘要與符號。',
    ]
    compact_text = "\n".join(compact_lines)

    # Estimate uncompressed equivalent size (full paths, full JSON/markdown representations for every node and script)
    raw_uncompressed_est = sum(
        len(str(e.get("path", ""))) * 3 + len(str(e.get("summary_1line", ""))) + len(json.dumps(e, ensure_ascii=False))
        for e in active_entries
    ) + sum(
        len(sp) * 4 + len(json.dumps(intel_map.get(sp, {}), ensure_ascii=False))
        for sp in selected_scripts
    )
    compact_len = len(compact_text)
    saved_pct = round((1.0 - (compact_len / max(raw_uncompressed_est, compact_len + 1))) * 100.0, 1)

    return {
        "tier": tier,
        "total_nodes": total_nodes,
        "total_scripts": len(selected_scripts),
        "raw_char_estimate": raw_uncompressed_est,
        "compact_char_count": compact_len,
        "compression_ratio_pct": saved_pct,
        "dirs": {dcode: code_to_dir[dcode] for dcode in sorted_dir_codes},
        "scripts": {script_to_code[sp]: sp for sp in selected_scripts},
        "compact_text": compact_text,
        "reverse_lookup": reverse_lookup,
    }


def is_private_memory_path(project_root: Path, md_path: Path) -> bool:
    rel_parts = md_path.relative_to(project_root).parts
    return "private" in rel_parts


def _compile_index_subset(
    project_root: Path,
    subset_files: List[Path],
    all_nodes_fm: Dict[str, Dict[str, Any]],
    key_to_id: Dict[str, str],
    healed_links: List[Dict[str, str]],
    code_dependency_edges: List[Dict[str, str]],
    include_code_intel: bool = True,
) -> Dict[str, Any]:
    domain_layers = load_domain_layers(project_root)
    entries: List[Dict[str, Any]] = []
    by_domain: Dict[str, List[Dict[str, Any]]] = {k: [] for k in domain_layers}
    edges: List[Dict[str, str]] = []
    subset_fm: Dict[str, Dict[str, Any]] = {}
    body_by_id: Dict[str, str] = {}
    path_by_id: Dict[str, str] = {}

    subset_key_to_id: Dict[str, str] = {}
    subset_id_to_key: Dict[str, str] = {}
    raw_parsed_nodes: List[Dict[str, Any]] = []

    for md_path in subset_files:
        rel_path = str(md_path.relative_to(project_root)).replace("\\", "/")
        try:
            fm, body = parse_markdown_frontmatter(md_path)
        except Exception as exc:
            print(f"⚠️ Skipping {rel_path}: {exc}", file=sys.stderr)
            continue

        if not isinstance(fm, dict) or not fm.get("node_id"):
            continue

        idx = fm.get("context_index", {}) if isinstance(fm.get("context_index"), dict) else {}
        topo = fm.get("topology", {}) if isinstance(fm.get("topology"), dict) else {}
        domain = str(idx.get("domain_code", "000"))
        src_id = str(fm.get("node_id", rel_path))
        node_key = idx.get("node_key")

        if src_id and node_key:
            subset_key_to_id[node_key] = src_id
            subset_id_to_key[src_id] = node_key

        raw_parsed_nodes.append({
            "md_path": md_path,
            "rel_path": rel_path,
            "fm": fm,
            "body": body,
            "domain": domain,
            "src_id": src_id,
            "node_key": node_key,
            "idx": idx,
            "topo": topo,
        })

    outbound_by_node: Dict[str, List[str]] = {}
    backlinks_map: Dict[str, List[str]] = {}

    for node in raw_parsed_nodes:
        src_id = node["src_id"]
        src_key = node["node_key"]
        canonical_src = src_key if src_key else src_id
        extracted_tokens = extract_wikilinks_outside_fenced_blocks(node["body"])

        resolved_outbound: List[str] = []
        for token in extracted_tokens:
            if token in subset_key_to_id:
                resolved_outbound.append(token)
                target_key = token
                target_id = subset_key_to_id[token]
            elif token in subset_id_to_key:
                target_key = subset_id_to_key[token]
                target_id = token
                resolved_outbound.append(target_key)
            else:
                continue

            backlinks_map.setdefault(target_key, []).append(canonical_src)
            backlinks_map.setdefault(target_id, []).append(canonical_src)

        outbound_by_node[src_id] = sorted(list(set(resolved_outbound)))

    for node in raw_parsed_nodes:
        md_path = node["md_path"]
        rel_path = node["rel_path"]
        fm = node["fm"]
        body = node["body"]
        domain = node["domain"]
        src_id = node["src_id"]
        node_key = node["node_key"]
        idx = node["idx"]
        topo = node["topo"]

        artifact_type = fm.get("artifact_type", "wiki")
        inferred_track = "official" if artifact_type in OFFICIAL_TYPES else "wiki"
        artifact_track = fm.get("artifact_track") or idx.get("artifact_track") or topo.get("artifact_track") or inferred_track

        subdomain = fm.get("subdomain") or idx.get("subdomain") or topo.get("subdomain")
        if not subdomain and domain and domain not in ("000", "100", "200", "300", "400", "500", "600", "700", "800", "900"):
            subdomain = domain

        outbound_links = outbound_by_node.get(src_id, [])
        node_backlinks = sorted(list(set(
            backlinks_map.get(src_id, []) + (backlinks_map.get(node_key, []) if node_key else [])
        )))

        entry = {
            "node_id": fm.get("node_id"),
            "artifact_type": artifact_type,
            "status": fm.get("status"),
            "access_tier": fm.get("access_tier"),
            "priority": fm.get("priority"),
            "domain_code": domain,
            "subdomain": subdomain,
            "artifact_track": artifact_track,
            "outbound_links": outbound_links,
            "backlinks": node_backlinks,
            "node_key": node_key,
            "facet_tags": idx.get("facet_tags", []),
            "keywords": idx.get("keywords", []),
            "summary_1line": idx.get("summary_1line", ""),
            "path": rel_path,
            "sha256_16": sha256_file(md_path),
            "author_model": fm.get("author", {}).get("model") if isinstance(fm.get("author"), dict) else None,
            "reviewer_model": fm.get("reviewer", {}).get("model") if isinstance(fm.get("reviewer"), dict) else None,
            "depends_on": topo.get("depends_on", []) if isinstance(topo, dict) else [],
            "affected_paths": topo.get("affected_paths", []) if isinstance(topo, dict) else [],
            "parent_blueprint": topo.get("parent_blueprint") if isinstance(topo, dict) else None,
            "shard_modules": topo.get("shard_modules", []) if isinstance(topo, dict) else [],
            "stub_paths": topo.get("stub_paths", []) if isinstance(topo, dict) else [],
        }
        entries.append(entry)
        by_domain.setdefault(domain, []).append(entry)

        subset_fm[src_id] = fm
        body_by_id[src_id] = body
        path_by_id[src_id] = rel_path

    for entry in entries:
        src_id = entry["node_id"]
        for dep in entry.get("depends_on", []):
            edges.append({"from": src_id, "to": key_to_id.get(dep, dep), "relation": "depends_on"})
        parent_bp = entry.get("parent_blueprint")
        if isinstance(parent_bp, str) and parent_bp.strip():
            edges.append({"from": src_id, "to": key_to_id.get(parent_bp, parent_bp), "relation": "shard_of"})

    pending_topology_alignments: List[Dict[str, Any]] = []
    for src_id, fm in subset_fm.items():
        if fm.get("status") != "verified":
            continue
        body = body_by_id.get(src_id, "")
        topo = fm.get("topology", {}) if isinstance(fm.get("topology"), dict) else {}
        declared_refs = set(
            (topo.get("depends_on") or [])
            + (topo.get("supersedes") or [])
            + (topo.get("conflicts_with") or [])
        )
        unlinked_targets: List[str] = []
        for target_id, target_fm in sorted(subset_fm.items()):
            if target_id == src_id or target_fm.get("status") != "verified":
                continue
            if target_fm.get("artifact_type") not in ("spec", "audit"):
                continue
            target_key = target_fm.get("context_index", {}).get("node_key", "")
            if target_id in declared_refs or (target_key and target_key in declared_refs):
                continue
            if target_id in body or (target_key and target_key in body):
                unlinked_targets.append(f"{target_id} ({target_key})" if target_key else target_id)
        if unlinked_targets:
            pending_topology_alignments.append(
                {
                    "source_node_id": src_id,
                    "source_node_key": fm.get("context_index", {}).get("node_key", ""),
                    "source_path": path_by_id.get(src_id, ""),
                    "unlinked_targets": unlinked_targets,
                }
            )

    domain_stats = {code: len(by_domain.get(code, [])) for code in domain_layers}
    facet_registry: Dict[str, int] = {}
    for entry in entries:
        for tag in entry.get("facet_tags", []) or []:
            if isinstance(tag, str) and tag.strip():
                facet_registry[tag] = facet_registry.get(tag, 0) + 1

    intel_map = build_code_intelligence_map(project_root, entries, code_dependency_edges) if include_code_intel else {}
    codebook_map = build_codebook_map(project_root, entries, intel_map) if include_code_intel else {}

    return {
        "schema_version": "2.3.0",
        "project": project_root.name,
        "harness": "NetArk",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_nodes": len(entries),
        "healed_links": healed_links,
        "pending_topology_alignments": pending_topology_alignments,
        "domain_stats": domain_stats,
        "facet_registry": facet_registry,
        "domain_registry": {
            code: {
                "title": title,
                "count": len(by_domain.get(code, [])),
                "items": by_domain.get(code, []),
            }
            for code, title in domain_layers.items()
        },
        "causal_topology_edges": edges,
        "code_dependency_edges": code_dependency_edges,
        "code_intelligence_map": intel_map,
        "codebook_map": codebook_map,
    }


def build_context_index(project_root: Path) -> Dict[str, Any]:
    public_index, _ = build_public_and_private_indices(project_root)
    return public_index


def build_public_and_private_indices(project_root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    memory_dir = project_root / "memory"
    if not memory_dir.exists():
        empty = _compile_index_subset(project_root, [], {}, {}, [], [], include_code_intel=True)
        return empty, _compile_index_subset(project_root, [], {}, {}, [], [], include_code_intel=False)

    md_files = sorted(
        p for p in memory_dir.rglob("*.md")
        if p.name != "CONTEXT_MAP.md"
    )

    healed_links = heal_dead_links(project_root, md_files)
    code_dependency_edges = scan_code_dependencies(project_root)

    all_nodes_fm: Dict[str, Dict[str, Any]] = {}
    key_to_id: Dict[str, str] = {}
    public_files: List[Path] = []
    private_files: List[Path] = []

    for md_path in md_files:
        rel_md = str(md_path.relative_to(project_root)).replace("\\", "/")
        try:
            fm, _ = parse_markdown_frontmatter(md_path)
        except Exception:
            continue
        if not isinstance(fm, dict) or not fm.get("node_id"):
            continue
        if is_private_memory_path(project_root, md_path) or is_gitignored_path(rel_md, project_root):
            private_files.append(md_path)
        else:
            public_files.append(md_path)
        nid = fm.get("node_id")
        nkey = fm.get("context_index", {}).get("node_key") if isinstance(fm.get("context_index"), dict) else None
        if nid:
            all_nodes_fm[nid] = fm
        if nkey and nid:
            key_to_id[nkey] = nid

    public_healed = [h for h in healed_links if not is_gitignored_path(h["file"], project_root) and "private" not in Path(h["file"]).parts]
    private_healed = [h for h in healed_links if is_gitignored_path(h["file"], project_root) or "private" in Path(h["file"]).parts]

    public_index = _compile_index_subset(
        project_root, public_files, all_nodes_fm, key_to_id, public_healed, code_dependency_edges, include_code_intel=True
    )
    private_index = _compile_index_subset(
        project_root, private_files, all_nodes_fm, key_to_id, private_healed, [], include_code_intel=False
    )
    return public_index, private_index


def render_context_map_md(project_root: Path, index: Dict[str, Any]) -> str:
    brain_rel = get_brain_rel_dir(project_root)
    codebook_text = (index.get("codebook_map") or {}).get("compact_text", "")
    lines: List[str] = [
        f"# 🗺️ {project_root.name} × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)",
        "",
        f"> **自動生成時間**: `{index['generated_at']}` | **Agentic Harness**: `{index['harness']}` | **記憶節點總數**: `{index['total_nodes']}`",
        "> **漸進式揭露原則 (Progressive Disclosure)**: Agent 啟動時於 Turn 1 凍結注入 `@D/@C/@G` 代號壓縮地圖，按短代號 (`C0..Cn` / `000..900`) 或節點鍵值 (`node_key`) 按需調閱對應檔案。",
        "",
    ]
    if codebook_text:
        lines.extend([
            "## 0. Turn-1 凍結代號壓縮地圖 (`@D/@C/@G` Codebook Map)",
            "",
            "```text",
            codebook_text,
            "```",
            "",
        ])

    lines.append("## 1. 領域分層註冊表 (Domain Layer Registry)")
    lines.append("")
    for code, layer in index["domain_registry"].items():
        items = layer["items"]
        if not items:
            continue
        lines.append(f"### 📂 `{layer['title']}` ({layer['count']} 節點)")
        lines.append("")
        lines.append("| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :--- | :--- |")
        for item in items:
            lines.append(
                f"| `{item['node_id']}` | `{item['node_key']}` | `{item.get('artifact_track', 'official')}` | `{item['artifact_type']}` | `{item['status']}` | {item['summary_1line']} | [`{item['path']}`](../../{item['path']}) |"
            )
        lines.append("")

    lines.extend([
        "## 2. 因果拓撲依賴邊 (Causal Topology DAG Edges)",
        "",
        "| 下游節點 (`from`) | 依賴關係 (`relation`) | 上游基礎節點 (`to`) |",
        "| :--- | :---: | :--- |",
    ])
    for edge in index["causal_topology_edges"]:
        lines.append(f"| `{edge['from']}` | `{edge['relation']}` | `{edge['to']}` |")

    lines.extend([
        "",
        "## 3. 程式碼模組依賴圖 (Code-Level AST Dependency Graph)",
        "",
        "| 來源模組 (`from`) | 目標依賴 (`to`) | 依賴類型 (`type`) |",
        "| :--- | :--- | :---: |",
    ])
    for cedge in index.get("code_dependency_edges", []):
        lines.append(f"| `{cedge['from']}` | `{cedge['to']}` | `{cedge['type']}` |")

    intel_map = index.get("code_intelligence_map", {})
    if intel_map:
        lines.extend([
            "",
            "### 3.2 源碼符號、Hook 註冊與規格影響圈總表 (Code Intelligence & Impact Map)",
            "",
            "| 源碼路徑 (`file_path`) | 主要符號與行號 (`symbols`) | Pi 擴充註冊 (`command`/`tool`/`hook`) | 影響圈 (`imported_by`) | 綁定規格 (`governing_specs`) |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for cpath, info in sorted(intel_map.items()):
            syms = ", ".join(
                f"`{s['name']}`(L{s['line_start']}-L{s['line_end']})"
                for s in info.get("symbols", [])[:6]
            ) or "—"
            regs = ", ".join(
                f"`{r['kind']}:{r['name']}`(L{r['line']})"
                for r in info.get("pi_registrations", [])[:6]
            ) or "—"
            imp_by = ", ".join(f"`{p}`" for p in info.get("imported_by", [])) or "—"
            specs = ", ".join(f"`{g.get('node_key') or g.get('node_id')}`" for g in info.get("governing_specs", [])) or "—"
            lines.append(f"| `{cpath}` | {syms} | {regs} | {imp_by} | {specs} |")

    lines.extend([
        "",
        "## 4. 專案治理目錄結構摘要",
        "",
        f"- `{brain_rel}/` — 專案內嵌可攜式 NetArk Agentic Harness 大腦（含模型路由、安全護欄、漸進式揭露與 5 角色子代理）",
        "- `schemas/` — 記憶節點標頭 (`artifact_header.schema.json`)、Context 拓撲節點 (`context_node.schema.json`)、Tier 0 AST 護欄 (`netark_guard_core.py`) 與防諂媚驗證器 (`schema_validator.py`)",
        "- `memory/codex/` — 核心架構規範 (`000_SOUL.md`, `100_ARCH_RULES.md`, `200_DECISIONS.md`) 與自動編譯總目錄 (`CONTEXT_MAP.md`)",
        "- `memory/LEDGER.md` — 專案唯一活躍工單台帳 (`<= 80` 行)",
        "- `memory/episodic/HANDOVER.md` — 微對話無縫交接快照 (`<= 65` 行)",
        "- `memory/index/CONTEXT_INDEX.json` — 機器可讀之漸進式揭露與 `@D/@C/@G` 代號壓縮索引",
        "- `scripts/` — 索引編譯器 (`auto_update_map.py`)、跨宿主守護程序 (`netark_guard_daemon.py`)、母版安裝器 (`netark_init.py`) 與自動化驗收套件",
        "",
    ])
    return "\n".join(lines)


def verify_no_plaintext_secrets_before_index_write(project_root: Path, index: Dict[str, Any]) -> None:
    """G-05 Fix: Enforce scan_plaintext_secrets() on compiled CONTEXT_INDEX payload and HANDOVER.md before persisting."""
    serialized = json.dumps(index, ensure_ascii=False)
    findings = scan_plaintext_secrets(serialized, cwd=str(project_root))
    if findings:
        first = findings[0]
        raise RuntimeError(
            f"[G-05 SEC-INDEX-SECRET] Blocked CONTEXT_INDEX.json write: detected plaintext secret ({first['type']}) in memory index metadata."
        )
    handover_path = project_root / "memory" / "episodic" / "HANDOVER.md"
    if handover_path.exists():
        h_findings = scan_plaintext_secrets(handover_path.read_text(encoding="utf-8", errors="ignore"), cwd=str(project_root))
        if h_findings:
            first = h_findings[0]
            raise RuntimeError(
                f"[G-05 SEC-HANDOVER-SECRET] Blocked index compilation: detected plaintext secret ({first['type']}) in memory/episodic/HANDOVER.md."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile NetArk Context Index & @D/@C/@G Codebook Map.")
    parser.add_argument("--project-root", default=None, help="Target project root directory")
    parser.add_argument("--print-codebook", action="store_true", help="Print compiled @D/@C/@G codebook_map to stdout")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve() if args.project_root else Path(__file__).resolve().parent.parent
    index, private_index = build_public_and_private_indices(project_root)

    try:
        verify_no_plaintext_secrets_before_index_write(project_root, index)
    except RuntimeError as err:
        print(f"❌ {err}", file=sys.stderr)
        return 1

    index_path = project_root / "memory" / "index" / "CONTEXT_INDEX.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    private_index_path = project_root / "memory" / "index" / "PRIVATE_INDEX.json"
    private_map_path = project_root / "memory" / "private" / "CONTEXT_MAP.md"
    if private_index.get("total_nodes", 0) > 0:
        private_index_path.write_text(json.dumps(private_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        private_map_path.parent.mkdir(parents=True, exist_ok=True)
        private_map_md = render_context_map_md(project_root, private_index).replace(
            f"# 🗺️ {project_root.name} × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)",
            f"# 🔒 {project_root.name} × NetArk Private Context Registry & Topology Map (memory/private/CONTEXT_MAP.md)",
            1,
        )
        private_map_path.write_text(private_map_md, encoding="utf-8")
    else:
        if private_index_path.exists():
            private_index_path.unlink()
        if private_map_path.exists():
            private_map_path.unlink()

    map_path = project_root / "memory" / "codex" / "CONTEXT_MAP.md"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(render_context_map_md(project_root, index), encoding="utf-8")

    healed = index.get("healed_links", []) + private_index.get("healed_links", [])
    if healed:
        print(f"🩹 Auto-healed {len(healed)} broken relative Markdown link(s): {healed}")
    cb = index.get("codebook_map", {})
    print(
        f"✅ Compiled CONTEXT_INDEX.json ({index['total_nodes']} public nodes, "
        f"{cb.get('total_scripts', 0)} scripts, Tier={cb.get('tier', 'L1-Full')}, "
        f"Compression={cb.get('compression_ratio_pct', 0.0)}%) -> {index_path}"
    )
    if private_index.get("total_nodes", 0) > 0:
        print(f"🔒 Compiled PRIVATE_INDEX.json ({private_index['total_nodes']} private nodes, git-ignored) -> {private_index_path}")
        print(f"🔒 Rendered Private CONTEXT_MAP.md -> {private_map_path}")
    print(f"✅ Rendered CONTEXT_MAP.md -> {map_path}")
    if args.print_codebook and cb.get("compact_text"):
        print("\n" + cb["compact_text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
