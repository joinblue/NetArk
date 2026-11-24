#!/usr/bin/env python3
"""NetArk MCP Record Validation & Frontmatter Builder (schemas/mcp_record_builder.py)."""

from __future__ import annotations

import datetime, re, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas import schema_validator as sv  # noqa: E402
from schemas.code_hygiene_ast import verify_spec_ast_symbols  # noqa: E402
from schemas.netark_dlp_core import check_prewrite_secret_lint  # noqa: E402
from schemas.topology_graph import load_all_memory_nodes  # noqa: E402
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


def _resolve_record_target(intent: str, title: str, slug: str, dom_arg: str, root: Path) -> Tuple[str, str, str, str]:
    target_dir, default_dom, art_type = INTENT_ROUTES[intent]
    dom = dom_arg.strip() or default_dom
    clean_slug = re.sub(r"[^A-Za-z0-9]+", "_", (slug or title or "ENTRY")).strip("_").upper() or "ENTRY"
    if intent == "handover":
        if not slug.strip():
            return f"{target_dir}/HANDOVER.md", dom, art_type, "HANDOVER"
        max_seq = max((int(m.group(1)) for p in (root / target_dir).glob("HANDOVER_*.md") if (m := re.match(r"^HANDOVER_(\d{2})_", p.name))), default=1)
        clean_ho = re.sub(r"^\d{2}_", "", clean_slug) or clean_slug
        return f"{target_dir}/HANDOVER_{max_seq + 1:02d}_{clean_ho}.md", dom, art_type, f"HANDOVER_{clean_ho}"
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


def _build_record_frontmatter(
    node_id: str, art_type: str, dom: str, node_slug: str, title: str, rel_path: str, checksum: str,
    counts: Dict[str, int], body: str, relates_to: Any, affected_paths: Any, root: Path, stub_paths: Any = None,
    topic_tag: str = "General", has_explicit_topic: bool = False, parent_blueprint: Any = None,
    shard_modules: Any = None, supersedes: Any = None, scope_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    from schemas.doc_initializer import default_lifecycle_status
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
    topo: Dict[str, Any] = {"depends_on": deps, "supersedes": sups, "conflicts_with": [], "outbound_links": _extract_wikilinks_outside_fenced_blocks(body), "backlinks": [], "verified_by": ["schemas/schema_validator.py" if has_disk_val else "netark-mcp"], "affected_paths": aff}
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
