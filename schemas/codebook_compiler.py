#!/usr/bin/env python3
"""
NetArk Turn-1 Frozen @D/@R/@M/@C/@G Codebook Compiler & Context Map Renderer (codebook_compiler.py)
===================================================================================================
Governing Node: 100.ARCH-RULES.v1 (MEM-2026-0002) & 200.ADR-001.v1 (MEM-2026-0003)
1. Compiles `@D/@R/@M/@C/@G` compressed codebook map with `[HYG-AST]` and `[HYG-DEBUG]` Turn-1 injection.
2. Renders `CONTEXT_MAP.md` and `memory/private/CONTEXT_MAP.md` with active vs. archived/deprecated separation.
"""

from __future__ import annotations

import json, re, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas.code_hygiene_ast import get_brain_rel_dir  # noqa: E402


def _select_codebook_scripts(
    tier: str, ordered_scripts: List[str], governed_set: set[str], priority_order: List[str]
) -> Tuple[List[str], List[str]]:
    if tier == "L1-Full":
        return list(ordered_scripts), []
    if tier == "L3-ActiveCone":
        return [p for p in ordered_scripts if p in governed_set or p in priority_order[:8]][:40], []
    selected_scripts, cluster_entries, dir_groups = [], [], {}
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
    return selected_scripts, cluster_entries


def _build_node_short_map(active_entries: List[Dict[str, Any]]) -> Dict[str, str]:
    domain_counts: Dict[str, int] = {}
    for e in active_entries:
        dc = str(e.get("domain_code") or "000")
        domain_counts[dc] = domain_counts.get(dc, 0) + 1
    domain_seen, node_short_map = {}, {}
    for e in active_entries:
        nid, nkey, dc = str(e.get("node_id") or ""), str(e.get("node_key") or ""), str(e.get("domain_code") or "000")
        if domain_counts.get(dc, 0) == 1:
            ncode = dc
        else:
            seen_idx = domain_seen.get(dc, 0) + 1
            domain_seen[dc] = seen_idx
            ncode = dc if seen_idx == 1 else f"{dc}.{seen_idx}"
        node_short_map[nid] = ncode
        if nkey:
            node_short_map[nkey] = ncode
    return node_short_map


def _collect_governed_script_codes(entry: Dict[str, Any], script_to_code: Dict[str, str]) -> List[str]:
    gov_c_codes: List[str] = []
    for aff in (entry.get("affected_paths") or []) + (entry.get("stub_paths") or []):
        aff_norm = str(aff).strip().replace("\\", "/")
        if aff_norm in script_to_code:
            sc = script_to_code[aff_norm]
            if sc not in gov_c_codes:
                gov_c_codes.append(sc)
            continue
        prefix = aff_norm.rstrip("/") + "/"
        for sp, sc in script_to_code.items():
            if sp.startswith(prefix) and sc not in gov_c_codes:
                gov_c_codes.append(sc)
    return gov_c_codes


def compile_codebook_map(
    project_root: Path, entries: List[Dict[str, Any]], intel_map: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """D-05: Compile Turn-1 Frozen @D/@C/@G Codebook Map with L1/L2/L3 scale tiering and reverse_lookup dictionary."""
    brain_rel = get_brain_rel_dir(project_root)
    active_entries = sorted(
        [e for e in entries if e.get("status") not in ("archived", "deprecated")],
        key=lambda e: (str(e.get("domain_code") or "999"), str(e.get("node_key") or ""), str(e.get("node_id") or "")),
    )
    total_scripts, total_nodes = len(intel_map), len(active_entries)
    tier = "L1-Full" if (total_scripts <= 150 and total_nodes <= 80) else ("L2-Cluster" if total_scripts <= 1500 else "L3-ActiveCone")
    canonical_dirs = [
        ("M", "memory/"), ("C", "memory/codex/"), ("E", "memory/episodic/"), ("P", "memory/specs/"),
        ("W", "memory/wiki/"), ("A", "memory/audits/"), ("H", "schemas/"), ("S", "scripts/"),
        ("X", f"{brain_rel}/extensions/"), ("XS", f"{brain_rel}/extensions/subagent/"),
    ]
    dir_to_code = {path: code for code, path in canonical_dirs}
    code_to_dir = {code: path for code, path in canonical_dirs}
    used_dir_codes: List[str] = []
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
            dir_to_code[dir_prefix] = dcode
            code_to_dir[dcode] = dir_prefix
        dcode = dir_to_code[dir_prefix]
        if dcode not in used_dir_codes:
            used_dir_codes.append(dcode)
        return dcode, Path(file_rel).name

    priority_order = [
        "schemas/schema_validator.py", "schemas/netark_guard_core.py", "schemas/code_hygiene_ast.py",
        "schemas/codebook_compiler.py", "schemas/topology_graph.py", "schemas/doc_initializer.py",
        "scripts/auto_update_map.py", "scripts/netark_guard_daemon.py", "scripts/netark_init.py",
        "scripts/sync_doc_metadata.py", f"{brain_rel}/extensions/epistemic-gate.ts",
        f"{brain_rel}/extensions/workspace-guard.ts", f"{brain_rel}/extensions/model-router.ts",
        f"{brain_rel}/extensions/session-handover.ts", f"{brain_rel}/extensions/web-research.ts",
    ]
    governed_set = {
        aff.strip().replace("\\", "/")
        for e in active_entries
        for aff in (e.get("affected_paths") or []) + (e.get("stub_paths") or [])
        if isinstance(aff, str) and aff.strip()
    }
    ordered_scripts = [p for p in priority_order if p in intel_map]
    ordered_scripts.extend(p for p in sorted(intel_map.keys()) if p not in ordered_scripts)
    selected_scripts, cluster_entries = _select_codebook_scripts(tier, ordered_scripts, governed_set, priority_order)

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
            "kind": "script", "code": ccode, "path": sp, "dir_code": dcode, "line_range": f"L1-{total_lines}",
            "total_lines": total_lines, "language": info.get("language", "unknown"), "symbols": info.get("symbols", []),
            "pi_registrations": info.get("pi_registrations", []), "governing_specs": info.get("governing_specs", []),
        }
    c_tokens.extend(cluster_entries)

    canonical_order_keys = [c for c, _ in canonical_dirs]
    sorted_dir_codes = [c for c in canonical_order_keys if c in used_dir_codes] + [c for c in used_dir_codes if c not in canonical_order_keys]
    for dcode in sorted_dir_codes:
        reverse_lookup[dcode] = {"kind": "dir", "code": dcode, "path": code_to_dir[dcode]}

    node_short_map = _build_node_short_map(active_entries)
    m_tokens, dag_edges, syn_edges = [], [], []
    for e in active_entries:
        nid = str(e.get("node_id") or "")
        nkey, status = str(e.get("node_key") or nid), str(e.get("status") or "draft")
        summary, npath = str(e.get("summary_1line") or "").replace('"', "'"), str(e.get("path") or "")
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
        gov_c_codes = _collect_governed_script_codes(e, script_to_code)
        if gov_c_codes:
            syn_edges.append(f"{ncode} => {','.join(gov_c_codes)}")
        node_meta = {
            "kind": "node", "code": ncode, "node_id": nid, "node_key": nkey, "status": status, "path": npath,
            "summary_1line": summary, "depends_on": e.get("depends_on") or [], "governed_scripts": gov_c_codes,
            "affected_paths": e.get("affected_paths") or [],
        }
        reverse_lookup[ncode] = reverse_lookup[nkey] = node_meta
        if nid:
            reverse_lookup[nid] = node_meta

    ast_edges: List[str] = []
    for sp in selected_scripts:
        src_code = script_to_code.get(sp)
        if not src_code:
            continue
        dst_codes: List[str] = []
        for imp in intel_map.get(sp, {}).get("imports", []):
            imp_code = script_to_code.get(str(imp))
            if imp_code and imp_code != src_code and imp_code not in dst_codes:
                dst_codes.append(imp_code)
        if dst_codes:
            ast_edges.append(f"{src_code} -> {','.join(dst_codes)}")

    d_line_tokens = [f"{dcode}={code_to_dir[dcode]}" for dcode in sorted_dir_codes]
    m_rows = ["  " + " | ".join(m_tokens[i : i + 3]) for i in range(0, len(m_tokens), 3)]
    c_rows = ["  " + " | ".join(c_tokens[i : i + 3]) for i in range(0, len(c_tokens), 3)]
    g_lines = [
        f"  [DAG] {' | '.join(dag_edges) if dag_edges else '(none)'}",
        f"  [SYN] {' | '.join(syn_edges) if syn_edges else '(none)'}",
        f"  [AST] {' | '.join(ast_edges) if ast_edges else '(none)'}",
        "  [HYG-AST] Python functions max control-flow nesting <= 4 layers (use Early-Return); NEVER write silent 'except: pass' without '# noqa: silent-except'; target file size <= 400 lines (hard cap 550).",
        "  [HYG-DEBUG] On bug/unexpected return, NEVER patch locally with nested if/try; trace backward [Return Point -> Call Chain -> Entry Input] and add Fail-Fast validation at entry.",
        "  [DELEGATE] Mandatory IF-THEN Routing: (1) Multi-file search or messy/large doc digestion (>=2 files or >300 lines, e.g. in scratch/) -> MUST call dispatch_specialist(specialist='scout', filePaths=[...]) instead of manual sliced read; (2) Code implementation/refactoring (>50 lines or multi-file) -> MUST delegate to dispatch_specialist(specialist='code') or subagent(agent='worker'); (3) NEVER use bash(cat << EOF) or /tmp to bypass write/edit AST gates.",
    ]
    compact_lines = [
        f"## 🧭 [{project_root.name} Turn-1 Frozen Codebook Map] (Nodes: {total_nodes} | Scripts: {len(selected_scripts)} | Tier: {tier})",
        f"@D (Dirs): {' '.join(d_line_tokens)}",
        "@R (Write Route): 開架知識庫(領域百科wiki/操作指南sop/詞彙表glossary/討論與備忘錄note)->W(memory/wiki/)[310-499,免雙審自動補標頭] | 抓蟲/修復藍帖->A(memory/audits/)[type:audit] | 已拍板新規格->P(memory/specs/)[type:spec] | 活躍工單->M:LEDGER.md | 臨時草稿->scratch/ (未定案嚴禁建spec；修Bug嚴禁塗改舊藍圖) | 生命週期: draft(規劃/施工中) -> verified(實測通過定稿) -> archived(討論筆記已收斂升級封存，保留 depends_on 脈絡但過濾 @M 視野) / deprecated(路線廢棄)",
        "@M (Nodes):",
        *(m_rows if m_rows else ["  (none)"]),
        "@C (Scripts):",
        *(c_rows if c_rows else ["  (none)"]),
        "@G (Topology Graph — DAG / Governance Synapses / Code AST Imports):",
        *g_lines,
        '💡 [Lookup Rule]: `<` 表示 depends_on，`=>` 表示記憶管轄腳本，`->` 表示程式碼 AST 引用；可直接用 `@D`+`@M`/`@C` 還原路徑，或呼叫 `query_library(query="200"|"C1")` 查閱完整中文摘要與符號。',
    ]
    compact_text = "\n".join(compact_lines)
    raw_uncompressed_est = sum(
        len(str(e.get("path", ""))) * 3 + len(str(e.get("summary_1line", ""))) + len(json.dumps(e, ensure_ascii=False))
        for e in active_entries
    ) + sum(len(sp) * 4 + len(json.dumps(intel_map.get(sp, {}), ensure_ascii=False)) for sp in selected_scripts)
    compact_len = len(compact_text)
    saved_pct = round((1.0 - (compact_len / max(raw_uncompressed_est, compact_len + 1))) * 100.0, 1)
    return {
        "tier": tier, "total_nodes": total_nodes, "total_scripts": len(selected_scripts),
        "raw_char_estimate": raw_uncompressed_est, "compact_char_count": compact_len, "compression_ratio_pct": saved_pct,
        "dirs": {dcode: code_to_dir[dcode] for dcode in sorted_dir_codes}, "scripts": {script_to_code[sp]: sp for sp in selected_scripts},
        "compact_text": compact_text, "reverse_lookup": reverse_lookup,
    }


build_codebook_map = compile_codebook_map


def render_context_map(project_root: Path, index: Dict[str, Any]) -> str:
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
        lines.extend(["## 0. Turn-1 凍結代號壓縮地圖 (`@D/@C/@G` Codebook Map)", "", "```text", codebook_text, "```", ""])

    lines.extend(["## 1. 領域分層註冊表 (Domain Layer Registry)", ""])
    historical_items: List[Dict[str, Any]] = []
    tbl_hdr = (
        "| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |\n"
        "| :--- | :--- | :---: | :---: | :---: | :--- | :--- |"
    )
    for _, layer in index["domain_registry"].items():
        items = layer["items"]
        active_items = [it for it in items if it.get("status") not in ("archived", "deprecated")]
        historical_items.extend(it for it in items if it.get("status") in ("archived", "deprecated"))
        if not active_items:
            continue
        lines.extend([f"### 📂 `{layer['title']}` ({len(active_items)} 節點)", "", tbl_hdr])
        for item in active_items:
            lines.append(f"| `{item['node_id']}` | `{item['node_key']}` | `{item.get('artifact_track', 'official')}` | `{item['artifact_type']}` | `{item['status']}` | {item['summary_1line']} | [`{item['path']}`](../../{item['path']}) |")
        lines.append("")

    if historical_items:
        lines.extend([f"### 🗄️ 歷史封存與退役節點紀錄表 (Archived & Deprecated Historical Nodes) ({len(historical_items)} 節點)", "", tbl_hdr])
        for item in historical_items:
            lines.append(f"| `{item['node_id']}` | `{item['node_key']}` | `{item.get('artifact_track', 'official')}` | `{item['artifact_type']}` | `{item['status']}` | {item['summary_1line']} | [`{item['path']}`](../../{item['path']}) |")
        lines.append("")

    lines.extend(["## 2. 因果拓撲依賴邊 (Causal Topology DAG Edges)", "", "| 下游節點 (`from`) | 依賴關係 (`relation`) | 上游基礎節點 (`to`) |", "| :--- | :---: | :--- |"])
    for edge in index["causal_topology_edges"]:
        lines.append(f"| `{edge['from']}` | `{edge['relation']}` | `{edge['to']}` |")

    lines.extend(["", "## 3. 程式碼模組依賴圖 (Code-Level AST Dependency Graph)", "", "| 來源模組 (`from`) | 目標依賴 (`to`) | 依賴類型 (`type`) |", "| :--- | :--- | :---: |"])
    for cedge in index.get("code_dependency_edges", []):
        lines.append(f"| `{cedge['from']}` | `{cedge['to']}` | `{cedge['type']}` |")

    intel_map = index.get("code_intelligence_map", {})
    if intel_map:
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
        "- `scripts/` — 索引編譯器 (`auto_update_map.py`)、跨宿主守護程序 (`netark_guard_daemon.py`)、母版安裝器 (`netark_init.py`) 與自動化驗收套件",
        "",
    ])
    return "\n".join(lines)


render_context_map_md = render_context_map


def render_private_context_map(project_root: Path, private_index: Dict[str, Any]) -> str:
    return render_context_map(project_root, private_index).replace(
        f"# 🗺️ {project_root.name} × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)",
        f"# 🔒 {project_root.name} × NetArk Private Context Registry & Topology Map (memory/private/CONTEXT_MAP.md)",
        1,
    )


render_private_context_map_md = render_private_context_map
