import re
import copy
import time
import opencc
import unicodedata
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Yuque:
    DRIVER_PATH = r'/usr/local/bin/chromedriver'

    # 定义 雨雀 网页中会被用来作为识别 字段、类型、描述 的字符串
    NAME_FIELD = ['字段', '变量名', '变量', '属性', '参数', '名称', 'key', 'keys', 'fields', 'field']
    NAME_TYPE = ['类型', 'type']
    NAME_DESC = ['描述', '含义', '释义', '说明', 'description']

    # 定义常用的正则
    _reg_last_word = re.compile(r'[A-Z][a-z]+$')  # 匹配 camel 字段名的最后的单词
    _reg_num = re.compile(r'^\d+(\.\d+)?\s+')  # 匹配开头的序号
    _reg_en = re.compile(r'[a-zA-Z_0-9 ]+')  # 匹配 英语字符串
    _reg_all_en = re.compile(r'^[a-zA-Z0-9_\-]+$')  # 匹配 必须是全部英文
    _reg_special = re.compile(r'[^a-zA-Z_\-0-9()\[\]. \u3400-\u9FFF]')  # 匹配特殊字符串

    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')  # 解决DevToolsActivePort文件不存在的报错
        chrome_options.add_argument('window-size=1920x3000')  # 指定浏览器分辨率
        chrome_options.add_argument('--disable-gpu')  # 谷歌文档提到需要加上这个属性来规避bug
        chrome_options.add_argument('--hide-scrollbars')  # 隐藏滚动条, 应对一些特殊页面
        chrome_options.add_argument('blink-settings=imagesEnabled=false')  # 不加载图片, 提升速度
        chrome_options.add_argument('--headless')  # 浏览器不提供可视化页面. linux下如果系统不支持可视化不加这条会启动失败

        self.driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=self.DRIVER_PATH)

    def __del__(self):
        self.driver.close()

    @staticmethod
    def unicode_to_ascii(s):
        """ unicode 转 ascii """
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

    @staticmethod
    def full_2_half(string):
        """ 全角转半角 """
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

    @staticmethod
    def complex_2_simply(string):
        """ 繁体转简体 """
        cc = opencc.OpenCC('t2s')
        return cc.convert(string)

    @staticmethod
    def _replace_symbol(string):
        """ 替换中文符号为英文符号，因为字典中的数据用的是英文符号 """
        return string.replace('（', '(').replace('）', ')').replace('【', '(').replace('】', ')').strip()

    @staticmethod
    def _preprocess(string):
        """ 预处理字符串，转 ascill，转半角，转简体，替换特殊符号 """
        string = Yuque.unicode_to_ascii(string.strip())
        string = Yuque.full_2_half(string)
        string = Yuque.complex_2_simply(string)
        string = Yuque._replace_symbol(string)
        return string

    @staticmethod
    def _extract_tables(body):
        """
        提取 表格 以及 表格的标题
        :returns:
            tables = [
                {'title': 'xxx', 'table': [ ['a', 'b', 'c'], [1, 2, 'aa'], ... ]},
                ...
            ]
        """
        tables = []

        # 获取 表格 元素
        o_tables = body.find_elements(By.CSS_SELECTOR, '.ne-table')

        # 遍历所有表格
        for table_i, o_table in enumerate(o_tables):
            one_table = []

            # 找标题；首先寻找最近的上方的标题，若不是标题，则继续往上找
            near_i = 1
            nearest_head = o_table.find_element(By.XPATH, f'../../../../preceding-sibling::*[{near_i}]')
            while nearest_head.tag_name not in ['ne-h2', 'ne-h3', 'ne-h1'] and near_i <= 2:
                near_i += 1
                try:
                    nearest_head = o_table.find_element(By.XPATH, f'../../../../preceding-sibling::*[{near_i}]')
                except:
                    nearest_head = o_table.find_element(By.XPATH, f'../../../../preceding-sibling::*[{near_i - 1}]')
                    break

                if nearest_head.tag_name in ['ne-table-hole']:
                    nearest_head = o_table.find_element(By.XPATH, f'../../../../preceding-sibling::*[{near_i - 1}]')
                    break

            # 检查找出的标题是否及格
            if nearest_head.tag_name not in ['ne-h2', 'ne-h3', 'ne-h1', 'ne-p']:
                nearest_head = o_table.find_element(By.XPATH, f'../../../../preceding-sibling::*[1]')

            # 获取标题文本
            title = nearest_head.text.strip()

            # 预处理 标题文本
            title = Yuque._reg_num.sub('', Yuque._preprocess(title))
            if Yuque._reg_en.search(title):  # 若含有英语
                title = Yuque._reg_en.findall(title)[0]  # 只取 英语部分 作为 标题

            # 遍历 tr 元素
            o_trs = o_table.find_elements(By.TAG_NAME, 'tr')
            for tr_i, o_tr in enumerate(o_trs):
                one_tr = []

                # 遍历 td 元素
                o_tds = o_tr.find_elements(By.TAG_NAME, 'td')
                for o_td in o_tds:
                    # 预处理 td text 并保存
                    td_text = Yuque._reg_special.sub('', Yuque._preprocess(o_td.text)).strip()
                    one_tr.append(td_text)

                one_table.append(one_tr)

            tables.append({'title': title, 'table': one_table})

        return tables

    @staticmethod
    def _match_from_list(string, list_string):
        """ 匹配 list_string 中的字符到 string 里 """
        for s in list_string:
            if s in string:
                return True
        return False

    @staticmethod
    def _convert_table_2_dict(table_v):
        """ 根据表头，将 table 转换成 dict 结构 """
        table = table_v['table']
        header = table[0]
        table = table[1:]

        # 记录 字段、类型、描述 所在的列的位置
        field_index = type_index = desc_index = -1

        # 遍历 表头，检查 字段、类型、描述 分别位于哪一列
        for i, val in enumerate(header):
            val = val.lower()

            if field_index == -1 and val in Yuque.NAME_FIELD:
                field_index = i

            elif type_index == -1 and val in Yuque.NAME_TYPE:
                type_index = i

            elif field_index == -1 and Yuque._match_from_list(val, Yuque.NAME_FIELD):
                field_index = i

            elif type_index == -1 and Yuque._match_from_list(val, Yuque.NAME_TYPE):
                type_index = i

            elif desc_index == -1 and Yuque._match_from_list(val, Yuque.NAME_DESC):
                desc_index = i

        if field_index == -1 or desc_index == -1:
            return

        # 若没有找到 类型
        if type_index == -1:
            table_v['table'] = {val[field_index]: val[desc_index] for val in table}

        # 若 字段、类型、描述 都找到
        else:
            table_v['table'] = {val[field_index]: {'#type': val[type_index], '#desc': val[desc_index]} for val in table}

        return table_v

    @staticmethod
    def _plural(word):
        """ 单词 转 复数 """
        if not word:
            return word
        elif word[-1] == 'y':
            return word[:-1] + 'ies'
        elif word[-2:] == 'is':
            return word[:-2] + 'es'
        elif word[-1] in 'sx' or word[-2:] in ['sh', 'ch']:
            return word + 'es'
        elif word[-2:] == 'an':
            return word[:-2] + 'en'
        else:
            return word + 's'

    @staticmethod
    def _get_right_bracket(string, offset, left='[', right=']'):
        """ 获取 右边的括号 的位置 """
        _index = offset
        length = len(string)
        left_count = 0

        while _index < length:
            if string[_index] == left:
                left_count += 1
            elif string[_index] == right:
                left_count -= 1

            # 若找到对应的闭合的括号
            if left_count < 0:
                return _index

            _index += 1

        # 若没有闭合的括号
        return length

    @staticmethod
    def _remove_dulplicate_title(tables):
        """ 解决 table 的 标题重复 问题 """
        d_title = {}
        for table_i, table in enumerate(tables):
            title = table['title']
            if title not in d_title:
                d_title[title] = 0
            else:
                d_title[title] += 1
                tables[table_i]['title'] = f'{title} {d_title[title]}'
        return tables

    @staticmethod
    def _reconstruct_nested_schema(tables):
        """ 重构 schema 的 嵌套结构 """
        titles = list(map(lambda x: x['title'], tables))

        _keys = []
        _types = []

        # 获取 每个表格 的所有 key 和 type，用于 判断 任意两表格之间是否存在 嵌套关系
        for table_i, table in enumerate(tables):
            # 获取 表格 的 keys
            tmp_keys = list(table['table'].keys())
            # 对 key 预处理
            tmp_keys_lower = list(map(lambda x: x.lower().replace('_', ''), tmp_keys))

            # 保持 key 以及 对应的 原key 和 table 索引位置
            _keys += list(zip(tmp_keys_lower, tmp_keys, [table_i] * len(tmp_keys)))

            # 获取表格的 type
            tmp_types = []
            for x in table['table'].values():
                # type 可能会不存在表格里，若不存在
                if '#type' not in x:
                    break

                # 对 type 做预处理
                _, _type = Yuque._parse_type(x['#type'])
                tmp_types.append(_type.lower())

            # 若 获取 type 成功
            if tmp_types:
                # 保留 type 以及 对应对 原key 和 table 的索引位置
                _types += list(zip(tmp_types, tmp_keys, [table_i] * len(tmp_keys)))

        # 将上面的 keys 和 types 转换为 dict
        d_key_2_table_i_list = {}
        d_type_2_table_i_list = {}

        for _key, _origin_key, _table_i in _keys:
            if _key not in d_key_2_table_i_list:
                d_key_2_table_i_list[_key] = []
            d_key_2_table_i_list[_key].append([_table_i, _origin_key])

        for _type, _origin_key, _table_i in _types:
            if _type not in d_type_2_table_i_list:
                d_type_2_table_i_list[_type] = []
            d_type_2_table_i_list[_type].append([_table_i, _origin_key])

        # 记录哪些表格被合并了，用于 删除已合并表格 和 添加 #
        has_merge = []

        # 遍历标题
        for title_i, title in enumerate(titles):
            # 对 标题 作预处理
            _last_word = title_lower = title.lower()
            title_no_under = title_lower.replace('_', '')
            if Yuque._reg_last_word.search(title):
                _last_word = Yuque._reg_last_word.search(title).group()

            # 获取 title 的 lower plural 和 去下划线 的组合处理后的形式
            _last_word_plural = Yuque._plural(_last_word)
            title_plural = title_lower[:-len(_last_word)] + _last_word_plural.lower()
            title_plural_no_under = title_plural.replace('_', '')

            # 获取 当前 table，用于 被合并，若存在 嵌套关系
            cur_table = tables[title_i]['table']

            # 有可能多个 表格 都会包含 该 cur_table
            parent_tables = []

            # 根据 预处理后的各种形式的 title 和 key type 的字典进行判断，找出 对应关系
            if title_lower in d_key_2_table_i_list:
                parent_tables = d_key_2_table_i_list[title_lower]

            elif title_lower in d_type_2_table_i_list:
                parent_tables = d_type_2_table_i_list[title_lower]

            elif title_plural in d_key_2_table_i_list:
                parent_tables = d_key_2_table_i_list[title_plural]

            elif title_no_under in d_key_2_table_i_list:
                parent_tables = d_key_2_table_i_list[title_no_under]

            elif title_no_under in d_type_2_table_i_list:
                parent_tables = d_type_2_table_i_list[title_no_under]

            elif title_plural_no_under in d_key_2_table_i_list:
                parent_tables = d_key_2_table_i_list[title_plural_no_under]

            # 根据对应关系，合并表格
            for _table_i, _origin_key in parent_tables:
                # 记录 该key的原始值 (一般是实体定义)，用于后面生成 # 的定义
                _origin_val = tables[_table_i]['table'][_origin_key]

                # 若只有一个 table 嵌套到这个 key
                if '#desc' in _origin_val:
                    # 合并
                    tables[_table_i]['table'][_origin_key] = cur_table
                    # 保留 合并记录
                    has_merge.append([title_i, _table_i, _origin_key, _origin_val])

                # 若之前已经有 table 合并到这个 key 上
                else:
                    # 合并
                    tables[_table_i]['table'][_origin_key] = {**_origin_val, **cur_table}
                    # 保留 合并记录
                    find_same_record = list(filter(lambda x: x[1] == _table_i and x[2] == _origin_key, has_merge))
                    real_origin_val = find_same_record[0][-1]
                    has_merge.append([title_i, _table_i, _origin_key, real_origin_val])

        # 根据 合并记录，生成 # (实体) 的定义
        for be_merged_i, _table_i, _origin_key, _origin_val in has_merge:
            tmp_table = tables[_table_i]['table'][_origin_key]
            tmp_table['#'] = _origin_val
            tables[_table_i]['table'][_origin_key] = tmp_table

        # 因为上面有可能 一个表格被多次合并到不同表格，所以 （指针的关系）实体定义会出错；以下是用于修正的
        for be_merged_i, _table_i, _origin_key, _origin_val in has_merge:
            tmp_table = copy.deepcopy(tables[_table_i]['table'][_origin_key])
            tmp_table['#'] = _origin_val
            tables[_table_i]['table'][_origin_key] = tmp_table

        # 避免下面去除被合并表格时受到影响，去除指针
        for table_i, table in enumerate(tables):
            table['table'] = copy.deepcopy(table['table'])

        # 获取 被合并的表格 的索引，并倒序
        be_merged_indices = list(set(list(map(lambda x: x[0], has_merge))))
        be_merged_indices.sort(reverse=True)

        # 删除已被合并的表格
        for be_merged_i in be_merged_indices:
            del tables[be_merged_i]

        # 若只有一个表格
        # if len(tables) == 1:
        #     final_table = tables[0]['table']
        #     tables = [{'title': '', 'table': final_table}]
        # else:
        #     final_table = {val['title']: val['table'] for val in tables}
        # tables = [{'title': '', 'table': final_table}]

        return tables

    @staticmethod
    def _parse_type(string):
        is_array = True
        if '[]' in string:
            return is_array, string.replace('[]', '')

        elif 'list[' in string.lower():
            l_start_index = string.lower().index('list[') + len('list[')
            return is_array, string[l_start_index: Yuque._get_right_bracket(string, l_start_index)]

        elif 'array[' in string.lower():
            l_start_index = string.lower().index('array[') + len('array[')
            return is_array, string[l_start_index: Yuque._get_right_bracket(string, l_start_index)]

        elif Yuque._reg_en.search(string):
            is_array = False
            return is_array, Yuque._reg_en.findall(string)[0].replace(' ', '_')

        else:
            is_array = False
            return is_array, string

    @staticmethod
    def _process_list_type(tables):
        """ 处理 list 类型 """

        # 遍历所有表格
        for table_i, table in enumerate(tables):
            table = table['table']

            stack = [(table, '', None)]
            while stack:
                tmp_table, parent_key, parent = stack.pop()  # parent[parent_key] == tmp_table

                # 若为 dict 类型
                if isinstance(tmp_table, dict):
                    if '#' in tmp_table and '#type' in tmp_table['#']:
                        is_array, _type = Yuque._parse_type(tmp_table['#']['#type'])
                        if is_array:
                            tmp_table['#']['#type'] = _type
                            if isinstance(parent, dict):
                                parent[parent_key] = [tmp_table]

                    if '#type' in tmp_table:
                        is_array, _type = Yuque._parse_type(tmp_table['#type'])
                        if is_array:
                            tmp_table['#type'] = _type
                            if isinstance(parent, dict):
                                parent[parent_key] = [tmp_table]

                    else:
                        for k, v in tmp_table.items():
                            if k == '#' or (not isinstance(v, dict) and not isinstance(v, list)):
                                continue
                            stack.append((v, k, tmp_table))

                elif isinstance(tmp_table, list):
                    for i, val in enumerate(tmp_table):
                        stack.append((val, i, tmp_table))

        return tables

    def extract_schema(self, _url):
        """ 根据 雨雀的 URL 提取 schemas """
        self.driver.get(_url)

        # 获取 body element
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.ne-viewer-body'))
        )
        body = self.driver.find_element(By.CSS_SELECTOR, '.ne-viewer-body')

        # 抽取表格
        tables = self._extract_tables(body)

        # 转换表格格式到 dict
        tables = list(map(self._convert_table_2_dict, tables))
        tables = list(filter(lambda x: x, tables))

        if not tables:
            return []

        # 解决 table 的 标题重复 问题
        tables = self._remove_dulplicate_title(tables)

        # 重构带有嵌套关系的 schemas
        tables = self._reconstruct_nested_schema(tables)

        # 处理 list 类型
        tables = self._process_list_type(tables)

        # 展示结果
        for i, val in enumerate(tables):
            print('\n------------------------------------')
            print(f'table_{i}: {val["title"]}')
            for k, v in val['table'].items():
                if isinstance(v, dict):
                    print(f'\t{k}: ')
                    for kk, vv in v.items():
                        print(f'\t\t{kk}: {vv}')
                else:
                    print(f'\t{k}: {v}')

        return tables


# url = r'https://nadileaf.github.io/mesoor-schema-types/index.html'
url = r'https://www.yuque.com/docs/share/3e32f586-f276-48f0-8592-da63982c927f'
# url = r'https://www.yuque.com/gtmfqm/igbw47/913211449'
# url = r'https://www.yuque.com/gtmfqm/igbw47/438534145'
# url = r'https://www.yuque.com/gtmfqm/igbw47/291012617'
# url = r'https://www.yuque.com/gtmfqm/igbw47/ognuyk'
# url = r'https://www.yuque.com/gtmfqm/igbw47/hibcyz'
# url = r'https://www.yuque.com/gtmfqm/igbw47/sb19xp'
# url = r'https://www.yuque.com/gtmfqm/igbw47/rlezc5'
# url = r'https://www.yuque.com/gtmfqm/igbw47/stlws3'
# url = r'https://www.yuque.com/gtmfqm/igbw47/hqwog0'
# url = r'https://www.yuque.com/gtmfqm/igbw47/800358494'
# url = r'https://www.yuque.com/gtmfqm/igbw47/800030815'
# url = r'https://www.yuque.com/gtmfqm/igbw47/mg41oy'
# url = r'https://www.yuque.com/gtmfqm/igbw47/fe4tfs'
# url = r'https://www.yuque.com/gtmfqm/igbw47/784302224'
# url = r'https://www.yuque.com/gtmfqm/igbw47/842727454'
# url = r'https://www.yuque.com/gtmfqm/igbw47/126845039'
# url = r'https://www.yuque.com/gtmfqm/igbw47/784171095'
# url = r'https://www.yuque.com/gtmfqm/igbw47/126976208'
# url = r'https://www.yuque.com/gtmfqm/igbw47/783942124'

o_yuque = Yuque()
tables = o_yuque.extract_schema(url)

for val in tables:
    print('\n---------------------------------------------------')
    print(f'## title ##: {val["title"]}')
    for k, v in val['table'].items():
        print(f'{k}: {v}')

# import os
# import json
#
# tmp_dir = r'/Users/samuellin/Documents/GitHub/table_column_match/tmp'
# for val in tables:
#     with open(os.path.join(tmp_dir, f'{val["title"].json}'), 'w') as f:
#         f.write(json.dumps(val['table'], ensure_ascii=False, indent=2))
