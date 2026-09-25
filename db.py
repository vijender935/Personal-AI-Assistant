"""Database backend with SQLite for local development and PostgreSQL for Render persistence."""
from __future__ import annotations
import os,sqlite3
from pathlib import Path
DATABASE_URL=os.getenv("DATABASE_URL","").strip()
def using_postgres(): return bool(DATABASE_URL)
def _pg_sql(sql): return sql.replace("?","%s")
class PostgresConnection:
    def __init__(self,dsn):
        import psycopg
        self._conn=psycopg.connect(dsn)
    def __enter__(self): self._conn.__enter__(); return self
    def __exit__(self,exc_type,exc,tb): return self._conn.__exit__(exc_type,exc,tb)
    def execute(self,sql,params=None): return self._conn.execute(_pg_sql(sql),params or ())
    def executemany(self,sql,seq): return self._conn.executemany(_pg_sql(sql),seq)
    def close(self): return self._conn.close()
def connect(path:Path|str|None=None):
    if using_postgres(): return PostgresConnection(DATABASE_URL)
    target=path if path is not None else os.getenv("AGENT_DB","data/agent_memory.db")
    return sqlite3.connect(target)
