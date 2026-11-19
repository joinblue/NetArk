# NetArk Security Guardrails & Remediation Reference

NetArk enforces a **deterministic, local-first defense architecture** inside `netark-mcp hook` (Tier 0 pure Python stdlib). Every blocked action returns a machine-readable guard code, `[RuleDoc]`, and `[SuggestedAlternative]` so AI coding agents can self-correct on the next tool call.

---

## 1. Two-Layer Defense Architecture

### Layer 1: Immutable Core Constitution (Cannot Be Disabled via Policy)
- **Credential & Vault Protection (`SEC-CRED`)**: Blocks reading, writing, or shell-redirecting `.env*`, `auth.json`, `*vault*.json`, private key files, and inline obfuscation attempts (`cat .e"n"v`, `python3 -c "open('.env')"`).
- **Pre-Write Secret DLP (`SEC-PREWRITE-SECRET` / `SEC-DLP-EGRESS`)**: Scans outbound network commands and file writes across raw text, Unicode zero-width stripped text, and Base64/Hex/URL-decoded layers for 12+ credential patterns (AWS keys, OpenAI `sk-*`, GitHub `ghp_*`, Anthropic, PEM headers, etc.) plus high-entropy strings.
- **Destructive Shell AST Inspection (`SEC-CMD-01..06`, `SEC-EXFIL-01`)**: Tokenizes shell pipelines, subshells (`$(...)`, backticks), and inline `python3 -c` ASTs to stop `rm -rf /`, disk formatting (`mkfs`, `dd of=/dev/`), `curl | sh`, fork bombs, and environment-variable exfiltration.
- **Session Vault Disabled**: `session_vault_disabled` is forced to `true` — NetArk never stores plaintext secrets locally.

### Layer 2: Workspace Customizable Policy (`enterprise-policy.json`)
`netark-mcp init` generates `.agents/enterprise-policy.json` (for AGY) or `.netark/enterprise-policy.json` (for `.mcp.json` / Claude / Pi) so teams can tailor project rules without touching Python code:

| Policy Field | Default | Purpose |
| :--- | :--- | :--- |
| `prewrite_secret_lint` | `true` | Enable secret scanning on `write_file` / `edit_file` payloads |
| `custom_redact_literals` | `[]` | Exact sensitive literals to redact/block in your organization |
| `custom_secret_patterns` | `[]` | Custom regex rules (`{"name": "...", "pattern": "..."}`) |
| `protected_paths` | `[".netark/", ".agents/", ".claude/", ".github/workflows/", "schemas/"]` | Control-plane paths requiring human confirmation (`ask`) |
| `entropy_threshold` / `entropy_min_token_len` | `4.35` / `24` | Shannon entropy sensitivity for unknown token detection |
| `ssrf_allowed_hosts` | `[]` | Internal/loopback host allowlist for local development |
| `approved_code_roots` | `["projects", "scratch", "schemas", "scripts", "dashboard", "templates", "src", "tests", ...]` | Top-level directories permitted to contain code files |
| `project_subdirs` | `["src", "scripts", "tests", "configs"]` | Required subdirectories under `projects/<project_id>/` |
| `max_direct_read_lines` / `max_salami_slices_per_file` | `300` / `2` | Prevents context bloat from giant file dumps or salami-slicing |
| `enforce_stub_first_for_new_modules` / `stub_first_edit_delta_lines` | `true` / `25` | Requires a `stub_ready` or `verified` spec before creating/refactoring governed modules |

---

## 2. Guard Codes & Standard Remediation Table

| Guard Code | Trigger Condition | `[SuggestedAlternative]` Remediation |
| :--- | :--- | :--- |
| **`SEC-CRED`** | Attempted read/write/grep/shell-redirect on `.env*`, `auth.json`, `*vault*.json`, or key files | Stop accessing the secret file directly; ask the user to configure environment variables and read via `os.environ.get(...)`. |
| **`SEC-PREWRITE-SECRET`** | Hardcoded API key, private key, or secret connection string detected in write content | Replace literal secrets with `os.environ.get("KEY_NAME")` before retrying the write. |
| **`SEC-CONTROL-PLANE`** | Attempted direct edit of `.agents/`, `.claude/`, `.github/workflows/`, `.netark/`, or `schemas/` | Triggers interactive human confirmation (`ask`); wait for user approval rather than bypassing. |
| **`SEC-CODE-PLACEMENT`** | Writing `.py`/`.ts`/`.js`/`.sh` into workspace root, unapproved root folders, or `scratch/` without `test_`/`probe_`/`debug_`/`tmp_` prefix | Move business code to `projects/<id>/{src,scripts,tests,configs}/` (or `src/`), or name scratch scripts `scratch/test_<name>.py`. |
| **`SEC-SSRF` / `SEC-XPIA-WEB` / `SEC-WEB-SECRET-QUERY`** | Outbound URL targets private/loopback/metadata IPs (`169.254.*`, `127.0.0.1`), non-HTTP schemes, secret query params, or deterministic prompt injection strings | Use public `https://` endpoints, remove tokens from URLs, or explicitly allowlist trusted dev hosts in `ssrf_allowed_hosts`. |
| **`CODE-ARROW-NESTING` / `CODE-NESTED-LOOPS`** | Python AST control-flow nesting exceeds `4` layers or nested loops exceed depth limit | Refactor with early returns (`if not cond: return`) or extract helper functions. |
| **`CODE-SILENT-EXCEPT`** | Bare/broad `except: pass` or `except Exception: pass` without `# noqa: silent-except` | Handle or log specific exception classes instead of silently swallowing errors. |
| **`CODE-GOD-FUNCTION` / `MODULARITY-GATE`** | Function exceeds effective line budget or module exceeds target `400` / hard `550` line cap | Split cohesive responsibilities into well-named modules or helpers. |
| **`SIDECAR-GATE`** | Reading `> 300` lines directly, exceeding `2` salami-slices on a large file, or dumping via `cat`/`head`/`sed` | Use `netark_query` / `CONTEXT_MAP.md` line ranges for targeted `<= 300`-line reads or delegate to a read-only research subagent. |
| **`SPEC-RIBC-GATE`** | Dispatching an implementation subagent without `[R]` Role/Path, `[I]` Invariants, `[B]` Boundaries, `[C]` Contracts & `>= 60` chars | Include all 4 RIBC sections and sufficient detail before invoking the subagent. |
| **`MCP-PROB-01-REDIRECT`** | Direct file write/edit to `memory/**/*.md` (excluding `CONTEXT_MAP.md`) while Hook mode is active | Use MCP tool `netark_record(intent, title, body, mode="preflight" | "write")` so frontmatter, checksums, and indices stay synchronized. |
| **`STUB-FIRST-GATE` / `SPEC-BLUEPRINT-REQUIRED`** | Creating or editing `>= 25` lines of a governed module without an active `stub_ready`/`verified` spec, or creating a complex spec without `parent_blueprint` | Advance the parent blueprint and shard spec via `netark_record` to `stub_ready` before implementing module code. |
| **`SPEC-AST-SYNC-GATE`** | Spec declares `affected_paths` / `stub_paths` pointing to existing code without referencing real AST symbols or marking `new` / `stub` | Query or inspect the file's real symbols and cite exact symbol names (or mark new functions as `stub`/`新增`). |
| **`SEC-HANDOVER-OVERWRITE`** | Overwriting an active `HANDOVER.md` with an unrelated task before closure | Create a track-specific `HANDOVER_<TRACK>.md` or close the active handover first. |
