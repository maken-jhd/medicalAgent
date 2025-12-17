import requests
import json
import os
import sys

# ================= 配置区域 =================
API_KEY = "sk-vsfrmtzhbyadnxhkafnxzicdlisrivlcqhkbveduyfqcocsh"  
BATCH_INPUT_FILE = "batch_input.jsonl" 
BASE_URL = "https://api.siliconflow.cn/v1" 
# ===========================================

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

def submit_batch():
    # 0. 检查文件是否存在
    if not os.path.exists(BATCH_INPUT_FILE):
        print(f"[Error] 找不到文件: {BATCH_INPUT_FILE}")
        print("请检查文件名是否正确，或者是否已运行 Step 1。")
        return

    # 1. 上传文件
    print(f"正在上传文件: {BATCH_INPUT_FILE} ...")
    files = {
        # 显式指定 application/jsonl 类型，防止服务端识别错误
        'file': (os.path.basename(BATCH_INPUT_FILE), open(BATCH_INPUT_FILE, 'rb'), 'application/jsonl')
    }
    
    try:
        upload_resp = requests.post(
            f"{BASE_URL}/files", 
            headers=headers, 
            files=files, 
            data={"purpose": "batch"},
            timeout=60 # 上传大文件可能需要较长时间
        )
        
        if upload_resp.status_code != 200:
            print(f"[Error] 文件上传失败 (Code {upload_resp.status_code}):")
            print(upload_resp.text)
            return
        
        file_id = upload_resp.json()['id']
        print(f"✅ 文件上传成功，File ID: {file_id}")

    except Exception as e:
        print(f"[Error] 上传过程发生异常: {e}")
        return

    # 2. 创建 Batch 任务
    print("正在创建 Batch 任务...")
    batch_payload = {
        "input_file_id": file_id,
        "endpoint": "/v1/chat/completions",
        "completion_window": "24h",
        "metadata": {
            "description": "medical_guideline_sft_generation"
        }
        # 这里不加 replace，直接使用 JSONL 内部指定的模型
    }
    
    try:
        # 创建任务通常响应很快
        batch_resp = requests.post(
            f"{BASE_URL}/batches", 
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}, 
            json=batch_payload,
            timeout=30
        )
        
        if batch_resp.status_code == 200:
            batch_id = batch_resp.json()['id']
            print(f"✅ Batch 任务创建成功！Batch ID: {batch_id}")
            print(f"{'-'*30}")
            print(f"请务必保存 Batch ID: {batch_id}")
            print(f"{'-'*30}")
            
            # 将 Batch ID 保存到本地文件
            with open("current_batch_id.txt", "w") as f:
                f.write(batch_id)
            print("Batch ID 已保存至 current_batch_id.txt")
        else:
            print(f"[Error] 创建任务失败 (Code {batch_resp.status_code}):")
            print(batch_resp.text)
            
    except Exception as e:
        print(f"[Error] 创建任务请求异常: {e}")

if __name__ == "__main__":
    submit_batch()