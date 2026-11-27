#!/usr/bin/env python3
"""NetArk Deterministic Hook `.md` Metadata & Topology Auto-Sync (sync_doc_metadata.py)."""

from __future__ import annotations

import argparse, datetime, json, os, re, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DEFAULT = SCRIPT_DIR.parent
for _p in (PROJECT_ROOT_DEFAULT, PROJECT_ROOT_DEFAULT / "schemas"):
    if str(_p) not in sys.path: sys.path.insert(0, str(_p))

import schema_validator as sv  # type: ignore  # noqa: E402
from schemas.doc_initializer import allocate_next_node_id, auto_initialize_wiki_node, init_governed_markdown, init_memory_node  # type: ignore  # noqa: E402,F401

ROLE_MODELS_MARKER_RE = re.compile(r"<!-- AUTO-ROLE-MODELS:START -->.*?<!-- AUTO-ROLE-MODELS:END -->", re.DOTALL)
AUTO_LEDGER_START = "<!-- NETARK:AUTO-LEDGER:START -->"
AUTO_LEDGER_END = "<!-- NETARK:AUTO-LEDGER:END -->"


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


def _fm_scalar(raw_fm: str, key: str) -> str:
    m = re.search(rf'(?m)^[ \t]*{re.escape(key)}:[ \t]*([^\n#]*)', raw_fm)
    return m.group(1).strip().strip("\"'") if m else ""


def _build_status_lookup(project_root: Path, all_nodes: Dict[str, Any] | None) -> Dict[str, str]:
    nodes = all_nodes if all_nodes is not None else load_all_node_paths(project_root)[2]
    lookup: Dict[str, str] = {}
    for nid, val in nodes.items():
        fm = val[1] if (isinstance(val, tuple) and len(val) == 2) else val
        if not isinstance(fm, dict): continue
        st, ci = str(fm.get("status") or "").strip().lower(), fm.get("context_index") if isinstance(fm.get("context_index"), dict) else {}
        for ref in (nid, fm.get("node_id"), ci.get("node_key"), fm.get("node_key")):
            if isinstance(ref, str) and ref.strip(): lookup[ref.strip()] = st
    return lookup


def _archive_md_status(md_file: Path, raw_fm: str, body: str, project_root: Path, today_str: str, old_st: str, extra: Dict[str, str] | None = None) -> Dict[str, str] | None:
    new_fm, changed = surgical_try_set_scalar(raw_fm, "status", "archived")
    if not changed: return None
    new_fm, _ = surgical_try_set_scalar(new_fm, "updated_at", today_str)
    md_file.write_text(f"---\n{new_fm}\n---\n{body}", encoding="utf-8")
    return {"path": str(md_file.relative_to(project_root)), "old_status": old_st, "new_status": "archived", **(extra or {})}


def _auto_archive_completed_handovers(md_path: Path, project_root: Path, today_str: str | Dict[str, Any] | None = None, all_nodes: Dict[str, Any] | None = None) -> List[Dict[str, str]]:
    """Auto-set YAML status='archived' on HANDOVER_*.md when track_status or active_blueprint is done."""
    if isinstance(today_str, dict): all_nodes, today_str = today_str, datetime.date.today().isoformat()
    today_str, ep_dir = today_str or datetime.date.today().isoformat(), project_root / "memory" / "episodic"
    targets = sorted(ep_dir.glob("HANDOVER_*.md")) if ep_dir.exists() else []
    if not targets: return []
    status_lookup, archived = None, []
    for ho_path in targets:
        try: raw_fm, body = split_frontmatter_raw(ho_path.read_text(encoding="utf-8"))
        except Exception: continue  # noqa: silent-except
        old_st = _fm_scalar(raw_fm, "status")
        if old_st.lower() in {"archived", "deprecated"}: continue
        t_st, active_bp, bp_done = _fm_scalar(raw_fm, "track_status").lower(), _fm_scalar(raw_fm, "active_blueprint"), False
        if active_bp and active_bp.lower() not in {"null", "none", "~"}:
            if status_lookup is None: status_lookup = _build_status_lookup(project_root, all_nodes)
            bp_done = status_lookup.get(active_bp) in {"verified", "archived"}
        if (t_st in {"completed", "archived"} or bp_done) and (rec := _archive_md_status(ho_path, raw_fm, body, project_root, today_str, old_st)):
            archived.append(rec)
    return archived


def _collect_blueprint_and_shard_stats(specs_dir: Path) -> Tuple[List[Tuple[int, str, Path, Dict[str, Any]]], Dict[str, Dict[str, int]]]:
    blueprints, shard_counts = [], {}
    if not specs_dir.is_dir(): return blueprints, shard_counts
    for sp in sorted(specs_dir.glob("*.md")):
        try: fm, _ = sv.parse_markdown_frontmatter(sp)
        except Exception: continue  # noqa: silent-except
        if not isinstance(fm, dict): continue
        if (m_seq := re.match(r"^200_(\d+)_", sp.name)): blueprints.append((int(m_seq.group(1)), m_seq.group(1), sp, fm))
        pb = str((fm.get("topology") or {}).get("parent_blueprint") or "").strip() if isinstance(fm.get("topology"), dict) else ""
        st = str(fm.get("status") or "").strip().lower()
        bucket = "done" if st == "verified" else ("wip" if st in {"stub_ready", "reviewing"} else ("draft" if st == "draft" else ""))
        if pb and bucket: shard_counts.setdefault(pb, {"done": 0, "wip": 0, "draft": 0})[bucket] += 1
    return blueprints, shard_counts


def _format_auto_ledger_row(seq_str: str, bp_key: str, bp_id: str, bp_st: str, summary: str, shard_counts: Dict[str, Dict[str, int]]) -> str:
    summary_clean = (summary or bp_key).replace("|", "｜").strip()
    head = re.split(r"[：—]", summary_clean, maxsplit=1)[0].replace("*", "").strip()
    title_clean = (head[:28].strip() if len(head) > 28 else head) or bp_key[:28]
    done, wip, draft = (sum((shard_counts.get(r) or {}).get(k, 0) for r in {x for x in (bp_key, bp_id) if x}) for k in ("done", "wip", "draft"))
    badge = "✅ 已完成" if bp_st == "verified" else ("📝 草案 (draft)" if bp_st == "draft" else f"🚧 施工中 ({bp_st})")
    return f"| `BP-{seq_str}` | **{title_clean}**｜{summary_clean} ({done}✅ {wip}🟡 {draft}🟠) | `{bp_key}` | `{badge}` |"


def sync_auto_ledger(project_root: Path) -> bool:
    """Sync unreferenced 200_*.md blueprints into memory/LEDGER.md auto-ledger markers (<= 80 lines)."""
    ledger_p = project_root / "memory" / "LEDGER.md"
    if not ledger_p.is_file(): return False
    lines = ledger_p.read_text(encoding="utf-8").splitlines()
    s_idx, e_idx = next((i for i, ln in enumerate(lines) if AUTO_LEDGER_START in ln), -1), next((i for i, ln in enumerate(lines) if AUTO_LEDGER_END in ln), -1)
    if s_idx == -1 or e_idx == -1 or e_idx <= s_idx: return False
    before_lines, after_lines = lines[:s_idx], lines[e_idx + 1:]
    while after_lines and not after_lines[-1].strip(): after_lines.pop()
    non_marker_lines = before_lines + after_lines
    hist_body = re.sub(r"^---\n[\s\S]*?\n---\n?", "", "\n".join(non_marker_lines))
    hist_tokens = set(re.findall(r"`([^`]+)`", hist_body))
    blueprints, shard_counts = _collect_blueprint_and_shard_stats(project_root / "memory" / "specs")
    candidates: List[Tuple[bool, int, str]] = []
    for seq_int, seq_str, sp, fm in blueprints:
        bp_st = str(fm.get("status") or "").strip().lower()
        if bp_st in {"archived", "deprecated"}: continue
        ci = fm.get("context_index") if isinstance(fm.get("context_index"), dict) else {}
        bp_id, bp_key = str(fm.get("node_id") or "").strip(), str(ci.get("node_key") or fm.get("node_key") or fm.get("node_id") or sp.stem).strip()
        if bp_key in hist_tokens or re.search(rf"(?<![A-Za-z0-9._-]){re.escape(bp_key)}(?![A-Za-z0-9._-])", hist_body): continue
        candidates.append((bp_st == "verified", seq_int, _format_auto_ledger_row(seq_str, bp_key, bp_id, bp_st, str(ci.get("summary_1line") or "").strip(), shard_counts)))
    budget = max(0, 80 - len(non_marker_lines) - 2)
    if len(candidates) > budget:
        candidates = sorted(candidates, key=lambda item: (1 if item[0] else 0, -item[1]))[:budget]
    selected_rows = [row for _, _, row in sorted(candidates, key=lambda item: item[1])]
    if lines[s_idx + 1 : e_idx] == selected_rows: return False
    new_text = "\n".join(before_lines + [lines[s_idx]] + selected_rows + [lines[e_idx]] + after_lines) + "\n"
    if new_text.startswith("---\n") and "\n---\n" in new_text:
        raw_fm, body = split_frontmatter_raw(new_text)
        new_fm, _ = surgical_try_set_scalar(raw_fm, "updated_at", datetime.date.today().isoformat())
        if re.search(r"(?m)^content_checksum:", new_fm):
            new_fm, _ = surgical_try_set_scalar(new_fm, "content_checksum", sv.compute_body_checksum(body))
        new_text = f"---\n{new_fm}\n---\n{body}"
    tmp_p = ledger_p.with_name(f".{ledger_p.name}.{os.getpid()}.tmp")
    try: tmp_p.write_text(new_text, encoding="utf-8"); os.replace(tmp_p, ledger_p)
    except Exception: tmp_p.unlink(missing_ok=True); raise
    return True


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


def _load_schema_pair(project_root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    for base in (project_root / "schemas", PROJECT_ROOT_DEFAULT / "schemas"):
        hdr, nod = base / "artifact_header.schema.json", base / "context_node.schema.json"
        if hdr.is_file() and nod.is_file():
            return json.loads(hdr.read_text(encoding="utf-8")), json.loads(nod.read_text(encoding="utf-8"))
    import builtins
    assets = getattr(builtins, "__NETARK_EMBEDDED_ASSETS__", None) or {}
    return json.loads(assets["schemas/artifact_header.schema.json"]), json.loads(assets["schemas/context_node.schema.json"])


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
        new_chk = sv.compute_body_checksum(new_body)
        if fm.get("content_checksum") != new_chk: new_raw_fm, checksum_changed = surgical_try_set_scalar(new_raw_fm, "content_checksum", f'"{new_chk}"')
    date_changed = False
    if str(fm.get("created_at", "")) > today_str: new_raw_fm, date_changed = surgical_try_set_scalar(new_raw_fm, "created_at", today_str)
    if counts_changed or checksum_changed or result["ssot_table_updated"] or date_changed or str(fm.get("updated_at", "")) != today_str:
        new_raw_fm, _ = surgical_try_set_scalar(new_raw_fm, "updated_at", today_str)
        md_path.write_text(f"---\n{new_raw_fm}\n---\n{new_body}", encoding="utf-8")
        result["counts_updated"] = counts_changed
    result["archived_handovers"] = _auto_archive_completed_handovers(md_path, project_root, today_str)
    header_schema, node_schema = _load_schema_pair(project_root)
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
