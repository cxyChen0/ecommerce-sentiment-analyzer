import re
import json

def _update_wordclouds(data, pos_data, neg_data):
    """辅助函数：抽离更新逻辑，保持代码整洁"""
    if isinstance(data, dict):
        if "positive_wordcloud" in data:
            pos_data.update(data["positive_wordcloud"])
        if "negative_wordcloud" in data:
            neg_data.update(data["negative_wordcloud"])

def extract_dual_wordclouds(text):
    """终极鲁棒提取器 2.0：专治漏写、大小写错乱、纯文本混排"""
    pos_data, neg_data = {}, {}

    # 策略 1：放宽正则限制
    # (?:json)? 表示 json 这个词可有可无，re.IGNORECASE 忽略大小写
    # 使用 `{3} 代替连续三个反引号，避免网页解析器提前截断代码
    json_blocks = re.findall(r'`{3}(?:json)?\s*(.*?)\s*`{3}', text, re.DOTALL | re.IGNORECASE)

    # 策略 2：如果 AI 没写反引号，或者混排了导致正则没抓到
    # 直接在全文中寻找第一个 '{' 和最后一个 '}' 之间的内容
    if not json_blocks:
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            json_blocks = [text[start_idx:end_idx + 1]]

    for block in json_blocks:
        block = block.strip()
        if not block:
            continue

        try:
            # 正常情况：尝试直接解析
            data = json.loads(block)
            _update_wordclouds(data, pos_data, neg_data)

        except json.JSONDecodeError:
            # 异常修复 1：处理 `{...} {...}` (Extra data 报错)
            try:
                # 兼容 {}{}, {} {} 或者 {},{} 的情况
                fixed_block = re.sub(r'\}\s*,?\s*\{', '}, {', block)
                fixed_block = f"[{fixed_block}]"
                for d in json.loads(fixed_block):
                    _update_wordclouds(d, pos_data, neg_data)
            except json.JSONDecodeError:
                # 异常修复 2：如果代码块内部还混排了中文说明文本
                # 再做一次暴力抠大括号
                sub_start = block.find('{')
                sub_end = block.rfind('}')
                if sub_start != -1 and sub_end != -1 and sub_start < sub_end:
                    clean_block = block[sub_start:sub_end + 1]
                    try:
                        clean_data = json.loads(clean_block)
                        _update_wordclouds(clean_data, pos_data, neg_data)
                    except Exception:
                        pass  # 尽力了，实在救不回来就跳过

    return pos_data, neg_data