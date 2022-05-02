from normalize.time_normalize import _parser


def normalize(text):
    try:
        return {'gte': _parser(text)['time'][0].split()[0], 'lte': _parser(text)['time'][1].split()[0]}
    except:
        return {}


if __name__ == "__main__":
    print(normalize("五天前"))
