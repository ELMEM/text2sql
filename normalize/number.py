import re
from typing import *

from pydantic import BaseModel, Field

RE_PURE_DIGITS = re.compile(r'\d+', re.U)


def normalize(text) -> dict:
    text = text.strip()
    nums = list(RE_PURE_DIGITS.findall(text))
    nums = [int(n) for n in nums]

    low = None
    high = None
    value = None

    if len(nums) == 0:
        pass

    elif len(nums) == 1:
        if "以上" in text or "多于" in text or "高于" in text or "下限" in text:
            low, high = nums[0], None
        elif "以下" in text or "少于" in text or "低于" in text or "上限" in text:
            low, high = None, nums[0]
        else:
            value = nums[0]
    else:
        low, high = min(nums), max(nums)

    if low is not None and high is not None:
        return {'gte': low, 'lte': high}
    elif value is not None:
        return {'value': value}
    elif low is not None:
        return {'gte': low}
    elif high is not None:
        return {'lte': high}
    return {}


if __name__ == "__main__":
    text = "60人"
    print(normalize(text))
