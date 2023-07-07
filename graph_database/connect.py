import json
from neo4j import GraphDatabase


with open('./config/db_config.json', 'r') as f:
    json_data = json.load(f)
url = json_data["url"]  # 远程Aura Neo4j地址
user = json_data["user"]
password = json_data["password"]
user_agent = json_data["user_agent"]    # VPN地址


class Neo4jDB:

    def __init__(self, uri, user, password, user_agent=None):
        self.driver = GraphDatabase.driver(uri, auth=(user, password), user_agent=user_agent)

    def close(self):
        self.driver.close()

    def print_greeting(self, message):
        with self.driver.session() as session:
            greeting = session.execute_write(self._create_and_return_greeting, message)
            print(greeting)

    @staticmethod
    def _create_and_return_greeting(tx, message):
        result = tx.run("CREATE (a:Greeting) "
                        "SET a.message = $message "
                        "RETURN a.message + ', from node ' + id(a)", message=message)
        return result.single()[0]


def connect_db():
    return Neo4jDB(url, user, password, user_agent)


if __name__ == "__main__":
    greeter = connect_db()
    # greeter.print_greeting("hello, world")
    greeter.close()
