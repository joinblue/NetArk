#!/usr/bin/env python3
"""
NetArk Causal Topology Graph & Gitignore Boundary Engine (schemas/topology_graph.py)
====================================================================================
Extracted from `schema_validator.py` to enforce modular separation:
  - `parse_markdown_frontmatter`: Parses YAML/JSON frontmatter and body from Markdown nodes
  - `load_all_memory_nodes`: Loads all governed Markdown memory nodes in `memory/`
  - `check_as06_node_exclusivity`: Validates `supersedes` and `conflicts_with` exclusivity rules
  - `detect_unlinked_topology_references`: Detects unlinked body references to active spec/audit nodes
  - `check_topology_graph`: Validates DAG dependencies (`depends_on`, `parent_blueprint`, `shard_modules`) and detects cycles
  - `_match_gitignore_rule` & `is_gitignored_path`: Prevents binding `affected_paths` to `.gitignore` secrets/caches
"""

from __future__ import annotations

import fnmatch, json, py_compile, re, subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

WIKI_TYPES = {"wiki", "note", "sop", "glossary", "digest"}


def parse_markdown_frontmatter(md_path: Path) -> Tuple[Dict[str, Any], str]:
    content = md_path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"{md_path}: Missing YAML frontmatter opening '---'")
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        raise ValueError(f"{md_path}: Missing YAML frontmatter closing '---'")
    raw_fm, body = parts[0][4:], parts[1]
    if yaml is not None:
        data = yaml.safe_load(raw_fm)
    else:
        from schemas.yaml_lite import _parse_simple_yaml
        data = _parse_simple_yaml(raw_fm)
    if not isinstance(data, dict):
        raise ValueError(f"{md_path}: Frontmatter must parse to a JSON/YAML object")
    return data, body


def load_all_memory_nodes(project_root: Path) -> Dict[str, Dict[str, Any]]:
    memory_dir = project_root / "memory"
    nodes: Dict[str, Dict[str, Any]] = {}
    if not memory_dir.exists():
        return nodes
    for p in sorted(memory_dir.rglob("*.md")):
        if p.name == "CONTEXT_MAP.md":
            continue
        try:
            fm, _ = parse_markdown_frontmatter(p)
        except Exception:
            continue
        if isinstance(fm, dict) and "node_id" in fm:
            nodes[fm["node_id"]] = fm
    return nodes


def check_as06_node_exclusivity(node_id: str, fm: Dict[str, Any], all_nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    key_to_id = {nkey: nid for nid, nfm in all_nodes.items() if (nkey := nfm.get("context_index", {}).get("node_key"))}
    topo, status = fm.get("topology", {}), fm.get("status", "")
    for sup in topo.get("supersedes", []) or []:
        target_id = sup if sup in all_nodes else key_to_id.get(sup)
        if not target_id or target_id not in all_nodes:
            errors.append(f"[AS-06 Supersedes] {node_id} 宣告取代不存在的節點 ID 或定位鍵: {sup}")
            continue
        target_status = all_nodes[target_id].get("status", "")
        if target_status not in ("archived", "deprecated"):
            errors.append(f"[AS-06 Supersedes Conflict] {node_id} 宣告取代 {sup} ({target_id})，但舊節點狀態仍為「{target_status}」（必須先降級為 archived 或 deprecated）。")
    for conf in topo.get("conflicts_with", []) or []:
        target_id = conf if conf in all_nodes else key_to_id.get(conf)
        if target_id and target_id in all_nodes and status == "verified" and all_nodes[target_id].get("status", "") == "verified":
            errors.append(f"[AS-06 Mutual Exclusion] {node_id} 與互斥節點 {conf} ({target_id}) 不可同時處於 verified 狀態！")
    return errors


def detect_unlinked_topology_references(node_id: str, fm: Dict[str, Any], body: str, all_nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    """Detects when an active (`verified`/`draft`) spec/audit explicitly references other `verified` spec/audit nodes while topology links are empty."""
    if fm.get("status", "") not in ("verified", "draft") or fm.get("artifact_type", "") in WIKI_TYPES:
        return []
    topo = fm.get("topology", {}) or {}
    declared_refs = set((topo.get("depends_on") or []) + (topo.get("supersedes") or []) + (topo.get("conflicts_with") or []) + (topo.get("shard_modules") or []) + ([topo["parent_blueprint"]] if topo.get("parent_blueprint") else []) + (fm.get("outbound_links") or []))
    unlinked_targets: List[str] = []
    for target_id, target_fm in sorted(all_nodes.items()):
        if target_id == node_id or target_fm.get("status") != "verified" or target_fm.get("artifact_type") not in ("spec", "audit"):
            continue
        target_key = target_fm.get("context_index", {}).get("node_key", "")
        if target_id in declared_refs or (target_key and target_key in declared_refs):
            continue
        if target_id in body or (target_key and target_key in body):
            unlinked_targets.append(f"{target_id} ({target_key})" if target_key else target_id)
    if not unlinked_targets:
        return []
    return [f"[AS-06 Pending Topology Alignment] 節點 {node_id} 內文提及活躍節點 {', '.join(unlinked_targets)}，但標頭尚未宣告拓撲關聯（若為一般引用請加入 `topology.depends_on`；若為新版取代舊版，請補齊 `supersedes` 並將舊節點降級為 archived/deprecated）。"]


def check_topology_graph(nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    known_ids = set(nodes.keys())
    key_to_node = {nkey: nid for nid, nfm in nodes.items() if (nkey := nfm.get("context_index", {}).get("node_key"))}
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for node_id, fm in nodes.items():
        is_inactive = fm.get("status", "") in ("archived", "deprecated")
        topo_obj = fm.get("topology", {}) if isinstance(fm.get("topology"), dict) else {}
        for dep in topo_obj.get("depends_on", []):
            resolved = dep if dep in known_ids else key_to_node.get(dep)
            if not resolved:
                errors.append(f"[AS-04 Topology] {node_id} 依賴不存在的節點 ID 或定位鍵: {dep}")
            elif not is_inactive and nodes.get(resolved, {}).get("status", "") not in ("archived", "deprecated"):
                adj[node_id].append(resolved)
        if isinstance(parent_bp := topo_obj.get("parent_blueprint"), str) and parent_bp.strip() and not (parent_bp if parent_bp in known_ids else key_to_node.get(parent_bp)):
            errors.append(f"[AS-04 Topology] {node_id} parent_blueprint 指向不存在的藍圖節點: {parent_bp}")
        for shard_ref in (topo_obj.get("shard_modules") if isinstance(topo_obj.get("shard_modules"), list) else []):
            if isinstance(shard_ref, str) and shard_ref.strip() and not (shard_ref if shard_ref in known_ids else key_to_node.get(shard_ref)):
                errors.append(f"[AS-04 Topology] {node_id} shard_modules 包含不存在的子節點: {shard_ref}")
        errors.extend(check_as06_node_exclusivity(node_id, fm, nodes))
    visited: Dict[str, int] = {}

    def dfs(node: str, stack: List[str]) -> None:
        visited[node] = 1
        for nxt in adj.get(node, []):
            state = visited.get(nxt, 0)
            if state == 1:
                errors.append(f"[AS-04 Topology Cycle] 偵測到循環依賴: {' -> '.join(stack + [nxt])}")
            elif state == 0:
                dfs(nxt, stack + [nxt])
        visited[node] = 2

    for n in nodes:
        if visited.get(n, 0) == 0:
            dfs(n, [n])
    return errors


def _match_gitignore_rule(raw_line: str, rel_norm: str, basename: str) -> Tuple[bool, bool]:
    """Early-return helper evaluating a single .gitignore line. Returns (matched, is_negated)."""
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return False, False
    neg = line.startswith("!")
    pat = line[1:].strip().lstrip("/") if neg else line.lstrip("/")
    if not pat:
        return False, False
    if pat.endswith("/"):
        dir_pat = pat.rstrip("/")
        matched = rel_norm == dir_pat or rel_norm.startswith(dir_pat + "/") or dir_pat in rel_norm.split("/")
        return matched, neg
    if fnmatch.fnmatch(rel_norm, pat) or fnmatch.fnmatch(basename, pat):
        return True, neg
    parts = rel_norm.split("/")
    matched = any(fnmatch.fnmatch("/".join(parts[:idx]), pat) for idx in range(1, len(parts)))
    return matched, neg


def is_gitignored_path(rel_path: str, project_root: Path) -> bool:
    """D-03 / #6 Fix: Prevent memory nodes from binding affected_paths to .gitignore-ignored secrets or ephemeral caches."""
    rel_norm = rel_path.strip().replace("\\", "/").lstrip("./")
    if not rel_norm:
        return False
    basename = Path(rel_norm).name
    if basename in {"auth.json", "models-store.json", ".env"} or (
        basename.startswith(".env.") and basename not in {".env.example", ".env.sample", ".env.template"}
    ) or ("vault" in basename.lower() and basename.endswith(".json")):
        return True
    gitignore_file = project_root / ".gitignore"
    if not gitignore_file.exists():
        return False
    ignored = False
    for raw_line in gitignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        matched, neg = _match_gitignore_rule(raw_line, rel_norm, basename)
        if matched:
            ignored = not neg
    return ignored


def _load_context_index(project_root: Path) -> Dict[str, Any]:
    idx_path = project_root / "memory" / "index" / "CONTEXT_INDEX.json"
    if not idx_path.is_file():
        return {}
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _iter_unique_rev_nodes(rev: Dict[str, Any]) -> List[Dict[str, Any]]:
    seen, nodes = set(), []
    for v in rev.values():
        if not isinstance(v, dict) or v.get("kind") != "node":
            continue
        sig = v.get("node_id") or v.get("node_key") or v.get("path") or v.get("code")
        if sig and sig not in seen:
            seen.add(sig)
            nodes.append(v)
    return nodes


def _extract_rev_topic(entry: Dict[str, Any]) -> str:
    if (t := str(entry.get("topic") or "").strip()):
        return t
    tags = entry.get("facet_tags")
    return str(tags[0]).split(":")[1].strip() if isinstance(tags, list) and tags and ":" in str(tags[0]) else ""


def _format_match_item(m: Dict[str, Any]) -> Dict[str, Any]:
    return {f: m[f] for f in ("kind", "code", "path", "node_id", "node_key", "status", "topic", "summary_1line", "folded") if m.get(f) is not None and m.get(f) != ""}


def _scan_md_outline(md_path: Path) -> Dict[str, Any]:
    if not md_path.is_file(): return {}
    lines, in_fence, bp, raw = md_path.read_text(encoding="utf-8", errors="ignore").splitlines(), False, None, []
    for idx, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("```"): in_fence = not in_fence; continue
        if in_fence: continue
        if bp is None and "<!-- 閱讀斷點" in s: bp = idx
        if re.match(r"^#{2,3}\s+", s) or s.startswith("<details>"):
            raw.append({"heading": "<details> 已落地歷史紀錄" if s.startswith("<details>") else s, "line_start": idx})
    sections = [{**sec, "line_end": (raw[i + 1]["line_start"] - 1 if i + 1 < len(raw) else len(lines))} for i, sec in enumerate(raw)]
    return {"total_lines": len(lines), "reading_breakpoint_line": bp, "sections": sections}


def _expand_entry_result(query: str, entry: Dict[str, Any], rev: Dict[str, Any], intel_map: Dict[str, Any], project_root: Optional[Path] = None) -> Dict[str, Any]:
    kind = entry.get("kind")
    if kind == "script":
        cinfo = intel_map.get(entry.get("path", ""), {}) if isinstance(intel_map, dict) else {}
        imports, imported_by = list(cinfo.get("imports") or entry.get("imports") or []), list(cinfo.get("imported_by") or entry.get("imported_by") or [])
        gov_specs = [{k: g[k] for k in ("code", "node_id", "node_key", "path") if k in g} if isinstance(g, dict) else g for g in (entry.get("governing_specs") or cinfo.get("governing_specs") or [])]
        return {"found": True, "query": query, **entry, "imports": imports, "imported_by": imported_by, "governing_specs": gov_specs, "neighbors": {"imports": imports, "imported_by": imported_by, "governing_specs": gov_specs}}
    if kind == "node":
        deps = [{k: t[k] for k in ("code", "node_id", "node_key", "path", "summary_1line") if k in t} if isinstance(t := rev.get(d), dict) else {"ref": d} for d in (entry.get("depends_on") or [])]
        govs = [{k: t[k] for k in ("code", "path", "line_range") if k in t} if isinstance(t := rev.get(g), dict) else {"code": g} for g in (entry.get("governed_scripts") or [])]
        res: Dict[str, Any] = {"found": True, "query": query, **entry, "neighbors": {"depends_on": deps, "governed_scripts": govs}}
        if project_root is not None and entry.get("path"): res.update(_scan_md_outline(project_root / str(entry["path"])))
        if entry.get("artifact_type") == "blueprint" or entry.get("type") == "blueprint" or entry.get("shard_modules"):
            bp_refs = {x for x in (str(entry.get("node_key") or ""), str(entry.get("node_id") or "")) if x}
            bp_shards = {str(s).strip() for s in (entry.get("shard_modules") or []) if str(s).strip()}
            children = [
                n for n in _iter_unique_rev_nodes(rev)
                if n is not entry and (not entry.get("node_id") or n.get("node_id") != entry.get("node_id"))
                and (str(n.get("parent_blueprint") or "").strip() in bp_refs or str(n.get("node_key") or "") in bp_shards or str(n.get("node_id") or "") in bp_shards)
            ]
            children.sort(key=lambda s: str(s.get("path") or ""))
            expanded = [{k: c.get(k, [] if k in ("stub_paths", "depends_on") else "") for k in ("code", "node_id", "node_key", "status", "stub_paths", "summary_1line", "path", "depends_on")} for c in children]
            res["shard_modules"] = res["expanded_shards"] = expanded
        return res
    scripts = [v["code"] for v in rev.values() if isinstance(v, dict) and v.get("kind") == "script" and v.get("dir_code") == entry.get("code")]
    return {"found": True, "query": query, **entry, "neighbors": {"scripts": scripts} if kind == "dir" else {}}


def query_codebook_entry(project_root: Path, query: str) -> Dict[str, Any]:
    """O(1) reverse_lookup query with blueprint shard, status bucket, topic, and substring expansion."""
    q = (query or "").strip()
    if not q:
        return {"found": False, "query": query, "matches": []}
    idx = _load_context_index(project_root)
    rev, intel_map = (idx.get("codebook_map") or {}).get("reverse_lookup"), idx.get("code_intelligence_map") or {}
    if not isinstance(rev, dict):
        return {"found": False, "query": query, "matches": []}
    if isinstance(direct := rev.get(q) or rev.get(q.upper()), dict):
        return _expand_entry_result(query, direct, rev, intel_map, project_root)
    nodes = _iter_unique_rev_nodes(rev)
    if (m_st := re.match(r"^(status|\d{3}):([A-Za-z_]+)$", q, re.IGNORECASE)):
        scope, target_st = m_st.group(1).lower(), m_st.group(2).lower()
        st_matches = sorted(
            [n for n in nodes if str(n.get("status") or "").lower() == target_st and (scope == "status" or str(n.get("subdomain") or "") == scope or str(n.get("domain_code") or "") == scope or str(n.get("code") or "").split(".")[0] == scope)],
            key=lambda x: str(x.get("path") or x.get("code") or ""),
        )
        return {"found": bool(st_matches), "query": q, "query_type": "status_bucket", "matches": [_format_match_item(m) for m in st_matches]}
    ql = q.lower()
    if (topic_nodes := sorted([n for n in nodes if _extract_rev_topic(n).lower() == ql], key=lambda x: str(x.get("path") or x.get("code") or ""))):
        return {"found": True, "query": q, "query_type": "topic", "topic": _extract_rev_topic(topic_nodes[0]), "matches": [_format_match_item(m) for m in topic_nodes]}
    seen, matches = set(), []
    for k, v in rev.items():
        if not isinstance(v, dict):
            continue
        sig = (v.get("kind"), v.get("code"), v.get("path"))
        hay = " ".join(str(v.get(f) or "") for f in ("code", "path", "node_id", "node_key", "topic", "summary_1line"))
        if sig not in seen and (ql in str(k).lower() or ql in hay.lower()):
            seen.add(sig)
            matches.append(v)
    if not matches:
        return {"found": False, "query": query, "matches": []}
    res = _expand_entry_result(query, matches[0], rev, intel_map, project_root)
    res["matches"] = [_format_match_item(m) for m in matches[:10]]
    return res


def check_code_to_spec_drift(project_root: Path, rel_path: str) -> Optional[str]:
    """Return a Code-to-Spec drift warning if non-markdown rel_path has governing_specs."""
    rel = (rel_path or "").strip().replace("\\", "/").lstrip("./")
    if not rel or rel.endswith(".md"): return None
    intel_map = _load_context_index(project_root).get("code_intelligence_map")
    info = intel_map.get(rel) if isinstance(intel_map, dict) else None
    specs = info.get("governing_specs") if isinstance(info, dict) else None
    if not isinstance(specs, list) or not specs: return None
    bullets = "\n".join(f"  - [{s.get('node_key') or s.get('node_id', '')} | {s.get('node_id', '')}] `{s.get('path', '')}`" for s in specs if isinstance(s, dict))
    if not bullets: return None
    return f"⚠️ [Code-to-Spec Drift Alert | 源碼變更連動警報] 已修改受規格綁定源碼 `{rel}`：\n{bullets}\n💡 若本次變更涉及介面、路由或安全規則調整，請同步檢視並更新對應記憶節點與 `epistemic_profile`。"


_SELF_SCHEMA_RE = re.compile(
    r'^python3?\s+(?:["\']?)schemas/schema_validator\.py(?:["\']?)\s+--file\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))\s*$'
)


def check_stub_syntax(stub_target: Path, checked_stubs: Optional[Set[Path]] = None) -> Optional[str]:
    """Compile a Python stub file in-process with optional per-run deduplication."""
    resolved = stub_target.resolve()
    if checked_stubs is not None and resolved in checked_stubs:
        return None
    try:
        py_compile.compile(str(resolved), doraise=True)
    except (py_compile.PyCompileError, OSError) as exc:
        return str(exc).strip()
    if checked_stubs is not None:
        checked_stubs.add(resolved)
    return None


def split_top_level_and(cmd: str) -> Optional[List[str]]:
    """Split a command on unquoted '&&' unless unquoted shell operators make splitting unsafe."""
    parts, buf, quote, esc, i, n = [], [], "", False, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if esc: buf.append(ch); esc = False
        elif ch == "\\" and quote != "'": buf.append(ch); esc = True
        elif quote:
            buf.append(ch)
            if ch == quote: quote = ""
        elif ch in ("'", '"'): quote = ch; buf.append(ch)
        elif cmd.startswith("&&", i):
            if not (seg := "".join(buf).strip()): return None
            parts.append(seg); buf = []; i += 2; continue
        elif ch in "|;><`" or cmd.startswith("$(", i): return None
        else: buf.append(ch)
        i += 1
    if quote or esc or not (tail := "".join(buf).strip()):
        return None
    return parts + [tail]


def is_self_schema_oracle(cmd: str, expected_code: int, md_path: Path, project_root: Path) -> bool:
    """Return True when the oracle command only re-validates the current Markdown file with expected_code == 0."""
    if expected_code != 0:
        return False
    parts = split_top_level_and(cmd.strip())
    if parts is None or len(parts) != 1:
        return False
    match = _SELF_SCHEMA_RE.match(parts[0])
    if not match:
        return False
    target = match.group(1) or match.group(2) or match.group(3)
    return (project_root / target).resolve() == md_path.resolve()


def _exec_oracle_cmd(sub_cmd: str, project_root: Path, oracle_cache: Optional[Dict[str, Tuple[int, str]]]) -> Tuple[int, str]:
    if oracle_cache is not None and sub_cmd in oracle_cache:
        return oracle_cache[sub_cmd]
    proc = subprocess.run(sub_cmd, shell=True, cwd=str(project_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    res = (proc.returncode, (proc.stderr or "").strip() or (proc.stdout or "").strip())
    if oracle_cache is not None:
        oracle_cache[sub_cmd] = res
    return res


def run_cached_oracle(cmd: str, expected_code: int, md_path: Path, project_root: Path, oracle_cache: Optional[Dict[str, Tuple[int, str]]] = None) -> Optional[str]:
    """Execute a verification_oracle command with self-schema short-circuit, && splitting, and caching."""
    safe_cmd = re.sub(r"\s+--run-oracle\b", "", cmd) if "schema_validator.py" in cmd else cmd
    if is_self_schema_oracle(safe_cmd, expected_code, md_path, project_root):
        return None
    if expected_code == 0 and (parts := split_top_level_and(safe_cmd)) and len(parts) > 1:
        for sub_cmd in parts:
            rc, out = _exec_oracle_cmd(sub_cmd, project_root, oracle_cache)
            if rc != 0:
                return f"[AS-03 Oracle Failed] 指令 `{cmd}` 子命令 `{sub_cmd}` 回傳碼 {rc} != 預期 0。輸出: {out}"
        return None
    rc, out = _exec_oracle_cmd(safe_cmd, project_root, oracle_cache)
    return f"[AS-03 Oracle Failed] 指令 `{cmd}` 回傳碼 {rc} != 預期 {expected_code}。輸出: {out}" if rc != expected_code else None


def collect_changed_memory_files(project_root: Path) -> List[Path]:
    """Return existing modified/untracked governed Markdown files under memory/ (excluding CONTEXT_MAP.md)."""
    proc = subprocess.run(["git", "status", "--porcelain", "-uall", "--", "memory"], cwd=str(project_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        return []
    found: Set[Path] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        raw_rel = line[3:].strip().split(" -> ")[-1].strip().strip('"')
        if raw_rel.endswith(".md") and Path(raw_rel).name != "CONTEXT_MAP.md" and (cand := (project_root / raw_rel).resolve()).is_file():
            found.add(cand)
    return sorted(found)
