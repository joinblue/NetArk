#!/usr/bin/env python3
"""NetArk Closed-Source MCP Tools Core, Preflight/Write Record & Zero-.py Init (mcp_tools_core.py)."""

from __future__ import annotations

import builtins, datetime, json, os, re, sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas import schema_validator as sv  # noqa: E402
from schemas.codebook_compiler import render_context_map, render_private_context_map  # noqa: E402
from schemas.doc_initializer import (  # noqa: E402
    allocate_next_node_id, collect_existing_node_ids_and_keys, collect_existing_topics,
    normalize_scope_profile, normalize_topic_tag, render_core_memory_template,
)
from schemas.guard_slots_and_audit import _resolve_audit_path, verify_enterprise_license  # noqa: E402
from schemas.mcp_record_builder import (  # noqa: E402,F401
    INTENT_ROUTES, _build_record_frontmatter, _dump_yaml_frontmatter, _emit_yaml_lines,
    _load_existing_frontmatter, _merge_existing_record_args, _prepare_record_body,
    _resolve_record_target, _validate_path_list, _validate_record_inputs, collect_spec_negative_warnings,
)
from schemas.topology_graph import check_topology_graph, load_all_memory_nodes, parse_markdown_frontmatter, query_codebook_entry  # noqa: E402
from scripts.auto_update_map import build_public_and_private_indices, verify_no_plaintext_secrets_before_index_write  # noqa: E402
from scripts.netark_init import CORE_MEMORY_MAP, DEFAULT_ENTERPRISE_POLICY  # noqa: E402
from scripts.sync_doc_metadata import apply_supersedes_transitions, load_all_node_paths, sync_auto_ledger  # noqa: E402

MCP_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {"name": "netark_query", "description": "Call FIRST before reading files or guessing paths. Resolves abbreviated codebook IDs (e.g. '310.18' -> exact '*_NOTE.md' path; 'C15' -> file path + exact function line_start/line_end), status buckets ('status:reviewing'|'status:draft'|'310:draft'), topics, or 1-hop AST impact. Use returned path & line ranges for sliced reads instead of whole-file reads.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Code/key/topic/bucket: '310.18' | 'C15' | 'status:reviewing' | 'status:draft' | '310:draft' | '<Topic>'"}, "project_id": {"type": "string"}}, "required": ["query"]}, "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "netark_record", "description": "REQUIRED for ALL creating/updating of memory/**/*.md files (NEVER raw-write memory files). Pass optional target_path to update existing memory/**/*.md in-place. Run mode='preflight' first to validate schema, paths, and epistemic tags, then mode='write' to persist and auto-refresh CONTEXT_MAP.md.", "inputSchema": {"type": "object", "properties": {"intent": {"enum": ["wiki", "note", "sop", "glossary", "blueprint", "spec", "audit", "handover"]}, "title": {"type": "string"}, "body": {"type": "string"}, "mode": {"enum": ["preflight", "write"]}, "target_path": {"type": "string"}, "domain_code": {}, "slug": {}, "topic": {}, "parent_blueprint": {}, "shard_modules": {}, "stub_paths": {}, "scope_profile": {}, "supersedes": {}, "relates_to": {}, "affected_paths": {}}, "required": ["intent", "title", "body"]}, "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "netark_guard", "description": "Read-only governance diagnostics (NEVER whole-read CONTEXT_MAP.md past '## 2.'). Use 'handover' BEFORE triaging memory for active tracks/objective; 'oracle' after multi-file/spec edits for full schema+DAG check; 'status' for policy/license/dashboard URL; 'setup' for host hook CLI contract.", "inputSchema": {"type": "object", "properties": {"action": {"enum": ["status", "oracle", "handover", "setup"], "description": "handover=tracks/objective; oracle=schema+DAG; status=policy/dashboard; setup=hook contract"}}, "required": ["action"]}, "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
]


def get_embedded_asset_text(rel_path: str) -> str:
    """Read a template or schema asset from embedded payload first, falling back to repo disk."""
    norm = rel_path.replace("\\", "/").lstrip("./")
    assets = getattr(builtins, "__NETARK_EMBEDDED_ASSETS__", None)
    if isinstance(assets, dict) and norm in assets: return str(assets[norm])
    disk_path = Path(__file__).resolve().parents[1] / norm
    if disk_path.is_file(): return disk_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Asset not found in embedded payload or repo: {norm}")


def _load_embedded_schemas() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return json.loads(get_embedded_asset_text("schemas/artifact_header.schema.json")), json.loads(get_embedded_asset_text("schemas/context_node.schema.json"))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def compile_and_write_indices(root: Path) -> Dict[str, Any]:
    """Compile CONTEXT_INDEX.json, optional private index, and CONTEXT_MAP.md in-process."""
    sync_auto_ledger(root)
    index, private_index = build_public_and_private_indices(root)
    verify_no_plaintext_secrets_before_index_write(root, index)
    _atomic_write_text(root / "memory" / "index" / "CONTEXT_INDEX.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    priv_idx, priv_map = root / "memory" / "index" / "PRIVATE_INDEX.json", root / "memory" / "private" / "CONTEXT_MAP.md"
    if private_index.get("total_nodes", 0) > 0:
        _atomic_write_text(priv_idx, json.dumps(private_index, ensure_ascii=False, indent=2) + "\n")
        _atomic_write_text(priv_map, render_private_context_map(root, private_index))
    else:
        for p in (priv_idx, priv_map): p.unlink(missing_ok=True)
    _atomic_write_text(root / "memory" / "codex" / "CONTEXT_MAP.md", render_context_map(root, index))
    return {"total_nodes": index["total_nodes"], "private_nodes": private_index.get("total_nodes", 0), "map_path": "memory/codex/CONTEXT_MAP.md"}


def _snapshot_superseded_files(fm: Dict[str, Any], root: Path) -> Dict[Path, bytes]:
    sup_refs = (fm.get("topology") or {}).get("supersedes") or []
    if not sup_refs: return {}
    id_to_path, key_to_id, _ = load_all_node_paths(root)
    backups: Dict[Path, bytes] = {}
    for ref in sup_refs:
        tid = ref if ref in id_to_path else key_to_id.get(ref)
        if tid and (p := id_to_path.get(tid)) and p.is_file(): backups[p] = p.read_bytes()
    return backups


def _restore_file_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_and_validate_record(target_path: Path, existed: bool, rendered: str, fm: Dict[str, Any], root: Path) -> List[str]:
    orig_bytes, sup_backups = (target_path.read_bytes() if existed else None), _snapshot_superseded_files(fm, root)
    _atomic_write_text(target_path, rendered)
    apply_supersedes_transitions(fm, root, today_str=fm["updated_at"])
    hdr_sch, nod_sch = _load_embedded_schemas()
    _, val_errs = sv.validate_document(target_path, root, hdr_sch, nod_sch, run_oracle=False)
    if not val_errs: return []
    if existed and orig_bytes is not None: _restore_file_bytes(target_path, orig_bytes)
    else: target_path.unlink(missing_ok=True)
    for sp, sbytes in sup_backups.items(): _restore_file_bytes(sp, sbytes)
    return val_errs


def _handle_netark_record(args: Dict[str, Any], root: Path, lic: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(args.get("intent") or "").strip().lower()
    if intent not in INTENT_ROUTES:
        return {"ok": False, "errors": [f"Unknown intent '{intent}'."], "prescriptions": ["Use wiki|note|sop|glossary|blueprint|spec|audit|handover."], "license": lic}
    mode, title, body = str(args.get("mode") or "write").strip().lower(), str(args.get("title") or ""), str(args.get("body") or "")
    target_path_arg = str(args.get("target_path") or "")
    rel_path, dom, art_type, node_slug = _resolve_record_target(intent, title, str(args.get("slug") or ""), str(args.get("domain_code") or ""), root, target_path=target_path_arg)
    existed, existing_fm = _load_existing_frontmatter(root, rel_path)
    existing_topics, raw_topic = collect_existing_topics(root), str(args.get("topic") or "").strip()
    norm_scope, scope_err = normalize_scope_profile(args.get("scope_profile"))
    eff_dom, eff_art, eff_aff, eff_stub, eff_pb, eff_shards, eff_sups, eff_scope = _merge_existing_record_args(args, dom, art_type, norm_scope, existing_fm)
    resolved_topic = normalize_topic_tag(raw_topic, existing_topics, default_topic="Episodic" if eff_art == "digest" else "General")
    counts, prose_lc, budget, errors, prescriptions = _validate_record_inputs(intent, mode, title, body, rel_path, eff_dom, eff_art, eff_aff, root, eff_stub, scope_err, eff_sups, eff_shards, eff_pb, eff_scope, target_path=target_path_arg)
    body_clean, existing_nid = _prepare_record_body(title, body), (str(existing_fm.get("node_id") or "") if isinstance(existing_fm, dict) else "")
    is_ho = rel_path.startswith("memory/episodic/HANDOVER") and rel_path.endswith(".md")
    if not errors and is_ho:
        fm_prev = _build_record_frontmatter(existing_nid or "MEM-0000-0000", eff_art, eff_dom, node_slug, title, rel_path, sv.compute_body_checksum(body_clean), counts, body_clean, args.get("relates_to"), args.get("affected_paths"), root, args.get("stub_paths"), resolved_topic, bool(raw_topic), args.get("parent_blueprint"), args.get("shard_modules"), args.get("supersedes"), norm_scope, existing_fm=existing_fm)
        hdr_text = _dump_yaml_frontmatter(fm_prev)
        hdr_lines, total_lines = len(hdr_text.splitlines()), len((hdr_text + body_clean).splitlines())
        budget = max(0, 65 - hdr_lines)
        if total_lines > 65:
            errors.append(f"[ProseBudget / HANDOVER] Total rendered file ({total_lines} lines = {hdr_lines} frontmatter + {len(body_clean.splitlines())} body) exceeds 65-line limit (max body lines: {budget}).")
            prescriptions.append("Trim handover body so frontmatter + body stays <= 65 total lines.")
    warnings = collect_spec_negative_warnings(intent, body)
    if mode == "preflight" or errors:
        pre: Dict[str, Any] = {"ok": len(errors) == 0, "mode": mode, "target_path": rel_path, "epistemic_profile": counts, "prose_lines": prose_lc, "budget": budget, "existing_topics": existing_topics, "topic": resolved_topic, "errors": errors, "prescriptions": prescriptions, "license": lic}
        if norm_scope is not None: pre["scope_profile"] = norm_scope
        if warnings: pre["warnings"] = warnings
        return pre
    node_id = existing_nid or allocate_next_node_id(root / "memory")
    fm = _build_record_frontmatter(node_id, art_type, dom, node_slug, title, rel_path, sv.compute_body_checksum(body_clean), counts, body_clean, args.get("relates_to"), args.get("affected_paths"), root, args.get("stub_paths"), resolved_topic, bool(raw_topic), args.get("parent_blueprint"), args.get("shard_modules"), args.get("supersedes"), norm_scope, existing_fm=existing_fm)
    rendered = _dump_yaml_frontmatter(fm) + ("" if is_ho else "\n") + body_clean
    if (val_errs := _write_and_validate_record(root / rel_path, existed, rendered, fm, root)):
        return {"ok": False, "mode": "write", "target_path": rel_path, "errors": val_errs, "prescriptions": ["Fix validation errors and retry."], "license": lic}
    compile_and_write_indices(root)
    return {"ok": True, "mode": "write", "node_id": node_id, "node_key": fm["context_index"]["node_key"], "target_path": rel_path, "status": fm["status"], "topic": resolved_topic, "epistemic_profile": counts, "license": lic}


def _guard_oracle_check(root: Path, lic: Dict[str, Any]) -> Dict[str, Any]:
    hdr_sch, nod_sch = _load_embedded_schemas()
    mem_dir = root / "memory"
    md_files = sorted(p for p in mem_dir.rglob("*.md") if p.name != "CONTEXT_MAP.md") if mem_dir.exists() else []
    all_nodes, passed_cnt, failed, validated = load_all_memory_nodes(root), 0, [], {}
    for md_file in md_files:
        rel = str(md_file.relative_to(root)).replace("\\", "/")
        fm, errs = sv.validate_document(md_file, root, hdr_sch, nod_sch, run_oracle=False, all_nodes=all_nodes)
        if fm and "node_id" in fm: validated[fm["node_id"]] = fm
        failed.append({"path": rel, "errors": errs}) if errs else (passed_cnt := passed_cnt + 1)
    topo_errs = check_topology_graph(validated) if validated else []
    return {"ok": len(failed) == 0 and len(topo_errs) == 0, "action": "oracle", "passed": passed_cnt, "failed": failed, "topology_errors": topo_errs, "license": lic}


def _guard_handover_summary(root: Path, lic: Dict[str, Any]) -> Dict[str, Any]:
    ep_dir, handovers = root / "memory" / "episodic", []
    if ep_dir.is_dir():
        for p in sorted(ep_dir.glob("HANDOVER*.md")):
            try:
                fm, _ = parse_markdown_frontmatter(p)
                handovers.append({"path": str(p.relative_to(root)), "node_id": fm.get("node_id"), "status": fm.get("status"), "track_id": fm.get("track_id"), "summary_1line": fm.get("context_index", {}).get("summary_1line", ""), "lines": len(p.read_text(encoding="utf-8").splitlines())})
            except Exception as exc: handovers.append({"path": str(p.relative_to(root)), "error": str(exc)})
    ledger_p = root / "memory" / "LEDGER.md"
    return {"ok": True, "action": "handover", "handovers": handovers, "ledger": {"exists": ledger_p.exists(), "lines": len(ledger_p.read_text(encoding="utf-8").splitlines()) if ledger_p.exists() else 0}, "license": lic}


def _handle_netark_guard(args: Dict[str, Any], root: Path, cwd: str, lic: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "status").strip().lower()
    if action == "oracle": return _guard_oracle_check(root, lic)
    if action == "handover": return _guard_handover_summary(root, lic)
    if action == "setup": return {"ok": True, "action": "setup", "contract": get_embedded_asset_text("templates/mcp/HOOK_CONTRACT.md"), "license": lic}
    if action != "status": return {"ok": False, "error": f"Unknown guard action '{action}'.", "license": lic}
    policy_info: Dict[str, Any] = {"found": False}
    for cand in (root / ".agents" / "enterprise-policy.json", root / ".netark" / "enterprise-policy.json", root / "enterprise-policy.json"):
        if cand.is_file():
            try:
                pdata = json.loads(cand.read_text(encoding="utf-8"))
                policy_info = {"found": True, "path": str(cand.relative_to(root)), "schema_version": pdata.get("schema_version"), "protected_paths": pdata.get("protected_paths", [])}
            except Exception as exc: policy_info = {"found": True, "path": str(cand.relative_to(root)), "error": str(exc)}
            break
    audit_path = _resolve_audit_path(cwd)
    entries = len([ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]) if audit_path.is_file() else 0
    return {"ok": True, "action": "status", "license": lic, "policy": policy_info, "audit_log": {"path": str(audit_path), "exists": audit_path.is_file(), "entries": entries}, "dashboard_url": os.environ.get("NETARK_ACTIVE_DASHBOARD_URL") or None}


def execute_netark_query(root: Path, query: str, project_id: str = "") -> Dict[str, Any]:
    """Execute on-demand codebook, blueprint shard, or topic query via topology_graph."""
    res = query_codebook_entry(root, query)
    if project_id and isinstance(res, dict):
        res.setdefault("project_id", project_id)
    return res


def resolve_mcp_workspace_root(cwd: str) -> Path:
    """Resolve workspace root for MCP server, honoring NETARK_MEMORY_ROOT and escaping host plugin dirs."""
    raw = (cwd or "").strip()
    if raw in ("", ".") and (env_root := os.environ.get("NETARK_MEMORY_ROOT", "").strip()) and "${" not in env_root:
        return Path(env_root).expanduser().resolve()
    cand = Path(raw or ".").resolve()
    parts = cand.parts
    for idx in range(len(parts) - 1):
        if parts[idx] == ".agents" and parts[idx + 1] == "plugins":
            return Path(*parts[:idx]).resolve() if idx > 0 else cand
    if cand.name in (".agents", ".claude", ".pi", ".netark") and (cand.parent / "memory").is_dir(): return cand.parent
    return cand


def handle_mcp_tool_call(name: str, arguments: Dict[str, Any], cwd: str) -> Dict[str, Any]:
    """Dispatch netark_query, netark_record, and netark_guard MCP tool invocations."""
    root, args, lic = resolve_mcp_workspace_root(cwd), (arguments if isinstance(arguments, dict) else {}), verify_enterprise_license()
    if name == "netark_query": return {**execute_netark_query(root, str(args.get("query") or ""), str(args.get("project_id") or "")), "license": lic}
    if name == "netark_record": return _handle_netark_record(args, root, lic)
    if name == "netark_guard": return _handle_netark_guard(args, root, str(root), lic)
    return {"ok": False, "error": f"Unknown tool: {name}", "license": lic}


def _merge_json_file(path: Path, updater: Callable[[Dict[str, Any]], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict): existing = loaded
        except Exception: existing = {}
    updater(existing)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_asset_if_needed(asset_rel: str, dest_path: Path, overwrite: bool = False) -> None:
    if dest_path.exists() and not overwrite: return
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(get_embedded_asset_text(asset_rel), encoding="utf-8")


def _mcp_server_entry(bin_cmd: str, include_env: bool = True, agy_eager: bool = False) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"command": bin_cmd, "args": ["serve"]}
    if include_env: entry["env"] = {"NETARK_LICENSE_KEY": "${NETARK_LICENSE_KEY}", "NETARK_MEMORY_ROOT": "${NETARK_MEMORY_ROOT}"}
    if agy_eager: entry["tools"] = {t: {"eager": True} for t in ("netark_query", "netark_record", "netark_guard")}
    return entry


def _merge_mcp_netark(cfg: Dict[str, Any], bin_cmd: str, include_env: bool = True, agy_eager: bool = False) -> None:
    if not isinstance(cfg.get("mcpServers"), dict): cfg["mcpServers"] = {}
    servers, entry = cfg["mcpServers"], _mcp_server_entry(bin_cmd, include_env=include_env, agy_eager=agy_eager)
    if isinstance((old := servers.get("netark")), dict):
        if isinstance(old.get("env"), dict):
            if include_env: entry["env"] = {**entry["env"], **old["env"]}
            elif (kept := {k: v for k, v in old["env"].items() if v not in ("${NETARK_LICENSE_KEY}", "${NETARK_MEMORY_ROOT}")}): entry["env"] = kept
        if agy_eager and isinstance(old.get("tools"), dict): entry["tools"] = {**entry["tools"], **old["tools"]}
    servers["netark"] = entry


def _list_asset_rels(prefix: str) -> List[str]:
    norm, base = prefix.replace("\\", "/").strip("/") + "/", Path(__file__).resolve().parents[1]
    if isinstance((assets := getattr(builtins, "__NETARK_EMBEDDED_ASSETS__", None)), dict): return sorted(k for k in assets if k.startswith(norm))
    return sorted(str(p.relative_to(base)).replace("\\", "/") for p in (base / norm.rstrip("/")).rglob("*") if p.is_file()) if (base / norm.rstrip("/")).is_dir() else []


def _merge_claude_hooks(cfg: Dict[str, Any], cls_hooks: Dict[str, Any]) -> None:
    if not isinstance(cfg.get("hooks"), dict): cfg["hooks"] = {}
    hooks = cfg["hooks"]
    for ev, entries in cls_hooks.items():
        hooks[ev] = [x for x in (hooks.get(ev) if isinstance(hooks.get(ev), list) else []) if "netark-mcp hook" not in json.dumps(x)] + entries


def _configure_closed_hosts(root: Path, targets: List[str], bin_cmd: str, write_rules: bool = False, update_rules: bool = False, pi_brain_dir: str = ".pi") -> None:
    if "agy" in targets:
        agy_guard = {"enabled": True, "SessionStart": [{"type": "command", "command": f"{bin_cmd} hook --session-start-mode agy --cwd .", "timeout": 5}], "PreInvocation": [{"type": "command", "command": f"{bin_cmd} hook --pre-invocation-mode agy --cwd .", "timeout": 5}],
                     "PreToolUse": [{"matcher": "read_file|view_file|write_file|edit_file|multiedit|write_to_file|replace_file_content|multi_replace_file_content|run_command|bash|invoke_subagent|Agent|Task|subagent|dispatch_specialist|search_web|read_url_content|web_fetch|http_request|web_research", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --hook-mode agy --cwd .", "timeout": 5}]}],
                     "PostToolUse": [{"matcher": "write_file|edit_file|multiedit|write_to_file|replace_file_content|multi_replace_file_content", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --post-hook-mode agy --cwd .", "timeout": 10}]}],
                     "Stop": [{"type": "command", "command": f"{bin_cmd} hook --stop-mode agy --cwd .", "timeout": 10}]}
        _merge_json_file(root / ".agents" / "hooks.json", lambda c: (c.pop("netark-v3-session-init", None), c.pop("netark-v3-guard", None), c.__setitem__("netark-enterprise-guard", agy_guard)) and None)
        _merge_json_file(root / ".agents" / "plugins" / "netark" / "plugin.json", lambda c: c.setdefault("name", "netark") and None)
        _merge_json_file(root / ".agents" / "plugins" / "netark" / "mcp_config.json", lambda c: _merge_mcp_netark(c, bin_cmd, agy_eager=True))
        if write_rules or update_rules: _copy_asset_if_needed("templates/hosts/agy/AGENTS.md.tpl", root / "AGENTS.md", overwrite=update_rules)
    if "claude" in targets:
        cls_hooks = {"SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --session-start-mode claude --cwd ."}]}], "PreToolUse": [{"matcher": "Bash|Write|Edit|MultiEdit|Read|Task|Agent|WebFetch", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --hook-mode claude --cwd ."}]}], "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --post-hook-mode claude --cwd ."}]}], "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --stop-mode claude --cwd ."}]}]}
        _merge_json_file(root / ".claude" / "settings.json", lambda c: _merge_claude_hooks(c, cls_hooks))
        if write_rules or update_rules: _copy_asset_if_needed("templates/hosts/claude/CLAUDE.md.tpl", root / "CLAUDE.md", overwrite=update_rules)
    if "pi" in targets:
        _merge_json_file(root / pi_brain_dir / "mcp.json", lambda c: _merge_mcp_netark(c, bin_cmd, include_env=False))
        for rel in _list_asset_rels("templates/hosts/pi"):
            if (sub := rel[len("templates/hosts/pi/"):]) == "enterprise-policy.json.tpl": continue
            _copy_asset_if_needed(rel, root / pi_brain_dir / (dsub := sub[:-4] if sub.endswith(".tpl") else sub), overwrite=update_rules and dsub not in ("settings.json", "role-models.json", "custom-models.json"))
        for rel in _list_asset_rels("templates/skills"): _copy_asset_if_needed(rel, root / pi_brain_dir / "skills" / rel[len("templates/skills/"):], overwrite=update_rules)
        if update_rules: (root / pi_brain_dir / "extensions" / "session-handover.ts").unlink(missing_ok=True)
        if write_rules or update_rules: _copy_asset_if_needed("templates/hosts/pi/AGENTS.md.tpl", root / "AGENTS.md", overwrite=update_rules)


def run_closed_mcp_init(cwd: str, target: str = "memory", lang: str = "zh-TW", bin_cmd: str = "netark-mcp", update_rules: bool = False, write_rules: bool = False, brain_dir: str = "") -> Dict[str, Any]:
    """Initialize a target project in closed-source MCP mode with 0 .py files written."""
    root = Path(cwd).resolve()
    for sub in ("memory/codex", "memory/episodic", "memory/specs", "memory/wiki", "memory/audits", "memory/index", "memory/private", "projects", "scratch"): (root / sub).mkdir(parents=True, exist_ok=True)
    pi_brain = brain_dir.strip() or (".netark" if (root / ".netark" / "enterprise-policy.json").is_file() else ".pi")
    pol_dir = next((d for d in (".agents", ".netark", ".pi") if (root / d / "enterprise-policy.json").is_file()), ".agents" if target == "agy" else (pi_brain if target == "pi" else ".netark"))
    _merge_json_file(root / pol_dir / "enterprise-policy.json", lambda d: d.update({**DEFAULT_ENTERPRISE_POLICY, **d}))
    targets = ["agy", "claude", "pi"] if target == "all" else ([] if target == "memory" else [target])
    if target in ("memory", "claude", "all"): _merge_json_file(root / ".mcp.json", lambda c: _merge_mcp_netark(c, bin_cmd))
    _configure_closed_hosts(root, targets, bin_cmd, write_rules=write_rules, update_rules=update_rules, pi_brain_dir=pi_brain)
    _copy_asset_if_needed("memory/index/TAXONOMY.json", root / "memory" / "index" / "TAXONOMY.json")
    today, created, has_py_core = datetime.date.today().isoformat(), [], (root / "schemas" / "schema_validator.py").exists()
    used_ids, used_keys = collect_existing_node_ids_and_keys(root / "memory")
    for tmpl_name, dest_rel in CORE_MEMORY_MAP:
        dst = root / dest_rel
        if dst.exists(): continue
        raw = render_core_memory_template(get_embedded_asset_text(f"templates/memory/{lang}/{tmpl_name}"), root / "memory", today, used_ids, used_keys)
        if raw is None: continue
        if not has_py_core: raw = re.sub(r'(?m)^  affected_paths:\n    - "(?:schemas|scripts)/[^"]+"\n', "  affected_paths: []\n", raw)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(raw, encoding="utf-8")
        created.append(dest_rel)
    compile_and_write_indices(root)
    return {"status": "ok", "workspace": str(root), "targets": targets, "lang": lang, "enterprise_policy": f"{pol_dir}/enterprise-policy.json", "bootstrapped_memory_nodes": created}
