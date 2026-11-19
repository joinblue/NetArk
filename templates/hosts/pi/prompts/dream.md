---
description: 執行 NetArk 記憶整合、孤兒節點盤點、台帳瘦身與雙軌圖譜重編譯 (/dream)
---
請立即執行「NetArk 記憶整合與雙軌知識圖譜重編譯 (`/dream`)」標準程序（全程強制使用繁體中文 `zh-TW`）：

### Phase 1: 暫存區與未納管知識盤點 (`scout`)
1. 掃描 `scratch/` 與 `memory/` 下所有新增或近期修改之 Markdown 文件。
2. 評估 `scratch/` 中是否有已定案之架構知識、SOP 或調試結論值得晉升（Promote）至 `memory/wiki/`（開架圖書館軌）或 `memory/specs/`（公文軌）。

### Phase 2: 雙向連結、台帳瘦身與 `@D/@C/@G` 索引重編譯 (`worker`)
1. 執行 `python3 scripts/auto_update_map.py`，自動修復斷鏈 (`heal_dead_links`)、掃描全專案業務源碼 AST 符號座標 (`code_intelligence_map`)，並重新編譯 `memory/index/CONTEXT_INDEX.json`（含 `@D/@C/@G` 代號壓縮地圖）與 `memory/codex/CONTEXT_MAP.md`。
2. 檢查 `CONTEXT_INDEX.json` 中是否存在孤兒節點（除 `000` 外，`outbound_links` 與 `backlinks` 皆為 0 之活躍節點），並在語意相關之規格或 Wiki 節點間補上 `[[node_key]]` 雙向參照。
3. 審計 `memory/LEDGER.md`：
   - 嚴格確保總行數 **`<= 80` 行**。
   - 已標記 `✅ 已完成` 之工單預設保留於表中供查閱；僅當總行數逼近 80 行上限時，先將早期完工里程碑寫入 `memory/codex/200_DECISIONS.md` 或 `memory/wiki/` 後，再修剪舊列。

### Phase 3: Independent Oracle 獨立驗證 (`auditor`)
1. 執行 `python3 schemas/schema_validator.py --run-oracle` 並確認 100% 通過（exit code `0`）。
2. 以三段式總結回報 `[FACT]`：新編目節點、`outbound_links`/`backlinks` 更新數、`codebook_map` 壓縮率、`LEDGER.md` 行數與 Oracle 驗證結果。
