import copy
import os
import sys
import time

cur_dir = os.path.split(os.path.abspath(__file__))[0]
root_dir = os.path.split(cur_dir)[0]
sys.path.append(root_dir)

from typing import List, Union
from pymilvus import DataType, Milvus
from config.milvus import milvus_server_conf
from lib.utils import md5, uid
from lib.redis_utils import redis_get, redis_save, redis_drop, redis_batch_get, redis_del
from lib import logs


class MyMilvus:
    DESC_NAME = 'descriptions'
    VALUE_NAME = 'values'
    AVG_VALUE_NAME = 'meanValues'

    COLLECTIONS = {
        DESC_NAME: {'nlist': 256},
        VALUE_NAME: {'nlist': 1024},
        AVG_VALUE_NAME: {'nlist': 16},
    }

    INSERT_BATCH_SIZE = 100

    NAMES = [DESC_NAME, VALUE_NAME, AVG_VALUE_NAME]

    DIM_SIZE = 384

    AUTO_FLUSH = True

    def __init__(self):
        # 连接 milvus
        logs.add('Milvus', 'connection', f'connecting ...')
        self.milvus = Milvus(**milvus_server_conf)
        logs.add('Milvus', 'connection', f'successfully connecting')

        # 创建 collection
        for collection_name, val in self.COLLECTIONS.items():
            self.create_collection(collection_name, self.DIM_SIZE, val['nlist'])

        self.has_load_dict = {}

    def drop_collection(self, collection_name: str):
        if self.milvus.has_collection(collection_name):
            logs.add('Milvus', f'drop_collection', f'dropping collection ({collection_name})')
            self.milvus.drop_collection(collection_name)
            logs.add('Milvus', f'drop_collection', f'finish dropping collection ({collection_name})')

        logs.add('Milvus', f'drop_collection', f'dropping related redis data ({collection_name})')
        redis_drop(collection_name)
        redis_drop(f'{collection_name}__md5_2_id')
        logs.add('Milvus', f'drop_collection', f'finish dropping related redis data ({collection_name})')

    def create_collection(self, collection_name: str, dim_size=384, n_list=512):
        if not self.milvus.has_collection(collection_name):
            logs.add('Milvus', 'create_collection', f'No collection: {collection_name}')

            fields = {
                "fields": [
                    {"field": "id", 'name': 'id', "type": DataType.INT64, "is_primary": True},
                    {"field": "embedding", 'name': 'embedding', "type": DataType.FLOAT_VECTOR,
                     "params": {"dim": dim_size}}
                ]
            }
            self.milvus.create_collection(collection_name, fields)
            logs.add('Milvus', 'create_collection', f'Successfully create collection: ({collection_name})')

            index_params = {'metric_type': 'IP', 'index_type': 'IVF_SQ8', 'params': {'nlist': n_list}}
            self.milvus.create_index(collection_name, 'embedding', index_params)
            logs.add('Milvus', 'create_collection', f'Successfully create index: embedding ({index_params})')

        else:
            logs.add('Milvus', 'create_collection', f'collection exist: {collection_name}')

    def recreate_collection(self, collection_name):
        if collection_name not in self.NAMES:
            logs.add('Milvus', f'recreate_collection', f'collection name must be in {self.NAMES}',
                     _level=logs.LEVEL_ERROR)
            return

        _start_ = time.time()

        self.drop_collection(collection_name)
        self.create_collection(collection_name, self.DIM_SIZE, self.COLLECTIONS[collection_name]['nlist'])
        self.has_load_dict[collection_name] = False

        logs.add('Milvus', f'recreate_collection',
                 f'finish recreating collection ({collection_name}) : {time.time() - _start_:.4f}s ')

    def load(self, collection_name: str = '*'):
        """ 加载 collection，若加载过，不会重复加载 """
        if collection_name and collection_name != '*' and collection_name not in self.COLLECTIONS:
            logs.add('Milvus', 'load', f'collection name must be in {self.NAMES}')
            return

        # 若 collection_name 为 * 或 空，则全部加载
        if not collection_name or collection_name == '*':
            for collection_name in self.COLLECTIONS.keys():
                if collection_name not in self.has_load_dict or not self.has_load_dict[collection_name]:
                    logs.add('Milvus', 'load', f'start loading collection "{collection_name}"')
                    self.milvus.load_collection(collection_name)
                    self.has_load_dict[collection_name] = True
                    logs.add('Milvus', 'load', f'successfully loading collection "{collection_name}"')

        # 加载指定 collection
        elif collection_name not in self.has_load_dict or not self.has_load_dict[collection_name]:
            logs.add('Milvus', 'load', f'start loading collection "{collection_name}"')
            self.milvus.load_collection(collection_name)
            self.has_load_dict[collection_name] = True
            logs.add('Milvus', 'load', f'successfully loading collection "{collection_name}"')

    def _insert(self, collection_name: str, texts: List[str], vectors: List[List[float]], info: list,
                partition: str = None) -> (int, int):
        ids = get_uids(collection_name, texts, info, partition)

        # data = [ids, vectors]
        data = [
            {'type': DataType.INT64, 'name': 'id', 'values': ids},
            {'type': DataType.FLOAT_VECTOR, 'name': 'embedding', 'values': vectors}
        ]

        info_dict = {}
        for i, _id in enumerate(ids):
            tmp_info = info[i]
            tmp_info['freq'] = 1 if _id not in info_dict else info_dict[_id]['freq'] + 1

            info_dict[_id] = tmp_info

        try:
            # 创建分区
            if partition and not self.milvus.has_partition(collection_name, partition):
                self.milvus.create_partition(collection_name, partition)

            # 保存 embedding 数据到 milvus
            ret_insert = self.milvus.insert(collection_name, data, partition_name=partition)
            insert_count = ret_insert.insert_count

            if insert_count:
                for k, v in info_dict.items():
                    tmp_v = redis_get(k, collection_name)
                    if tmp_v:
                        v['freq'] = tmp_v['freq'] + v['freq']
                    redis_save(k, v, collection_name)

            return 1, insert_count

        except Exception as e:
            print(e)
            return 0, 0

    def insert(self, collection_name: str, texts: List[str], vectors: List[List[float]], info: list,
               partition=None) -> (int, int):
        """
        插入数据到 milvus
        :param collection_name:
        :param texts:
        :param vectors:
        :param info:
        :param partition:
        :return:
        """
        if not texts:
            return 1, 0

        length = len(texts)
        batch_size = self.INSERT_BATCH_SIZE
        insert_count = 0

        logs.add('Milvus', 'insert', f'start inserting "{collection_name}" data (len: {len(texts)})')

        for i in range(0, length, batch_size):
            tmp_ret, tmp_insert_count = self._insert(collection_name, texts[i: i + batch_size],
                                                     vectors[i: i + batch_size], info[i:i + batch_size], partition)

            # 若出现错误，则返回错误状态 0
            if not tmp_ret:
                return 0, insert_count
            insert_count += tmp_insert_count

        logs.add('Milvus', 'insert', f'successfully insert "{collection_name}" data ({insert_count}/{len(texts)})')

        # 将 milvus 内存里的数据写到磁盘
        if self.AUTO_FLUSH:
            self.flush([collection_name])

        return 1, insert_count

    def search(self,
               collection_name: str,
               vectors: list,
               limit=20,
               partitions: List[str] = None):
        # 加载 collection
        self.load(collection_name)

        start_search = time.time()

        # 检查是否存在该分区
        if partitions:
            filtered_partitions = list(filter(lambda x: self.milvus.has_partition(collection_name, x), partitions))
            if not filtered_partitions:
                logs.add('unknown', 'milvus_search', f'no valid partitions: {partitions}')
                return []

            # 有效 partitions
            partitions = filtered_partitions

        search_params = {"metric_type": "IP", "params": {"nprobe": limit}}

        try:
            results = self.milvus.search(
                collection_name,
                vectors,
                anns_field='embedding',
                param=search_params,
                limit=limit,
                partition_names=partitions,
                timeout=5
            )
        except:
            logs.add('Milvus', 'search', f'Error in search (collection: {collection_name})', _level=logs.LEVEL_ERROR)
            return []

        end_search = time.time()
        logs.add('unknown', f'milvus_search', f'milvus search for collection : {end_search - start_search:.4f}s ')
        logs.add('unknown', 'milvus_search', f'milvus search ids: {list(map(lambda x: x.ids, results))}')

        # 根据 milvus 返回的 id，去 redis 里取数据详细信息
        data = []
        for res in results:
            infos = redis_batch_get(res.ids, collection_name, num_thread=15)
            one_result = list(map(
                lambda x: {'data': x[0], 'similarity': max(min(round(x[1], 4), 1.), 0)},
                list(zip(infos, res.distances))
            ))
            data.append(one_result)

        end_redis = time.time()
        logs.add('unknown', f'milvus_search', f'milvus search for redis : {end_redis - end_search:.4f}s ')
        logs.add('unknown', 'milvus_search', f'milvus search result: {data}')
        return data

    def drop_partition(self, collection_name: str, partition_name):
        if self.milvus.has_partition(collection_name, partition_name):
            self.milvus.drop_partition(collection_name, partition_name)

    def flush(self, collection_names: List[str]):
        collection_names = list(filter(lambda x: x in self.NAMES, collection_names))
        if not collection_names:
            logs.add('Milvus', 'flush', f'collection names must be in "{self.NAMES}"', _level=logs.LEVEL_ERROR)
            return

        logs.add('Milvus', 'flush', f'start flushing collection "{collection_names}"')
        try:
            self.milvus.flush(collection_names)
            logs.add('Milvus', 'flush', f'successfully flush collection "{collection_names}"')
        except:
            logs.add('Milvus', 'flush', f'Error occur in flushing collection "{collection_names}"')


def get_uids(db_name: str, texts: List[str], info: List[dict], partition: Union[str, None] = ''):
    if partition:
        texts = list(map(lambda x: f'{partition}____{x}', texts))
    md5_ids = list(map(md5, zip(texts, info)))

    ids = []
    for m in md5_ids:
        tmp_uid = redis_get(m, f'{db_name}__md5_2_id')
        if not tmp_uid:
            tmp_uid = uid()
            redis_save(m, tmp_uid, f'{db_name}__md5_2_id')
        ids.append(int(tmp_uid))
    return ids


def filter_duplicate_texts(db_name: str, texts: List[str], info: List[dict], partition: str = ''):
    """ 过滤 milvus 已有的 texts """
    if not texts:
        return [], [], []

    # 根据 text, partition, info 获取 md5
    tmp_texts = list(map(lambda x: f'{partition}____{x}', texts)) if partition else texts
    md5_ids = list(map(md5, zip(tmp_texts, info)))

    # 根据 md5 读取 uid
    _uids = redis_batch_get(md5_ids, f'{db_name}__md5_2_id')

    # 过滤uid，只保留已有的 uid
    _valid_uids = list(filter(lambda x: x, _uids))
    # 检查该 uid 是否存在 db 中
    _db_rets = redis_batch_get(_valid_uids, db_name)
    # 保留 db 中有结果的 uid
    d_uid_2_ret = dict(filter(lambda x: x[1], zip(_valid_uids, _db_rets)))

    # 返回 uid 对应的结果是否在 db 中存在的 exist 结果
    _exist_rets = list(map(lambda x: True if x and x in d_uid_2_ret else False, _uids))

    # 根据 exist 结果进行过滤
    ret = list(filter(lambda x: not x[-1], zip(texts, info, list(range(len(texts))), _exist_rets)))
    if not ret:
        return [], [], []
    else:
        filtered_texts, filtered_info, indices, _ = list(zip(*ret))
        return filtered_texts, filtered_info, indices


desc_info_format = {'text': '$text', 'field': '$field', 'type': 'column_desc'}
value_info_format = {'text': '$text', 'column': '$field'}
avg_value_info_format = {'column': '$field'}
d_db_2_info_format = {
    MyMilvus.DESC_NAME: desc_info_format,
    MyMilvus.VALUE_NAME: value_info_format,
    MyMilvus.AVG_VALUE_NAME: avg_value_info_format,
}


def check_redis(origin_text: str):
    from core.processor import fields_v2

    results = []

    for field in fields_v2:
        column = field.name
        for partition in ['column_desc', column]:
            for db_name in MyMilvus.NAMES:
                info_format = d_db_2_info_format[db_name]

                # 获取 inof
                new_info_format = copy.deepcopy(info_format)
                for k, v in new_info_format.items():
                    new_info_format[k] = v.replace('$text', origin_text).replace('$field', column)

                    text = f'{partition}____{origin_text}'
                    md5_id = md5((text, info_format))

                    tmp_uid = redis_get(md5_id, f'{db_name}__md5_2_id')
                    if not tmp_uid:
                        continue

                    result = redis_get(tmp_uid, db_name)
                    if not result:
                        continue

                    results.append({'md5_id': md5_id, 'uid': tmp_uid, 'text': text,
                                    'partition': partition, 'column': column, 'data': result})

    print('\n------------------------------------')
    for v in results:
        print(v)

    return results


o_milvus = MyMilvus()

if __name__ == '__main__':
    if len(sys.argv) >= 3:
        _action = sys.argv[1]
        _collection_name = sys.argv[2]

        if _action == '--drop':
            o_milvus.drop_collection(_collection_name)

        elif _action == '--create':
            n_list = o_milvus.COLLECTIONS[_collection_name]['nlist'] \
                if _collection_name in o_milvus.COLLECTIONS else 1024
            o_milvus.create_collection(_collection_name, n_list=n_list)

        elif _action == '--recreate':
            o_milvus.recreate_collection(_collection_name)

        elif _action == '--redis':
            check_redis(sys.argv[2])
