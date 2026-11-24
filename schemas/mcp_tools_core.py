#!/usr/bin/env python3
"""NetArk Closed-Source MCP Tools Core, Preflight/Write Record & Zero-.py Init (mcp_tools_core.py)."""

from __future__ import annotations

import builtins, datetime, json, os, re, sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas import schema_validator as sv  # noqa: E402
from schemas.codebook_compiler import render_context_map, render_private_context_map  # noqa: E402
from schemas.doc_initializer import allocate_next_node_id, collect_existing_topics, normalize_scope_profile, normalize_topic_tag  # noqa: E402
from schemas.guard_slots_and_audit import _resolve_audit_path, verify_enterprise_license  # noqa: E402
from schemas.mcp_record_builder import (  # noqa: E402,F401
    INTENT_ROUTES, _build_record_frontmatter, _dump_yaml_frontmatter, _emit_yaml_lines,
    _resolve_record_target, _validate_path_list, _validate_record_inputs,
)
from schemas.topology_graph import check_topology_graph, load_all_memory_nodes, parse_markdown_frontmatter, query_codebook_entry  # noqa: E402
from scripts.auto_update_map import build_public_and_private_indices, verify_no_plaintext_secrets_before_index_write  # noqa: E402
from scripts.netark_init import CORE_MEMORY_MAP, DEFAULT_ENTERPRISE_POLICY  # noqa: E402
from scripts.sync_doc_metadata import apply_supersedes_transitions  # noqa: E402

MCP_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {"name": "netark_query", "description": "Query map/nodes/topics", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Code/key/topic/bucket: status:reviewing | status:draft | 310:draft | <Topic>"}, "project_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "netark_record", "description": "Record md", "inputSchema": {"type": "object", "properties": {"intent": {"enum": ["wiki", "note", "sop", "glossary", "blueprint", "spec", "audit", "handover"]}, "title": {"type": "string"}, "body": {"type": "string"}, "mode": {"enum": ["preflight", "write"]}, "domain_code": {}, "slug": {}, "topic": {}, "parent_blueprint": {}, "shard_modules": {}, "stub_paths": {}, "scope_profile": {}, "supersedes": {}, "relates_to": {}, "affected_paths": {}}, "required": ["intent", "title", "body"]}},
    {"name": "netark_guard", "description": "Guard/handover/setup (never whole-read CONTEXT_MAP.md past '## 2.')", "inputSchema": {"type": "object", "properties": {"action": {"enum": ["status", "oracle", "handover", "setup"], "description": "handover=tracks/objective; oracle=schema+DAG; status=policy; setup=hooks"}}, "required": ["action"]}},
]


def get_embedded_asset_text(rel_path: str) -> str:
    """Read a template or schema asset from embedded payload first, falling back to repo disk."""
    norm = rel_path.replace("\\", "/").lstrip("./")
    assets = getattr(builtins, "__NETARK_EMBEDDED_ASSETS__", None)
    if isinstance(assets, dict) and norm in assets:
        return str(assets[norm])
    disk_path = Path(__file__).resolve().parents[1] / norm
    if disk_path.is_file():
        return disk_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Asset not found in embedded payload or repo: {norm}")


def _load_embedded_schemas() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return json.loads(get_embedded_asset_text("schemas/artifact_header.schema.json")), json.loads(get_embedded_asset_text("schemas/context_node.schema.json"))


def compile_and_write_indices(root: Path) -> Dict[str, Any]:
    """Compile CONTEXT_INDEX.json, optional private index, and CONTEXT_MAP.md in-process."""
    index, private_index = build_public_and_private_indices(root)
    verify_no_plaintext_secrets_before_index_write(root, index)
    idx_path = root / "memory" / "index" / "CONTEXT_INDEX.json"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    priv_idx, priv_map = root / "memory" / "index" / "PRIVATE_INDEX.json", root / "memory" / "private" / "CONTEXT_MAP.md"
    if private_index.get("total_nodes", 0) > 0:
        priv_idx.write_text(json.dumps(private_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        priv_map.parent.mkdir(parents=True, exist_ok=True)
        priv_map.write_text(render_private_context_map(root, private_index), encoding="utf-8")
    else:
        for p in (priv_idx, priv_map):
            p.unlink(missing_ok=True)
    map_path = root / "memory" / "codex" / "CONTEXT_MAP.md"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(render_context_map(root, index), encoding="utf-8")
    return {"total_nodes": index["total_nodes"], "private_nodes": private_index.get("total_nodes", 0), "map_path": "memory/codex/CONTEXT_MAP.md"}


def _handle_netark_record(args: Dict[str, Any], root: Path, lic: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(args.get("intent") or "").strip().lower()
    if intent not in INTENT_ROUTES:
        return {"ok": False, "errors": [f"Unknown intent '{intent}'."], "prescriptions": ["Use wiki|note|sop|glossary|blueprint|spec|audit|handover."], "license": lic}
    mode, title, body = str(args.get("mode") or "write").strip().lower(), str(args.get("title") or ""), str(args.get("body") or "")
    rel_path, dom, art_type, node_slug = _resolve_record_target(intent, title, str(args.get("slug") or ""), str(args.get("domain_code") or ""), root)
    existing_topics = collect_existing_topics(root)
    raw_topic = str(args.get("topic") or "").strip()
    resolved_topic = normalize_topic_tag(raw_topic, existing_topics, default_topic="Episodic" if art_type == "digest" else "General")
    norm_scope, scope_err = normalize_scope_profile(args.get("scope_profile"))
    counts, prose_lc, budget, errors, prescriptions = _validate_record_inputs(intent, mode, title, body, rel_path, dom, art_type, args.get("affected_paths"), root, args.get("stub_paths"), scope_err, args.get("supersedes"), args.get("shard_modules"), args.get("parent_blueprint"), norm_scope)
    if mode == "preflight" or errors:
        pre: Dict[str, Any] = {"ok": len(errors) == 0, "mode": mode, "target_path": rel_path, "epistemic_profile": counts, "prose_lines": prose_lc, "budget": budget, "existing_topics": existing_topics, "topic": resolved_topic, "errors": errors, "prescriptions": prescriptions, "license": lic}
        if norm_scope is not None: pre["scope_profile"] = norm_scope
        return pre
    body_clean = body.strip("\r\n")
    if not re.search(r"(?m)^#\s+", body_clean):
        body_clean = f"# {title.strip()}\n\n{body_clean}"
    body_clean += "\n"
    node_id = allocate_next_node_id(root / "memory")
    fm = _build_record_frontmatter(node_id, art_type, dom, node_slug, title, rel_path, sv.compute_body_checksum(body_clean), counts, body_clean, args.get("relates_to"), args.get("affected_paths"), root, args.get("stub_paths"), resolved_topic, bool(raw_topic), args.get("parent_blueprint"), args.get("shard_modules"), args.get("supersedes"), norm_scope)
    target_path = root / rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existed, tmp_path = target_path.exists(), target_path.with_name(f".{target_path.name}.tmp")
    tmp_path.write_text(_dump_yaml_frontmatter(fm) + "\n" + body_clean, encoding="utf-8")
    os.replace(tmp_path, target_path)
    apply_supersedes_transitions(fm, root, today_str=fm["updated_at"])
    hdr_sch, nod_sch = _load_embedded_schemas()
    _, val_errs = sv.validate_document(target_path, root, hdr_sch, nod_sch, run_oracle=False)
    if val_errs:
        if not existed: target_path.unlink(missing_ok=True)
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
        if fm and "node_id" in fm:
            validated[fm["node_id"]] = fm
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
            except Exception as exc:
                handovers.append({"path": str(p.relative_to(root)), "error": str(exc)})
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
            except Exception as exc:
                policy_info = {"found": True, "path": str(cand.relative_to(root)), "error": str(exc)}
            break
    audit_path = _resolve_audit_path(cwd)
    entries = len([ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]) if audit_path.is_file() else 0
    return {"ok": True, "action": "status", "license": lic, "policy": policy_info, "audit_log": {"path": str(audit_path), "exists": audit_path.is_file(), "entries": entries}}


def execute_netark_query(root: Path, query: str, project_id: str = "") -> Dict[str, Any]:
    """Execute on-demand codebook, blueprint shard, or topic query via topology_graph."""
    res = query_codebook_entry(root, query)
    if project_id and isinstance(res, dict):
        res.setdefault("project_id", project_id)
    return res


def handle_mcp_tool_call(name: str, arguments: Dict[str, Any], cwd: str) -> Dict[str, Any]:
    """Dispatch netark_query, netark_record, and netark_guard MCP tool invocations."""
    root, args, lic = Path(cwd).resolve(), (arguments if isinstance(arguments, dict) else {}), verify_enterprise_license()
    if name == "netark_query": return {**execute_netark_query(root, str(args.get("query") or ""), str(args.get("project_id") or "")), "license": lic}
    if name == "netark_record": return _handle_netark_record(args, root, lic)
    if name == "netark_guard": return _handle_netark_guard(args, root, cwd, lic)
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


def _mcp_server_entry(bin_cmd: str, include_env: bool = True) -> Dict[str, Any]:
    return {"command": bin_cmd, "args": ["serve"], **({"env": {"NETARK_LICENSE_KEY": "${NETARK_LICENSE_KEY}", "NETARK_MEMORY_ROOT": "${NETARK_MEMORY_ROOT}"}} if include_env else {})}


def _merge_mcp_netark(cfg: Dict[str, Any], bin_cmd: str, include_env: bool = True) -> None:
    if not isinstance(cfg.get("mcpServers"), dict): cfg["mcpServers"] = {}
    servers, entry = cfg["mcpServers"], _mcp_server_entry(bin_cmd, include_env=include_env)
    if isinstance((old := servers.get("netark")), dict) and isinstance(old.get("env"), dict):
        if include_env: entry["env"] = {**entry["env"], **old["env"]}
        elif (kept := {k: v for k, v in old["env"].items() if v not in ("${NETARK_LICENSE_KEY}", "${NETARK_MEMORY_ROOT}")}): entry["env"] = kept
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
        agy_guard = {
            "enabled": True, "SessionStart": [{"type": "command", "command": f"{bin_cmd} hook --session-start-mode agy --cwd .", "timeout": 5}], "PreInvocation": [{"type": "command", "command": f"{bin_cmd} hook --pre-invocation-mode agy --cwd .", "timeout": 5}],
            "PreToolUse": [{"matcher": "read_file|view_file|write_file|edit_file|multiedit|write_to_file|replace_file_content|multi_replace_file_content|run_command|bash|invoke_subagent|Agent|Task|subagent|dispatch_specialist|search_web|read_url_content|web_fetch|http_request|web_research", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --hook-mode agy --cwd .", "timeout": 5}]}],
            "PostToolUse": [{"matcher": "write_file|edit_file|multiedit|write_to_file|replace_file_content|multi_replace_file_content", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --post-hook-mode agy --cwd .", "timeout": 10}]}],
            "Stop": [{"type": "command", "command": f"{bin_cmd} hook --stop-mode agy --cwd .", "timeout": 10}],
        }
        _merge_json_file(root / ".agents" / "hooks.json", lambda c: (c.pop("netark-v3-session-init", None), c.pop("netark-v3-guard", None), c.__setitem__("netark-enterprise-guard", agy_guard)) and None)
        _merge_json_file(root / ".agents" / "plugins" / "netark" / "plugin.json", lambda c: c.setdefault("name", "netark") and None)
        _merge_json_file(root / ".agents" / "plugins" / "netark" / "mcp_config.json", lambda c: _merge_mcp_netark(c, bin_cmd))
        if write_rules or update_rules: _copy_asset_if_needed("templates/hosts/agy/AGENTS.md.tpl", root / "AGENTS.md", overwrite=update_rules)
    if "claude" in targets:
        cls_hooks = {"SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --session-start-mode claude --cwd ."}]}],
                     "PreToolUse": [{"matcher": "Bash|Write|Edit|MultiEdit|Read|Task|Agent|WebFetch", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --hook-mode claude --cwd ."}]}],
                     "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --post-hook-mode claude --cwd ."}]}],
                     "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --stop-mode claude --cwd ."}]}]}
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
    for tmpl_name, dest_rel in CORE_MEMORY_MAP:
        dst = root / dest_rel
        if dst.exists(): continue
        raw = get_embedded_asset_text(f"templates/memory/{lang}/{tmpl_name}").replace("2026-11-08", today)
        if not has_py_core: raw = re.sub(r'(?m)^  affected_paths:\n    - "(?:schemas|scripts)/[^"]+"\n', "  affected_paths: []\n", raw)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(raw, encoding="utf-8")
        created.append(dest_rel)
    compile_and_write_indices(root)
    return {"status": "ok", "workspace": str(root), "targets": targets, "lang": lang, "enterprise_policy": f"{pol_dir}/enterprise-policy.json", "bootstrapped_memory_nodes": created}
