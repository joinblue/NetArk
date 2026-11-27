# NetArk Universal Hook CLI Contract

NetArk is Hook-first: all security, AST hygiene, RIBC, and handover guardrails listed below live inside `netark-mcp hook`.
Use the fast path for natively supported hosts (`AGY`, `Claude Code`, `Pi Agent`), or wire **1 thin bridge** using the Universal Hook CLI Contract for any other custom host (`Cursor`, `Windsurf`, `Cline`, `Codex`, `Gemini CLI`, etc.).

## 1. Fast Path (Zero-Intrusion Memory / Native AGY, Claude Code & Pi Agent)
- Default (zero host pollution — creates/merges only `.mcp.json`, `memory/`, and policy): `netark-mcp init --cwd .` (or `--target memory`)
- Native Hooks + MCP: `netark-mcp init --target agy --cwd .`, `netark-mcp init --target claude --cwd .`, or `netark-mcp init --target pi --cwd .` (pass `--brain-dir .netark` if migrating an existing `.netark/` Pi workspace; pass `--write-rules` only if you also want root `AGENTS.md`/`CLAUDE.md`)
- Upgrading an existing install (required if `< 3.2.2` for `--target pi`): `uv tool upgrade netark-mcp` (or `uv tool install --force --refresh netark-mcp`) and verify with `netark-mcp --version`.
- Non-destructively merges host JSON/hooks/env, preserves existing `memory/` files, and locks the absolute `netark-mcp` path (preventing GUI `ENOENT`).

## 2. Black-Box Capabilities Built Into `netark-mcp hook` (No Duplicate Logic Needed)
- **Replacement Principle**: Because all guardrails below are already built into `netark-mcp hook`, a host only needs **1 thin bridge** forwarding lifecycle events to `netark-mcp hook` — do NOT re-implement security/AST/hygiene checks in `.ts` or shell wrappers (keep non-guard plugins such as model routers, subagent dispatchers, or web-search tools untouched).
- `--session-start-mode`: Injects the Turn-1 frozen `@D/@M/@C/@G` Codebook Map, `HANDOVER.md` snapshot, and active side-tracks.
- `--pre-invocation-mode` *(optional, e.g. AGY)*: Injects delta codebook updates and queued `PostToolUse` alerts.
- `--hook-mode` (`PreToolUse`): Enforces credential & control-plane isolation (`SEC-CRED`, `SEC-CONTROL-PLANE`), pre-write secret scanning (`SEC-PREWRITE-SECRET`), Web/SSRF protection, shell AST inspection, large-file direct-read / salami-slicing lease (`SIDECAR-GATE`), subagent RIBC 4D gate (`SPEC-RIBC-GATE`), Python AST hygiene (P1–P4) & modularity line limits, `STUB-FIRST-GATE`, YAML frontmatter prefill check, active handover overwrite protection, and redirecting raw `memory/**/*.md` writes to MCP `netark_record` (`MCP-PROB-01-REDIRECT`).
- `--post-hook-mode` (`PostToolUse`): Runs embedded single-file schema validation, refreshes `CONTEXT_INDEX.json` / `CONTEXT_MAP.md`, and emits Spec↔Code drift alerts on code edits.
- `--stop-mode` (`Stop`): Safety-net recompile of `CONTEXT_INDEX.json` and `CONTEXT_MAP.md`.

## 3. Universal Hook CLI Contract (Custom Hosts & Manual Pi .ts Wiring)
### 3.1 Five Lifecycle Modes
- `SessionStart` -> `netark-mcp hook --session-start-mode <dialect> --cwd .` (timeout 5s)
- `PreInvocation` *(optional)* -> `netark-mcp hook --pre-invocation-mode <dialect> --cwd .` (timeout 5s)
- `PreToolUse` -> `netark-mcp hook --hook-mode <dialect> --cwd .` (timeout 5s)
- `PostToolUse` -> `netark-mcp hook --post-hook-mode <dialect> --cwd .` (timeout 10s)
- `Stop` -> `netark-mcp hook --stop-mode <dialect> --cwd .` (timeout 10s)

### 3.2 Stdin JSON Payload (Flexible Keys)
- `workspacePaths`: `["<project_root>"]` (optional; overrides `--cwd`)
- Tool name: `toolCall.name` | `tool_name` | `tool` | `name`
- Tool args: `toolCall.args` | `toolCall.arguments` | `tool_input` | `args` | `arguments`
  - File path: `Path` | `path` | `file_path` | `TargetFile`
  - Content: `Content` | `content` | `Replacement` | `new_string`
  - Shell command: `CommandLine` | `command` | `cmd`

### 3.3 Three Output Dialects (`<dialect>`)
- `agy`: Always exits `0`; prints stdout JSON:
  - `PreToolUse`: `{"decision": "allow" | "ask" | "deny", "reason": "..."}`
  - `SessionStart`: `{"additionalContext": "..."}` | `PreInvocation`: `{"injectSteps": [{"ephemeralMessage": "..."}]}`
- `claude`: `allow` exits `0`; `ask` prints `{"permissionDecision": "ask", "message": "..."}` exits `0`; `deny` prints reason to `stderr` + `{"permissionDecision": "deny", "message": "..."}` to `stdout` and exits `2`.
- `pi` *(recommended for custom `.ts` extensions & shell wrappers)*: `allow` exits `0`; `deny`/`ask` prints reason to `stderr` and exits `2`. Spawn `netark-mcp hook --hook-mode pi --cwd <root>` with JSON on `stdin` and block whenever exit code != `0`.

### 3.4 Recommended Tool Matchers
- `PreToolUse`: file read/write/edit, shell/command execution, subagent dispatch, web fetch/search.
- `PostToolUse`: file write/edit.

## 4. Mandatory Post-Wiring Verification (Anti-Silent-Failure)
1. Show the generated host hook config or `.ts` extension to the human user for review.
2. Run 1 synthetic `PreToolUse` smoke test (do NOT touch disk):
   - Pipe `{"tool_name":"read_file","tool_input":{"path":".env"}}` into `netark-mcp hook --hook-mode <dialect> --cwd .` and verify `SEC-CRED` `deny` / exit `2` triggers.

## 5. Fallback (Hosts Without Shell `PreToolUse` Hooks)
- Wire `netark-mcp serve --cwd .` as the MCP server and copy NetArk's 3-tool (`netark_query`, `netark_record`, `netark_guard`) and security rules into the host's workspace rules file (e.g. `.cursorrules`).
