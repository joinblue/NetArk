---
node_id: "MEM-2026-0004"
artifact_type: "spec"
access_tier: "standard"
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
  fact_count: 2
  inferred_count: 1
  hypothesis_count: 0
  unverified_count: 0
verification_oracle:
  type: "schema_check"
  command: "python3 schemas/schema_validator.py --file memory/LEDGER.md"
  expected_exit_code: 0
  falsifiable_criterion: "若 memory/LEDGER.md 總行數超過 80 行或未通過 Schema 驗證，則判定無效。"
context_index:
  domain_code: "300"
  node_key: "300.LEDGER.v1"
  artifact_track: "official"
  facet_tags:
    - "NetArk:Core:Ledger:WorkOrders"
  keywords:
    - "LEDGER"
    - "Work Orders"
    - "Active Tasks"
  summary_1line: "專案唯一活躍工單台帳 (<=80行)"
topology:
  depends_on:
    - "000.SOUL.v1"
  supersedes: []
  conflicts_with: []
  verified_by:
    - "schemas/schema_validator.py"
  affected_paths: []
---

# 📋 `300.LEDGER.v1` (MEM-2026-0004) — 專案唯一活躍工單台帳 (`LEDGER.md`)

- [FACT] 本台帳遵循 [[000.SOUL.v1]] 漸進式揭露規範，嚴格維持總行數 `<= 80` 行，作為全專案唯一活躍工單追蹤入口。
- [FACT] 每一工單第 2 欄採 `**白話任務主旨**｜技術細項與驗收指標` 雙層格式，供终端與視覺化戰情室即時解析。
- [INFERRED] 保持單一精煉台帳可避免多份散落 TODO 清單造成狀態漂移。

| 工單編號 (`WO`) | 任務主旨與技術細項 (`Title & Technical Summary`) | 綁定規格 (`Spec`) | 狀態 (`Status`) |
| :--- | :--- | :---: | :---: |
| `WO-0001` | **NetArk V1 乾淨商業級母版初始化**｜建立 `.netark/` 大腦、5 核心記憶節點、`@D/@C/@G` 代號壓縮地圖與跨宿主安全護欄 | `000.SOUL.v1` | `✅ 已完成` |
