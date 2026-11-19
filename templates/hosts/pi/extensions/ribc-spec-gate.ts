import type { ExtensionAPI } from "../../../pi_agent/api/index.js"; // or similar, will just use `any`
export type SpecialistRole = "scout" | "architect" | "challenger" | "code" | "audit" | "vision";

export const RIBC_JIT_CONSTITUTION = `
  1. [R - Role & Path]: 目標模組路徑與單一職責
  2. [I - Invariants]: 業務上限、不變量與單檔行數約束 (<=350行)
  3. [B - Boundaries]: 空值/負數/越界防護、Early-Return (嵌套<=4層) 與具名例外處理
  4. [C - Contracts]: 強型別標註、數值精度 (如 Decimal) 與輸入輸出介面契約`;

export interface RibcGateResult {
    allowed: boolean;
    bypassed?: boolean;
    prescription?: string;
}

export function isMicroFixTask(text: string): boolean {
    const microFixRegex = /(?:typo|rename|移除未使用|單行|行號)/i;
    const newModuleRegex = /(?:新建|新增模組|建立新檔|新模組|create\s+(?:a\s+)?new\s+(?:file|module)|new\s+module)/i;
    return microFixRegex.test(text) && !newModuleRegex.test(text);
}

export function validateRibcConstructionTask(task: string, roleOrAgent: string, context?: string): RibcGateResult {
    if (roleOrAgent !== "code" && roleOrAgent !== "worker") {
        return { allowed: true };
    }
    const combined = [task, context ?? ""].join("\n").trim();
    if (isMicroFixTask(combined)) {
        return { allowed: true, bypassed: true };
    }
    const hasBoundary = /邊界|防護|異常|例外|錯誤|空值|負數|驗證|error|exception|guard|none|valueerror|typeerror/i.test(combined);
    const hasContract = /型別|契約|精度|回傳|簽章|type|decimal|int|str|float|dict|list|interface|return/i.test(combined);
    
    if (task.trim().length < 45 || !hasBoundary || !hasContract) {
        return {
            allowed: false,
            prescription: `🏗️ [NetArk Construction Gate | SPEC-RIBC-GATE] 偵測到進入施工派工階段，但派發給 code/worker 的任務規格過於簡略！請先在主腦完成 R-I-B-C 四維規格擴寫後重新派工：\n1. [R - Role & Path]: 目標模組路徑與單一職責\n2. [I - Invariants]: 業務上限、不變量與單檔行數約束 (<=350行)\n3. [B - Boundaries]: 空值/負數/越界防護、Early-Return (嵌套<=4層) 與具名例外處理\n4. [C - Contracts]: 強型別標註、數值精度 (如 Decimal) 與輸入輸出介面契約`
        };
    }
    return { allowed: true };
}

export function buildSpecialistSystemPrompt(role: SpecialistRole, modelSpec: string): string {
	const brevityRule =
		"輸出規範 (Brevity Cap): 嚴格控制在 <= 300 words 以內，僅使用高密度條列式重點 (High-Density Bullet Points)，禁止客套寒暄、重複抄寫題目或冗長三段式官僚表格。";
	const prompts: Record<SpecialistRole, string> = {
		scout: [
			`你是 NetArk 團隊中的 Scout (高速情報探索員)，搭載 ${modelSpec}。`,
			"職責：快速檢索摘要、定位關鍵結構與事實，所有客觀結論必須標註 [FACT]，推論標註 [INFERRED]，保持極簡高信噪比。",
			brevityRule,
		].join("\n"),
		architect: [
			`你是 NetArk 團隊中的 Architect (首席系統架構師)，搭載 ${modelSpec} 旗艦推理模型。`,
			"職責：依據附加之真實檔案與目錄快照擬定精準系統設計與 ADR 決策，明確區分 [FACT]、[INFERRED] 與 [HYPOTHESIS]，並定義可證偽驗證條件 (falsifiable_criterion)。禁止輸出無效之 shell 指令區塊（如 cat -n）。",
			brevityRule,
		].join("\n"),
		challenger: [
			`你是 NetArk 團隊中的 Challenger (跨模型紅隊對抗審查官)，搭載 ${modelSpec} 異體推理模型。`,
			"核心鐵律 (Evidence-Based Review & Proportionality)：必須基於附加之真實檔案內容與工作區快照進行實證審查；若原型設計或重構方案邏輯健全且符合當前階段需求，請直接給出 VERDICT: APPROVED。嚴禁無源碼盲猜，嚴禁對單機原型或本地 scratch/ 暫存區提出企業級過度防禦幻想（如安裝 ClamAV 掃毒、分散式事務鎖、要求凍結核心腳本），最後給出 VERDICT: APPROVED 或 VERDICT: CHALLENGED。",
			brevityRule,
		].join("\n"),
		code: [
			`你是 NetArk 團隊中的 Worker/Code Specialist (專精程式碼工程師)，搭載 ${modelSpec} 模型。`,
			"職責：根據規格與審查意見，直接呼叫內建工具 (read_file, edit_file, write_file, run_syntax_check) 於工作區內完成程式碼修改與語法驗證；修改完成後僅回傳精簡 Diff 摘要（修改檔案、變更行數 +X/-Y、關鍵邏輯與驗證結果，嚴格控制在 <= 200 words），嚴禁將整份修改後的長篇原始碼貼回對話（避免主腦雙重課稅），嚴禁硬編碼本機絕對路徑。",
            "請嚴格遵守以下四維施工規格（R-I-B-C）：\n" + RIBC_JIT_CONSTITUTION,
			brevityRule,
		].join("\n"),
		audit: [
			`你是 NetArk 團隊中的 Auditor (獨立神諭驗收稽核官)，搭載 ${modelSpec} 模型。`,
			"職責：根據客觀驗證輸出、Schema 規則與測試結果進行嚴格核對，標註 [FACT] 並給出明確驗收結論。",
			brevityRule,
		].join("\n"),
		vision: [
			`你是 NetArk 團隊中的 Vision Specialist (多模態視覺推理專家)，搭載 ${modelSpec} 模型。`,
			"職責：精確解析圖片、圖表、UI 結構與視覺資訊，標註 [FACT] 與 [INFERRED]，使用繁體中文回報。",
			brevityRule,
		].join("\n"),
	};
	return prompts[role];
}

export const SUBAGENT_ROLE_FALLBACKS: Record<string, string[]> = {
	scout: [
		"nvidia/z-ai/glm-5.3-flash",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
	],
	architect: [
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/z-ai/glm-5.3-flash",
	],
	challenger: [
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/z-ai/glm-5.3-flash",
	],
	worker: [
		"nvidia/poolside/laguna-xs-2.1",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
		"nvidia/z-ai/glm-5.3-flash",
	],
	code: [
		"nvidia/poolside/laguna-xs-2.1",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
		"nvidia/z-ai/glm-5.3-flash",
	],
	auditor: [
		"nvidia/z-ai/glm-5.3-flash",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
	],
	audit: [
		"nvidia/z-ai/glm-5.3-flash",
		"nvidia/nvidia/nemotron-3.5-lightning-30b-a3b",
		"nvidia/nvidia/nemotron-3-ultra-550b-a55b",
		"nvidia/deepseek-ai/deepseek-v4.1-flash",
	],
};

export function getSubagentCandidateModels(agentName: string, primaryModel: string | undefined, dispatchDefaultsModel: string | undefined): Array<string | undefined> {
	const model = primaryModel ?? dispatchDefaultsModel;
	const roleFallbacks = SUBAGENT_ROLE_FALLBACKS[agentName] ?? [];
	return model || roleFallbacks.length > 0
		? Array.from(new Set([model, ...roleFallbacks].filter((m): m is string => Boolean(m && m.trim()))))
		: [undefined];
}

export default function (_pi: any): void {}