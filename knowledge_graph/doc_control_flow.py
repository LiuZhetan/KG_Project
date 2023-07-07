import sys
from knowledge_graph.parse_config import DocConfig


class DocControlFlow:
    def __init__(self, doc_config: DocConfig):
        self.__control_flow_json = doc_config.control_flow()
        self.doc_config_path = doc_config.config_path

    def get_control_signs(self, sign_type: str):
        try:
            return [item["match_pair"] for item in self.__control_flow_json[sign_type]]
        except KeyError:
            sys.stderr.write(f"{sign_type} signs for doc config file \"{self.doc_config_path}\" "
                             f" is not set")
            return []
