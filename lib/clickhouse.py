import os
from typing import Any
from clickhouse_driver import Client
from lib import logs

CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', '127.0.0.1')
CLICKHOUSE_PORT = os.getenv('CLICKHOUSE_PORT', 9000)
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER', 'default')
CLICKHOUSE_PASS = os.getenv('CLICKHOUSE_PASS', 'password')
NQL_DATABASE = 'nql'


def _get_clickhouse_conn() -> Client:
    logs.add('ClickHouse', '_get_clickhouse_conn', 'start connecting ... ')
    clickhouse_client = Client(host=CLICKHOUSE_HOST,
                               port=CLICKHOUSE_PORT,
                               user=CLICKHOUSE_USER,
                               password=CLICKHOUSE_PASS,
                               database=NQL_DATABASE)
    clickhouse_client.connection.connect()
    logs.add('ClickHouse', '_get_clickhouse_conn', 'successfully connect')
    return clickhouse_client


def exec_sql(sql: str) -> Any:
    connection = _get_clickhouse_conn()
    try:
        logs.add('ClickHouse', 'exec_sql', f'start executing sql: "{sql}"')
        _data = connection.execute(sql, with_column_types=True)
        _data = _data[0]
        logs.add('ClickHouse', 'exec_sql', f'successfully executing sql: "{sql}" (len: {len(_data)}, result: {_data})')
        return _data
    finally:
        connection.disconnect()


def get_distinct_count(column_name: str, table: str) -> int:
    """ 获取某个 column 的 distinct count; 如果失败，返回 -1 """
    try:
        count_sql = f'select count (distinct {column_name}) from v_{table}'
        return exec_sql(count_sql)[0][0]
    except:
        return -1


if __name__ == '__main__':
    import json

    # from core.processor import fields_v2
    # column = fields_v2[0]
    # print(get_distinct_count(column.actual_column, column.table))

    # data = exec_sql("SELECT distinct updatedAt2 FROM v_tenant limit 10")
    # print(f'{data}')
    # print(json.dumps(data, ensure_ascii=False, indent=2))
