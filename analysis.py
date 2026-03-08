import os
import re
from dotenv import load_dotenv

load_dotenv()

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False


def get_client(model_name, user_provided_key=None):
    """
    获取OpenAI兼容客户端 (支持智能路由与密钥隔离)
    """
    if not OPENAI_AVAILABLE:
        return None

    is_volcengine = model_name.startswith("ep-") or "doubao" in model_name.lower()

    # 提取系统底层的默认 Key
    sys_aliyun = os.getenv("ALIYUN_API_KEY")
    sys_volc = os.getenv("VOLC_API_KEY")

    if is_volcengine:
        # 火山方舟(豆包)
        base_url = "https://ark.cn-beijing.volces.com/api/v3"

        if user_provided_key and user_provided_key != sys_aliyun:
            api_key = user_provided_key  # 强制使用用户传入的Key，哪怕是乱填的 "12345"
        else:
            api_key = sys_volc

    else:
        # ======= 阿里云百炼通道 =======
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        if user_provided_key and user_provided_key != sys_volc:
            api_key = user_provided_key  # 强制使用用户传入的Key
        else:
            api_key = sys_aliyun

    if not api_key:
        return None

    return OpenAI(api_key=api_key, base_url=base_url)

def stream_wrapper(client, model, messages):
    """通用流式包装器 (支持深度思考模式)"""
    yield f">  **分析引擎**：`{model}` \n\n"

    extra_params = {}
    if "r1" in model.lower() or "deepseek" in model.lower():
        extra_params = {"enable_thinking": True}

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            extra_body=extra_params
        )

        is_thinking = False
        has_answered = False

        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta

                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not is_thinking:
                        yield ">  **深度思考过程**：\n> "
                        is_thinking = True
                    content = delta.reasoning_content.replace("\n", "\n> ")
                    yield content

                if hasattr(delta, "content") and delta.content:
                    if is_thinking and not has_answered:
                        yield "\n\n---\n\n"
                        is_thinking = False
                        has_answered = True
                    yield delta.content

    except Exception as e:
        yield f"\n\n **AI 分析中断**: {str(e)}"

# ==========================================
# 1. 单品深度分析 (精准数据导向版)
# ==========================================
def analyze_single_product_stream(product_name, comments_list, sales_volume=0, api_key=None, model="deepseek-v3.2-exp"):
    client = get_client(model, api_key)
    if not client:
        yield " 未配置对应平台的 API Key (阿里云或火山引擎)"
        return

    valid_comments = [str(c) for c in comments_list if len(str(c)) > 4]
    text_input = "\n".join(valid_comments[:80]) # 增加样本量提升好评率计算准确度

    system_prompt = f"""
    你是一位严谨的电商数据分析师。请基于提供的用户评论数据，输出客观、直接、一针见血的诊断报告。
    不需要花哨的营销词汇，必须提供明确的数据预估和具体的改进方向。

    ### 报告结构要求：
    #  {product_name}单品诊断报告

    ### 1. 📊 核心指标预估 (供数据库记录参考)
    - **预估好评率**：[请严格根据评论的情感倾向，推算出一个具体的百分比，例如 82%]
    - **核心关注标签**：[提取3-5个用户最关注的客观属性，如：材质、发货速度、包装]

    ### 2. ⚠️ 核心痛点与缺陷 (按严重程度排序)
    *要求：直击要害，必须指出具体的导致差评的原因。*
    - **[痛点1简述]**：[具体表现] (引用1句典型原声：> "...")
    - **[痛点2简述]**：[具体表现] (引用1句典型原声：> "...")

    ### 3. ⭐ 核心优势与爽点
    *要求：找出用户真正愿意掏钱或复购的理由。*
    - **[优势1简述]**：[具体表现]
    - **[优势2简述]**：[具体表现]

    ### 4. 🛠️ 改进方向与执行建议 (一针见血)
    - **供应链/产品端**：[指出需要改进的工艺、材质或品控环节]
    - **运营/客服端**：[指出详情页需要规避的预期差，或客服需要增加的话术]
    
    --------
    在报告的最后，严格输出两段独立的 JSON 数据（分别代表正面好评特征、负面差评特征），用于生成词云。
    【 强制执行指令】：
    1. 数量达标：正面词云和负面词云的字典中，**每一个都必须绝对包含至少 20 个的特征词**！严禁偷懒！如果原始评论较少，请利用商业推理强行细分维度（如将“好用”拆分为手感、外观、出墨、包装等）。
    2. 【极其重要！权重极度分化】：为了在词云中形成强烈的视觉主次感，权重必须**呈断崖式的阶梯分布**！
       - 最核心的 1-2 个决定性特征，权重必须给 90-100。
       - 次要的 3-5 个特征，权重给 40-60。
       - 剩下的 15 个以上的长尾凑数词汇，权重强制压低到 5-15 之间。
       - 严禁出现所有词权重都集中在 70-90 的情况，必须突出重点！
    3. 提取词必须是“具体属性/场景 + 评价”的短语，坚决去除无意义废话。
    
    格式必须严格如下（分成两个独立的代码块）：
    ```json
    {{"positive_wordcloud": {{"书写极度顺滑": 100, "握感舒适": 50, "墨水均匀": 45, "其他凑数词汇": 10, "必须写满20个": 5}}}}
    ```
    
    ```json
    {{"negative_wordcloud": {{"原装笔芯断墨": 100, "假货争议": 55, "笔夹歪斜": 40, "其他凑数词汇": 12, "必须写满20个": 8}}}}
    ```
    
    严厉警告：
    如果你的模型支持输出前置的深度思考或推演过程，请注意：在你的【思考/推演过程】阶段，绝对禁止使用任何 Markdown 格式的标题语法（例如不要使用 #、##、###）。思考过程必须是纯碎的普通段落文本。只有在输出最终正式报告时，才能使用上述 Markdown 语法。
    """

    # 【修改点】：在传给 AI 的 user content 中，明确告诉它商品标题和当前销量
    user_prompt = f"【分析目标商品】：{product_name}\n【当前总销量】：{sales_volume}\n\n【用户评论数据样本】：\n{text_input}"

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': f"【用户评论数据样本】：\n{user_prompt}"}
    ]
    yield from stream_wrapper(client, model, messages)

# ==========================================
# 2. 市场调研分析 (加入搜索关键词/市场名称)
# ==========================================
def analyze_market_trends_stream(search_query, comments_list, api_key=None, model="qwen-plus"):
    client = get_client(model, api_key)
    if not client:
        yield " 未配置对应平台的 API Key"
        return

    text_input = "\n".join(comments_list[:100])

    system_prompt = f"""
    你是一位专业的行业调研分析师。基于这批市场热销竞品的混合评论，请客观总结该品类的市场现状和未被满足的痛点。
    拒绝废话，直击商业本质。

    ###  报告结构要求：
    # {search_query}市场品类趋势调研报告

    ### 1. 🎯 消费者核心决策因子
    *按重要性降序，列出决定用户购买的 Top 3 因素。*
    1. **[因子名称]**：[具体解释为什么用户看重这个]
    2. ...

    ### 2. 🌊 市场共性痛点 (机会空间)
    *总结目前市场上头部产品依然存在的普遍问题，这正是新品切入的机会。*
    - **[共性痛点1]**：...
    - **[共性痛点2]**：...

    ### 3. 💡 差异化突围建议
    *基于上述痛点，如果我们要研发/上架一款新品，建议在哪些方面做差异化打法？*
    - **产品差异化**：...
    - **服务差异化**：...
    
    --------
    在报告的最后，严格输出两段独立的 JSON 数据（分别代表正面好评特征、负面差评特征），用于生成词云。
    【 强制执行指令】：
    1. 数量达标：正面词云和负面词云的字典中，**每一个都必须绝对包含至少 20 个的特征词**！严禁偷懒！如果原始评论较少，请利用商业推理强行细分维度（如将“好用”拆分为手感、外观、出墨、包装等）。
    2. 【极其重要！权重极度分化】：为了在词云中形成强烈的视觉主次感，权重必须**呈断崖式的阶梯分布**！
       - 最核心的 1-2 个决定性特征，权重必须给 90-100。
       - 次要的 3-5 个特征，权重给 40-60。
       - 剩下的 15 个以上的长尾凑数词汇，权重强制压低到 5-15 之间。
       - 严禁出现所有词权重都集中在 70-90 的情况，必须突出重点！
    3. 提取词必须是“具体属性/场景 + 评价”的短语，坚决去除无意义废话。
    
    格式必须严格如下（分成两个独立的代码块）：
    ```json
    {{"positive_wordcloud": {{"书写极度顺滑": 100, "握感舒适": 50, "墨水均匀": 45, "其他凑数词汇": 10, "必须写满20个": 5}}}}
    ```
    
    ```json
    {{"negative_wordcloud": {{"原装笔芯断墨": 100, "假货争议": 55, "笔夹歪斜": 40, "其他凑数词汇": 12, "必须写满20个": 8}}}}
    ```
    
    严厉警告：
    如果你的模型支持输出前置的深度思考或推演过程，请注意：在你的【思考/推演过程】阶段，绝对禁止使用任何 Markdown 格式的标题语法（例如不要使用 #、##、###）。思考过程必须是纯碎的普通段落文本。只有在输出最终正式报告时，才能使用上述 Markdown 语法。
    """

    # 【修改点】：明确告诉 AI 当前调研的市场或关键词是什么
    user_prompt = f"【当前调研市场/关键词】：{search_query}\n\n【全网竞品混合评论样本】：\n{text_input}"

    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
    yield from stream_wrapper(client, model, messages)

# ==========================================
# 3. 竞品比对 (战力客观对比版)
# ==========================================
def analyze_competitor_comparison_stream(my_product_name, my_comments, competitor_comments, api_key=None, model="qwen-max"):
    client = get_client(model, api_key)
    if not client:
        yield " 未配置对应平台的 API Key"
        return

    my_text = "\n".join([str(c) for c in my_comments[:50]])
    comp_text = "\n".join([str(c) for c in competitor_comments[:50]])

    system_prompt = f"""
    你是一名商业数据分析师。请对本品（{my_product_name}）与市场竞品进行客观、冷酷的横向数据对比。
    切忌偏袒本品，指出真实的差距。

    ### 报告结构要求：
    # ⚖️ 竞品差异化诊断报告

    ### 1. 📊 核心能力雷达比对
    | 评估维度 | 本品核心表现 | 竞品核心表现 | 优劣势判定 |
    | :--- | :--- | :--- | :--- |
    | **品质做工** | ... | ... | (本品优 / 竞品优 / 均等) |
    | **性价比感知** | ... | ... | ... |
    | **服务体验** | ... | ... | ... |

    ### 2. 🚨 严重落后项警告
    *列出本品明显不如竞品的痛点，这是导致客户流失的核心原因。*
    - ...

    ### 3. 🛡️ 核心壁垒项
    *列出本品明显优于竞品的点，这是我们需要在详情页主打的卖点。*
    - ...

    ### 4. 📌 战术动作下达
    *列出 3 条具体、可执行的优化动作（针对供应链或运营）。*
    1. ...
    2. ...
    3. ...
    
    ------
    在报告的最后，基于本品的评价数据，严格输出两段独立的 JSON 数据（代表本品的正面优势特征、负面劣势特征），用于生成词云。
    【强制执行指令】：
    1. 数量达标：正面优势词云和负面劣势词云的字典中，**每一个都必须绝对包含至少 20 个的特征词**！严禁偷懒！如果原始评论较少，请利用商业推理强行细分维度。
    2. 【极其重要！权重极度分化】：为了在词云中形成强烈的视觉主次感，权重必须**呈断崖式的阶梯分布**！
       - 最核心的 1-2 个优势/劣势，权重必须给 90-100。
       - 次要的 3-5 个特征，权重给 40-60。
       - 剩下的 15 个以上的长尾凑数词汇，权重强制压低到 5-15 之间。
       - 严禁出现所有词权重都集中在 70-90 的情况，必须突出重点！
    3. 提取词必须是“具体属性/场景 + 评价”的短语，坚决去除无意义废话。
    
    格式必须严格如下（分成两个独立的代码块）：
    ```json
    {{"positive_wordcloud": {{"书写极度顺滑": 100, "握感舒适": 50, "性价比高": 45, "凑数词1": 10, "必须满20个": 5}}}}
    ```
    ```json
    {{"negative_wordcloud": {{"原装笔芯断墨": 100, "做工粗糙": 55, "物流太慢": 40, "凑数词1": 12, "必须满20个": 8}}}}
    ```
    
    严厉警告：
    如果你的模型支持输出前置的深度思考或推演过程，请注意：在你的【思考/推演过程】阶段，绝对禁止使用任何 Markdown 格式的标题语法（例如不要使用 #、##、###）。思考过程必须是纯碎的普通段落文本。只有在输出最终正式报告时，才能使用上述 Markdown 语法。
    """

    user_prompt = f"【本品评价数据】\n{my_text}\n\n【竞品评价数据】\n{comp_text}"
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]

    yield from stream_wrapper(client, model, messages)