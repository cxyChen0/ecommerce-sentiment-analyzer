import os
import pandas as pd

def merge_csv_files(input_dir: str, output_filename: str, has_header: bool = True):
    # 只筛选符合格式的文件：content_snakes数字.csv
    csv_files = []
    for f in os.listdir(input_dir):
        if f.endswith('.csv') and f.startswith("content_snakes"):
            # 提取文件名中的数字部分
            name_without_ext = os.path.splitext(f)[0]
            num_part = name_without_ext.replace("content_snakes", "")
            if num_part.isdigit():  # 确保是纯数字
                csv_files.append(f)

    if not csv_files:
        print("未找到符合格式的 CSV 文件！")
        return

    # 按数字 0,1,2,3... 严格排序
    def get_sort_key(filename):
        num = filename.replace("content_snakes", "").replace(".csv", "")
        return int(num)

    csv_files.sort(key=get_sort_key)
    print("✅ 正确合并顺序：", csv_files)

    merged_data = []
    for idx, file_name in enumerate(csv_files, 1):
        file_path = os.path.join(input_dir, file_name)
        try:
            # 自动尝试编码，解决中文乱码/报错
            try:
                df = pd.read_csv(file_path, encoding='utf-8', on_bad_lines='skip')
            except:
                df = pd.read_csv(file_path, encoding='gbk', on_bad_lines='skip')

            # 跳过重复表头
            if has_header and idx > 1:
                df = df.iloc[1:]

            merged_data.append(df)
            print(f"已读取：{file_name}")

        except Exception as e:
            print(f"读取失败 {file_name}: {e}")

    if not merged_data:
        print("没有可合并的数据！")
        return

    # 合并并保存
    final_df = pd.concat(merged_data, ignore_index=True)
    final_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
    print(f"\n🎉 全部合并完成！文件：{output_filename}")

if __name__ == "__main__":
    merge_csv_files(
        input_dir="./",
        output_filename="content_snack.csv",  # 你要的最终文件名
        has_header=True
    )