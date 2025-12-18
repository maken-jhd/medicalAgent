import json
import time
import os
import requests
from tqdm import tqdm 

# ================= 配置区域 =================
API_KEY = "sk-vsfrmtzhbyadnxhkafnxzicdlisrivlcqhkbveduyfqcocsh" 

MODEL_NAME = "Pro/deepseek-ai/DeepSeek-R1" 

API_URL = "https://api.siliconflow.cn/v1/chat/completions" 

INPUT_FILE = "猴痘诊疗指南（2022年版）.json"

OUTPUT_FILE = "step3_猴痘_CoT标注_R1_R1.jsonl"

def generate_cot_prompt(item):
    """
    构建 Step 3 的思维链 Prompt (包含场景感知)
    """
    SCENARIO_MAPPING = {
        "场景A": "操作规范与测量",
        "场景B": "生活方式与风险干预 ",
        "场景C": "分级诊疗与随访",
        "场景D": "复杂合并症治疗",
        "场景E": "常规诊断与治疗",
        "E": "常规诊断与治疗",
        "场景F": "行政与伦理"
    }
    scenario_type = item.get("scenario_type", "场景E") 
    readable_context = SCENARIO_MAPPING.get(scenario_type, "常规诊断与治疗")
    case_input = item.get("case_input", "")
    # 将规则对象转为字符串，方便嵌入 Prompt
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

def read_json_input(file_path):
    """读取标准 JSON 数组文件 [...]"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                print(f"成功读取输入数据: {len(data)} 条")
                return data
            else:
                print("错误：输入文件格式不正确，需要是一个 JSON 数组 [...]")
                return []
    except Exception as e:
        print(f"读取输入文件失败: {e}")
        return []

def process_data():
    # 1. 读取输入数据 (JSON Array)
    data = read_json_input(INPUT_FILE)
    if not data:
        return

    # 2. 读取已处理的数据（用于断点续传）
    processed_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    if not line.strip(): continue
                    record = json.loads(line)
                    if 'id' in record:
                        processed_ids.add(record['id'])
                except:
                    pass
        print(f"检测到已有存档，跳过 {len(processed_ids)} 条已处理数据")

    # --- 计时开始 ---
    start_time = time.time()
    newly_processed_count = 0 

    # 3. 打开输出文件准备写入 (Append 模式)
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        for item in tqdm(data, desc="生成专家思维链(CoT)中"):
            
            # 提取 ID 用于断点续传
            item_id = item.get('id')
            
            # 如果 ID 已经存在，直接跳过
            if item_id in processed_ids:
                continue

            # 构建 Prompt
            user_prompt = generate_cot_prompt(item)
            
            # 构造请求 Payload
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "你是一位经验丰富的临床医学专家。请严格遵循JSON格式输出。"},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "max_tokens": 4096, 
                "temperature": 0.6, # R1 稍微调高一点点有助于思考多样性，但为了JSON格式也不宜过高
                "response_format": {"type": "json_object"} 
            }

            # 重试机制
            retries = 3
            success = False
            for attempt in range(retries):
                try:
                    response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
                    response.raise_for_status()
                    
                    result = response.json()
                    generated_text = result['choices'][0]['message']['content']
                    
                    # R1 兼容性处理：DeepSeek-R1 有时会在 JSON 外面包裹 <think> 标签
                    # 如果 json.loads 失败，我们尝试简单清洗一下
                    clean_text = generated_text
                    if "<think>" in clean_text:
                         # 简单的策略：如果 R1 把思考过程放在了 JSON 外面，我们只取 JSON 部分
                         # 注意：这里假设 JSON 在思考之后。更复杂的正则匹配可以视情况添加
                         if "```json" in clean_text:
                             clean_text = clean_text.split("```json")[1].split("```")[0]
                         elif "{" in clean_text:
                             # 找到第一个 { 和最后一个 }
                             start = clean_text.find("{")
                             end = clean_text.rfind("}") + 1
                             clean_text = clean_text[start:end]

                    try:
                        cot_json = json.loads(clean_text)
                    except json.JSONDecodeError:
                        # 如果实在解不开，保存原始文本，回头人工看一眼
                        cot_json = {"raw_text": generated_text, "error": "JSON parse failed"}

                    # 构建最终保存的数据结构 
                    final_record = item.copy()
                    final_record['step3_cot_response'] = cot_json
                    final_record['step3_model'] = MODEL_NAME
                    
                    # 写入一行 JSONL
                    f_out.write(json.dumps(final_record, ensure_ascii=False) + "\n")
                    f_out.flush()
                    
                    success = True
                    break

                except Exception as e:
                    print(f"\n[Warning] ID {item_id} 请求失败 (尝试 {attempt+1}/{retries}): {e}")
                    time.sleep(2)
            
            if success:
                newly_processed_count += 1
            else:
                print(f"\n[Error] ID {item_id} 处理彻底失败，已跳过。")
            
            # 避免触发速率限制
            time.sleep(0.3)

    # --- 计时结束与统计输出 ---
    end_time = time.time()
    total_duration = end_time - start_time

    print(f"\n{'='*30}")
    print(f"处理完成！结果已保存至: {OUTPUT_FILE}")
    if newly_processed_count > 0:
        avg_time = total_duration / newly_processed_count
        print(f"本次新增处理: {newly_processed_count} 条")
        print(f"平均处理时间: {avg_time:.2f} 秒/条")
    print(f"{'='*30}\n")

if __name__ == "__main__":
    process_data()