# ⚓ NetArk (`N.E.T.A.R.K.`) Claude Code Host Governance Rules (`CLAUDE.md`)

You are operating inside a **NetArk (`N.E.T.A.R.K.`)** governed workspace.

## 1. Memory & `@D/@C/@G` Codebook Map
- Inspect `memory/codex/CONTEXT_MAP.md` (containing the `@D/@C/@G` Codebook Map), `memory/LEDGER.md` (`<= 80` lines), and `memory/episodic/HANDOVER.md` (`<= 65` lines).
- After modifying `memory/**/*.md` or source files, run `python3 scripts/auto_update_map.py && python3 schemas/schema_validator.py --run-oracle`.

## 2. Security Guardrails (`SEC-CRED` & `SEC-PREWRITE-SECRET`)
- Never access `.env*`, `auth.json`, or `*vault*.json`.
- Never hardcode secrets in code (`SEC-PREWRITE-SECRET`); use `os.environ.get('KEY_NAME')` and instruct the user to set `.env`.
