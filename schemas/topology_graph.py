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

import fnmatch
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    data = yaml.safe_load(raw_fm) if yaml is not None else json.loads(raw_fm)
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


def check_as06_node_exclusivity(
    node_id: str,
    fm: Dict[str, Any],
    all_nodes: Dict[str, Dict[str, Any]],
) -> List[str]:
    errors: List[str] = []
    key_to_id: Dict[str, str] = {}
    for nid, nfm in all_nodes.items():
        nkey = nfm.get("context_index", {}).get("node_key")
        if nkey:
            key_to_id[nkey] = nid

    topo = fm.get("topology", {})
    status = fm.get("status", "")

    for sup in topo.get("supersedes", []) or []:
        target_id = sup if sup in all_nodes else key_to_id.get(sup)
        if not target_id or target_id not in all_nodes:
            errors.append(f"[AS-06 Supersedes] {node_id} 宣告取代不存在的節點 ID 或定位鍵: {sup}")
            continue
        target_status = all_nodes[target_id].get("status", "")
        if target_status not in ("archived", "deprecated"):
            errors.append(
                f"[AS-06 Supersedes Conflict] {node_id} 宣告取代 {sup} ({target_id})，"
                f"但舊節點狀態仍為「{target_status}」（必須先降級為 archived 或 deprecated）。"
            )

    for conf in topo.get("conflicts_with", []) or []:
        target_id = conf if conf in all_nodes else key_to_id.get(conf)
        if not target_id or target_id not in all_nodes:
            continue
        target_status = all_nodes[target_id].get("status", "")
        if status == "verified" and target_status == "verified":
            errors.append(
                f"[AS-06 Mutual Exclusion] {node_id} 與互斥節點 {conf} ({target_id}) 不可同時處於 verified 狀態！"
            )

    return errors


def detect_unlinked_topology_references(
    node_id: str,
    fm: Dict[str, Any],
    body: str,
    all_nodes: Dict[str, Dict[str, Any]],
) -> List[str]:
    """
    Detects when an active (`verified`/`draft`) spec/audit explicitly references other `verified`
    spec/audit nodes in its Markdown body while `depends_on`, `supersedes`, and `conflicts_with` are left empty.
    """
    notices: List[str] = []
    if fm.get("status", "") not in ("verified", "draft") or fm.get("artifact_type", "") in WIKI_TYPES:
        return notices

    topo = fm.get("topology", {}) or {}
    declared_refs = set(
        (topo.get("depends_on") or [])
        + (topo.get("supersedes") or [])
        + (topo.get("conflicts_with") or [])
        + (topo.get("shard_modules") or [])
        + ([topo["parent_blueprint"]] if topo.get("parent_blueprint") else [])
        + (fm.get("outbound_links") or [])
    )

    unlinked_targets: List[str] = []
    for target_id, target_fm in sorted(all_nodes.items()):
        if target_id == node_id or target_fm.get("status") != "verified":
            continue
        if target_fm.get("artifact_type") not in ("spec", "audit"):
            continue
        target_key = target_fm.get("context_index", {}).get("node_key", "")
        if target_id in declared_refs or (target_key and target_key in declared_refs):
            continue
        if target_id in body or (target_key and target_key in body):
            unlinked_targets.append(f"{target_id} ({target_key})" if target_key else target_id)

    if unlinked_targets:
        notices.append(
            f"[AS-06 Pending Topology Alignment] 節點 {node_id} 內文提及活躍節點 {', '.join(unlinked_targets)}，"
            f"但標頭尚未宣告拓撲關聯（若為一般引用請加入 `topology.depends_on`；若為新版取代舊版，請補齊 `supersedes` 並將舊節點降級為 archived/deprecated）。"
        )
    return notices


def check_topology_graph(nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    known_ids = set(nodes.keys())
    key_to_node: Dict[str, str] = {}
    for node_id, fm in nodes.items():
        node_key = fm.get("context_index", {}).get("node_key")
        if node_key:
            key_to_node[node_key] = node_id

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

        parent_bp = topo_obj.get("parent_blueprint")
        if isinstance(parent_bp, str) and parent_bp.strip():
            if not (parent_bp if parent_bp in known_ids else key_to_node.get(parent_bp)):
                errors.append(f"[AS-04 Topology] {node_id} parent_blueprint 指向不存在的藍圖節點: {parent_bp}")

        shard_mods = topo_obj.get("shard_modules")
        for shard_ref in (shard_mods if isinstance(shard_mods, list) else []):
            if isinstance(shard_ref, str) and shard_ref.strip():
                if not (shard_ref if shard_ref in known_ids else key_to_node.get(shard_ref)):
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
