from config import env

if env.ENV == env.DEV:
    redis_conf = {'host': 'mesoor.f3322.net', 'port': '31012'}
elif env.ENV == env.PRE_TEST:
    redis_conf = {'host': '10.10.10.202', 'port': '1012'}
else:
    redis_conf = {'host': 'text2sql-redis', 'port': '6379'}
