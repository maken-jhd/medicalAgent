import json
import os
import re

# ================= 配置区域 =================
BATCH_RESULT_FILE = "batch_output_kimi_step3.jsonl"
INPUT_DIR = "../诊疗指南整合step2_kimi（创建病例）"
OUTPUT_DIR = "../诊疗指南整合step3_kimi（生成诊疗手段）"
ERROR_LOG_FILE = "error_records_kimi_step3.txt"
# ===========================================

def clean_llm_json(text):
    """
    清洗 LLM 返回的文本，提取合法的 JSON 部分。
    针对 DeepSeek R1 等模型，可能会包含思维链内容，需精准提取 JSON。
    """
    if not text: return None
    try:
        # 1. 尝试直接解析
        return json.loads(text)
    except json.JSONDecodeError:
        # 2. 尝试提取 Markdown 代码块 ```json ... ```
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass
        
        # 3. 尝试提取纯大括号内容 { ... }
        # 贪婪匹配：从第一个 { 到 最后一个 }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try: return json.loads(match.group(0))
            except: pass
            
        return None

def log_error(f_err, error_type, custom_id, message, raw_data=None):
    """
    将错误写入日志文件
    """
    f_err.write(f"[{error_type}] ID: {custom_id}\n")
    f_err.write(f"Message: {message}\n")
    if raw_data:
        f_err.write(f"Raw Data: {raw_data[:200]}...\n") 
    f_err.write("-" * 50 + "\n")

def process_merge_results():
    # 0. 检查文件是否存在
    if not os.path.exists(BATCH_RESULT_FILE):
        print(f"❌ 错误：找不到批量结果文件 {BATCH_RESULT_FILE}")
        return

    # 1. [递归预加载] Step 2 的所有数据到内存
    # 目的：通过 custom_id 中的路径和索引，找到原始的 case_input 和 reference_rule
    print(f"📂 正在递归扫描 {INPUT_DIR} 加载 Step 2 源数据...")
    step2_data_cache = {}
    
    if os.path.exists(INPUT_DIR):
        for root, dirs, files in os.walk(INPUT_DIR):
            for file in files:
                if file.endswith(".json"):
                    full_path = os.path.join(root, file)
                    # 获取相对路径，例如： "儿科/儿童猴痘诊疗和预防专家共识.json"
                    rel_path = os.path.relpath(full_path, INPUT_DIR).replace("\\", "/")
                    
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # 确保缓存的是列表，如果文件只有单个对象，转为列表
                            if isinstance(data, list):
                                step2_data_cache[rel_path] = data
                            else:
                                step2_data_cache[rel_path] = [data]
                    except Exception as e:
                        print(f"[Warn] 无法读取源文件 {rel_path}: {e}")
    else:
        print(f"❌ 错误: 源数据目录 {INPUT_DIR} 不存在！")
        return

    print(f"✅ 已缓存 {len(step2_data_cache)} 个 Step 2 文件。")

    # 2. [流式处理] 读取 Batch 结果并融合
    print(f"🚀 正在处理 {BATCH_RESULT_FILE} ...")
    final_results = {} 
    success_count = 0
    fail_count = 0

    with open(BATCH_RESULT_FILE, 'r', encoding='utf-8') as f_in, \
         open(ERROR_LOG_FILE, 'w', encoding='utf-8') as f_err:
        
        for line_num, line in enumerate(f_in):
            if not line.strip(): continue
            
            custom_id = f"Line_{line_num}"
            
            try:
                res_item = json.loads(line)
                custom_id = res_item.get('custom_id', f"Unknown_ID_Line_{line_num}")
                
                # A. 解析 ID (格式：相对路径|索引)
                if '|' in custom_id:
                    relative_path, original_idx_str = custom_id.rsplit('|', 1)
                    original_idx = int(original_idx_str)
                else:
                    log_error(f_err, "ID Format Error", custom_id, "缺少 '|' 分隔符", line)
                    fail_count += 1
                    continue

                # B. 检查 API 错误
                if res_item.get('error'):
                    err_msg = str(res_item['error'])
                    print(f"[API Error] {custom_id}: {err_msg}")
                    log_error(f_err, "API Error", custom_id, err_msg)
                    fail_count += 1
                    continue
                
                # C. 解析 DeepSeek 返回的内容
                llm_json = None
                generated_content = ""
                try:
                    # 获取 content 字段 (DeepSeek R1 的 output 通常在 choices[0].message.content)
                    generated_content = res_item['response']['body']['choices'][0]['message']['content']
                    llm_json = clean_llm_json(generated_content)
                except Exception as e:
                    log_error(f_err, "Content Parse Error", custom_id, str(e), str(res_item)[:200])
                    fail_count += 1
                    continue

                if not llm_json: 
                    log_error(f_err, "JSON Extraction Failed", custom_id, "无法提取有效 JSON", generated_content)
                    fail_count += 1
                    continue

                # D. 从缓存中获取 Step 2 的原始数据
                source_record = {}
                if relative_path in step2_data_cache:
                    data_list = step2_data_cache[relative_path]
                    if 0 <= original_idx < len(data_list):
                        source_record = data_list[original_idx]
                    else:
                        msg = f"索引越界: Index {original_idx} >= Length {len(data_list)}"
                        log_error(f_err, "Index Out of Bounds", custom_id, msg)
                        fail_count += 1
                        continue
                else:
                    msg = f"找不到源文件缓存: {relative_path}"
                    log_error(f_err, "Source File Missing", custom_id, msg)
                    fail_count += 1
                    continue

                # E. 组装最终数据 (Step 3 格式)
                # 保留 Step 2 的 id, file_name, case_input, reference_rule
                # 新增 thought, medical_order, patient_dialogue
                final_record = {
                    "id": source_record.get("id"), # 保持 ID 一致性
                    "file_name": source_record.get("file_name"),
                    "case_input": source_record.get("case_input"),
                    "reference_rule": source_record.get("reference_rule"),
                    # --- DeepSeek 生成的新字段 ---
                    "thought": llm_json.get("thought"),
                    "medical_order": llm_json.get("medical_order"),
                    "patient_dialogue": llm_json.get("patient_dialogue")
                }

                # 按文件路径分组存储
                if relative_path not in final_results:
                    final_results[relative_path] = []
                
                final_results[relative_path].append(final_record)
                success_count += 1

            except json.JSONDecodeError:
                log_error(f_err, "JSONL Line Error", custom_id, "Line not valid JSON", line)
                fail_count += 1
            except Exception as e:
                print(f"[Unknown Error] {custom_id}: {e}")
                log_error(f_err, "Unknown Error", custom_id, str(e))
                fail_count += 1

    # 3. [分发保存] 保持目录结构写入文件
    print(f"💾 正在保存文件到 {OUTPUT_DIR} ...")
    
    for relative_path, records in final_results.items():
        output_file_path = os.path.join(OUTPUT_DIR, relative_path)
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
        # 为了美观，按 ID 排序（可选）
        # records.sort(key=lambda x: x.get('id', 0))

        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        print(f"  └─ 已保存: {output_file_path} ({len(records)} 条)")

    print(f"\n{'='*30}")
    print(f"处理完成！")
    print(f"✅ 成功合并: {success_count} 条")
    print(f"❌ 失败/跳过: {fail_count} 条 (详情见 {ERROR_LOG_FILE})")
    print(f"📂 结果已存入: {OUTPUT_DIR}")
    print(f"{'='*30}")

if __name__ == "__main__":
    process_merge_results()