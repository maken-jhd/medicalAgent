import json
import os
from tqdm import tqdm

# ================= 配置区域 =================
INPUT_DIR = "../诊疗指南整合（知识结构化）"       
BATCH_INPUT_FILE = "batch_input.jsonl" # 生成的用于上传的大文件
MODEL_NAME = "deepseek-ai/DeepSeek-R1"
# ===========================================

def generate_case_prompt(item, topic):
    """
    你的原始 Prompt 生成逻辑 (保持不变，这里省略具体内容以节省篇幅)
    """
    condition = item.get("condition", "")
    action = item.get("action", "")
    prompt_content = f"""
你是一名顶尖的医学病例场景构建专家。你当前的任务是基于**《{topic}》**这一特定医疗领域的指南进行创作。
你的任务是将给定的【医疗指南规则】转化为一个**具体、真实且富含细节的临床瞬间**。

**当前背景主题：** {topic}

**输入数据：**
* **Trigger (Condition)**: {condition}
* **Guide (Action)**: {action}

**任务流程：**

**第一步：智能路由（分析规则类型）**
请根据 Condition 和 Action 的内容，判断其属于以下哪种核心场景，并采用对应的生成策略：

---

**场景 A：操作规范与测量 (Technical SOPs)**
* **关键词**：测量、袖带、休息5分钟、体位、仪器标准。
* **生成策略**：
    * **角色**：门诊护士或初级医生。
    * **Input设计**：描述一个**具有特定体征**的患者（如“肥胖”、“心律不齐”或“初次就诊紧张”），正在准备进行检查。
    * **重点**：构造出需要运用该条操作规范的物理条件（如“患者上臂很粗，普通袖带扣不上”）。

**场景 B：生活方式与风险干预 (Lifestyle & Prevention)**
* **关键词**：盐、饮食、运动、吸烟、体重、心理压力、疫苗。
* **生成策略**：
    * **角色**：慢性病管理门诊的医生。
    * **Input设计**：在现病史中，**必须植入**与规则对应的不良习惯（如“患者自述口味重，无肉不欢”或“每天抽烟2包”）。
    * **重点**：不要直接请求建议，而是暴露问题，等待医生指出。

**场景 C：分级诊疗与随访 (Referral & Follow-up)**
* **关键词**：转出、转回、上级医院、社区管理、随访频率、达标。
* **生成策略**：
    * **角色**：社区全科医生。
    * **Input设计**：描述一个**复诊场景**。重点描述患者经过一段时间治疗后的**现状**（如“吃了3种药血压还是160” 或者 “血压最近半年都很稳”）。
    * **重点**：考察医生是继续治疗还是发起转诊。

**场景 D：复杂合并症治疗 (Comorbidity Management)**
* **关键词**：合并糖尿病、CKD、脑卒中、妊娠、心力衰竭、药物相互作用。
* **生成策略**：
    * **角色**：专科医生。
    * **Input设计**：构建一个**多病共存**的复杂病例。必须明确列出患者的**既往史**（如“既往有心梗病史”）和**关键实验室指标**（如“肌酐升高”、“尿蛋白阳性”），以触发特定的用药规则。

**场景 E：常规诊断与治疗 (General Diagnosis & Rx)**
* **关键词**：确诊、首选药物、疑似病例、隔离。
* **生成策略**：
    * **角色**：门诊或急诊医生。
    * **Input设计**：描述典型的症状、体征和初步检查结果。

**场景 F：自适应通用场景 (Adaptive / Administrative)**
* **适用**：**上述 A-E 无法覆盖的情况**。例如：医疗文书书写、传染病上报流程、药物保存方法、医患沟通伦理、知情同意等。
* **策略**：
    1. **分析意图**：这条规则是写给谁看的？（医生、护士、还是公卫人员？）
    2. **构建情境**：
       - 如果是**行政规则**（如上报）：生成医生在电脑前处理病历或打电话汇报的场景。
       - 如果是**药物保存**：生成患者询问“药怎么放”或药师发药时的叮嘱场景。
       - 如果是**伦理规则**：生成家属对手术风险或隐私的顾虑。

---

**第二步：生成内容 (Input Generation)**
* 基于上述策略，生成一段 `input` 文本。
* **关键约束**：
    1.  **Implicit Input（隐式输入）**：如果是生活方式或测量类规则，不要让病人直接问“我该怎么用大袖带？”，而是描述“患者上臂围35cm，护士发现标准袖带过紧”。
    2.  **Realistic Noise（真实噪音）**：加入 1 个干扰信息（如患者的职业、天气或无关的轻微主诉）。
    3.  **Strict Compliance（严格一致）**：生成的数值必须落在 Condition 规定的范围内（例如规则是 SBP≥180，生成的病例就写 190，不要写 175）。
    4.  **No Leaking（禁止泄露）**：Input 中绝对不能包含 Action 中的建议内容。

**输出格式 (JSON)：**
{{
    "scenario_type": "场景A/B/C/D/E",
    "patient_demographics": "简述（如：65岁男性，社区复诊）",
    "input": "生成的完整病例描述..."
}}
"""
    return prompt_content

def prepare_batch_file():
    # 1. 递归获取所有 JSON 文件
    json_files = []
    print(f"正在递归扫描目录: {INPUT_DIR} ...")
    
    for root, dirs, files in os.walk(INPUT_DIR):
        for file in files:
            if file.endswith(".json"):
                full_path = os.path.join(root, file)
                json_files.append(full_path)

    print(f"共找到 {len(json_files)} 个 JSON 数据文件。")

    request_count = 0
    
    with open(BATCH_INPUT_FILE, 'w', encoding='utf-8') as f_out:
        for file_path in tqdm(json_files, desc="处理文件中"):
            
            # === 1. 计算唯一标识 (用于 Custom ID) ===
            file_unique_name = os.path.relpath(file_path, INPUT_DIR)
            file_unique_name = file_unique_name.replace("\\", "/")
            
            # === 2. 提取主题 (用于 Prompt) ===
            # 从文件名中提取，例如 "儿科/猴痘诊疗指南.json" -> "猴痘诊疗指南"
            file_name_only = os.path.basename(file_path)
            topic = os.path.splitext(file_name_only)[0]

            with open(file_path, 'r', encoding='utf-8') as f_in:
                try:
                    data = json.load(f_in)
                except json.JSONDecodeError:
                    print(f"\n[Warn] 跳过损坏文件: {file_unique_name}")
                    continue

            if not isinstance(data, list):
                print(f"\n[Warn] 文件格式不是列表，跳过: {file_unique_name}")
                continue

            for idx, item in enumerate(data):
                # === 3. 生成 Prompt (传入 topic) ===
                user_prompt = generate_case_prompt(item, topic)
                
                # === 4. 构造 Custom ID ===
                custom_id = f"{file_unique_name}|{idx}"

                # === 5. 构造 Batch 请求 ===
                batch_request = {
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": MODEL_NAME,
                        "messages": [
                            {"role": "system", "content": "你是一个严谨的医学数据生成助手。"},
                            {"role": "user", "content": user_prompt}
                        ],
                        # DeepSeek-R1 话多，Token给足
                        "max_tokens": 2048, 
                        # 0.6 是 R1 推荐的温度，既有创造力又不太会胡言乱语
                        "temperature": 0.6 
                    }
                }

                f_out.write(json.dumps(batch_request, ensure_ascii=False) + "\n")
                request_count += 1

    print(f"\n{'='*30}")
    print(f"成功生成 Batch 任务文件: {BATCH_INPUT_FILE}")
    print(f"包含请求总数: {request_count}")
    print(f"请继续运行 Step 2 脚本上传并提交任务。")
    print(f"{'='*30}")

if __name__ == "__main__":
    prepare_batch_file()