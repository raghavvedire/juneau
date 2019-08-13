import pandas as pd
from py2neo import Graph, Node, Relationship, cypher, NodeMatcher
import base64

class Store_Provenance:

    def __connect2gdb(self):
        graph = Graph("http://neo4j:yizhang@localhost:7474/db/data")
        graph.delete_all()
        return graph

    def __init__(self, postgres_eng, graph_eng):
        self.graph_db = graph_eng #self.__connect2gdb()
        self.postgres_eng = postgres_eng
        self.code_dict = {}
        self.__fetch_code_dict()


    def __initialize_code_dict(self):

        try:
            query1 = "DROP SCHEMA IF EXISTS nb_provenance CASCADE;"
            query2 = "CREATE SCHEMA nb_provenance;"
            query3 = "CREATE TABLE nb_provenance.code_dict (code VARCHAR(1000), cell_id INTEGER);"

            try:
                self.postgres_eng.execute(query1)
            except:
                print("store provenance: DROP PROVENANCE SCHEMA FAILED!\n")

            try:
                self.postgres_eng.execute(query2)
                self.postgres_eng.execute(query3)
            except:
                print("store provenance: CREATE PROVENANCE SCHEMA FAILED\n")

            return True
        except:
            print("store provenance: Connecting Database Failed!\n")
            return False

    def __fetch_code_dict(self):
        try:
            code_table = pd.read_sql_table('code_dict', self.postgres_eng, schema = 'nb_provenance')
            for index, row in code_table.iterrows():
                self.code_dict[row['code']] = int(row['cell_id'])
            return True
        except:
            print("store provenance: Reading Code Table Failed!\n")
            return False

    def store_code_dict(self):
        dict_store = {'code':[], 'cell_id': []}
        for i in self.code_dict.keys():
            dict_store['code'].append(i)
            dict_store['cell_id'].append(self.code_dict[i])
        dict_store_code = pd.DataFrame.from_dict(dict_store)
        dict_store_code.to_sql('code_dict', self.postgres_eng, schema = 'nb_provenance', if_exists = 'replace')
        return True

    def add_cell(self, code, prev_node, var, cell_id, nb_name):

        bcode = str(base64.b64encode(bytes(code,'utf-8')))
        matcher = NodeMatcher(self.graph_db)
        if bcode in self.code_dict:
            current_cell = matcher.match("Cell", source_code = bcode).first()
        else:
            if len(list(self.code_dict.values())) != 0:
                max_id = max(list(self.code_dict.values()))
            else:
                max_id = 0
            current_cell = Node('Cell', name = 'cell_' + str(max_id + 1), source_code = bcode)
            self.graph_db.create(current_cell)
            self.graph_db.push(current_cell)

            if prev_node != None:
                cell_edge = Relationship(prev_node, 'Successor', current_cell)
                self.graph_db.create(cell_edge)
                self.graph_db.push(cell_edge)
                cell_edge2 = Relationship(current_cell, 'Parent', prev_node)
                self.graph_db.create(cell_edge2)
                self.graph_db.push(cell_edge2)

            self.code_dict[bcode] = max_id + 1

        var_name = str(cell_id) + "_" + var + "_" + nb_name

        current_var = matcher.match("Var", name = var_name).first()

        if current_var is None:
            current_var = Node('Var', name = var_name)

            self.graph_db.create(current_var)
            self.graph_db.push(current_var)

            edge = Relationship(current_cell, 'Contains', current_var)
            edge2 = Relationship(current_var, 'Containedby', current_cell)
            self.graph_db.create(edge)
            self.graph_db.push(edge)
            self.graph_db.create(edge2)
            self.graph_db.push(edge2)

        return current_cell