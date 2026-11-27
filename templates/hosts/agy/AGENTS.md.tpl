# ⚓ NetArk (`N.E.T.A.R.K.`) Antigravity (AGY) Host Governance Rules (`AGENTS.md`)

You are operating inside a **NetArk (`N.E.T.A.R.K.`)** governed workspace.

## 1. Turn-1 `@D/@C/@G` Codebook & Hook-First Memory Protocol
- **Auto-Injected Context & Read Boundary**: On `SessionStart` / `PreInvocation`, `.agents/hooks.json` injects the frozen `@D/@C/@G` Codebook (`memory/codex/CONTEXT_MAP.md`), `memory/episodic/HANDOVER.md` (`<= 65` lines), and active tracks. NEVER whole-read `memory/codex/CONTEXT_MAP.md` (only `StartLine=1` before `'## 2.'`; enforced by `CONTEXT-MAP-READ-GATE`), and NEVER read `memory/index/CONTEXT_INDEX.json` directly.
- **Core Nodes & Lifecycle**: Core nodes live in `memory/codex/{000_SOUL,100_ARCH_RULES,200_DECISIONS}.md` and `memory/LEDGER.md` (`<= 80` lines; auto-syncs `200_*.md` blueprints). Follow the 5-stage lifecycle: `note (draft ➔ reviewing) ➔ blueprint (reviewing ➔ stub_ready ➔ verified) ➔ shard spec (draft/reviewing + planned stub_paths ➔ stub skeleton + Negative Matrix & Red Negative Tests ➔ stub_ready ➔ full code ➔ independent Challenger review ➔ verified)`.
- **Auto-Sync Hooks**: `PreToolUse` and `PostToolUse` run NetArk's embedded single-file `schema_validator` and index/map compiler automatically via `netark-mcp hook` (no manual index re-runs needed during editing).
- **MCP 3-Tool Workflow**:
  - **Query (`netark_query`)**: Call `netark_query(query="status:reviewing"|"status:draft"|"310:draft"|"<Topic>")` BEFORE reading/triaging memory files to resolve `@D/@C/@G` short codes, status buckets, blueprints/topics, or 1-hop AST impact (see `.agents/skills/memory-triage/SKILL.md` for low-token memory inventory and triage).
  - **Record (`netark_record`)**: Use `netark_record(intent, title, body, mode="preflight"|"write", target_path?)` for creating or updating `memory/**/*.md` (pass `target_path` for in-place updates; in closed mode, `write_file` creating new files under `memory/{wiki,specs,audits,episodic}/` is blocked by `MCP-PROB-01-REDIRECT`, while core/private paths `memory/LEDGER.md`, `memory/codex/*.md`, `memory/private/**/*.md` and `edit_file` on existing files are allowed and auto-validated).
  - **Verify (`netark_guard`)**: Call `netark_guard(action="handover")` BEFORE reading/triaging memory files for active session objective/tracks; call `netark_guard(action="oracle")` after multi-file or spec updates for full-repo Schema + DAG verification (alongside the project's own test suite); call `netark_guard(action="setup")` only when wiring hooks on another host.
- Temporary scripts and scratch notes belong in `scratch/`.

## 2. Epistemic Honesty & Mandatory Subagent Delegation (`invoke_subagent`)
- Prefix key claims in governed Markdown lists with `- [FACT]`, `- [INFERRED]`, `- [HYPOTHESIS]`, or `- [UNVERIFIED]`.
- **[IF Multi-File Search / Large Doc Digestion ($\ge 2$ files or $> 600$ lines) $\rightarrow$ MUST Delegate]**: Call `invoke_subagent(TypeName="research", ...)` to digest off-context instead of slicing large files.
- **[IF Multi-File Implementation / Refactoring or Spec Verification $\rightarrow$ MUST Delegate]**: Delegate isolated implementation via `invoke_subagent(TypeName="self", ...)` (including `[R]` Role/Path, `[I]` Invariants/line-cap, `[B]` 4Q boundaries: `rollback / omitted-field preservation / cross-rule caps / malformed bypass`, `[C]` Contracts + concrete test/negative verification target & `>= 60` chars per `SPEC-RIBC-GATE`), or read-only verification/Challenger review via `TypeName="research"`, then run project tests and `netark_guard(action="oracle")`. In discussion mode, label unverified ideas as proposals/hypotheses; in execution mode, report only directly observed file/test outputs.
- **[No Gate Bypass]**: Always use native `write_file`/`edit_file` tools for code/tests (`test_*` in `scratch/`); NEVER use `bash` (`cat > ... << 'EOF'`) or `/tmp` to bypass Pre-Write AST hygiene gates (`HYG-01` nesting $\le 4$, `HYG-02` no silent `except: pass`).

## 3. Security Guardrails (`SEC-CRED` & `SEC-PREWRITE-SECRET`)
- Never read or write `.env*`, `auth.json`, or `*vault*.json` (`SEC-CRED`).
- Never hardcode API keys or secrets in files (`SEC-PREWRITE-SECRET`); always use `os.environ.get('KEY_NAME')` and ask the human user to configure `.env` manually.
