# -*- coding: utf-8 -*-
"""极简登录 + 角色：pbkdf2 密码校验 + HMAC 签名的会话 cookie。角色：admin / quoter。"""
import hmac, hashlib, base64, json, time
from fastapi import Request, HTTPException
from db import connect

COOKIE = "lk_session"
TTL = 12 * 3600

def _secret():
    r = connect().execute("SELECT value FROM app_meta WHERE key='session_secret'").fetchone()
    return (r[0] if r else "insecure-dev-secret").encode()

def verify_password(username, password):
    r = connect().execute("SELECT pw_hash,role FROM users WHERE username=?", (username,)).fetchone()
    if not r: return None
    salt, h = r[0].split("$", 1)
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return {"username": username, "role": r[1]} if hmac.compare_digest(calc, h) else None

def _b64(b): return base64.urlsafe_b64encode(b).decode().rstrip("=")
def _unb64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def make_token(username, role):
    payload = _b64(json.dumps({"u": username, "r": role, "exp": int(time.time()) + TTL}).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"

def read_token(token):
    if not token or "." not in token: return None
    payload, sig = token.rsplit(".", 1)
    expect = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect): return None
    try:
        data = json.loads(_unb64(payload))
    except Exception:
        return None
    if data.get("exp", 0) < time.time(): return None
    return {"username": data["u"], "role": data["r"]}

def current_user(request: Request):
    return read_token(request.cookies.get(COOKIE))

def require_user(request: Request):
    u = current_user(request)
    if not u: raise HTTPException(status_code=401, detail="请先登录")
    return u

def require_admin(request: Request):
    u = require_user(request)
    if u["role"] != "admin": raise HTTPException(status_code=403, detail="需要管理员权限")
    return u
