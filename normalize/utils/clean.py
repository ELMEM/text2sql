import re

RE_HYPHENS_IN_RANGE = re.compile(r'([-‐－~～]{3,})', re.U)
RE_WHITESPACE = re.compile(r'(\s+)', re.U)
ch_symbol_map_en = {
    "～": "~",
    "：": ":",
    "，": ",",
    "。": ".",
    "（": "(",
    "）": ")",
    "——": "_",
    "！": "!",
    "？": "?",
    "【": "[",
    "】": "]",
    "「": "{",
    "」": "}",
    "—": "-"
}


def clean_whitespace(s):
    return RE_WHITESPACE.sub('', s)


def compress_hyphens_in_range(s):
    return RE_HYPHENS_IN_RANGE.sub('---', s)


def convert_ch_symbols_to_en(s):
    result = s
    for cn, en in ch_symbol_map_en.items():
        result = result.replace(cn, en)
    return result
