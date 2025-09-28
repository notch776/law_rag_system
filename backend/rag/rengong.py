import re
from fuzzywuzzy import fuzz

#Transfer to human agent detection (including keyword matching, regular expressions, and fuzzy matching)
class HumanHandoffDetector:
    def __init__(self):

        self.keywords = [
            "转人工", "人工客服", "找客服", "找人", "客服",
            "人工", "客服热线", "人工服务", "我要投诉", "真人", "没用", "机器人"
        ]

        self.patterns = [
            r"(找.*[人服])",  # 找人, 找客服, 找个真人
            r"(换.*[人服])",  # 换人, 换客服
            r"(人工.*)",  # 人工服务, 人工客服
            r"(客服.*热线)", #客服热线
            r"(有人.*吗)" #有人能来帮吗
        ]

        self.fuzzy_threshold = 80

    def need_human(self, user_input: str) -> bool:

        text = user_input.strip().lower()

        for kw in self.keywords:
            if kw.lower() in text:
                return True

        for pattern in self.patterns:
            if re.search(pattern, text):
                return True

        for kw in self.keywords:
            score = fuzz.partial_ratio(kw.lower(), text)
            if score >= self.fuzzy_threshold:
                return True

        return False