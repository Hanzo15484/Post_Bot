import sqlite3
import threading

DB_PATH = "Post.db"
_lock = threading.Lock()


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path

    def query(self, sql, params=(), fetch=False, many=False):
        with _lock:
            conn = sqlite3.connect(self.path)
            cur = conn.cursor()

            if many:
                cur.executemany(sql, params)
            else:
                cur.execute(sql, params)

            data = None
            if fetch:
                data = cur.fetchall()

            conn.commit()
            conn.close()
            return data


db = Database()
