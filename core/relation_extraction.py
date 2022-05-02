from typing import List
from server.definitions.suggestions import LastChoice, Relation, Choice
from core.type_classification import _load_config, _match_rule

_RULES = _load_config('relation')


def extract_relations(suggestion_history: List[LastChoice]) -> List[Relation]:
    len_history = len(suggestion_history)
    relations = []

    index = 0
    while index < len_history:
        for rule in _RULES:
            pre_rules = rule['rule']
            len_rule = len(pre_rules)

            # 判断历史长度与规则长度
            if len_rule > len_history - index:
                continue

            tmp_relations = rule['relations']
            history = suggestion_history[index: index + len_rule]

            # 匹配历史数据
            not_match = False
            for i in range(-1, -len_rule - 1, -1):
                pre_history = suggestion_history[:index + len_rule + i]
                pre_values = list(map(lambda x: x.data[0].value if x and x.data else '', pre_history))

                next_history = suggestion_history[index + len_rule + i + 1:]
                next_values = list(map(lambda x: x.data[0].value if x and x.data else '', next_history))

                if not _match_rule(pre_rules[i], history[i], False, pre_values, next_values):
                    not_match = True
                    break

            # 若历史数据不匹配该规则，换下一规则
            if not_match:
                continue

            relations += list(map(lambda x: Relation(
                relation_type=x['type'],
                head_id=history[x['head']].id,
                tail_id=history[x['tail']].id,
                priority=x['priority'] if 'priority' in x else 1,
            ), tmp_relations))

            index += len_rule - 1
            break

        index += 1

    return relations


if __name__ == '__main__':
    # 测试代码
    # pre_5 = get_type("工作地点")
    # pre_4 = get_type("上海")
    # pre_3 = get_type("OR")
    # pre_2 = get_type("北京")
    # pre_1 = get_type("OR")
    # cur = get_type("深圳")
    # rela = extract_relations([pre_5, pre_4, pre_3, pre_2, pre_1, cur])
    # print(f'pre_5: {pre_5}')
    # print(f'pre_4: {pre_4}')
    # print(f'pre_3: {pre_3}')
    # print(f'pre_2: {pre_2}')
    # print(f'pre_1: {pre_1}')
    # print(f'cur: {cur}')
    # print(f'rela: {rela}')
    # _result = [["column_desc", "工作地点", ["JobLocationsNormalizedProvince", "JobLocationsNormalizedCity"]],
    #            ["comparison_op_desc", "不在", ["!="]], ["value", "北京", ["JobLocationsNormalizedCity"]],
    #            ["condition_op_desc", "or", ["or"]], ["value", "上海", ["JobLocationsNormalizedCity"]]]
    # _result_index = [[index, data] for index, data in enumerate(_result)]
    # _result_index = list(map(lambda x: LastChoice(
    #     id=str(x[0]), text=x[1][1], type=x[1][0][0] if isinstance(x[1][0], list) else x[1][0],
    #     data=[Choice(text=x[1][1], value=x[1][2][0], score=1.)])
    #                          , _result_index))
    # print(_result_index)
    _history = [["column_desc", "平均薪资", "ResumeWorkYearNormalizedGte"], ["group_fn", "最高", "Max"]]
    _history = list(map(
        lambda x: LastChoice(id=x[1], text=x[1], data=[
            Choice(text=x[1], type=x[0] if isinstance(x[0], str) else x[0][0], value=x[-1], score=1.)
        ]),
        _history
    ))

    _relations = extract_relations(_history)
    print('\n------------ relations ---------------')
    for r in _relations:
        print(r)
