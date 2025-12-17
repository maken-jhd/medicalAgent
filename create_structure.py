import os

def mirror_structure_and_create_jsonl(source_root, target_root):
    """
    复制目录结构，并将.md文件转换为空的.jsonl文件
    """
    # 检查源文件夹是否存在
    if not os.path.exists(source_root):
        print(f"错误：未找到源文件夹 '{source_root}'")
        return

    print(f"开始处理：从 '{source_root}' 到 '{target_root}' ...")

    # 遍历源文件夹
    for root, dirs, files in os.walk(source_root):
        # 计算相对路径，用于在目标文件夹中构建相同的层级
        relative_path = os.path.relpath(root, source_root)
        target_dir = os.path.join(target_root, relative_path)

        # 如果目标子目录不存在，则创建
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        # 遍历当前目录下的文件
        for filename in files:
            # 检查文件后缀是否为 .md
            if filename.endswith('.md'):
                # 获取文件名（不带后缀）
                base_name = os.path.splitext(filename)[0]
                # 拼接新的文件名
                new_filename = f"{base_name}.jsonl"
                # 拼接完整的目标路径
                target_file_path = os.path.join(target_dir, new_filename)

                # 创建一个新的空 .jsonl 文件
                try:
                    with open(target_file_path, 'w', encoding='utf-8') as f:
                        pass # 这里什么都不做，只创建一个空文件
                    print(f"已创建: {target_file_path}")
                except IOError as e:
                    print(f"创建文件失败: {target_file_path}, 错误: {e}")

if __name__ == '__main__':
    # 定义源文件夹和目标文件夹名称
    source_folder = "诊疗指南整合"
    target_folder = "诊疗指南整合step2（创建病例）"

    mirror_structure_and_create_jsonl(source_folder, target_folder)
    print("\n处理完成！")