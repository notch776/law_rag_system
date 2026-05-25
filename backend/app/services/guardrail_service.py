from typing import Tuple


class GuardrailService:
    def __init__(self):
        self.handoff_keywords = ["转人工", "人工客服", "找客服", "找律师", "真人", "投诉"]
        self.illegal_keywords = ["逃避执行", "转移资产", "骗", "诈骗", "规避社保", "不被抓", "洗钱"]

    def need_human(self, query: str) -> bool:
        return any(k in query for k in self.handoff_keywords)

    def reject_reason(self, query: str) -> Tuple[bool, str]:
        if any(k in query for k in self.illegal_keywords):
            return True, "抱歉，我不能帮助规避法律义务、逃避执行或实施违法行为。你可以咨询合法合规的权利救济路径。"
        return False, ""
