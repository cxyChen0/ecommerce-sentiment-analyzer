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

# =====================================================================
# 工业级 CBEI 提示词基座 (全局复用，保证各模块评判标准绝对一致)
# =====================================================================
CBEI_PROMPT_BASE = """
# Role
你是一位资深的电商数据分析专家和消费者行为心理学家。你的目标是仔细阅读批量电商评论，并严格按照 CBEI（基于评论的员工影响力指数）的四个维度进行分类、打分、痛点提炼和关键词提取。

# Definitions & Boundaries (严格边界界定)
在处理每一条评论时，必须严格按照以下边界将其情感倾向归类。如果评论包含多个维度（如：“鞋好看但物流慢”），需拆解并分别计入【产品】和【物流】。
1. 【Product 产品】：包含质量、材质、口感、外观设计、功能效果、气味、尺码、商品本身包装（如礼盒）。排除价格和发货速度。
2. 【Price 价格】：包含性价比、是否划算、降价抱怨、优惠券使用、退差价。
3. 【Logistics 物流】：包含发货速度、运输速度、快递员态度、运输纸箱破损。
4. 【Service 服务】：包含售前咨询专业度、回复速度、售后退换货效率、态度、虚假发货通知。

# Scoring Standards (量化打分标准)
你需要为这四个维度分别给出一个综合的【绝对满意度得分】（范围：0 到 100 分）。
- 强好评倾向 (80-100分)：超出预期，多次复购，“非常棒”、“绝了”。
- 中评/中性倾向 (40-79分)：符合预期，没有明显缺点，“还行”、“一分钱一分货”。
- 差评倾向 (0-39分)：明确指出缺陷，表达愤怒、失望，“垃圾”、“退货”。
*(注：如果样本中没有任何关于某维度的评论，该维度默认给 50 分)*。

# JSON Output Format (强制输出格式)
在你的分析报告的最末尾，你必须严格输出一段纯净的 JSON 格式数据。
【 强制执行指令】：
1. 自动品类识别：根据商品名称和评论内容，判断其是否属于以下四个大类：digital（数码）、lifestyle（生活用品）、snack（零食）、sports（运动）。如果属于则将其所属大类的英文填入 `category` 字段，否则将 general 填入 `category` 字段。
2. 【词汇量动态扩充与权重控制法则】（核心！）：为了保证前端词云视觉丰满，请尽量让每个维度的 positive/negative_keywords 输出 10-15 个词，但必须严格遵循以下阶梯事实法则：
   - 核心提取 (权重 70-100)：原文中明确提及的具体痛点/爽点词汇，直接提取并赋予高权重。
   - 语义泛化 (权重 5-40)：如果原文样本极少导致词汇不足，允许你基于**仅有的真实样本**进行“同义词替换、相关场景推演、或上级概念归纳”来扩充词库。
   - 严禁无中生有：泛化扩充必须与原文情感基调绝对绑定！若原文根本没有任何关于某维度（如物流）的反馈，则该维度的词云直接输出空字典 `{}`，绝不可强行捏造！
3. 核心痛点 core_pain_points：严格基于真实样本总结，如果没有真实群体性痛点，输出空数组 `[]`。

请务必严格模仿以下 JSON 结构的丰满程度进行输出（不要包裹在 ```json 代码块中，直接输出大括号包裹的纯文本）：
{
  "category": "sports",
  "scores": {
    "product": 90,
    "price": 20,
    "logistics": 65,
    "service": 20
  },
  "dimensions_data": {
    "product": {
      "positive_keywords": {"面料舒服": 100, "版型绝佳": 80, "透气性强": 60, "尺码标准": 40, "颜色很正": 20, "做工精细": 10, "轻便": 5},
      "negative_keywords": {"起球严重": 100, "洗后掉色": 80, "线头太多": 60, "有异味": 40, "领口变形": 20, "材质扎人": 10, "显胖": 5},
      "core_pain_points": ["深色款式存在严重掉色风险，污染其他衣物", "洗涤两三次后大面积起球，面料耐用性差", "领口设计缺陷导致容易松垮变形"]
    },
    ...
  }
}
"""


def get_client(model_name, user_provided_key=None):
    """
    获取OpenAI兼容客户端 (支持智能路由与密钥隔离)
    """
    if not OPENAI_AVAILABLE:
        return None

    is_volcengine = model_name.startswith("ep-") or "doubao" in model_name.lower()

    # 【获取环境变量】在此处读取 .env 文件中的 API Key
    sys_aliyun = os.getenv("ALIYUN_API_KEY")
    sys_volc = os.getenv("VOLC_API_KEY")

    if is_volcengine:
        # 【修复点 1】：去掉了多余的 Markdown 超链接括号
        base_url = "https://ark.cn-beijing.volces.com/api/v3"

        if user_provided_key and user_provided_key != sys_aliyun:
            api_key = user_provided_key
        else:
            api_key = sys_volc

    else:
        # 【修复点 2】：去掉了多余的 Markdown 超链接括号，使用兼容模式官方 URL
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        if user_provided_key and user_provided_key != sys_volc:
            api_key = user_provided_key
        else:
            api_key = sys_aliyun

    if not api_key:
        return None

    # 将获取到的环境变量传递给底层 OpenAI 客户端进行鉴权
    return OpenAI(api_key=api_key, base_url=base_url)


def stream_wrapper(client, model, messages):
    yield f">  **分析引擎**：`{model}` \n\n"
    extra_params = {"enable_thinking": True} if "r1" in model.lower() or "deepseek" in model.lower() else {}

    try:
        # 【核心修改】：解除字数封印，并让 AI 变得冷酷严谨！
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=4096,  # 给足 4096 个 Token 的答题纸，确保 JSON 绝对能写完
            temperature=0.3,  # 降低温度，杜绝幻觉，保证严格按照结构输出 JSON
            top_p=0.9,  # 收拢概率采样，让用词更精准
            extra_body=extra_params
        )

        is_thinking, has_answered = False, False

        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not is_thinking:
                        yield ">  **深度思考过程**：\n> "
                        is_thinking = True
                    yield delta.reasoning_content.replace("\n", "\n> ")

                if hasattr(delta, "content") and delta.content:
                    if is_thinking and not has_answered:
                        yield "\n\n---\n\n"
                        is_thinking, has_answered = False, True
                    yield delta.content

    except Exception as e:
        yield f"\n\n **AI 分析中断**: {str(e)}"


# =====================================================================
# 1. 单品诊断分析
# =====================================================================
def analyze_single_product_stream(product_name, comments_list, sales_volume=0, api_key=None, model="deepseek-v3.2-exp"):
    client = get_client(model, api_key)
    if not client:
        yield " 未配置对应平台的 API Key"
        return

    valid_formatted_comments = []

    for c in comments_list:
        if isinstance(c, dict):
            # 如果是新版本传入的字典
            content = str(c.get('content', '')).strip()
            date_str = str(c.get('date', '未知')).strip()

            # 只判断真实评论内容的长度
            if len(content) > 4:
                # 拼接成极度易读的格式：[日期] 内容
                valid_formatted_comments.append(f"[{date_str}] {content}")
        else:
            # 向下兼容：万一别的地方还传老的纯文本进来
            content = str(c).strip()
            if len(content) > 4:
                valid_formatted_comments.append(f"[未知] {content}")

    # 取前 100 条组合成文本串
    text_input = "\n".join(valid_formatted_comments[:150])
    # ==========================================

    system_prompt = CBEI_PROMPT_BASE + f"""
    ### 附加报告生成指令：
    在输出最后的 CBEI JSON 数据之前，请先输出一份 Markdown 格式的单品诊断报告。拒绝废话，直击商业本质：

    # {product_name} 单品诊断报告

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

    【 强制执行指令 】：
    报告结束后，严格按照 CBEI 的大括号 JSON 格式输出数据。请严格遵守全局规则中的【词汇量动态扩充与权重控制法则】，对微小样本进行零幻觉的语义推演，并保持权重断崖式分布以突出主次。若毫无样本，坚决输出空字典。

    严厉警告：
    如果你的模型支持输出前置的深度思考或推演过程，请注意：在【思考/推演过程】阶段，绝对禁止使用任何 Markdown 格式的标题语法（例如不要使用 #、##、###）。思考过程必须是纯碎的普通段落文本。只有在输出最终正式报告时，才能使用上述 Markdown 语法。
    """

    user_prompt = f"【分析目标商品】：{product_name}\n【当前总销量】：{sales_volume}\n\n【用户评论数据样本】：\n{text_input}"
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
    yield from stream_wrapper(client, model, messages)


# =====================================================================
# 2. 市场品类趋势分析
# =====================================================================
def analyze_market_trends_stream(search_query, comments_list, api_key=None, model="qwen-max"):
    client = get_client(model, api_key)
    if not client:
        yield " 未配置对应平台的 API Key"
        return

    valid_formatted_comments = []
    for c in comments_list:
        if isinstance(c, dict):
            content = str(c.get('content', '')).strip()
            date_str = str(c.get('date', '未知')).strip()
            if len(content) > 4:
                valid_formatted_comments.append(f"[{date_str}] {content}")
        else:
            content = str(c).strip()
            if len(content) > 4:
                valid_formatted_comments.append(f"[未知] {content}")

    text_input = "\n".join(valid_formatted_comments[:200])

    system_prompt = CBEI_PROMPT_BASE + f"""
    ### 附加报告生成指令：
    在输出最后的 CBEI JSON 数据之前，请先输出一份 Markdown 格式的市场品类趋势调研报告。客观总结现状与痛点：

    # {search_query} 市场品类趋势调研报告

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
    【 强制执行指令 】：
    报告结束后，严格按照 CBEI 的大括号 JSON 格式输出数据。请严格遵守全局规则中的【词汇量动态扩充与权重控制法则】，对微小样本进行受控的语义泛化，若无特定维度的评价请保持空字典。
    
    严厉警告：前置思考过程绝对禁止使用任何 Markdown 标题语法（#、## 等）。
    """

    user_prompt = f"【当前调研市场/关键词】：{search_query}\n\n【全网竞品混合评论样本】：\n{text_input}"
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
    yield from stream_wrapper(client, model, messages)


# =====================================================================
# 3. 竞品对比分析
# =====================================================================
def analyze_competitor_comparison_stream(my_product_name, my_comments, competitor_comments, api_key=None,
                                         model="qwen-max", single_ai_report=None):
    client = get_client(model, api_key)
    if not client:
        yield " 未配置对应平台的 API Key"
        return

    def format_comments(comments_data, limit=50):
        formatted = []
        for c in comments_data:
            if isinstance(c, dict):
                content = str(c.get('content', '')).strip()
                date_str = str(c.get('date', '未知')).strip()
                if len(content) > 4:
                    formatted.append(f"[{date_str}] {content}")
            else:
                content = str(c).strip()
                if len(content) > 4:
                    formatted.append(f"[未知] {content}")
        return "\n".join(formatted[:limit])

    # 调用格式化函数
    my_text = format_comments(my_comments, limit=150)
    comp_text = format_comments(competitor_comments, limit=150)

    system_prompt = CBEI_PROMPT_BASE + f"""
        ### 附加报告生成指令：
        在输出最后的 CBEI JSON 数据之前，请基于对比数据输出一份客观、冷酷的 Markdown 诊断报告。切忌偏袒本品：

        # ⚖️ {my_product_name} 竞品差异化诊断报告

        ### 1. 📊 核心能力雷达比对
        | 评估维度 | 本品核心表现 | 竞品核心表现 | 优劣势判定 |
        | :--- | :--- | :--- | :--- |
        | **产品体验** | ... | ... | (本品优 / 竞品优 / 均等) |
        | **价格感受** | ... | ... | ... |
        | **服务水平** | ... | ... | ... |
        | **物流履约** | ... | ... | ... |

        ### 2. 🚨 严重落后项警告 (本品劣势)
        *列出本品明显不如竞品的痛点，这是导致客户流失的核心原因。*
        - ...

        ### 3. 🛡️ 核心壁垒项 (本品优势)
        *列出本品明显优于竞品的点，这是我们需要在详情页主打的卖点。*
        - ...

        ### 4. 📌 战术动作下达
        *列出 3 条具体、可执行的优化动作。*

        --------
        【 强制执行指令 - 竞品对比专属 JSON 格式 】：
        注意：请忽略上方全局设定的单品 JSON 格式！在此次竞品对比任务中，你必须严格输出以下包含双边数据的 JSON 结构。
        确保分数和权重客观反映两者的真实差异：

        {{
          "category": "sports",
          "comparison_scores": {{
            "product": {{"mine": 85, "competitor": 92}},
            "price": {{"mine": 70, "competitor": 65}},
            "logistics": {{"mine": 90, "competitor": 90}},
            "service": {{"mine": 60, "competitor": 80}}
          }},
          "dimensions_data": {{
            "product": {{
              "my_advantages": {{"面料舒服": 100, "透气": 80}},
              "my_pain_points": {{"起球": 100, "掉色": 60}},
              "comp_advantages": {{"版型绝佳": 100, "设计感强": 90}},
              "comp_pain_points": {{"线头多": 80, "偏贵": 50}},
              "core_difference": "竞品在版型设计上占据绝对优势，但本品在基础面料舒适度上更胜一筹。"
            }},
            "price": {{ ... }},
            "logistics": {{ ... }},
            "service": {{ ... }}
          }}
        }}

        严厉警告：前置思考过程绝对禁止使用任何 Markdown 标题语法（#、## 等）。大括号 JSON 必须放在回复的最末尾。
        """

    user_prompt = f"【本品评价数据】\n{my_text}\n\n【竞品评价数据】\n{comp_text}"

    if single_ai_report:
        user_prompt += f"\n\n【前期本品 AI 深度诊断报告与评分基准】\n以下是本品前期的独立分析报告（包含末尾的 JSON 打分）。\n请你严格参考此报告中 JSON 里的各项分数作为本品分数，并以此为绝对基准来评估竞品的分差！\n\n{single_ai_report}"

    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
    yield from stream_wrapper(client, model, messages)