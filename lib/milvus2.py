import os
import sys
import time

cur_dir = os.path.split(os.path.abspath(__file__))[0]
root_dir = os.path.split(cur_dir)[0]
sys.path.append(root_dir)

from typing import List, Union
from pymilvus import CollectionSchema, FieldSchema, DataType
from pymilvus import connections, utility, Collection
from config.milvus import milvus_server_conf
from lib.utils import md5, uid
from lib.redis_utils import redis_get, redis_save, redis_drop, redis_batch_get, redis_del
from lib import logs


def connect(name='default'):
    try:
        connections.connect(**milvus_server_conf, alias=name)
        logs.add('Initialization', f'milvus', f'connect "{name}"')
        return
    except:
        pass

    # 失败重新连接 (尝试3遍)
    try:
        connections.connect(**milvus_server_conf, alias=name)
        logs.add('Initialization', f'milvus', f'connect "{name}"')
        return
    except:
        pass

    # 失败重新连接
    try:
        connections.connect(**milvus_server_conf, alias=name)
        logs.add('Initialization', f'milvus', f'connect "{name}"')
        return
    except:
        pass

    # 失败重新连接
    connections.connect(**milvus_server_conf, alias=name)
    logs.add('Initialization', f'milvus', f'connect "{name}"')


def disconnect(name='default'):
    connections.disconnect(name)


def get_uid(text: str, db_name: str, partition: str):
    _mid = md5((f'{partition}____' if partition else '') + text)
    _uid = redis_get(_mid, f'{db_name}__md5_2_id')
    if not _uid:
        _uid = uid()
        redis_save(_mid, _uid, f'{db_name}__md5_2_id')
    return int(_uid)


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
    tmp_texts = list(map(lambda x: f'{partition}____{x}', texts)) if partition else texts
    md5_ids = list(map(md5, zip(tmp_texts, info)))

    indices = []
    filtered_texts = []
    filtered_info = []
    for i, m in enumerate(md5_ids):
        _uid = redis_get(m, f'{db_name}__md5_2_id')
        if _uid and redis_get(_uid, db_name):
            continue

        filtered_texts.append(texts[i])
        filtered_info.append(info[i])
        indices.append(i)

    return filtered_texts, filtered_info, indices


def create_collection(collection_name, dim_size=384, nlist=1024):
    # 若不存在，则创建 collection
    if not utility.has_collection(collection_name):
        logs.add('Initialization', 'Milvus', f'No collection: {collection_name}')

        # 定义 collection schema
        id_schema = FieldSchema(name='id', dtype=DataType.INT64, is_primary=True)
        vector_schema = FieldSchema(name='embedding', dtype=DataType.FLOAT_VECTOR, dim=dim_size)
        schema = CollectionSchema(fields=[id_schema, vector_schema], description=collection_name)

        # 创建 collection
        collection = Collection(name=collection_name, schema=schema)

        logs.add('Initialization', 'Milvus', f'Successfully create collection: {collection_name}')

        # 创建索引
        index_params = {'metric_type': 'IP', 'index_type': 'IVF_FLAT', 'params': {'nlist': nlist}}
        collection.create_index(field_name='embedding', index_params=index_params)

        logs.add('Initialization', 'Milvus', f'Successfully create index: embedding ({index_params})')

    # 获取 existing collection
    else:
        collection = Collection(name=collection_name)
        logs.add('Initialization', 'Milvus', f'Get exist collection: {collection_name}')

    return collection


def _insert(collection: Collection, texts: List[str], vectors: List[List[float]], info: list, partition=None):
    partition = None

    ids = get_uids(collection.name, texts, info, partition)

    data = [ids, vectors]

    info_dict = {}
    for i, _id in enumerate(ids):
        tmp_info = info[i]
        tmp_info['freq'] = 1 if _id not in info_dict else info_dict[_id]['freq'] + 1

        info_dict[_id] = tmp_info

    try:
        # 创建分区
        if partition and not collection.has_partition(partition):
            collection.create_partition(partition, description=partition)

        # 保存 embedding 数据到 milvus
        mr = collection.insert(data, partition_name=partition)
        insert_count = mr.insert_count

    except Exception as e:
        print(e)
        insert_count = 0

    if insert_count:
        for k, v in info_dict.items():
            tmp_v = redis_get(k, collection.name)
            if tmp_v:
                v['freq'] = tmp_v['freq'] + v['freq']
            redis_save(k, v, collection.name)

    return insert_count


def insert(collection: Collection, texts: List[str], vectors: List[List[float]], info: list, partition=None):
    length = len(texts)
    batch_size = 100
    insert_count = 0

    for i in range(0, length, batch_size):
        insert_count += _insert(
            collection, texts[i: i + batch_size], vectors[i: i + batch_size], info[i:i + batch_size], partition)

    return insert_count


def update(collection: Collection, p_ids: List[int], texts: List[str], vectors: list, info: list, partition=''):
    # 获取 texts 对应的 唯一 int id
    ids = get_uids(collection.name, texts, info, partition)

    for p_id, _id in list(zip(p_ids, ids)):
        # 查看 p_id id 的映射表
        old_id = redis_get(f'{p_id}', partition)
        # 若出现更新
        if old_id and f'{old_id}' != f'{_id}':
            # 查看老数据对应的详情
            old_info = redis_get(old_id, collection.name)
            if old_info:
                # 频率降低
                old_info['freq'] -= 1

                if old_info['freq'] <= 0:
                    # 若频率 <= 0, 则从 redis milvus 中删除数据
                    redis_del(old_id, table_name=collection.name)
                    # collection.delete(f'id in [{old_id}]')

                else:
                    # 更新数据出现频率
                    redis_save(old_id, old_info, collection.name)

        # 更新 当前 p_id id 的映射表
        redis_save(f'{p_id}', _id, partition)

    # 插入数据
    return insert(collection, texts, vectors, info, partition)


def search(
        collection: Collection,
        vectors: list,
        limit=10,
        partitions: List[str] = None):
    partitions = None

    search_params = {"metric_type": "IP", "params": {"nprobe": limit}}
    start_search = time.time()

    # 检查是否存在该分区
    if partitions:
        partitions = list(filter(lambda x: collection.has_partition(x), partitions))
        if not partitions:
            logs.add('unknown', 'milvus_search', f'no valid partitions: {partitions}')
            return []

    # milvus 向量搜索
    results = collection.search(
        data=vectors,
        anns_field='embedding',
        param=search_params,
        limit=limit,
        partition_names=partitions,
    )
    end_search = time.time()
    logs.add('unknown', f'milvus_search', f'milvus search for collection : {end_search - start_search:.4f}s ')
    logs.add('unknown', 'milvus_search', f'milvus search ids: {list(map(lambda x: x.ids, results))}')

    # 根据 milvus 返回的 id，去 redis 里取数据详细信息
    data = []
    for res in results:
        infos = redis_batch_get(res.ids, collection.name, num_thread=15)
        one_result = list(map(
            lambda x: {'data': x[0], 'similarity': max(min(round(x[1], 4), 1.), 0)},
            list(zip(infos, res.distances))
        ))
        data.append(one_result)
    end_redis = time.time()
    logs.add('unknown', f'milvus_search', f'milvus search for redis : {end_redis - end_search:.4f}s ')
    logs.add('unknown', 'milvus_search', f'milvus search result: {data}')
    return data


def drop_collection(collection_name):
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)

    redis_drop(collection_name)
    redis_drop(f'{collection_name}__md5_2_id')


def drop_partition(collection: Collection, partition_name):
    if collection.has_partition(partition_name):
        collection.drop_partition(partition_name)


class Milvus:
    DESC_NAME = 'descriptions'
    COLUMN_DESC_NAME = 'columnDescriptions'
    VALUE_NAME = 'values'
    AVG_VALUE_NAME = 'meanValues'

    NAMES = [DESC_NAME, COLUMN_DESC_NAME, VALUE_NAME, AVG_VALUE_NAME]

    N_LIST_DESC = 256
    N_LIST_COLUMN_DESC = 128
    N_LIST_VALUE = 2048
    N_LIST_AVG_VALUE = 32

    def __init__(self, name='default'):
        self._con_name = name
        connect(self._con_name)

        _start_ = time.time()
        self.desc_collection = create_collection(self.DESC_NAME, nlist=self.N_LIST_DESC)
        logs.add('Initialization', f'milvus', f'milvus for desc collection : {time.time() - _start_:.4f}s ')

        _start_ = time.time()
        self.column_desc_collection = create_collection(self.COLUMN_DESC_NAME, nlist=self.N_LIST_COLUMN_DESC)
        logs.add('Initialization', f'milvus', f'milvus for column_desc collection : {time.time() - _start_:.4f}s ')

        _start_ = time.time()
        self.value_collection = create_collection(self.VALUE_NAME, nlist=self.N_LIST_VALUE)
        logs.add('Initialization', f'milvus', f'milvus for values collection : {time.time() - _start_:.4f}s ')

        _start_ = time.time()
        self.avg_value_collection = create_collection(self.AVG_VALUE_NAME, nlist=self.N_LIST_AVG_VALUE)
        logs.add('Initialization', f'milvus', f'milvus for avg values collection : {time.time() - _start_:.4f}s ')

        self.load()

    def load(self):
        _start_ = time.time()
        self.desc_collection.load()
        logs.add('Initialization', f'milvus', f'milvus for desc load : {time.time() - _start_:.4f}s ')

        _start_ = time.time()
        self.column_desc_collection.load()
        logs.add('Initialization', f'milvus', f'milvus for column_desc load : {time.time() - _start_:.4f}s ')

        _start_ = time.time()
        self.value_collection.load()
        logs.add('Initialization', f'milvus', f'milvus for values load : {time.time() - _start_:.4f}s ')

        _start_ = time.time()
        self.avg_value_collection.load()
        logs.add('Initialization', f'milvus', f'milvus for avg values load : {time.time() - _start_:.4f}s ')

    def recreate_index(self, collection_name):
        if collection_name not in self.NAMES:
            return f'collection name must be in {self.NAMES}'

        logs.add('Initialization', f'milvus', f'recreating index ("{collection_name}")')
        _start_ = time.time()

        if collection_name == self.DESC_NAME:
            if self.desc_collection.has_index():
                self.desc_collection.drop_index()

            index_params = {'metric_type': 'IP', 'index_type': 'IVF_FLAT', 'params': {'nlist': self.N_LIST_DESC}}
            self.desc_collection.create_index(field_name='embedding', index_params=index_params)

        elif collection_name == self.COLUMN_DESC_NAME:
            if self.column_desc_collection.has_index():
                self.column_desc_collection.drop_index()

            index_params = {'metric_type': 'IP', 'index_type': 'IVF_FLAT', 'params': {'nlist': self.N_LIST_COLUMN_DESC}}
            self.column_desc_collection.create_index(field_name='embedding', index_params=index_params)

        elif collection_name == self.VALUE_NAME:
            if self.value_collection.has_index():
                self.value_collection.drop_index()

            index_params = {'metric_type': 'IP', 'index_type': 'IVF_FLAT', 'params': {'nlist': self.N_LIST_VALUE}}
            self.value_collection.create_index(field_name='embedding', index_params=index_params)

        elif collection_name == self.AVG_VALUE_NAME:
            if self.avg_value_collection.has_index():
                self.avg_value_collection.drop_index()

            index_params = {'metric_type': 'IP', 'index_type': 'IVF_FLAT', 'params': {'nlist': self.N_LIST_AVG_VALUE}}
            self.avg_value_collection.create_index(field_name='embedding', index_params=index_params)

        logs.add('Initialization', f'milvus',
                 f'finish recreating index ("{collection_name}") : {time.time() - _start_:.4f}s')

    def recreate_collection(self, collection_name):
        if collection_name not in self.NAMES:
            print(f'collection name must be in {self.NAMES}')
            logs.add('Milvus', f'collection', f'collection name must be in {self.NAMES}', _level=logs.LEVEL_ERROR)
            return

        logs.add('Initialization', f'milvus', f'recreating collection ({collection_name})')
        _start_ = time.time()

        if collection_name == self.DESC_NAME:
            drop_collection(self.DESC_NAME)
            self.desc_collection = create_collection(self.DESC_NAME, nlist=self.N_LIST_DESC)
            self.desc_collection.load()

        elif collection_name == self.COLUMN_DESC_NAME:
            drop_collection(self.COLUMN_DESC_NAME)
            self.column_desc_collection = create_collection(self.COLUMN_DESC_NAME, nlist=self.N_LIST_COLUMN_DESC)
            self.column_desc_collection.load()

        elif collection_name == self.VALUE_NAME:
            drop_collection(self.VALUE_NAME)
            self.value_collection = create_collection(self.VALUE_NAME, nlist=self.N_LIST_VALUE)
            self.value_collection.load()

        elif collection_name == self.AVG_VALUE_NAME:
            drop_collection(self.AVG_VALUE_NAME)
            self.avg_value_collection = create_collection(self.AVG_VALUE_NAME, nlist=self.N_LIST_AVG_VALUE)
            self.avg_value_collection.load()

        logs.add('Initialization', f'milvus',
                 f'finish recreating collection ({collection_name}) : {time.time() - _start_:.4f}s ')

    # def __del__(self):
    #     disconnect(self._con_name)


o_milvus = Milvus()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--index':
        for _index in sys.argv[2:]:
            o_milvus.recreate_index(_index)
