import math
import numpy as np
import pandas as pd
from numpy import log
from graph_database.connect import Neo4jDB, connect_db


def records2dataframe(records, keys, set_index=None):
    if len(records) < 0:
        pd.DataFrame(columns=keys)
    res = pd.DataFrame(columns=keys)
    for record in records:
        res.loc[len(res)] = list(record)
    if set_index is not None:
        res = res.set_index(set_index)
    return res


def get_knowledge_num(db: Neo4jDB):
    records, summary, keys = db.driver.execute_query(
        "MATCH (k:Knowledge) RETURN count(*) AS knowledge_num",
        database_="neo4j",
    )
    return records[0][0]


# neo4j_db = connect_db()
# D = get_knowledge_num(neo4j_db)

# 关键词i在知识点j中的频数
kf_statement_1 = "match (i:KeyWord) -[r:related_to]-> (j:Knowledge) " \
                 "where i.keyword_id = $kw_id and j.knowledge_id = $kn_id" \
                 " return r.count"
# 知识点j所有的关键词数
kf_statement_2 = "match (i:KeyWord) -[r:related_to]-> (j:Knowledge) " \
                 "where j.knowledge_id = $kn_id" \
                 " return sum(r.count)"


def keyword_frequency(keyword_id: int, knowledge_id: int, db: Neo4jDB):
    records, summary, keys = db.driver.execute_query(kf_statement_1,
                                                     kw_id=keyword_id,
                                                     kn_id=knowledge_id,
                                                     database_="neo4j")
    keyword_connection_num = records[0][0] if len(records) != 0 else 0
    records, summary, keys = db.driver.execute_query(kf_statement_2,
                                                     kn_id=knowledge_id,
                                                     database_="neo4j")
    knowledge_connection_num = records[0][0]
    assert knowledge_connection_num > 0
    return keyword_connection_num / knowledge_connection_num


def inverse_document_frequency(keyword_id_list: [int], db: Neo4jDB):
    idf_statement = "match (i:KeyWord) -[r:related_to]-> (j:Knowledge) " \
                    "where i.keyword_id in $keyword_id_list " \
                    "return i.keyword_id as keyword_id, count(j) as knowledge_num"
    D = get_knowledge_num(neo4j_db)
    records, summary, keys = db.driver.execute_query(idf_statement,
                                                     keyword_id_list=keyword_id_list,
                                                     database_="neo4j")
    knowledge_num = records2dataframe(records, keys, set_index='keyword_id')
    return log(D / (1 + knowledge_num))


def kf_idf(keyword_id_list: [int], knowledge_id: int, db: Neo4jDB):
    result = 0
    for keyword_id in keyword_id_list:
        kf = keyword_frequency(keyword_id, knowledge_id, db)
        idf = inverse_document_frequency(keyword_id, db)
        result += kf * idf
    return result


keyword2id_statement = "match (k:KeyWord) where k.content in $keyword_list " \
                       "return k.content as name, k.keyword_id as id"


def filer_keyword(kw_id_series: pd.Series,
                  max_count: int = 25,
                  filter_rate: float = 0.25):
    """
    过滤一部分连接knowledge太多的关键词
    :param kw_id_series: keyword列表
    :param max_count: 连接超过max_count的关键词将被过滤
    :param filter_rate: 去掉的关键词比例
    :return: 留下的关键词列表和连接计数
    """
    value_count = kw_id_series.value_counts()
    filtered_ids = value_count[value_count > max_count]
    filtered_num = max(len(filtered_ids), math.ceil(len(value_count) * filter_rate))
    return value_count.iloc[filtered_num:].index.values


def generate_if(kw_kn_df: pd.DataFrame):
    # kn_count = pd.Series([i[1] for i in kw_kn_df.index]).value_counts()
    kn_count = kw_kn_df["relation_num"].groupby(level=1).sum()
    kn_id_array = kn_count.index.values
    kw_id_array = pd.Series([i[0] for i in kw_kn_df.index]).unique()
    idf_table = pd.DataFrame(
        np.zeros((len(kw_id_array), len(kn_id_array))),
        index=kw_id_array,
        columns=kn_id_array
    )
    for i, j in kw_kn_df.index:
        idf_table.loc[i][j] = kw_kn_df.loc[(i, j)]['relation_num']
    for col_index in kn_id_array:
        idf_table[col_index] /= kn_count[col_index]
    return idf_table


find_parent_statement = "match (s:Knowledge) -[:belong_to]-> (p:Knowledge) " \
                        "where s.knowledge_id in $kn_id_list " \
                        "return distinct s.knowledge_id as s_id, " \
                        "p.knowledge_id as p_id, p.name as p_name, " \
                        "p.level as p_level;"


def generate_transfer_table(kn_id_list: [], db: Neo4jDB):
    records, summary, keys = db.driver.execute_query(find_parent_statement,
                                                     kn_id_list=kn_id_list,
                                                     database_="neo4j")
    return records2dataframe(records, keys, set_index='s_id')


def generate_relation_by_level(kw_kn_temp: pd.DataFrame, level: int, db: Neo4jDB):
    """
    生成层级level的关键字-知识点连接表
    :param kw_kn_temp: 辅助数组，存储上一次生成的kw_kn_supplement
    :param level: 需要生成的层级
    :param db:
    :return:
    """
    assert kw_kn_temp.index.values.max() <= level
    kw_kn_level_df = kw_kn_temp.loc[level]
    level_df = kw_kn_level_df.copy()
    # 生成下一个kw_kn_temp
    kn_id_list = level_df["kn_id"].unique().tolist()
    transfer_table = generate_transfer_table(kn_id_list, db)
    index = level_df["kn_id"]
    level_df = level_df.reset_index()
    level_df[["kn_id", "kn_name", "kn_level"]] = transfer_table.loc[index].values
    kw_kn_temp = kw_kn_temp.drop(level, axis=0)
    kw_kn_temp = pd.concat([kw_kn_temp, level_df.set_index("kn_level")]).reset_index()
    # 重新统计relation_num
    by = kw_kn_temp.columns.tolist()
    by.remove("relation_num")
    kw_kn_temp = kw_kn_temp \
        .groupby(by=by) \
        .sum()
    # kw_kn_supplement = kw_kn_supplement.set_index(["kw_id", "kn_id"]).drop(columns="relation_num").drop_duplicates()
    # kw_kn_supplement["relation_num"] = re_count
    return kw_kn_level_df, kw_kn_temp.reset_index().set_index("kn_level")


def get_relation_table(keyword_id_list: [int], subject: str, db: Neo4jDB):
    """
    根据keyword_id_list获与之直接关联的knowledge关系表
    表头为: [kw_id, kw_name, kn_id, kn_name, kn_level, relation_num]
    :param subject:
    :param keyword_id_list:
    :param db:
    :return:
    """
    search_knowledge_statement = "match (k:KeyWord) -[r:related_to]-> (t:Knowledge) " \
                                 "where k.keyword_id in $keyword_id_list and t.subject=$subject " \
                                 "return k.keyword_id as kw_id, k.content as kw_name, " \
                                 "t.knowledge_id as kn_id, t.name as kn_name, " \
                                 "t.level as kn_level, r.count as relation_num"
    records, summary, keys = db.driver.execute_query(search_knowledge_statement,
                                                     subject=subject,
                                                     keyword_id_list=keyword_id_list,
                                                     database_="neo4j")
    # 获取keyword和knowledge的初始关联表
    return records2dataframe(records, keys)


def get_keyword_table(db: Neo4jDB, subject: str, keyword_list: [str] = None):
    """
    获取关键词表
    :param subject:
    :param db:
    :param keyword_list:
    :return:
    """
    if keyword_list is not None:
        statement = "match (k:KeyWord) " \
                    "where k.content in $keyword_list and k.subject = $subject " \
                    "return k.keyword_id as kw_id, k.content as kw_name"
        records, summary, keys = db.driver.execute_query(statement,
                                                         keyword_list=keyword_list,
                                                         subject=subject,
                                                         database_="neo4j")
    else:
        statement = "match (k:KeyWord) where k.subject = $subject " \
                    "return k.keyword_id as kw_id, k.content as kw_name"
        records, summary, keys = db.driver.execute_query(statement,
                                                         subject=subject,
                                                         database_="neo4j")

    return records2dataframe(records, keys, set_index="kw_id")


def get_knowledge_table(subject: str, db: Neo4jDB):
    """
    获取包含所有knowledge的table
    :param db:
    :return:
    """
    statement = "match (k:Knowledge) where k.subject=$subject " \
                "return k.knowledge_id as kn_id, k.name as kn_name, " \
                "k.level as kn_level, k.subject as subject"
    records, summary, keys = db.driver.execute_query(statement,
                                                     subject=subject,
                                                     database_="neo4j")
    return records2dataframe(records, keys, set_index="kn_id")


def get_keyword_idf(keyword_id_list: [int], kw_kn_level_df: pd.DataFrame):
    kw_connection_count = kw_kn_level_df["kw_id"].value_counts()
    d = len(kw_kn_level_df["kn_id"].unique())
    return np.log(d / (1 + kw_connection_count[keyword_id_list]))


def get_level_list(subject: str, db:Neo4jDB):
    statement = "match (k:Knowledge) where k.subject = $subject" \
                " return distinct k.level as level order by level desc"
    records, summary, keys = db.driver.execute_query(statement,
                                                     subject=subject,
                                                     database_="neo4j")
    return records2dataframe(records, keys)["level"]


def generate_recommend_set(keyword_list: [str],
                           subject: str,
                           db: Neo4jDB,
                           row_limit: int):
    """
    使用知识图谱获取知识点推荐
    :param keyword_list:包含关键词的列表
    :param subject:知识点学科
    :param db:Neo4jDB连接
    :param row_limit:每一层返回知识点的行数
    :return: 包含了各个层级知识点得分表的字典
    """
    # 首先匹配keyword_list对应的id,无法匹配的过滤掉
    keyword_table = get_keyword_table(db, subject, keyword_list)
    keyword_id_list = keyword_table.index.to_list()
    # keyword_idf = inverse_document_frequency(keyword_id_list, db)
    # 获得与keyword连接的知识点
    kw_kn_df = get_relation_table(keyword_id_list, subject, db).set_index("kn_level")
    # id到knowledge的转化表
    knowledge_table = get_knowledge_table(subject, db)

    # level_list = list(sorted(kw_kn_df.index.unique(), reverse=True))
    level_list = get_level_list(subject,db)[:-1]
    kw_kn_temple = kw_kn_df
    result_dict = {}
    for level in level_list:
        # kw_kn_level_df = kw_kn_df.loc[level]
        kw_kn_level_df, kw_kn_temple = generate_relation_by_level(kw_kn_temple, level, db)
        keyword_id_list = kw_kn_level_df["kw_id"].unique().tolist()
        keyword_idf = get_keyword_idf(keyword_id_list, kw_kn_level_df)
        # filtered_keyword_id_list = filer_keyword(kw_kn_level_df['kw_id'],
        #                                         max_count,
        #                                         filter_rate)
        kw_kn_level_df = kw_kn_level_df.set_index(["kw_id", "kn_id"])
        # kw_kn_level_df = kw_kn_level_df.loc[filtered_keyword_id_list, :]
        if_table = generate_if(kw_kn_level_df)
        # filtered_kw_idf = keyword_idf.loc[filtered_keyword_id_list]
        # result = if_table.transpose().dot(filtered_kw_idf)
        result = if_table.transpose().dot(keyword_idf)
        result_name = knowledge_table['kn_name'].loc[result.index]
        result = pd.DataFrame({"score": result, "name": result_name}).sort_values(by=["score"], ascending=False)
        result.index.name = "knowledge_id"
        result_dict[level] = result[:row_limit]
    return result_dict


if __name__ == '__main__':
    # 测试知识点推荐模块
    keyword_list = ['Cl', 'AlO', '电离方程式', '弱电解质', '导电', '熔点', '消毒液', '已知', 'C', 'H', '无水', '熔融',
                    'B', 'Al(OH)3', 'Al3', 'H2O', '离子化合物', '升华', 'HgCl2', '300 ℃', '手术刀', '说法正确', '晶体',
                    '强电解质', 'AlCl3', '溶液', '共价化合物', '固体', '作为']
    neo4j_db = connect_db()
    generate_recommend_set(keyword_list, db=neo4j_db, subject="化学", row_limit=5)
    neo4j_db.close()
