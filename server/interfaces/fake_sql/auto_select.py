import os
import sys

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from typing import Optional, List
from pydantic import BaseModel, Field
from lib import logs
from server.interfaces.base import app
from server.definitions.suggestions import LastChoice
from core.relation_extraction import extract_relations
from core.complete_sql import get_sql
from server.interfaces.suggestions.suggestions import suggestions, SuggestionInput


class SqlText(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    sql: Optional[str] = Field(description='生成的 fake sql (For 王永和 处理)')
    zh_sql: Optional[str] = Field(description='sql 的中文版')


class TestInput(BaseModel):
    inputs: List[str] = Field(["上海", "北京", "java工程师", "薪资"], description="输入的文本列表")
    domain: Optional[dict] = Field(description='限制的域; example, 若在某职位下，则传 {"JobOpenId" = "xxx"}')


@app.post('/v1/sql/auto_select',
          name="v1 sql auto select",
          response_model=SqlText,
          description="根据用户选择的输入结果，整合成 王永和 所需的 fake sql")
def sql_test(_input: TestInput):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    texts = _input.inputs
    domain = _input.domain

    full_text = ''
    history = []

    print('\n---------------- prediction ---------------------')
    for text in texts:
        full_text += f' {text}'
        ret_suggestion = suggestions(SuggestionInput(
            text=text,
            full_text=full_text.strip(),
            suggestion_history=history,
        ))
        print(ret_suggestion)

        history += list(map(lambda x: LastChoice(id=x.id, text=x.text, data=x.data[:1]), ret_suggestion['data']))

    # 抽取关系
    relations = extract_relations(history)

    print('\n--------------- relations -------------------')
    for r in relations:
        print(r)

    # 根据 history 和 关系 生产 sql
    sql = get_sql(history, relations, domain=domain)

    return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 1, **sql})


if __name__ == '__main__':
    # 测试代码

    ret = sql_test(TestInput(inputs=['北京', '上海', 'java工程师', '薪资', '>', '2w']))

    print('\n-----------------------------------------------')
    print(ret['sql'])
    print(ret['zh_sql'])
