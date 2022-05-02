import re
from typing import *
from pydantic import BaseModel, Field

RE_PURE_DIGITS = re.compile(r'\d+', re.U)


class Age(BaseModel):
    gte: Optional[int] = Field(default=None, title='下限', gte=0)
    lte: Optional[int] = Field(default=None, title='上限', gte=0)


def normalize(text) -> Age:
    text = text.strip()
    nums = list(RE_PURE_DIGITS.findall(text))
    nums = [int(n) for n in nums]

    if len(nums) == 0:
        low, high = None, None
    elif len(nums) == 1:
        if "以上" in text or "大于" in text or "高于" in text or "下限" in text:
            low, high = nums[0], None
        elif "以下" in text or "小于" in text or "低于" in text or "上限" in text:
            low, high = None, nums[0]
        else:
            low, high = nums[0], nums[0]
    else:
        low, high = min(nums), max(nums)
    return Age(gte=low, lte=high)

if __name__ == '__main__':
    text = "大于22岁"
    temp = normalize(text)
    print(temp)
