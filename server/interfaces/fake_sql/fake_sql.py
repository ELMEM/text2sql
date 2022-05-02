import os
import sys
import time

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from typing import Optional, List
from pydantic import BaseModel, Field
from server.interfaces.base import app
from server.definitions.suggestions import LastChoice, Choice
from core.relation_extraction import extract_relations
from core.complete_sql import get_sql
from lib import logs

example_history = [
    LastChoice(id='1', text='北京',
               data=[Choice(text='北京', type='value', value='JobLocationsNormalizedCity', score=1.0)]),
    LastChoice(id='3', text='java工程师', data=[Choice(text='java工程师', type='value', value='JobJobName', score=1.0)]),
    LastChoice(id='8', text='平均薪资',
               data=[Choice(text='平均薪资', type='aggregation_column_desc',
                            value='WorkExperienceSalaryRangeNormalizedGteAvg', score=1.0)]),
    LastChoice(id='9', text='大于', data=[Choice(text='大于', type='comparison_op_desc', value='>', score=1.0)]),
    LastChoice(id='10', text='2w', data=[Choice(text='2w', type='value', value='JobLowSalaryMonthlyAvg', score=1.0)])
]


class ThoughtSpotInput(BaseModel):
    full_text: str = Field('', description='完整的输入文本')
    suggestion_history: Optional[List[LastChoice]] = Field(example_history, description='已经匹配的结果 (结构化)')
    domain: Optional[dict] = Field(description='限制的域; example, 若在某职位下，则传 {"JobOpenId" = "xxx"}')


class SqlText(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    sql: Optional[str] = Field(description='生成的 fake sql (For 王永和 处理)')
    zh_sql: Optional[str] = Field(description='sql 的中文版')


@app.post('/v1/fake_sql',
          name="v1 fake sql",
          response_model=SqlText,
          description="根据用户选择的输入结果，整合成 王永和 所需的 fake sql")
def fake_sql(_input: ThoughtSpotInput):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    full_text = _input.full_text
    _suggestion_history = _input.suggestion_history
    _domain = _input.domain

    start = time.time()

    # 抽取关系
    relations = extract_relations(_suggestion_history)

    # 根据 history 和 关系 生产 sql
    sql = get_sql(_suggestion_history, relations, domain=_domain)

    # 记录使用时间
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}', f'use time: {time.time() - start:.4f}s ')

    return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 1, **sql})


if __name__ == '__main__':
    # 测试代码

    suggestion_history = [
        # LastChoice(id='1', text='北京', data=[Choice(text='北京', type='value', value='JobCity', score=1.0)]),
        # LastChoice(id='2', text='and', data=[Choice(text='and', type='condition_op_desc',value='and', score=1.0)]),
        # LastChoice(id='3', text='java工程师', data=[Choice(text='java工程师', type='value', value='JobName', score=1.0)]),
        # LastChoice(id='4', text='or', data=[Choice(text='or', type='condition_op_desc', value='or', score=1.0)]),
        # LastChoice(id='5', text='上海', data=[Choice(text='上海', type='value', value='JobCity', score=1.0)]),
        # LastChoice(id='6', text='and', data=[Choice(text='and', type='condition_op_desc', value='and', score=1.0)]),
        # LastChoice(id='7', text='ios工程师', data=[Choice(text='java工程师', type='value', value='JobName', score=1.0)]),
        # LastChoice(id='14', text='ios程序员', data=[Choice(text='ios程序员', type='value', value='JobName', score=1.0)]),
        # LastChoice(id='8', text='平均薪资', data=[
        #     Choice(text='平均薪资', type='aggregation_column_desc', value='ResumeSalaryRangeNormalizedGteAvg', score=1.0)]),
        # LastChoice(id='9', text='大于', data=[Choice(text='大于', type='comparison_op_desc', value='>', score=1.0)]),
        # LastChoice(id='10', text='2w', data=[
        #     Choice(text='2w', type='value', value='ResumeSalaryRangeNormalizedGteAvg', score=1.0)]),
        # LastChoice(id='14', text='or', data=[Choice(text='or', type='condition_op_desc', value='or', score=1.0)]),
        # LastChoice(id='11', text='小于', data=[Choice(text='小于', type='comparison_op_desc', value='<', score=1.0)]),
        # LastChoice(id='12', text='4w', data=[
        #     Choice(text='4w', type='value', value='ResumeSalaryRangeNormalizedGteAvg', score=1.0)]),
        # LastChoice(id='13', text='每月', data=[
        #     Choice(text='每月', type='column_desc', value='JobPublishedDateByMonth', score=1.0)]),
        # LastChoice(id='1', text='北京', data=[Choice(text='北京', type='value', value='JobCity', score=1.0)]),
        LastChoice(id='3', text='java工程师', data=[Choice(text='java工程师', type='value', value='JobName', score=1.0)]),
        LastChoice(id='8', text='平均薪资', data=[
            Choice(text='平均薪资', type='aggregation_column_desc', value='WorkExperienceSalaryRangeNormalizedGte', score=1.0)]),
        LastChoice(id='9', text='大于', data=[Choice(text='大于', type='comparison_op_desc', value='>', score=1.0)]),
        LastChoice(id='10', text='2w', data=[Choice(text='2w', type='value', value='WorkExperienceSalaryRangeNormalizedGte', score=1.0)])
        # LastChoice(id='0', text='工作地点', data=[
        #     Choice(text='工作地点', type='column_desc', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
        # LastChoice(id='1', text='不在',
        #            data=[Choice(text='不在', type='comparison_op_desc', value='!=', score=1.0, zh_value=None)]),
        # LastChoice(id='99', text='(', type='keyword',
        #            data=[Choice(text='(', type='keyword', value='(', score=1.0, zh_value=None)]),
        # LastChoice(id='2', text='北京', data=[
        #     Choice(text='北京', type='value', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
        # LastChoice(id='3', text='深圳',
        #            data=[Choice(text='深圳', type='value', value='JobLocationsNormalizedCity', score=1.0,
        #                         zh_value=None)]),
        # LastChoice(id='4', text='上海', data=[
        #     Choice(text='上海', type='value', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
        # LastChoice(id='999', text=')',
        #            data=[Choice(text=')', type='keyword', value=')', score=1.0, zh_value=None)])
    ]

    ret = fake_sql(ThoughtSpotInput(suggestion_history=suggestion_history, domain={'JobOpenId': 'xxx'}))

    print('\n-----------------------------------------------')
    print(ret['sql'])
    print(ret['zh_sql'])
