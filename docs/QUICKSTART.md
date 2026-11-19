# NetArk (`netark-mcp`) Quickstart Guide

NetArk is packaged as a zero-dependency Python CLI & stdio MCP server (`requires-python >= 3.10`, `dependencies = []`). Target business repositories stay completely clean with **0 `.py` runtime files** copied into your codebase.

---

## 1. Install `netark-mcp`

### Option A: Install Globally via `uv` (Recommended for Hooks + MCP)
Installing via `uv tool install` places an isolated, native-speed shim on your `PATH`, ideal for frequent `PreToolUse` hook invocations (`~62ms`):

```bash
# From PyPI (recommended)
uv tool install netark-mcp

# Or directly from GitHub
# uv tool install git+https://github.com/joinblue/NetArk
```

### Option B: Ephemeral Execution via `uvx` (MCP-Only)
If you only want to run the 3-tool MCP server without permanent installation:

```json
{
  "mcpServers": {
    "netark": {
      "command": "uvx",
      "args": ["netark-mcp", "serve", "--cwd", "."]
    }
  }
}
```

---

## 2. Initialize Your Project (`4 Integration Modes`)

Navigate to your target repository and choose the integration depth you need:

### Mode 1: Zero-Intrusion Memory & MCP Only (Default)
Creates/merges `.mcp.json`, policy config, and bootstraps the 5-node `memory/` starter core (`000_SOUL.md`, `100_ARCH_RULES.md`, `200_DECISIONS.md`, `LEDGER.md`, `HANDOVER.md`) without touching host-specific hook folders or root `AGENTS.md` / `CLAUDE.md`:

```bash
cd /path/to/your-project
netark-mcp init --cwd .
# Use --lang en for English starter memory templates (default: zh-TW)
netark-mcp init --lang en --cwd .
```

### Mode 2: Claude Code (MCP + Native Lifecycle Hooks)
Wires `.mcp.json`, `.claude/settings.json` (`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop`), slash commands in `.claude/commands/`, and `memory/`:

```bash
netark-mcp init --target claude --lang en --cwd .
# Pass --write-rules only if you also want a root CLAUDE.md template
netark-mcp init --target claude --lang en --write-rules --cwd .
```

### Mode 3: Google Antigravity (`agy` — MCP + Hooks + Workflows/Skills)
Wires `.agents/hooks.json`, `.agents/plugins/netark/mcp_config.json`, `.agents/enterprise-policy.json`, `.agents/skills/`, `.agents/workflows/`, and `memory/`:

```bash
netark-mcp init --target agy --lang en --cwd .
# Pass --write-rules only if you also want a root AGENTS.md template
```

### Mode 4: Pi Agent (`.ts`) & Custom MCP Hosts
1. Wire `netark-mcp serve --cwd .` in your host's MCP configuration.
2. Have your coding agent call `netark_guard(action="setup")` (or read [HOOK_CONTRACT.md](HOOK_CONTRACT.md)) to receive the Universal Hook CLI Contract with the `agy`, `claude`, and `pi` stdin/stdout dialects.
3. For Pi Agent `.ts` extensions or shell wrappers, spawn `netark-mcp hook --hook-mode pi --cwd <root>` with tool JSON on `stdin` and block whenever exit code `!= 0`.

---

## 3. Non-Destructive Merge Guarantees & Clean Uninstall

- **Existing Memory Preserved**: `netark-mcp init` never overwrites existing Markdown nodes in `memory/`.
- **Existing Hooks & Env Preserved**: Host `.mcp.json`, `.claude/settings.json`, and `.agents/hooks.json` are merged non-destructively — your unrelated MCP servers, environment variables, and custom hooks stay intact.
- **Absolute Binary Locking**: `init` resolves and records the absolute path to `netark-mcp` so GUI IDEs do not fail with `ENOENT`.
- **Clean Uninstall**: Remove NetArk hooks and MCP wiring while preserving your `memory/` directory by default:

```bash
netark-mcp uninstall --target all --cwd .
# Add --purge-memory only if you explicitly want to delete memory/
```

---

## 4. Verify Installation (30-Second Smoke Test)

Verify both the `PreToolUse` secret block and the full-repo schema/DAG oracle:

```bash
# 1. Synthetic PreToolUse smoke test (does not touch disk)
echo '{"tool_name":"read_file","tool_input":{"path":".env"}}' | netark-mcp hook --hook-mode claude --cwd .
# Expected: exit code 2 + SEC-CRED block

# 2. Compile & print Turn-1 compressed @D/@M/@C/@G Codebook Map
netark-mcp hook --query "" --cwd .
```
