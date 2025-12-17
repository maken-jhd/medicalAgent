import json
import os
import re

# ================= 配置区域 =================
# 本地已下载的批量结果文件
BATCH_RESULT_FILE = "batch_output_kimi.jsonl"

# 原始数据目录（用于获取 Reference Rule）
INPUT_DIR = "../诊疗指南整合（知识结构化）"

# 最终成品存放目录
OUTPUT_DIR = "../诊疗指南整合step2_kimi（创建病例）"

# 错误日志文件
ERROR_LOG_FILE = "error_records_kimi.txt"
# ===========================================

def clean_llm_json(text):
    """
    清洗 LLM 返回的文本，提取合法的 JSON 部分。
    """
    if not text: return None
    try:
        # 尝试直接解析
        return json.loads(text)
    except json.JSONDecodeError:
        # 1. 尝试提取 Markdown 代码块 ```json ... ```
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass
        
        # 2. 尝试提取纯大括号内容 { ... }
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
        f_err.write(f"Raw Data: {raw_data[:200]}...\n") # 只记录前200字符防止文件过大
    f_err.write("-" * 50 + "\n")

def process_local_batch_results():
    # 0. 检查文件是否存在
    if not os.path.exists(BATCH_RESULT_FILE):
        print(f"错误：找不到文件 {BATCH_RESULT_FILE}")
        return

    # 1. [递归预加载] 所有原始数据到内存
    print(f"正在递归扫描 {INPUT_DIR} 加载原始数据...")
    original_data_cache = {}
    
    if os.path.exists(INPUT_DIR):
        for root, dirs, files in os.walk(INPUT_DIR):
            for file in files:
                if file.endswith(".json"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, INPUT_DIR).replace("\\", "/")
                    
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            original_data_cache[rel_path] = json.load(f)
                    except Exception as e:
                        print(f"[Warn] 无法读取原始文件 {rel_path}: {e}")
    else:
        print(f"错误: 原始数据目录 {INPUT_DIR} 不存在！")
        return

    print(f"✅ 已缓存 {len(original_data_cache)} 个原始文件的规则数据。")

    # 2. [流式处理] 读取本地 Batch 结果并合并
    print(f"正在处理 {BATCH_RESULT_FILE} ...")
    final_results = {} 
    global_id_counter = 0
    success_count = 0
    fail_count = 0

    # 打开输入文件和错误日志文件
    with open(BATCH_RESULT_FILE, 'r', encoding='utf-8') as f_in, \
         open(ERROR_LOG_FILE, 'w', encoding='utf-8') as f_err:
        
        for line_num, line in enumerate(f_in):
            if not line.strip(): continue
            
            # 预定义 custom_id 防止异常块中使用未定义变量
            custom_id = f"Line_{line_num}" 
            
            try:
                res_item = json.loads(line)
                custom_id = res_item.get('custom_id', f"Unknown_ID_Line_{line_num}")
                
                # 解析 ID
                if '|' in custom_id:
                    relative_path, original_idx_str = custom_id.rsplit('|', 1)
                    original_idx = int(original_idx_str)
                else:
                    print(f"[Error] 行 {line_num}: Custom ID 格式错误")
                    log_error(f_err, "ID Format Error", custom_id, "Custom ID missing pipe separator", line)
                    fail_count += 1
                    continue

                # A. 检查 API 错误
                if res_item.get('error'):
                    err_msg = str(res_item['error'])
                    print(f"[API Error] {custom_id}: {err_msg}")
                    log_error(f_err, "API Error", custom_id, err_msg)
                    fail_count += 1
                    continue
                
                # B. 解析 LLM 内容
                llm_json = None
                generated_content = ""
                try:
                    generated_content = res_item['response']['body']['choices'][0]['message']['content']
                    llm_json = clean_llm_json(generated_content)
                except Exception as e:
                    print(f"[Parse Error] {custom_id}: 解析失败")
                    log_error(f_err, "Content Parse Error", custom_id, str(e), generated_content)
                    llm_json = None

                if not llm_json: 
                    # 如果 clean_llm_json 返回 None，说明也没提取到 JSON
                    if generated_content and not llm_json:
                         log_error(f_err, "JSON Extraction Failed", custom_id, "No valid JSON found in content", generated_content)
                    fail_count += 1
                    continue

                # C. 获取原始规则
                original_rule = {}
                if relative_path in original_data_cache:
                    data_list = original_data_cache[relative_path]
                    if original_idx < len(data_list):
                        original_rule = data_list[original_idx]
                    else:
                        msg = f"索引越界: Index {original_idx} >= Length {len(data_list)}"
                        print(f"[Data Error] {relative_path} {msg}")
                        log_error(f_err, "Index Out of Bounds", custom_id, msg)
                        # 这里可以选择是否跳过，或者给一个空规则继续生成。
                        # 通常为了数据质量，选择跳过或标记。此处选择继续（original_rule为空）但记录错误
                        # 如果你希望严格跳过，取消下面注释：
                        # fail_count += 1
                        # continue
                else:
                    msg = f"找不到原始文件缓存: {relative_path}"
                    print(f"[Cache Error] {msg}")
                    log_error(f_err, "Source File Missing", custom_id, msg)
                    # 同样，找不到原始规则通常意味着数据无效，建议跳过
                    fail_count += 1
                    continue

                # D. 组装最终数据
                final_record = {
                    "id": global_id_counter,
                    "file_name": os.path.basename(relative_path),
                    "scenario_type": llm_json.get("scenario_type", "Unknown"),
                    "case_input": llm_json.get("input", ""),
                    "reference_rule": {
                        "condition": original_rule.get("condition"),
                        "action": original_rule.get("action"),
                        "contraindication": original_rule.get("contraindication"),
                        "evidence": original_rule.get("evidence")
                    }
                }

                if relative_path not in final_results:
                    final_results[relative_path] = []
                
                final_results[relative_path].append(final_record)
                global_id_counter += 1
                success_count += 1

            except json.JSONDecodeError:
                print(f"[Error] 行 {line_num}: JSON Line 格式错误")
                log_error(f_err, "JSONL Format Error", custom_id, "Line is not valid JSON", line)
                fail_count += 1
            except Exception as e:
                print(f"[Unknown Error] {custom_id}: {e}")
                log_error(f_err, "Unknown Error", custom_id, str(e))
                fail_count += 1

    # 3. [分发保存] 保持目录结构写入文件
    print(f"正在保存文件到 {OUTPUT_DIR} ...")
    
    for relative_path, records in final_results.items():
        output_file_path = os.path.join(OUTPUT_DIR, relative_path)
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        print(f"已保存: {output_file_path} ({len(records)} 条)")

    print(f"\n{'='*30}")
    print(f"处理完成！")
    print(f"成功合并: {success_count} 条")
    print(f"失败/跳过: {fail_count} 条 (详情见 {ERROR_LOG_FILE})")
    print(f"结果已存入: {OUTPUT_DIR}")
    print(f"{'='*30}")

if __name__ == "__main__":
    process_local_batch_results()