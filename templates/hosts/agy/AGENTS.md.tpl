# ⚓ NetArk (`N.E.T.A.R.K.`) Antigravity (AGY) Host Governance Rules (`AGENTS.md`)

You are operating inside a **NetArk (`N.E.T.A.R.K.`)** governed workspace.

## 1. Turn-1 `@D/@C/@G` Codebook Map & Progressive Memory Disclosure
- On `SessionStart`, `.agents/hooks.json` automatically injects the frozen `@D/@C/@G` Codebook Map (`memory/codex/CONTEXT_MAP.md`) and `memory/episodic/HANDOVER.md`.
- Inspect `memory/codex/CONTEXT_MAP.md` for fast human/agent directory routing (Do NOT directly read `memory/index/CONTEXT_INDEX.json` giant JSON compiled database).
- Core memory nodes reside in `memory/codex/{000_SOUL,100_ARCH_RULES,200_DECISIONS}.md`, `memory/LEDGER.md` (`<= 80` lines), and `memory/episodic/HANDOVER.md` (`<= 65` lines).
- Temporary scripts and scratch notes belong in `scratch/`.

## 2. Epistemic Honesty & Mandatory Subagent Delegation (`invoke_subagent` IF-THEN Rules)
- Prefix key claims in governed Markdown lists with `- [FACT]`, `- [INFERRED]`, `- [HYPOTHESIS]`, or `- [UNVERIFIED]`.
- **[IF Multi-File Search / Messy Doc Digestion ($\ge 2$ files or $> 300$ lines, e.g. in `scratch/`) $\rightarrow$ MUST Delegate]**: Proactively call `invoke_subagent(TypeName="research", ...)` (or `nexus-sidecar` MCP tools if available) to digest off-context instead of reading giant files into the main context.
- **[IF Multi-File Code Implementation / Refactoring or Spec Verification $\rightarrow$ MUST Delegate]**: Delegate isolated implementation or cross-subagent verification via `invoke_subagent(TypeName="self"|"research", ...)`, then run `python3 schemas/schema_validator.py --run-oracle`.
- **[No Gate Bypass]**: Always use native `write_file`/`edit_file` tools for code and tests (place temporary tests in `scratch/`); NEVER use `bash` (`cat > ... << 'EOF'`) or `/tmp` to bypass Pre-Write AST hygiene gates (`HYG-01` nesting $\le 4$, `HYG-02` no silent `except: pass`).

## 3. Security Guardrails (`SEC-CRED` & `SEC-PREWRITE-SECRET`)
- Never read or write `.env*`, `auth.json`, or `*vault*.json` (`SEC-CRED`).
- Never hardcode API keys or secrets in files (`SEC-PREWRITE-SECRET`); always use `os.environ.get('KEY_NAME')` and ask the human user to configure `.env` manually.
