---
node_id: "MEM-2026-0001"
artifact_type: "constitution"
access_tier: "immutable"
priority: "critical"
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
  fact_count: 5
  inferred_count: 2
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "schema_check"
  command: "python3 schemas/schema_validator.py --file memory/codex/000_SOUL.md"
  expected_exit_code: 0
  falsifiable_criterion: "Invalid if this core constitution fails schema validation, cross-model sign-off, or epistemic tag honesty."
context_index:
  domain_code: "000"
  node_key: "000.SOUL.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Core:Constitution:Governance"
    - "Epistemic:AntiSycophancy:DualTrack:Oracle"
  keywords:
    - "NetArk"
    - "Constitution"
    - "Epistemic Honesty"
    - "Dual-Track Library"
    - "Anti-Sycophancy"
  summary_1line: "NetArk Core Constitution: 4-tier epistemic tags, Official/Wiki dual-track memory, and anti-sycophancy Oracle rules"
topology:
  depends_on: []
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/schema_validator.py"
  affected_paths:
    - "schemas/schema_validator.py"
---

# ⚓ `000.SOUL.v1` (MEM-2026-0001) — NetArk (`N.E.T.A.R.K.`) Core Epistemic Constitution

## §1 Dual-Layer Portable Brain & Dual-Track Memory Governance

- [FACT] `NetArk` (**N**etwork-shielded, **E**nforced-**T**emplate **A**rchival & **R**ule-indexed **K**ernel) uses a portable dual-layer architecture combining an embedded brain directory (`.netark/`) with a governed memory graph (`memory/`).
- [FACT] The memory graph operates on two tracks: the **Official Track** (`constitution`, `rule`, `adr`, `blueprint`, `spec`, `audit`) and the **Wiki Track** (`wiki`, `note`, `sop`, `glossary`, `digest`).
- [INFERRED] Decoupling concise prompt navigation from deterministic hook remediation (`RemediationPointer`) keeps the system prompt lean while guaranteeing 100% policy enforcement.

## §2 Four-Tier Epistemic Honesty & Anti-Sycophancy Oracles (`AS-01` ~ `AS-06`)

- [FACT] Every official memory node must prefix key claims at the start of Markdown list items with `[FACT]`, `[INFERRED]`, `[HYPOTHESIS]`, or `[UNVERIFIED]`.
- [FACT] Official nodes transitioning to `verified` require heterogeneous cross-model review (`author.model != reviewer.model` with `verdict: "APPROVED"`), zero `[UNVERIFIED]` items, and a passing `verification_oracle`.
- [FACT] Strict prose line budgets apply: `<= 50` prose lines for `constitution`/`rule`/`adr`, `<= 160` prose lines for `spec`/`audit`, `<= 80` total lines for `LEDGER.md`, and `<= 65` total lines for `HANDOVER.md`.
- [INFERRED] Turn-1 frozen `@D/@C/@G` codebook injection combined with `1 Module = 1 Spec` sharding eliminates context rot and single-model sycophancy.
