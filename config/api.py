from config import env

if env.ENV == env.DEV:
    yonghe_domain = 'localhost:2222'
    synonym_domain = 'mesoor.f3322.net:31999'
elif env.ENV == env.PRE_TEST:
    yonghe_domain = 'localhost:2000'
    synonym_domain = '10.10.10.202:1999'
elif env.ENV == env.TEST:
    yonghe_domain = 'dev-nql'
    synonym_domain = 'dev-synonyms'
else:
    yonghe_domain = 'prod-nql'
    synonym_domain = 'prod-synonyms'
