import copy
import time

import numpy as np
import jieba
from typing import List
import os
import sys

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(_cur_dir)[0])[0]
sys.path.append(_root_dir)
from core.type_classification import batch_get_type, get_type
from server.definitions.suggestions import Prediction, LastChoice
from lib import logs


def n_gram(text: str, num_gram: int = 3) -> List[dict]:
    """ 在返回 n-gram 的时候，可以把原 text 一并返回，方便确认是否需要切 """
    start = time.time()
    tokens = list(jieba.cut(text.strip(), cut_all=False))
    end_jieba = time.time()
    log_id = logs.uid()
    logs.add(f'{log_id}', f'POST {jieba.__name__}', f'payload: {text}'[:200], f'spendtime : {end_jieba - start}')
    length = len(tokens)

    _grams = [{'text': text, 'start': 0, 'end': length}]
    if length == 1:
        return _grams

    for n in range(min(num_gram, length)):
        for i in range(length - n):
            tmp_text = ''.join(tokens[i: i + n + 1])
            if tmp_text == text:
                continue

            _grams.append({
                'text': tmp_text,
                'start': i,
                'end': i + n + 1
            })
    end = time.time()
    log_id = logs.uid()
    logs.add(f'{log_id}', f'POST {logs.fn_name()}', f'payload: {text}'[:200], f'spendtime : {end - start}')
    return _grams


def choose_valid_gram(_grams: List[dict]) -> List[Prediction]:
    """
    grams: [[text1,[token1]],[text2,[token1]]]
    根据每个 gram 的分数进行排序和筛选
    :return:
        valid_grams: List[str] 按顺序返回筛选出来的 n-gram 或 完整 text
    """
    if len(_grams) == 1:
        return [Prediction(id='', text=_grams[0]['text'], data=[])]

    len_tokens = _grams[-1]['end']

    texts = list(map(lambda x: x['text'], _grams))

    start_ = time.time()
    predictions = batch_get_type(texts)
    end_ = time.time()
    logs.add('unknown', f'choose_valid_gram', f'batch get type : {end_ - start_:.4f}s ')

    for i, gram in enumerate(_grams):
        gram['prediction'] = predictions[i]

    # 先按 分数 排序，若 分数 相等，则按 text 长度排序
    _grams.sort(key=lambda x: (-x['prediction'].data[0].score, -len(x['text'])) if x['prediction'].data else (999, 999))

    print('\n----------------- grams ----------------')
    for v in _grams:
        print(v)

    _l = np.zeros(len_tokens)

    _valid_grams = []
    for gram in _grams:
        start = gram['start']
        end = gram['end']

        if np.sum(_l[start: end]) > 0 or not gram['prediction'].data or gram['prediction'].data[0].score <= 0.5:
            continue

        _l[start: end] = 1
        _valid_grams.append(gram)

    _valid_grams.sort(key=lambda x: x['start'])
    return list(map(lambda x: x['prediction'], _valid_grams))


def valid_gram_predict(_valid_grams: List[Prediction],
                       suggestion_history: List[LastChoice] = [],
                       top_k: int = 10,
                       cur_index: int = -1) -> List[Prediction]:
    """
    对筛选出的 valid_grams，一个一个进行 predict，
        predict 后的 gram 放到 suggestion history 里给下一个 gram 的 prediction 用
    """
    cur_index = len(suggestion_history) if cur_index < 0 else cur_index
    final_prediction = []

    tmp_suggestion_history = copy.deepcopy(suggestion_history)
    for i, gram in enumerate(_valid_grams):
        _history = tmp_suggestion_history + list(map(
            lambda x: LastChoice(id='', text=x.text, data=x.data[:1]), _valid_grams[i + 1:]))

        prediction = get_type(gram, _history, top_k, cur_index)
        final_prediction.append(prediction)

        last_choice = LastChoice(
            id=prediction.id,
            text=prediction.text,
            data=prediction.data[:1]
        )
        tmp_suggestion_history.insert(cur_index, last_choice)
        cur_index += 1

    return final_prediction


if __name__ == '__main__':
    # 测试代码
    grams = n_gram("count name used before")
    print('\n--------------------------')
    for v in grams:
        print(v)
    valid_grams = choose_valid_gram(grams)
    print('\n----------------------------')
    for v in valid_grams:
        print(v)
    # text_, tokens_list, type_list, field_list = choose_valid_gram(tokens_grams)
    # print(text_)
    # print("--------------------------------" * 3)
    # print(tokens_list)
    # print("--------------------------------" * 3)
    # print(type_list)
    # print("--------------------------------" * 3)
    # print(field_list)
