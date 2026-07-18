# -*- coding: utf-8 -*-
"""李记包装报价系统 · 服务端（FastAPI）。demo 版：无登录，顶部两个 tab 切「报价员 / 管理员」。"""
import os, json, tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from db import connect, audit
from catalog import build_catalog, build_rules
from compat_logic import resolve
import copilot, importer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
TPL = os.path.join(HERE, "templates", "quote.tpl.html")
ACTOR = "管理员"

app = FastAPI(title="李记包装报价系统")

@app.on_event("startup")
def _bootstrap_db():
    """Railway volume 首次启动时目标 DB 为空——从仓库里打包的种子库复制过去，
    这样管理员的改动/上传会持久化在卷上，重新部署也不丢。"""
    import shutil
    from db import DB_PATH
    seed = os.path.join(os.path.dirname(HERE), "pricing_db", "pricing.db")
    if os.path.abspath(DB_PATH) != os.path.abspath(seed) and not os.path.exists(DB_PATH):
        d = os.path.dirname(DB_PATH)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        shutil.copy(seed, DB_PATH)
        print(f"[bootstrap] 种子库已复制到 {DB_PATH}")

TABS = [("/quote", "报价员", "quote"), ("/rules", "规则", "rules"), ("/data", "数据", "data")]

def tabbar(active):
    def tab(href, label, key):
        on = key == active
        s = ("color:var(--accent);border-bottom:2px solid var(--accent)" if on
             else "color:var(--ink2);border-bottom:2px solid transparent")
        return (f'<a href="{href}" style="text-decoration:none;font:600 14px/46px system-ui,sans-serif;'
                f'padding:0 2px;{s}">{label}</a>')
    bar = ('<div style="position:fixed;top:0;left:0;right:0;z-index:1000;height:46px;display:flex;'
           'align-items:center;gap:22px;padding:0 22px;background:var(--surface);'
           'border-bottom:1px solid var(--line)">'
           '<span style="font:700 13px/46px ui-monospace,Menlo,monospace;color:var(--accent);letter-spacing:.02em">李记包装</span>'
           + "".join(tab(*t) for t in TABS) + "</div>")
    return bar + '<div style="height:46px"></div>'

def inject(html, active):
    return html.replace('<div class="wrap">', '<div class="wrap">' + tabbar(active), 1)

def serve(name, active):
    return HTMLResponse(inject(open(os.path.join(STATIC, name), encoding="utf-8").read(), active))

# ---------------- 页面 ----------------
@app.get("/", response_class=HTMLResponse)
def root(): return RedirectResponse("/quote")

@app.get("/admin", response_class=HTMLResponse)
def admin_redirect(): return RedirectResponse("/rules")

@app.get("/quote", response_class=HTMLResponse)
def quote_page():
    if not os.path.exists(TPL):
        raise HTTPException(500, "缺少 quote 模板，请在 pricing_db 运行 gen_quote_app.py")
    con = connect(); data = build_catalog(con); con.close()
    html = open(TPL, encoding="utf-8").read().replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False))
    return HTMLResponse(inject(html, "quote"))

@app.get("/rules", response_class=HTMLResponse)
def rules_page(): return serve("rules.html", "rules")

@app.get("/data", response_class=HTMLResponse)
def data_page(): return serve("data.html", "data")

# ---------------- 只读 API ----------------
@app.get("/api/catalog")
def api_catalog():
    con = connect(); d = build_catalog(con); con.close(); return d

@app.get("/api/rules")
def api_rules():
    con = connect(); r = build_rules(con); con.close(); return r

@app.get("/api/compat/check")
def api_compat_check(a: str, b: str):
    con = connect(); r = resolve(con, a, b); con.close(); return r

@app.get("/api/compat/overrides")
def api_overrides():
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT code_a,code_b,verdict,reason,author,ts FROM compat_overrides ORDER BY ts DESC")]
    con.close(); return rows

@app.get("/api/audit")
def api_audit():
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT ts,actor,action,target,before,after,source FROM audit_log ORDER BY id DESC LIMIT 100")]
    con.close(); return rows

# ---------------- 写 API ----------------
class Markup(BaseModel): tier: str; markup_pct: float
class Fee(BaseModel): process: str; fee: float; unit: str = "每次"
class Qty(BaseModel): min_qty: int; discount_pct: float; note: str = ""
class Override(BaseModel): code_a: str; code_b: str; verdict: str; reason: str = ""
class Ask(BaseModel): text: str
class Proposal(BaseModel): proposal: dict

@app.post("/api/rules/markup")
def set_markup(m: Markup):
    con = connect()
    old = con.execute("SELECT markup_pct FROM customer_markups WHERE tier=?", (m.tier,)).fetchone()
    if old:
        con.execute("UPDATE customer_markups SET markup_pct=?,confirmed=1 WHERE tier=?", (m.markup_pct, m.tier))
    else:
        con.execute("INSERT INTO customer_markups(tier,markup_pct,note,confirmed) VALUES(?,?,?,1)",
                    (m.tier, m.markup_pct, "手动"))
    audit(con, ACTOR, "set_markup", f"{m.tier}档", (f"+{old[0]}%" if old else "新增"), f"+{m.markup_pct}%")
    con.commit(); con.close(); return {"ok": True}

@app.post("/api/rules/fee")
def set_fee(f: Fee):
    con = connect()
    old = con.execute("SELECT fee FROM surface_fees WHERE process=?", (f.process,)).fetchone()
    if old:
        con.execute("UPDATE surface_fees SET fee=?,unit=?,confirmed=1 WHERE process=?", (f.fee, f.unit, f.process))
    else:
        con.execute("INSERT INTO surface_fees(process,fee,unit,note,confirmed) VALUES(?,?,?,?,1)",
                    (f.process, f.fee, f.unit, "手动"))
    audit(con, ACTOR, "set_fee", f.process, (f"¥{old[0]}" if old else "新增"), f"¥{f.fee}/{f.unit}")
    con.commit(); con.close(); return {"ok": True}

@app.post("/api/rules/qty")
def set_qty(q: Qty):
    con = connect()
    old = con.execute("SELECT discount_pct FROM qty_discount_tiers WHERE min_qty=?", (q.min_qty,)).fetchone()
    if old:
        con.execute("UPDATE qty_discount_tiers SET discount_pct=?,confirmed=1 WHERE min_qty=?", (q.discount_pct, q.min_qty))
    else:
        con.execute("INSERT INTO qty_discount_tiers(min_qty,note,discount_pct,confirmed) VALUES(?,?,?,1)",
                    (q.min_qty, q.note or "手动", q.discount_pct))
    audit(con, ACTOR, "set_qty", f"≥{q.min_qty}", (f"-{old[0] or 0}%" if old else "新增"), f"-{q.discount_pct}%")
    con.commit(); con.close(); return {"ok": True}

class Del(BaseModel):
    kind: str; tier: str = None; process: str = None; min_qty: int = None
    code_a: str = None; code_b: str = None

@app.post("/api/rule/delete")
def rule_delete(d: Del):
    con = connect()
    if d.kind == "markup":
        con.execute("DELETE FROM customer_markups WHERE tier=?", (d.tier,)); tgt = f"{d.tier}档加成"
    elif d.kind == "fee":
        con.execute("DELETE FROM surface_fees WHERE process=?", (d.process,)); tgt = d.process
    elif d.kind == "qty":
        con.execute("DELETE FROM qty_discount_tiers WHERE min_qty=?", (d.min_qty,)); tgt = f"≥{d.min_qty}"
    elif d.kind == "override":
        con.execute("DELETE FROM compat_overrides WHERE code_a=? AND code_b=?",
                    (d.code_a.upper(), d.code_b.upper())); tgt = f"{d.code_a}⇄{d.code_b}"
    else:
        con.close(); raise HTTPException(400, "未知规则类型")
    audit(con, ACTOR, f"delete:{d.kind}", tgt, "存在", "已删除")
    con.commit(); con.close(); return {"ok": True}

@app.post("/api/compat/override")
def add_override(o: Override):
    con = connect()
    con.execute("""INSERT INTO compat_overrides(code_a,code_b,verdict,reason,author,ts)
                   VALUES(?,?,?,?,?,datetime('now'))""",
                (o.code_a.upper(), o.code_b.upper(), o.verdict, o.reason, ACTOR))
    audit(con, ACTOR, "add_compat", f"{o.code_a}⇄{o.code_b}", None, o.verdict)
    con.commit(); con.close(); return {"ok": True}

@app.get("/api/stats")
def api_stats():
    con = connect(); c = con.cursor()
    one = lambda q: c.execute(q).fetchone()[0]
    counts = {
        "series": one("SELECT COUNT(DISTINCT series_code) FROM price_items WHERE series_code IS NOT NULL"),
        "products": one("SELECT COUNT(*) FROM products"),
        "price_rows": one("SELECT COUNT(*) FROM price_items"),
        "glass": one("SELECT COUNT(*) FROM glass_bottles"),
    }
    imports = [dict(r) for r in c.execute(
        "SELECT ts,target,after FROM audit_log WHERE action='import_excel' ORDER BY id DESC LIMIT 12")]
    con.close(); return {"counts": counts, "imports": imports}

# ---------------- 上传新报价单 Excel ----------------
def _save_tmp(up: UploadFile):
    suffix = os.path.splitext(up.filename or "x.xlsx")[1] or ".xlsx"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(up.file.read())
    return path

@app.post("/api/import/preview")
def import_preview(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "请上传 .xlsx 或 .xls 文件")
    path = _save_tmp(file)
    try:
        items = importer.parse_upload(path, file.filename)
    except Exception as e:
        os.remove(path); raise HTTPException(400, f"解析失败：{e}")
    os.remove(path)
    con = connect()
    if not items:
        con.close()
        return {"ok": False, "n_rows": 0, "msg": "没解析到价目行——请检查是不是标准的报价表(含 编号/工艺/统一价 等列)。"}
    s = importer.summarize(con, items); con.close()
    s["ok"] = True; s["filename"] = file.filename
    return s

@app.post("/api/import/apply")
def import_apply(file: UploadFile = File(...)):
    path = _save_tmp(file)
    try:
        items = importer.parse_upload(path, file.filename)
    except Exception as e:
        os.remove(path); raise HTTPException(400, f"解析失败：{e}")
    os.remove(path)
    if not items:
        raise HTTPException(400, "没解析到价目行，未导入。")
    con = connect()
    fid, n = importer.do_import(con, items, file.filename)
    series = sorted({it["series"] for it in items if it["series"]})
    audit(con, ACTOR, "import_excel", file.filename, None, f"{n} 条价目 / 套系 {','.join(series) or '—'}")
    con.commit(); con.close()
    return {"ok": True, "imported": n, "series": series, "source_file_id": fid}

# ---------------- AI 副驾 ----------------
@app.post("/api/copilot/propose")
def copilot_propose(ask: Ask):
    con = connect(); out = copilot.propose(con, ask.text); con.close(); return out

@app.post("/api/copilot/apply")
def copilot_apply(pr: Proposal):
    con = connect()
    try:
        prev = copilot.apply_change(con, pr.proposal, ACTOR)
    except Exception as e:
        con.close(); raise HTTPException(400, f"应用失败：{e}")
    con.close(); return {"ok": True, "applied": prev}
