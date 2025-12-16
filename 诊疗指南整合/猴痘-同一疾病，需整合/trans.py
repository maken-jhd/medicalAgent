import os
import json
import requests
import re

# ================= 配置区域 =================
# 请在此处填入您的 SiliconFlow API Key
API_KEY = "sk-vsfrmtzhbyadnxhkafnxzicdlisrivlcqhkbveduyfqcocsh" 
# 目标模型名称 (请确保该模型在平台可用)
MODEL_NAME = "zai-org/GLM-4.6"  # 如果V3.2不可用，请尝试 V3 或 V2.5
# 目标文件名
TARGET_FILENAME = "猴痘公众防护指南(2023).md"
# API 地址
API_URL = "https://api.siliconflow.cn/v1/chat/completions"

def get_structured_data(content, filename):
    """
    构造 Prompt 并调用 API 获取结构化数据
    """
    system_prompt = """# Role
你是一名资深的临床数据结构化专家，专注于构建高精度的临床决策支持系统（CDSS）。你的核心能力是将非结构化的医学指南文本，转化为机器可读的、原子化的“条件-动作（If-Then）”规则。

# Task
阅读我为你提供的医学文章，提取其中所有的诊疗决策逻辑，并以 JSON 列表格式输出。

# Extraction Rules (至关重要)

1. **逻辑原子化原则 (Atomic Logic) —— 核心规则！**
   - **严禁聚合**：如果原文描述了针对不同症状（如发热、疼痛、口腔溃疡）的不同处理方式，**必须拆分为多个独立的 JSON 对象**。
   - **一事一议**：每一个 JSON 对象只能包含一条独立的决策路径。
   - 错误做法：Condition: "猴痘患者", Action: "1.退热... 2.止痛... 3.漱口..."
   - 正确做法：
     - {Condition: "猴痘患者出现发热", Action: "..."}
     - {Condition: "猴痘患者疼痛难忍", Action: "..."}
     - {Condition: "猴痘患者出现口腔损伤", Action: "..."}

2. **条件提取精细化 (Condition Granularity)**
   - **数值前置**：将所有的生理指标、实验室数值（如 CD4计数、肌酐值）从文本中提取出来，放入 `condition` 字段，而不是留在 action 或 contraindication 中。机器需要这些数值来做判断。
   - **逻辑完备**：包含人群特征、合并症、用药史等所有触发逻辑的前提。

3. **Evidence 字段逐字引用 (Verbatim Copy)**
   - `evidence` 必须是原文的**逐字摘录**。
   - **上下文完整**：如果逻辑依赖于前文的主语（如“对于此类患者...”），引用时需包含前文信息，确保引用的句子语义独立完整。
   - **严禁**使用“...”省略号替代关键信息。

4. **Action 字段可执行化**
   - 提取具体的**药物名称**、**剂量**、**疗程**、**时机**。
   - 不要包含编号列表（1., 2.），除非这些步骤是必须按顺序执行的同一套流程。

# Output Format
请仅输出一个 JSON 列表，严格遵守以下 Schema，不要包含 Markdown 标记以外的解释：

```json
[
  {
    "condition": "触发该逻辑的具体前提（包含数值、症状、人群）",
    "action": "具体的处置措施（药物、检查、隔离方式）",
    "contraindication": "原文明确提及的禁忌或不推荐情况（无则填 null）",
    "evidence": "原文的完整引用，证明上述逻辑的来源"
  }
]

```

#Few-Shot Examples (学习示例)为了让你更好地理解任务，请仔细阅读以下“错误”与“正确”的对比：

**输入文本：**

> “对于已知的HIV感染患者若被诊断感染猴痘病毒，应继续进行抗反转录病毒治疗。对于西多福韦，若血清肌酐>0.132 mmol/L，则应禁用。”

**❌ 错误输出 (Bad Case) —— 问题：逻辑未拆分，数值未提取**

```json
[
  {
    "condition": "已知HIV感染合并猴痘",
    "action": "继续抗反转录病毒治疗，使用西多福韦",
    "contraindication": "若血清肌酐>0.132 mmol/L则禁用西多福韦",
    "evidence": "对于已知的HIV感染患者若被诊断感染猴痘病毒..."
  }
]

```

*(点评：机器无法识别肌酐阈值，且将两个不同的药理逻辑混在了一起)*

**✅ 正确输出 (Good Case) —— 优点：逻辑原子化，数值结构化**

```json
[
  {
    "condition": "已知HIV感染患者被诊断感染猴痘病毒",
    "action": "继续进行抗反转录病毒治疗",
    "contraindication": null,
    "evidence": "对于已知的HIV感染患者若被诊断感染猴痘病毒，应继续进行抗反转录病毒治疗。"
  },
  {
    "condition": "HIV感染的猴痘患者，且血清肌酐>0.132 mmol/L",
    "action": "禁用西多福韦",
    "contraindication": "禁用西多福韦",
    "evidence": "对于西多福韦，若血清肌酐>0.132 mmol/L (1.5 mg/dL)，则应禁用"
  }
]

```

*(点评：拆分为两条规则；将 ">0.132 mmol/L" 明确放入了 Condition 字段，便于计算机执行)*"""

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"请处理以下文本内容：\n\n{content}"
            }
        ],
        "stream": False,
        "max_tokens": 8192,
        "temperature": 0.5,  # 降低温度以保证提取的准确性
        "top_p": 0.95,
        "response_format": {
            "type": "text"
        }
    }

    try:
        print(f"正在请求大模型处理 {filename} ...")
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()  # 检查请求是否成功
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        return content
        
    except requests.exceptions.RequestException as e:
        print(f"API 请求失败: {e}")
        if response.text:
            print(f"错误详情: {response.text}")
        return None

def clean_json_string(json_str):
    """
    清洗大模型返回的字符串，去除 Markdown 标记
    """
    # 移除 ```json 和 ``` 标记
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, json_str, re.DOTALL)
    if match:
        return match.group(1)
    
    # 如果没有 json 标记，尝试移除普通代码块标记
    pattern_simple = r"```\s*(.*?)\s*```"
    match_simple = re.search(pattern_simple, json_str, re.DOTALL)
    if match_simple:
        return match_simple.group(1)
        
    return json_str

def main():
    # 1. 检查文件是否存在
    if not os.path.exists(TARGET_FILENAME):
        print(f"错误：在当前目录下未找到文件 '{TARGET_FILENAME}'")
        return

    # 2. 读取文件内容
    try:
        with open(TARGET_FILENAME, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    # 3. 调用 AI 进行处理
    ai_response = get_structured_data(file_content, TARGET_FILENAME)
    
    if ai_response:
        # 4. 清洗和验证 JSON
        cleaned_json_str = clean_json_string(ai_response)
        
        try:
            # 尝试解析 JSON 以确保格式正确
            json_data = json.loads(cleaned_json_str)
            
            # 5. 保存结果
            output_filename = os.path.splitext(TARGET_FILENAME)[0] + ".json"
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
                
            print(f"成功！结果已保存至: {output_filename}")
            
        except json.JSONDecodeError as e:
            print("解析 JSON 失败。大模型返回的内容可能不是合法的 JSON 格式。")
            print("原始内容如下：")
            print(ai_response)
            # 也可以选择保存原始内容以便调试
            with open("error_output.txt", "w", encoding="utf-8") as f:
                f.write(ai_response)

if __name__ == "__main__":
    main()