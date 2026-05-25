"""
数据库操作模块
"""
import pymysql
import pymysql.cursors
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS


class Database:
    """MySQL 数据库连接管理"""
    _instance = None

    def __init__(self):
        self._conn = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def _connect(self):
        if self._conn is None or not self._conn.open:
            self._conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=10,
            )
        return self._conn

    def query(self, sql, params=None, fetch=True):
        """执行查询并返回结果"""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            if fetch:
                return cur.fetchall()
            return cur

    def query_one(self, sql, params=None):
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()

    def execute(self, sql, params=None):
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.lastrowid

    def execute_many(self, sql, params_list):
        conn = self._connect()
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)
            return cur.rowcount

    def insert(self, table, data):
        cols = ", ".join(f"`{k}`" for k in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})"
        return self.execute(sql, list(data.values()))

    def update(self, table, data, where, where_params=None):
        sets = ", ".join(f"`{k}` = %s" for k in data.keys())
        sql = f"UPDATE `{table}` SET {sets} WHERE {where}"
        params = list(data.values()) + (list(where_params) if where_params else [])
        return self.execute(sql, params)

    def delete(self, table, where, params=None):
        sql = f"DELETE FROM `{table}` WHERE {where}"
        return self.execute(sql, params)

    def begin(self):
        self._connect().begin()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()