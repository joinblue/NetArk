#!/usr/bin/env python3
"""NetArk Closed-Source MCP Tools Core, Preflight/Write Record & Zero-.py Init (mcp_tools_core.py)."""

from __future__ import annotations

import builtins, datetime, hashlib, json, os, re, sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas import schema_validator as sv  # noqa: E402
from schemas.code_hygiene_ast import verify_spec_ast_symbols  # noqa: E402
from schemas.codebook_compiler import render_context_map, render_private_context_map  # noqa: E402
from schemas.doc_initializer import allocate_next_node_id, collect_existing_topics, default_lifecycle_status, normalize_scope_profile, normalize_topic_tag  # noqa: E402
from schemas.netark_guard_core import check_prewrite_secret_lint  # noqa: E402
from schemas.topology_graph import check_topology_graph, load_all_memory_nodes, parse_markdown_frontmatter, query_codebook_entry  # noqa: E402
from schemas.workspace_placement_guard import check_spec_blueprint_required, check_spec_filename_format  # noqa: E402
from scripts.auto_update_map import build_public_and_private_indices, extract_wikilinks_outside_fenced_blocks, verify_no_plaintext_secrets_before_index_write  # noqa: E402
from scripts.netark_guard_daemon import _resolve_audit_path, verify_enterprise_license  # noqa: E402
from scripts.netark_init import CORE_MEMORY_MAP, DEFAULT_ENTERPRISE_POLICY  # noqa: E402
from scripts.sync_doc_metadata import apply_supersedes_transitions  # noqa: E402

MCP_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {"name": "netark_query", "description": "Query map", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "project_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "netark_record", "description": "Record md", "inputSchema": {"type": "object", "properties": {"intent": {"enum": ["wiki", "note", "sop", "glossary", "blueprint", "spec", "audit", "handover"]}, "title": {"type": "string"}, "body": {"type": "string"}, "mode": {"enum": ["preflight", "write"]}, "domain_code": {}, "slug": {}, "topic": {}, "parent_blueprint": {}, "shard_modules": {}, "stub_paths": {}, "scope_profile": {}, "supersedes": {}, "relates_to": {}, "affected_paths": {}}, "required": ["intent", "title", "body"]}},
    {"name": "netark_guard", "description": "Guard/setup", "inputSchema": {"type": "object", "properties": {"action": {"enum": ["status", "oracle", "handover", "setup"]}}, "required": ["action"]}},
]

INTENT_ROUTES: Dict[str, Tuple[str, str, str]] = {
    "wiki": ("memory/wiki", "310", "wiki"), "note": ("memory/wiki", "310", "note"),
    "sop": ("memory/wiki", "320", "sop"), "glossary": ("memory/wiki", "330", "glossary"),
    "blueprint": ("memory/specs", "200", "blueprint"),
    "spec": ("memory/specs", "500", "spec"), "audit": ("memory/audits", "700", "audit"), "handover": ("memory/episodic", "900", "digest"),
}


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


def _emit_yaml_lines(data: Dict[str, Any], indent: int = 0) -> List[str]:
    pad, lines = "  " * indent, []
    for k, v in data.items():
        lines.extend([f"{pad}{k}:", *_emit_yaml_lines(v, indent + 1)] if isinstance(v, dict) else [f"{pad}{k}: {json.dumps(v, ensure_ascii=False)}"])
    return lines


def _dump_yaml_frontmatter(fm: Dict[str, Any]) -> str:
    return "---\n" + "\n".join(_emit_yaml_lines(fm)) + "\n---\n"


def _resolve_record_target(intent: str, title: str, slug: str, dom_arg: str, root: Path) -> Tuple[str, str, str, str]:
    target_dir, default_dom, art_type = INTENT_ROUTES[intent]
    dom = dom_arg.strip() or default_dom
    clean_slug = re.sub(r"[^A-Za-z0-9]+", "_", (slug or title or "ENTRY")).strip("_").upper() or "ENTRY"
    if intent == "handover":
        fname = f"HANDOVER_{clean_slug}.md" if slug.strip() else "HANDOVER.md"
        return f"{target_dir}/{fname}", dom, art_type, (f"HANDOVER_{clean_slug}" if slug.strip() else "HANDOVER")
    tdir = root / target_dir
    existing = list(tdir.glob(f"{dom}_*.md")) if tdir.is_dir() else []
    max_seq = max((int(m.group(1)) for p in existing if (m := re.match(rf"^{re.escape(dom)}_(\d{{2}})_", p.name))), default=0)
    return f"{target_dir}/{dom}_{max_seq + 1:02d}_{clean_slug}.md", dom, art_type, clean_slug


def _validate_affected_paths(affected_paths: Any, rel_path: str, root: Path, errors: List[str], prescriptions: List[str]) -> None:
    if affected_paths is None: return
    if not isinstance(affected_paths, list):
        errors.append("affected_paths must be an array of workspace-relative paths.")
        return
    for raw_p in affected_paths:
        p_str = str(raw_p).strip().replace("\\", "/")
        if not p_str: continue
        if sv.is_gitignored_path(p_str, root):
            errors.append(f"[AS-03 Gitignore Violation] affected_paths cannot bind gitignored path: {p_str}")
            prescriptions.append(f"Remove '{p_str}' from affected_paths.")
            continue
        cand = (root / p_str).resolve()
        if not cand.is_relative_to(root) or (not cand.exists() and p_str != rel_path):
            errors.append(f"[AS-03 Grounding] affected_paths target does not exist: {p_str}")
            prescriptions.append(f"Create '{p_str}' first or omit it from affected_paths.")


def _validate_record_inputs(
    intent: str, mode: str, title: str, body: str, rel_path: str, dom: str, art_type: str, affected_paths: Any, root: Path,
    stub_paths: Any = None, scope_err: str | None = None, supersedes: Any = None, shard_modules: Any = None, parent_blueprint: Any = None,
    scope_profile: Any = None,
) -> Tuple[Dict[str, int], int, int, List[str], List[str]]:
    errors, prescriptions = [], []
    if mode not in {"preflight", "write"}: errors.append(f"Invalid mode '{mode}'. Expected 'preflight' or 'write'.")
    if not title.strip() or not body.strip(): errors.append("Both 'title' and 'body' must be non-empty.")
    if scope_err: errors.append(scope_err)
    if supersedes is not None and not isinstance(supersedes, list): errors.append("supersedes must be an array of node_id or node_key strings.")
    if shard_modules is not None and not isinstance(shard_modules, list): errors.append("shard_modules must be an array of node_key strings.")
    if parent_blueprint is not None and not isinstance(parent_blueprint, str): errors.append("parent_blueprint must be a string or null.")
    if (sec_err := check_prewrite_secret_lint(f"{title}\n{body}", target_path=rel_path, cwd=str(root))):
        errors.append(sec_err["reason"])
        prescriptions.append("Remove plaintext secrets and read via os.environ.get().")
    if (fn_err := check_spec_filename_format(rel_path, str(root))):
        errors.append(fn_err["reason"])
    if not re.match(r"^\d{3}$", dom) or dom not in sv.load_valid_taxonomy_codes(root):
        errors.append(f"[AS-07 Taxonomy] Unregistered or invalid domain_code '{dom}'.")
        prescriptions.append("Use a registered 3-digit domain_code from memory/index/TAXONOMY.json.")
    for port_err in sv.check_as05_portability(title) + sv.check_as05_portability(body):
        errors.append(port_err)
        prescriptions.append("Replace local user/home absolute paths with workspace-relative paths.")
    if str(root) in body or str(Path.home()) in body:
        errors.append("[AS-05 Portability] Absolute workspace or home path detected in body.")
        prescriptions.append("Use workspace-relative paths instead of absolute machine paths.")
    budget, prose_lc = sv.PROSE_LINE_BUDGETS.get(art_type, 500), sv.count_prose_lines(body)
    if prose_lc > budget:
        errors.append(f"[ProseBudget] Prose lines ({prose_lc}) exceed budget ({budget}) for '{art_type}'.")
        prescriptions.append("Convert long prose paragraphs into concise Markdown tables or bullets.")
    if rel_path == "memory/episodic/HANDOVER.md" and len(body.splitlines()) > 39:
        errors.append("[ProseBudget / HANDOVER] Body exceeds 39 lines (total file must stay <= 65 lines).")
    counts = {k: len(pat.findall(body)) for k, pat in sv.EPISTEMIC_TAGS.items()}
    if intent in ("spec", "blueprint", "audit") and (counts["fact_count"] + counts["inferred_count"] < 1 or counts["unverified_count"] > 0):
        errors.append("[AS-02 Epistemic Gate] Official blueprint/spec/audit requires >=1 '- [FACT]'/'- [INFERRED]' item and 0 '[UNVERIFIED]' items.")
        prescriptions.append("Prefix at least one list item with '- [FACT] ' or '- [INFERRED] ' and remove '[UNVERIFIED]'.")
    _validate_affected_paths(affected_paths, rel_path, root, errors, prescriptions)
    if intent in ("spec", "blueprint"):
        for e in verify_spec_ast_symbols(body, affected_paths if isinstance(affected_paths, list) else [], stub_paths if isinstance(stub_paths, list) else [], root):
            errors.append(e)
            prescriptions.append("Align spec symbol names with actual AST symbols in affected_paths or mark as '新增'.")
    if intent == "spec":
        tmp_fm = {"artifact_type": art_type, "context_index": {"domain_code": dom}, "scope_profile": scope_profile if isinstance(scope_profile, dict) else {}, "topology": {"parent_blueprint": parent_blueprint, "affected_paths": affected_paths if isinstance(affected_paths, list) else [], "stub_paths": stub_paths if isinstance(stub_paths, list) else []}}
        if (bp_err := check_spec_blueprint_required(tmp_fm, body, rel_path)):
            errors.append(bp_err["reason"])
            prescriptions.append("Create a blueprint first and pass parent_blueprint.")
    return counts, prose_lc, budget, errors, prescriptions


def _build_record_frontmatter(
    node_id: str, art_type: str, dom: str, node_slug: str, title: str, rel_path: str, checksum: str,
    counts: Dict[str, int], body: str, relates_to: Any, affected_paths: Any, root: Path, stub_paths: Any = None,
    topic_tag: str = "General", has_explicit_topic: bool = False, parent_blueprint: Any = None,
    shard_modules: Any = None, supersedes: Any = None, scope_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    today, is_official = datetime.date.today().isoformat(), art_type in sv.OFFICIAL_TYPES
    has_soul = any(n.get("context_index", {}).get("node_key") == "000.SOUL.v1" for n in load_all_memory_nodes(root).values())
    deps = [str(x) for x in relates_to if str(x).strip()] if isinstance(relates_to, list) and relates_to else (["000.SOUL.v1"] if has_soul else [])
    aff = [str(x).strip().replace("\\", "/") for x in affected_paths if str(x).strip()] if isinstance(affected_paths, list) and affected_paths else [rel_path]
    clean_title = re.sub(r"[\r\n\"]+", " ", title).strip()
    summary = clean_title if 10 <= len(clean_title) <= 160 else f"NetArk {art_type}: {clean_title}"[:160]
    summary = f"{summary} governance node"[:160] if len(summary) < 10 else summary
    has_disk_val = (root / "schemas" / "schema_validator.py").exists()
    oracle = ({
        "type": "schema_check" if has_disk_val else "bash_assert",
        "command": f"python3 schemas/schema_validator.py --file {rel_path}" if has_disk_val else f"test -f {rel_path}",
        "expected_exit_code": 0, "falsifiable_criterion": f"Fail if {rel_path} is missing or fails schema checks.",
    } if is_official else None)
    init_status, reviewer_obj = default_lifecycle_status(art_type, counts.get("unverified_count", 0))
    facet = "NetArk:Episodic:Handover:SessionState" if (art_type == "digest" and not has_explicit_topic) else f"NetArk:{topic_tag}:{art_type.title()}:{'Official' if is_official else art_type.title()}"
    sups = [str(x).strip() for x in supersedes if str(x).strip()] if isinstance(supersedes, list) else []
    shards = [str(x).strip() for x in shard_modules if str(x).strip()] if isinstance(shard_modules, list) else []
    stubs = [str(x).strip().replace("\\", "/") for x in stub_paths if str(x).strip()] if isinstance(stub_paths, list) else []
    pb = str(parent_blueprint).strip() if isinstance(parent_blueprint, str) and parent_blueprint.strip() else None
    topo: Dict[str, Any] = {"depends_on": deps, "supersedes": sups, "conflicts_with": [], "outbound_links": extract_wikilinks_outside_fenced_blocks(body), "backlinks": [], "verified_by": ["schemas/schema_validator.py" if has_disk_val else "netark-mcp"], "affected_paths": aff}
    if art_type in ("blueprint", "spec") or pb is not None: topo["parent_blueprint"] = pb
    if art_type == "blueprint" or shards: topo["shard_modules"] = shards
    if art_type in ("blueprint", "spec") or stubs: topo["stub_paths"] = stubs
    return {
        "node_id": node_id, "artifact_type": art_type, "access_tier": "restricted" if is_official else "standard",
        "priority": "high" if (is_official or art_type == "digest") else "normal",
        "status": init_status, "created_at": today, "updated_at": today, "author": {"role": "architect", "model": "agy/orchestrator-argon"},
        "reviewer": reviewer_obj, "content_checksum": checksum, "epistemic_profile": counts, "verification_oracle": oracle,
        **({"scope_profile": scope_profile} if scope_profile is not None else {}),
        "context_index": {"domain_code": dom, **({"subdomain": "910"} if art_type == "digest" and dom == "900" else {}), "node_key": f"{dom}.{node_slug}.v1", **({"topic": topic_tag} if has_explicit_topic else {}), "artifact_track": "official" if is_official else "wiki", "facet_tags": [facet], "keywords": [node_slug, art_type], "summary_1line": summary},
        "topology": topo,
    }


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
    fm = _build_record_frontmatter(node_id, art_type, dom, node_slug, title, rel_path, hashlib.sha256(body_clean.encode("utf-8")).hexdigest()[:16], counts, body_clean, args.get("relates_to"), args.get("affected_paths"), root, args.get("stub_paths"), resolved_topic, bool(raw_topic), args.get("parent_blueprint"), args.get("shard_modules"), args.get("supersedes"), norm_scope)
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
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    updater(existing)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_asset_if_needed(asset_rel: str, dest_path: Path, overwrite: bool = False) -> None:
    if dest_path.exists() and not overwrite: return
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(get_embedded_asset_text(asset_rel), encoding="utf-8")


def _mcp_server_entry(bin_cmd: str) -> Dict[str, Any]:
    return {"command": bin_cmd, "args": ["serve"], "env": {"NETARK_LICENSE_KEY": "${NETARK_LICENSE_KEY}", "NETARK_MEMORY_ROOT": "${NETARK_MEMORY_ROOT}"}}


def _merge_mcp_netark(cfg: Dict[str, Any], bin_cmd: str) -> None:
    if not isinstance(cfg.get("mcpServers"), dict): cfg["mcpServers"] = {}
    servers, entry = cfg["mcpServers"], _mcp_server_entry(bin_cmd)
    if isinstance((old := servers.get("netark")), dict) and isinstance(old.get("env"), dict): entry["env"] = {**entry["env"], **old["env"]}
    servers["netark"] = entry


def _merge_claude_hooks(cfg: Dict[str, Any], cls_hooks: Dict[str, Any]) -> None:
    if not isinstance(cfg.get("hooks"), dict): cfg["hooks"] = {}
    hooks = cfg["hooks"]
    for ev, entries in cls_hooks.items():
        hooks[ev] = [x for x in (hooks.get(ev) if isinstance(hooks.get(ev), list) else []) if "netark-mcp hook" not in json.dumps(x)] + entries


def _configure_closed_hosts(root: Path, targets: List[str], bin_cmd: str, write_rules: bool = False, update_rules: bool = False) -> None:
    if "agy" in targets:
        agy_guard = {
            "enabled": True,
            "SessionStart": [{"type": "command", "command": f"{bin_cmd} hook --session-start-mode agy --cwd .", "timeout": 5}],
            "PreInvocation": [{"type": "command", "command": f"{bin_cmd} hook --pre-invocation-mode agy --cwd .", "timeout": 5}],
            "PreToolUse": [{"matcher": "read_file|view_file|write_file|edit_file|multiedit|write_to_file|replace_file_content|multi_replace_file_content|run_command|bash|invoke_subagent|Agent|Task|subagent|dispatch_specialist|search_web|read_url_content|web_fetch|http_request|web_research", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --hook-mode agy --cwd .", "timeout": 5}]}],
            "PostToolUse": [{"matcher": "write_file|edit_file|multiedit|write_to_file|replace_file_content|multi_replace_file_content", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --post-hook-mode agy --cwd .", "timeout": 10}]}],
            "Stop": [{"type": "command", "command": f"{bin_cmd} hook --stop-mode agy --cwd .", "timeout": 10}],
        }
        _merge_json_file(root / ".agents" / "hooks.json", lambda c: (c.pop("netark-v3-session-init", None), c.pop("netark-v3-guard", None), c.__setitem__("netark-enterprise-guard", agy_guard)) and None)
        _merge_json_file(root / ".agents" / "plugins" / "netark" / "plugin.json", lambda c: c.setdefault("name", "netark") and None)
        _merge_json_file(root / ".agents" / "plugins" / "netark" / "mcp_config.json", lambda c: _merge_mcp_netark(c, bin_cmd))
        if write_rules or update_rules: _copy_asset_if_needed("templates/hosts/agy/AGENTS.md.tpl", root / "AGENTS.md", overwrite=update_rules)
    if "claude" in targets:
        cls_hooks = {
            "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --session-start-mode claude --cwd ."}]}],
            "PreToolUse": [{"matcher": "Bash|Write|Edit|MultiEdit|Read|Task|Agent|WebFetch", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --hook-mode claude --cwd ."}]}],
            "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --post-hook-mode claude --cwd ."}]}],
            "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": f"{bin_cmd} hook --stop-mode claude --cwd ."}]}],
        }
        _merge_json_file(root / ".claude" / "settings.json", lambda c: _merge_claude_hooks(c, cls_hooks))
        if write_rules or update_rules: _copy_asset_if_needed("templates/hosts/claude/CLAUDE.md.tpl", root / "CLAUDE.md", overwrite=update_rules)


def run_closed_mcp_init(cwd: str, target: str = "memory", lang: str = "zh-TW", bin_cmd: str = "netark-mcp", update_rules: bool = False, write_rules: bool = False) -> Dict[str, Any]:
    """Initialize a target project in closed-source MCP mode with 0 .py files written."""
    root = Path(cwd).resolve()
    for sub in ("memory/codex", "memory/episodic", "memory/specs", "memory/wiki", "memory/audits", "memory/index", "memory/private", "projects", "scratch"): (root / sub).mkdir(parents=True, exist_ok=True)
    pol_dir = ".agents" if (root / ".agents" / "enterprise-policy.json").is_file() else (".netark" if (root / ".netark" / "enterprise-policy.json").is_file() else (".agents" if target == "agy" else ".netark"))
    _merge_json_file(root / pol_dir / "enterprise-policy.json", lambda d: d.update({**DEFAULT_ENTERPRISE_POLICY, **d}))
    targets = ["agy", "claude"] if target == "all" else ([] if target == "memory" else [target])
    if target in ("memory", "claude", "all"): _merge_json_file(root / ".mcp.json", lambda c: _merge_mcp_netark(c, bin_cmd))
    _configure_closed_hosts(root, targets, bin_cmd, write_rules=write_rules, update_rules=update_rules)
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
