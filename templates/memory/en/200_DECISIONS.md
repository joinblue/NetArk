---
node_id: "MEM-2026-0003"
artifact_type: "adr"
access_tier: "restricted"
priority: "high"
status: "verified"
created_at: "2026-11-08"
updated_at: "2026-11-08"
author:
  role: "architect"
  model: "nvidia/nemotron-3-ultra-550b-a55b"
reviewer:
  role: "challenger"
  model: "deepseek-ai/deepseek-v4.1-flash"
  verdict: "APPROVED"
epistemic_profile:
  fact_count: 4
  inferred_count: 2
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "schema_check"
  command: "python3 schemas/schema_validator.py --file memory/codex/200_DECISIONS.md"
  expected_exit_code: 0
  falsifiable_criterion: "Invalid if auto_update_map.py fails to generate the @D/@C/@G codebook_map and reverse_lookup dictionary."
context_index:
  domain_code: "200"
  node_key: "200.ADR-001.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Architecture:ADR:Codebook"
    - "Context:KV-Cache:Compression:MultiHost"
  keywords:
    - "ADR-001"
    - "Codebook Compression"
    - "Turn-1 Frozen Map"
    - "Prefix KV Cache"
    - "Portable Brain"
  summary_1line: "ADR-001: Dual-layer portable brain, Turn-1 @D/@C/@G codebook map, and deterministic boundary guard"
topology:
  depends_on:
    - "000.SOUL.v1"
    - "100.ARCH-RULES.v1"
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/schema_validator.py"
  affected_paths:
    - "scripts/auto_update_map.py"
---

# 🏛️ `200.ADR-001.v1` (MEM-2026-0003) — NetArk Architecture Decision Record

## §1 Dual-Layer Portable Brain (`ADR-001`)

- [FACT] Following [[000.SOUL.v1]] and [[100.ARCH-RULES.v1]], `NetArk` unifies its portable control plane under `.netark/` while keeping the initial `memory/` graph clean with 5 core nodes.
- [FACT] Cross-host adapters (`Pi`, `Antigravity/AGY`, `Claude Code`) share the same deterministic Python validation and Tier 0 AST guard kernel.

## §2 Turn-1 Frozen `@D/@C/@G` Codebook Map

- [FACT] `scripts/auto_update_map.py` excludes `.gitignore` paths, runs `scan_plaintext_secrets()`, and compiles `@D` (directory codes), `@C` (script codes), and `@G` (topology synapses) into `codebook_map`.
- [FACT] The compiler automatically scales across L1 (`<= 150` scripts), L2 (`151 ~ 1,500` module clusters), and L3 (`> 1,500` active cone) tiers with O(1) short-code lookup in `reverse_lookup`.
- [INFERRED] Freezing the `@D/@C/@G` map at Turn 1 saves 75%~85% of context tokens and preserves 100% Prefix KV Cache hit rate across turns.
- [INFERRED] Dynamic workspace AST discovery links specifications to source files without manual path hardcoding.
