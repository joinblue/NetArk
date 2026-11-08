# 🗺️ NetArk × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)

> **自動生成時間**: `2026-11-08T15:12:03Z` | **Agentic Harness**: `NetArk` | **記憶節點總數**: `5`
> **漸進式揭露原則 (Progressive Disclosure)**: Agent 啟動時於 Turn 1 凍結注入 `@D/@C/@G` 代號壓縮地圖，按短代號 (`C0..Cn` / `000..900`) 或節點鍵值 (`node_key`) 按需調閱對應檔案。

## 0. Turn-1 凍結代號壓縮地圖 (`@D/@C/@G` Codebook Map)

```text
## 🧭 [NetArk Turn-1 Frozen Codebook Map] (Nodes: 5 | Scripts: 11 | Tier: L1-Full)
@D (Dirs): M=memory/ C=memory/codex/ E=memory/episodic/ H=schemas/ S=scripts/ X=.netark/extensions/ XS=.netark/extensions/subagent/
@M (Nodes):
  000=C:000_SOUL.md[000.SOUL.v1|verified] | 100=C:100_ARCH_RULES.md[100.ARCH-RULES.v1|verified] | 200=C:200_DECISIONS.md[200.ADR-001.v1|verified]
  300=M:LEDGER.md[300.LEDGER.v1|verified] | 900=E:HANDOVER.md[900.HANDOVER.v1|verified]
@C (Scripts):
  C0=H:schema_validator.py(L1-758) | C1=H:netark_guard_core.py(L1-399) | C2=S:auto_update_map.py(L1-1192)
  C3=S:sync_doc_metadata.py(L1-582) | C4=X:epistemic-gate.ts(L1-678) | C5=X:workspace-guard.ts(L1-863)
  C6=X:model-router.ts(L1-3283) | C7=X:session-handover.ts(L1-112) | C8=X:web-research.ts(L1-591)
  C9=XS:agents.ts(L1-157) | C10=XS:index.ts(L1-1185)
@G (Topology Graph — DAG / Governance Synapses / Code AST Imports):
  [DAG] 100 < 000 | 200 < 000,100 | 300 < 000 | 900 < 000
  [SYN] 000 => C0 | 100 => C1,C5 | 200 => C2,C4 | 900 => C4
  [AST] C2 -> C1,C0 | C3 -> C0 | C10 -> C9
💡 [Lookup Rule]: `<` 表示 depends_on，`=>` 表示記憶管轄腳本，`->` 表示程式碼 AST 引用；可直接用 `@D`+`@M`/`@C` 還原路徑，或呼叫 `query_library(query="200"|"C1")` 查閱完整中文摘要與符號。
```

## 1. 領域分層註冊表 (Domain Layer Registry)

### 📂 `000 Core Constitution & Soul (核心憲法與靈魂)` (1 節點)

| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `MEM-2026-0001` | `000.SOUL.v1` | `official` | `constitution` | `verified` | NetArk核心憲法：四級認知標籤、Official/Wiki雙軌制與反盲從Oracle鐵律 | [`memory/codex/000_SOUL.md`](../../memory/codex/000_SOUL.md) |

### 📂 `100 System Architecture & Security Guardrails (系統架構與安全護欄)` (1 節點)

| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `MEM-2026-0002` | `100.ARCH-RULES.v1` | `official` | `rule` | `verified` | 邊界與零外洩護欄：工作區鎖定、.netark保護、SEC-CRED與Pre-Write防呆 | [`memory/codex/100_ARCH_RULES.md`](../../memory/codex/100_ARCH_RULES.md) |

### 📂 `200 Architecture Decisions & Epistemic Governance (架構決策與認識論治理)` (1 節點)

| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `MEM-2026-0003` | `200.ADR-001.v1` | `official` | `adr` | `verified` | 架構決策錄：採用雙層可攜式大腦、Turn-1代號壓縮地圖與確定性邊界防禦 | [`memory/codex/200_DECISIONS.md`](../../memory/codex/200_DECISIONS.md) |

### 📂 `300 Core Domain Logic & Active Ledger (核心領域邏輯與活躍台帳)` (1 節點)

| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `MEM-2026-0004` | `300.LEDGER.v1` | `official` | `spec` | `verified` | 專案唯一活躍工單台帳 (<=80行) | [`memory/LEDGER.md`](../../memory/LEDGER.md) |

### 📂 `900 Episodic Handover & Historical Archives (情節交接與歷史封存)` (1 節點)

| 節點 ID (`node_id`) | 定位鍵 (`node_key`) | 軌道 (`track`) | 類型 (`type`) | 狀態 (`status`) | 單行摘要 (`summary_1line`) | 檔案路徑 (`path`) |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `MEM-2026-0005` | `900.HANDOVER.v1` | `wiki` | `digest` | `verified` | 微對話無縫交接快照 (<=65行) | [`memory/episodic/HANDOVER.md`](../../memory/episodic/HANDOVER.md) |

## 2. 因果拓撲依賴邊 (Causal Topology DAG Edges)

| 下游節點 (`from`) | 依賴關係 (`relation`) | 上游基礎節點 (`to`) |
| :--- | :---: | :--- |
| `MEM-2026-0004` | `depends_on` | `MEM-2026-0001` |
| `MEM-2026-0002` | `depends_on` | `MEM-2026-0001` |
| `MEM-2026-0003` | `depends_on` | `MEM-2026-0001` |
| `MEM-2026-0003` | `depends_on` | `MEM-2026-0002` |
| `MEM-2026-0005` | `depends_on` | `MEM-2026-0001` |

## 3. 程式碼模組依賴圖 (Code-Level AST Dependency Graph)

| 來源模組 (`from`) | 目標依賴 (`to`) | 依賴類型 (`type`) |
| :--- | :--- | :---: |
| `scripts/auto_update_map.py` | `schemas/netark_guard_core.py` | `py_from_import` |
| `scripts/auto_update_map.py` | `schemas/schema_validator.py` | `py_from_import` |
| `scripts/sync_doc_metadata.py` | `schemas/schema_validator.py` | `py_import` |
| `.netark/extensions/epistemic-gate.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/model-router.ts` | `@earendil-works/pi-ai` | `ts_sdk_import` |
| `.netark/extensions/model-router.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/workspace-guard.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/subagent/agents.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-agent-core` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-ai` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-tui` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `.netark/extensions/subagent/agents.ts` | `ts_local_import` |

### 3.2 源碼符號、Hook 註冊與規格影響圈總表 (Code Intelligence & Impact Map)

| 源碼路徑 (`file_path`) | 主要符號與行號 (`symbols`) | Pi 擴充註冊 (`command`/`tool`/`hook`) | 影響圈 (`imported_by`) | 綁定規格 (`governing_specs`) |
| :--- | :--- | :--- | :--- | :--- |
| `.netark/extensions/epistemic-gate.ts` | `CATALOG_STAGE2_THRESHOLD`(L19-L19), `CODE_SOFT_LINE_LIMIT`(L20-L20), `CODE_HARD_LINE_LIMIT`(L21-L21), `readHandoverBodySnapshot`(L23-L23), `buildProgressiveContextSummary`(L41-L41), `findAffectedMemoryNodes`(L150-L150) | `tool:query_library`(L384), `hook:session_shutdown`(L406), `hook:session_start`(L490), `hook:before_agent_start`(L495), `hook:tool_call`(L509), `hook:tool_result`(L551) | — | `200.ADR-001.v1`, `900.HANDOVER.v1` |
| `.netark/extensions/model-router.ts` | `NetArkEpistemicBridge`(L32-L32), `DEFAULT_ROLE_MODELS`(L79-L79), `RoleName`(L89-L89), `SpecialistRole`(L90-L90), `StrategyMode`(L91-L91), `ROLE_FALLBACK_CHAINS`(L94-L94) | `hook:session_start`(L1104), `hook:session_shutdown`(L1109), `hook:turn_start`(L1181), `hook:before_agent_start`(L1185), `hook:tool_call`(L1305), `tool:dispatch_specialist`(L1429) | — | — |
| `.netark/extensions/session-handover.ts` | `HANDOVER_SOFT_THRESHOLD`(L15-L15), `HANDOVER_HARD_THRESHOLD`(L16-L16), `HANDOVER_REMIND_STEP_TOKENS`(L17-L17), `buildHandoverMandateMessage`(L19-L19), `sessionHandoverExtension`(L46-L46) | `hook:session_start`(L50), `command:/handover`(L55), `hook:before_agent_start`(L73) | — | — |
| `.netark/extensions/subagent/agents.ts` | `AgentScope`(L9-L9), `AgentConfig`(L11-L11), `AgentDiscoveryResult`(L21-L21), `discoverAgents`(L128-L128), `formatAgentList`(L149-L149) | — | `.netark/extensions/subagent/index.ts` | — |
| `.netark/extensions/subagent/index.ts` | — | `tool:subagent`(L578) | — | — |
| `.netark/extensions/web-research.ts` | `OutboundCheckResult`(L5-L5), `WebPageSnippet`(L10-L10), `NemotronGuardVerdict`(L17-L17), `IPI_DETERMINISTIC_RE`(L32-L32), `validateOutboundSafety`(L35-L35), `loadNvidiaApiKeys`(L74-L74) | `tool:web_research`(L513) | — | — |
| `.netark/extensions/workspace-guard.ts` | `formatRemediation`(L128-L128), `parseShellCommandQuoteAware`(L140-L140), `isReadOnlyBashCommand`(L266-L266), `checkPortabilityViolation`(L354-L354), `extractPathsFromBash`(L404-L404) | `hook:session_start`(L597), `hook:user_bash`(L603), `hook:tool_call`(L627), `command:/guard`(L802) | — | `100.ARCH-RULES.v1` |
| `schemas/netark_guard_core.py` | `_is_printable_text`(L47-L52), `normalize_and_deobfuscate`(L55-L97), `calculate_shannon_entropy`(L100-L107), `load_enterprise_policy`(L110-L120), `scan_plaintext_secrets`(L123-L150), `redact_sensitive_payload`(L156-L174) | — | `scripts/auto_update_map.py` | `100.ARCH-RULES.v1` |
| `schemas/schema_validator.py` | `load_valid_taxonomy_codes`(L66-L86), `parse_markdown_frontmatter`(L96-L111), `count_prose_lines`(L114-L140), `check_as05_portability`(L143-L152), `load_all_memory_nodes`(L155-L169), `check_as06_node_exclusivity`(L172-L211) | — | `scripts/auto_update_map.py`, `scripts/sync_doc_metadata.py` | `000.SOUL.v1` |
| `scripts/auto_update_map.py` | `get_brain_rel_dir`(L84-L92), `load_domain_layers`(L95-L117), `extract_wikilinks_outside_fenced_blocks`(L120-L132), `sha256_file`(L135-L136), `discover_workspace_code_files`(L139-L175), `heal_dead_links`(L178-L243) | — | — | `200.ADR-001.v1` |
| `scripts/sync_doc_metadata.py` | `split_frontmatter_raw`(L52-L59), `surgical_set_scalar`(L62-L88), `surgical_remove_from_yaml_list`(L91-L151), `render_role_models_ssot_block`(L154-L182), `compute_actual_epistemic_counts`(L185-L190), `load_all_node_paths`(L193-L216) | — | — | — |

## 4. 專案治理目錄結構摘要

- `.netark/` — 專案內嵌可攜式 NetArk Agentic Harness 大腦（含模型路由、安全護欄、漸進式揭露與 5 角色子代理）
- `schemas/` — 記憶節點標頭 (`artifact_header.schema.json`)、Context 拓撲節點 (`context_node.schema.json`)、Tier 0 AST 護欄 (`netark_guard_core.py`) 與防諂媚驗證器 (`schema_validator.py`)
- `memory/codex/` — 核心架構規範 (`000_SOUL.md`, `100_ARCH_RULES.md`, `200_DECISIONS.md`) 與自動編譯總目錄 (`CONTEXT_MAP.md`)
- `memory/LEDGER.md` — 專案唯一活躍工單台帳 (`<= 80` 行)
- `memory/episodic/HANDOVER.md` — 微對話無縫交接快照 (`<= 65` 行)
- `memory/index/CONTEXT_INDEX.json` — 機器可讀之漸進式揭露與 `@D/@C/@G` 代號壓縮索引
- `scripts/` — 索引編譯器 (`auto_update_map.py`)、跨宿主守護程序 (`netark_guard_daemon.py`)、母版安裝器 (`netark_init.py`) 與自動化驗收套件
