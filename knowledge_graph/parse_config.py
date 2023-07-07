import json
import os


class GlobalConfig:
    def __init__(self, config_path, encoding):
        self.config_path = config_path
        self.encoding = encoding
        with open(config_path, 'r', encoding=encoding) as f:
            self.config_json = json.load(f)

    def doc_dir(self):
        try:
            return self.config_json["doc_dir"]
        except KeyError:
            raise Exception("Fail to parse global config, "
                            "\"doc_dir\" have not been set yet")

    def subject(self):
        try:
            return self.config_json["subject"]
        except KeyError:
            raise Exception("Fail to parse global config, "
                            "\"subject\" have not been set yet")

    def ignored_doc_patterns(self):
        try:
            return self.config_json["ignored_doc_patterns"]
        except KeyError:
            raise Exception("Fail to parse global config, "
                            "\"ignored_doc_patterns\" have not been set yet")

    def doc_config_path(self):
        try:
            return self.config_json["doc_config_path"]
        except KeyError:
            raise Exception("Fail to parse global config, "
                            "\"doc_config_path\" have not been set yet")

    def get_doc_configs(self):
        file_names = os.listdir(self.config_path())
        doc_configs = []
        for file_name in file_names:
            doc_configs.append(DocConfig(file_name, self.encoding))
        return doc_configs


class DocConfig:
    def __init__(self, config_path, encoding):
        self.config_path = config_path
        self.encoding = encoding
        with open(config_path, 'r', encoding=encoding) as f:
            self.config_json = json.load(f)

    def config_name(self):
        try:
            return self.config_json["config_name"]
        except KeyError:
            raise Exception("Fail to parse doc config, "
                            "\"config_name\" have not been set yet")

    def file_pattern(self):
        try:
            return self.config_json["file_pattern"]
        except KeyError:
            raise Exception("Fail to parse doc config, "
                            "\"file_pattern\" have not been set yet")

    def subject(self):
        try:
            return self.config_json["subject"]
        except KeyError:
            raise Exception("Fail to parse doc config, "
                            f"path: {self.config_path}"
                            "\"subject\" have not been set yet")

    def title_list(self):
        try:
            return self.config_json["title_list"]
        except KeyError:
            raise Exception("Fail to parse doc config, "
                            f"path: {self.config_path}"
                            "\"titlee_list\" have not been set yet")

    def control_flow(self):
        try:
            return self.config_json["control_flow"]
        except KeyError:
            raise Exception("Fail to parse doc config, "
                            f"path: {self.config_path}"
                            "\"control_flow\" have not been set yet")
