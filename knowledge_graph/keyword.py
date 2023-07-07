import json
import re
from paddlenlp import Taskflow

# 使用Paddlenlp的TaskFlow模块提取中文试题
ner = Taskflow("ner", entity_only=True)

with open('./config/keyword_config.json', 'r', encoding='utf-8') as f:
    json_data = json.load(f)
keyword_extract_pattern = json_data["keyword_extract_pattern"]  # 远程Aura Neo4j地址
keyword_ignore_pattern = json_data["keyword_ignore_pattern"]


def generate_element_set():
    """
    生成化学元素集
    :return: set
    """
    s1 = 'H, He, Li, Be, B, C, N, O, F, Ne, Na, Mg, Al, Si, P, S, Cl, Ar, K, Ca, Sc, Ti, V, Cr, Mn, Fe, Co, Ni, Cu, Zn, Ga, Ge, As, Se, Br'
    s2 = 'Kr，Rb，Sr，Y，Zr，Nb，Mo，Tc，Ru，Rh，Pd，Ag，Cd，In，Sn，Sb，Te，I，Xe，Cs，Ba，La，Ce，Pr，Nd，Pm，Sm，Eu，Gd，Tb，Dy，Ho，Er，Tm，Yb，Lu，Hf，Ta，W，Re，Os，Ir，Pt，Au，Hg，Fr，Ra，Ac，Th，Pa，U，Np，Pu，Am，Cm，Bk，Cf，Es，Fm，Md，No，Lr，Rf，Db，Sg，Bh，Hs，Mt，Ds，Rg，Cn，Nh，Fl，Mc，Lv，Ts，Og'
    # s3 = 'A, B, X'  # 一般题目中可能用这三个字母代指某种元素
    s1 = s1.split(', ')
    s2 = s2.split('，')
    # s3 = s3.split()
    return set(s1 + s2)


element_set = generate_element_set()


def extract_keyword_pattern(pattern: str, text: str):
    elements = re.finditer(pattern, text)
    res = set()
    for element in elements:
        start = element.start()
        end = element.end()
        formula = element.string[start:end]
        if len(formula) <= 2 and formula not in element_set:
            # 过滤一些无关的关键字
            continue
        res.add(element.string[start:end])
    return res


def extract_entity(text):
    # 使用TaskFlow模块抽取中文实体
    entity_set = ner(text)
    res = set()
    for e in entity_set:
        res.add(e[0])
    return res


def ignore_keyword(keyword_set):
    # 忽略特定的关键字
    res = set.copy(keyword_set)
    for keyword in keyword_set:
        for pattern in keyword_ignore_pattern:
            if re.search(pattern, keyword) is not None:
                res.remove(keyword)
    return res


def add_longest_prefix(target_set: set, new_set: set):
    ans = target_set.copy()
    for new_item in new_set:
        for old_item in target_set:
            if len(new_item) > len(old_item) and new_item.startswith(old_item):
                try:
                    ans.remove(old_item)
                except KeyError:
                    # 重复删除了
                    continue
    return ans.union(new_set)


def extract_keyword(text: str):
    """
    给定文本，提取中文实体并按照配置规则识别特定实体
    :param text:
    :return:
    """
    # 去掉不必要的分隔符
    text = text.replace('\u3000', ' ')
    res = set()
    for pattern in keyword_extract_pattern:
        # res = res.union(extract_keyword_pattern(pattern, text))
        res = add_longest_prefix(res,extract_keyword_pattern(pattern, text))
    entities = extract_entity(text)
    res = res.union(entities)
    return ignore_keyword(res)
