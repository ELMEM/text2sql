import enum
from typing import *

from pydantic import BaseModel, Field

from normalize.utils.clean import clean_whitespace
from normalize.utils.clean import convert_ch_symbols_to_en


class DegreeName(enum.Enum):
    PRIMARY = '小学'
    JUNIOR_HIGH = '初中'
    HIGH = '高中'
    SECONDARY = '中专'
    COLLEGE = '大专'
    SPECIALIST = '专科'
    JUNIOR_COLLEGE = '专升本'
    BACHELOR = '本科'
    ONJOB_MASTER = '在职研究生'
    MASTER = '硕士'
    SPECIAL_MASTER = '专业学位硕士'
    ACADEMIC_MASTER = '学术型硕士'
    ONJOB_DOCTOR = '在职博士生'
    DOCTOR = '博士'
    SPECIAL_DOCTOR = '专业学位博士'
    ACADEMIC_DOCTOR = '学术型博士'
    POSTDOCTORAL = '博士后'
    MBA = 'MBA'
    EMBA = 'EMBA'


class Degree(BaseModel):
    name: str = Field(default=..., title='学历')
    rank: Optional[int] = Field(default=None, title='学历rank，越大学历越高')


class DegreeRange(BaseModel):
    gte: Optional[str] = Field(default=None, title='学历下限')
    lte: Optional[str] = Field(default=None, title='学历上限')


degree_to_score = {
    DegreeName.PRIMARY: -4,
    DegreeName.JUNIOR_HIGH: -2,
    DegreeName.HIGH: 0,
    DegreeName.SECONDARY: -1,
    DegreeName.COLLEGE: 8,
    DegreeName.SPECIALIST: 8,
    DegreeName.JUNIOR_COLLEGE: 10,
    DegreeName.BACHELOR: 16,
    DegreeName.ONJOB_MASTER: 20,
    DegreeName.MASTER: 24,
    DegreeName.SPECIAL_MASTER: 24,
    DegreeName.ACADEMIC_MASTER: 28,
    DegreeName.ONJOB_DOCTOR: 30,
    DegreeName.DOCTOR: 32,
    DegreeName.SPECIAL_DOCTOR: 32,
    DegreeName.ACADEMIC_DOCTOR: 36,
    DegreeName.POSTDOCTORAL: 40,
    DegreeName.MBA: 29,
    DegreeName.EMBA: 30
}

degree_to_keywords = [(DegreeName.PRIMARY, ['小学']),
                      (DegreeName.JUNIOR_HIGH, ['初中']),
                      (DegreeName.HIGH, ['高中']),
                      (DegreeName.SECONDARY, ['中专']),
                      (DegreeName.COLLEGE, ['大专']),
                      (DegreeName.SPECIALIST, ['专科']),
                      (DegreeName.JUNIOR_COLLEGE, ['专升本', '成人本科', '成人学士']),
                      (DegreeName.BACHELOR, ['本科', '学士', '大学']),
                      (DegreeName.ONJOB_MASTER, ['在职研究生', '在职硕士', '在职工程硕士']),
                      (DegreeName.MASTER, ['硕士', '研究生']),
                      (DegreeName.SPECIAL_MASTER, ['专业学位硕士', '专硕', '专业硕士', '专业型硕士']),
                      (DegreeName.ACADEMIC_MASTER, ['学术型硕士']),
                      (DegreeName.ONJOB_DOCTOR, ['在职博士']),
                      (DegreeName.DOCTOR, ['博士']),
                      (DegreeName.SPECIAL_DOCTOR, ['专业学位博士', '专业型博士']),
                      (DegreeName.ACADEMIC_DOCTOR, ['学术型博士']),
                      (DegreeName.POSTDOCTORAL, ['博士后']),
                      (DegreeName.MBA, ['mba']),
                      (DegreeName.EMBA, ['emba']),
                      ][::-1]

mapper = {
    '不限': -4,
    '初中': -2,
    '中专': -1,
    '高中': 0,
    '专科': 8,
    '大专': 8,
    '统招': 16,
    '本科': 16,
    '大学': 16,
    '硕士': 24,
    '专业学位硕士': 24,
    '学术型硕士': 28,
    'mba': 29,
    'emba': 30,
    '博士': 32,
    '专业学位博士': 32,
    '学术型博士': 36,
    '博士后': 40,
}

symbol_split_deg_range_most_possible = [
    "~", ",", "-", ".", "至", "到", "下限", "|", "/", "&", "#", "以上", "以下", "下限"
]


def normalize_value(deg_str: str) -> str:
    """
    分析学历字段，返回Degree，Degree.rank越大学历越高
    如果未解析出学历，返回None
    :param deg_str: 任意学历字符串
    :return: Optional[Degree]
    """
    cleaned_deg_str = clean_whitespace(deg_str).lower()
    for degree_name, keys in degree_to_keywords:
        for k in keys:
            if k in cleaned_deg_str:
                return degree_name.value
                # return Degree(name=degree_name.value, rank=degree_to_score[degree_name])
    return ''


def normalize(deg_range_str: str) -> dict:
    deg_range_str_converted = convert_ch_symbols_to_en(deg_range_str)
    if not deg_range_str_converted:
        return {}
    for possible_symbol in symbol_split_deg_range_most_possible:
        deg_range_str_converted_split = deg_range_str_converted.split(possible_symbol)
        if len(deg_range_str_converted_split) >= 2:
            if "以上" in deg_range_str_converted or "大于" in deg_range_str_converted or "高于" in deg_range_str_converted or \
                    "下限" in deg_range_str_converted:
                degree_lower_limit = normalize_value(deg_range_str_converted_split[0])
                return {'gte': degree_lower_limit}
            elif "以下" in deg_range_str_converted or "小于" in deg_range_str_converted or "低于" in deg_range_str_converted or \
                    "上限" in deg_range_str_converted:
                degree_upper_limit = normalize_value(deg_range_str_converted_split[0])
                return {'lte': degree_upper_limit}
            else:
                g, l = sorted(list(map(normalize_value, deg_range_str_converted_split)), key=lambda x: x.rank)
                return {'gte': g, 'lte': l}
    normalized_result = normalize_value(deg_range_str)
    if not normalized_result:
        return {}
    return {'value': normalized_result}


if __name__ == '__main__':
    print((normalize("本科")))
