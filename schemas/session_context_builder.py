#!/usr/bin/env python3
"""NetArk Session Context Builder, Codebook Refresh & AGY Alert Queue (schemas/session_context_builder.py)."""

from __future__ import annotations

import hashlib, json, re, sys, tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas.netark_dlp_core import scan_plaintext_secrets  # noqa: E402

AGY_SESSION_LRU_CAP = 32


def _parse_yaml_list(src: str, key: str) -> List[str]:
    """Extract inline `[a, b]` or multiline `- a` YAML list values for `key`."""
    m = re.search(rf"(?m)^[ \t]*{re.escape(key)}:[ \t]*(.*)$", src)
    if not m: return []
    inline = re.sub(r"(?:^|\s+)#.*$", "", m.group(1)).strip()
    if inline.startswith("[") and inline.endswith("]"):
        return [it.strip().strip("\"'") for it in inline[1:-1].split(",") if it.strip().strip("\"'")]
    if inline:
        val = inline.strip("\"'")
        return [val] if val and val.lower() not in {"null", "none", "~"} else []
    items: List[str] = []
    for ln in src[m.end():].splitlines()[1:]:
        if not ln.strip() or ln.lstrip().startswith("#"): continue
        if not ln.startswith((" ", "\t", "-")): break
        if not (m_it := re.match(r"^[ \t]*-\s+(.+?)(?:\s+#.*)?$", ln)): break
        if (val := m_it.group(1).strip().strip("\"'")): items.append(val)
    return items


def _parse_handover_meta(text: str, filename: str = "") -> Dict[str, Any]:
    """Extract track_id, status, track_status, §1 topic, WO ids, and active blueprint/shards."""
    m_fm = re.match(r"^---\n([\s\S]*?)\n---\n", text)
    fm, body = (m_fm.group(1), text[m_fm.end():]) if m_fm else ("", text)
    def _val(key: str, src: str) -> str:
        m = re.search(rf'(?m)^{key}:\s*["\']?([^"\'\n#]+)', src)
        return m.group(1).strip() if m else ""
    m_s1 = re.search(r"(?m)^##\s*1\..*?\n([\s\S]*?)(?=\n##\s|\Z)", body)
    s1_lines = [ln.strip() for ln in (m_s1.group(1).splitlines() if m_s1 else []) if ln.strip()]
    track_id, active_wo = _val("track_id", fm) or _val("track_id", body), _val("active_wo", fm) or _val("active_wo", body)
    explicit_wos = list(dict.fromkeys(re.findall(r"\bWO-\d+\b", f"{filename}\n{track_id}\n{active_wo}")))
    s1_wos = list(dict.fromkeys(re.findall(r"\bWO-\d+\b", "\n".join(s1_lines))))
    m_bp = re.search(r'(?m)^active_blueprint:\s*["\']?([A-Za-z0-9._-]+)["\']?', f"{fm}\n{body}")
    bp_val = m_bp.group(1).strip() if m_bp else ""
    return {
        "status": _val("status", fm).lower(), "track_id": track_id, "track_status": (_val("track_status", fm) or _val("track_status", body)).lower(),
        "summary_1line": _val("summary_1line", fm), "s1": "\n".join(s1_lines), "s1_first": s1_lines[0] if s1_lines else "",
        "explicit_wo_ids": explicit_wos, "wo_ids": explicit_wos or s1_wos,
        "active_blueprint": "" if bp_val.lower() in {"null", "none", "~"} else bp_val,
        "active_shards": _parse_yaml_list(fm, "active_shards") or _parse_yaml_list(body, "active_shards"),
    }


def _load_codebook_data(root: Path) -> Tuple[str, Dict[str, Any]]:
    idx_file = root / "memory" / "index" / "CONTEXT_INDEX.json"
    if not idx_file.exists(): return "", {}
    try:
        cb = json.loads(idx_file.read_text(encoding="utf-8")).get("codebook_map", {})
        compact = str(cb.get("compact_text") or "").strip() if isinstance(cb, dict) else ""
        return ("", {}) if (compact and scan_plaintext_secrets(compact)) else (compact, cb if isinstance(cb, dict) else {})
    except Exception: return "", {}  # noqa: silent-except


def _load_compact_codebook(root: Path) -> str: return _load_codebook_data(root)[0]


def _agy_tmp_path(root: Path, prefix: str) -> Path:
    return Path(tempfile.gettempdir()) / f"{prefix}_{hashlib.sha256(str(root).encode('utf-8')).hexdigest()[:12]}.json"


def _agy_session_state_path() -> Path: return Path(tempfile.gettempdir()) / "netark_agy_session_state.json"


def _cleanup_legacy_agy_tmp_files() -> None:
    try:
        for p in Path(tempfile.gettempdir()).glob("netark_codebook_state_*.json"): p.unlink(missing_ok=True)
    except Exception: pass  # noqa: silent-except


def queue_agy_post_alert(cwd: str, message: str) -> None:
    """Persist a one-shot PostToolUse alert for AGY PreInvocation to consume."""
    if not (msg := (message or "").strip()): return
    try: _agy_tmp_path(Path(cwd).resolve(), "netark_post_alert").write_text(json.dumps({"message": msg}, ensure_ascii=False), encoding="utf-8")
    except Exception: pass  # noqa: silent-except


def pop_agy_post_alert(cwd: str) -> str:
    """Read and delete any queued PostToolUse alert for this workspace."""
    path = _agy_tmp_path(Path(cwd).resolve(), "netark_post_alert")
    if not path.exists(): return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        path.unlink(missing_ok=True)
        return str(data.get("message") or "").strip() if isinstance(data, dict) else ""
    except Exception: return ""  # noqa: silent-except


def _agy_session_keys(root: Path, payload: Optional[Dict[str, Any]]) -> Tuple[str, str, Optional[int]]:
    rhash, p = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:12], payload if isinstance(payload, dict) else {}
    raw_inv, inv_num = p.get("invocationNum"), None
    if raw_inv not in (None, "") and not isinstance(raw_inv, bool):
        try: inv_num = int(raw_inv)
        except (TypeError, ValueError): pass  # noqa: silent-except
    return rhash, str(p.get("conversationId") or "").strip(), inv_num


def _update_agy_lru(session_key: str, cur_hash: str) -> Tuple[Optional[str], bool]:
    state_file = _agy_session_state_path()
    try:
        raw = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
        data = raw if isinstance(raw, dict) else {}
        raw_order, raw_hashes = (data.get("order") if isinstance(data.get("order"), list) else []), (data.get("hashes") if isinstance(data.get("hashes"), dict) else {})
        prev_hash = raw_hashes.get(session_key) if isinstance(raw_hashes.get(session_key), str) else None
        order = ([k for k in dict.fromkeys(raw_order) if isinstance(k, str) and k != session_key] + [session_key])[-AGY_SESSION_LRU_CAP:]
        keep = set(order)
        hashes = {**{str(k): str(v) for k, v in raw_hashes.items() if k in keep and v is not None}, session_key: cur_hash}
        state_file.write_text(json.dumps({"order": order, "hashes": hashes}), encoding="utf-8")
        return prev_hash, prev_hash != cur_hash
    except Exception: return None, True  # noqa: silent-except


def _codebook_changed_for_agy(root: Path, compact: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[bool, bool]:
    _cleanup_legacy_agy_tmp_files()
    if not compact: return False, False
    cur_hash, (rhash, conv_id, inv_num) = hashlib.sha256(compact.encode("utf-8")).hexdigest()[:16], _agy_session_keys(root, payload)
    if conv_id:
        prev_hash, changed = _update_agy_lru(f"{rhash}:{conv_id}", cur_hash)
        return (True, True) if prev_hash is None else (changed, False)
    if inv_num is not None:
        _, changed = _update_agy_lru(f"{rhash}:__inv__", cur_hash)
        return (True, True) if inv_num == 1 else (changed, False)
    return True, True


def _collect_active_side_tracks(root: Path) -> str:
    """Scan memory/episodic/HANDOVER_*.md (excluding archived/deprecated) for 1-line index."""
    ep_dir = root / "memory" / "episodic"
    if not ep_dir.exists(): return ""
    lines: List[str] = []
    for p in sorted(ep_dir.glob("HANDOVER_*.md")):
        try: txt = p.read_text(encoding="utf-8")
        except Exception: continue  # noqa: silent-except
        if not txt.strip() or scan_plaintext_secrets(txt): continue
        meta = _parse_handover_meta(txt, p.name)
        if meta["status"] in {"archived", "deprecated"}: continue
        tid = meta["track_id"] or re.sub(r"^\d{2}_", "", p.stem.removeprefix("HANDOVER_"))
        lines.append(f"- `{p.name}` (`{tid}`): {(meta['summary_1line'] or meta['s1_first'] or '(active side-track)')[:80]}")
    return "[Active Side-Tracks (Read on demand)]\n" + "\n".join(lines) if lines else ""


def _format_shard_token(shard: str, rev: Dict[str, Any], dir_to_code: Dict[str, str]) -> str:
    meta = rev.get(shard) if isinstance(rev, dict) else None
    if not isinstance(meta, dict): return shard
    code, nkey, st, path = str(meta.get("code") or shard), str(meta.get("node_key") or shard), str(meta.get("status") or "unknown"), str(meta.get("path") or "")
    dcode = dir_to_code.get((str(Path(path).parent) + "/") if path and "/" in path else "", "")
    loc = f"{dcode}:{Path(path).name}" if dcode and path else path
    return f"{code}={loc}[{nkey}|{st}]" if loc else f"{code}[{nkey}|{st}]"


def _expand_active_shards(compact: str, cb: Dict[str, Any], ho_meta: Dict[str, Any]) -> str:
    shards, active_bp = ho_meta.get("active_shards") or [], ho_meta.get("active_blueprint") or ""
    if not shards: return compact
    missing = [s for s in shards if s not in compact]
    if not missing and (not active_bp or active_bp in compact): return compact
    rev, dirs = cb.get("reverse_lookup") or {}, cb.get("dirs") or {}
    d2c = {str(v): str(k) for k, v in dirs.items()} if isinstance(dirs, dict) else {}
    tokens = [_format_shard_token(s, rev, d2c) for s in (missing or shards)]
    bp_part = f"bp={_format_shard_token(active_bp, rev, d2c)} | " if active_bp else ""
    extra = f"[Active Blueprint & Shards] {bp_part}shards: {', '.join(tokens)}"
    if scan_plaintext_secrets(extra): return compact
    if not compact: return extra
    return compact.replace("\n@C ", f"\n  {extra}\n@C ", 1) if "\n@C " in compact else f"{compact}\n{extra}"


def build_session_context(cwd: str, include_handover: bool = True) -> str:
    """Build Turn-1 / Turn-N codebook context and optional handover snapshot."""
    root = Path(cwd).resolve()
    compact, cb = _load_codebook_data(root)
    ho_file, ho_snapshot = root / "memory" / "episodic" / "HANDOVER.md", ""
    if include_handover and ho_file.exists():
        try:
            ho_text = ho_file.read_text(encoding="utf-8")
            compact = _expand_active_shards(compact, cb, _parse_handover_meta(ho_text, "HANDOVER.md"))
            body = re.sub(r"^---\n[\s\S]*?\n---\n", "", ho_text).strip()
            if body and not scan_plaintext_secrets(body):
                ho_snapshot = "### 🔄 [Session Boot Handover Snapshot]\n" + "\n".join(body.splitlines()[:45])
        except Exception: pass  # noqa: silent-except
    parts: List[str] = [p for p in (compact, ho_snapshot) if p]
    if include_handover and (side_idx := _collect_active_side_tracks(root)): parts.append(side_idx)
    return "\n\n".join(parts)


def _read_payload_and_cwd(default_cwd: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    if payload is None:
        raw = sys.stdin.read().strip()
        try: payload = json.loads(raw) if raw else None
        except Exception: payload = None  # noqa: silent-except
    cwd = default_cwd
    if payload and isinstance(payload.get("workspacePaths"), list) and payload["workspacePaths"]:
        wp = str(payload["workspacePaths"][0]).strip()
        if wp and Path(wp).exists(): cwd = wp
    return payload, cwd


def _run_session_start_mode(host: str, default_cwd: str, payload: Optional[Dict[str, Any]] = None) -> int:
    """Inject Turn-1 Codebook Map & Handover into host session context."""
    payload, cwd = _read_payload_and_cwd(default_cwd, payload)
    ctx = build_session_context(cwd)
    if host == "agy":
        _cleanup_legacy_agy_tmp_files()
        if ctx:
            rhash, conv_id, inv_num = _agy_session_keys(root := Path(cwd).resolve(), payload)
            if (conv_id or inv_num is not None) and (compact := _load_compact_codebook(root)):
                _update_agy_lru(f"{rhash}:{conv_id or '__inv__'}", hashlib.sha256(compact.encode("utf-8")).hexdigest()[:16])
        print(json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": ctx}}] if ctx else []}, ensure_ascii=False))
        return 0
    if ctx: print(ctx)
    return 0


def _format_refresh_codebook(compact: str) -> str:
    """F5: tag mid-session refresh header so it is distinguishable from Turn-1 Frozen."""
    if not compact: return ""
    first, sep, rest = re.sub(r"^(## 🧭 \[[^\]]+?)\s+Turn-1 Frozen Codebook Map\]", r"\1 Codebook Map · Refresh]", compact, count=1).partition("\n")
    return f"{first}\n> 🔄 [Codebook Refresh] 本份取代先前 Map，舊短代碼以本份為準。{sep}{rest}"


def _run_pre_invocation_mode(host: str, default_cwd: str, payload: Optional[Dict[str, Any]] = None) -> int:
    """Inject Turn-N systemMessage Codebook Context before model invocation (3-tier/delta for AGY)."""
    payload, cwd = _read_payload_and_cwd(default_cwd, payload)
    if host == "agy":
        compact = _load_compact_codebook(root := Path(cwd).resolve())
        should_inject, is_first = _codebook_changed_for_agy(root, compact, payload)
        msg = (build_session_context(cwd) if is_first else _format_refresh_codebook(compact)) if should_inject else ""
        print(json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": s}} for s in (msg, pop_agy_post_alert(cwd)) if s]}, ensure_ascii=False))
        return 0
    ctx = build_session_context(cwd)
    if host == "claude": print(json.dumps({"additionalContext": ctx} if ctx else {}, ensure_ascii=False))
    elif ctx: print(ctx)
    return 0
