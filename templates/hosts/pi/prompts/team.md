---
description: "啟動 NetArk 跨模型子代理協作管線 (預設極速實作鏈: scout -> worker -> auditor；深度對抗鏈: scout -> architect -> challenger -> worker -> auditor)"
---
請針對以下任務啟動 NetArk 跨模型子代理協作團隊 (`subagent` 工具的 `chain` 模式，各角色自動讀取 `.pi/agents/*.md` 與 `.pi/role-models.json` 綁定之極速模型，並向下相容 `.netark/`；每角色回報嚴格限制 $\le 300$ 字高密度列點)：

任務目標：$@

請依任務複雜度選擇以下任一子代理鏈 (`chain`) 調度（指派 `worker` 執行實作時，任務書須符合 `SPEC-RIBC-GATE`：含 `[R]` 角色/路徑、`[I]` 不變量、`[B]` 邊界與 `[C]` 契約，且總長 $\ge 60$ 字元）：

### A. 預設極速實作鏈（一般功能實作、Bug 修復、測試撰寫 — 省時高成功率）
1. `scout`：優先使用 `netark_query` 或檢索 `memory/index/CONTEXT_INDEX.json`（含 `codebook_map` 與 `PRIVATE_INDEX.json`）與目標檔案結構，整理關鍵行號與 `[FACT]` 摘要（$\le 300$ 字）。
2. `worker`：根據 `{previous}` 與符合 `SPEC-RIBC-GATE`（`[R]/[I]/[B]/[C]`，$\ge 60$ 字元）之主腦指令，在獨立沙盒內完成程式碼修改，自主執行語法檢查與單元測試，回傳極簡 Diff 摘要（$\le 300$ 字）。
3. `auditor`：根據 `{previous}` 進行獨立神諭驗收——於零 `.py` 工作區優先呼叫 `netark_guard(action="oracle")`，若存在本機腳本亦可執行 `python3 schemas/schema_validator.py --run-oracle` 與相關測試（$\le 300$ 字）。

### B. 完整深度對抗鏈（重大跨模組架構變更、新增核心 ADR 或使用者明確要求深度推演時啟用）
1. `scout`：優先使用 `netark_query` 與索引檔案快速檢索公私索引與相關檔案真實路徑（$\le 300$ 字）。
2. `architect`：立足 `{previous}` 真實檔案 Context 擬定具備可證偽驗證條件 (`falsifiable_criterion`) 的精煉藍圖（$\le 300$ 字，嚴禁輸出未執行的 `cat` 指令）。
3. `challenger`：對 `{previous}` 進行實證與階段比例審查（查證真實檔案、不提過度企業級防禦；若合理符合階段需求即 `VERDICT: APPROVED` $\le 150$ 字，僅在確有重大漏洞時 `VERDICT: REJECTED`）。
4. `worker`：根據 `{previous}` 與符合 `SPEC-RIBC-GATE`（`[R]/[I]/[B]/[C]`，$\ge 60$ 字元）之契約落實檔案修改、沙盒內測試驗證並回報極簡 Diff 摘要（$\le 300$ 字）。
5. `auditor`：於零 `.py` 工作區優先呼叫 `netark_guard(action="oracle")`，若存在本機腳本亦可執行 `python3 schemas/schema_validator.py --run-oracle` 與相關測試進行最終驗收（$\le 300$ 字）。
