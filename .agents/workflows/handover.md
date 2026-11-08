---
description: 將當前微對話之進度、修改檔案行號座標、已排除死路與下一步寫入 memory/episodic/HANDOVER.md (/handover)
---
請立即執行「微對話無縫交接 (`/handover`)」標準程序（全程強制使用繁體中文 `zh-TW`）：

1. **更新 `memory/episodic/HANDOVER.md`（嚴格維持總行數 `<= 65` 行）**：
   保留既有 YAML Frontmatter，僅將下方四大 H2 結構化區塊覆寫為當前對話之最新實況（支援 Dashboard 智慧別名膠囊跳轉）：
   - `## 1. Active Objective & Blueprint Shard（當前目標與分片座標）`：標註當前 `WO-XXXX` 工單與 `[[node_key]]` 或三位數簡碼分片進度（含 `- [FACT]` 標籤）。
   - `## 2. Modified, Stub & Target Files（異動、空殼與目標檔案行號座標）`：以頓號 `、` 分隔列出本輪異動或待修改之檔案與分片，格式統一為 `` `path/to/file.py`（中文職責或 Lxx-Lyy 座標） ``，使 Dashboard 自動將每項拆解為獨立可點擊之檔案卡片。
   - `## 3. Key Decisions & Rejected Paths（已拍板決策與已排除死路）`：濃縮已確認之架構決策與已排除之死胡同（含 `- [INFERRED]` 標籤），防止下一輪新對話重蹈覆轍。
   - `## 4. Immediate Next Step（下一輪開局第一步指令）`：明確寫出新開 Session 後第 1 步要執行的具體動作或對齊項目。
2. **同步台帳（若工單已達階段性完工）**：若當前工單已完成驗收，請同步於 `memory/LEDGER.md` 原地更新狀態（第 2 欄維持 `**白話任務主旨**｜技術細項` 格式）。
3. **輸出交接確認單**：以極簡三行摘要告知使用者 `📦 [Handover Ready]`，提示可直接開啟新對話（或 `/new`）0 秒無縫接續。
