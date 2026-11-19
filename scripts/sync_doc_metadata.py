#!/usr/bin/env python3
"""NetArk Deterministic Hook `.md` Metadata & Topology Auto-Sync (sync_doc_metadata.py)."""

from __future__ import annotations

import argparse, datetime, hashlib, json, os, re, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DEFAULT = SCRIPT_DIR.parent
for _p in (PROJECT_ROOT_DEFAULT, PROJECT_ROOT_DEFAULT / "schemas"):
    if str(_p) not in sys.path: sys.path.insert(0, str(_p))

import schema_validator as sv  # type: ignore  # noqa: E402
from schemas.doc_initializer import allocate_next_node_id, auto_initialize_wiki_node, init_governed_markdown, init_memory_node  # type: ignore  # noqa: E402,F401

ROLE_MODELS_MARKER_RE = re.compile(r"<!-- AUTO-ROLE-MODELS:START -->.*?<!-- AUTO-ROLE-MODELS:END -->", re.DOTALL)
ETERNAL_CORE_REFS = frozenset({
    "000.SOUL.v1", "MEM-2026-0001", "100.ARCH-RULES.v1", "MEM-2026-0002", "200.ADR-001.v1", "MEM-2026-0003",
    "300.LEDGER.v1", "MEM-2026-0004", "900.HANDOVER.v1", "MEM-2026-0005", "700.V32-ENGINEERING-RECORD.v1", "MEM-2026-0011",
})


def split_frontmatter_raw(content: str) -> Tuple[str, str]:
    """Splits Markdown into (raw_frontmatter, body) without altering formatting."""
    if not content.startswith("---\n"): raise ValueError("Missing YAML frontmatter opening '---'")
    parts = content.split("\n---\n", 1)
    if len(parts) != 2: raise ValueError("Missing YAML frontmatter closing '---'")
    return parts[0][4:], parts[1]


def surgical_set_scalar(raw_fm: str, key: str, new_value_str: str) -> str:
    """Replaces `key: <old_value>` in raw YAML frontmatter while preserving indentation, quotes, and comments."""
    pattern = re.compile(rf"(?m)^([ \t]*{re.escape(key)}:[ \t]*)([^\n#]+?)([ \t]*(?:#[^\r\n]*)?)$")
    def repl(match: re.Match[str]) -> str:
        prefix, old_val, suffix = match.group(1), match.group(2).strip(), match.group(3)
        needs_quote = not (new_value_str.startswith('"') or new_value_str.startswith("'")) and not new_value_str.isdigit() and old_val.startswith('"') and old_val.endswith('"')
        return f'{prefix}"{new_value_str}"{suffix}' if needs_quote else f"{prefix}{new_value_str}{suffix}"
    updated, count = pattern.subn(repl, raw_fm, count=1)
    if count == 0: raise KeyError(f"Key '{key}' not found in frontmatter")
    return updated


def surgical_try_set_scalar(raw_fm: str, key: str, new_value_str: str) -> Tuple[str, bool]:
    """Attempts surgical_set_scalar and returns (updated_fm, changed) without raising KeyError."""
    try: return surgical_set_scalar(raw_fm, key, new_value_str), True
    except KeyError: return raw_fm, False


def surgical_remove_from_yaml_list(raw_fm: str, list_key: str, item_to_remove: str) -> str:
    """Surgically removes `item_to_remove` from a YAML list `list_key:` in `raw_fm`."""
    inline_pat = re.compile(rf"(?m)^([ \t]*{re.escape(list_key)}:[ \t]*\[)([^\]]*)(\][ \t]*(?:#[^\r\n]*)?)$")
    if (m_inline := inline_pat.search(raw_fm)):
        kept = [x for x in (s.strip() for s in m_inline.group(2).split(",")) if x and x.strip("\"'") != item_to_remove]
        return inline_pat.sub(rf"\g<1>{', '.join(kept)}\g<3>", raw_fm, count=1)
    out_lines: List[str] = []
    in_list, list_indent, hdr_idx, rem_items, removed = False, 0, -1, 0, False
    empty_hdr_re = rf"^([ \t]*{re.escape(list_key)}:)[ \t]*((?:#[^\r\n]*)?\r?\n?)$"
    for line in raw_fm.splitlines(keepends=True):
        st, ind = line.strip(), len(line) - len(line.lstrip(" "))
        if not in_list:
            if (m_hdr := re.match(rf"^([ \t]*){re.escape(list_key)}:[ \t]*(?:#[^\r\n]*)?\r?\n?$", line)):
                in_list, list_indent, hdr_idx, rem_items = True, len(m_hdr.group(1)), len(out_lines), 0
            out_lines.append(line)
            continue
        if st.startswith("- ") and ind > list_indent:
            if st[2:].split("#", 1)[0].strip().strip("\"'") == item_to_remove: removed = True
            else:
                rem_items += 1
                out_lines.append(line)
        elif not st or st.startswith("#"): out_lines.append(line)
        else:
            in_list = False
            if removed and rem_items == 0 and hdr_idx >= 0:
                out_lines[hdr_idx] = re.sub(empty_hdr_re, r"\1 []\2", out_lines[hdr_idx])
            out_lines.append(line)
    if in_list and removed and rem_items == 0 and hdr_idx >= 0:
        out_lines[hdr_idx] = re.sub(empty_hdr_re, r"\1 []\2", out_lines[hdr_idx])
    return "".join(out_lines)


def render_role_models_ssot_block(project_root: Path) -> str | None:
    brain_env = os.environ.get("PI_CODING_AGENT_DIR")
    candidates = ([Path(brain_env) / "role-models.json"] if brain_env else []) + [
        project_root / ".netark" / "role-models.json", project_root / "templates" / "hosts" / "pi" / "role-models.json.tpl",
    ]
    rm_path = next((p for p in candidates if p.exists()), None)
    if rm_path is None: return None
    try: rm_data = json.loads(rm_path.read_text(encoding="utf-8"))
    except Exception: return None  # noqa: silent-except
    lines = ["<!-- AUTO-ROLE-MODELS:START -->", "| 角色 (Role) | 當前綁定模型 (`.netark/role-models.json` SSOT) |", "| :--- | :--- |"]
    for rk in ("orchestrator", "scout", "architect", "challenger", "code", "audit", "vision", "strategyMode"):
        if rk in rm_data: lines.append(f"| `{rk}` | `{rm_data[rk]}` |")
    return "\n".join(lines + ["<!-- AUTO-ROLE-MODELS:END -->"])


def compute_actual_epistemic_counts(body: str) -> Dict[str, int]:
    """Uses the exact same regexes as schema_validator.EPISTEMIC_TAGS."""
    return {key: len(pattern.findall(body)) for key, pattern in sv.EPISTEMIC_TAGS.items()}


def load_all_node_paths(project_root: Path) -> Tuple[Dict[str, Path], Dict[str, str], Dict[str, Dict[str, Any]]]:
    memory_dir = project_root / "memory"
    id_to_path, key_to_id, all_nodes = {}, {}, {}
    if not memory_dir.exists(): return id_to_path, key_to_id, all_nodes
    for p in sorted(memory_dir.rglob("*.md")):
        if p.name == "CONTEXT_MAP.md": continue
        try: fm, _ = sv.parse_markdown_frontmatter(p)
        except Exception: continue  # noqa: silent-except
        if not isinstance(fm, dict): continue
        ci = fm.get("context_index") if isinstance(fm.get("context_index"), dict) else {}
        nkey = str(ci.get("node_key") or fm.get("node_key") or "").strip()
        nid = str(fm.get("node_id") or nkey or p.stem).strip()
        if not nid: continue
        id_to_path[nid], all_nodes[nid] = p, fm
        if nkey: key_to_id[nkey] = nid
    return id_to_path, key_to_id, all_nodes


def _extract_completed_wos(project_root: Path) -> set[str]:
    """Return set of WO-XXXX ids marked completed in memory/LEDGER.md."""
    ledger = project_root / "memory" / "LEDGER.md"
    if not ledger.exists(): return set()
    try: txt = ledger.read_text(encoding="utf-8")
    except Exception: return set()  # noqa: silent-except
    done: set[str] = set()
    for line in txt.splitlines():
        if not line.lstrip().startswith("|"): continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.search(r"(?i)(?:✅|已完成|\bcompleted\b|\bdone\b|\bverified\b)", cells[-1]):
            src = cells[0] if re.search(r"\bWO-\d+\b", cells[0]) else " ".join(cells[:-1])
            done.update(re.findall(r"\bWO-\d+\b", src))
    return done


def _extract_yaml_list_items(raw_fm: str, key: str) -> List[str]:
    """Extract inline `[a, b]` or multiline `- a` YAML list items from raw frontmatter."""
    m = re.search(rf"(?m)^([ \t]*){re.escape(key)}:[ \t]*(.*)$", raw_fm)
    if not m: return []
    base_ind, inline = len(m.group(1)), re.sub(r"(?:^|\s+)#.*$", "", m.group(2)).strip()
    if inline.startswith("[") and inline.endswith("]"):
        return [x.strip().strip("\"'") for x in inline[1:-1].split(",") if x.strip().strip("\"'")]
    if inline:
        v = inline.strip("\"'")
        return [v] if v and v.lower() not in {"null", "none", "~"} else []
    items: List[str] = []
    for ln in raw_fm[m.end():].splitlines()[1:]:
        st = ln.strip()
        if not st or st.startswith("#"): continue
        ind = len(ln) - len(ln.lstrip(" \t"))
        if ind < base_ind or (ind == base_ind and not st.startswith("-")) or not st.startswith("- "): break
        if (v := st[2:].split("#", 1)[0].strip().strip("\"'")): items.append(v)
    return items


def _node_aliases(nid: str, npath: Path | None, fm: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    ci = fm.get("context_index") if isinstance(fm.get("context_index"), dict) else {}
    node_id = str(fm.get("node_id") or nid).strip()
    node_key = str(ci.get("node_key") or fm.get("node_key") or "").strip()
    aliases = [k for k in (node_id, node_key) if k]
    if isinstance(npath, Path):
        aliases.append(npath.stem)
        if (ms := re.match(r"^310_\d{2}(?:_\d+)?_(.+)$", npath.stem)): aliases.append(f"310.{ms.group(1)}.v1")
    return node_id, node_key, aliases


def _index_target_nodes(all_nodes: Dict[str, Any], excluded: set[str]) -> Tuple[Dict[str, Tuple[str, Dict[str, Any], set[str]]], Dict[str, List[Tuple[str, Dict[str, Any], set[str]]]]]:
    exact, pfx = {}, {}
    for nid, val in all_nodes.items():
        npath, fm = val if (isinstance(val, tuple) and len(val) == 2) else (None, val)
        if not isinstance(fm, dict): continue
        node_id, node_key, aliases = _node_aliases(nid, npath if isinstance(npath, Path) else None, fm)
        if node_id in excluded or (node_key and node_key in excluded): continue
        entry = (node_id, fm, set(aliases))
        for a in aliases: exact.setdefault(a, entry)
        if node_key: exact[node_key] = entry
        if isinstance(npath, Path):
            posix = npath.as_posix().replace("\\", "/")
            exact[npath.name] = exact[posix] = entry
            if "/memory/" in posix: exact["memory/" + posix.split("/memory/", 1)[1]] = entry
            if (m_310 := re.match(r"^(310_\d{2})(?:_|\.|$)", npath.name)): pfx.setdefault(m_310.group(1), []).append(entry)
    return exact, pfx


def _is_non_wo_handover_converged(raw_fm: str, body: str, all_nodes: Dict[str, Any]) -> bool:
    """Return True when non-WO handover has >=1 resolved target and all are archived/deprecated or superseded by verified nodes."""
    m_nid, m_nkey = re.search(r'(?m)^node_id:\s*["\']?(MEM-\d{4}-\d{4})["\']?', raw_fm), re.search(r'(?m)^[ \t]*node_key:\s*["\']?([^"\'\s#]+)', raw_fm)
    excluded = set(ETERNAL_CORE_REFS) | {m.group(1) for m in (m_nid, m_nkey) if m}
    superseded: set[str] = set()
    for val in all_nodes.values():
        n_fm = val[1] if (isinstance(val, tuple) and len(val) == 2) else val
        if not isinstance(n_fm, dict) or str(n_fm.get("status") or "").strip().lower() != "verified": continue
        topo = n_fm.get("topology") if isinstance(n_fm.get("topology"), dict) else {}
        superseded.update(str(t).strip() for t in (topo.get("supersedes") or []) if isinstance(t, str) and str(t).strip())
    m_s1 = re.search(r"(?m)^##\s*1\..*?\n([\s\S]*?)(?=\n##\s|\Z)", body)
    s1 = (m_s1.group(1).strip() if m_s1 else "") or body
    refs = (_extract_yaml_list_items(raw_fm, "depends_on") + _extract_yaml_list_items(raw_fm, "affected_paths")
            + [lk.split("|", 1)[0].strip() for lk in re.findall(r"\[\[([^\]]+)\]\]", s1)]
            + re.findall(r"\bMEM-\d{4}-\d{4}\b|\b\d{3}\.[A-Za-z0-9._-]+\.v\d+\b|\b310_\d{2}(?:_[A-Za-z0-9_-]+)?\b", s1))
    exact, pfx = _index_target_nodes(all_nodes, excluded)
    resolved: Dict[str, Tuple[Dict[str, Any], set[str]]] = {}
    for ref in refs:
        if not ref or ref in excluded: continue
        if ref in exact: resolved[exact[ref][0]] = (exact[ref][1], exact[ref][2])
        elif ref.endswith(".md") and Path(ref).name in exact and Path(ref).name not in {"HANDOVER.md", "LEDGER.md"}:
            t = exact[Path(ref).name]; resolved[t[0]] = (t[1], t[2])
        elif ref in pfx:
            for nid, fm, als in pfx[ref]: resolved[nid] = (fm, als)
    return bool(resolved) and all(str(fm.get("status") or "").strip().lower() in {"archived", "deprecated"} or bool(superseded & als) for fm, als in resolved.values())


def _archive_md_status(md_file: Path, raw_fm: str, body: str, project_root: Path, today_str: str, old_st: str, extra: Dict[str, str] | None = None) -> Dict[str, str] | None:
    new_fm, changed = surgical_try_set_scalar(raw_fm, "status", "archived")
    if not changed: return None
    new_fm, _ = surgical_try_set_scalar(new_fm, "updated_at", today_str)
    md_file.write_text(f"---\n{new_fm}\n---\n{body}", encoding="utf-8")
    return {"path": str(md_file.relative_to(project_root)), "old_status": old_st, "new_status": "archived", **(extra or {})}


def _extract_wo_refs_for_ho(ho_path: Path, raw_fm: str, body: str) -> Tuple[str, set[str]]:
    src = f"{raw_fm}\n{body}"
    m_ts = re.search(r'(?m)^track_status:\s*["\']?([^"\'\s#]+)', src)
    t_st = m_ts.group(1).strip().lower() if m_ts else ""
    tids = [v.strip() for v in re.findall(r'(?m)^(?:track_id|active_wo):\s*["\']?([^"\'\n#]+)', src) if v.strip()]
    if tids or re.search(r"\bWO-\d+\b", ho_path.name): wo_src = f"{ho_path.name}\n" + "\n".join(tids)
    elif t_st == "active": wo_src = ""
    else:
        m_s1 = re.search(r"(?m)^##\s*1\..*?\n([\s\S]*?)(?=\n##\s|\Z)", body)
        wo_src = m_s1.group(1) if m_s1 else ""
    return t_st, set(re.findall(r"\bWO-\d+\b", wo_src))


def _auto_archive_completed_handovers(md_path: Path, project_root: Path, today_str: str | Dict[str, Any] | None = None, all_nodes: Dict[str, Any] | None = None) -> List[Dict[str, str]]:
    """Auto-set YAML status='archived' on HANDOVER_*.md when self-done, WO done, or non-WO targets converged."""
    if isinstance(today_str, dict): all_nodes, today_str = today_str, datetime.date.today().isoformat()
    today_str = today_str or datetime.date.today().isoformat()
    ep_dir = project_root / "memory" / "episodic"
    targets = sorted(ep_dir.glob("HANDOVER_*.md")) if ep_dir.exists() else []
    if not targets: return []
    if all_nodes is None:
        id_to_path, _, fm_map = load_all_node_paths(project_root)
        all_nodes = {nid: (id_to_path[nid], fm_map[nid]) for nid in fm_map if nid in id_to_path}
    completed_wos, archived = _extract_completed_wos(project_root), []
    for ho_path in targets:
        try: raw_fm, body = split_frontmatter_raw(ho_path.read_text(encoding="utf-8"))
        except Exception: continue  # noqa: silent-except
        m_st = re.search(r'(?m)^status:\s*["\']?([^"\'\s#]+)', raw_fm)
        old_st = m_st.group(1).strip() if m_st else ""
        if old_st.lower() in {"archived", "deprecated"}: continue
        t_st, wo_refs = _extract_wo_refs_for_ho(ho_path, raw_fm, body)
        is_wo_done = bool(wo_refs and wo_refs.issubset(completed_wos))
        if not (t_st in {"completed", "archived"} or is_wo_done or (not wo_refs and _is_non_wo_handover_converged(raw_fm, body, all_nodes))): continue
        if (rec := _archive_md_status(ho_path, raw_fm, body, project_root, today_str, old_st)): archived.append(rec)
    return archived


def _cascade_archive_blueprint_shards(fm_after: Dict[str, Any], project_root: Path, today_str: str, id_to_path: Dict[str, Path], all_nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    """Archive verified child shards when parent blueprint is archived and all siblings are verified/archived."""
    if fm_after.get("artifact_type") != "blueprint" or str(fm_after.get("status") or "").lower() != "archived": return []
    bp_nid = str(fm_after.get("node_id") or "")
    bp_refs = {r for r in (bp_nid, str((fm_after.get("context_index") or {}).get("node_key") or "")) if r}
    siblings = [(nid, id_to_path[nid], tfm) for nid, tfm in all_nodes.items() if nid != bp_nid and nid in id_to_path and str((tfm.get("topology") or {}).get("parent_blueprint") or "").strip() in bp_refs]
    if not bp_refs or not siblings or not all(str(tfm.get("status") or "").lower() in {"verified", "archived"} for _, _, tfm in siblings): return []
    cascaded: List[Dict[str, str]] = []
    for nid, spath, tfm in siblings:
        if str(tfm.get("status") or "").lower() != "verified": continue
        s_raw_fm, s_body = split_frontmatter_raw(spath.read_text(encoding="utf-8"))
        if (rec := _archive_md_status(spath, s_raw_fm, s_body, project_root, today_str, "verified", {"node_id": nid})): cascaded.append(rec)
    return cascaded


def apply_supersedes_transitions(fm_after: Dict[str, Any], project_root: Path, today_str: str | None = None, id_to_path: Dict[str, Path] | None = None, key_to_id: Dict[str, str] | None = None, all_nodes: Dict[str, Dict[str, Any]] | None = None) -> List[Dict[str, str]]:
    """Archive superseded note/wiki targets on reviewing+ or deprecate official targets on verified."""
    today_str, status = today_str or datetime.date.today().isoformat(), fm_after.get("status", "")
    supersedes_list = (fm_after.get("topology", {}) or {}).get("supersedes", []) or []
    if not supersedes_list or status not in ("reviewing", "stub_ready", "verified"): return []
    if id_to_path is None or key_to_id is None or all_nodes is None:
        id_to_path, key_to_id, all_nodes = load_all_node_paths(project_root)
    this_nid, this_nkey, transitions = fm_after.get("node_id", ""), (fm_after.get("context_index", {}) or {}).get("node_key", ""), []
    for sup_ref in supersedes_list:
        tid = sup_ref if sup_ref in id_to_path else key_to_id.get(sup_ref)
        if not tid or tid not in id_to_path: continue
        tpath, tfm = id_to_path[tid], all_nodes.get(tid, {})
        t_status, t_art, t_track = tfm.get("status", ""), tfm.get("artifact_type", ""), (tfm.get("context_index", {}) or {}).get("artifact_track", "")
        desired = "archived" if (t_art == "note" or t_track == "wiki") else ("deprecated" if status == "verified" else "")
        if not desired: continue
        t_raw_fm, t_body = split_frontmatter_raw(tpath.read_text(encoding="utf-8"))
        t_mod = False
        if t_status not in ("archived", "deprecated"):
            t_raw_fm, t_mod = surgical_set_scalar(t_raw_fm, "status", desired), True
        t_sups = (tfm.get("topology", {}) or {}).get("supersedes", []) or []
        for rev_ref in (this_nid, this_nkey):
            if rev_ref and rev_ref in t_sups:
                t_raw_fm, t_mod = surgical_remove_from_yaml_list(t_raw_fm, "supersedes", rev_ref), True
        if t_mod:
            t_raw_fm, _ = surgical_try_set_scalar(t_raw_fm, "updated_at", today_str)
            tpath.write_text(f"---\n{t_raw_fm}\n---\n{t_body}", encoding="utf-8")
            transitions.append({"node_id": tid, "path": str(tpath.relative_to(project_root)), "old_status": t_status, "new_status": desired})
    return transitions


def sync_governed_markdown(md_path: Path, project_root: Path, today_str: str | None = None) -> Dict[str, Any]:  # noqa: god-function
    today_str = today_str or datetime.date.today().isoformat()
    result: Dict[str, Any] = {"file": str(md_path), "counts_updated": False, "ssot_table_updated": False, "old_counts": {}, "new_counts": {}, "deprecated_targets": [], "archived_shards": [], "archived_handovers": [], "phase1_errors": [], "phase2_aborted": False}
    if not md_path.exists(): result["phase2_aborted"] = True; return result
    raw_content = auto_initialize_wiki_node(md_path, project_root, md_path.read_text(encoding="utf-8"))
    try:
        raw_fm, body = split_frontmatter_raw(raw_content)
        fm, _ = sv.parse_markdown_frontmatter(md_path)
    except Exception as exc:
        result["phase1_errors"], result["phase2_aborted"] = [str(exc)], True
        return result
    new_body = body
    if ROLE_MODELS_MARKER_RE.search(new_body) and (rendered_block := render_role_models_ssot_block(project_root)):
        if (replaced_body := ROLE_MODELS_MARKER_RE.sub(rendered_block, new_body)) != new_body: new_body, result["ssot_table_updated"] = replaced_body, True
    actual_counts, declared_profile = compute_actual_epistemic_counts(new_body), fm.get("epistemic_profile", {}) or {}
    result["old_counts"], result["new_counts"] = {k: declared_profile.get(k) for k in sv.EPISTEMIC_TAGS}, actual_counts
    new_raw_fm, counts_changed = raw_fm, False
    for key, actual_val in actual_counts.items():
        if declared_profile.get(key) != actual_val:
            new_raw_fm, did_set = surgical_try_set_scalar(new_raw_fm, key, str(actual_val))
            counts_changed = counts_changed or did_set
    checksum_changed = False
    if "content_checksum" in fm:
        body_for_hash = new_body.lstrip("\r\n") if new_body.startswith("\r\n") else (new_body.lstrip("\n") if new_body.startswith("\n") else new_body)
        new_chk = hashlib.sha256(body_for_hash.encode("utf-8")).hexdigest()[:16]
        if fm.get("content_checksum") != new_chk: new_raw_fm, checksum_changed = surgical_try_set_scalar(new_raw_fm, "content_checksum", f'"{new_chk}"')
    date_changed = False
    if str(fm.get("created_at", "")) > today_str: new_raw_fm, date_changed = surgical_try_set_scalar(new_raw_fm, "created_at", today_str)
    if counts_changed or checksum_changed or result["ssot_table_updated"] or date_changed or str(fm.get("updated_at", "")) != today_str:
        new_raw_fm, _ = surgical_try_set_scalar(new_raw_fm, "updated_at", today_str)
        md_path.write_text(f"---\n{new_raw_fm}\n---\n{new_body}", encoding="utf-8")
        result["counts_updated"] = counts_changed
    result["archived_handovers"] = _auto_archive_completed_handovers(md_path, project_root, today_str)
    schemas_dir = (project_root / "schemas") if (project_root / "schemas" / "artifact_header.schema.json").exists() else (PROJECT_ROOT_DEFAULT / "schemas")
    header_schema, node_schema = json.loads((schemas_dir / "artifact_header.schema.json").read_text(encoding="utf-8")), json.loads((schemas_dir / "context_node.schema.json").read_text(encoding="utf-8"))
    id_to_path, key_to_id, all_nodes = load_all_node_paths(project_root)
    fm_after, errs = sv.validate_document(md_path, project_root, header_schema, node_schema, run_oracle=False, all_nodes=all_nodes)
    blocking_errs = [e for e in errs if not e.startswith("[AS-06 Supersedes Conflict]")]
    result["phase1_errors"] = blocking_errs
    if blocking_errs or not fm_after: result["phase2_aborted"] = True; return result
    result["deprecated_targets"] = apply_supersedes_transitions(fm_after, project_root, today_str=today_str, id_to_path=id_to_path, key_to_id=key_to_id, all_nodes=all_nodes)
    result["archived_shards"] = _cascade_archive_blueprint_shards(fm_after, project_root, today_str, id_to_path, all_nodes)
    if result["deprecated_targets"] or result["archived_shards"]: result["archived_handovers"].extend(_auto_archive_completed_handovers(md_path, project_root, today_str))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Hook Metadata & Topology Sync for NetArk Memory Nodes.")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("positional_file", nargs="?", default=None, help="Target file (positional)")
    parser.add_argument("--file", default=None, help="Target governed Markdown file to sync")
    parser.add_argument("--init", nargs="?", const=True, default=False, help="Initialize a draft Markdown file with governed YAML frontmatter")
    parser.add_argument("--type", default="wiki", help="Artifact type for initialization (default: wiki)")
    parser.add_argument("--domain", default=None, help="Domain code for initialization (default: auto-detected or 310/300)")
    parser.add_argument("--node-key", default=None, help="Node key for initialization")
    parser.add_argument("--title", default=None, help="Document title for initialization")
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    target_file = args.init if (isinstance(args.init, str) and args.init is not True) else (args.file or args.positional_file)
    if not target_file: parser.error("Either --file <path>, positional <path>, or --init <path> must be specified.")
    md_path = Path(target_file).resolve()
    if args.init:
        init_governed_markdown(md_path, project_root, artifact_type=args.type, domain_code=args.domain, node_key=args.node_key, title=args.title)
    res = sync_governed_markdown(md_path, project_root)
    rel = md_path.relative_to(project_root) if md_path.is_relative_to(project_root) else md_path
    msgs: List[str] = []
    if res.get("counts_updated"): msgs.append(f"🔄 [Hook Auto-Sync] 已自動校正 `{rel}` 之 `epistemic_profile` 標籤計數: {res['old_counts']} -> {res['new_counts']}")
    if res.get("ssot_table_updated"): msgs.append(f"🔄 [Hook Auto-Sync] 已由 `.netark/role-models.json` 自動同步 `{rel}` 內之 SSOT 角色模型表")
    for dep in res.get("deprecated_targets", []): msgs.append(f"🔄 [Hook Auto-Supersede] 因應 `{rel}` 宣告 `supersedes`，已自動將舊節點 `{dep['node_id']}` (`{dep['path']}`) 狀態由 `{dep['old_status']}` 降級為 `{dep['new_status']}`")
    for arc in res.get("archived_handovers", []): msgs.append(f"🔄 [Hook Auto-Archive] 交接軌道 `{arc['path']}` 已結案，狀態由 `{arc['old_status']}` 自動歸檔為 `archived`")
    for shd in res.get("archived_shards", []): msgs.append(f"🔄 [Hook Cascade-Archive] 母藍圖已歸檔，子切片 `{shd['node_id']}` (`{shd['path']}`) 自動由 `{shd['old_status']}` 歸檔為 `archived`")
    if msgs: print("\n".join(msgs))
    return 0


if __name__ == "__main__": sys.exit(main())
