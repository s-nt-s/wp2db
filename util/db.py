import os
import re
import sqlite3
from subprocess import DEVNULL, STDOUT, check_call

import yaml
from bunch import Bunch

re_select = re.compile(r"^\s*select\b")


def build_result(c, to_tuples=False, to_bunch=False):
    results = c.fetchall()
    if len(results) == 0:
        return results
    if isinstance(results[0], tuple) and len(results[0]) == 1:
        return [a[0] for a in results]
    if to_tuples:
        return results
    cols = [(i, col[0]) for i, col in enumerate(c.description)]
    n_results = []
    for r in results:
        d = {}
        for i, col in cols:
            d[col] = r[i]
        if to_bunch:
            d = Bunch(**d)
        n_results.append(d)
    return n_results


class DBLite:
    def __init__(self, file):
        self.file = file
        self.con = sqlite3.connect(file)
        self.cursor = self.con.cursor()
        self.tables = {}
        self.load_tables()

    def execute(self, sql_file):
        with open(sql_file, 'r') as schema:
            qry = schema.read()
            self.cursor.executescript(qry)
            self.con.commit()
            if "CREATE TABLE" in qry.upper():
                self.load_tables()

    def load_tables(self):
        self.tables = {}
        for t in self.select("SELECT name FROM sqlite_master WHERE type='table'"):
            self.cursor.execute("select * from "+t+" limit 0")
            self.tables[t] = tuple(col[0] for col in self.cursor.description)

    def insert(self, table, **kargv):
        ok_keys = [k.upper() for k in self.tables[table]]
        keys = []
        vals = []
        for k, v in kargv.items():
            if k.upper() in ok_keys and v is not None and not(isinstance(v, str) and len(v) == 0):
                keys.append(k)
                vals.append(v)
        sql = "insert into %s (%s) values (%s)" % (
            table, ", ".join(keys), ("?," * len(vals))[:-1])
        self.cursor.execute(sql, vals)

    def commit(self):
        self.con.commit()

    def close(self):
        self.con.commit()
        self.cursor.close()
        self.con.execute("VACUUM")
        self.con.commit()
        self.con.close()

    def select(self, sql, to_bunch=False, to_tuples=False):
        sql = sql.strip()
        if not sql.lower().startswith("select"):
            sql = "select * from "+sql
        self.cursor.execute(sql)
        r = build_result(self.cursor, to_bunch=to_bunch, to_tuples=to_tuples)
        return r

    def get_sql_table(self, table):
        sql = "SELECT sql FROM sqlite_master WHERE type='table' AND name=?"
        self.cursor.execute(sql, (table,))
        sql = self.cursor.fetchone()[0]
        return sql

    def size(self, file=None, suffix='B'):
        file = file or self.file
        num = os.path.getsize(file)
        for unit in ('', 'K', 'M', 'G', 'T', 'P', 'E', 'Z'):
            if abs(num) < 1024.0:
                return ("%3.1f%s%s" % (num, unit, suffix))
            num /= 1024.0
        return ("%.1f%s%s" % (num, 'Yi', suffix))

    def zip(self):
        zip = os.path.splitext(self.file)[0]+".7z"
        if os.path.isfile(zip):
            os.remove(zip)
        cmd = "7z a %s %s" % (zip, self.file)
        check_call(cmd.split(), stdout=DEVNULL, stderr=STDOUT)
        return self.size(zip)