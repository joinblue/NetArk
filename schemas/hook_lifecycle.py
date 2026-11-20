#!/usr/bin/env python3
"""NetArk Hook Lifecycle & Pre-Write Reconstruction Module (hook_lifecycle.py).

Governing Nodes: 100.ARCH-RULES.v1, 200.NETARK-V3-MASTER.v1 & 500.SHARD-HOOK-LIFECYCLE.v1
Exports WRITE_TOOL_NAMES, extract_added_content, reconstruct_post_edit_content,
_check_governance_pre_write, build_session_context, _run_session_start_mode,
and _run_pre_invocation_mode for AGY, Claude, and Pi agents.
"""

from __future__ import annotations

import difflib, fnmatch, hashlib, json, os, re, sys, tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas.code_hygiene_ast import check_python_ast_hygiene, count_effective_code_lines  # noqa: E402
from schemas.netark_guard_core import check_prewrite_secret_lint, load_enterprise_policy, scan_plaintext_secrets  # noqa: E402
from schemas.schema_validator import generate_prescription_skeleton  # noqa: E402
from schemas.workspace_placement_guard import check_spec_blueprint_required, check_spec_filename_format, check_stub_first_gate, parse_frontmatter_text  # noqa: E402

WRITE_TOOL_NAMES = {"write", "edit", "write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content", "multiedit"}


def _extract_chunk_repl(chunk: Any) -> str:
    if not isinstance(chunk, dict): return ""
    return str(chunk.get("ReplacementContent") or chunk.get("replacement") or chunk.get("Replacement") or chunk.get("new_str") or chunk.get("new_string") or "")


def extract_added_content(tool_name: str, args: Dict[str, Any]) -> str:
    """Extract newly added/replaced content string from various agent tool payload schemas."""
    tn = (tool_name or "").lower()
    if tn in {"multi_replace_file_content", "multiedit"}:
        chunks = args.get("ReplacementChunks") or args.get("edits") or []
        return "\n".join(r for c in chunks if (r := _extract_chunk_repl(c))) if isinstance(chunks, list) else ""
    if tn in {"write", "write_file", "write_to_file"}:
        return str(args.get("CodeContent") or args.get("content") or args.get("Content") or args.get("file_text") or "")
    if tn in {"edit", "edit_file", "replace_file_content"}:
        return str(args.get("ReplacementContent") or args.get("replacement") or args.get("Replacement") or args.get("new_str") or args.get("new_string") or "")
    return ""


def _apply_multi_replace(chunks: List[Any], base_text: str, args: Dict[str, Any]) -> Tuple[str, bool]:
    eff_text, matched = base_text, False
    for chunk in chunks:
        if not isinstance(chunk, dict): continue
        tgt = str(chunk.get("TargetContent") or chunk.get("target") or chunk.get("Target") or chunk.get("old_str") or chunk.get("old_string") or "")
        repl = _extract_chunk_repl(chunk)
        allow_m = bool(chunk.get("AllowMultiple") or chunk.get("allow_multiple") or args.get("AllowMultiple") or args.get("allow_multiple"))
        if tgt and tgt in eff_text:
            eff_text, matched = eff_text.replace(tgt, repl, -1 if allow_m else 1), True
    return eff_text, matched


def reconstruct_post_edit_content(tool_name: str, args: Dict[str, Any], target: Path) -> Tuple[str, int, int]:
    """Reconstruct resulting file content, returning (eff_src, old_lines, new_lines)."""
    old_text = ""
    if target.exists():
        try: old_text = target.read_text(encoding="utf-8")
        except Exception: old_text = ""  # noqa: silent-except
    old_lines, tn, added_text = (len(old_text.splitlines()) if old_text else 0), (tool_name or "").lower(), extract_added_content(tool_name, args)
    if tn in {"write", "write_file", "write_to_file"}: eff_src = added_text
    elif tn in {"multi_replace_file_content", "multiedit"}:
        chunks = args.get("ReplacementChunks") or args.get("edits") or []
        eff_text, matched = _apply_multi_replace(chunks if isinstance(chunks, list) else [], old_text, args)
        eff_src = eff_text if matched else added_text
    elif tn in {"edit", "edit_file", "replace_file_content"}:
        old_part = str(args.get("TargetContent") or args.get("target") or args.get("Target") or args.get("old_str") or args.get("old_string") or "")
        eff_src = old_text.replace(old_part, added_text, 1) if (old_part and old_part in old_text) else added_text
    else: eff_src = added_text
    return eff_src, old_lines, (len(eff_src.splitlines()) if eff_src else 0)


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

def _is_ledger_wo_done(ledger_txt: str, wo: str) -> bool:
    wo_re, done_re = re.compile(rf"\b{re.escape(wo)}\b"), re.compile(r"(?i)(?:✅|已完成|\bcompleted\b|\bdone\b|\bverified\b)")
    for ln in ledger_txt.splitlines():
        if not ln.lstrip().startswith("|"): continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 2 and done_re.search(cells[-1]) and wo_re.search(cells[0] if wo_re.search(cells[0]) else " ".join(cells[:-1])): return True
    return False

def _is_handover_closed(meta: Dict[str, Any], root: Path) -> bool:
    """Self-State first (completed/archived), then LEDGER.md WO completion auxiliary check."""
    if meta["status"] in {"archived", "deprecated", "completed"} or meta["track_status"] in {"completed", "archived"}: return True
    use_exp = (meta["track_status"] == "active" or bool(meta.get("track_id")))
    target_wos = list(meta.get("explicit_wo_ids") or ()) if use_exp else list(meta.get("explicit_wo_ids") or meta.get("wo_ids") or ())
    ledger = root / "memory" / "LEDGER.md"
    if not target_wos or not ledger.exists(): return False
    try: ledger_txt = ledger.read_text(encoding="utf-8")
    except Exception: return False  # noqa: silent-except
    return all(_is_ledger_wo_done(ledger_txt, wo) for wo in target_wos)

def _check_handover_overwrite(rel: str, target: Path, eff_src: str, root: Path) -> Optional[Dict[str, Any]]:
    """Block overwriting an active HANDOVER*.md with a different track_id, WO, or §1 topic."""
    if not (rel.startswith("memory/episodic/HANDOVER") and rel.endswith(".md")) or not target.exists(): return None
    try: old_text = target.read_text(encoding="utf-8")
    except Exception: return None  # noqa: silent-except
    if not old_text.strip() or _is_handover_closed((old_meta := _parse_handover_meta(old_text, target.name)), root): return None
    new_meta = _parse_handover_meta(eff_src, target.name)
    old_tid, new_tid = old_meta["track_id"], new_meta["track_id"]
    if old_tid and new_tid and old_tid != new_tid:
        return {"allowed": False, "code": "SEC-HANDOVER-OVERWRITE", "ask_confirmation": True, "reason": f"Active handover '{rel}' (track '{old_tid}') cannot be overwritten by track '{new_tid}' without confirmation."}
    old_wos, new_wos = set(old_meta["wo_ids"]), set(new_meta["wo_ids"])
    if old_meta["track_status"] == "active" and not old_tid and new_tid and not (old_wos & new_wos):
        return {"allowed": False, "code": "SEC-HANDOVER-OVERWRITE", "ask_confirmation": True, "reason": f"Active handover '{rel}' cannot be overwritten by track '{new_tid}' without confirmation."}
    if old_wos and new_wos and not (old_wos & new_wos):
        return {"allowed": False, "code": "SEC-HANDOVER-OVERWRITE", "ask_confirmation": True, "reason": f"Active handover '{rel}' (WO {sorted(old_wos)}) cannot be overwritten by WO {sorted(new_wos)} without confirmation."}
    old_s1, new_s1 = old_meta["s1"], new_meta["s1"]
    if not old_s1 or old_s1 == new_s1 or old_s1 in new_s1 or difflib.SequenceMatcher(None, old_s1, new_s1).ratio() >= 0.45: return None
    return {"allowed": False, "code": "SEC-HANDOVER-OVERWRITE", "ask_confirmation": True, "reason": f"Active handover '{rel}' is not completed/archived; overwriting §1 objective requires confirmation."}


def _is_modularity_exempt(rel: str, exempt_paths: Any) -> bool:
    """Return True if rel matches any exact, directory prefix, or glob entry in modularity_exempt_paths."""
    if not isinstance(exempt_paths, list): return False
    rel_norm = rel.replace("\\", "/").lstrip("./")
    for raw_pat in exempt_paths:
        pat = str(raw_pat or "").strip().replace("\\", "/").lstrip("./")
        if not pat: continue
        if rel_norm == pat or rel_norm.startswith(pat.rstrip("/") + "/") or fnmatch.fnmatch(rel_norm, pat): return True
    return False


def _parse_modularity_limit(policy: Dict[str, Any], key: str, default: int) -> int:
    raw = policy.get(key)
    if raw is None: return default
    try: return int(raw)
    except (TypeError, ValueError): return default


def _check_governance_pre_write(tool_name: str, args: Dict[str, Any], cwd: str) -> Optional[Dict[str, Any]]:
    """Enforce secret lint, doc governance, modularity budget, AST hygiene, and frontmatter."""
    if (tool_name or "").lower() not in WRITE_TOOL_NAMES: return None
    raw_path = str(args.get("path") or args.get("Path") or args.get("file_path") or args.get("TargetFile") or "")
    if not raw_path: return None
    root = Path(cwd).resolve()
    target = (root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
    try: rel = str(target.relative_to(root)).replace("\\", "/")
    except ValueError: return None
    added_text = extract_added_content(tool_name, args)
    eff_src, old_lines, new_lines = reconstruct_post_edit_content(tool_name, args, target)
    if (secret_lint := check_prewrite_secret_lint(added_text or eff_src, target_path=rel, cwd=cwd)): return secret_lint
    if eff_src != added_text and (secret_lint := check_prewrite_secret_lint(eff_src, target_path=rel, cwd=cwd)): return secret_lint
    if (root / "memory" / "codex").exists() and rel.endswith(".md") and "/" not in rel and rel not in {"README.md", "README.zh-TW.md", "AGENTS.md", "CLAUDE.md", "COMMERCIAL-LICENSE.md", "CLA.md"}:
        return {"allowed": False, "code": "SEC-DOC-GOVERNANCE", "reason": f"Unmanaged root markdown '{rel}' is blocked. Place governed specs in memory/specs/ or memory/wiki/."}
    if (spec_err := check_spec_filename_format(rel, cwd)): return spec_err
    mod_warn: Optional[Dict[str, Any]] = None
    if rel.endswith((".py", ".ts")) and not Path(rel).name.startswith("test_"):
        old_text = ""
        if target.exists():
            try: old_text = target.read_text(encoding="utf-8")
            except Exception: old_text = ""  # noqa: silent-except
        ext = Path(rel).suffix
        eff_old, eff_new = count_effective_code_lines(old_text, ext), count_effective_code_lines(eff_src, ext)
        policy = load_enterprise_policy(cwd)
        soft_limit = _parse_modularity_limit(policy, "modularity_soft_limit", 400)
        hard_limit = _parse_modularity_limit(policy, "modularity_hard_limit", 550)
        is_exempt = _is_modularity_exempt(rel, policy.get("modularity_exempt_paths"))
        if not is_exempt and ((eff_new > hard_limit and eff_new > eff_old) or (new_lines > 750 and new_lines > old_lines)):
            return {"allowed": False, "ask_confirmation": True, "code": "MODULARITY-GATE", "reason": f"Anti-God-Script Gate: '{rel}' would reach {eff_new} effective / {new_lines} physical lines (> {hard_limit} effective or > 750 physical limit, delta +{eff_new - eff_old}). Explain your module-splitting plan vs reason for keeping a single file to the human and proceed only after confirmation."}
        if rel.endswith(".py") and (ast_viol := check_python_ast_hygiene(eff_src, rel)): return ast_viol
        if rel.endswith(".py") and (stub_err := check_stub_first_gate(rel, old_text, eff_src, target.exists(), cwd, policy)):
            return stub_err
        if not is_exempt and soft_limit < eff_new <= hard_limit:
            w_msg = f"⚠️ [Modularity Buffer] '{rel}' reached {eff_new} effective / {new_lines} physical lines (> {soft_limit} budget, <= {hard_limit} hard cap). Evaluate module cohesion (do NOT cram logic into upstream callers or compress onto single lines) and present a split vs keep-single-file recommendation to the human."
            queue_agy_post_alert(cwd, w_msg)
            mod_warn = {"allowed": True, "code": "MODULARITY-BUFFER-WARN", "warning": w_msg, "systemMessage": w_msg, "reason": w_msg}
    if os.environ.get("NETARK_MCP_HOOK_MODE") == "1" and rel.startswith("memory/") and rel.endswith(".md") and not rel.endswith("CONTEXT_MAP.md"):
        return {"allowed": False, "code": "MCP-PROB-01-REDIRECT", "reason": f"Direct native write to governed memory '{rel}' is blocked in closed MCP mode. Use MCP tool netark_record(intent=..., title=..., body=..., mode='preflight'|'write')."}
    if rel.startswith("memory/") and rel.endswith(".md") and not rel.endswith("CONTEXT_MAP.md") and not rel.startswith("memory/wiki/"):
        if str(root) in eff_src or str(Path.home()) in eff_src:
            return {"allowed": False, "code": "SEC-PORTABILITY", "reason": f"Machine-specific absolute path detected in governed file '{rel}'. Use workspace-relative paths."}
        if (ho_err := _check_handover_overwrite(rel, target, eff_src, root)):
            return ho_err
        if (tool_name or "").lower() in {"write", "write_file", "write_to_file"} and eff_src.strip() and not eff_src.lstrip().startswith("---"):
            skel = generate_prescription_skeleton(target, root, None)
            return {"allowed": False, "code": "SCHEMA-403-PREFILL", "reason": f"Governed memory node '{rel}' is missing YAML frontmatter (Note: for wiki/sop/glossary/note entries, write to 'memory/wiki/' for auto-header init; for official specs/audits, run `--init` or prepend):\n{skel}"}
    if re.match(r"^(?:memory|projects/[^/]+)/specs/[^/]+\.md$", rel) and eff_src.lstrip().startswith("---"):
        fm_obj, body_txt = parse_frontmatter_text(eff_src)
        if (bp_err := check_spec_blueprint_required(fm_obj, body_txt, rel)):
            return bp_err
    return mod_warn


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

def _codebook_changed_for_agy(root: Path, compact: str) -> bool:
    if not compact: return False
    state_file, cur_hash = _agy_tmp_path(root, "netark_codebook_state"), hashlib.sha256(compact.encode("utf-8")).hexdigest()[:16]
    try:
        if state_file.exists() and json.loads(state_file.read_text(encoding="utf-8")).get("hash") == cur_hash: return False
        state_file.write_text(json.dumps({"hash": cur_hash}), encoding="utf-8")
    except Exception: return True  # noqa: silent-except
    return True

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
        tid = meta["track_id"] or p.stem.removeprefix("HANDOVER_")
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
    _, cwd = _read_payload_and_cwd(default_cwd, payload)
    ctx = build_session_context(cwd)
    if host == "agy": print(json.dumps({"additionalContext": ctx} if ctx else {}, ensure_ascii=False))
    elif ctx: print(ctx)
    return 0

def _run_pre_invocation_mode(host: str, default_cwd: str, payload: Optional[Dict[str, Any]] = None) -> int:
    """Inject Turn-N ephemeral Codebook Context before model invocation (delta-only for AGY)."""
    _, cwd = _read_payload_and_cwd(default_cwd, payload)
    if host == "agy":
        root = Path(cwd).resolve()
        compact = _load_compact_codebook(root)
        steps: List[Dict[str, Any]] = [{"ephemeralMessage": compact}] if _codebook_changed_for_agy(root, compact) else []
        if (post_alert := pop_agy_post_alert(cwd)): steps.append({"ephemeralMessage": post_alert})
        print(json.dumps({"injectSteps": steps}, ensure_ascii=False))
        return 0
    ctx = build_session_context(cwd)
    if host == "claude": print(json.dumps({"additionalContext": ctx} if ctx else {}, ensure_ascii=False))
    elif ctx: print(ctx)
    return 0
