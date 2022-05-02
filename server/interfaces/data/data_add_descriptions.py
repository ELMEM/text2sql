from typing import List
from pydantic import BaseModel, Field
from server.interfaces.base import app
from server.definitions.common import Response
from core.encode import encode
from lib import logs
from lib.preprocess import preprocess


class DescInput(BaseModel):
    field: str = Field(description='column name 或 comparison op 或 condition op 或 "group_by_trigger"')
    type: str = Field(
        description='数据的类型; type in [ column_desc, aggregation_column_desc, '
                    'comparison_op_desc, condition_op_desc, group_by_trigger_desc ]')
    data: List[str] = Field(description='插入的数据；支持批量')


@app.post('/v1/data/add/descriptions',
          name="v1 data add descriptions",
          response_model=Response,
          description="注入描述数据到 milvus，以用于进行向量匹配")
def data_add_descriptions(_input: DescInput):
    from lib.milvus import o_milvus, filter_duplicate_texts

    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    field = _input.field
    desc_type = _input.type.lower()
    data = _input.data

    if desc_type not in ['column_desc', 'aggregation_column_desc', 'time_column_desc', 'keyword',
                         'comparison_op_desc', 'condition_op_desc', 'count_column_desc', 'agg_fn', 'group_fn']:
        return logs.ret(log_id, logs.fn_name(), 'POST', {
            'ret': 0,
            'msg': 'type 只支持 [ column_desc, aggregation_column_desc, time_column_desc, '
                   'comparison_op_desc, condition_op_desc, count_column_desc, agg_fn, group_fn]'
        })

    # 转换所有数据到字符串
    texts = list(map(preprocess, data))

    # 关联信息
    info = list(map(lambda x: {'text': x, 'field': field, 'type': desc_type}, texts))

    # 过滤重复数据
    partition = desc_type
    filtered_texts, filtered_info, indices = filter_duplicate_texts(o_milvus.DESC_NAME, texts, info,
                                                                    partition=partition)

    # encode 到 vector
    filtered_embeddings = encode(filtered_texts)

    # 插入数据
    ret, count = o_milvus.insert(o_milvus.DESC_NAME, filtered_texts, filtered_embeddings, filtered_info, partition)

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': ret,
        'msg': f'insert descriptions (field: {field}, desc_type: {desc_type}): {count}/{len(data)}'
    })


if __name__ == '__main__':
    # 测试代码
    data_add_descriptions(DescInput(
        field='test',
        type='column_desc',
        data=['你好']
    ))
