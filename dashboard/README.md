# 🌌 NetArk (`N.E.T.A.R.K.`) 專案控管中心 (`dashboard/` — V1.1)

零外部依賴、獨立分離安裝之專案知識圖譜、藍圖分片 (`Blueprint Sharding`)、工單台帳 (`LEDGER.md`) 與防上帝腳本行數水位 (`Code Health`) 視覺化戰情室。

---

## 🚀 1. 快速啟動方式

### 方式 A：使用 npm 快捷鍵或 Python 直接啟動
```bash
npm run dashboard
# 或
python3 dashboard/backend/server.py 8765
```
*（預設監聽 `0.0.0.0:8765`，內建首字節 `0x16` TLS 自動探測，同一埠號同時支援 `http://127.0.0.1:8765` 與 `https://127.0.0.1:8765`）*

### 方式 B：同時掛載多個 NetArk 架構專案
透過環境變數 `NETARK_EXTRA_PROJECTS`（以 `:` 分隔多個專案根目錄路徑）即可於右上角下拉選單一鍵切換不同專案：
```bash
NETARK_EXTRA_PROJECTS="/path/to/ProjectA:/path/to/ProjectB" python3 dashboard/backend/server.py 8765
```

---

## 🧭 2. 四大核心視圖與 V1.1 互動特性

| 分頁名稱 | 核心功能與 V1.1 升級亮點 |
| :--- | :--- |
| **🌳 專案結構樹 (`Structure Tree`)** | 預設首頁。置頂呈現 **「🏛️ 藍圖分片與子模組樹 (`Blueprint ➔ Shards`)」** 並內嵌**子切片落地進度條**；下方依序陳列第 1~3 層（憲法守則、核心規格、Wiki 與台帳）。 |
| **🌌 節點關聯圖譜 (`Graph View`)** | `16:9` 四層動態高度水平泳道拓撲圖譜。採 **3-Pass 圖層分離 + 文字深色膠囊底襯 (`Pill Backdrop`) + S 型貝茲曲線**，確保百級節點下文字絕不被線條遮擋；支援**滑鼠懸停預覽小卡 (`Hover Tooltip`)** 與點擊「聚光燈隔離模式」。 |
| **📋 工單與交接看板 (`Ledger & Handover`)** | • **`HANDOVER.md`**：四格標題中文化，異動檔案自動拆解為獨立條列卡片，所有節點簡碼（如 `` `931` ``）、`[[WikiLink]]` 與路徑皆可點擊於右側開啟。<br>• **`LEDGER.md`**：支援 `[🔥 進行中/草案]` 篩選器與置頂高亮，任務名稱採「金色粗體白話主旨 + 技術細項」雙層顯示，狀態欄之藍圖與驗收基準之測試腳本皆可點擊於右側預覽。 |
| **🛡️ 程式碼行數監控 (`Code Health`)** | 即時掃描全專案 `.ts` / `.py` 檔案行數與 AST 函式座標，對超過 `400` 行（🟡 預警）與 `600` 行（🔴 上帝腳本凍結）之檔案進行視覺化監控。 |

---

## 🧪 3. 執行單元測試

```bash
python3 dashboard/tests/test_dashboard_shards.py
```

---

## 🔒 4. 隱私與分離架構設計

- **100% 解耦分離**：`dashboard/` 為純外掛視覺化讀取器，不侵入 `.netark/` 大腦 Runtime、不增加 LLM Context Token 消耗。
- **零私密節點洩漏**：讀取器於執行期動態合併本地 `memory/index/CONTEXT_INDEX.json`（公開）與 `memory/index/PRIVATE_INDEX.json`（受 `.gitignore` 保護之本地私有節點），本身不落地儲存任何私密快照。
