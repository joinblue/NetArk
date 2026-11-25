"""Standalone Epistemic Graph & AST Scanner (`dashboard/backend/graph_scanner.py` — <= 400 lines)."""
from __future__ import annotations

import json, os, re, subprocess, sys
from pathlib import Path
from typing import Any, Dict, List

BASE_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_ROOT: Path | None = None
CAPSULE_SUBDIRS = ("specs", "src", "scripts", "tests", "configs")


def _is_discoverable_project(p: Path) -> bool:
    if not p.is_dir() or p.name.startswith("."):
        return False
    return (p / "memory" / "index" / "CONTEXT_INDEX.json").exists() or (p / "memory").is_dir() or any((p / s).is_dir() for s in CAPSULE_SUBDIRS)


def _discover_projects(base_root: Path | None = None) -> Dict[str, Dict[str, str]]:
    """Auto-discover host NetArk workspace, projects/* capsules, and NETARK_EXTRA_PROJECTS."""
    root = (base_root or _WORKSPACE_ROOT or BASE_ROOT).resolve()
    candidates: List[Path] = [root] if ((root / "memory" / "index" / "CONTEXT_INDEX.json").exists() or (root / "memory").is_dir()) else []
    projects_dir = root / "projects"
    if projects_dir.is_dir():
        candidates.extend(p for p in sorted(projects_dir.iterdir()) if _is_discoverable_project(p))
    for env_var in ("NETARK_EXTRA_PROJECTS", "PRISM_EXTRA_PROJECTS"):
        extra = os.environ.get(env_var, "").strip()
        if extra:
            candidates.extend(Path(p.strip()).resolve() for p in extra.split(os.pathsep) if p.strip())
    projects: Dict[str, Dict[str, str]] = {}
    for p in candidates:
        if _is_discoverable_project(p) and p.name not in projects:
            detected = next((d for d in (".netark", ".agents", ".claude", ".pi", ".Tiandao") if (p / d).exists()), None)
            h_dir = detected or (".agents" if p.parent == projects_dir else ".Friday")
            label = "NetArk Clean-Room V1" if p.name == "NetArk" else (detected or ("NetArk Workspace" if p == root else ("Project Capsule" if p.parent == projects_dir else h_dir)))
            projects[p.name] = {"id": p.name, "name": f"{p.name} ({label})", "root": str(p.resolve()), "harness_dir": h_dir}
    return projects


REGISTERED_PROJECTS: Dict[str, Dict[str, str]] = _discover_projects()


def set_workspace_root(cwd: str | Path) -> Dict[str, Dict[str, str]]:
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = Path(cwd).resolve()
    return _get_projects()


def _get_projects() -> Dict[str, Dict[str, str]]:
    if _WORKSPACE_ROOT is not None or not REGISTERED_PROJECTS:
        REGISTERED_PROJECTS.clear()
        REGISTERED_PROJECTS.update(_discover_projects(_WORKSPACE_ROOT))
    return REGISTERED_PROJECTS


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}


def _split_frontmatter(md_text: str) -> tuple[str, str]:
    if md_text.startswith("---\n") and (end_idx := md_text.find("\n---\n", 4)) != -1:
        return md_text[4:end_idx], md_text[end_idx + 5 :].strip()
    return "", md_text.strip()


def _safe_str_list(val: Any) -> List[str]:
    """Normalize None, string, or mixed lists into a clean list of non-empty strings."""
    if isinstance(val, str): return [val.strip()] if val.strip() else []
    return [str(x).strip() for x in val if isinstance(x, (str, int, float)) and str(x).strip()] if isinstance(val, list) else []


def _extract_topic(n: Dict[str, Any]) -> str:
    """Resolve topic from explicit node field or 2nd colon-segment of facet_tags[0]."""
    if isinstance(rt := n.get("topic"), str) and rt.strip(): return rt.strip()
    for tag in _safe_str_list(n.get("facet_tags")):
        if len(parts := [p.strip() for p in tag.split(":")]) >= 2 and parts[1]: return parts[1]
    return ""


def _parse_ledger_table(ledger_path: Path) -> List[Dict[str, Any]]:
    if not ledger_path.exists():
        return []
    items: List[Dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "工單編號" in s or "工單 ID" in s:
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) < 4:
            continue
        # 支援 4 欄 (WO | Title | Spec | Status) 與 5 欄 (WO | Title | Status | Role | Oracle) 格式
        wo_id = re.sub(r"[*`]+", "", cols[0]).strip()
        raw_title = cols[1]
        if len(cols) >= 5:
            status_raw = re.sub(r"`+", "", cols[2]).strip()
            role, oracle = cols[3], cols[4]
        else:
            status_raw = re.sub(r"`+", "", cols[3]).strip()
            role, oracle = "", re.sub(r"`+", "", cols[2]).strip()
        sep = "｜" if "｜" in raw_title else ("：" if "：" in raw_title else None)
        p1, p2 = raw_title.split(sep, 1) if sep else (raw_title, "")
        items.append({
            "wo_id": wo_id, "title": raw_title, "title_main": re.sub(r"\*+", "", p1).strip(),
            "title_sub": p2.strip(), "status": status_raw, "role": role, "oracle": oracle,
            "is_done": "✅" in status_raw or "已完成" in status_raw,
        })
    return items


def _parse_fm_scalar(fm_raw: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", fm_raw, re.MULTILINE)
    if not m: return ""
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"): return val[1:-1]
    return "" if val in ("null", "~", "[]", "{}") else val


def _parse_sections_from_body(body: str) -> Dict[str, str]:
    sections, current_title, buf = {}, "Overview", []
    for line in body.splitlines():
        if line.startswith("## "):
            if buf: sections[current_title] = "\n".join(buf).strip()
            current_title, buf = line[3:].strip(), []
        else: buf.append(line)
    if buf: sections[current_title] = "\n".join(buf).strip()
    return sections


def _parse_handover_sections(handover_path: Path) -> Dict[str, Any]:
    if not handover_path.exists(): return {"exists": False, "sections": {}, "raw_markdown": ""}
    _, body = _split_frontmatter(handover_path.read_text(encoding="utf-8", errors="ignore"))
    return {"exists": True, "sections": _parse_sections_from_body(body), "raw_markdown": body}


def _scan_handovers(episodic_dir: Path) -> List[Dict[str, Any]]:
    if not episodic_dir.is_dir(): return []
    files = sorted(episodic_dir.glob("HANDOVER*.md"), key=lambda p: (0 if p.name == "HANDOVER.md" else 1, p.name))
    items: List[Dict[str, Any]] = []
    for fpath in files:
        if not fpath.is_file(): continue
        fm_raw, body = _split_frontmatter(fpath.read_text(encoding="utf-8", errors="ignore"))
        default_track = "main" if fpath.name == "HANDOVER.md" else (fpath.stem[len("HANDOVER_"):] or fpath.stem)
        raw_st, trk_st = _parse_fm_scalar(fm_raw, "status"), _parse_fm_scalar(fm_raw, "track_status")
        status = raw_st if raw_st in ("archived", "deprecated") else (trk_st or raw_st or "active")
        summary = _parse_fm_scalar(fm_raw, "summary_1line") or _parse_fm_scalar(fm_raw, "summary")
        if not summary and body:
            summary = next((ln.strip().lstrip("#- ") for ln in body.splitlines() if ln.strip()), "")[:120]
        items.append({
            "filename": fpath.name, "track_id": _parse_fm_scalar(fm_raw, "track_id") or default_track,
            "status": status, "updated_at": _parse_fm_scalar(fm_raw, "updated_at"), "summary": summary,
            "content": body, "sections": _parse_sections_from_body(body) if body else {},
        })
    return items


def _compute_file_line_health(project_root: Path, rel_path: str) -> Dict[str, Any]:
    target = (project_root / rel_path).resolve()
    exists = target.exists() and target.is_file()
    lc = len(target.read_text(encoding="utf-8", errors="ignore").splitlines()) if exists else 0
    if lc > 600: tier, label = "god_script", f"🔴 上帝腳本凍結 ({lc} 行 > 600)"
    elif lc > 400: tier, label = "warning", f"🟡 建議拆片 ({lc} 行 > 400)"
    elif exists: tier, label = "healthy", f"🟢 健康 ({lc} 行)"
    else: tier, label = "stub", "⚪ 待建立骨架"
    return {"exists": exists, "line_count": lc, "health_tier": tier, "health_label": label}


def _derive_title_and_layer(n: Dict[str, Any]) -> tuple[str, int]:
    fpath = str(n.get("file_path") or "")
    fname = Path(fpath).stem if fpath else str(n.get("node_key") or n.get("node_id"))
    num_m = re.match(r"^(\d{3})", fname)
    num_prefix = f"{num_m.group(1)} " if num_m else ""
    summary = str(n.get("summary_1line") or "")
    clean_zh = re.split(r"[：:（(，,。；;]", re.sub(r"^[A-Za-z0-9_.\s/-]+[:：]\s*", "", summary))[0].strip()
    if not clean_zh or len(clean_zh) < 3:
        clean_zh = summary[:18].strip() or fname
    title_zh = f"{num_prefix}{clean_zh[:18] + ('…' if len(clean_zh) > 18 else '')}".strip()
    dom, atype = str(n.get("domain_code") or "000"), str(n.get("artifact_type") or "")
    has_pb = bool(str(n.get("parent_blueprint") or "").strip())
    if dom in ("000", "100"): layer = 1
    elif atype in ("blueprint", "spec", "adr") or has_pb or dom in ("200", "300", "400", "500"): layer = 2
    else: layer = 3
    return title_zh, layer


def _extract_index_items(idx_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(idx_obj.get("nodes"), list):
        raw = [n for n in idx_obj["nodes"] if isinstance(n, dict)]
    else:
        raw = [n for d in (idx_obj.get("domain_registry") or {}).values() if isinstance(d, dict) for n in (d.get("items") or []) if isinstance(n, dict)]
    return [{**n, "topic": _extract_topic(n)} for n in raw]


def _resolve_repo_script_path(root: Path, token: str) -> str | None:
    clean = token.strip("`'\"()[] ")
    if not clean or not clean.endswith((".py", ".ts", ".js", ".sh")): return None
    for candidate in (root / clean, root / "scripts" / clean, root / "schemas" / clean):
        if candidate.exists() and candidate.is_file(): return str(candidate.relative_to(root))
    return None


def list_registered_projects() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for pid, meta in _get_projects().items():
        root = Path(meta["root"])
        pub_idx, priv_idx = _read_json(root / "memory/index/CONTEXT_INDEX.json"), _read_json(root / "memory/index/PRIVATE_INDEX.json")
        result.append({
            "id": pid, "name": meta["name"], "root": str(root), "harness_dir": meta["harness_dir"], "exists": root.exists(),
            "public_node_count": len(_extract_index_items(pub_idx)), "private_node_count": len(_extract_index_items(priv_idx)),
        })
    return result


def _node_matches_topic(n: Dict[str, Any], t_low: str) -> bool:
    if str(n.get("topic") or "").strip().lower() == t_low: return True
    return any(len(p := [x.strip() for x in tag.split(":")]) >= 2 and p[1].lower() == t_low for tag in _safe_str_list(n.get("facet_tags")))


def _filter_memory_nodes(
    mem_nodes: List[Dict[str, Any]], category: str, blueprint: str, topic: str
) -> tuple[List[Dict[str, Any]], set[str] | None]:
    filtered = mem_nodes
    if category == "official": filtered = [n for n in filtered if n.get("artifact_track") == "official"]
    elif category == "wiki": filtered = [n for n in filtered if n.get("artifact_track") == "wiki" or str(n.get("domain_code") or "") == "310"]
    elif category == "blueprint_tree": filtered = [n for n in filtered if n.get("artifact_type") == "blueprint" or bool(n.get("shard_modules")) or bool(n.get("parent_blueprint"))]
    if topic:
        t_low = topic.lower()
        filtered = [n for n in filtered if _node_matches_topic(n, t_low)]
    if not blueprint: return filtered, None
    bp_node = next((n for n in filtered if blueprint in (n.get("node_key"), n.get("node_id"))), None)
    if not bp_node: return [], set()
    bp_key, bp_id = str(bp_node.get("node_key") or bp_node.get("node_id") or ""), str(bp_node.get("node_id") or "")
    core_keys: set[str] = {bp_key, bp_id} | set(_safe_str_list(bp_node.get("shard_modules")))
    for n in filtered:
        if n.get("parent_blueprint") in (bp_key, bp_id): core_keys.add(str(n.get("node_key") or n.get("node_id") or ""))
    allowed_keys = core_keys | set(_safe_str_list(bp_node.get("depends_on")))
    kept = [n for n in filtered if n.get("node_key") in allowed_keys or n.get("node_id") in allowed_keys]
    return kept, {k for k in core_keys if k}


def _build_graph_edges(
    root: Path, raw_nodes: List[Dict[str, Any]], pub_idx: Dict[str, Any], intel_map: Dict[str, Any],
    ledger_items: List[Dict[str, Any]], code_owner_keys: set[str] | None = None, include_intel: bool = True,
) -> tuple[List[Dict[str, str]], set[str]]:
    edges: List[Dict[str, str]] = []
    code_paths_referenced: set[str] = set(intel_map.keys()) if include_intel else set()
    id_to_key = {n.get("node_id"): (n.get("node_key") or n.get("node_id")) for n in raw_nodes}
    for n in raw_nodes:
        src = str(n.get("node_key") or n.get("node_id") or "")
        for dep in _safe_str_list(n.get("depends_on")): edges.append({"source": src, "target": id_to_key.get(dep, dep), "kind": "depends_on"})
        for out_link in _safe_str_list(n.get("outbound_links")): edges.append({"source": src, "target": id_to_key.get(out_link, out_link), "kind": "wikilink"})
        for shard in _safe_str_list(n.get("shard_modules")): edges.append({"source": src, "target": shard, "kind": "shard_module"})
        if n.get("parent_blueprint"): edges.append({"source": str(n["parent_blueprint"]), "target": src, "kind": "shard_module"})
        if code_owner_keys is None or src in code_owner_keys or n.get("node_id") in code_owner_keys:
            for ap in _safe_str_list(n.get("affected_paths")): code_paths_referenced.add(ap); edges.append({"source": src, "target": f"code:{ap}", "kind": "affects_code"})
            for sp in _safe_str_list(n.get("stub_paths")): code_paths_referenced.add(sp); edges.append({"source": src, "target": f"code:{sp}", "kind": "stub_path"})
    if include_intel:
        for item in ledger_items:
            for tok in re.findall(r"[A-Za-z0-9_./-]+\.(?:py|ts|js|sh)", f"{item['title']} {item['oracle']}"):
                if (resolved := _resolve_repo_script_path(root, tok)): code_paths_referenced.add(resolved)
    for cedge in pub_idx.get("code_dependency_edges", []):
        c_src, c_dst = cedge.get("from", ""), cedge.get("to", "")
        if c_src in code_paths_referenced and c_dst in code_paths_referenced:
            edges.append({"source": f"code:{c_src}", "target": f"code:{c_dst}", "kind": "code_import"})
    return edges, code_paths_referenced


def _build_code_health_and_aliases(
    root: Path, raw_nodes: List[Dict[str, Any]], code_paths_referenced: set[str], intel_map: Dict[str, Any], pub_idx: Dict[str, Any]
) -> tuple[List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    code_health_list: List[Dict[str, Any]] = []
    for cpath in sorted(code_paths_referenced):
        if cpath.endswith(".md"): continue
        health, intel = _compute_file_line_health(root, cpath), intel_map.get(cpath, {})
        symbols = intel.get("symbols", [])
        code_entry = {
            "node_id": f"code:{cpath}", "node_key": f"code:{cpath}", "label": Path(cpath).name, "title_zh": f"📄 {Path(cpath).name}",
            "layer_rank": 4, "file_path": cpath, "node_kind": "code", "status": health["health_tier"], "health_label": health["health_label"],
            "line_count": health["line_count"], "symbol_count": len(symbols), "symbols": symbols,
            "governing_specs": intel.get("governing_specs", []), "pi_registrations": intel.get("pi_registrations", []),
            "summary_1line": f"程式碼模組 `{cpath}`（共 {health['line_count']} 行，{len(symbols)} 個 AST 符號）",
        }
        code_health_list.append(code_entry); raw_nodes.append(code_entry)
    alias_map: Dict[str, Dict[str, str]] = {}
    for n in raw_nodes:
        key = n.get("node_key") or n.get("node_id")
        if not key: continue
        entry = {"key": key, "label": n.get("title_zh") or key, "kind": n.get("node_kind", "memory"), "status": n.get("status", "draft"), "file_path": n.get("file_path", "")}
        alias_map[key] = entry
        if n.get("node_id"): alias_map[n["node_id"]] = entry
        if (fp := str(n.get("file_path") or "")):
            alias_map[fp] = alias_map[Path(fp).name] = entry
            if n.get("node_kind") == "memory":
                if (m_num := re.match(r"^(\d{3})_", Path(fp).name)) and m_num.group(1) not in alias_map: alias_map[m_num.group(1)] = entry
                if (dom_c := str(n.get("domain_code") or "")) and dom_c not in alias_map: alias_map[dom_c] = entry
    for scode, spath in (pub_idx.get("codebook_map", {}).get("scripts") or {}).items():
        if spath in alias_map: alias_map[scode] = alias_map[spath]
    return code_health_list, alias_map


def build_project_graph_payload(
    project_id: str, include_archived: bool = False, category: str = "all", blueprint: str = "", topic: str = ""
) -> Dict[str, Any]:
    projects = _get_projects()
    if project_id not in projects:
        raise ValueError(f"Unknown project_id: {project_id}")
    meta, root = projects[project_id], Path(projects[project_id]["root"])
    pub_idx, priv_idx = _read_json(root / "memory/index/CONTEXT_INDEX.json"), _read_json(root / "memory/index/PRIVATE_INDEX.json")
    taxonomy, intel_map = _read_json(root / "memory/index/TAXONOMY.json"), pub_idx.get("code_intelligence_map", {})
    cat, bp_q, topic_q = (category or "all").strip().lower() or "all", (blueprint or "").strip(), (topic or "").strip()

    all_mem, seen_keys = [], set()
    for visibility, idx_obj in (("public", pub_idx), ("private", priv_idx)):
        for n in _extract_index_items(idx_obj):
            key = n.get("node_key") or n.get("node_id")
            if not key or key in seen_keys: continue
            seen_keys.add(key)
            pb_raw = n.get("parent_blueprint")
            nc = {
                **n, "file_path": n.get("path") or n.get("file_path") or "", "visibility": visibility, "node_kind": "memory",
                "facet_tags": _safe_str_list(n.get("facet_tags")), "depends_on": _safe_str_list(n.get("depends_on")),
                "outbound_links": _safe_str_list(n.get("outbound_links")), "backlinks": _safe_str_list(n.get("backlinks")),
                "shard_modules": _safe_str_list(n.get("shard_modules")), "affected_paths": _safe_str_list(n.get("affected_paths")),
                "stub_paths": _safe_str_list(n.get("stub_paths")),
                "parent_blueprint": pb_raw.strip() if isinstance(pb_raw, str) and pb_raw.strip() else None,
            }
            nc["title_zh"], nc["layer_rank"] = _derive_title_and_layer(nc)
            all_mem.append(nc)

    archived_count = sum(1 for n in all_mem if n.get("status") in ("archived", "deprecated"))
    active_mem = all_mem if include_archived else [n for n in all_mem if n.get("status") not in ("archived", "deprecated")]
    available_topics = sorted({str(n.get("topic") or "") for n in active_mem if str(n.get("topic") or "").strip()})
    available_blueprints = sorted(
        [{"node_key": n.get("node_key") or n.get("node_id"), "title_zh": n.get("title_zh") or n.get("node_key"),
          "status": n.get("status", "draft"), "shard_count": len(n.get("shard_modules") or [])}
         for n in active_mem if n.get("artifact_type") == "blueprint" or bool(n.get("shard_modules"))],
        key=lambda x: str(x["node_key"]),
    )

    raw_nodes, code_owner_keys = _filter_memory_nodes(active_mem, cat, bp_q, topic_q)
    ledger_items = _parse_ledger_table(root / "memory/LEDGER.md")
    handover_data, handovers_list = _parse_handover_sections(root / "memory/episodic/HANDOVER.md"), _scan_handovers(root / "memory/episodic")
    edges, code_paths_referenced = _build_graph_edges(root, raw_nodes, pub_idx, intel_map, ledger_items, code_owner_keys, cat == "all" and not bp_q and not topic_q)
    code_health_list, alias_map = _build_code_health_and_aliases(root, raw_nodes, code_paths_referenced, intel_map, pub_idx)
    valid_ids = {n.get("node_key") for n in raw_nodes if n.get("node_key")} | {n.get("node_id") for n in raw_nodes if n.get("node_id")}
    edges = [e for e in edges if e["source"] in valid_ids and e["target"] in valid_ids]
    mem_nodes = [n for n in raw_nodes if n.get("node_kind") == "memory"]
    stats = {
        "total_memory_nodes": len(mem_nodes), "archived_count": archived_count,
        "verified_count": sum(1 for n in mem_nodes if n.get("status") == "verified" and n.get("artifact_type") != "blueprint"),
        "blueprint_count": sum(1 for n in mem_nodes if n.get("artifact_type") == "blueprint" or bool(n.get("shard_modules"))),
        "reviewing_count": sum(1 for n in mem_nodes if n.get("status") == "reviewing"),
        "stub_ready_count": sum(1 for n in mem_nodes if n.get("status") == "stub_ready"),
        "draft_count": sum(1 for n in mem_nodes if n.get("status") == "draft"),
        "ledger_total": len(ledger_items), "ledger_done": sum(1 for x in ledger_items if x["is_done"]),
        "code_files_count": len(code_health_list),
        "god_script_count": sum(1 for c in code_health_list if c["status"] == "god_script"),
        "warning_script_count": sum(1 for c in code_health_list if c["status"] == "warning"),
    }
    return {
        "project": meta, "stats": stats, "nodes": raw_nodes, "edges": edges, "alias_map": alias_map,
        "available_topics": available_topics, "available_blueprints": available_blueprints,
        "ledger": ledger_items, "handover": handover_data, "handovers": handovers_list,
        "code_health": sorted(code_health_list, key=lambda x: x["line_count"], reverse=True), "taxonomy": taxonomy.get("domains", {}),
    }


def get_node_detail(project_id: str, node_id_or_key: str) -> Dict[str, Any]:
    payload = build_project_graph_payload(project_id, include_archived=True)
    root = Path(_get_projects()[project_id]["root"])
    resolved_key = payload.get("alias_map", {}).get(node_id_or_key, {}).get("key", node_id_or_key)
    target_node = next((n for n in payload["nodes"] if resolved_key in (n.get("node_key"), n.get("node_id"), n.get("file_path"))), None)
    if not target_node: raise KeyError(f"Node not found: {node_id_or_key}")
    if target_node.get("node_kind") == "code":
        cpath = target_node["file_path"]
        abs_file = (root / cpath).resolve()
        lines = abs_file.read_text(encoding="utf-8", errors="ignore").splitlines() if abs_file.is_file() else []
        src_preview = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines[:140]))
        return {**target_node, "body_markdown": f"### 📄 源碼預覽 (`{cpath}` 前 140 行)\n```python\n{src_preview}\n```", "code_bindings": [target_node]}
    md_path = (root / target_node.get("file_path", "")).resolve()
    fm_raw, body_md = _split_frontmatter(md_path.read_text(encoding="utf-8", errors="ignore")) if md_path.exists() else ("", "")
    code_map = {c["file_path"]: c for c in payload["code_health"]}
    bound_paths = list(dict.fromkeys(target_node.get("affected_paths", []) + target_node.get("stub_paths", [])))
    code_bindings = [code_map.get(p, {**_compute_file_line_health(root, p), "file_path": p, "symbols": []}) for p in bound_paths]
    return {**target_node, "frontmatter_raw": fm_raw, "body_markdown": body_md, "code_bindings": code_bindings}


def trigger_project_rescan(project_id: str) -> Dict[str, Any]:
    if project_id not in (projects := _get_projects()): raise ValueError(f"Unknown project_id: {project_id}")
    root = Path(projects[project_id]["root"])
    if (script := root / "scripts/auto_update_map.py").exists():
        subprocess.run([sys.executable, str(script)], cwd=str(root), timeout=30, check=False)
    elif (root / "memory").is_dir():
        if str(BASE_ROOT) not in sys.path and (BASE_ROOT / "schemas").is_dir(): sys.path.insert(0, str(BASE_ROOT))
        from schemas.mcp_tools_core import compile_and_write_indices
        compile_and_write_indices(root)
    return build_project_graph_payload(project_id)
