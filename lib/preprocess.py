import re
import chardet
import unicodedata

_reg_en = re.compile(r'^[ \w_\-]+$')
_reg_space = re.compile(r'\s+')
_reg_fuhao = re.compile(r'[^\u3400-\u9FFFa-zA-Z0-9]')
_reg_zh = re.compile(r'[\u4e00-\u9fff]')


def preprocess(value):
    """ 预处理任意 value 到字符串 """
    if isinstance(value, bytes):
        text = decode_2_utf8(value)
    elif not isinstance(value, str):
        text = f'{value}'
    else:
        text = value

    text = unicode_to_ascii(text)
    text = full_2_half(text)

    if _reg_en.search(text):
        text = tokenize_key(text)
    return text.strip().lower()


def decode_2_utf8(string):
    if not isinstance(string, bytes):
        return string

    try:
        return string.decode('utf-8')
    except:
        encoding = chardet.detect(string)['encoding']
        if encoding:
            try:
                return string.decode(encoding)
            except:
                pass
        return string


def unicode_to_ascii(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def full_2_half(string):
    ss = []
    for s in string:
        rstring = ""
        for uchar in s:
            inside_code = ord(uchar)
            # 全角空格直接转换
            if inside_code == 12288:
                inside_code = 32

            # 全角字符（除空格）根据关系转化
            elif 65281 <= inside_code <= 65374:
                inside_code -= 65248
            rstring += chr(inside_code)
        ss.append(rstring)
    return ''.join(ss)


def tokenize_key(string: str):
    upper_s = ord('A')
    upper_e = ord('Z')
    lower_s = ord('a')
    lower_e = ord('z')
    num_s = ord('0')
    num_e = ord('9')

    new_string = ''
    length = len(string)
    i = 0

    while i < length:
        c = string[i]
        ord_c = ord(c)

        if _reg_fuhao.search(c):
            # if ord_c < num_s or num_e < ord_c < upper_s or upper_e < ord_c < lower_s or lower_e < ord_c:
            new_string += ' '
            i += 1
            continue

        last_ord = ord(string[i - 1])
        if i > 0 and (lower_s <= last_ord <= lower_e or upper_s <= last_ord <= upper_e) and num_s <= ord_c <= num_e:
            new_string += ' '
            i += 1
            continue

        c = c.lower()
        if upper_s <= ord_c <= upper_e and i > 0 and (lower_s <= last_ord <= lower_e or num_s <= last_ord <= num_e):
            new_string += ' '
        new_string += c

        i += 1

    new_string = _reg_space.sub(' ', new_string).strip()
    return new_string


def format_suffix(suffix: str) -> str:
    if not suffix:
        return ''

    words = tokenize_key(suffix).split(' ')
    words = list(map(lambda x: f'{x[0].upper()}{x[1:]}', words))
    return ''.join(words)

