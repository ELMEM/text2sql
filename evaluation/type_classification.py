import os
import sys
import json

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from config.path import TEST_DATA_PATH
from server.definitions.suggestions import Prediction, Choice, LastChoice
from core.processor import is_normalizable
from server.interfaces.suggestions.suggestions import suggestions, SuggestionInput


def _load_json():
    with open(TEST_DATA_PATH, 'rb') as f:
        data = json.load(f)
    return data


def type_correct(_pred: Prediction, results: list, result_index):
    hits_ = []
    is_find = 9999
    if len(_pred) != len(results):
        return is_find
    for pred_index, result in enumerate(results):
        if len(result) == 4:
            if result_index != result[-1]:
                hits_.append(is_find)
                break
        result_type = result[0] if isinstance(result[0], list) else [result[0]]
        use_data = list(filter(lambda x: x.type in result_type, _pred[pred_index].data))
        if use_data:
            for _index, use_data_temp in enumerate(use_data):
                if use_data_temp.type == "value":
                    if not is_normalizable(use_data_temp.value):
                        if use_data_temp.value in result[2]:
                            hits_.append(_index)
                            break
                    else:
                        if use_data_temp.value in result[2] and use_data_temp.text == result[1]:
                            hits_.append(_index)
                            break
                else:
                    if use_data_temp.value in result[2]:
                        hits_.append(_index)
                        break
                if _index == len(use_data):
                    hits_.append(9999)
    return hits_


if __name__ == '__main__':
    record_temp = []
    pool_size = 30
    data = _load_json()
    MRR = 0
    hit_1 = 0
    hit_5 = 0
    hit_10 = 0
    num = 0
    record = []
    for i, tmp_data in enumerate(data):
        _temp_add = 0
        _temp_start = 0
        input_texts = tmp_data["input"]
        _result = tmp_data["output_type"]
        for _index, _text in enumerate(input_texts):
            _history = _result[:_index + _temp_add - 1] if _index > 0 else []
            _history = list(map(
                lambda x: LastChoice(id='', text=x[1], data=[
                    Choice(text=x[1], type=x[0] if isinstance(x[0], str) else x[0][0], value=x[2][0], score=1.)
                ]),
                _history
            ))
            _preds = suggestions(SuggestionInput(text=_text, suggestion_history=_history))['data'] if \
                suggestions(SuggestionInput(text=_text, suggestion_history=_history))['ret'] else []
            _temp_add = len(_preds)
            _temp_start += len(_preds)
            if len(_result[0]) == 3:
                _hits = type_correct(_preds, _result[_temp_start - _temp_add:_temp_start], _index)
            else:
                _result_temp = list(filter(lambda x: x[-1] == _index, _result))
                _hits = type_correct(_preds, _result_temp, _index)
            _hits = _hits if isinstance(_hits, list) else [_hits]
            for _hit in _hits:
                MRR += 1 / (_hit + 1)
                num += 1
                if _hit == 0:
                    hit_1 += 1
                if _hit < 5:
                    hit_5 += 1
                if _hit < 10:
                    hit_10 += 1
                if _hit > 10:
                    print(f"第{i}个数据的第{_index}词错误,预测为{_preds}")
    print("---------n-------------")
    print(f"hit_1: {hit_1 / num}")
    print(f"hit_5: {hit_5 / num}")
    print(f"hit_10: {hit_10 / num}")
    print(f"MRR: {MRR / num}")

