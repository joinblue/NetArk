---
node_id: "MEM-2026-0002"
artifact_type: "rule"
access_tier: "restricted"
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
  inferred_count: 1
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "bash_assert"
  command: "python3 schemas/netark_guard_core.py --self-test"
  expected_exit_code: 0
  falsifiable_criterion: "Invalid if Tier 0 AST guard fails to block .env/auth.json/*vault*.json access or SEC-PREWRITE-SECRET lint."
context_index:
  domain_code: "100"
  node_key: "100.ARCH-RULES.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Security:Boundary:Rule"
    - "Guard:Tier0AST:DLP:PreWriteLint"
  keywords:
    - "Workspace Boundary"
    - "SEC-CRED"
    - "SEC-PREWRITE-SECRET"
    - "SEC-CONTROL-PLANE"
    - "Zero Exfiltration"
  summary_1line: "Workspace boundary & zero-exfiltration guardrails: .netark lock, SEC-CRED, and Pre-Write Secret Lint"
topology:
  depends_on:
    - "000.SOUL.v1"
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/netark_guard_core.py"
  affected_paths:
    - "schemas/netark_guard_core.py"
---

# 🛡️ `100.ARCH-RULES.v1` (MEM-2026-0002) — Workspace Boundary & Zero-Exfiltration Security Rules

## §1 Workspace Boundary & Control-Plane Protection (`SEC-BOUNDARY` & `SEC-CONTROL-PLANE`)

- [FACT] Pursuant to [[000.SOUL.v1]], all file and shell tool invocations are confined to the active project workspace (`cwd`).
- [FACT] Control-plane directories (`.netark/`, `.agents/`, `.claude/`, `.github/workflows/`, `schemas/`) are protected by `SEC-CONTROL-PLANE` against unauthorized agent mutation.
- [FACT] Memory node `topology.affected_paths` must never bind `.gitignore`-ignored runtime secret or cache files (such as `.netark/auth.json`, `.netark/models-store.json`, or `.env`).

## §2 Credential Isolation & Pre-Write Secret Lint (`G-01` ~ `G-05`)

- [FACT] `SEC-CRED` blocks all direct or subshell/AST access to `.env*` (except `.env.example`), `auth.json`, `*vault*.json`, and SSH/cloud private keys.
- [FACT] Persistent plaintext redaction vaults (`.session_vault.json`) and two-way secret restoration are abolished; `SEC-PREWRITE-SECRET` blocks writing hardcoded credentials across 12 secret formats and instructs using `os.environ.get('KEY_NAME')`.
- [INFERRED] Enforcing boundary blocking (`SEC-CRED`) plus pre-write secret linting (`SEC-PREWRITE-SECRET`) eliminates vault leakage, `edit_file` mismatches, and secret restoration attacks.
