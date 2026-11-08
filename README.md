# ⚓ NetArk (`N.E.T.A.R.K.`) — Clean-Room V1 Agentic Engineering Kernel

> **Language / 語言**: **English** | [繁體中文](README.zh-TW.md)

**N**etwork-shielded, **E**nforced-**T**emplate **A**rchival & **R**ule-indexed **K**ernel (`NetArk`) is a portable, multi-host Agentic Engineering & Epistemic Governance Engine for **Pi Coding Agent**, **Google Antigravity (AGY)**, and **Claude Code**.

---

## 🌟 Core Architecture Pillars

1. **Two-Layer Portable Brain (`.netark/` + `memory/`)**
   - **Execution Brain (`.netark/`)**: Portable extensions, subagent roles (`scout`, `architect`, `challenger`, `worker`, `auditor`), model routing (`role-models.json`), and zero-trust workspace guardrails.
   - **Governed Memory Graph (`memory/`)**: Clean 5-node starting foundation (`000_SOUL.md`, `100_ARCH_RULES.md`, `200_DECISIONS.md`, `LEDGER.md`, `HANDOVER.md`) enforced by an external deterministic Oracle (`schemas/schema_validator.py`).

2. **Turn-1 Frozen `@D/@M/@C/@G` Codebook Topology Map (~94% Token Compression)**
   - Compiled automatically by `scripts/auto_update_map.py` into `memory/index/CONTEXT_INDEX.json`.
   - Injects a compact directory dictionary (`@D`), memory node dictionary (`@M`), script coordinate dictionary (`@C`), and 3-layer Dashboard topology graph (`@G`: `[DAG]` causal links, `[SYN]` governance synapses, `[AST]` code imports) at Turn 1 for 100% Prefix KV-Cache hit rates.
   - Scales automatically across **L1-Full** ($\le 150$ scripts), **L2-Cluster** ($151\sim1,500$ scripts), and **L3-ActiveCone** ($> 1,500$ scripts).

3. **3-Tier Local Security Guard & Vaultless DLP (`G-01` ~ `G-05` Hardened)**
   - **Tier 0 (`schemas/netark_guard_core.py`)**: Three-stage structural AST (`shlex` quote coalescing, subshell unwrapping, inline `python -c` `ast.parse`), workspace confinement, control-plane protection (`.netark/`, `.agents/`, `.claude/`, `schemas/`), `*vault*.json` & `.env*` hard block (`G-01`), and pre-write secret lint (`SEC-PREWRITE-SECRET`, `G-02`/`G-04`).
   - **Tier 1 (`scripts/netark_guard_daemon.py`)**: Local ONNX CPU classifier (`Llama-Prompt-Guard-2-22M`) with zero-VRAM heuristic fallback and developer Fast-Path bypass.
   - **Tier 2**: Pluggable OpenAI-compatible semantic guardian slot with HMAC-SHA256 chained SOC2 audit logging (`.netark/audit/soc2_audit.jsonl`).

4. **Standalone PM Control Center (`dashboard/` — V1.1)**
   - Zero-dependency HTTP/HTTPS dual-protocol visual war room (`python3 dashboard/backend/server.py 8765`) featuring Structure Tree, 4-Lane Causal Graph View, Ledger & Handover Kanban, and Code Line-Budget Health Monitor.

---

## 🚀 Quick Start

### 1. Bootstrap Current or External Workspace (`netark_init.py`)

```bash
# Initialize all host adapters (Pi + AGY + Claude) with Traditional Chinese memory templates
python3 scripts/netark_init.py --target all --lang zh-TW --cwd /path/to/your-project

# Or initialize with English memory templates
python3 scripts/netark_init.py --target all --lang en --cwd /path/to/your-project
```

### 2. Launch with Pi Coding Agent

```bash
export PI_CODING_AGENT_DIR="$(pwd)/.netark"
cp .netark/auth.example.json .netark/auth.json
# Configure your API keys via `.netark/auth.json` or interactive `/mode` inside Pi
pi
```

### 3. Launch Standalone Visual Dashboard

```bash
npm run dashboard
# Or directly via Python:
python3 dashboard/backend/server.py 8765
```

---

## 🧪 Deterministic Verification Suite

Run all 5 built-in verification suites before committing:

```bash
# 1. Tier 0 AST & G-01..G-05 DLP Self-Test
python3 schemas/netark_guard_core.py --self-test

# 2. Multi-Host Daemon & Pre-Write Secret Lint Self-Test
python3 scripts/netark_guard_daemon.py --self-test

# 3. Codebook Map Compiler & Schema Oracle
python3 scripts/auto_update_map.py --print-codebook
python3 schemas/schema_validator.py --run-oracle

# 4. Dashboard Shards Contract Suite
python3 dashboard/tests/test_dashboard_shards.py

# 5. Full Harness & Enterprise Guard E2E Suites
python3 scripts/test_netark_harness.py
python3 scripts/test_netark_enterprise_guard.py
```

---

## ⚖️ License

Dual-licensed under the **Prosperity Public License 3.0.0** ([LICENSE](LICENSE)) and the **NetArk Commercial License** ([COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). Contributions are governed by [CLA.md](CLA.md).
