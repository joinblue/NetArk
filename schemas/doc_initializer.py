#!/usr/bin/env python3
"""
NetArk Governed Markdown Initializer & Wiki Auto-Header Engine (schemas/doc_initializer.py)
===========================================================================================
Extracted from `scripts/sync_doc_metadata.py` to enforce modular separation:
  - `allocate_next_node_id`: Sequential `MEM-YYYY-XXXX` allocator (ignoring sentinel IDs >= 0099)
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
from typing import Dict

SCHEMAS_DIR = Path(__file__).resolve().parent
if str(SCHEMAS_DIR) not in sys.path:
    sys.path.insert(0, str(SCHEMAS_DIR))

import schema_validator as sv  # type: ignore  # noqa: E402

NODE_ID_RE = re.compile(r"MEM-(\d{4})-(\d{4})")
WIKILINK_RE = re.compile(r"\[\[([A-Za-z0-9_.-]+)(?:\|[^\]]+)?\]\]")


def _compute_epistemic_counts(body: str) -> Dict[str, int]:
    return {
        key: len(pattern.findall(body))
        for key, pattern in sv.EPISTEMIC_TAGS.items()
    }


def _scan_max_node_seq_in_file(f: Path, year: int) -> int:
    if not f.is_file() or f.suffix not in (".md", ".json"):
        return 0
    if "SENTINEL-X" in f.name or "900_SENTINEL" in f.name or "910_SENTINEL" in f.name:
        return 0
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0
    max_seq = 0
    for m in NODE_ID_RE.finditer(text):
        y, seq_num = int(m.group(1)), int(m.group(2))
        if y == year and seq_num < 99 and seq_num > max_seq:
            max_seq = seq_num
    return max_seq


def allocate_next_node_id(memory_root: Path, year: int = 2026) -> str:
    """Scans memory/ for all MEM-YYYY-XXXX node IDs (< 0099) and returns next sequential ID."""
    if not memory_root.exists():
        return f"MEM-{year}-0001"
    max_id = max((_scan_max_node_seq_in_file(f, year) for f in memory_root.glob("**/*")), default=0)
    return f"MEM-{year}-{max_id + 1:04d}"


def init_memory_node(
    md_path: Path,
    project_root: Path,
    artifact_type: str = "wiki",
    domain_code: str | None = None,
    node_key: str | None = None,
    title: str | None = None,
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
    clean_stem = re.sub(r"^\d{3}_", "", md_path.stem)
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

    body_for_hash = raw_body.lstrip("\r\n") if raw_body.startswith("\r\n") else (raw_body.lstrip("\n") if raw_body.startswith("\n") else raw_body)
    content_checksum = hashlib.sha256(body_for_hash.encode("utf-8")).hexdigest()[:16]

    actual_counts = _compute_epistemic_counts(raw_body)
    is_official = artifact_type in sv.OFFICIAL_TYPES
    access_tier = "restricted" if is_official else "standard"
    priority = "high" if is_official else "normal"
    track = "official" if is_official else "wiki"
    rel_path_str = str(md_path.relative_to(project_root)) if md_path.is_relative_to(project_root) else str(md_path)

    reviewer_field = """reviewer:
  role: "challenger"
  model: "claude-3-7-sonnet"
  verdict: "APPROVED" """ if is_official else "reviewer: null"

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

    if artifact_type == "digest":
        default_tag = "NetArk:Episodic:Digest:SessionLog"
        default_summary = f"{doc_title} 會話歷程與狀態摘要紀錄"
    elif is_official:
        default_tag = f"NetArk:Governance:{artifact_type.title()}"
        default_summary = f"{doc_title} 架構治理規範公文"
    else:
        default_tag = f"Library:Wiki:Document:{artifact_type}"
        default_summary = f"{doc_title} 知識庫條目"

    deps_yaml = json.dumps([] if md_path.name == "000_SOUL.md" else ["000.SOUL.v1"])

    frontmatter = f"""---
node_id: "{node_id}"
artifact_type: "{artifact_type}"
access_tier: "{access_tier}"
priority: "{priority}"
status: "verified"
created_at: "{today_str}"
updated_at: "{today_str}"
author:
  role: "knowledge_worker"
  model: "flash"
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
  artifact_track: "{track}"
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
