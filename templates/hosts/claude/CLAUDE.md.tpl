# ⚓ NetArk (`N.E.T.A.R.K.`) Claude Code Host Governance Rules (`CLAUDE.md`)

You are operating inside a **NetArk (`N.E.T.A.R.K.`)** governed workspace.

## 1. Turn-1 `@D/@C/@G` Codebook & Hook-First Memory Protocol
- **Auto-Injected Context & Read Boundary**: On `SessionStart`, `.claude/settings.json` injects the frozen `@D/@C/@G` Codebook (`memory/codex/CONTEXT_MAP.md`), `memory/episodic/HANDOVER.md` (`<= 65` lines), and active tracks. NEVER whole-read `memory/codex/CONTEXT_MAP.md` (only `StartLine=1` before `'## 2.'`; enforced by `CONTEXT-MAP-READ-GATE`), and NEVER read `memory/index/CONTEXT_INDEX.json` directly.
- **Core Nodes & Lifecycle**: Core nodes live in `memory/codex/{000_SOUL,100_ARCH_RULES,200_DECISIONS}.md` and `memory/LEDGER.md` (`<= 80` lines; auto-syncs `200_*.md` blueprints). Follow `note (draft ➔ reviewing) ➔ blueprint (reviewing ➔ stub_ready ➔ verified) ➔ shard spec (draft/reviewing + planned stub_paths ➔ stub skeleton + Negative Matrix & Red Negative Tests ➔ stub_ready ➔ full code ➔ independent Challenger review ➔ verified)`.
- **Auto-Sync Hooks**: `PreToolUse` and `PostToolUse` automatically enforce security/AST gates and run NetArk's embedded single-file `schema_validator` + index compiler via `netark-mcp hook` (no manual `auto_update_map.py` or `schema_validator.py` needed).
- **MCP 3-Tool Workflow**:
  - **Query (`netark_query`)**: Call `netark_query(query="status:reviewing"|"status:draft"|"310:draft"|"<Topic>")` BEFORE reading/triaging memory files to resolve `@D/@C/@G` codes, status buckets, blueprints/topics, or 1-hop AST impact (see `.agents/skills/memory-triage/SKILL.md` for low-token memory inventory and triage).
  - **Record (`netark_record`)**: Use `netark_record(intent, title, body, mode="preflight"|"write", target_path?)` for creating or updating `memory/**/*.md` (pass `target_path` for in-place updates; in closed mode, `Write` on `memory/` is blocked by `MCP-PROB-01-REDIRECT`, while `Edit` on existing `memory/**/*.md` is allowed and auto-validated).
  - **Verify (`netark_guard`)**: Call `netark_guard(action="handover")` BEFORE reading/triaging memory files for active session objective/tracks; call `netark_guard(action="oracle")` after multi-file or spec changes for full-repo Schema + DAG verification (alongside the project's test suite); call `netark_guard(action="setup")` only when wiring hooks on another host.

## 2. Epistemic Honesty, Delegation & Gate Integrity
- Prefix key claims in governed Markdown lists with `- [FACT]`, `- [INFERRED]`, `- [HYPOTHESIS]`, or `- [UNVERIFIED]`.
- For large files (`> 600` lines) or multi-file implementation/verification, delegate via `Task`/`Explore` subagents (`[R]` Role/Path, `[I]` Invariants/line-cap, `[B]` 4Q boundaries: `rollback / omitted-field preservation / cross-rule caps / malformed bypass`, `[C]` Contracts + concrete test/negative verification target, `>= 60` chars per `SPEC-RIBC-GATE`), then run project tests and `netark_guard(action="oracle")`. In discussion mode, label unverified ideas as proposals/hypotheses; in execution mode, report only directly observed file/test outputs.
- Always use native `Write`/`Edit` for code/tests (`test_*` in `scratch/`); NEVER use `Bash` (`cat > ...`) or `/tmp` to bypass AST hygiene gates (nesting `<= 4`, no silent `except: pass`).

## 3. Security Guardrails (`SEC-CRED` & `SEC-PREWRITE-SECRET`)
- Never access `.env*`, `auth.json`, or `*vault*.json` (`SEC-CRED`).
- Never hardcode secrets in code (`SEC-PREWRITE-SECRET`); use `os.environ.get('KEY_NAME')` and instruct the user to set `.env`.
