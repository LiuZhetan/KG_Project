import json

from flask import Flask, request

from knowledge_graph.keyword import extract_keyword
from knowledge_graph.kg_managment import query_knowledge_by_id, get_keyword_by_id, get_knowledge_table, \
    delete_leaf_knowledge, delete_keyword, get_parent_list
from recommender.kf_ikf import generate_recommend_set
from graph_database.connect import connect_db

app = Flask(__name__)
db = connect_db()


def result2json(result_dict: dict):
    res = {}
    for key, df in result_dict.items():
        res[key] = df.to_json()
    return res


@app.route("/question/")
def extract_knowledge():
    question = request.args.get('question', '')
    row_limit = request.args.get('row_limit', '')
    subject = request.args.get('subject', '')
    if question == '' or row_limit == '' or subject == '':
        return json.dumps({"return_result": False, "wrong_info": "query parameter is incorrect"})
    else:
        row_limit = int(row_limit)
        keyword_set = extract_keyword(question)
        result_dict = generate_recommend_set(list(keyword_set),
                                             subject=subject,
                                             db=db,
                                             row_limit=row_limit)
        # 构造返回结构
        return json.dumps({"return_result": True, "result": result2json(result_dict)})


@app.route("/query_by_id/")
def handle_query_id():
    id = request.args.get('id', '')
    type = request.args.get('type', 'knowledge')
    if type == 'knowledge':
        res = query_knowledge_by_id(db, int(id))
    elif type == 'keyword':
        res = get_keyword_by_id(db, int(id))
    else:
        return json.dumps({"return_result": False})
    return json.dumps({"return_result": True, "result": res.to_json()})


@app.route("/query_by_level/")
def handle_query_level():
    level = request.args.get('level', '')
    subject = request.args.get('subject', '')
    try:
        res = get_knowledge_table(db, subject, int(level))
        return json.dumps({"return_result": True, "result": res.to_json()})
    except:
        return json.dumps({"return_result": False})


@app.route("/query_parent/")
def handle_query_parent():
    id = request.args.get('id', '')
    type = request.args.get('type', 'knowledge')
    if type == 'knowledge':
        res = get_parent_list(db, int(id))
    elif type == 'keyword':
        res = get_parent_list(db, int(id))
    else:
        return json.dumps({"return_result": False})
    return json.dumps({"return_result": True, "result": res.to_json()})


@app.route("/delete/")
def handle_delete():
    id = request.args.get('id', '')
    type = request.args.get('type', 'knowledge')
    if type == 'knowledge':
        res = delete_leaf_knowledge(db, int(id))
    elif type == 'keyword':
        res = delete_keyword(db, int(id))
    else:
        return json.dumps({"return_result": False})
    return json.dumps({"return_result": True, "result": res})
