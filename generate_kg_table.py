import argparse
import base64
import os
import sys
import re
import pandas
import mammoth
import pandas as pd
from re import Match

from bs4 import BeautifulSoup

from knowledge_graph.read_images import image2text
from knowledge_graph.keyword import extract_keyword
from knowledge_graph.parse_config import DocConfig, GlobalConfig
from knowledge_graph.doc_control_flow import DocControlFlow


# 标题段落
# ignored_pattern = ['第.+章\s', '答案\s', '微专题']  # 匹配到此模式时忽略该段落
# skip_pattern = ['递进题组·练能力', '题组.\s']  # 跳过当前段落以及接下来的段落
# stop_pattern = ['易错警示', '练后反思', '规律方法']  # 匹配到其中的模式时停止
# end_pattern = ['真题演练\s明确考向', '课时精练\s巩固提高', '.*专题精.']  # 结束文档树构建

class_map = {'paragraph': 0, 'img': 1, 'table': 2}
paragraph_set = {'h2', 'p', 'h3'}

temp_path = 'temp'


class IntegerGenerator:
    def __init__(self):
        self.x = 0

    def next(self):
        self.x += 1
        return self.x


class DocumentTreeNode:
    def __init__(self, title_id, title_name: str, title_level: int):
        # title_level必须为一个正整数
        assert title_level >= 0
        self.title_id = title_id
        self.title_name: str = title_name  # 标题名字
        self.title_level: int = title_level  # 标题层级，是一个正整数
        self.sub_nodes = []  # 孩子节点，为当前标题下的子标题
        self.paragraphs = []  # 当前标题下的正文段的字符串列表
        self.picture_texts = []  # 内容为{paragraph_index, picture_index}的列表
        self.table_texts = []  # 内容为{paragraph_index, table_index}的列表

    def to_dict(self):
        result = dict()
        result['title_name'] = self.title_name
        result['title_level'] = self.title_level
        nodes = []
        for node in self.sub_nodes:
            nodes.append(node.to_dict())
        result['sub_nodes'] = nodes
        result['paragraphs'] = self.paragraphs
        return result

    def attach_text(self, tag_class, text):
        if tag_class in paragraph_set:
            self.paragraphs.append(text)
        elif tag_class == 'img':
            self.picture_texts.append(text)
        elif tag_class == 'table':
            self.table_texts.append(text)
        else:
            raise Exception(f"Unidentified class: {tag_class}")


class Neo4jTables:
    def __init__(self):
        self.knowledge_table = pandas.DataFrame(columns=['knowledge_id', 'name', 'level', 'subject'])
        self.keyword_table = pandas.DataFrame(columns=['keyword_id', 'content', 'subject'])
        self.knowledge_relations = pandas.DataFrame(columns=['knowledge_id_from', 'knowledge_id_to'])
        self.keyword_relations = pandas.DataFrame(columns=['keyword_id', 'knowledge_id', 'count'])

    def from_tables(self, title_table, keyword_table, title_relations, keyword_relations):
        self.knowledge_table = title_table
        self.keyword_table = keyword_table
        self.knowledge_relations = title_relations
        self.keyword_relations = keyword_relations

    def add_node(self, row, node_type='knowledge'):
        if node_type == 'knowledge':
            self.knowledge_table.loc[len(self.knowledge_table)] = row
        elif node_type == 'keyword':
            self.keyword_table.loc[len(self.keyword_table)] = row
        else:
            raise KeyError

    def add_relation(self, row, relation_type='knowledge'):
        if relation_type == 'knowledge':
            self.knowledge_relations.loc[len(self.knowledge_relations)] = row
        elif relation_type == 'keyword':
            self.keyword_relations.loc[len(self.keyword_relations)] = row
        else:
            raise KeyError

    def save(self, path):
        self.knowledge_table.to_csv(os.path.join(path, 'knowledge_table.csv'), index=False)
        self.keyword_table.to_csv(os.path.join(path, 'keyword_table.csv'), index=False)
        self.knowledge_relations.to_csv(os.path.join(path, 'knowledge_relations.csv'), index=False)
        self.keyword_relations.to_csv(os.path.join(path, 'keyword_relations.csv'), index=False)

    def append(self, other_tables):
        self.knowledge_table = pd.concat([self.knowledge_table, other_tables.knowledge_table])
        self.keyword_table = pd.concat([self.keyword_table, other_tables.keyword_table])
        self.knowledge_relations = pd.concat([self.knowledge_relations, other_tables.knowledge_relations])
        self.keyword_relations = pd.concat([self.keyword_relations, other_tables.keyword_relations])


def match_title(text: str, title_list: []):
    """
    根据配置的模式字典匹配标题
    :param text: 段落文字
    :return: 正数为标题的层级，-1表示段落
    """
    pattern_list = [item["match_pair"] for item in title_list]
    res = find_pattern(text, pattern_list)
    if res is not None:
        (match_res, index) = res
        return match_res, title_list[index]
    else:
        return None


def parse_title_pattern(raw_text: str, match_result: Match, title_item: dict):
    """
    解析title模式，返回title_level和经过加工的形成的知识点文字
    :param raw_text:
    :param match_result:
    :param title_item:
    :return: title_level, knowledge_text
    """
    title_level = title_item["level"]
    try:
        cut_prefix = title_item["cut_prefix"]
    except KeyError:
        cut_prefix = False
    start, end = match_result.span()
    knowledge_text = raw_text[:start] + raw_text[end:] if cut_prefix else raw_text
    return title_level, knowledge_text


def extract_pictures(doc, result_path):
    # result_path为存放word文档图片的地方
    dict_rel = doc.part._rels
    count = 0
    for i in range(len(dict_rel)):
        rel = dict_rel[f"rId{i + 1}"]
        if "image" in rel.target_ref:
            if not os.path.exists(result_path):
                os.makedirs(result_path)
            with open(f'{result_path}/picture{count}.png', "wb") as f:
                f.write(rel.target_part.blob)
            count += 1
    return count


def _para_to_string(tag):
    assert tag.name in paragraph_set
    res = ''
    for s in tag.stripped_strings:
        res += s
    return res


def _img_to_string(tag):
    assert tag.name == 'img'
    base64_str = tag['src']
    head, context = base64_str.split(',')
    img_data = base64.b64decode(context)
    with open(".\\temp\\temp.jpg", 'wb') as f:
        f.write(img_data)
    return image2text(".\\temp\\temp.jpg")


def _table_to_string(tag):
    assert tag.name == 'table'
    res = ''
    for row in tag.contents:
        for cel in row.contents:
            if cel.text == '':
                continue
            if cel.contents[0].name == 'img':
                res += _img_to_string(cel.contents[0]) + ' '
            else:
                res += _para_to_string(cel.contents[0]) + ' '
        res += ','
    return res


def get_tag_text(tag):
    """
    解析html标签，返回标签名字和由对应标签转化的字符串
    :param tag: html标签
    :return: tag_name, tag_text
    """
    tag_name = tag.name
    if tag_name in paragraph_set:
        return tag_name, _para_to_string(tag)
    elif tag_name == 'img':
        return tag_name, _img_to_string(tag)
    elif tag_name == 'table':
        return tag_name, _table_to_string(tag)


def match_pattern(text, pattern_set):
    for pattern in pattern_set:
        if re.match(pattern, text):
            return True
    return False


def search_pattern(text, pattern_set):
    for pattern in pattern_set:
        if re.search(pattern, text):
            return True
    return False


def find_pattern(text: str, match_pair_list: [dict]):
    """
    text是否匹配match_pair_list中的一个模式
    :param text: 目标字符串
    :param match_pair_list: 匹配模式列表，形式为[{
      "match_mode": ...,
      "pattern":...
    },......]
    :return: 匹配结果,索引
    """
    for i, pair in enumerate(match_pair_list):
        try:
            match_mode = pair["match_mode"]
            res = None
            if match_mode == "match_prefix":
                res = (re.match(pair["pattern"], text), i)
            elif match_mode == "search_pattern":
                res = (re.search(pair["pattern"], text), i)
            if res[0] is not None:
                return res
        except KeyError:
            raise Exception(f"pair is not set properly, pair: {pair}")
    return None


def paras_docx(file_path: str,
               root_node: DocumentTreeNode,
               subject: str,
               doc_config: DocConfig,
               title_id_generator: IntegerGenerator,
               keyword_id_generator: IntegerGenerator,
               neo4j_tables: Neo4jTables = None,
               keyword2id: dict = None,
               ):
    """
    解析一个文档文件，返回以文档树根节点和neo4j的关系表
    :param file_path:需要解析的文档路径
    :param root_node:初始化的根节点
    :param subject: 学科名称
    :param doc_config:文档解析规则配置
    :param title_id_generator:全局的title_id生成器
    :param keyword_id_generator:全局的keyword_id生成器
    :param neo4j_tables:Neo4jTables对象，如果为None则新建一个，否则在传入的Neo4jTables对象后怎加行数
    :param keyword2id:全局的keyword字典，如果为None则新建一个
    :param relation_set:全局的关系字典，如果为None则新建一个
    :return:root_node，tables
    """
    # docx文件转化为html
    with open(file_path, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file)
        html = result.value  # The generated HTML
    soup = BeautifulSoup(html, 'html.parser')

    title_list = doc_config.title_list()
    control_flow = DocControlFlow(doc_config)
    ignore_signs = control_flow.get_control_signs("ignore_signs")
    skip_signs = control_flow.get_control_signs("skip_signs")
    stop_signs = control_flow.get_control_signs("stop_signs")
    end_signs = control_flow.get_control_signs("end_signs")

    # title表
    if neo4j_tables is None:
        neo4j_tables = Neo4jTables()

    # title_id_generator = IntegerGenerator()
    # keyword_id_generator = IntegerGenerator()
    # keyword2id = {}
    if keyword2id is None:
        keyword2id = {}

    node_stack = [root_node]
    skip_sign = False
    for tag in soup.contents:
        tag_class, tag_text = get_tag_text(tag)
        if tag_text == '' or find_pattern(tag_text, ignore_signs) is not None:
            # 标签被忽略
            continue
        if find_pattern(tag_text, end_signs) is not None:
            # 终止解析
            break
        if find_pattern(tag_text, skip_signs) is not None:
            # 跳过当前标签和接下来的标签，
            # 直到遇到stop控制模式或者匹配到同级别/更高级别的标题
            skip_sign = True
        if find_pattern(tag_text, stop_signs) is not None:
            skip_sign = False

        match_result = match_title(tag_text, title_list)
        if match_result is not None:
            # 匹配到了标题段落
            match_result, title_item = match_result
            current_level, knowledge_text = parse_title_pattern(tag_text, match_result, title_item)

            if node_stack[-1].title_level >= current_level:
                skip_sign = False
            if skip_sign:
                continue

            # 找到当前的父节点
            while node_stack[-1].title_level >= current_level:
                node_stack.pop()
                skip_sign = False
            parent_node = node_stack[-1]

            # 长度限制
            try:
                length_limit = title_item["length_limit"]
            except KeyError:
                length_limit = float("inf")
            if len(knowledge_text) > length_limit:
                # 知识点长度超过限制
                sys.stderr.write(f"knowledge_text: '{knowledge_text}' is too long")
                continue

            # 隐藏节点
            try:
                hidden: bool = title_item["hidden"]
            except KeyError:
                hidden: bool = False
            if hidden:
                # 隐藏节点
                continue

            new_id = title_id_generator.next()
            new_node = DocumentTreeNode(new_id, knowledge_text, current_level)
            parent_node.sub_nodes.append(new_node)
            node_stack.append(new_node)

            # 更新title_table和title_relations
            neo4j_tables.add_node([new_id, knowledge_text, current_level, subject], 'knowledge')
            neo4j_tables.add_relation([new_id, parent_node.title_id], 'knowledge')

        elif skip_sign:
            continue
        else:
            # 匹配到了正文段落
            node_stack[-1].attach_text(tag_class, tag_text)
            # 没有消除重复
            keyword_set = extract_keyword(tag_text)
            # 更新keyword_table和keyword_relation
            for keyword in keyword_set:
                try:
                    # keyword已经创建
                    keyword_id = keyword2id[keyword]
                except KeyError:
                    # 新的keyword
                    keyword_id = keyword_id_generator.next()
                    keyword2id[keyword] = keyword_id
                    neo4j_tables.add_node([keyword_id, keyword, subject], 'keyword')
                neo4j_tables.add_relation([keyword_id, node_stack[-1].title_id, 1], 'keyword')
    return root_node, neo4j_tables


def build_KG(doc_dir: str,
             subject: str,
             ignored_doc_patterns: [],
             doc_config_list: [DocConfig],
             parse_filename_fn=None):
    """
    构建知识图谱所需要的文件并返回知识树
    :param doc_dir: 存放docx文档的目录
    :param subject: 学科名称
    :param ignored_doc_patterns: 被忽略的文档的匹配模式
    :param doc_config_list:文档配置列表
    :param parse_filename_fn: 为每个doc文件生成分支节点的函数
    :return:文档知识树的根节点和构建KG所需的关系报表
    """
    # 匹配文件名称的模式列表
    match_file_list = [doc_config.file_pattern()["match_pair"]
                       for doc_config in doc_config_list]
    # 全局的id生成器
    title_id_generator = IntegerGenerator()
    keyword_id_generator = IntegerGenerator()
    # 存储构建KG需要的表
    neo4j_tables = Neo4jTables()
    # keyword和id的对应关系，keyword是唯一的，用集合存储
    keyword2id = {}
    # 用于关系计数
    # relation_set = {}
    # 生成文档树根节点
    document_tree_root = DocumentTreeNode(title_id_generator.next(), subject, 0)
    neo4j_tables.add_node([document_tree_root.title_id, subject, 0, subject], 'knowledge')
    for filename in os.listdir(doc_dir):
        # if ignore_file(filename):
        #     continue
        if find_pattern(filename, ignored_doc_patterns) is not None:
            # 文件被忽略
            continue
        res = find_pattern(filename, match_file_list)
        if res is not None:
            # 文件被被捕获
            # branch_node = DocumentTreeNode

            # if filename.endswith('.docx'):
            # res = filename[10:].replace('\u3000', ' ').split(' ')
            # chapter_key = res[0]
            # title = res[-1].split('.')[0]
            _, doc_config_index = res
            doc_config = doc_config_list[doc_config_index]
            # 对于每一个文件生成新得到节点
            new_id = title_id_generator.next()
            # branch_name = chapter_dict[chapter_key]
            branch_name = filename if parse_filename_fn is None else parse_filename_fn(filename)
            branch_node = DocumentTreeNode(new_id, branch_name, 1)
            document_tree_root.sub_nodes.append(branch_node)
            neo4j_tables.add_node([new_id, branch_name, 1, subject], 'knowledge')
            neo4j_tables.add_relation([new_id, document_tree_root.title_id], 'knowledge')
            path = os.path.join(doc_dir, filename)
            paras_docx(path, branch_node, subject,
                       doc_config,
                       title_id_generator,
                       keyword_id_generator,
                       neo4j_tables,
                       keyword2id,
                       )
    # keyword relation有重复，去重
    unique_table = neo4j_tables.keyword_relations \
        .groupby(by=["keyword_id", "knowledge_id"]) \
        .count() \
        .reset_index()
    neo4j_tables.keyword_relations = unique_table
    return document_tree_root, neo4j_tables


chapter_dict = {'第一章': '从化学到实验', '第二章': '化学物质及其变化', '第三章': '金属及其化合物',
                '第四章': '非金属及其化合物', '第五章': '物质结构、元素周期律', '第六章': '化学反应与能量',
                '第七章': '化学反应速率和化学平衡', '第八章': '水溶液中的离子平衡', '第九章': '有机化合物',
                '第十章': '化学实验热点', '第十一章': '有机化学基础(选考)', '第十二章': '物质结构与性质(选考)'}


def parse_filename(filename: str):
    res = filename[10:].replace('\u3000', ' ').split(' ')
    chapter_key = res[0]
    return chapter_dict[chapter_key]


parser = argparse.ArgumentParser()
parser.add_argument("--config_path", default="./config", type=str,
                    help="全局配置文件位置，以当前脚本位置为参照")
args = parser.parse_args()


if __name__ == '__main__':
    # 运行脚本生成构建知识图谱的数据
    config_path = args.config_path
    global_config = GlobalConfig(os.path.join(config_path, "global_config.json"), encoding="utf-8")
    doc_path = global_config.doc_dir()
    subject = global_config.subject()
    ignored_doc_patterns = global_config.ignored_doc_patterns()
    ignored_doc_patterns = [item["match_pair"] for item in ignored_doc_patterns]
    doc_config_path = global_config.doc_config_path()
    doc_config_list = []
    for doc_config_name in os.listdir(doc_config_path):
        doc_config_list.append(
            DocConfig(
                os.path.join(doc_config_path, doc_config_name),
                encoding='utf-8'
            )
        )
    root, tables = build_KG(doc_path, subject, ignored_doc_patterns, doc_config_list, parse_filename)
    tables.save('./csv')
