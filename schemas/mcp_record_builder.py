#!/usr/bin/env python3
"""NetArk MCP Record Validation & Frontmatter Builder (schemas/mcp_record_builder.py)."""

from __future__ import annotations

import datetime, re, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas import schema_validator as sv  # noqa: E402
from schemas.code_hygiene_ast import verify_spec_ast_symbols  # noqa: E402
from schemas.netark_dlp_core import check_prewrite_secret_lint  # noqa: E402
from schemas.topology_graph import load_all_memory_nodes, parse_markdown_frontmatter  # noqa: E402
from schemas.workspace_placement_guard import check_spec_blueprint_required, check_spec_filename_format  # noqa: E402

INTENT_ROUTES: Dict[str, Tuple[str, str, str]] = {
    "wiki": ("memory/wiki", "310", "wiki"), "note": ("memory/wiki", "310", "note"),
    "sop": ("memory/wiki", "320", "sop"), "glossary": ("memory/wiki", "330", "glossary"),
    "blueprint": ("memory/specs", "200", "blueprint"),
    "spec": ("memory/specs", "500", "spec"), "audit": ("memory/audits", "700", "audit"), "handover": ("memory/episodic", "900", "digest"),
}


def _extract_wikilinks_outside_fenced_blocks(body: str) -> List[str]:
    in_fence, links, seen = False, [], set()
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence: continue
        for m in re.finditer(r"\[\[([A-Za-z0-9_.-]+)(?:\|[^\]]+)?\]\]", line):
            if (tok := m.group(1).strip()) and tok not in seen:
                seen.add(tok)
                links.append(tok)
    return links


def _emit_yaml_lines(data: Dict[str, Any], indent: int = 0) -> List[str]:
    import json
    pad, lines = "  " * indent, []
    for k, v in data.items():
        lines.extend([f"{pad}{k}:", *_emit_yaml_lines(v, indent + 1)] if isinstance(v, dict) else [f"{pad}{k}: {json.dumps(v, ensure_ascii=False)}"])
    return lines


def _dump_yaml_frontmatter(fm: Dict[str, Any]) -> str:
    return "---\n" + "\n".join(_emit_yaml_lines(fm)) + "\n---\n"


def _is_active_handover_file(path: Path) -> bool:
    try: head = path.read_text(encoding="utf-8").split("\n---", 1)[0]
    except Exception: return True
    m = re.search(r'(?m)^status:\s*["\']?([a-zA-Z_-]+)', head)
    return not (m and m.group(1).strip().lower() in {"archived", "deprecated"})


def _load_existing_frontmatter(root: Path, rel_path: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    cand = (root / rel_path).resolve()
    if not (cand.is_relative_to(root) and cand.is_file()): return False, None
    try:
        fm, _ = parse_markdown_frontmatter(cand)
        return True, (fm if isinstance(fm, dict) else None)
    except Exception: return True, None


def _prepare_record_body(title: str, body: str) -> str:
    body_clean = body.strip("\r\n")
    if not re.search(r"(?m)^#\s+", body_clean): body_clean = f"# {title.strip()}\n\n{body_clean}"
    return body_clean + "\n"


def _merge_existing_record_args(args: Dict[str, Any], dom: str, art_type: str, norm_scope: Any, existing_fm: Optional[Dict[str, Any]]) -> Tuple[str, str, Any, Any, Any, Any, Any, Any]:
    ex_fm = existing_fm if isinstance(existing_fm, dict) else {}
    ex_ci = ex_fm.get("context_index") if isinstance(ex_fm.get("context_index"), dict) else {}
    ex_topo = ex_fm.get("topology") if isinstance(ex_fm.get("topology"), dict) else {}
    eff_dom, eff_art = str(ex_ci.get("domain_code") or dom), str(ex_fm.get("artifact_type") or art_type)
    pick = lambda k: args.get(k) if args.get(k) is not None else ex_topo.get(k)
    eff_scope = norm_scope if norm_scope is not None else (ex_fm.get("scope_profile") if isinstance(ex_fm.get("scope_profile"), dict) else None)
    return eff_dom, eff_art, pick("affected_paths"), pick("stub_paths"), pick("parent_blueprint"), pick("shard_modules"), pick("supersedes"), eff_scope


def collect_spec_negative_warnings(intent: str, body: str) -> List[str]:
    if intent == "spec" and not re.search(r"(?:失敗|阻斷|回滾|負向|反例|越界|繞過|reject|deny|rollback|fail|invalid|negative|falsifiable)", body, re.IGNORECASE):
        return ["[NegativeMatrix] Spec body lacks explicit negative/failure acceptance criteria; add 3-5 adversarial cases (rollback, omitted-field preservation, cross-rule caps, malformed bypass) and red tests before promoting to stub_ready."]
    return []


def _resolve_record_target(intent: str, title: str, slug: str, dom_arg: str, root: Path, target_path: str = "") -> Tuple[str, str, str, str]:
    target_dir, default_dom, art_type = INTENT_ROUTES[intent]
    dom = dom_arg.strip() or default_dom
    clean_slug = re.sub(r"[^A-Za-z0-9]+", "_", (slug or title or "ENTRY")).strip("_").upper() or "ENTRY"
    raw_tp = target_path.strip().replace("\\", "/")
    if raw_tp:
        cand = Path(raw_tp)
        resolved = cand.resolve() if cand.is_absolute() else (root / raw_tp).resolve()
        rel = str(resolved.relative_to(root)).replace("\\", "/") if resolved.is_relative_to(root) else raw_tp
        return rel, dom, art_type, clean_slug
    if intent == "handover":
        if not slug.strip():
            return f"{target_dir}/HANDOVER.md", dom, art_type, "HANDOVER"
        clean_ho = re.sub(r"^\d{2}_", "", clean_slug) or clean_slug
        ep_dir = root / target_dir
        if ep_dir.is_dir():
            matches = [p for p in sorted(ep_dir.glob(f"HANDOVER_[0-9][0-9]_{clean_ho}.md")) if _is_active_handover_file(p)]
            if not matches:
                matches = [p for p in sorted(ep_dir.glob("HANDOVER_[0-9][0-9]_*.md")) if _is_active_handover_file(p) and (m := re.match(r"^HANDOVER_\d{2}_(.+)\.md$", p.name)) and re.sub(r"[^A-Za-z0-9]+", "_", m.group(1)).strip("_").upper() == clean_ho]
            if matches:
                return f"{target_dir}/{matches[0].name}", dom, art_type, f"HANDOVER_{clean_ho}"
        max_seq = max((int(m.group(1)) for p in (ep_dir.glob("HANDOVER_*.md") if ep_dir.is_dir() else []) if (m := re.match(r"^HANDOVER_(\d{2})_", p.name))), default=1)
        return f"{target_dir}/HANDOVER_{max_seq + 1:02d}_{clean_ho}.md", dom, art_type, f"HANDOVER_{clean_ho}"
    if target_dir != "memory/wiki" and re.match(r"^\d+_", clean_slug):
        clean_slug = f"REF_{clean_slug}"
    tdir = root / target_dir
    existing = list(tdir.glob(f"{dom}_*.md")) if tdir.is_dir() else []
    max_seq = max((int(m.group(1)) for p in existing if (m := re.match(rf"^{re.escape(dom)}_(\d{{2}})_", p.name))), default=0)
    return f"{target_dir}/{dom}_{max_seq + 1:02d}_{clean_slug}.md", dom, art_type, clean_slug


def _validate_path_list(paths: Any, field: str, rel_path: str, root: Path, errors: List[str], prescriptions: List[str], require_exists: bool) -> None:
    if paths is None: return
    if not isinstance(paths, list):
        errors.append(f"{field} must be an array of workspace-relative paths.")
        return
    for raw_p in paths:
        p_str = str(raw_p).strip().replace("\\", "/")
        if not p_str: continue
        if sv.is_gitignored_path(p_str, root):
            errors.append(f"[AS-03 Gitignore Violation] {field} cannot bind gitignored path: {p_str}")
            prescriptions.append(f"Remove '{p_str}' from {field}.")
            continue
        cand = (root / p_str).resolve()
        if not cand.is_relative_to(root) or (require_exists and not cand.exists() and p_str != rel_path):
            code = "AS-03 Grounding" if require_exists else "AS-03 Stub Grounding"
            errors.append(f"[{code}] {field} target does not exist: {p_str}" if cand.is_relative_to(root) else f"[{code}] {field} path escapes workspace root: {p_str}")
            prescriptions.append(f"Create '{p_str}' first or omit it from {field}." if require_exists else f"Use a workspace-relative path inside root in {field}.")


def _validate_record_inputs(
    intent: str, mode: str, title: str, body: str, rel_path: str, dom: str, art_type: str, affected_paths: Any, root: Path,
    stub_paths: Any = None, scope_err: str | None = None, supersedes: Any = None, shard_modules: Any = None, parent_blueprint: Any = None,
    scope_profile: Any = None, target_path: str = "",
) -> Tuple[Dict[str, int], int, int, List[str], List[str]]:
    errors, prescriptions = [], []
    if mode not in {"preflight", "write"}: errors.append(f"Invalid mode '{mode}'. Expected 'preflight' or 'write'.")
    if not title.strip() or not body.strip(): errors.append("Both 'title' and 'body' must be non-empty.")
    has_tp_err = False
    if target_path.strip():
        raw_tp = target_path.strip().replace("\\", "/")
        cand_tp = Path(raw_tp).resolve() if Path(raw_tp).is_absolute() else (root / raw_tp).resolve()
        valid_rel = cand_tp.is_relative_to(root) and rel_path.startswith("memory/") and rel_path.endswith(".md") and Path(rel_path).name != "CONTEXT_MAP.md"
        if not valid_rel:
            errors.append(f"[TargetPath] Invalid target_path '{target_path}': must resolve to an existing memory/**/*.md inside workspace (excluding CONTEXT_MAP.md).")
            prescriptions.append("Pass a workspace-relative memory/**/*.md path other than CONTEXT_MAP.md.")
            has_tp_err = True
        elif not cand_tp.is_file():
            errors.append(f"[TargetPath] target_path '{target_path}' does not exist; omit target_path to create a new file or pass an existing memory/**/*.md path.")
            prescriptions.append("Omit target_path to create a new file or pass an existing memory/**/*.md path.")
            has_tp_err = True
    if scope_err: errors.append(scope_err)
    if supersedes is not None and not isinstance(supersedes, list): errors.append("supersedes must be an array of node_id or node_key strings.")
    if shard_modules is not None and not isinstance(shard_modules, list): errors.append("shard_modules must be an array of node_key strings.")
    if parent_blueprint is not None and not isinstance(parent_blueprint, str): errors.append("parent_blueprint must be a string or null.")
    if (sec_err := check_prewrite_secret_lint(f"{title}\n{body}", target_path=rel_path, cwd=str(root))):
        errors.append(sec_err["reason"])
        prescriptions.append("Remove plaintext secrets and read via os.environ.get().")
    if not has_tp_err and (fn_err := check_spec_filename_format(rel_path, str(root))):
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
    is_ho = rel_path.startswith("memory/episodic/HANDOVER") and rel_path.endswith(".md")
    budget, prose_lc = (39 if is_ho else sv.PROSE_LINE_BUDGETS.get(art_type, 500)), sv.count_prose_lines(body)
    if prose_lc > budget:
        errors.append(f"[ProseBudget] Prose lines ({prose_lc}) exceed budget ({budget}) for '{art_type}'.")
        prescriptions.append("Convert long prose paragraphs into concise Markdown tables or bullets.")
    if is_ho and len(body.splitlines()) > 39:
        errors.append("[ProseBudget / HANDOVER] Body exceeds 39 lines (total file must stay <= 65 lines).")
    counts = {k: len(pat.findall(body)) for k, pat in sv.EPISTEMIC_TAGS.items()}
    if intent in ("spec", "blueprint", "audit") and (counts["fact_count"] + counts["inferred_count"] < 1 or counts["unverified_count"] > 0):
        errors.append("[AS-02 Epistemic Gate] Official blueprint/spec/audit requires >=1 '- [FACT]'/'- [INFERRED]' item and 0 '[UNVERIFIED]' items.")
        prescriptions.append("Prefix at least one list item with '- [FACT] ' or '- [INFERRED] ' and remove '[UNVERIFIED]'.")
    _validate_path_list(affected_paths, "affected_paths", rel_path, root, errors, prescriptions, require_exists=True)
    _validate_path_list(stub_paths, "stub_paths", rel_path, root, errors, prescriptions, require_exists=False)
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


def _merge_existing_topology(
    art_type: str, rel_path: str, body: str, root: Path, has_disk_val: bool,
    relates_to: Any, affected_paths: Any, stub_paths: Any, parent_blueprint: Any,
    shard_modules: Any, supersedes: Any, ex_topo: Dict[str, Any],
) -> Dict[str, Any]:
    has_soul = any(n.get("context_index", {}).get("node_key") == "000.SOUL.v1" for n in load_all_memory_nodes(root).values())
    if relates_to is None and isinstance(ex_topo.get("depends_on"), list) and ex_topo["depends_on"]:
        deps = ex_topo["depends_on"]
    else:
        deps = [str(x) for x in relates_to if str(x).strip()] if isinstance(relates_to, list) and relates_to else (["000.SOUL.v1"] if has_soul else [])
    if affected_paths is None and isinstance(ex_topo.get("affected_paths"), list):
        aff = ex_topo["affected_paths"]
    else:
        aff = [str(x).strip().replace("\\", "/") for x in affected_paths if str(x).strip()] if isinstance(affected_paths, list) and affected_paths else [rel_path]
    sups = ex_topo["supersedes"] if supersedes is None and isinstance(ex_topo.get("supersedes"), list) else ([str(x).strip() for x in supersedes if str(x).strip()] if isinstance(supersedes, list) else [])
    shards = ex_topo["shard_modules"] if shard_modules is None and isinstance(ex_topo.get("shard_modules"), list) else ([str(x).strip() for x in shard_modules if str(x).strip()] if isinstance(shard_modules, list) else [])
    stubs = ex_topo["stub_paths"] if stub_paths is None and isinstance(ex_topo.get("stub_paths"), list) else ([str(x).strip().replace("\\", "/") for x in stub_paths if str(x).strip()] if isinstance(stub_paths, list) else [])
    pb = ex_topo["parent_blueprint"] if parent_blueprint is None and "parent_blueprint" in ex_topo else (str(parent_blueprint).strip() if isinstance(parent_blueprint, str) and parent_blueprint.strip() else None)
    vby = ex_topo["verified_by"] if isinstance(ex_topo.get("verified_by"), list) and ex_topo["verified_by"] else ["schemas/schema_validator.py" if has_disk_val else "netark-mcp"]
    topo: Dict[str, Any] = {"depends_on": deps, "supersedes": sups, "conflicts_with": [], "outbound_links": _extract_wikilinks_outside_fenced_blocks(body), "backlinks": [], "verified_by": vby, "affected_paths": aff}
    if art_type in ("blueprint", "spec") or pb is not None or "parent_blueprint" in ex_topo: topo["parent_blueprint"] = pb
    if art_type == "blueprint" or shards or "shard_modules" in ex_topo: topo["shard_modules"] = shards
    if art_type in ("blueprint", "spec") or stubs or "stub_paths" in ex_topo: topo["stub_paths"] = stubs
    return topo


def _merge_existing_context_index(
    art_type: str, dom: str, node_slug: str, is_official: bool, summary: str,
    topic_tag: str, has_explicit_topic: bool, ex_ci: Dict[str, Any],
) -> Dict[str, Any]:
    ctx_dom = str(ex_ci.get("domain_code") or dom)
    node_key = str(ex_ci.get("node_key") or f"{ctx_dom}.{node_slug}.v1")
    default_facet = "NetArk:Episodic:Handover:SessionState" if (art_type == "digest" and not has_explicit_topic) else f"NetArk:{topic_tag}:{art_type.title()}:{'Official' if is_official else art_type.title()}"
    facets = ex_ci["facet_tags"] if (not has_explicit_topic and isinstance(ex_ci.get("facet_tags"), list) and ex_ci["facet_tags"]) else [default_facet]
    keywords = ex_ci["keywords"] if (isinstance(ex_ci.get("keywords"), list) and ex_ci["keywords"]) else [node_slug, art_type]
    ci: Dict[str, Any] = {"domain_code": ctx_dom}
    if "subdomain" in ex_ci and ex_ci["subdomain"] is not None: ci["subdomain"] = ex_ci["subdomain"]
    elif art_type == "digest" and ctx_dom == "900": ci["subdomain"] = "910"
    ci["node_key"] = node_key
    if "context_pin" in ex_ci and ex_ci["context_pin"] is not None: ci["context_pin"] = ex_ci["context_pin"]
    if has_explicit_topic: ci["topic"] = topic_tag
    elif ex_ci.get("topic"): ci["topic"] = ex_ci["topic"]
    ci.update({"artifact_track": "official" if is_official else "wiki", "facet_tags": facets, "keywords": keywords, "summary_1line": summary})
    return ci


def _build_record_frontmatter(
    node_id: str, art_type: str, dom: str, node_slug: str, title: str, rel_path: str, checksum: str,
    counts: Dict[str, int], body: str, relates_to: Any, affected_paths: Any, root: Path, stub_paths: Any = None,
    topic_tag: str = "General", has_explicit_topic: bool = False, parent_blueprint: Any = None,
    shard_modules: Any = None, supersedes: Any = None, scope_profile: Dict[str, Any] | None = None,
    existing_fm: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    from schemas.doc_initializer import default_lifecycle_status
    today = datetime.date.today().isoformat()
    ex_fm = existing_fm if isinstance(existing_fm, dict) else {}
    art_type = str(ex_fm.get("artifact_type") or art_type)
    is_official = art_type in sv.OFFICIAL_TYPES
    ex_ci = ex_fm.get("context_index") if isinstance(ex_fm.get("context_index"), dict) else {}
    ex_topo = ex_fm.get("topology") if isinstance(ex_fm.get("topology"), dict) else {}
    created = str(ex_fm.get("created_at") or today)
    clean_title = re.sub(r"[\r\n\"]+", " ", title).strip()
    summary = clean_title if 10 <= len(clean_title) <= 160 else f"NetArk {art_type}: {clean_title}"[:160]
    summary = f"{summary} governance node"[:160] if len(summary) < 10 else summary
    has_disk_val = (root / "schemas" / "schema_validator.py").exists()
    default_oracle = ({"type": "schema_check" if has_disk_val else "bash_assert", "command": f"python3 schemas/schema_validator.py --file {rel_path}" if has_disk_val else f"test -f {rel_path}", "expected_exit_code": 0, "falsifiable_criterion": f"Fail if {rel_path} is missing or fails schema checks."} if is_official else None)
    oracle = ex_fm["verification_oracle"] if isinstance(ex_fm.get("verification_oracle"), dict) else default_oracle
    init_status, reviewer_obj = default_lifecycle_status(art_type, counts.get("unverified_count", 0))
    if ex_fm.get("status"):
        init_status = str(ex_fm["status"])
        if "reviewer" in ex_fm: reviewer_obj = ex_fm["reviewer"]
    author_obj = ex_fm["author"] if isinstance(ex_fm.get("author"), dict) and ex_fm["author"] else {"role": "architect", "model": "agy/orchestrator-argon"}
    eff_scope = scope_profile if scope_profile is not None else (ex_fm["scope_profile"] if isinstance(ex_fm.get("scope_profile"), dict) else None)
    digest_fields: Dict[str, Any] = {}
    if art_type == "digest":
        digest_fields = {"track_id": str(ex_fm.get("track_id") or ("MAIN" if rel_path.endswith("/HANDOVER.md") else re.sub(r"^HANDOVER_", "", node_slug))), "track_status": str(ex_fm.get("track_status") or "active")}
        for k in ("active_blueprint", "active_shards"):
            if k in ex_fm: digest_fields[k] = ex_fm[k]
    topo = _merge_existing_topology(art_type, rel_path, body, root, has_disk_val, relates_to, affected_paths, stub_paths, parent_blueprint, shard_modules, supersedes, ex_topo)
    ci = _merge_existing_context_index(art_type, dom, node_slug, is_official, summary, topic_tag, has_explicit_topic, ex_ci)
    return {"node_id": node_id, "artifact_type": art_type, "access_tier": str(ex_fm.get("access_tier") or ("restricted" if is_official else "standard")), "priority": str(ex_fm.get("priority") or ("high" if (is_official or art_type == "digest") else "normal")), "status": init_status, "created_at": created, "updated_at": today, "author": author_obj, "reviewer": reviewer_obj, "content_checksum": checksum, "epistemic_profile": counts, "verification_oracle": oracle, **digest_fields, **({"scope_profile": eff_scope} if eff_scope is not None else {}), "context_index": ci, "topology": topo}
