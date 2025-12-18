import json
import os
from tqdm import tqdm

# ================= 配置区域 =================
INPUT_DIR = "../诊疗指南整合step2_kimi（创建病例）" 
BATCH_INPUT_FILE = "batch_input_step3_cot_kimi.jsonl" 
UNKNOWN_LOG_FILE = "unknown_scenarios.txt"
MODEL_NAME = "deepseek-ai/DeepSeek-R1"

# 场景映射表 (提取为全局变量，方便检查和生成)
SCENARIO_MAPPING = {
    "场景A": "操作规范与测量",
    "A": "操作规范与测量",
    "场景B": "生活方式与风险干预", 
    "B": "生活方式与风险干预",
    "场景C": "分级诊疗与随访",
    "场景 C": "分级诊疗与随访",
    "C": "分级诊疗与随访",
    "场景D": "复杂合并症治疗",
    "场景 D": "复杂合并症治疗",
    "D": "复杂合并症治疗",
    "场景E": "常规诊断与治疗",
    "场景 E": "常规诊断与治疗",
    "E": "常规诊断与治疗",
    "场景E:常规诊断与治疗": "常规诊断与治疗",
    "场景F": "行政与伦理",
    "F": "行政与伦理"
}
# ===========================================

def generate_cot_prompt(item):
    """
    构建 Step 3 的思维链 Prompt (包含场景感知)
    """
    scenario_type = item.get("scenario_type", "场景E") 
    
    # 使用全局映射表，默认值为 "常规诊断与治疗"
    readable_context = SCENARIO_MAPPING.get(scenario_type, "常规诊断与治疗")
    
    case_input = item.get("case_input", "")
    
    # 将规则对象转为字符串，方便嵌入 Prompt
    # 注意：这里假设输入数据中 reference_rule 是一个字典
    reference_rule_str = json.dumps(item.get("reference_rule", {}), ensure_ascii=False, indent=2)

    prompt_content = f"""
你是一位顶尖的医学专家，具备深厚的临床推理能力。请根据【患者病例】、【场景类型】和【参考指南】，模拟真实的诊疗思维过程，并给出专业的建议。

**输入信息**：
* **Context (场景类型)**: {readable_context}
* **Patient Case (患者病例)**: 
{case_input}
* **Guideline Rule (参考指南)**: 
{reference_rule_str}

**核心指令：思维模式适配 (Reasoning Mode Adaptation)**
请阅读输入的 `Context (场景类型)`，并根据以下分类采用对应的思维模式（请关注内容的匹配，而非仅仅匹配标签）：

* **若涉及 [操作规范与测量]**：你是一丝不苟的**操作执行者**。
    * *思维重点*：物理条件是否满足？操作步骤是否遗漏？是否存在影响准确性的干扰因素？
* **若涉及 [生活方式与风险干预]**：你是循循善诱的**健康管理师**。
    * *思维重点*：识别隐式的不良习惯，关联长期风险，用共情但坚定的语气提出非药物干预建议。
* **若涉及 [分级诊疗与随访]**：你是严谨的**守门人 (Gatekeeper)**。
    * *思维重点*：对比现状与达标标准。判断是“维持原状”还是“触发转诊/升级治疗”。
* **若涉及 [复杂合并症治疗]**：你是博学的**专科专家**。
    * *思维重点*：**全网扫描**！检查药物相互作用、禁忌症及共病风险。优先级：安全 > 疗效。
* **若涉及 [常规诊断与治疗]**：你是果断的**急诊/门诊医生**。
    * *思维重点*：快速建立鉴别诊断（Differential Diagnosis），排除危急重症，给出最直接的指令。
* **若涉及 [行政/通用/伦理]**：你是规范的**管理者**。
    * *思维重点*：流程合规性、文书完整性、伦理告知及公共卫生责任。

---

**任务目标**：生成 JSON 格式响应。

**输出格式 (JSON)**：
{{
  "thought": "思维链（包含场景分析、临床解码、规则对齐、决策生成）",
  "medical_order": "专业的诊疗方案（书面语，给医生同行或护士看的）",
  "patient_dialogue": "医生对患者说的话（口语，充满人情味和解释性）"
}}

**详细步骤要求**：

**1. Thought (思维链)**
请严格按照以下步骤进行推理：
* **Step 1: 场景定义 (Scenario Definition)**
    * 明确指出当前属于哪种诊疗场景（如：“本案例属于常规急诊诊疗场景...”），并声明你的关注重点。
* **Step 2: 临床解码 (Clinical Decoding)**
    * 从病例中提取关键信息（尤其是隐式线索），将其转化为医学术语。
* **Step 3: 规则对齐与安全检查 (Alignment & Safety)**
    * 将解码后的信息与指南 Condition 进行匹配，并**强制检查**是否存在 Contraindication。
* **Step 4: 决策生成 (Decision Making)**
    * 根据指南 Action 生成具体决策。

**2. Medical Order (诊疗方案 - 书面)**
* **风格**：像写病历一样严谨、简洁、客观。
* **内容**：使用专业医学术语（如“予一级护理”、“低盐饮食”、“静脉推注”、“完善...检查”）。不要包含情绪性语言。

**3. Patient Dialogue (医患对话 - 口语)**
* **任务**：将上述“诊疗方案”翻译成**面对面沟通**的语言。
* **风格要求**：
    * **通俗化**：把“低盐饮食”转化为“做菜少放盐，咸菜也不要吃”。
    * **解释性**：告诉患者“为什么要这样做”（例如：“如果不隔离，家里人很容易被传染”）。
    * **情绪适配**：
        * 若患者焦虑（如生活方式/慢病场景），语气要安抚、鼓励。
        * 若情况危急（如急诊场景），语气要紧凑、有力、沉稳。
    * **去AI化**：严禁使用“综上所述”、“根据指南”等生硬词汇，使用自然的人类口语。
"""
    return prompt_content

def prepare_batch_file():
    # 1. 递归获取所有 JSON 文件
    json_files = []
    print(f"正在递归扫描目录: {INPUT_DIR} ...")
    
    if not os.path.exists(INPUT_DIR):
        print(f"[Error] 输入目录不存在: {INPUT_DIR}")
        return

    for root, dirs, files in os.walk(INPUT_DIR):
        for file in files:
            if file.endswith(".json"):
                full_path = os.path.join(root, file)
                json_files.append(full_path)

    print(f"共找到 {len(json_files)} 个 JSON 数据文件。")

    request_count = 0
    unknown_scenarios_set = set() # 用于去重记录未知的场景类型
    
    with open(BATCH_INPUT_FILE, 'w', encoding='utf-8') as f_out:
        for file_path in tqdm(json_files, desc="处理文件中"):
            
            # === 1. 计算唯一标识 (用于 Custom ID) ===
            # 保持和 Step 1 一致的逻辑，方便后续数据对齐
            file_unique_name = os.path.relpath(file_path, INPUT_DIR)
            file_unique_name = file_unique_name.replace("\\", "/")
            
            with open(file_path, 'r', encoding='utf-8') as f_in:
                try:
                    data = json.load(f_in)
                except json.JSONDecodeError:
                    print(f"\n[Warn] 跳过损坏文件: {file_unique_name}")
                    continue

            # 兼容：如果文件内容不是列表而是单个对象（虽然示例是列表，但做个防御性编程）
            if isinstance(data, dict):
                data = [data]
            
            if not isinstance(data, list):
                print(f"\n[Warn] 文件格式不正确，跳过: {file_unique_name}")
                continue

            for idx, item in enumerate(data):
                # === 2. 检查场景类型 (未知类型记录) ===
                s_type = item.get("scenario_type")
                # 如果 s_type 存在，但不在我们的映射表中，记录下来
                if s_type and s_type not in SCENARIO_MAPPING:
                    unknown_scenarios_set.add(f"Type: [{s_type}] | File: {file_unique_name}")

                # === 3. 生成 Prompt ===
                user_prompt = generate_cot_prompt(item)
                
                # === 4. 构造 Custom ID ===
                # 格式：文件名|索引 (确保和 Step 1 生成时的逻辑链条能对上，或者建立新的链条)
                custom_id = f"{file_unique_name}|{idx}"

                # === 5. 构造 Batch 请求 ===
                batch_request = {
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": MODEL_NAME,
                        "messages": [
                            {"role": "system", "content": "你是一个严谨的医学诊疗专家。"},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 4096,  
                        "temperature": 0.6   
                    }
                }

                f_out.write(json.dumps(batch_request, ensure_ascii=False) + "\n")
                request_count += 1

    # === 处理结束：写入异常日志 ===
    if unknown_scenarios_set:
        print(f"\n[Info] 发现 {len(unknown_scenarios_set)} 类/次 未知场景类型，正在写入日志...")
        with open(UNKNOWN_LOG_FILE, 'w', encoding='utf-8') as f_log:
            f_log.write("=== Unknown Scenario Types Detected ===\n")
            for record in sorted(unknown_scenarios_set):
                f_log.write(record + "\n")
        print(f"日志已保存至: {UNKNOWN_LOG_FILE}")
    else:
        print(f"\n[Info] 所有场景类型均已识别，无异常。")

    print(f"\n{'='*30}")
    print(f"Step 3 任务生成完毕: {BATCH_INPUT_FILE}")
    print(f"包含请求总数: {request_count}")
    print(f"{'='*30}")

if __name__ == "__main__":
    prepare_batch_file()