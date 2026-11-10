---
node_id: "MEM-2026-0002"
artifact_type: "rule"
access_tier: "restricted"
priority: "critical"
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
  fact_count: 6
  inferred_count: 1
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "bash_assert"
  command: "python3 schemas/netark_guard_core.py --self-test"
  expected_exit_code: 0
  falsifiable_criterion: "若 Tier 0 AST 護欄未能阻斷 .env/auth.json/*vault*.json 存取或寫檔明文金鑰防呆攔截失效，則本規則判定無效。"
context_index:
  domain_code: "100"
  node_key: "100.ARCH-RULES.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Security:Boundary:Rule"
    - "Guard:Tier0AST:DLP:PreWriteLint"
  keywords:
    - "Workspace Boundary"
    - "SEC-CRED"
    - "SEC-PREWRITE-SECRET"
    - "SEC-CONTROL-PLANE"
    - "Zero Exfiltration"
  summary_1line: "邊界與零外洩護欄：工作區鎖定、.netark保護、SEC-CRED與Pre-Write防呆"
topology:
  depends_on:
    - "000.SOUL.v1"
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/netark_guard_core.py"
  affected_paths:
    - "schemas/netark_guard_core.py"
---

# 🛡️ `100.ARCH-RULES.v1` (MEM-2026-0002) — 工作區邊界與零外洩安全護欄規範

## §1 工作區邊界鎖定與控制面防竄改 (`SEC-BOUNDARY` & `SEC-CONTROL-PLANE`)

- [FACT] 遵循 [[000.SOUL.v1]] 治理基線，所有工具呼叫（`read`/`write`/`edit`/`bash`）預設嚴格限制於專案根目錄（`cwd`）內部，禁止越界修改上層或系統目錄。
- [FACT] 受保護之控制面目錄（`.netark/`、`.agents/`、`.claude/`、`.github/workflows/`、`schemas/`）受 `SEC-CONTROL-PLANE` 鎖定，禁止子代理或未授權工具擅自竄改驗證器與護欄規則。
- [FACT] 記憶節點之 `topology.affected_paths` 嚴禁綁定 `.gitignore` 忽略之私密金鑰或執行期快取檔（如 `.netark/auth.json`、`.netark/models-store.json`、`.env`）。

## §2 機密隔離、廢除明文對照檔與寫檔前金鑰防呆 (`G-01` ~ `G-05`)

- [FACT] `SEC-CRED` 最高機密黑名單涵蓋 `.env*`（排除 `.env.example`）、`auth.json`、`*vault*.json`、SSH 私鑰與雲端憑證檔，透過 Stage A/B/C 三階段 Shell + Python AST 解析器 100% 阻斷直接與間接讀取。
- [FACT] 全面廢除落盤明文對照表（`.session_vault.json`）與雙向替換機制，改由 `SEC-PREWRITE-SECRET` 寫檔前防呆攔截（精準檢測 12 種金鑰格式），強制程式碼改用 `os.environ.get('KEY_NAME')` 並由人類使用者設定 `.env`。
- [INFERRED] 以「邊界阻斷（`SEC-CRED`）+ 寫檔前防呆（`SEC-PREWRITE-SECRET`）+ 單向輸出脫敏」取代雙向還原戲法，可同時根除對照檔洩漏、`edit_file` 脫靶、高熵誤傷與誘導還原攻擊。

## §3 代碼衛生與結構防腐規範 (`HYG-01` ~ `HYG-05`)

- [FACT] 所有工作區新增或修改之程式碼受 Turn-1 `@G` 治理契約與 `schemas/code_hygiene_ast.py` Pre-Write AST 門禁雙重約束，強制執行 `HYG-01 ~ HYG-05` 結構衛生標準：

| 代號 | 名稱 | 規則摘要 |
| :--- | :--- | :--- |
| **`HYG-01`** | 控制流深度上限 | 函式控制流最大嵌套深度嚴格 `<= 4 層`（平行 `elif` 與方法鏈不累加），優先使用 Early-Return (衛語句)。 |
| **`HYG-02`** | 禁絕靜默吞異常 | 嚴禁無處理之 `except: pass` / `except: ...`，合法非阻塞豁免必須明確標註 `# noqa: silent-except`。 |
| **`HYG-03`** | 入口反向溯源防禦 | 遇非預期回傳或 Bug，禁止就地疊加 `if/try` 補丁，必須逆推 `[Return Point -> Call Chain -> Entry Input]` 並於入口加設 Fail-Fast 驗證。 |
| **`HYG-04`** | 單次 AST 廢代碼雷達 | 以 Single-Pass AST 掃描同步提取符號、嵌套深度與孤立 `unused_imports`，持續清創死變數與死函式。 |
| **`HYG-05`** | 模組化分級行數門禁 | 核心模組目標 `<= 400 行`；`401~550 行` 為軟警告緩衝區；`> 550 行` 且淨增行數 `> 0` 觸發 Pre-Write 硬性阻斷。 |
