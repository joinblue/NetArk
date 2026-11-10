# 🗺️ NetArk × NetArk Context Registry & Topology Map (CONTEXT_MAP.md)

> **自動生成時間**: `2026-11-10T15:06:04Z` | **Agentic Harness**: `NetArk` | **記憶節點總數**: `5`
> **漸進式揭露原則 (Progressive Disclosure)**: Agent 啟動時於 Turn 1 凍結注入 `@D/@C/@G` 代號壓縮地圖，按短代號 (`C0..Cn` / `000..900`) 或節點鍵值 (`node_key`) 按需調閱對應檔案。

## 0. Turn-1 凍結代號壓縮地圖 (`@D/@C/@G` Codebook Map)

```text
## 🧭 [NetArk Turn-1 Frozen Codebook Map] (Nodes: 5 | Scripts: 21 | Tier: L1-Full)
@D (Dirs): M=memory/ C=memory/codex/ E=memory/episodic/ H=schemas/ S=scripts/ X=.netark/extensions/ XS=.netark/extensions/subagent/
@R (Write Route): 開架知識庫(領域百科wiki/操作指南sop/詞彙表glossary/討論與備忘錄note)->W(memory/wiki/)[310-499,免雙審自動補標頭] | 抓蟲/修復藍帖->A(memory/audits/)[type:audit] | 已拍板新規格->P(memory/specs/)[type:spec] | 活躍工單->M:LEDGER.md | 臨時草稿->scratch/ (未定案嚴禁建spec；修Bug嚴禁塗改舊藍圖) | 生命週期: draft(規劃/施工中) -> verified(實測通過定稿) -> archived(討論筆記已收斂升級封存，保留 depends_on 脈絡但過濾 @M 視野) / deprecated(路線廢棄)
@M (Nodes):
  000=C:000_SOUL.md[000.SOUL.v1|verified] | 100=C:100_ARCH_RULES.md[100.ARCH-RULES.v1|verified] | 200=C:200_DECISIONS.md[200.ADR-001.v1|verified]
  300=M:LEDGER.md[300.LEDGER.v1|verified] | 900=E:HANDOVER.md[900.HANDOVER.v1|verified]
@C (Scripts):
  C0=H:schema_validator.py(L1-369) | C1=H:netark_guard_core.py(L1-399) | C2=H:code_hygiene_ast.py(L1-256)
  C3=H:codebook_compiler.py(L1-322) | C4=H:topology_graph.py(L1-234) | C5=H:doc_initializer.py(L1-205)
  C6=S:auto_update_map.py(L1-349) | C7=S:netark_guard_daemon.py(L1-391) | C8=S:netark_init.py(L1-319)
  C9=S:sync_doc_metadata.py(L1-304) | C10=X:epistemic-gate.ts(L1-328) | C11=X:workspace-guard.ts(L1-350)
  C12=X:model-router.ts(L1-3283) | C13=X:session-handover.ts(L1-112) | C14=X:web-research.ts(L1-591)
  C15=X:epistemic-library-tools.ts(L1-298) | C16=X:guard-shell-parser.ts(L1-265) | C17=XS:agents.ts(L1-157)
  C18=XS:index.ts(L1-1185) | C19=S:test_netark_enterprise_guard.py(L1-314) | C20=S:test_netark_harness.py(L1-261)
@G (Topology Graph — DAG / Governance Synapses / Code AST Imports):
  [DAG] 100 < 000 | 200 < 000,100 | 300 < 000 | 900 < 000
  [SYN] 000 => C0 | 100 => C1,C7,C11 | 200 => C6,C8,C10 | 900 => C10
  [AST] C0 -> C4 | C2 -> C4 | C3 -> C2 | C5 -> C0 | C6 -> C2,C3,C1,C0 | C7 -> C2,C1 | C9 -> C0,C5 | C10 -> C15 | C11 -> C16 | C18 -> C17 | C19 -> C1,C7,C8 | C20 -> C2,C0,C7
  [HYG-AST] Python functions max control-flow nesting <= 4 layers (use Early-Return); NEVER write silent 'except: pass' without '# noqa: silent-except'; target file size <= 400 lines (hard cap 550).
  [HYG-DEBUG] On bug/unexpected return, NEVER patch locally with nested if/try; trace backward [Return Point -> Call Chain -> Entry Input] and add Fail-Fast validation at entry.
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
| `schemas/code_hygiene_ast.py` | `schemas/topology_graph.py` | `py_from_import` |
| `schemas/codebook_compiler.py` | `schemas/code_hygiene_ast.py` | `py_from_import` |
| `schemas/doc_initializer.py` | `schemas/schema_validator.py` | `py_import` |
| `schemas/schema_validator.py` | `schemas/topology_graph.py` | `py_from_import` |
| `scripts/auto_update_map.py` | `schemas/code_hygiene_ast.py` | `py_from_import` |
| `scripts/auto_update_map.py` | `schemas/codebook_compiler.py` | `py_from_import` |
| `scripts/auto_update_map.py` | `schemas/netark_guard_core.py` | `py_from_import` |
| `scripts/auto_update_map.py` | `schemas/schema_validator.py` | `py_from_import` |
| `scripts/netark_guard_daemon.py` | `schemas/code_hygiene_ast.py` | `py_from_import` |
| `scripts/netark_guard_daemon.py` | `schemas/netark_guard_core.py` | `py_from_import` |
| `scripts/sync_doc_metadata.py` | `schemas/schema_validator.py` | `py_import` |
| `scripts/sync_doc_metadata.py` | `schemas/doc_initializer.py` | `py_from_import` |
| `scripts/test_netark_enterprise_guard.py` | `schemas/netark_guard_core.py` | `py_from_import` |
| `scripts/test_netark_enterprise_guard.py` | `scripts/netark_guard_daemon.py` | `py_from_import` |
| `scripts/test_netark_enterprise_guard.py` | `scripts/netark_init.py` | `py_from_import` |
| `scripts/test_netark_harness.py` | `schemas/code_hygiene_ast.py` | `py_from_import` |
| `scripts/test_netark_harness.py` | `schemas/schema_validator.py` | `py_from_import` |
| `scripts/test_netark_harness.py` | `scripts/netark_guard_daemon.py` | `py_from_import` |
| `.netark/extensions/epistemic-gate.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/epistemic-gate.ts` | `.netark/extensions/epistemic-library-tools.ts` | `ts_local_import` |
| `.netark/extensions/epistemic-library-tools.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/model-router.ts` | `@earendil-works/pi-ai` | `ts_sdk_import` |
| `.netark/extensions/model-router.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/workspace-guard.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/workspace-guard.ts` | `.netark/extensions/guard-shell-parser.ts` | `ts_local_import` |
| `.netark/extensions/subagent/agents.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-agent-core` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-ai` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-coding-agent` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `@earendil-works/pi-tui` | `ts_sdk_import` |
| `.netark/extensions/subagent/index.ts` | `.netark/extensions/subagent/agents.ts` | `ts_local_import` |

### 3.2 源碼符號、Hook 註冊與規格影響圈總表 (Code Intelligence & Impact Map)

| 源碼路徑 (`file_path`) | 主要符號與行號 (`symbols`) | Pi 擴充註冊 (`command`/`tool`/`hook`) | 影響圈 (`imported_by`) | 綁定規格 (`governing_specs`) |
| :--- | :--- | :--- | :--- | :--- |
| `.netark/extensions/epistemic-gate.ts` | `CATALOG_STAGE2_THRESHOLD`(L23-L23), `CODE_SOFT_LINE_LIMIT`(L24-L24), `CODE_HARD_LINE_LIMIT`(L25-L25), `readHandoverBodySnapshot`(L27-L27), `buildProgressiveContextSummary`(L44-L44), `getSessionPinnedContextSummary`(L144-L144) | `hook:session_shutdown`(L184), `hook:session_start`(L193), `hook:before_agent_start`(L198), `hook:tool_call`(L205), `hook:tool_result`(L240) | — | `200.ADR-001.v1`, `900.HANDOVER.v1` |
| `.netark/extensions/epistemic-library-tools.ts` | `findAffectedMemoryNodes`(L19-L19), `queryLibraryNodes`(L62-L62), `queryCodeIntelligenceMap`(L177-L177), `runSessionShutdownConsolidation`(L212-L212), `registerEpistemicLibraryTools`(L261-L261) | `tool:query_library`(L265), `tool:code_intelligence_map`(L283) | `.netark/extensions/epistemic-gate.ts` | — |
| `.netark/extensions/guard-shell-parser.ts` | `FILE_TOOLS`(L14-L14), `SECRET_FILE_PATTERNS`(L16-L16), `PREWRITE_SECRET_PATTERNS`(L27-L27), `DESTRUCTIVE_BASH_PATTERNS`(L42-L42), `SAFE_SYSTEM_PREFIXES`(L56-L56), `READ_ONLY_COMMANDS`(L58-L58) | — | `.netark/extensions/workspace-guard.ts` | — |
| `.netark/extensions/model-router.ts` | `NetArkEpistemicBridge`(L32-L32), `DEFAULT_ROLE_MODELS`(L79-L79), `RoleName`(L89-L89), `SpecialistRole`(L90-L90), `StrategyMode`(L91-L91), `ROLE_FALLBACK_CHAINS`(L94-L94) | `hook:session_start`(L1104), `hook:session_shutdown`(L1109), `hook:turn_start`(L1181), `hook:before_agent_start`(L1185), `hook:tool_call`(L1305), `tool:dispatch_specialist`(L1429) | — | — |
| `.netark/extensions/session-handover.ts` | `HANDOVER_SOFT_THRESHOLD`(L15-L15), `HANDOVER_HARD_THRESHOLD`(L16-L16), `HANDOVER_REMIND_STEP_TOKENS`(L17-L17), `buildHandoverMandateMessage`(L19-L19), `sessionHandoverExtension`(L46-L46) | `hook:session_start`(L50), `command:/handover`(L55), `hook:before_agent_start`(L73) | — | — |
| `.netark/extensions/subagent/agents.ts` | `AgentScope`(L9-L9), `AgentConfig`(L11-L11), `AgentDiscoveryResult`(L21-L21), `discoverAgents`(L128-L128), `formatAgentList`(L149-L149) | — | `.netark/extensions/subagent/index.ts` | — |
| `.netark/extensions/subagent/index.ts` | — | `tool:subagent`(L578) | — | — |
| `.netark/extensions/web-research.ts` | `OutboundCheckResult`(L5-L5), `WebPageSnippet`(L10-L10), `NemotronGuardVerdict`(L17-L17), `IPI_DETERMINISTIC_RE`(L32-L32), `validateOutboundSafety`(L35-L35), `loadNvidiaApiKeys`(L74-L74) | `tool:web_research`(L513) | — | — |
| `.netark/extensions/workspace-guard.ts` | — | `hook:session_start`(L134), `hook:user_bash`(L154), `hook:tool_call`(L169), `command:/guard`(L301) | — | `100.ARCH-RULES.v1` |
| `schemas/code_hygiene_ast.py` | `get_brain_rel_dir`(L31-L38), `_max_cf_depth`(L41-L60), `_is_silent_except_body`(L63-L67), `check_python_ast_hygiene`(L70-L100), `discover_workspace_code_files`(L103-L127), `_add_py_edge`(L130-L134) | — | `schemas/codebook_compiler.py`, `scripts/auto_update_map.py`, `scripts/netark_guard_daemon.py`, `scripts/test_netark_harness.py` | — |
| `schemas/codebook_compiler.py` | `_select_codebook_scripts`(L21-L41), `_build_node_short_map`(L44-L61), `_collect_governed_script_codes`(L64-L77), `compile_codebook_map`(L80-L237), `render_context_map`(L243-L308), `render_private_context_map`(L314-L319) | — | `scripts/auto_update_map.py` | — |
| `schemas/doc_initializer.py` | `_compute_epistemic_counts`(L31-L35), `_scan_max_node_seq_in_file`(L38-L52), `allocate_next_node_id`(L55-L60), `init_memory_node`(L63-L185), `auto_initialize_wiki_node`(L191-L205) | — | `scripts/sync_doc_metadata.py` | — |
| `schemas/netark_guard_core.py` | `_is_printable_text`(L47-L52), `normalize_and_deobfuscate`(L55-L97), `calculate_shannon_entropy`(L100-L107), `load_enterprise_policy`(L110-L120), `scan_plaintext_secrets`(L123-L150), `redact_sensitive_payload`(L156-L174) | — | `scripts/auto_update_map.py`, `scripts/netark_guard_daemon.py`, `scripts/test_netark_enterprise_guard.py` | `100.ARCH-RULES.v1` |
| `schemas/schema_validator.py` | `load_valid_taxonomy_codes`(L56-L74), `count_prose_lines`(L77-L90), `check_as05_portability`(L93-L102), `generate_prescription_skeleton`(L105-L149), `validate_against_schema`(L152-L163), `validate_document`(L166-L286) | — | `schemas/doc_initializer.py`, `scripts/auto_update_map.py`, `scripts/sync_doc_metadata.py`, `scripts/test_netark_harness.py` | `000.SOUL.v1` |
| `schemas/topology_graph.py` | `parse_markdown_frontmatter`(L29-L40), `load_all_memory_nodes`(L43-L57), `check_as06_node_exclusivity`(L60-L97), `detect_unlinked_topology_references`(L100-L141), `check_topology_graph`(L144-L193), `_match_gitignore_rule`(L196-L213) | — | `schemas/code_hygiene_ast.py`, `schemas/schema_validator.py` | — |
| `scripts/auto_update_map.py` | `_extract_subdomain_layers`(L47-L52), `load_domain_layers`(L55-L69), `extract_wikilinks_outside_fenced_blocks`(L72-L79), `sha256_file`(L82-L83), `heal_dead_links`(L86-L130), `is_private_memory_path`(L133-L134) | — | — | `200.ADR-001.v1` |
| `scripts/netark_guard_daemon.py` | `GuardModelSlot`(L34-L39), `Tier1ClassifierSlot`(L42-L103), `Tier2SemanticSlot`(L106-L130), `generate_offline_license_token`(L133-L138), `verify_enterprise_license`(L141-L155), `append_signed_audit_log`(L158-L176) | — | `scripts/test_netark_enterprise_guard.py`, `scripts/test_netark_harness.py` | `100.ARCH-RULES.v1` |
| `scripts/netark_init.py` | `ensure_enterprise_policy`(L50-L61), `_sync_workflow_commands`(L64-L73), `_sync_skills`(L76-L87), `install_agy_adapter`(L90-L129), `install_claude_adapter`(L132-L174), `install_pi_adapter`(L177-L206) | — | `scripts/test_netark_enterprise_guard.py` | `200.ADR-001.v1` |
| `scripts/sync_doc_metadata.py` | `split_frontmatter_raw`(L33-L40), `surgical_set_scalar`(L43-L58), `surgical_try_set_scalar`(L61-L66), `surgical_remove_from_yaml_list`(L69-L111), `render_role_models_ssot_block`(L114-L132), `compute_actual_epistemic_counts`(L135-L137) | — | — | — |
| `scripts/test_netark_enterprise_guard.py` | `test_01_tier0_ast_73_vectors_and_g01_to_g05`(L46-L172), `test_02_daemon_slots_vaultless_dlp_and_soc2`(L175-L216), `test_03_multi_host_init_and_agy_nested_hooks`(L219-L284), `test_04_bilingual_docs_and_line_budgets`(L287-L306) | — | — | — |
| `scripts/test_netark_harness.py` | `test_01_clean_5_core_nodes_and_oracle`(L38-L64), `test_02_block_gitignored_affected_paths`(L67-L100), `test_03_codebook_topology_map_and_reverse_lookup`(L103-L151), `test_04_role_models_and_subagent_alignment`(L154-L173), `test_05_extensions_turn1_codebook_and_guard_hooks`(L176-L192), `test_06_code_hygiene_p1_p2_and_modularity_gates`(L195-L251) | — | — | — |

## 4. 專案治理目錄結構摘要

- `.netark/` — 專案內嵌可攜式 NetArk Agentic Harness 大腦（含模型路由、安全護欄、漸進式揭露與 5 角色子代理）
- `schemas/` — 記憶節點標頭 (`artifact_header.schema.json`)、Context 拓撲節點 (`context_node.schema.json`)、Tier 0 AST 護欄 (`netark_guard_core.py`) 與防諂媚驗證器 (`schema_validator.py`)
- `memory/codex/` — 核心架構規範 (`000_SOUL.md`, `100_ARCH_RULES.md`, `200_DECISIONS.md`) 與自動編譯總目錄 (`CONTEXT_MAP.md`)
- `memory/LEDGER.md` — 專案唯一活躍工單台帳 (`<= 80` 行)
- `memory/episodic/HANDOVER.md` — 微對話無縫交接快照 (`<= 65` 行)
- `memory/index/CONTEXT_INDEX.json` — 機器可讀之漸進式揭露與 `@D/@C/@G` 代號壓縮索引
- `scripts/` — 索引編譯器 (`auto_update_map.py`)、跨宿主守護程序 (`netark_guard_daemon.py`)、母版安裝器 (`netark_init.py`) 與自動化驗收套件
