#!/usr/bin/env python3
"""
NetArk Turn-1 Frozen @D/@R/@M/@C/@G Codebook Compiler & Context Map Renderer (codebook_compiler.py)
===================================================================================================
Governing Node: 100.ARCH-RULES.v1 (MEM-2026-0002) & 200.ADR-001.v1 (MEM-2026-0003)
1. Compiles `@D/@R/@M/@C/@G` compressed codebook map with `[HYG-AST]` and `[HYG-DEBUG]` Turn-1 injection.
   Short codes are stable (derived from each file's own name/seq, F1-F4); duplicates fail fast (`[CODEBOOK-DUP-CODE]`).
2. Renders `CONTEXT_MAP.md` and `memory/private/CONTEXT_MAP.md` with active vs. archived/deprecated separation.
"""

from __future__ import annotations

import json, re, sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas.code_hygiene_ast import get_brain_rel_dir  # noqa: E402


def _select_codebook_scripts(tier: str, ordered_scripts: List[str], governed_set: set[str], priority_order: List[str]) -> Tuple[List[str], List[str]]:
    if tier == "L1-Full":
        return list(ordered_scripts), []
    if tier == "L3-ActiveCone":
        return [p for p in ordered_scripts if p in governed_set or p in priority_order[:8]][:40], []
    selected_scripts, cluster_entries, dir_groups = [], [], {}
    for p in ordered_scripts:
        if p in governed_set or p in priority_order:
            selected_scripts.append(p)
        else:
            dir_groups.setdefault(str(Path(p).parent).replace("\\", "/"), []).append(p)
    for dparent, group_files in sorted(dir_groups.items()):
        if len(group_files) <= 2:
            selected_scripts.extend(group_files)
        else:
            cluster_entries.append(f"M_{re.sub(r'[^A-Za-z0-9]', '_', dparent).upper().strip('_')[:12]}={dparent}/*({len(group_files)} files)")
    return selected_scripts, cluster_entries


def _derive_entry_short_code(entry: Dict[str, Any]) -> str:
    """F1-F4 (700.CODEBOOK_SHORT_CODE_DRIFT): short code is a pure function of the entry's own path/domain (never a sequential counter)."""
    npath = str(entry.get("path") or "").replace("\\", "/")
    fname = Path(npath).name
    dc = str(entry.get("domain_code") or "000")
    nkey = str(entry.get("node_key") or entry.get("node_id") or dc)
    if fname == "HANDOVER.md":
        return dc or "900"
    if fname == "LEDGER.md":
        return "300"
    if npath.startswith("memory/codex/") and (m := re.match(r"^(\d{3})_(?!\d)", fname)):
        return m.group(1)
    if m := re.match(r"^HANDOVER_(\d{2})_.*\.md$", fname):
        return f"{dc}.H{int(m.group(1))}"
    m_sub = re.match(r"^(\d{3})_(\d{2})_(\d{1,2})_[A-Za-z]", fname)
    m_std = m_sub or re.match(r"^(\d{3})_(\d{2})_", fname)
    if not m_std:
        return nkey
    file_dom, seq = m_std.group(1), int(m_std.group(2))
    prefix = f"{file_dom}.S{seq}" if (file_dom == "700" and npath.startswith("memory/specs/")) else f"{file_dom}.{seq}"
    return f"{prefix}.{int(m_sub.group(3))}" if m_sub else prefix


def _short_code_sort_key(code: str, nkey: str, nid: str) -> Tuple[Any, ...]:
    parts: List[Tuple[Any, ...]] = []
    for part in str(code).split("."):
        m = re.match(r"^([A-Za-z_-]*)(\d*)(.*)$", part)
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, m.group(1), int(m.group(2) or 0), m.group(3)))
    return (tuple(parts), nkey, nid)


def _build_node_short_map(active_entries: List[Dict[str, Any]]) -> Dict[str, str]:
    node_short_map: Dict[str, str] = {}
    code_owner: Dict[str, str] = {}
    for e in active_entries:
        nid, nkey = str(e.get("node_id") or ""), str(e.get("node_key") or "")
        ncode = _derive_entry_short_code(e)
        if ncode in code_owner:
            raise ValueError(f"[CODEBOOK-DUP-CODE] Duplicate short code '{ncode}' for '{code_owner[ncode]}' and '{e.get('path') or nkey}'")
        code_owner[ncode] = str(e.get("path") or nkey)
        node_short_map[nid] = ncode
        if nkey:
            node_short_map[nkey] = ncode
    return node_short_map


def _collect_governed_script_codes(entry: Dict[str, Any], script_to_code: Dict[str, str]) -> List[str]:
    gov_c_codes: List[str] = []
    for aff in (entry.get("affected_paths") or []) + (entry.get("stub_paths") or []):
        aff_norm = str(aff).strip().replace("\\", "/")
        if aff_norm in script_to_code:
            if (sc := script_to_code[aff_norm]) not in gov_c_codes:
                gov_c_codes.append(sc)
            continue
        prefix = aff_norm.rstrip("/") + "/"
        gov_c_codes.extend(sc for sp, sc in script_to_code.items() if sp.startswith(prefix) and sc not in gov_c_codes)
    return gov_c_codes


def _extract_entry_topic(entry: Dict[str, Any]) -> str:
    if (t := str(entry.get("topic") or "").strip()):
        return t
    tags = entry.get("facet_tags")
    return str(tags[0]).split(":")[1].strip() if isinstance(tags, list) and tags and ":" in str(tags[0]) else ""


def _load_active_handover_pins(project_root: Path) -> Set[str]:
    """Extract active_shards from HANDOVER.md if present and not archived/completed."""
    ho_path = project_root / "memory" / "episodic" / "HANDOVER.md"
    if not ho_path.is_file():
        return set()
    try:
        text = ho_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    m_fm = re.match(r"^---\n([\s\S]*?)\n---\n", text)
    fm = m_fm.group(1) if m_fm else text
    for fld in ("status", "track_status"):
        if (ms := re.search(rf'(?m)^{fld}:\s*["\']?([A-Za-z_-]+)', fm)) and ms.group(1).lower() in {"archived", "deprecated", "completed"}:
            return set()
    if not (m_sh := re.search(r"(?m)^[ \t]*active_shards:[ \t]*(.*)$", text)):
        return set()
    inline = re.sub(r"(?:^|\s+)#.*$", "", m_sh.group(1)).strip()
    if inline.startswith("[") and inline.endswith("]"):
        return {x.strip().strip("\"'") for x in inline[1:-1].split(",") if x.strip().strip("\"'")}
    if inline:
        val = inline.strip("\"'")
        return {val} if val and val.lower() not in {"null", "none", "~"} else set()
    pins: Set[str] = set()
    for ln in text[m_sh.end():].splitlines()[1:]:
        if not ln.strip() or ln.strip().startswith("#"):
            continue
        if not ln.startswith((" ", "\t", "-")) or not (mi := re.match(r"^[ \t]*-\s+(.+?)(?:\s+#.*)?$", ln)):
            break
        if (val := mi.group(1).strip().strip("\"'")):
            pins.add(val)
    return pins


def _bp_children(bp: Dict[str, Any], active_entries: List[Dict[str, Any]], bp_shards: Set[str]) -> List[Dict[str, Any]]:
    bp_refs = {x for x in (str(bp.get("node_id") or ""), str(bp.get("node_key") or "")) if x}
    return [c for c in active_entries if c is not bp and (str(c.get("parent_blueprint") or "").strip() in bp_refs or str(c.get("node_key") or "") in bp_shards or str(c.get("node_id") or "") in bp_shards)]


def _compute_blueprint_folding(active_entries: List[Dict[str, Any]], active_pins: Set[str]) -> Tuple[Set[str], Dict[str, str]]:
    """Fold shard_modules of blueprints with >= 2 active children unless pinned."""
    folded_ids, bp_summaries = set(), {}
    for bp in active_entries:
        bp_shards = {str(s).strip() for s in (bp.get("shard_modules") or []) if str(s).strip()}
        if bp.get("artifact_type") != "blueprint" and bp.get("type") != "blueprint" and len(bp_shards) < 2:
            continue
        children = _bp_children(bp, active_entries, bp_shards)
        if len(children) < 2:
            continue
        v_cnt = sum(1 for c in children if c.get("status") == "verified")
        s_cnt = sum(1 for c in children if c.get("status") == "stub_ready")
        bp_summaries[str(bp.get("node_id") or "")] = f"|{len(children)} shards: {v_cnt}✅ {s_cnt}🟡 {len(children) - v_cnt - s_cnt}🟠"
        for c in children:
            cid, ckey = str(c.get("node_id") or ""), str(c.get("node_key") or "")
            if c.get("context_pin") != "always" and ckey not in active_pins and cid not in active_pins:
                folded_ids.add(cid)
    return folded_ids, bp_summaries


def _format_310_stem(entry: Dict[str, Any]) -> str:
    stem = re.sub(r"^310_", "", Path(str(entry.get("path") or entry.get("node_key") or entry.get("node_id") or "")).stem)
    for sfx in ("_BLUEPRINT_NOTE", "_SUPPLEMENT_NOTE", "_NOTE"):
        if stem.endswith(sfx):
            return stem[: -len(sfx)] or str(entry.get("node_key") or entry.get("node_id") or "")
    return stem or str(entry.get("node_key") or entry.get("node_id") or "")


def _build_310_topic_directory(
    active_entries: List[Dict[str, Any]], node_short_map: Dict[str, str], folded_shard_ids: Set[str], active_pins: Set[str]
) -> Tuple[Set[str], str]:
    """Group foldable 310 entries into status -> topic lead-index when repo exceeds threshold."""
    active_310 = [e for e in active_entries if str(e.get("subdomain") or e.get("domain_code") or e.get("domain") or "") == "310" and str(e.get("node_id") or "") not in folded_shard_ids]
    if len(active_entries) <= 25 and len(active_310) <= 8:
        return set(), ""
    grouped, folded_310 = {}, set()
    for e in active_310:
        nid, nkey = str(e.get("node_id") or ""), str(e.get("node_key") or "")
        if e.get("context_pin") == "always" or nkey in active_pins or nid in active_pins:
            continue
        folded_310.add(nid)
        st = str(e.get("status") or "draft")
        st = st if st in {"reviewing", "draft", "stub_ready", "verified"} else "draft"
        code = node_short_map.get(nid, node_short_map.get(nkey, "310"))
        grouped.setdefault(st, {}).setdefault(_extract_entry_topic(e) or "General", []).append(f"{code}={_format_310_stem(e)}")
    if not folded_310:
        return set(), ""
    buckets = (("reviewing", "🔵待立項[reviewing]"), ("draft", "🟠討論中[draft]"), ("stub_ready", "🟡就緒[stub_ready]"), ("verified", "🟢常駐[verified]"))
    parts = [f"{lbl}{{{' | '.join(f'{t}: ' + ', '.join(its) for t, its in grouped[st].items())}}}" for st, lbl in buckets if st in grouped]
    return folded_310, "310_wiki: " + " | ".join(parts)


def compile_codebook_map(  # noqa: god-function
    project_root: Path, entries: List[Dict[str, Any]], intel_map: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """D-05: Compile Turn-1 Frozen @D/@C/@G Codebook Map with L1/L2/L3 scale tiering and reverse_lookup dictionary."""
    brain_rel = get_brain_rel_dir(project_root)
    active_entries = [e for e in entries if e.get("status") not in ("archived", "deprecated")]
    node_short_map = _build_node_short_map(active_entries)
    active_entries.sort(key=lambda e: _short_code_sort_key(node_short_map.get(str(e.get("node_id") or ""), node_short_map.get(str(e.get("node_key") or ""), str(e.get("domain_code") or "000"))), str(e.get("node_key") or ""), str(e.get("node_id") or "")))
    total_scripts, total_nodes = len(intel_map), len(active_entries)
    tier = "L1-Full" if (total_scripts <= 150 and total_nodes <= 80) else ("L2-Cluster" if total_scripts <= 1500 else "L3-ActiveCone")
    canonical_dirs = [("M", "memory/"), ("C", "memory/codex/"), ("E", "memory/episodic/"), ("P", "memory/specs/"), ("W", "memory/wiki/"), ("A", "memory/audits/"), ("H", "schemas/"), ("S", "scripts/"), ("J", "projects/"), ("X", f"{brain_rel}/extensions/"), ("XS", f"{brain_rel}/extensions/subagent/")]
    dir_to_code, code_to_dir = {p: c for c, p in canonical_dirs}, {c: p for c, p in canonical_dirs}
    used_dir_codes: List[str] = ["J"] if (project_root / "projects").is_dir() else []
    dyn_dir_counter = 0

    def _register_dir(file_rel: str) -> Tuple[str, str]:
        nonlocal dyn_dir_counter
        parent = str(Path(file_rel).parent).replace("\\", "/")
        dir_prefix = "./" if parent in ("", ".") else (parent.rstrip("/") + "/")
        if dir_prefix not in dir_to_code:
            while f"D{dyn_dir_counter}" in code_to_dir:
                dyn_dir_counter += 1
            dcode = f"D{dyn_dir_counter}"
            dyn_dir_counter += 1
            dir_to_code[dir_prefix], code_to_dir[dcode] = dcode, dir_prefix
        dcode = dir_to_code[dir_prefix]
        if dcode not in used_dir_codes:
            used_dir_codes.append(dcode)
        return dcode, Path(file_rel).name

    priority_order = ["schemas/schema_validator.py", "schemas/netark_guard_core.py", "schemas/code_hygiene_ast.py", "schemas/codebook_compiler.py", "schemas/topology_graph.py", "schemas/doc_initializer.py", "scripts/auto_update_map.py", "scripts/netark_guard_daemon.py", "scripts/netark_init.py", "scripts/sync_doc_metadata.py", f"{brain_rel}/extensions/epistemic-gate.ts", "schemas/workspace_placement_guard.py", "schemas/hook_lifecycle.py", "schemas/ribc_gate.py"]
    governed_set = {aff.strip().replace("\\", "/") for e in active_entries for aff in (e.get("affected_paths") or []) + (e.get("stub_paths") or []) if isinstance(aff, str) and aff.strip()}
    ordered_scripts = [p for p in priority_order if p in intel_map] + [p for p in sorted(intel_map.keys()) if p not in priority_order]
    selected_scripts, cluster_entries = _select_codebook_scripts(tier, ordered_scripts, governed_set, priority_order)
    for e in active_entries:
        _register_dir(str(e.get("path") or ""))
    for sp in selected_scripts:
        _register_dir(sp)

    script_to_code, reverse_lookup, c_tokens = {}, {}, []
    for idx, sp in enumerate(selected_scripts):
        ccode = f"C{idx}"
        script_to_code[sp] = ccode
        dcode, fname = _register_dir(sp)
        info = intel_map.get(sp, {})
        total_lines = info.get("total_lines", 1)
        c_tokens.append(f"{ccode}={dcode}:{fname}(L1-{total_lines})")
        reverse_lookup[ccode] = {"kind": "script", "code": ccode, "path": sp, "dir_code": dcode, "line_range": f"L1-{total_lines}", "project": (sp.split("/")[1] if sp.startswith("projects/") and len(sp.split("/")) >= 3 else "netark_core"), "total_lines": total_lines, "language": info.get("language", "unknown"), "symbols": info.get("symbols", []), "pi_registrations": info.get("pi_registrations", []), "governing_specs": info.get("governing_specs", [])}
    c_tokens.extend(cluster_entries)

    canonical_order_keys = [c for c, _ in canonical_dirs]
    sorted_dir_codes = [c for c in canonical_order_keys if c in used_dir_codes] + [c for c in used_dir_codes if c not in canonical_order_keys]
    for dcode in sorted_dir_codes:
        reverse_lookup[dcode] = {"kind": "dir", "code": dcode, "path": code_to_dir[dcode]}

    active_pins = _load_active_handover_pins(project_root)
    folded_shard_ids, bp_summaries = _compute_blueprint_folding(active_entries, active_pins)
    folded_310_ids, wiki_dir_line = _build_310_topic_directory(active_entries, node_short_map, folded_shard_ids, active_pins)
    explicit_folded_ids = {eid for e in active_entries if (eid := str(e.get("node_id") or e.get("node_key") or "")) and str(e.get("context_pin") or (e.get("context_index") or {}).get("context_pin") or "").lower() == "folded" and str(e.get("node_id") or "") not in active_pins and str(e.get("node_key") or "") not in active_pins}
    folded_ids = folded_shard_ids | folded_310_ids | explicit_folded_ids
    active_topics: Dict[str, int] = {}
    m_tokens, dag_edges, syn_edges = [], [], []
    for e in active_entries:
        nid, nkey, status = str(e.get("node_id") or ""), str(e.get("node_key") or str(e.get("node_id") or "")), str(e.get("status") or "draft")
        summary, npath = str(e.get("summary_1line") or "").replace('"', "'"), str(e.get("path") or "")
        ncode = node_short_map.get(nid, node_short_map.get(nkey, str(e.get("domain_code") or "000")))
        dcode, fname = _register_dir(npath)
        topic = _extract_entry_topic(e) or None
        if topic:
            active_topics[topic] = active_topics.get(topic, 0) + 1
        gov_c_codes = _collect_governed_script_codes(e, script_to_code)
        is_folded = (nid in folded_ids) or (nkey in folded_ids)
        if not is_folded:
            m_tokens.append(f"{ncode}={dcode}:{fname}[{nkey}|{status}{bp_summaries.get(nid, '')}]")
            if (dep_codes := list(dict.fromkeys(node_short_map.get(str(dep), str(dep)) for dep in (e.get("depends_on") or []) if node_short_map.get(str(dep), str(dep))))):
                dag_edges.append(f"{ncode} < {','.join(dep_codes)}")
            if gov_c_codes:
                syn_edges.append(f"{ncode} => {','.join(gov_c_codes)}")
        node_meta = {"kind": "node", "code": ncode, "node_id": nid, "node_key": nkey, "status": status, "path": npath, "artifact_type": e.get("artifact_type") or e.get("type") or "", "domain_code": str(e.get("domain_code") or ""), "subdomain": e.get("subdomain"), "topic": topic, "context_pin": str(e.get("context_pin") or "auto"), "parent_blueprint": e.get("parent_blueprint"), "shard_modules": e.get("shard_modules") or [], "stub_paths": e.get("stub_paths") or [], "folded": is_folded, "summary_1line": summary, "depends_on": e.get("depends_on") or [], "governed_scripts": gov_c_codes, "affected_paths": e.get("affected_paths") or []}
        reverse_lookup[ncode] = reverse_lookup[nkey] = node_meta
        if nid:
            reverse_lookup[nid] = node_meta

    ast_edges = [f"{sc} -> {','.join(dc)}" for sp in selected_scripts if (sc := script_to_code.get(sp)) and (dc := list(dict.fromkeys(ic for imp in intel_map.get(sp, {}).get("imports", []) if (ic := script_to_code.get(str(imp))) and ic != sc)))]
    d_line_tokens = [f"{dcode}={code_to_dir[dcode]}" for dcode in sorted_dir_codes]
    m_rows = ["  " + " | ".join(m_tokens[i : i + 3]) for i in range(0, len(m_tokens), 3)]
    if wiki_dir_line:
        m_rows.append(f"  {wiki_dir_line}")
    if folded_ids:
        m_rows.append(f"  folded: {len(folded_ids)} nodes")
    c_rows = ["  " + " | ".join(c_tokens[i : i + 3]) for i in range(0, len(c_tokens), 3)]
    g_lines = [
        *[f"  [{tag}] {' | '.join(edges) if edges else '(none)'}" for tag, edges in (("DAG", dag_edges), ("SYN", syn_edges), ("AST", ast_edges))],
        "  [HYG-AST] Python functions max control-flow nesting <= 4 layers (use Early-Return); NEVER write silent 'except: pass' without '# noqa: silent-except'; target file size <= 400 lines (hard cap 550).",
        "  [HYG-DEBUG] On bug/unexpected return, NEVER patch locally with nested if/try; trace backward [Return Point -> Call Chain -> Entry Input] and add Fail-Fast validation at entry.",
        "  [DELEGATE] Mandatory IF-THEN Routing: (1) Multi-file search or messy/large doc digestion (>=2 files or >600 lines, e.g. in scratch/) -> MUST call invoke_subagent(TypeName='research', ...) instead of manual sliced read; (2) Code implementation/refactoring (>50 lines or multi-file) -> MUST delegate via invoke_subagent(TypeName='self', ...) with [R]/[I]/[B]/[C] & >=60 chars (SPEC-RIBC-GATE); (3) NEVER use run_command(cat << EOF) or /tmp to bypass write_file/edit_file AST gates.",
    ]
    compact_text = "\n".join([
        f"## 🧭 [{project_root.name} Turn-1 Frozen Codebook Map] (Nodes: {total_nodes} | Scripts: {len(selected_scripts)} | Tier: {tier})",
        f"@D (Dirs): {' '.join(d_line_tokens)}",
        "@R (Write Route): 業務專案程式碼->J(projects/<project_id>/{src,scripts,tests,configs}/) | 開架知識庫(領域百科wiki/操作指南sop/詞彙表glossary/討論與備忘錄note)->W(memory/wiki/)[310-499,免雙審自動補標頭] | 抓蟲/修復藍帖->A(memory/audits/)[type:audit] | 已拍板新規格->P(memory/specs/)[type:spec] | 活躍工單->M:LEDGER.md | 臨時草稿->scratch/ (未定案嚴禁建spec；修Bug嚴禁塗改舊藍圖) | 生命週期: draft(規劃/施工中) -> verified(實測通過定稿) -> archived(討論筆記已收斂升級封存，保留 depends_on 脈絡但過濾 @M 視野) / deprecated(路線廢棄)",
        "@M (Nodes):", *(m_rows if m_rows else ["  (none)"]), "@C (Scripts):", *(c_rows if c_rows else ["  (none)"]),
        "@G (Topology Graph — DAG / Governance Synapses / Code AST Imports):", *g_lines,
        '💡 [Lookup Rule]: `<` 表示 depends_on，`=>` 表示記憶管轄腳本，`->` 表示程式碼 AST 引用；地圖含縮寫簡稱與折疊節點且不含章節／函式行號，凡需定位未知／折疊路徑、章節或函式行號（嚴禁猜檔名或整讀 >200 行檔案），或查詢 status:reviewing | status:draft | 310:draft | <Topic>，請先呼叫 netark_query(query=...) 再做局部行號讀取；寫改記憶檔呼叫 netark_record(intent, title, body, mode=\'preflight\'|\'write\', target_path?)；盤點交接軌／驗收／狀態呼叫 netark_guard(action=\'handover\'|\'oracle\'|\'status\'|\'setup\')，嚴禁整讀 CONTEXT_MAP.md (\'## 2.\' 之後)（CLI 備援：`python3 scripts/auto_update_map.py --query "200"`）。',
    ])
    raw_uncompressed_est = sum(len(str(e.get("path", ""))) * 3 + len(str(e.get("summary_1line", ""))) + len(json.dumps(e, ensure_ascii=False)) for e in active_entries) + sum(len(sp) * 4 + len(json.dumps(intel_map.get(sp, {}), ensure_ascii=False)) for sp in selected_scripts)
    saved_pct = round((1.0 - (len(compact_text) / max(raw_uncompressed_est, len(compact_text) + 1))) * 100.0, 1)
    return {"tier": tier, "total_nodes": total_nodes, "total_scripts": len(selected_scripts), "raw_char_estimate": raw_uncompressed_est, "compact_char_count": len(compact_text), "compression_ratio_pct": saved_pct, "dirs": {dc: code_to_dir[dc] for dc in sorted_dir_codes}, "scripts": {script_to_code[sp]: sp for sp in selected_scripts}, "active_topics": dict(sorted(active_topics.items())), "compact_text": compact_text, "reverse_lookup": reverse_lookup}


build_codebook_map = compile_codebook_map


def _append_registry_section(lines: List[str], heading: str, items: List[Dict[str, Any]], tbl_hdr: str) -> None:
    if not items:
        return
    lines.extend([f"### {heading} ({len(items)} 節點)", "", tbl_hdr])
    lines.extend(f"| `{it['node_id']}` | `{it['node_key']}` | `{it.get('artifact_track', 'official')}` | `{it['artifact_type']}` | `{it['status']}` | {it['summary_1line']} | [`{it['path']}`](../../{it['path']}) |" for it in items)
    lines.append("")


def render_context_map(project_root: Path, index: Dict[str, Any]) -> str:
    brain_rel = get_brain_rel_dir(project_root)
    codebook_text = (index.get("codebook_map") or {}).get("compact_text", "")
    lines: List[str] = [
        f"# 🗺️ {project_root.name} × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)", "",
        f"> **自動生成時間**: `{index['generated_at']}` | **Agentic Harness**: `{index['harness']}` | **記憶節點總數**: `{index['total_nodes']}`",
        "> **漸進式揭露原則 (Progressive Disclosure)**: Agent 啟動時於 Turn 1 凍結注入 `@D/@C/@G` 代號壓縮地圖，按短代號 (`C0..Cn` / `000..900`) 或節點鍵值 (`node_key`) 按需調閱對應檔案。", "",
    ]
    if codebook_text:
        lines.extend(["## 0. Turn-1 凍結代號壓縮地圖 (`@D/@C/@G` Codebook Map)", "", "```text", codebook_text, "```", ""])
    lines.extend(["## 1. 領域分層註冊表 (Domain Layer Registry)", ""])
    historical_items: List[Dict[str, Any]] = []
    tbl_hdr = "| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |\n| :--- | :--- | :---: | :---: | :---: | :--- | :--- |"
    for _, layer in index["domain_registry"].items():
        items = layer["items"]
        active_items = [it for it in items if it.get("status") not in ("archived", "deprecated")]
        historical_items.extend(it for it in items if it.get("status") in ("archived", "deprecated"))
        _append_registry_section(lines, f"📂 `{layer['title']}`", active_items, tbl_hdr)
    _append_registry_section(lines, "🗄️ 歷史封存與退役節點紀錄表 (Archived & Deprecated Historical Nodes)", historical_items, tbl_hdr)
    lines.extend(["## 2. 因果拓撲依賴邊 (Causal Topology DAG Edges)", "", "| 下游節點 (`from`) | 依賴關係 (`relation`) | 上游基礎節點 (`to`) |", "| :--- | :---: | :--- |"])
    lines.extend(f"| `{e['from']}` | `{e['relation']}` | `{e['to']}` |" for e in index["causal_topology_edges"])
    lines.extend(["", "## 3. 程式碼模組依賴圖 (Code-Level AST Dependency Graph)", "", "| 來源模組 (`from`) | 目標依賴 (`to`) | 依賴類型 (`type`) |", "| :--- | :--- | :---: |"])
    lines.extend(f"| `{c['from']}` | `{c['to']}` | `{c['type']}` |" for c in index.get("code_dependency_edges", []))
    if (intel_map := index.get("code_intelligence_map", {})):
        lines.extend(["", "### 3.2 源碼符號、Hook 註冊與規格影響圈總表 (Code Intelligence & Impact Map)", "", "| 源碼路徑 (`file_path`) | 主要符號與行號 (`symbols`) | Pi 擴充註冊 (`command`/`tool`/`hook`) | 影響圈 (`imported_by`) | 綁定規格 (`governing_specs`) |", "| :--- | :--- | :--- | :--- | :--- |"])
        for cpath, info in sorted(intel_map.items()):
            syms = ", ".join(f"`{s['name']}`(L{s['line_start']}-L{s['line_end']})" for s in info.get("symbols", [])[:6]) or "—"
            regs = ", ".join(f"`{r['kind']}:{r['name']}`(L{r['line']})" for r in info.get("pi_registrations", [])[:6]) or "—"
            imp_by = ", ".join(f"`{p}`" for p in info.get("imported_by", [])) or "—"
            specs = ", ".join(f"`{g.get('node_key') or g.get('node_id')}`" for g in info.get("governing_specs", [])) or "—"
            lines.append(f"| `{cpath}` | {syms} | {regs} | {imp_by} | {specs} |")
    lines.extend([
        "", "## 4. 專案治理目錄結構摘要", "",
        f"- `{brain_rel}/` — 專案內嵌可攜式 NetArk Agentic Harness 大腦（含模型路由、安全護欄、漸進式揭露與 5 角色子代理）",
        "- `schemas/` — 記憶節點標頭 (`artifact_header.schema.json`)、Context 拓撲節點 (`context_node.schema.json`)、Tier 0 AST 護欄 (`netark_guard_core.py`) 與防諂媚驗證器 (`schema_validator.py`)",
        "- `memory/codex/` — 核心架構規範 (`000_SOUL.md`, `100_ARCH_RULES.md`, `200_DECISIONS.md`) 與自動編譯總目錄 (`CONTEXT_MAP.md`)",
        "- `memory/LEDGER.md` — 專案唯一活躍工單台帳 (`<= 80` 行)",
        "- `memory/episodic/HANDOVER.md` — 微對話無縫交接快照 (`<= 65` 行)",
        "- `memory/index/CONTEXT_INDEX.json` — 機器可讀之漸進式揭露與 `@D/@C/@G` 代號壓縮索引",
        "- `scripts/` — 索引編譯器 (`auto_update_map.py`)、跨宿主守護程序 (`netark_guard_daemon.py`)、母版安裝器 (`netark_init.py`) 與自動化驗收套件", "",
    ])
    return "\n".join(lines)


render_context_map_md = render_context_map


def render_private_context_map(project_root: Path, private_index: Dict[str, Any]) -> str:
    return render_context_map(project_root, private_index).replace(f"# 🗺️ {project_root.name} × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)", f"# 🔒 {project_root.name} × NetArk Private Context Registry & Topology Map (memory/private/CONTEXT_MAP.md)", 1)


render_private_context_map_md = render_private_context_map
