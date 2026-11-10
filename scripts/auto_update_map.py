#!/usr/bin/env python3
"""
NetArk Context Index, Code Intelligence & @D/@C/@G Codebook Map Compiler (auto_update_map.py)
=============================================================================================
Scans governed memory nodes in `memory/` and workspace source code (excluding `.gitignore`):
heals broken Markdown links, runs Single-Pass AST intelligence (`code_hygiene_ast`), enforces G-05
secret guard, compiles `CONTEXT_INDEX.json` + `@D/@C/@G` codebook (`codebook_compiler`), and renders `CONTEXT_MAP.md`.
"""

from __future__ import annotations

import argparse, hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schemas"))
from code_hygiene_ast import discover_workspace_code_files, get_brain_rel_dir, scan_code_intelligence_single_pass  # type: ignore
from codebook_compiler import compile_codebook_map, render_context_map, render_private_context_map  # type: ignore
from netark_guard_core import scan_plaintext_secrets  # type: ignore
from schema_validator import is_gitignored_path, parse_markdown_frontmatter  # type: ignore

build_codebook_map = compile_codebook_map
render_context_map_md = render_context_map

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
    "900": "900 歷史封存與交接節點 (Episodic Handover & Archived Nodes)", "910": "910 情節交接與會話狀態 (Episodic Handover & Session State)",
}
OFFICIAL_TYPES, WIKI_TYPES = {"constitution", "rule", "adr", "blueprint", "spec", "audit"}, {"wiki", "note", "sop", "glossary", "digest"}
WIKILINK_RE = re.compile(r"\[\[([A-Za-z0-9_.-]+)(?:\|[^\]]+)?\]\]")
MD_LINK_PATTERN = re.compile(r"(\[[^\]]+\]\()([^)\s]+)(\))")


def _extract_subdomain_layers(v: Any, layers: Dict[str, str]) -> None:
    if not isinstance(v, dict) or not isinstance(v.get("subdomains"), dict):
        return
    for sk, sv_obj in v["subdomains"].items():
        stitle = sv_obj.get("title", sk) if isinstance(sv_obj, dict) else str(sv_obj)
        layers[str(sk)] = f"{sk} {stitle}"


def load_domain_layers(project_root: Path) -> Dict[str, str]:
    tax_path = project_root / "memory" / "index" / "TAXONOMY.json"
    if not tax_path.exists():
        return dict(DEFAULT_DOMAIN_LAYERS)
    try:
        domains = json.loads(tax_path.read_text(encoding="utf-8")).get("domains", {})
        layers: Dict[str, str] = {}
        for k, v in domains.items():
            layers[str(k)] = f"{k} {v.get('title', k) if isinstance(v, dict) else str(v)}"
            _extract_subdomain_layers(v, layers)
        for k, v in DEFAULT_DOMAIN_LAYERS.items():
            layers.setdefault(k, v)
        return layers
    except Exception:
        return dict(DEFAULT_DOMAIN_LAYERS)


def extract_wikilinks_outside_fenced_blocks(body: str) -> List[str]:
    links, in_fence = [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            links.extend(m.group(1) for m in WIKILINK_RE.finditer(line))
    return sorted(set(links))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def heal_dead_links(project_root: Path, md_files: List[Path]) -> List[Dict[str, str]]:
    healed_records: List[Dict[str, str]] = []
    brain_rel = get_brain_rel_dir(project_root)
    basename_map: Dict[str, List[Path]] = {}
    for root_sub in ("memory", brain_rel, "schemas", "scripts"):
        sub_dir = project_root / root_sub
        if not sub_dir.exists():
            continue
        for p in sub_dir.rglob("*"):
            if p.is_file() and not is_gitignored_path(str(p.relative_to(project_root)).replace("\\", "/"), project_root):
                basename_map.setdefault(p.name, []).append(p)

    for md_path in md_files:
        lines = md_path.read_text(encoding="utf-8").splitlines(keepends=True)
        in_fence, modified, new_lines = False, False, []
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
                if not target_no_anchor or (md_path.parent / target_no_anchor).resolve().exists():
                    return match.group(0)
                candidates = basename_map.get(Path(target_no_anchor).name, [])
                if len(candidates) == 1:
                    healed_rel = os.path.relpath(candidates[0], md_path.parent).replace("\\", "/") + anchor
                    modified = True
                    healed_records.append({"file": str(md_path.relative_to(project_root)), "old_target": raw_target, "new_target": healed_rel})
                    return f"{prefix}{healed_rel}{suffix}"
                return match.group(0)

            new_lines.append(MD_LINK_PATTERN.sub(_replace_link, line))
        if modified:
            md_path.write_text("".join(new_lines), encoding="utf-8")
    return healed_records


def is_private_memory_path(project_root: Path, md_path: Path) -> bool:
    return "private" in md_path.relative_to(project_root).parts


def _find_pending_topology_alignments(
    subset_fm: Dict[str, Dict[str, Any]], body_by_id: Dict[str, str], path_by_id: Dict[str, str]
) -> List[Dict[str, Any]]:
    pending: List[Dict[str, Any]] = []
    for src_id, fm in subset_fm.items():
        if fm.get("status") != "verified":
            continue
        body = body_by_id.get(src_id, "")
        topo = fm.get("topology", {}) if isinstance(fm.get("topology"), dict) else {}
        declared = set((topo.get("depends_on") or []) + (topo.get("supersedes") or []) + (topo.get("conflicts_with") or []))
        unlinked: List[str] = []
        for target_id, target_fm in sorted(subset_fm.items()):
            if target_id == src_id or target_fm.get("status") != "verified" or target_fm.get("artifact_type") not in ("spec", "audit"):
                continue
            target_key = target_fm.get("context_index", {}).get("node_key", "")
            if target_id in declared or (target_key and target_key in declared):
                continue
            if target_id in body or (target_key and target_key in body):
                unlinked.append(f"{target_id} ({target_key})" if target_key else target_id)
        if unlinked:
            pending.append({"source_node_id": src_id, "source_node_key": fm.get("context_index", {}).get("node_key", ""), "source_path": path_by_id.get(src_id, ""), "unlinked_targets": unlinked})
    return pending


def _compile_index_subset(
    project_root: Path, subset_files: List[Path], all_nodes_fm: Dict[str, Dict[str, Any]],
    key_to_id: Dict[str, str], healed_links: List[Dict[str, str]], include_code_intel: bool = True,
) -> Dict[str, Any]:
    domain_layers = load_domain_layers(project_root)
    entries, edges, raw_parsed_nodes = [], [], []
    by_domain: Dict[str, List[Dict[str, Any]]] = {k: [] for k in domain_layers}
    subset_fm, body_by_id, path_by_id, subset_key_to_id, subset_id_to_key = {}, {}, {}, {}, {}

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
        domain, src_id, node_key = str(idx.get("domain_code", "000")), str(fm.get("node_id", rel_path)), idx.get("node_key")
        if src_id and node_key:
            subset_key_to_id[node_key], subset_id_to_key[src_id] = src_id, node_key
        raw_parsed_nodes.append({"md_path": md_path, "rel_path": rel_path, "fm": fm, "body": body, "domain": domain, "src_id": src_id, "node_key": node_key, "idx": idx, "topo": topo})

    outbound_by_node, backlinks_map = {}, {}
    for node in raw_parsed_nodes:
        src_id, src_key = node["src_id"], node["node_key"]
        canonical_src, resolved_outbound = (src_key if src_key else src_id), []
        for token in extract_wikilinks_outside_fenced_blocks(node["body"]):
            if token in subset_key_to_id:
                target_key, target_id = token, subset_key_to_id[token]
            elif token in subset_id_to_key:
                target_key, target_id = subset_id_to_key[token], token
            else:
                continue
            resolved_outbound.append(target_key)
            backlinks_map.setdefault(target_key, []).append(canonical_src)
            backlinks_map.setdefault(target_id, []).append(canonical_src)
        outbound_by_node[src_id] = sorted(set(resolved_outbound))

    for node in raw_parsed_nodes:
        md_path, rel_path, fm, body = node["md_path"], node["rel_path"], node["fm"], node["body"]
        domain, src_id, node_key, idx, topo = node["domain"], node["src_id"], node["node_key"], node["idx"], node["topo"]
        artifact_type = fm.get("artifact_type", "wiki")
        inferred_track = "official" if artifact_type in OFFICIAL_TYPES else "wiki"
        artifact_track = fm.get("artifact_track") or idx.get("artifact_track") or topo.get("artifact_track") or inferred_track
        subdomain = fm.get("subdomain") or idx.get("subdomain") or topo.get("subdomain") or (domain if domain and domain not in ("000", "100", "200", "300", "400", "500", "600", "700", "800", "900") else None)
        node_backlinks = sorted(set(backlinks_map.get(src_id, []) + (backlinks_map.get(node_key, []) if node_key else [])))
        entry = {
            "node_id": fm.get("node_id"), "artifact_type": artifact_type, "status": fm.get("status"),
            "access_tier": fm.get("access_tier"), "priority": fm.get("priority"), "domain_code": domain,
            "subdomain": subdomain, "artifact_track": artifact_track, "outbound_links": outbound_by_node.get(src_id, []),
            "backlinks": node_backlinks, "node_key": node_key, "facet_tags": idx.get("facet_tags", []),
            "keywords": idx.get("keywords", []), "summary_1line": idx.get("summary_1line", ""),
            "path": rel_path, "sha256_16": sha256_file(md_path),
            "author_model": fm.get("author", {}).get("model") if isinstance(fm.get("author"), dict) else None,
            "reviewer_model": fm.get("reviewer", {}).get("model") if isinstance(fm.get("reviewer"), dict) else None,
            "depends_on": topo.get("depends_on", []) if isinstance(topo, dict) else [],
            "supersedes": topo.get("supersedes", []) if isinstance(topo, dict) else [],
            "affected_paths": topo.get("affected_paths", []) if isinstance(topo, dict) else [],
            "parent_blueprint": topo.get("parent_blueprint") if isinstance(topo, dict) else None,
            "shard_modules": topo.get("shard_modules", []) if isinstance(topo, dict) else [],
            "stub_paths": topo.get("stub_paths", []) if isinstance(topo, dict) else [],
        }
        entries.append(entry)
        by_domain.setdefault(domain, []).append(entry)
        subset_fm[src_id], body_by_id[src_id], path_by_id[src_id] = fm, body, rel_path

    for entry in entries:
        src_id = entry["node_id"]
        for dep in entry.get("depends_on", []):
            edges.append({"from": src_id, "to": key_to_id.get(dep, dep), "relation": "depends_on"})
        for sup in entry.get("supersedes", []):
            edges.append({"from": src_id, "to": key_to_id.get(sup, sup), "relation": "supersedes"})
        if isinstance(parent_bp := entry.get("parent_blueprint"), str) and parent_bp.strip():
            edges.append({"from": src_id, "to": key_to_id.get(parent_bp, parent_bp), "relation": "shard_of"})

    pending_topology_alignments = _find_pending_topology_alignments(subset_fm, body_by_id, path_by_id)
    domain_stats = {code: len(by_domain.get(code, [])) for code in domain_layers}
    facet_registry: Dict[str, int] = {}
    for entry in entries:
        for tag in entry.get("facet_tags", []) or []:
            if isinstance(tag, str) and tag.strip():
                facet_registry[tag] = facet_registry.get(tag, 0) + 1

    code_dependency_edges, intel_map = scan_code_intelligence_single_pass(project_root, entries) if include_code_intel else ([], {})
    codebook_map = compile_codebook_map(project_root, entries, intel_map) if include_code_intel else {}
    return {
        "schema_version": "2.3.0", "project": project_root.name, "harness": "NetArk",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_nodes": len(entries), "healed_links": healed_links,
        "pending_topology_alignments": pending_topology_alignments, "domain_stats": domain_stats,
        "facet_registry": facet_registry,
        "domain_registry": {code: {"title": title, "count": len(by_domain.get(code, [])), "items": by_domain.get(code, [])} for code, title in domain_layers.items()},
        "causal_topology_edges": edges, "code_dependency_edges": code_dependency_edges,
        "code_intelligence_map": intel_map, "codebook_map": codebook_map,
    }


def build_public_and_private_indices(project_root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    memory_dir = project_root / "memory"
    if not memory_dir.exists():
        empty = _compile_index_subset(project_root, [], {}, {}, [], include_code_intel=True)
        return empty, _compile_index_subset(project_root, [], {}, {}, [], include_code_intel=False)

    md_files = sorted(p for p in memory_dir.rglob("*.md") if p.name != "CONTEXT_MAP.md")
    healed_links = heal_dead_links(project_root, md_files)
    all_nodes_fm, key_to_id, public_files, private_files = {}, {}, [], []
    for md_path in md_files:
        rel_md = str(md_path.relative_to(project_root)).replace("\\", "/")
        try:
            fm, _ = parse_markdown_frontmatter(md_path)
        except Exception:
            continue
        if not isinstance(fm, dict) or not fm.get("node_id"):
            continue
        (private_files if (is_private_memory_path(project_root, md_path) or is_gitignored_path(rel_md, project_root)) else public_files).append(md_path)
        nid = fm.get("node_id")
        nkey = fm.get("context_index", {}).get("node_key") if isinstance(fm.get("context_index"), dict) else None
        if nid:
            all_nodes_fm[nid] = fm
        if nkey and nid:
            key_to_id[nkey] = nid

    public_healed = [h for h in healed_links if not is_gitignored_path(h["file"], project_root) and "private" not in Path(h["file"]).parts]
    private_healed = [h for h in healed_links if is_gitignored_path(h["file"], project_root) or "private" in Path(h["file"]).parts]
    public_index = _compile_index_subset(project_root, public_files, all_nodes_fm, key_to_id, public_healed, include_code_intel=True)
    private_index = _compile_index_subset(project_root, private_files, all_nodes_fm, key_to_id, private_healed, include_code_intel=False)
    return public_index, private_index


def verify_no_plaintext_secrets_before_index_write(project_root: Path, index: Dict[str, Any]) -> None:
    """G-05 Fix: Enforce scan_plaintext_secrets() on compiled CONTEXT_INDEX payload and HANDOVER.md before persisting."""
    if (findings := scan_plaintext_secrets(json.dumps(index, ensure_ascii=False), cwd=str(project_root))):
        raise RuntimeError(f"[G-05 SEC-INDEX-SECRET] Blocked CONTEXT_INDEX.json write: detected plaintext secret ({findings[0]['type']}) in memory index metadata.")
    handover_path = project_root / "memory" / "episodic" / "HANDOVER.md"
    if handover_path.exists() and (h_findings := scan_plaintext_secrets(handover_path.read_text(encoding="utf-8", errors="ignore"), cwd=str(project_root))):
        raise RuntimeError(f"[G-05 SEC-HANDOVER-SECRET] Blocked index compilation: detected plaintext secret ({h_findings[0]['type']}) in memory/episodic/HANDOVER.md.")


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
        private_map_path.write_text(render_private_context_map(project_root, private_index), encoding="utf-8")
    else:
        for p in (private_index_path, private_map_path):
            if p.exists():
                p.unlink()

    map_path = project_root / "memory" / "codex" / "CONTEXT_MAP.md"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(render_context_map(project_root, index), encoding="utf-8")

    if (healed := index.get("healed_links", []) + private_index.get("healed_links", [])):
        print(f"🩹 Auto-healed {len(healed)} broken relative Markdown link(s): {healed}")
    cb = index.get("codebook_map", {})
    print(f"✅ Compiled CONTEXT_INDEX.json ({index['total_nodes']} public nodes, {cb.get('total_scripts', 0)} scripts, Tier={cb.get('tier', 'L1-Full')}, Compression={cb.get('compression_ratio_pct', 0.0)}%) -> {index_path}")
    if private_index.get("total_nodes", 0) > 0:
        print(f"🔒 Compiled PRIVATE_INDEX.json ({private_index['total_nodes']} private nodes, git-ignored) -> {private_index_path}")
        print(f"🔒 Rendered Private CONTEXT_MAP.md -> {private_map_path}")
    print(f"✅ Rendered CONTEXT_MAP.md -> {map_path}")
    if args.print_codebook and cb.get("compact_text"):
        print("\n" + cb["compact_text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
