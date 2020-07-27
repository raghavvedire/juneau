# Copyright 2020 Juneau
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
TODO: Explain what this module does.
"""

import ast
import queue

import networkx as nx
from py2neo import Graph
from sqlalchemy import create_engine

from juneau import config
from juneau.utils.funclister import FuncLister

from sqlalchemy.orm import sessionmaker


def create_tables_as_needed(engine, eng):
    """
    Creates the PostgreSQL schema and Juneau's metadata tables, if necessary.
    """
    # Open the session
    Session = sessionmaker(bind=engine)
    session = Session()

    eng.execute(f"create schema if not exists {config.sql_dbs};")
    eng.execute(f"create schema if not exists {config.sql_graph};")
    eng.execute(f"create schema if not exists {config.sql_provenance};")

    eng.execute(
        f"CREATE TABLE IF NOT EXISTS {config.sql_graph}.dependen (view_id character varying(1000), view_cmd text);"
    )

    eng.execute(
        f"CREATE TABLE IF NOT EXISTS {config.sql_graph}.line2cid (view_id character varying(1000), view_cmd text);"
    )

    eng.execute(
        f"CREATE TABLE IF NOT EXISTS {config.sql_graph}.lastliid (view_id character varying(1000), view_cmd text);"
    )

    session.commit()
    session.close()


def connect2db(dbname):
    """
    Connects to the PostgreSQL instance, creating it if necessary.
    """
    try:
        engine = create_engine(
            f"postgresql://{config.sql_name}:{config.sql_password}@{config.sql_host}/{dbname}"
        )
        eng = engine.connect()
        create_tables_as_needed(engine, eng)
        return eng
    except:
        engine = create_engine(
            f"postgresql://{config.sql_name}:{config.sql_password}@{config.sql_host}/"
        )
        eng = engine.connect()
        eng.connection.connection.set_isolation_level(0)
        eng.execute(f"create database {dbname};")

        create_tables_as_needed(engine, eng)
        eng.connection.connection.set_isolation_level(1)

        engine = create_engine(
            f"postgresql://{config.sql_name}:{config.sql_password}@{config.sql_host}/{dbname}"
        )
        return engine.connect()


def connect2db_engine(dbname):
    """
    Connect to the PostgreSQL instance, creating it if necessary
    """
    try:
        engine = create_engine(
            f"postgresql://{config.sql_name}:{config.sql_password}@{config.sql_host}/{dbname}",
            isolation_level="AUTOCOMMIT"
        )

        eng = engine.connect()
        create_tables_as_needed(engine, eng)
        eng.close()

        return engine
    except:
        engine = create_engine(
            f"postgresql://{config.sql_name}:{config.sql_password}@{config.sql_host}/"
        )
        eng = engine.connect()
        eng.connection.connection.set_isolation_level(0)
        eng.execute("create database {dbname};")

        create_tables_as_needed(engine, eng)
        eng.connection.connection.set_isolation_level(1)
        eng.close()

        engine = create_engine(
            f"postgresql://{config.sql_name}:{config.sql_password}@{config.sql_host}/{dbname}",
            isolation_level="AUTOCOMMIT"
        )
        return engine


def connect2gdb():
    """
    Connect to Neo4J.
    """
    return Graph(f"http://{config.neo_name}:{config.neo_password}@{config.neo_host}/db/{config.neo_db}")


def fetch_all_table_names(schema, eng):
    """
    Finds all tables within a given schema.
    """
    tables = eng.execute(
        f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}';"
    )
    return [table[0] for table in tables]


def fetch_all_views(eng):
    """
    Finds all views.
    """
    tables = eng.execute("SELECT table_name from information_schema.views;")
    return [table[0] for table in tables if "exp_view_table" in table[0]]


def last_line_var(varname, code):
    """
    Finds the last line in the code where a variable was assigned.
    """
    code = code.split("\n")
    ret = 0
    for idx, line in enumerate(code, 1):
        if "=" in line and varname in line.split("=")[0]:
            ret = idx
    return ret


def parse_code(all_code):
    """
    Parses code within a Jupyter notebook cell.
    """
    test = FuncLister()
    tree = ast.parse(all_code)
    test.visit(tree)
    return test.dependency


def generate_graph(dependency):
    """
    Generates a dependency graph using the library networkx.
    """
    G = nx.DiGraph()
    for i in dependency.keys():
        left = dependency[i][0]
        right = list(set(dependency[i][1]))

        left_node = []
        for ele in left:
            if type(ele) is tuple:
                ele = ele[0]
            left_node.append("var_" + ele + "_" + str(i))

        for ele in left:
            if type(ele) is tuple:
                ele = ele[0]

            new_node = "var_" + ele + "_" + str(i)
            G.add_node(new_node, line_id=i, var=ele)

            for dep, ename in right:
                candidate_list = G.nodes
                rankbyline = []
                for cand in candidate_list:
                    if G.nodes[cand]["var"] == dep:
                        if cand in left_node:
                            continue
                        rankbyline.append((cand, G.nodes[cand]["line_id"]))
                rankbyline = sorted(rankbyline, key=lambda d: d[1], reverse=True)

                if len(rankbyline) == 0:
                    if dep not in ["np", "pd"]:
                        candidate_node = "var_" + dep + "_" + str(1)
                        G.add_node(candidate_node, line_id=1, var=dep)
                    else:
                        candidate_node = dep
                        G.add_node(candidate_node, line_id=1, var=dep)

                else:
                    candidate_node = rankbyline[0][0]

                G.add_edge(new_node, candidate_node, label=ename)

    return G


def pre_vars(node, graph):
    """
    TODO: Describe what this does.
    FIXME: Duplicated code.
    """
    node_list = {}
    q = queue.Queue()
    q.put(node)
    dep = 0
    while not q.empty():
        temp_node = q.get()
        dep = dep + 1
        if temp_node not in node_list:
            node_list[temp_node] = {}
        predecessors = graph.successors(temp_node)
        for n in predecessors:
            q.put(n)
            node_list[temp_node][n] = "+" + graph[temp_node][n]["label"]
            successors = graph.predecessors(n)
            for s in successors:
                if s in node_list:
                    if n not in node_list:
                        node_list[n] = {}
                    node_list[n][s] = "-" + graph[s][n]["label"]
        if dep > 100:
            break
    return node_list
