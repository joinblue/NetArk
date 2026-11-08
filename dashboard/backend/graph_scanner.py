"""Standalone Epistemic Graph & AST Scanner (`dashboard/backend/graph_scanner.py` — < 380 lines)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_ROOT = Path(__file__).resolve().parent.parent.parent


def _discover_projects() -> Dict[str, Dict[str, str]]:
    """Auto-discover host NetArk workspace and any extra projects configured via NETARK_EXTRA_PROJECTS."""
    candidates: List[Path] = []
    if (BASE_ROOT / "memory" / "index" / "CONTEXT_INDEX.json").exists():
        candidates.append(BASE_ROOT)
    for env_var in ("NETARK_EXTRA_PROJECTS", "PRISM_EXTRA_PROJECTS"):
        extra_env = os.environ.get(env_var, "").strip()
        if extra_env:
            candidates.extend(Path(p.strip()).resolve() for p in extra_env.split(os.pathsep) if p.strip())

    projects: Dict[str, Dict[str, str]] = {}
    for p in candidates:
        if p.exists() and (p / "memory" / "index" / "CONTEXT_INDEX.json").exists():
            h_dir = ".netark" if (p / ".netark").exists() else (".Tiandao" if (p / ".Tiandao").exists() else ".Friday")
            label = "NetArk Clean-Room V1" if p.name == "NetArk" else h_dir
            projects[p.name] = {"id": p.name, "name": f"{p.name} ({label})", "root": str(p.resolve()), "harness_dir": h_dir}
    return projects


REGISTERED_PROJECTS: Dict[str, Dict[str, str]] = _discover_projects()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _split_frontmatter(md_text: str) -> tuple[str, str]:
    if md_text.startswith("---\n"):
        end_idx = md_text.find("\n---\n", 4)
        if end_idx != -1:
            return md_text[4:end_idx], md_text[end_idx + 5 :].strip()
    return "", md_text.strip()


def _parse_ledger_table(ledger_path: Path) -> List[Dict[str, Any]]:
    if not ledger_path.exists():
        return []
    items: List[Dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s or "工單 ID" in s:
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) >= 5:
            wo_id = re.sub(r"\*+", "", cols[0]).strip()
            raw_title = cols[1]
            sep = "｜" if "｜" in raw_title else ("：" if "：" in raw_title else None)
            if sep:
                p1, p2 = raw_title.split(sep, 1)
                title_main, title_sub = re.sub(r"\*+", "", p1).strip(), p2.strip()
            else:
                title_main, title_sub = re.sub(r"\*+", "", raw_title).strip(), ""
            status_raw = cols[2]
            items.append({
                "wo_id": wo_id,
                "title": raw_title,
                "title_main": title_main,
                "title_sub": title_sub,
                "status": status_raw,
                "role": cols[3],
                "oracle": cols[4],
                "is_done": "✅" in status_raw or "已完成" in status_raw,
            })
    return items


def _parse_handover_sections(handover_path: Path) -> Dict[str, Any]:
    if not handover_path.exists():
        return {"exists": False, "sections": {}, "raw_markdown": ""}
    _, body = _split_frontmatter(handover_path.read_text(encoding="utf-8"))
    sections: Dict[str, str] = {}
    current_title, buf = "Overview", []
    for line in body.splitlines():
        if line.startswith("## "):
            if buf:
                sections[current_title] = "\n".join(buf).strip()
            current_title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        sections[current_title] = "\n".join(buf).strip()
    return {"exists": True, "sections": sections, "raw_markdown": body}


def _compute_file_line_health(project_root: Path, rel_path: str) -> Dict[str, Any]:
    target = (project_root / rel_path).resolve()
    exists = target.exists() and target.is_file()
    line_count = len(target.read_text(encoding="utf-8", errors="ignore").splitlines()) if exists else 0
    if line_count > 600:
        tier, label = "god_script", f"🔴 上帝腳本凍結 ({line_count} 行 > 600)"
    elif line_count > 400:
        tier, label = "warning", f"🟡 建議拆片 ({line_count} 行 > 400)"
    elif exists:
        tier, label = "healthy", f"🟢 健康 ({line_count} 行)"
    else:
        tier, label = "stub", "⚪ 待建立骨架"
    return {"exists": exists, "line_count": line_count, "health_tier": tier, "health_label": label}


def _derive_title_and_layer(n: Dict[str, Any]) -> tuple[str, int]:
    fpath = str(n.get("file_path") or "")
    fname = Path(fpath).stem if fpath else str(n.get("node_key") or n.get("node_id"))
    num_match = re.match(r"^(\d{3})", fname)
    num_prefix = f"{num_match.group(1)} " if num_match else ""
    summary = str(n.get("summary_1line") or "")
    clean_zh = re.split(r"[：:（(，,。；;]", re.sub(r"^[A-Za-z0-9_.\s/-]+[:：]\s*", "", summary))[0].strip()
    if not clean_zh or len(clean_zh) < 3:
        clean_zh = summary[:18].strip() or fname
    title_zh = f"{num_prefix}{clean_zh[:18] + ('…' if len(clean_zh) > 18 else '')}".strip()

    dom = str(n.get("domain_code") or "000")
    if dom in ("000", "100"):
        layer = 1
    elif n.get("parent_blueprint") or n.get("artifact_track") == "wiki" or dom in ("310", "320", "900"):
        layer = 3 if not n.get("shard_modules") else 2
    else:
        layer = 2
    return title_zh, layer


def _extract_index_items(idx_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(idx_obj.get("nodes"), list):
        return idx_obj["nodes"]
    items: List[Dict[str, Any]] = []
    for dom_data in (idx_obj.get("domain_registry") or {}).values():
        if isinstance(dom_data, dict) and isinstance(dom_data.get("items"), list):
            items.extend(dom_data["items"])
    return items


def _resolve_repo_script_path(root: Path, token: str) -> str | None:
    clean = token.strip("`'\"()[] ")
    if not clean or not clean.endswith((".py", ".ts", ".js", ".sh")):
        return None
    for candidate in (root / clean, root / "scripts" / clean, root / "schemas" / clean):
        if candidate.exists() and candidate.is_file():
            return str(candidate.relative_to(root))
    return None


def list_registered_projects() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for pid, meta in REGISTERED_PROJECTS.items():
        root = Path(meta["root"])
        pub_idx = _read_json(root / "memory" / "index" / "CONTEXT_INDEX.json")
        priv_idx = _read_json(root / "memory" / "index" / "PRIVATE_INDEX.json")
        result.append({
            "id": pid,
            "name": meta["name"],
            "root": str(root),
            "harness_dir": meta["harness_dir"],
            "exists": root.exists(),
            "public_node_count": len(_extract_index_items(pub_idx)),
            "private_node_count": len(_extract_index_items(priv_idx)),
        })
    return result


def build_project_graph_payload(project_id: str) -> Dict[str, Any]:
    if project_id not in REGISTERED_PROJECTS:
        raise ValueError(f"Unknown project_id: {project_id}")
    meta = REGISTERED_PROJECTS[project_id]
    root = Path(meta["root"])
    pub_idx = _read_json(root / "memory" / "index" / "CONTEXT_INDEX.json")
    priv_idx = _read_json(root / "memory" / "index" / "PRIVATE_INDEX.json")
    taxonomy = _read_json(root / "memory" / "index" / "TAXONOMY.json")
    intel_map: Dict[str, Any] = pub_idx.get("code_intelligence_map", {})

    raw_nodes: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for visibility, idx_obj in (("public", pub_idx), ("private", priv_idx)):
        for n in _extract_index_items(idx_obj):
            key = n.get("node_key") or n.get("node_id")
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            node_copy = {
                **n,
                "file_path": n.get("path") or n.get("file_path") or "",
                "visibility": visibility,
                "node_kind": "memory",
                "shard_modules": n.get("shard_modules") or [],
                "parent_blueprint": n.get("parent_blueprint"),
                "stub_paths": n.get("stub_paths") or [],
            }
            node_copy["title_zh"], node_copy["layer_rank"] = _derive_title_and_layer(node_copy)
            raw_nodes.append(node_copy)

    edges: List[Dict[str, str]] = []
    code_paths_referenced: set[str] = set(intel_map.keys())
    id_to_key = {n.get("node_id"): (n.get("node_key") or n.get("node_id")) for n in raw_nodes}

    for n in raw_nodes:
        src = n.get("node_key") or n.get("node_id")
        for dep in n.get("depends_on", []):
            edges.append({"source": src, "target": id_to_key.get(dep, dep), "kind": "depends_on"})
        for out_link in n.get("outbound_links", []):
            edges.append({"source": src, "target": id_to_key.get(out_link, out_link), "kind": "wikilink"})
        for shard in n.get("shard_modules", []):
            edges.append({"source": src, "target": shard, "kind": "shard_module"})
        if n.get("parent_blueprint"):
            edges.append({"source": n["parent_blueprint"], "target": src, "kind": "shard_module"})
        for ap in n.get("affected_paths", []):
            code_paths_referenced.add(ap)
            edges.append({"source": src, "target": f"code:{ap}", "kind": "affects_code"})
        for sp in n.get("stub_paths", []):
            code_paths_referenced.add(sp)
            edges.append({"source": src, "target": f"code:{sp}", "kind": "stub_path"})

    ledger_items = _parse_ledger_table(root / "memory" / "LEDGER.md")
    handover_data = _parse_handover_sections(root / "memory" / "episodic" / "HANDOVER.md")

    for item in ledger_items:
        for tok in re.findall(r"[A-Za-z0-9_./-]+\.(?:py|ts|js|sh)", f"{item['title']} {item['oracle']}"):
            resolved = _resolve_repo_script_path(root, tok)
            if resolved:
                code_paths_referenced.add(resolved)

    for cedge in pub_idx.get("code_dependency_edges", []):
        c_src, c_dst = cedge.get("from", ""), cedge.get("to", "")
        if c_src in code_paths_referenced and c_dst in code_paths_referenced:
            edges.append({"source": f"code:{c_src}", "target": f"code:{c_dst}", "kind": "code_import"})

    code_health_list: List[Dict[str, Any]] = []
    for cpath in sorted(code_paths_referenced):
        if cpath.endswith(".md"):
            continue
        health = _compute_file_line_health(root, cpath)
        intel = intel_map.get(cpath, {})
        symbols = intel.get("symbols", [])
        code_entry = {
            "node_id": f"code:{cpath}",
            "node_key": f"code:{cpath}",
            "label": Path(cpath).name,
            "title_zh": f"📄 {Path(cpath).name}",
            "layer_rank": 4,
            "file_path": cpath,
            "node_kind": "code",
            "status": health["health_tier"],
            "health_label": health["health_label"],
            "line_count": health["line_count"],
            "symbol_count": len(symbols),
            "symbols": symbols,
            "governing_specs": intel.get("governing_specs", []),
            "pi_registrations": intel.get("pi_registrations", []),
            "summary_1line": f"程式碼模組 `{cpath}`（共 {health['line_count']} 行，{len(symbols)} 個 AST 符號）",
        }
        code_health_list.append(code_entry)
        raw_nodes.append(code_entry)

    alias_map: Dict[str, Dict[str, str]] = {}
    for n in raw_nodes:
        key = n.get("node_key") or n.get("node_id")
        if not key:
            continue
        entry = {
            "key": key,
            "label": n.get("title_zh") or key,
            "kind": n.get("node_kind", "memory"),
            "status": n.get("status", "draft"),
            "file_path": n.get("file_path", ""),
        }
        alias_map[key] = entry
        if n.get("node_id"):
            alias_map[n["node_id"]] = entry
        fp = str(n.get("file_path") or "")
        if fp:
            alias_map[fp] = entry
            alias_map[Path(fp).name] = entry
            if n.get("node_kind") == "memory":
                m_num = re.match(r"^(\d{3})_", Path(fp).name)
                if m_num and m_num.group(1) not in alias_map:
                    alias_map[m_num.group(1)] = entry
                dom_c = str(n.get("domain_code") or "")
                if dom_c and dom_c not in alias_map:
                    alias_map[dom_c] = entry

    for scode, spath in (pub_idx.get("codebook_map", {}).get("scripts") or {}).items():
        if spath in alias_map:
            alias_map[scode] = alias_map[spath]

    mem_nodes = [n for n in raw_nodes if n.get("node_kind") == "memory"]
    stats = {
        "total_memory_nodes": len(mem_nodes),
        "verified_count": sum(1 for n in mem_nodes if n.get("status") == "verified" and n.get("artifact_type") != "blueprint"),
        "blueprint_count": sum(1 for n in mem_nodes if n.get("artifact_type") == "blueprint" or bool(n.get("shard_modules"))),
        "stub_ready_count": sum(1 for n in mem_nodes if n.get("status") == "stub_ready"),
        "draft_count": sum(1 for n in mem_nodes if n.get("status") == "draft"),
        "ledger_total": len(ledger_items),
        "ledger_done": sum(1 for x in ledger_items if x["is_done"]),
        "code_files_count": len(code_health_list),
        "god_script_count": sum(1 for c in code_health_list if c["status"] == "god_script"),
        "warning_script_count": sum(1 for c in code_health_list if c["status"] == "warning"),
    }

    return {
        "project": meta,
        "stats": stats,
        "nodes": raw_nodes,
        "edges": edges,
        "alias_map": alias_map,
        "ledger": ledger_items,
        "handover": handover_data,
        "code_health": sorted(code_health_list, key=lambda x: x["line_count"], reverse=True),
        "taxonomy": taxonomy.get("domains", {}),
    }


def get_node_detail(project_id: str, node_id_or_key: str) -> Dict[str, Any]:
    payload = build_project_graph_payload(project_id)
    root = Path(REGISTERED_PROJECTS[project_id]["root"])
    resolved_key = payload.get("alias_map", {}).get(node_id_or_key, {}).get("key", node_id_or_key)
    target_node = next((n for n in payload["nodes"] if resolved_key in (n.get("node_key"), n.get("node_id"), n.get("file_path"))), None)
    if not target_node:
        raise KeyError(f"Node not found: {node_id_or_key}")

    if target_node.get("node_kind") == "code":
        cpath = target_node["file_path"]
        abs_file = (root / cpath).resolve()
        lines = abs_file.read_text(encoding="utf-8", errors="ignore").splitlines() if abs_file.is_file() else []
        src_preview = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines[:140]))
        return {
            **target_node,
            "body_markdown": f"### 📄 源碼預覽 (`{cpath}` 前 140 行)\n```python\n{src_preview}\n```",
            "code_bindings": [target_node],
        }

    md_path = (root / target_node.get("file_path", "")).resolve()
    fm_raw, body_md = _split_frontmatter(md_path.read_text(encoding="utf-8", errors="ignore")) if md_path.exists() else ("", "")
    code_map = {c["file_path"]: c for c in payload["code_health"]}
    bound_paths = list(dict.fromkeys(target_node.get("affected_paths", []) + target_node.get("stub_paths", [])))
    code_bindings = [code_map.get(p, {**_compute_file_line_health(root, p), "file_path": p, "symbols": []}) for p in bound_paths]
    return {**target_node, "frontmatter_raw": fm_raw, "body_markdown": body_md, "code_bindings": code_bindings}


def trigger_project_rescan(project_id: str) -> Dict[str, Any]:
    if project_id not in REGISTERED_PROJECTS:
        raise ValueError(f"Unknown project_id: {project_id}")
    root = Path(REGISTERED_PROJECTS[project_id]["root"])
    script = root / "scripts" / "auto_update_map.py"
    if script.exists():
        subprocess.run([sys.executable, str(script)], cwd=str(root), timeout=30, check=False)
    return build_project_graph_payload(project_id)
