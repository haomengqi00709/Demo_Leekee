import os, sqlite3

DB_PATH = os.environ.get("PRICING_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pricing_db", "pricing.db")

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def audit(con, actor, action, target, before, after, source="ui"):
    import json
    con.execute("""INSERT INTO audit_log(actor,action,target,before,after,source)
                   VALUES(?,?,?,?,?,?)""",
                (actor, action, target,
                 json.dumps(before, ensure_ascii=False) if before is not None else None,
                 json.dumps(after, ensure_ascii=False) if after is not None else None, source))
