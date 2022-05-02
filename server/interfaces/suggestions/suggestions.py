import os
import sys
import time
from typing import List

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from server.interfaces.base import app
from server.definitions.suggestions import SuggestionResponse, SuggestionInput, Prediction, Choice
from core import seg
from core.type_classification import get_type, get_type_for_number
from core.processor import filter_columns, uid, keywords, to_zh
from lib import logs


@app.post('/v1/suggestions',
          name="v1 suggestions",
          response_model=SuggestionResponse,
          description="预想输入 (正在输入时)，返回相近的value或column的列表(top k)")
def suggestions(_input: SuggestionInput):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    text = _input.text.strip()
    full_text = _input.full_text
    suggestion_history = _input.suggestion_history
    top_k = _input.top_k
    cur_index = _input.cur_index

    # 获取全部 columns
    columns: List[str] = filter_columns(suggestion_history)

    # 若输入为空时，返回所有 column 让用户选择
    if not text:
        prediction = Prediction(id=uid('', suggestion_history), text='', data=list(map(
            lambda x: Choice(text=to_zh(x), type='column_desc', value=x, zh_value=to_zh(x), score=1.0),
            columns
        )))
        return logs.ret(log_id, logs.fn_name(), 'POST', {
            'ret': 1,
            'data': [prediction]
        })

    # 若输入全是数字
    prediction = get_type_for_number(text, suggestion_history, top_k, cur_index)
    if prediction is not None:
        return logs.ret(log_id, logs.fn_name(), 'POST', {
            'ret': 1,
            'data': [prediction]
        })

    # 若输入是关键字
    if text in keywords:
        prediction = Prediction(id=uid(text, suggestion_history), text=text, data=[
            Choice(text=text, type='keyword', value=text, score=1.0)])
        return logs.ret(log_id, logs.fn_name(), 'POST', {
            'ret': 1,
            'data': [prediction]
        })

    # 判断 text 是否 columns 中的一部分
    tmp_text = text.lower().replace(' ', '')
    in_columns = list(filter(lambda x: tmp_text in x.lower().replace(' ', ''), columns))
    in_columns.sort(key=len)

    s_time = time.time()
    grams = seg.n_gram(text, num_gram=3)
    e_1_time = time.time()
    valid_grams = seg.choose_valid_gram(grams)
    e_2_time = time.time()

    logs.add(log_id, f'POST {logs.fn_name()}', f'seg n gram use time: {e_1_time - s_time:.4f}s ')
    logs.add(log_id, f'POST {logs.fn_name()}', f'choose valid gram use time: {e_2_time - e_1_time:.4f}s ')

    if not valid_grams:
        # 没有匹配到任何东西
        prediction = Prediction(
            id=uid(text, suggestion_history),
            text=text,
            data=list(map(lambda x: Choice(
                text=to_zh(x),
                type='column_desc',
                value=x,
                score=len(text) / len(x),
                zh_value=to_zh(x)
            ), in_columns))
        ) if in_columns else None

        predictions = [prediction]

    elif len(valid_grams) == 1:
        text = valid_grams[0].text

        start = time.time()
        prediction = get_type(valid_grams[0] if valid_grams[0].data else text, suggestion_history, top_k, cur_index)
        end = time.time()
        logs.add(log_id, f'POST {logs.fn_name()}', f'get type use time: {end - start:.4f}s ')

        # 若匹配的分数不高，且输入 text 是 columns 的一部分
        if in_columns and (not prediction.data or prediction.data[0].score <= 0.7):
            prediction.data += list(map(
                lambda x: Choice(text=to_zh(x), type=x, value=x, score=len(text) / len(x)),
                in_columns
            ))[:max(3, top_k - len(prediction.data))]

        predictions = [prediction]

    else:
        start = time.time()
        predictions = seg.valid_gram_predict(valid_grams, suggestion_history, top_k)
        end = time.time()
        logs.add(log_id, f'POST {logs.fn_name()}', f'valid gram predict use time: {end - start:.4f}s ')

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': 1,
        'data': predictions
    })


if __name__ == '__main__':
    # 测试代码
    from server.definitions.suggestions import LastChoice

    history = [
        # LastChoice(id='1', text='工作年限要求',
        #            data=[Choice(text='工作年限要求', type='column_desc', value='ResumeWorkYearNormalizedGte', score=1.0)]),
        # LastChoice(id='2', text='<', data=[Choice(text='<', type='comparison_op_desc', value='<', score=1.0)])

        # LastChoice(id='1', text='职位', data=[Choice(text='职位', type='column_desc', value='JobJobName', score=1.0)]),
    ]

    test_text = '100个' if len(sys.argv) <= 1 else sys.argv[1]
    ret = suggestions(SuggestionInput(text=test_text, full_text='', suggestion_history=history))

    print('\n##########################################')
    for _prediction in ret['data']:
        print('\n-------------------------')
        print(_prediction)
        for v in _prediction.data:
            print(v)
