"""PostgreSQL database backend for the Personal AI Assistant."""
from __future__ import annotations
import os

def _database_url():
    url=os.getenv("DATABASE_URL","").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required.")
    return url


class PostgresConnection:
    def __init__(self,dsn):
        import psycopg
        self._conn=psycopg.connect(dsn)
    def __enter__(self):
        self._conn.__enter__()
        return self
    def __exit__(self,exc_type,exc,tb):
        return self._conn.__exit__(exc_type,exc,tb)
    def execute(self,sql,params=None):
        return self._conn.execute(sql.replace("?", "%s"), params or ())
    def executemany(self,sql,seq):
        with self._conn.cursor() as cur:
            return cur.executemany(sql.replace("?", "%s"),seq)
    def close(self):
        return self._conn.close()

def connect():
    return PostgresConnection(_database_url())
