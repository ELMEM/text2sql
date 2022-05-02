from pydantic import BaseModel, Field
from server.interfaces.base import app
from server.definitions.common import Response


class ColumnInput(BaseModel):
    type: str = Field('values', description='type = [ "values", "descriptions" ]')
    column: str = Field(description='若 type == "values", 则 column 为 sql 中的 column name; '
                                    '否则，column in [ column_desc, aggregation_column_desc, '
                                    'comparison_op_desc, condition_op_desc, group_by_trigger_desc ]')


@app.post('/v1/data/delete',
          name="v1 data delete",
          response_model=Response,
          description="注入数据，以用于预想输入的数据 value 提示")
def data_delete(_input: ColumnInput):
    from lib.milvus import o_milvus

    column = _input.column
    _type = _input.type.lower()

    # 检查参数
    if _type not in o_milvus.NAMES:
        return {'ret': 0, 'msg': f'type 只支持 {o_milvus.NAMES}'}

    if _type == o_milvus.DESC_NAME and column and column not in ['*', 'column_desc', 'aggregation_column_desc',
                                                                 'comparison_op_desc', 'condition_op_desc',
                                                                 'group_by_trigger_desc']:
        return {'ret': 0, 'msg': '当 type 为 descriptions 时, column 只支持 [ column_desc, aggregation_column_desc, '
                                 'comparison_op_desc, condition_op_desc, group_by_trigger_desc ]'}

    if column == '*':
        for collection_name in o_milvus.NAMES:
            o_milvus.recreate_collection(collection_name)

    elif _type == o_milvus.DESC_NAME:
        if column and column not in ['', '*']:
            o_milvus.drop_partition(o_milvus.DESC_NAME, column)
        else:
            o_milvus.recreate_collection(_type)

    elif _type == o_milvus.VALUE_NAME:
        if column and column not in ['', '*']:
            o_milvus.drop_partition(o_milvus.value_collection, column)
        else:
            o_milvus.recreate_collection(_type)

    else:
        o_milvus.recreate_collection(_type)

    return {'ret': 1}


if __name__ == '__main__':
    # 测试代码
    ret = data_delete(ColumnInput(
        column='test',
        type='values',
    ))
    print(ret)
