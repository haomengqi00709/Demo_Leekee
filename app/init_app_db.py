#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 pricing.db 上叠加应用层表（用户 / 审计 / 会话密钥），并给规则表补列。幂等，可重复运行。"""
import os, sqlite3, hashlib, secrets, sys

DB = os.environ.get("PRICING_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pricing_db", "pricing.db")

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${h}"

def col_exists(c, table, col):
    return any(r[1] == col for r in c.execute(f"PRAGMA table_info({table})"))

def main():
    if not os.path.exists(DB):
        print("!! pricing.db 不存在，请先在 pricing_db/ 运行 build_db.py"); sys.exit(1)
    con = sqlite3.connect(DB); c = con.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY, pw_hash TEXT, role TEXT, created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY, ts TEXT DEFAULT (datetime('now')),
        actor TEXT, action TEXT, target TEXT, before TEXT, after TEXT, source TEXT);
    CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    # 规则表补列：数量档加折扣率；加成/费用表补更新人
    if not col_exists(c, "qty_discount_tiers", "discount_pct"):
        c.execute("ALTER TABLE qty_discount_tiers ADD COLUMN discount_pct REAL DEFAULT 0")
    # 播种数量档折扣占位值（如为空）
    rows = c.execute("SELECT COUNT(*) FROM qty_discount_tiers WHERE discount_pct IS NOT NULL AND discount_pct<>0").fetchone()[0]
    if rows == 0:
        for mn, d in [(5000, 0), (20000, 3), (50000, 6)]:
            c.execute("UPDATE qty_discount_tiers SET discount_pct=? WHERE min_qty=?", (d, mn))

    # 会话签名密钥
    if not c.execute("SELECT 1 FROM app_meta WHERE key='session_secret'").fetchone():
        c.execute("INSERT INTO app_meta(key,value) VALUES('session_secret',?)", (secrets.token_hex(32),))

    # 播种两个用户（存在则跳过）
    seed = [("admin", "admin123", "admin"), ("sales", "sales123", "quoter")]
    for u, p, role in seed:
        if not c.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
            c.execute("INSERT INTO users(username,pw_hash,role) VALUES(?,?,?)", (u, hash_pw(p), role))
            print(f"  seeded user {u}/{p} ({role})")
    con.commit()
    print("app db ready:", DB)
    print("users:", [r[0]+':'+r[1] for r in c.execute("SELECT username,role FROM users")])
    con.close()

if __name__ == "__main__":
    main()
