import re
from normalize.salary_months import normalize

if __name__ == "__main__":
    text = "下限为5年"
    print(normalize(text))
