---
node_id: "MEM-2026-0001"
artifact_type: "constitution"
access_tier: "immutable"
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
  fact_count: 5
  inferred_count: 2
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "schema_check"
  command: "python3 schemas/schema_validator.py --file memory/codex/000_SOUL.md"
  expected_exit_code: 0
  falsifiable_criterion: "若本核心憲法未通過 Schema 驗證、違反跨模型異質雙簽或認知標籤不一致，則判定無效。"
context_index:
  domain_code: "000"
  node_key: "000.SOUL.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Core:Constitution:Governance"
    - "Epistemic:AntiSycophancy:DualTrack:Oracle"
  keywords:
    - "NetArk"
    - "Constitution"
    - "Epistemic Honesty"
    - "Dual-Track Library"
    - "Anti-Sycophancy"
  summary_1line: "NetArk核心憲法：四級認知標籤、Official/Wiki雙軌制與反盲從Oracle鐵律"
topology:
  depends_on: []
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/schema_validator.py"
  affected_paths:
    - "schemas/schema_validator.py"
---

# ⚓ `000.SOUL.v1` (MEM-2026-0001) — NetArk (`N.E.T.A.R.K.`) 核心認知憲法

## §1 雙層可攜式大腦與雙軌記憶治理 (`Dual-Track Memory Governance`)

- [FACT] `NetArk`（**N**etwork-shielded, **E**nforced-**T**emplate **A**rchival & **R**ule-indexed **K**ernel）採用「內嵌大腦目錄（`.netark/`）+ 結構化記憶庫（`memory/`）」雙層可攜式架構。
- [FACT] 記憶庫分為「公文軌（`official`：`constitution`/`rule`/`adr`/`blueprint`/`spec`/`audit`）」與「圖書館開架軌（`wiki`：`wiki`/`note`/`sop`/`glossary`/`digest`）」雙軌制，兼顧剛性契約門禁與低摩擦知識積累。
- [INFERRED] 將「提示詞分區導航」與「Hook 確定性處方籤執法（`RemediationPointer`）」解耦，可在維持極簡 System Prompt 的同時確保 100% 規則遵循率。

## §2 四級認知誠實標籤與反盲從鐵律 (`AS-01` ~ `AS-06`)

- [FACT] 所有公文軌記憶節點之關鍵論點必須於列表行首標註四級認知標籤：`[FACT]`（已驗證客觀事實）、`[INFERRED]`（架構推導結論）、`[HYPOTHESIS]`（待驗證假設）、`[UNVERIFIED]`（未查證資訊）。
- [FACT] 進入 `verified` 狀態之公文軌節點，必須具備異質模型交叉審查（`author.model != reviewer.model` 且 `verdict == "APPROVED"`）、零 `[UNVERIFIED]` 殘留，並通過可證偽之 `verification_oracle` 實測（`AS-01`~`AS-03`）。
- [FACT] 漸進式揭露與分片鐵律：單一憲法／規則／ADR 純散文嚴格限制 `<= 50` 行，`spec`/`audit` 純散文 `<= 160` 行，`LEDGER.md` 總行數 `<= 80` 行，`HANDOVER.md` 總行數 `<= 65` 行。
- [INFERRED] 透過 Turn 1 凍結注入 `@D/@C/@G` 代號壓縮地圖與 `1 Modul = 1 Spec` 分片紀律，可徹底根除長對話 Context 腐敗與模型自審盲從。
