#!/usr/bin/env python3
"""
NetArk Governed Markdown Initializer & Wiki Auto-Header Engine (schemas/doc_initializer.py)
===========================================================================================
Extracted from `scripts/sync_doc_metadata.py` to enforce modular separation:
  - `allocate_next_node_id`: Sequential `MEM-YYYY-XXXX+` allocator (frontmatter-only scan, dynamic year, skipping sentinel band 9900-9999)
  - `init_memory_node` (`init_governed_markdown` alias): Generates governed YAML frontmatter & body
  - `auto_initialize_wiki_node`: Automatically initializes headerless Markdown nodes under `memory/wiki/`
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMAS_DIR = Path(__file__).resolve().parent
if str(SCHEMAS_DIR) not in sys.path:
    sys.path.insert(0, str(SCHEMAS_DIR))

import schema_validator as sv  # type: ignore  # noqa: E402

NODE_ID_RE = re.compile(r"MEM-(\d{4})-(\d{4,})")
FM_NODE_ID_RE = re.compile(r'(?m)^node_id:\s*["\']?MEM-(\d{4})-(\d{4,})["\']?\s*(?:#.*)?$')
FM_NODE_KEY_RE = re.compile(r'(?m)^[ \t]*node_key:\s*["\']?([^"\'\s#]+)["\']?\s*(?:#.*)?$')
SENTINEL_SEQ_MIN = 9900
SENTINEL_SEQ_MAX = 9999
WIKILINK_RE = re.compile(r"\[\[([A-Za-z0-9_.-]+)(?:\|[^\]]+)?\]\]")
GENERIC_TOPICS = {"Wiki", "Governance", "General"}
TOPIC_TAG_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _extract_topics_from_file(md_file: Path) -> List[str]:
    try:
        fm, _ = sv.parse_markdown_frontmatter(md_file)
    except Exception:
        return []
    ci = fm.get("context_index") if isinstance(fm, dict) else None
    if not isinstance(ci, dict):
        return []
    found = [t] if (t := str(ci.get("topic") or "").strip()) and t not in GENERIC_TOPICS and TOPIC_TAG_RE.match(t) else []
    for tag in (ci.get("facet_tags") if isinstance(ci.get("facet_tags"), list) else []):
        parts = str(tag).strip().split(":")
        if len(parts) == 4 and parts[1] and parts[1] not in GENERIC_TOPICS and TOPIC_TAG_RE.match(parts[1]):
            found.append(parts[1])
    return found


def collect_existing_topics(project_root: Path) -> List[str]:
    """Scan memory/**/*.md frontmatter and return unique non-generic Topic names."""
    mem_dir = project_root / "memory"
    if not mem_dir.is_dir():
        return []
    topics: set[str] = set()
    for md_file in sorted(mem_dir.rglob("*.md")):
        if md_file.name != "CONTEXT_MAP.md":
            topics.update(_extract_topics_from_file(md_file))
    return sorted(topics)


def normalize_topic_tag(raw_topic: Any, existing: List[str], default_topic: str = "General") -> str:
    """Align raw_topic case/separator-insensitively to existing topics, or PascalCase for facet_tags."""
    cand_fb = str(default_topic or "General").strip()
    fallback = cand_fb if TOPIC_TAG_RE.match(cand_fb) else "General"
    raw = str(raw_topic or "").strip()
    if not raw:
        return fallback
    norm_key = re.sub(r"[^A-Za-z0-9]+", "", raw).lower()
    if norm_key:
        for item in existing:
            if re.sub(r"[^A-Za-z0-9]+", "", str(item)).lower() == norm_key:
                return str(item)
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", raw) if t]
    if not tokens:
        return fallback
    pascal = "".join(t[0].upper() + (t[1:].lower() if t.isupper() and len(t) > 2 else t[1:]) for t in tokens)
    return pascal if TOPIC_TAG_RE.match(pascal) else fallback


def normalize_scope_profile(raw_scope: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate scope_profile fields and enforce composite auto-escalation."""
    if raw_scope is None: return None, None
    if not isinstance(raw_scope, dict): return None, "scope_profile must be a JSON object."
    vals: Dict[str, int] = {}
    for fld in ("new_modules_count", "target_files_count"):
        v = raw_scope.get(fld)
        if v is None: vals[fld] = 0; continue
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            return None, f"scope_profile.{fld} must be a non-negative integer."
        try: vals[fld] = max(0, int(v))
        except (TypeError, ValueError): return None, f"scope_profile.{fld} must be a valid integer."
    tier = str(raw_scope.get("complexity_tier") or "atomic").strip().lower()
    if tier not in ("atomic", "composite"):
        return None, f"Invalid scope_profile.complexity_tier '{tier}'. Expected 'atomic' or 'composite'."
    raw_algo = raw_scope.get("requires_new_algorithm", False)
    req_algo = raw_algo.strip().lower() in ("true", "1", "yes") if isinstance(raw_algo, str) else bool(raw_algo)
    if vals["new_modules_count"] >= 1 or vals["target_files_count"] >= 3 or req_algo:
        tier = "composite"
    return {"complexity_tier": tier, "new_modules_count": vals["new_modules_count"], "target_files_count": vals["target_files_count"], "requires_new_algorithm": req_algo}, None


def default_lifecycle_status(artifact_type: str, unverified_count: int = 0) -> Tuple[str, Optional[Dict[str, str]]]:
    """Return initial (status, reviewer) defaults for a governed memory artifact_type."""
    if artifact_type in ("note", "spec", "audit"): return "draft", None
    if artifact_type == "blueprint": return "reviewing", None
    if artifact_type in ("constitution", "rule", "adr"):
        return "verified", {"role": "challenger", "model": "agy/pro-subagent", "verdict": "APPROVED"}
    return ("verified" if unverified_count == 0 else "draft"), None


def _compute_epistemic_counts(body: str) -> Dict[str, int]:
    return {key: len(pattern.findall(body)) for key, pattern in sv.EPISTEMIC_TAGS.items()}


def _extract_frontmatter_block(text: str) -> str:
    norm = text.lstrip("\ufeff")
    if not (norm.startswith("---\n") or norm.startswith("---\r\n")):
        return ""
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)", norm)
    return m.group(1) if m else ""


def _scan_max_node_seq_in_file(f: Path, year: int) -> int:
    if not f.is_file() or f.suffix != ".md" or f.name == "CONTEXT_MAP.md" or any(s in f.name for s in ("SENTINEL-X", "900_SENTINEL", "910_SENTINEL")):
        return 0
    try: fm_block = _extract_frontmatter_block(f.read_text(encoding="utf-8", errors="ignore"))
    except Exception: return 0  # noqa: silent-except
    if not fm_block:
        return 0
    m = FM_NODE_ID_RE.search(fm_block)
    if not m or int(m.group(1)) != year:
        return 0
    seq = int(m.group(2))
    return 0 if SENTINEL_SEQ_MIN <= seq <= SENTINEL_SEQ_MAX else seq


def allocate_next_node_id(memory_root: Path, year: int | None = None) -> str:
    """Scans memory/**/*.md YAML frontmatter for MEM-YYYY-XXXX+ node IDs and returns next sequential ID."""
    target_year = year if year is not None else datetime.date.today().year
    if not memory_root.exists():
        return f"MEM-{target_year}-0001"
    max_id = max((_scan_max_node_seq_in_file(f, target_year) for f in memory_root.rglob("*.md")), default=0)
    next_seq = max_id + 1
    if SENTINEL_SEQ_MIN <= next_seq <= SENTINEL_SEQ_MAX:
        next_seq = SENTINEL_SEQ_MAX + 1
    return f"MEM-{target_year}-{next_seq:04d}"


def collect_existing_node_ids_and_keys(memory_root: Path) -> Tuple[set[str], set[str]]:
    """Scan existing memory/**/*.md frontmatter for occupied node_id and node_key values."""
    used_ids: set[str] = set()
    used_keys: set[str] = set()
    if not memory_root.is_dir():
        return used_ids, used_keys
    for md_file in memory_root.rglob("*.md"):
        if not md_file.is_file() or md_file.name == "CONTEXT_MAP.md":
            continue
        try: fm_block = _extract_frontmatter_block(md_file.read_text(encoding="utf-8", errors="ignore"))
        except Exception: continue  # noqa: silent-except
        if not fm_block:
            continue
        if (m_id := FM_NODE_ID_RE.search(fm_block)):
            used_ids.add(f"MEM-{m_id.group(1)}-{m_id.group(2)}")
        if (m_key := FM_NODE_KEY_RE.search(fm_block)):
            used_keys.add(m_key.group(1).strip())
    return used_ids, used_keys


def render_core_memory_template(
    raw_text: str, memory_root: Path, today: str, used_ids: set[str], used_keys: set[str]
) -> Optional[str]:
    """Render a core memory template without node_key duplication or node_id collisions."""
    fm_block = _extract_frontmatter_block(raw_text)
    m_key = FM_NODE_KEY_RE.search(fm_block)
    tmpl_key = m_key.group(1).strip() if m_key else ""
    if tmpl_key and tmpl_key in used_keys:
        return None
    rendered = raw_text.replace("2026-11-08", today)
    m_id = FM_NODE_ID_RE.search(fm_block)
    if m_id:
        tmpl_id = f"MEM-{m_id.group(1)}-{m_id.group(2)}"
        final_id = tmpl_id
        if tmpl_id in used_ids:
            final_id = allocate_next_node_id(memory_root)
            while final_id in used_ids:
                parts = final_id.split("-")
                seq = int(parts[2]) + 1
                if SENTINEL_SEQ_MIN <= seq <= SENTINEL_SEQ_MAX:
                    seq = SENTINEL_SEQ_MAX + 1
                final_id = f"MEM-{parts[1]}-{seq:04d}"
            rendered = rendered.replace(tmpl_id, final_id)
        used_ids.add(final_id)
    if tmpl_key:
        used_keys.add(tmpl_key)
    return rendered


def init_memory_node(  # noqa: god-function
    md_path: Path,
    project_root: Path,
    artifact_type: str = "wiki",
    domain_code: str | None = None,
    node_key: str | None = None,
    title: str | None = None,
    topic: str | None = None,
) -> None:
    if not md_path.exists():
        md_path.parent.mkdir(parents=True, exist_ok=True)
        raw_body = f"# {title or md_path.stem}\n\n- [FACT] 初始條目建立。"
    else:
        raw_body = md_path.read_text(encoding="utf-8")

    if raw_body.startswith("---\n"):
        return

    if not domain_code:
        prefix_match = re.match(r"^(\d{3})_", md_path.name)
        domain_code = prefix_match.group(1) if prefix_match else ("310" if artifact_type in sv.WIKI_TYPES else "300")

    today_str = datetime.date.today().isoformat()
    node_id = allocate_next_node_id(project_root / "memory")
    clean_stem = re.sub(r"^\d{3}_(?:\d{2}_)?", "", md_path.stem)
    slug = clean_stem.upper().replace(" ", "_").replace("-", "_")
    if not node_key:
        node_key = f"{domain_code}.{slug}.v1"
    h1_match = re.search(r"^#\s+(.+)$", raw_body, flags=re.MULTILINE)
    extracted_h1 = h1_match.group(1).strip().replace('"', "'") if h1_match else ""
    doc_title = title or extracted_h1 or clean_stem.replace("_", " ").title()

    outbound = []
    for m in WIKILINK_RE.finditer(raw_body):
        ref = m.group(1).strip()
        if ref and ref not in outbound:
            outbound.append(ref)

    content_checksum = sv.compute_body_checksum(raw_body)

    actual_counts = _compute_epistemic_counts(raw_body)
    is_official = artifact_type in sv.OFFICIAL_TYPES
    access_tier = "restricted" if is_official else "standard"
    priority = "high" if is_official else "normal"
    track = "official" if is_official else "wiki"
    rel_path_str = (str(md_path.relative_to(project_root)) if md_path.is_relative_to(project_root) else str(md_path)).replace("\\", "/")

    init_status, reviewer_obj = default_lifecycle_status(artifact_type, actual_counts.get("unverified_count", 0))
    reviewer_field = (
        f'reviewer:\n  role: "{reviewer_obj["role"]}"\n  model: "{reviewer_obj["model"]}"\n  verdict: "{reviewer_obj["verdict"]}"'
        if reviewer_obj
        else "reviewer: null"
    )

    oracle_field = f"""verification_oracle:
  type: "schema_check"
  command: "python3 schemas/schema_validator.py --file {rel_path_str} --run-oracle"
  expected_exit_code: 0
  falsifiable_criterion: "節點內容與標頭不合規或驗證器回傳非 0 結束碼" """ if is_official else "verification_oracle: null"

    extra_topo = (
        "  parent_blueprint: null\n  shard_modules: []\n  stub_paths: []\n"
        if artifact_type in ("blueprint", "spec")
        else ""
    )

    resolved_topic = normalize_topic_tag(topic, collect_existing_topics(project_root)) if topic else "General"
    topic_line = f'  topic: "{resolved_topic}"\n' if topic else ""
    if artifact_type == "digest" and not topic:
        default_tag = "NetArk:Episodic:Digest:SessionLog"
        default_summary = f"{doc_title} 會話歷程與狀態摘要紀錄"
    elif topic or artifact_type != "wiki":
        default_tag = f"NetArk:{resolved_topic}:{artifact_type.title()}:{artifact_type.title()}"
        default_summary = f"{doc_title} {'架構治理規範公文' if is_official else '知識庫條目'}"
    else:
        default_tag = f"Library:Wiki:Document:{artifact_type}"
        default_summary = f"{doc_title} 知識庫條目"

    deps_yaml = json.dumps([] if md_path.name == "000_SOUL.md" else ["000.SOUL.v1"])

    frontmatter = f"""---
node_id: "{node_id}"
artifact_type: "{artifact_type}"
access_tier: "{access_tier}"
priority: "{priority}"
status: "{init_status}"
created_at: "{today_str}"
updated_at: "{today_str}"
author:
  role: "knowledge_worker"
  model: "agy/orchestrator-argon"
{reviewer_field}
content_checksum: "{content_checksum}"
epistemic_profile:
  fact_count: {actual_counts['fact_count']}
  inferred_count: {actual_counts['inferred_count']}
  hypothesis_count: {actual_counts['hypothesis_count']}
  unverified_count: {actual_counts['unverified_count']}
epistemic_stats:
  fact_count: {actual_counts['fact_count']}
  inferred_count: {actual_counts['inferred_count']}
  hypothesis_count: {actual_counts['hypothesis_count']}
  unverified_count: {actual_counts['unverified_count']}
{oracle_field}
context_index:
  domain_code: "{domain_code}"
  node_key: "{node_key}"
{topic_line}  artifact_track: "{track}"
  facet_tags:
    - "{default_tag}"
  keywords:
    - "{slug}"
    - "wiki"
  summary_1line: "{default_summary}"
topology:
  depends_on: {deps_yaml}
  supersedes: []
  conflicts_with: []
{extra_topo}  outbound_links: {json.dumps(outbound)}
  backlinks: []
  verified_by:
    - "schemas/schema_validator.py"
  affected_paths:
    - "{rel_path_str}"
---
"""
    md_path.write_text(frontmatter + "\n" + raw_body.lstrip(), encoding="utf-8")


init_governed_markdown = init_memory_node


def auto_initialize_wiki_node(md_path: Path, project_root: Path, raw_content: str) -> str:
    """Auto-initializes headerless Markdown files under memory/wiki/ and returns updated raw_content."""
    if raw_content.lstrip().startswith("---\n") or "wiki" not in md_path.parts:
        return raw_content
    stem_upper = md_path.stem.upper()
    if any(k in stem_upper for k in ("SOP", "RECIPE", "GUIDE")) or md_path.name.startswith("320_"):
        inferred_type = "sop"
    elif any(k in stem_upper for k in ("GLOSSARY", "ONTOLOGY")) or md_path.name.startswith("330_"):
        inferred_type = "glossary"
    elif any(k in stem_upper for k in ("NOTE", "MEMO", "BACKLOG", "DISCUSSION")):
        inferred_type = "note"
    else:
        inferred_type = "wiki"
    init_memory_node(md_path, project_root, artifact_type=inferred_type)
    return md_path.read_text(encoding="utf-8")
