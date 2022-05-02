import os
import yaml
import copy
import json
from functools import reduce

_cur_dir = os.path.split(os.path.abspath(__file__))[0]


class Yaml:

    def __init__(self, path):
        with open(path, 'rb') as f:
            self.__data = yaml.load(f)

    def __get_attribute(self, key_string):
        key_string = key_string.split('/')[1:]
        return copy.deepcopy(reduce(lambda a, b: a[b], key_string, self.__data))

    def process_nested_structure(self, target_attributes):
        data = self.__get_attribute(target_attributes)
        stack = [(data, '', {}, False)]

        while stack:
            tmp_json, parent_key, parent, to_combine = stack.pop(0)

            if isinstance(tmp_json, dict):

                # 不在 properties 里
                if 'type' in tmp_json:
                    if tmp_json['type'].lower() == 'object':
                        if 'properties' in tmp_json:
                            if to_combine:
                                if parent:
                                    for k, v in parent[parent_key].items():
                                        tmp_json['properties'][k] = v
                                    parent[parent_key] = tmp_json['properties']
                                    # parent[parent_key] = {**parent[parent_key], **tmp_json['properties']}
                                else:
                                    for k, v in data.items():
                                        tmp_json['properties'][k] = v
                                    data = tmp_json['properties']
                                    # data = {**data, **tmp_json['properties']}
                            else:
                                if parent:
                                    parent[parent_key] = tmp_json['properties']
                                else:
                                    data = tmp_json['properties']

                            if '#' in tmp_json:
                                tmp_json['properties']['#'] = tmp_json['#']
                            elif 'description' in tmp_json:
                                tmp_json['properties']['#'] = tmp_json['description']

                            to_combine = True
                            stack.append((tmp_json['properties'], parent_key, parent, to_combine))

                        if 'allOf' in tmp_json:
                            attribute_name = tmp_json['allOf'][0]['$ref']
                            all_of_object = self.__get_attribute(attribute_name)

                            if 'description' in tmp_json:
                                all_of_object['#'] = tmp_json['description']

                            stack.append((all_of_object, parent_key, parent, to_combine))

                    elif tmp_json['type'].lower() == 'array' and 'items' in tmp_json:
                        new_tmp_json = [tmp_json['items']]
                        if parent:
                            parent[parent_key] = new_tmp_json
                        else:
                            data = new_tmp_json

                        if 'description' in tmp_json:
                            tmp_json['items']['#'] = tmp_json['description']

                        stack.append((tmp_json['items'], 0, new_tmp_json, False))

                    elif '#' in tmp_json:
                        if 'type' in tmp_json:
                            # TODO keep type or not
                            parent[parent_key] = tmp_json['#']
                            # parent[parent_key] = {
                            #     'type': tmp_json['type'],
                            #     'desc': tmp_json['#'],
                            # }
                        else:
                            # TODO keep type or not
                            parent[parent_key] = tmp_json['#']
                            # parent[parent_key] = {
                            #     'desc': tmp_json['#'],
                            # }

                    elif 'description' in tmp_json:
                        if 'type' in tmp_json:
                            # TODO keep type or not
                            parent[parent_key] = tmp_json['description']
                            # parent[parent_key] = {
                            #     'type': tmp_json['type'],
                            #     'desc': tmp_json['description'],
                            # }
                        else:
                            # TODO keep type or not
                            parent[parent_key] = tmp_json['description']
                            # parent[parent_key] = {
                            #     'desc': tmp_json['description'],
                            # }

                elif '$ref' in tmp_json:
                    attribute_name = tmp_json['$ref']
                    ref_object = self.__get_attribute(attribute_name)
                    if 'description' in tmp_json:
                        ref_object['#'] = tmp_json['description']

                    stack.append((ref_object, parent_key, parent, to_combine))

                elif 'allOf' in tmp_json:
                    attribute_name = tmp_json['allOf'][0]['$ref']
                    all_of_object = self.__get_attribute(attribute_name)

                    if 'description' in tmp_json:
                        all_of_object['#'] = tmp_json['description']

                    stack.append((all_of_object, parent_key, parent, to_combine))

                # 在 properties 里
                else:
                    for k, v in tmp_json.items():
                        stack.append((v, k, tmp_json, False))

        return data


from utils import expand_json, reconstruct_nested_json

# p = r'/Users/samuellin/Downloads/openapi.yaml'
# p = r'/Users/samuellin/Downloads/resume_stage3.yaml'
p = os.path.join(_cur_dir, 'tmp_data', 'schema.yaml')
o_yaml = Yaml(p)
# new_data = o_yaml.process_nested_structure('#/components/schemas/ResumeAttribute')
# new_data = o_yaml.process_nested_structure('#/components/schemas/JobAttribute')
# new_data = o_yaml.process_nested_structure('#/components/schemas/ResumeStage5')
new_data = o_yaml.process_nested_structure('#/components/schemas/JobStage2')

# new_data = expand_json(new_data)
# new_data = list(filter(lambda x: '#' in x[0] or 'text' in x[0] and 'type' in x[0] or 'numbers' in x[0] or 'format' in x[0], new_data.items()))
# new_data = list(map(lambda x: (x[0].replace('#', 'desc'), x[1]) if '#' in x[0] else x, new_data))
# new_data = list(map(lambda x: (x[0].replace('.text.list_0.type', '.type'), x[1]) if '.text.list_0.type' in x[0] else x, new_data))
# new_data = list(map(lambda x: (x[0].replace('.numbers.list_0.type', '.type'), x[1]) if '.numbers.list_0.type' in x[0] else x, new_data))
# new_data = list(map(lambda x: (x[0].replace('.text.list_0.format', '.type'), f'string({x[1]})') if '.text.list_0.format' in x[0] else x, new_data))
# new_data = dict(new_data)
# new_data = reconstruct_nested_json(new_data)
# del new_data['desc']

# new_data = expand_json(new_data)
# new_data = list(filter(lambda x: str(x[0]).endswith('.desc'), new_data.items()))
# new_data = dict(map(lambda x: (x[0][:-len('.desc')], x[1]), new_data))
# new_data = reconstruct_nested_json(new_data)

# with open(r'/Users/samuellin/Downloads/lxw_resume_schema_v2.json', 'wb') as f:
# with open(r'/Users/samuellin/Downloads/lxw_job_schema_v2.json', 'wb') as f:
# with open(r'/Users/samuellin/Downloads/stage5_resume_schema_v0.json', 'wb') as f:

with open(os.path.join(_cur_dir, 'tmp_data', 'job_i2_schema.json'), 'wb') as f:
    f.write(json.dumps(new_data, ensure_ascii=False, indent=2).encode('utf-8'))

print(json.dumps(new_data, ensure_ascii=False, indent=2))

# print('\n-------------------------------------------')
# for k, v in new_data.items():
#     print(f'{k}: {v}')
