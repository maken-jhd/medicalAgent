import os
import json
import requests
import re
import time

# ================= 配置区域 =================
# 您的 SiliconFlow API Key
API_KEY = "sk-vsfrmtzhbyadnxhkafnxzicdlisrivlcqhkbveduyfqcocsh" 
# 模型名称
MODEL_NAME = "Pro/deepseek-ai/DeepSeek-R1" 

# 输入文件夹名称
SOURCE_ROOT_DIR = "诊疗指南整合"
# 输出文件夹名称
TARGET_ROOT_DIR = "诊疗指南整合（知识结构化）"

# 【筛选】仅处理指定文件（如果列表不为空，脚本只处理这里列出的文件）
TARGET_SPECIFIC_FILES = [
    "慢性阻塞性肺疾病诊治指南（2021年修订版）.md",
    "HIV合并结核分枝杆菌感染诊治专家共识.md",
    "2型糖尿病中医防治指南_倪青.md",
]

# 分段长度限制（字符数）
MAX_CHUNK_SIZE = 15000

# 黑名单文件夹列表
BLACKLIST_DIRS = []

# API 地址
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
# ===========================================

def split_markdown_content(content, max_length=15000):
    """
    智能分段函数：基于 Markdown 标题 (#) 将文章拆分为章节并合并。
    """
    pattern = r'(^#{1,2}\s.*$)'
    parts = re.split(pattern, content, flags=re.MULTILINE)
    
    chunks = []
    current_chunk = ""
    
    for part in parts:
        if not part: continue
        
        if len(current_chunk) + len(part) < max_length:
            current_chunk += part
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = part
            
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

def get_structured_data(chunk_content, filename, chunk_index, total_chunks):
    """
    构造 Prompt 并调用 API 获取结构化数据
    """
    
    # --- 1. 构造 System Prompt (使用优化后的原子化提示词) ---
    system_prompt = f"""# Role
你是一名专业的临床数据结构化专家。你的任务是从医学指南片段中精准提取诊疗逻辑，并将其转化为机器可读的结构化数据。

# Task
提取其中**所有章节**的诊疗决策逻辑。

# Extraction Rules (至关重要)

1. **逻辑原子化 (Atomic Logic) —— 核心规则！**
   - **严禁聚合分支**：如果原文针对不同情况（如不同分级、不同症状、不同指标）推荐了不同的治疗方案，**必须拆分为多条独立的 JSON 对象**。
   - ❌ 错误做法：Action: "1. A组用支气管舒张剂; 2. B组用长效支气管舒张剂..." (这是把多条逻辑混在了一起)
   - ✅ 正确做法：
     - {{ "condition": "A组", "action": "使用支气管舒张剂..." }}
     - {{ "condition": "B组", "action": "使用长效支气管舒张剂..." }}

2. **Condition字段要“数值化”与“前置化”**：
   - 所有的触发阈值（如 "CAT>20分"、"EOS≥300"、"FEV1<70%"）**必须**提取到 `condition` 字段中。
   - **严禁**将 "若..." 或 "当..." 的判断逻辑留在 `action` 字段里。
   - `condition` 需包含完整的人群特征、合并症、用药史等前提。

3. **Action字段仅包含指令**：
   - Action 应该是具体的执行动作（药物、检查、手术）。
   - **关于编号的使用**：仅当必须**按顺序执行**一系列步骤时（例如：先进行A，观察无效后再进行B），才使用 "1. ...; 2. ..." 格式。如果是并列的选项（A 或 B），请拆分为不同的条目。
   - 包含时机、药物名称、剂量、疗程等细节。

4. **Evidence字段严禁省略**：
   - `evidence` 必须是**原文的逐字摘录（Verbatim Copy）**。
   - **禁止**使用“...”或“等”来替代原文内容。如果是依据长段落得出的结论，请引用相关完整句子。

5. **完整性要求**：
   - 提取一般治疗、抗病毒治疗、重症治疗、**中医治疗（包括辨证分型方药）**等所有方案，不得遗漏。

# Output Format
请以 JSON 列表格式输出，不要包含 Markdown 代码块标记以外的多余解释：
```json
[
  {{
    "condition": "触发该逻辑的具体前提（包含数值、症状、人群）",
    "action": "具体的处置措施",
    "contraindication": "原文明确提及的禁忌或不推荐情况，如无则填null",
    "evidence": "原文的完整引用"
  }}
]
```"""

    # --- 2. 构造 User Content (注入全局上下文) ---
    # 告诉模型：虽然这是片段，但它是《某某指南》的一部分
    context_note = ""
    if total_chunks > 1:
        context_note = f"\n（注：由于文件较长，这是第 {chunk_index}/{total_chunks} 部分的内容。请提取该部分内容中的所有诊疗逻辑，无需顾虑上下文是否完整。）"

    user_content = f"""
【当前文档上下文】：
本文档完整标题为：《{filename.replace('.md', '')}》。请始终基于此背景理解文中的"本组"、"该类患者"等指代。

【待处理文本片段】：
{chunk_content}
{context_note}
"""

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}  # 这里使用了新构造的 user_content
        ],
        "stream": False,
        "max_tokens": 8192,
        "temperature": 0.6,
        "top_p": 0.95
    }

    retries = 3
    for attempt in range(retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=300)
            response.raise_for_status() 
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            print(f"  [Warning] API 请求失败 (尝试 {attempt+1}/{retries}): {e}")
            time.sleep(2)
            
    print(f"  [Error] {filename} 第 {chunk_index} 部分处理彻底失败，跳过。")
    return None

def clean_json_string(json_str):
    """清洗大模型返回的字符串"""
    if not json_str: return "[]"
    json_str = re.sub(r"<think>.*?</think>", "", json_str, flags=re.DOTALL)
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, json_str, re.DOTALL)
    if match: return match.group(1)
    pattern_simple = r"```\s*(.*?)\s*```"
    match_simple = re.search(pattern_simple, json_str, re.DOTALL)
    if match_simple: return match_simple.group(1)
    return json_str.strip()

def process_file(file_path, output_path):
    print(f"正在读取: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  [Error] 读取文件失败: {e}")
        return

    # 1. 执行分段
    chunks = split_markdown_content(content, MAX_CHUNK_SIZE)
    print(f"  -> 文件较长，已拆分为 {len(chunks)} 段进行处理...")
    
    final_data = [] 
    
    # 2. 逐段处理
    for i, chunk in enumerate(chunks, 1):
        print(f"  -> 正在处理第 {i}/{len(chunks)} 段 (长度: {len(chunk)}) ...")
        
        # 传递 filename 和 chunk 信息给 get_structured_data
        ai_response = get_structured_data(chunk, os.path.basename(file_path), i, len(chunks))
        
        if ai_response:
            cleaned_json_str = clean_json_string(ai_response)
            try:
                chunk_data = json.loads(cleaned_json_str)
                if isinstance(chunk_data, list):
                    final_data.extend(chunk_data)
                    print(f"     第 {i} 段提取成功，获取 {len(chunk_data)} 条数据。")
                else:
                    print(f"     [Warning] 第 {i} 段返回的不是列表，跳过。")
            except json.JSONDecodeError:
                print(f"     [Error] 第 {i} 段 JSON 解析失败，跳过该段。")
                # 调试用：保存错误的片段
                with open(output_path.replace('.json', f'_err_part{i}.txt'), 'w', encoding='utf-8') as f:
                    f.write(ai_response)
        
        time.sleep(1)

    # 3. 保存最终整合结果
    if final_data:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"  [Success] 整合完毕，共 {len(final_data)} 条数据。")
            print(f"  保存路径: {output_path}")
        except Exception as e:
            print(f"  [Error] 保存文件失败: {e}")
    else:
        print(f"  [Warning] {os.path.basename(file_path)} 未提取到任何有效数据。")

def main():
    if not os.path.exists(SOURCE_ROOT_DIR):
        print(f"错误：未找到输入文件夹 '{SOURCE_ROOT_DIR}'")
        return

    processed_count = 0
    
    for root, dirs, files in os.walk(SOURCE_ROOT_DIR):
        if any(bad in root for bad in BLACKLIST_DIRS): continue

        for file in files:
            if not file.endswith('.md'): continue
            
            # 【筛选逻辑】只处理指定列表中的文件
            if TARGET_SPECIFIC_FILES and file not in TARGET_SPECIFIC_FILES:
                continue
                
            source_file_path = os.path.join(root, file)
            
            relative_path = os.path.relpath(root, SOURCE_ROOT_DIR)
            target_dir_path = os.path.join(TARGET_ROOT_DIR, relative_path)
            if not os.path.exists(target_dir_path):
                os.makedirs(target_dir_path)
            
            # 输出文件名改为：原名 + (1).json
            target_file_name = os.path.splitext(file)[0] + "(1).json"
            target_file_path = os.path.join(target_dir_path, target_file_name)
            
            # 检查是否已存在（可选：如果不想重复跑，可以取消注释下面两行）
            # if os.path.exists(target_file_path):
            #     print(f"跳过已存在文件: {target_file_path}")
            #     continue

            process_file(source_file_path, target_file_path)
            processed_count += 1
            print("-" * 30)

    print(f"全部任务完成！共处理文件: {processed_count} 个")

if __name__ == "__main__":
    main()