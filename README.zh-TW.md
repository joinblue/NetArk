# ⚓ NetArk (`N.E.T.A.R.K.`) — Clean-Room V1 代理工程與認知治理核心

> **語言 / Language**: [English](README.md) | **繁體中文**

**N**etwork-shielded, **E**nforced-**T**emplate **A**rchival & **R**ule-indexed **K**ernel (`NetArk`) 是一套專為 **Pi Coding Agent**、**Google Antigravity (AGY)** 與 **Claude Code** 打造的可攜式雙層大腦、知識圖譜治理與零信任本地資安護欄核心。

---

## 🌟 四大核心架構支柱

1. **可攜式雙層大腦架構（`.netark/` + `memory/`）**
   - **執行期大腦（`.netark/`）**：內建漸進式記憶揭露、工作區資安門禁、多金鑰 Sticky Round-Robin 模型路由（`role-models.json`）與 5 大異質審查角色（`scout`、`architect`、`challenger`、`worker`、`auditor`）。
   - **受納管知識圖譜（`memory/`）**：以 5 個極簡純淨核心節點起點（`000_SOUL.md`、`100_ARCH_RULES.md`、`200_DECISIONS.md`、`LEDGER.md`、`HANDOVER.md`），由外部決定性驗證器（`schemas/schema_validator.py`）強制檢驗四級認知標籤與因果無環圖（DAG）。

2. **Turn-1 凍結 `@D/@M/@C/@G` 代號壓縮拓撲圖（~94% Token 壓縮率）**
   - 由 `scripts/auto_update_map.py` 自動掃描全專案記憶節點與程式碼 AST，編譯至 `memory/index/CONTEXT_INDEX.json`。
   - 開局 Turn 1 凍結注入目錄字典（`@D`）、記憶節點字典（`@M`）、腳本行號字典（`@C`）與三層 Dashboard 拓撲關係圖（`@G`：`[DAG]` 記憶因果邊、`[SYN]` 記憶管轄代碼突觸、`[AST]` 程式碼引用邊），100% 命中 Prefix KV Cache。
   - 支援 **L1-Full**（$\le 150$ 檔全圖）、**L2-Cluster**（$151\sim1,500$ 檔目錄叢集）與 **L3-ActiveCone**（$> 1,500$ 萬檔級活躍因果錐）三級自動縮放與 `query_library` 短代號反查。

3. **三層本地資安護欄與無對照檔單向脫敏（`G-01` ~ `G-05` 全面封口）**
   - **Tier 0（`schemas/netark_guard_core.py`）**：三階段結構化 AST 解析（`shlex` 引號接合、子 Shell 拆解、`python -c` 內嵌 `ast.parse`）、工作區物理邊界鎖定、控制面保護（`.netark/`、`.agents/`、`.claude/`、`schemas/`）、`*vault*.json` 與 `.env*` 絕對黑名單（`G-01`），以及寫檔前硬編碼私鑰防呆攔截（`SEC-PREWRITE-SECRET`，`G-02`/`G-04`）。
   - **Tier 1（`scripts/netark_guard_daemon.py`）**：本地 ONNX CPU 語意注入分類器（`Llama-Prompt-Guard-2-22M`），支援 0-VRAM 啟發式降級與本地開發工具 Fast-Path 免癱瘓通道。
   - **Tier 2**：可插拔內網語意守護模型插槽與 HMAC-SHA256 雜湊鏈簽章稽核日誌（`.netark/audit/soc2_audit.jsonl`）。

4. **獨立分離式專案控管中心（`dashboard/` — V1.1）**
   - 零外部依賴、支援單埠 HTTP/HTTPS 雙協定自動探測之視覺化戰情室（`python3 dashboard/backend/server.py 8765`），提供專案結構樹、四泳道節點關聯圖譜、工單與交接看板、以及程式碼行數水位監控（400 行預警 / 600 行防上帝腳本）。

---

## 🚀 快速開始

### 1. 一鍵初始化跨宿主轉接器與雙語記憶庫（`netark_init.py`）

```bash
# 為目標專案安裝 Pi / AGY / Claude 轉接器並建立繁體中文 5 核心記憶庫
python3 scripts/netark_init.py --target all --lang zh-TW --cwd /path/to/your-project

# 或使用英文母版初始化
python3 scripts/netark_init.py --target all --lang en --cwd /path/to/your-project
```

### 2. 啟動 Pi Coding Agent

```bash
export PI_CODING_AGENT_DIR="$(pwd)/.netark"
cp .netark/auth.example.json .netark/auth.json
# 於 .netark/auth.json 填入 API Key，或進入 Pi 後輸入 /mode 設定多組逗號分隔金鑰
pi
```

### 3. 啟動視覺化專案控管中心 (`dashboard/`)

```bash
npm run dashboard
# 或直接以 Python 啟動：
python3 dashboard/backend/server.py 8765
```

---

## 🧪 全套決定性驗收測試指令

```bash
# 1. Tier 0 AST 與 G-01..G-05 資安封口自檢
python3 schemas/netark_guard_core.py --self-test

# 2. 跨宿主守護進程與寫檔防呆自檢
python3 scripts/netark_guard_daemon.py --self-test

# 3. @D/@M/@C/@G 壓縮拓撲編譯與 Schema Oracle 驗收
python3 scripts/auto_update_map.py --print-codebook
python3 schemas/schema_validator.py --run-oracle

# 4. Dashboard V1.1 契約測試
python3 dashboard/tests/test_dashboard_shards.py

# 5. NetArk 核心檢驗套件與 73+ 對抗樣本企業級護欄驗收
python3 scripts/test_netark_harness.py
python3 scripts/test_netark_enterprise_guard.py
```

---

## ⚖️ 雙重授權條款 (License)

本專案採 **Prosperity Public License 3.0.0**（[LICENSE](LICENSE)）與 **NetArk 商業授權**（[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)）雙重授權；外部貢獻請參閱 [CLA.md](CLA.md)。
