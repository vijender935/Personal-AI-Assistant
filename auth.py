import hashlib,hmac,os,secrets,time
from config import DB_PATH,ensure_directories
from db import connect,using_postgres
SESSION_TTL=int(os.getenv("SESSION_TTL",str(60*60*24*30)))
PASSWORD_ITERATIONS=310_000
def _hash_password(password,salt=None):
    if len(password)<8: raise ValueError("Password must contain at least 8 characters.")
    salt=salt or secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,PASSWORD_ITERATIONS)
    return "pbkdf2_sha256$%s$%s$%s"%(PASSWORD_ITERATIONS,salt.hex(),digest.hex())
def _verify_password(password,encoded):
    try:
        _,iterations,salt_hex,digest_hex=encoded.split("$"); actual=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt_hex),int(iterations)).hex()
        return hmac.compare_digest(actual,digest_hex)
    except (ValueError,TypeError): return False
def init_auth_db():
    ensure_directories()
    with connect(DB_PATH) as con:
        if using_postgres():
            con.execute("""CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at DOUBLE PRECISION NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        else:
            con.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT NOT NULL UNIQUE COLLATE NOCASE,name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires_at REAL NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)")
def create_user(name,email,password):
    name,email=name.strip(),email.strip().lower()
    if not name or "@" not in email: raise ValueError("Valid name and email are required.")
    password_hash=_hash_password(password)
    try:
        with connect(DB_PATH) as con:
            if using_postgres():
                row=con.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?) RETURNING id",(name,email,password_hash)).fetchone()
                return {"id":row[0],"name":name,"email":email}
            cur=con.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",(name,email,password_hash))
            return {"id":cur.lastrowid,"name":name,"email":email}
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower(): raise ValueError("An account with this email already exists.") from exc
        raise
def authenticate(email,password):
    email = email.strip().lower()
    with connect(DB_PATH) as con: row=con.execute("SELECT id,name,email,password_hash FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
    if not row or not _verify_password(password,row[3]): return None
    return {"id":row[0],"name":row[1],"email":row[2]}
def _cleanup_expired_sessions():
    with connect(DB_PATH) as con: con.execute("DELETE FROM auth_sessions WHERE expires_at <= ?",(time.time(),))
def create_session(user_id):
    _cleanup_expired_sessions(); raw=secrets.token_urlsafe(32); token_hash=hashlib.sha256(raw.encode()).hexdigest()
    with connect(DB_PATH) as con: con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(token_hash,user_id,time.time()+SESSION_TTL))
    return raw
def get_user(token):
    if not token:return None
    token_hash=hashlib.sha256(token.encode()).hexdigest()
    with connect(DB_PATH) as con: row=con.execute("SELECT u.id,u.name,u.email FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",(token_hash,time.time())).fetchone()
    return {"id":row[0],"name":row[1],"email":row[2]} if row else None
def revoke_session(token):
    with connect(DB_PATH) as con: con.execute("DELETE FROM auth_sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
