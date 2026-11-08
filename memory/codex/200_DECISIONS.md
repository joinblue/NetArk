---
node_id: "MEM-2026-0003"
artifact_type: "adr"
access_tier: "restricted"
priority: "high"
status: "verified"
created_at: "2026-11-08"
updated_at: "2026-11-08"
author:
  role: "architect"
  model: "nvidia/nemotron-3-ultra-550b-a55b"
reviewer:
  role: "challenger"
  model: "deepseek-ai/deepseek-v4.1-flash"
  verdict: "APPROVED"
epistemic_profile:
  fact_count: 4
  inferred_count: 2
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "schema_check"
  command: "python3 schemas/schema_validator.py --file memory/codex/200_DECISIONS.md"
  expected_exit_code: 0
  falsifiable_criterion: "若 auto_update_map.py 未能產出含 @D/@C/@G 與 reverse_lookup 之 codebook_map，則本架構決策判定失效。"
context_index:
  domain_code: "200"
  node_key: "200.ADR-001.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Architecture:ADR:Codebook"
    - "Context:KV-Cache:Compression:MultiHost"
  keywords:
    - "ADR-001"
    - "Codebook Compression"
    - "Turn-1 Frozen Map"
    - "Prefix KV Cache"
    - "Portable Brain"
  summary_1line: "架構決策錄：採用雙層可攜式大腦、Turn-1代號壓縮地圖與確定性邊界防禦"
topology:
  depends_on:
    - "000.SOUL.v1"
    - "100.ARCH-RULES.v1"
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/schema_validator.py"
  affected_paths:
    - "scripts/auto_update_map.py"
    - ".netark/extensions/epistemic-gate.ts"
---

# 🏛️ `200.ADR-001.v1` (MEM-2026-0003) — NetArk 核心架構決策錄

## §1 決策背景與雙層可攜式大腦 (`ADR-001`)

- [FACT] 依據 [[000.SOUL.v1]] 與 [[100.ARCH-RULES.v1]]，傳統 AI Coding 工具缺乏跨對話結構化記憶，且每回合動態拼接 RepoMap 會破壞 LLM Prefix KV Cache 並消耗大量 Token。
- [FACT] `NetArk` 拍板將執行期控制大腦統一收斂於 `.netark/`（支援 Pi 原生擴充與跨宿主 `AGY`/`Claude` 標準轉接骨架），並將初始記憶庫精簡為 5 個零污染核心節點。

## §2 Turn-1 凍結 `@D/@C/@G` 代號字典壓縮地圖 (`Codebook Map`)

- [FACT] `scripts/auto_update_map.py` 於排除 `.gitignore` 與通過 `scan_plaintext_secrets()` 檢查後，自動將目錄字典（`@D`）、受管轄與探索所得之業務腳本代號（`@C`）及記憶拓撲突觸邊（`@G`）編譯為 `CONTEXT_INDEX.json` 內之 `codebook_map`。
- [FACT] 系統支援依專案規模自動切換 L1（`<= 150` 檔全圖）、L2（`151 ~ 1,500` 檔模組叢集）與 L3（`> 1,500` 檔活躍影響圈），並於 `query_library` 提供 `@C`/`@G` 短代號（如 `C1`、`100`）O(1) 反查展開。
- [INFERRED] 在 Turn 1 開局凍結注入 `@D/@C/@G` 緊湊代號圖譜與 `HANDOVER.md` 快照，可較傳統全路徑列表節省 75%~85% Token 並達成 100% 對話期間 Prefix KV Cache 命中率。
- [INFERRED] 透過動態探索全工作區 `.py`/`.ts`/`.js` 業務源碼並自動建立規格與腳本之雙向突觸，任何新創或既有專案掛載 `NetArk` 即可零設定獲得完整拓撲視野。
