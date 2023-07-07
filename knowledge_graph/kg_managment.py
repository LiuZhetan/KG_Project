import pandas as pd
from graph_database.connect import Neo4jDB, connect_db
from recommender.kf_ikf import records2dataframe


def query_knowledge_by_id(db: Neo4jDB, id: [int]):
    query_statement = "match (k:Knowledge) where k.knowledge_id in $id_list " \
                      "return k.knowledge_id as kn_id, k.name as name, " \
                      "k.level as level, k.subject as subject"
    id_list = id if isinstance(id, list) else [id]
    records, summary, keys = db.driver.execute_query(query_statement, id_list=id_list, database_="neo4j")
    return records2dataframe(records, keys)


def get_knowledge_table(db: Neo4jDB, subject: str, level: int = None):
    match_statement = "match (k:Knowledge) "
    return_statement = "return k.knowledge_id as kn_id, k.name as name, " \
                       "k.level as level, k.subject as subject"
    condition = f"where k.subject = $subject "
    if level is not None:
        condition += f"and k.level = $level "
        query_statement = match_statement + condition + return_statement
        records, summary, keys = db.driver.execute_query(query_statement,
                                                         subject=subject,
                                                         level=level,
                                                         database_="neo4j")
    else:
        query_statement = match_statement + condition + return_statement
        records, summary, keys = db.driver.execute_query(query_statement,
                                                         subject=subject,
                                                         database_="neo4j")
    return records2dataframe(records, keys, set_index="kn_id")


def get_keyword_table(db: Neo4jDB, subject: str):
    query_statement = "match (k:KeyWord) " \
                      "where k.subject = $subject " \
                      "return k.keyword_id as kw_id, k.content as content, " \
                      "k.subject as subject"
    records, summary, keys = db.driver. \
        execute_query(query_statement, subject=subject, database_="neo4j")
    return records2dataframe(records, keys, set_index="kw_id")


def get_keyword_by_id(db: Neo4jDB, id: [int]):
    query_statement = "match (k:KeyWord) " \
                      "where k.keyword_id in $id_list " \
                      "return k.keyword_id as kw_id, k.content as content, " \
                      "k.subject as subject"
    id_list = id if isinstance(id, list) else [id]
    records, summary, keys = db.driver. \
        execute_query(query_statement, id_list=id_list, database_="neo4j")
    return records2dataframe(records, keys, set_index="kw_id")


def get_parent_list(db: Neo4jDB, kn_id: int):
    query_statement = "match (s:Knowledge) -[:belong_to]-> (p:Knowledge)" \
                      "where s.knowledge_id = $kn_id " \
                      "return p.knowledge_id as kn_id, p.name as name, " \
                      "p.level as level, p.subject as subject"
    records, summary, keys = db.driver. \
        execute_query(query_statement, kn_id=kn_id, database_="neo4j")
    result = records2dataframe(records, keys, set_index="kn_id")
    try:
        kn_id = result.index[0]
    except IndexError:
        return result
    while len(records) > 0:
        records, summary, keys = db.driver. \
            execute_query(query_statement, kn_id=kn_id, database_="neo4j")
        temp_res = records2dataframe(records, keys, set_index="kn_id")
        try:
            kn_id = temp_res.index[0]
        except IndexError:
            return result
        result = pd.concat([result, temp_res])
    return result


def delete_leaf_knowledge(db: Neo4jDB, kn_id: int):
    query_statement = "match (s:Knowledge) -[:belong_to]-> (p:Knowledge)" \
                      "where p.knowledge_id = $kn_id " \
                      "return s.knowledge_id as kn_id, s.name as name, " \
                      "s.level as level, s.subject as subject"
    records, summary, keys = db.driver. \
        execute_query(query_statement, kn_id=kn_id, database_="neo4j")
    if len(records) > 0:
        return []
    else:
        # 删除知识点及其连接
        delete_statement = "MATCH (k:Knowledge) " \
                           "where k.knowledge_id = $kn_id " \
                           "detach delete k"
        _, summary, _ = db.driver.execute_query(delete_statement,
                                                kn_id=kn_id,
                                                database_="neo4j")
        counters = summary.counters
        return {
            "update": counters.contains_updates,
            "nodes_deleted": counters.nodes_deleted,
            "relationships_deleted": counters.relationships_deleted
        }


def delete_keyword(db: Neo4jDB, kw_id: int):
    delete_statement = "MATCH (k:KeyWord) where k.keyword_id = $kw_id detach delete k"
    _, summary, _ = db.driver.execute_query(delete_statement,
                                            kw_id=kw_id,
                                            database_="neo4j")
    counters = summary.counters
    return {
        "update": counters.contains_updates,
        "nodes_deleted": counters.nodes_deleted,
        "relationships_deleted": counters.relationships_deleted
    }


if __name__ == '__main__':
    # 测试管理模块的功能
    neo4j_bd = connect_db()
    res = query_knowledge_by_id(neo4j_bd, 2)
    # res = get_knowledge_table(neo4j_bd, "化学", 2)
    # res = get_keyword_table(neo4j_bd, "化学")
    # res = get_keyword_by_id(neo4j_bd, [2,3,4])
    # res = get_parent_list(neo4j_bd, 255)
    # res = delete_leaf_knowledge(neo4j_bd, 5)
    # res = delete_keyword(neo4j_bd, 5)
    neo4j_bd.close()
    # print(res)
