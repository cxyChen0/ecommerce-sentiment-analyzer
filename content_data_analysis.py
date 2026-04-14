import pandas as pd
import os
import json
import re
import requests
from dotenv import load_dotenv
load_dotenv()

# ===================== 配置 =====================
BATCH_SIZE = 10
API_KEY = os.getenv("ALIYUN_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ===================== 【终极容错】JSON 修复 =====================
def robust_json_parse(text):
    try:
        text = re.sub(r'[^\w\s\[\]\{\},:"]', ' ', text)
        text += ']' * max(0, text.count('[') - text.count(']'))
        text += '}' * max(0, text.count('{') - text.count('}'))

        arr_match = re.search(r'\[.*\]', text, re.DOTALL)
        if not arr_match:
            return None

        s = arr_match.group(0)
        s = re.sub(r'\{\{+', '{', s)
        s = re.sub(r'\}\}+', '}', s)
        s = re.sub(r'\}\s*\{', '},{', s)
        s = re.sub(r'(\d|")\s*{', r'\1,{', s)
        s = re.sub(r',\s*}', '}', s)
        s = re.sub(r',\s*]', ']', s)

        data = json.loads(s)
        if not isinstance(data, list):
            return None

        res = []
        for item in data:
            if isinstance(item, dict):
                res.append({
                    "product": int(item.get("product", 0)),
                    "service": int(item.get("service", 0)),
                    "logistics": int(item.get("logistics", 0)),
                    "price": int(item.get("price", 0))
                })
        return res

    except:
        return None

# ===================== 批量分析（最强稳定版提示词） =====================
def analyze_batch(comments_batch):
    comment_text = "\n".join([f"{i}. {c}" for i, c in enumerate(comments_batch)])

    prompt = f"""
你是专业的商品评论关注度分析师，只做严格的数值计算。
任务：对每一条评论，分析4个维度的关注度百分比，四个数字加起来必须 = 100。

维度定义：
1. product：产品本身（质量、功能、外观、性能）
2. service：客服、售后、发货速度
3. logistics：物流、快递、包装、配送
4. price：价格、性价比、优惠、划算程度

【输出规则】
1. 每条评论输出一个JSON对象
2. 只输出JSON数组，不要任何解释、不要文字、不要备注
3. 数字必须是整数，总和严格等于100
4. 严格按顺序输出，与评论一一对应

【格式示例（2条评论）】
[
  {{"product":50,"service":10,"logistics":20,"price":20}},
  {{"product":100,"service":0,"logistics":0,"price":0}}
]

请分析以下{len(comments_batch)}条评论：
{comment_text}
"""

    try:
        data = {
            "model": "qwen-long",  # 最优：数值准、格式稳、便宜
            # "model": "qwen-max", # 备选：最准，但贵一点
            "input": {"messages": [{"role": "user", "content": prompt}]},
            "parameters": {
                "temperature": 0,          # 最稳定，不发散
                "top_p": 0.05,             # 只选最高概率词
                "seed": 12345,             # 固定种子，完全可复现
                # "response_format": {"type": "json"}
            }
        }
        resp = requests.post(API_URL, headers=HEADERS, json=data, timeout=60)
        print("=== API 响应 ===")
        print("状态码:", resp.status_code)
        # print("响应文本:", resp.text)
        result_text = resp.json()["output"]["choices"][0]["message"]["content"]

        print("\n==================================")
        print("本批次 AI 返回结果：")
        print(result_text)
        print("==================================\n")
        return robust_json_parse(result_text)


    except Exception as e:
        # 新增：打印异常信息
        print("=== API 调用异常 ===")
        print(e)
        return None

# ===================== 处理分类 =====================
def process_category(input_csv, output_csv):
    # 上次处理到第几行
    processed_lines = 0
    if os.path.exists(output_csv):
        tmp = pd.read_csv(output_csv, encoding="utf-8-sig")
        processed_lines = len(tmp)  # 直接等于已处理评论数，无需减1

    if not os.path.exists(input_csv):
        return

    df = pd.read_csv(input_csv, encoding="utf-8-sig")
    comments = df["content"].fillna("").astype(str).str.strip().tolist()

    discarded = 0

    for i in range(processed_lines, len(comments), BATCH_SIZE):
        batch = comments[i:i+BATCH_SIZE]

        start = i + 1
        end = min(i + BATCH_SIZE, len(comments))
        print(f"📍 处理 {input_csv} → 当前批次：{start} ~ {end}")

        res = analyze_batch(batch)
        if res and len(res) == len(batch):
            # 只保留未处理过的
            new_data = [[c, r["product"], r["service"], r["logistics"], r["price"]] for c, r in zip(batch, res)]
            if new_data:
                batch_df = pd.DataFrame(new_data, columns=["content", "product", "service", "logistics", "price"])
                batch_df.to_csv(output_csv, mode="a", header=not os.path.exists(output_csv), index=False,
                                encoding="utf-8-sig")

            print(f"✅ 批次 {i // BATCH_SIZE + 1} 成功 → 已保存")
        else:
            discarded += len(batch)
            # 失败也写入，标记错误
            fail_data = [[c, -1, -1, -1, -1] for c in batch]
            fail_df = pd.DataFrame(fail_data, columns=["content", "product", "service", "logistics", "price"])
            fail_df.to_csv(output_csv, mode="a", header=not os.path.exists(output_csv), index=False,
                           encoding="utf-8-sig")
            print(f"❌ 批次失败 → 已标记为 -1")

    # ============= 自动计算成功率 =============
    df_final = pd.read_csv(output_csv, encoding="utf-8-sig")
    total = len(df_final)
    success = len(df_final[df_final["product"] != -1])
    rate = round(success / total * 100, 2) if total > 0 else 0

    print(f"总数据量：{total} 条")
    print(f"成功：{success} 条")
    print(f"失败：{total - success} 条")
    print(f"成功率：{rate}%")

# ===================== 执行 =====================
if __name__ == "__main__":
    tasks = {
        "cleaned_lifestyle.csv": "attention_lifestyle.csv"
    }
    for i, o in tasks.items():
        process_category(i, o)