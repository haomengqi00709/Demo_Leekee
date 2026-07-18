# -*- coding: utf-8 -*-
"""AI 副驾：把管理员的自然语言 → 一次结构化规则改动（提议→确认→应用）。
有 ANTHROPIC_API_KEY 用 Claude（工具调用，保证结构）；没有则用确定性正则兜底，保证可演示。"""
import os, re, json
from db import audit

# LLM 配置 —— OpenAI 兼容接口。DeepSeek / Kimi(Moonshot) / OpenAI 都行，只改这三个环境变量：
#   DeepSeek : LLM_BASE_URL=https://api.deepseek.com          LLM_MODEL=deepseek-chat
#   Kimi     : LLM_BASE_URL=https://api.moonshot.cn/v1        LLM_MODEL=kimi-k2-0905-preview (或 moonshot-v1-8k)
#   OpenAI   : LLM_BASE_URL=https://api.openai.com/v1         LLM_MODEL=gpt-4o
LLM_API_KEY  = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL    = os.environ.get("LLM_MODEL", "deepseek-chat")

# propose_change 的参数 schema（OpenAI function calling 通用格式）
SCHEMA = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum":
                ["set_markup", "set_fee", "set_qty_discount", "add_compat", "clarify"]},
            "tier": {"type": "string", "description": "客户加成档，如 A/B/C"},
            "markup_pct": {"type": "number", "description": "加成百分比，如 28 表示 +28%"},
            "process": {"type": "string", "description": "工艺/表面费名称，如 烫金、普通印刷、蒙砂/门杀"},
            "fee": {"type": "number"},
            "unit": {"type": "string", "description": "每次 / 每个"},
            "min_qty": {"type": "integer", "description": "数量档下限，如 20000"},
            "discount_pct": {"type": "number", "description": "该档折扣百分比，如 5 表示降 5%"},
            "note": {"type": "string"},
            "code_a": {"type": "string"},
            "code_b": {"type": "string"},
            "verdict": {"type": "string", "enum": ["yes", "no"]},
            "reason": {"type": "string"},
            "summary": {"type": "string", "description": "一句话中文说明这次改动"},
            "clarification": {"type": "string", "description": "action=clarify 时要问的问题"},
        },
        "required": ["action", "summary"],
}
FUNCTIONS = [{"type": "function", "function": {
    "name": "propose_change",
    "description": "把管理员的一句话指令翻译成对报价规则库的一次改动。信息不足时用 action=clarify 追问。",
    "parameters": SCHEMA,
}}]

def _context(con):
    tiers = [f"{t}(+{m}%)" for t, m in con.execute("SELECT tier,markup_pct FROM customer_markups")]
    fees = [f"{p}(¥{f}/{u})" for p, f, u in con.execute("SELECT process,fee,unit FROM surface_fees")]
    return f"现有客户加成档：{', '.join(tiers)}。现有工艺费：{', '.join(fees)}。"

def _ai_propose(con, text):
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    sys = ("你是李记包装报价系统的管理助手。把管理员这一句话翻译成对规则库的**一次**结构化改动，"
           "必须调用 propose_change 函数输出，不要输出多余文字。" + _context(con))
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": text}],
        tools=FUNCTIONS,
        tool_choice={"type": "function", "function": {"name": "propose_change"}},
        temperature=0,
    )
    msg = resp.choices[0].message
    if msg.tool_calls:
        p = json.loads(msg.tool_calls[0].function.arguments); p["_engine"] = f"ai:{LLM_MODEL}"; return p
    if msg.content:  # 有些兼容实现会把 JSON 直接放 content
        try:
            p = json.loads(msg.content); p["_engine"] = f"ai:{LLM_MODEL}"; return p
        except Exception:
            pass
    return {"action": "clarify", "summary": "未能解析", "clarification": "请换个说法再试。", "_engine": f"ai:{LLM_MODEL}"}

CODE_RE = re.compile(r'[A-Z]{1,3}\d{3,}[A-Z]?')

def _cn_num(t):
    """把 '2万' / '5千' 这类中文单位展开成阿拉伯数字，方便正则兜底。"""
    t = re.sub(r'(\d+(?:\.\d+)?)\s*万', lambda m: str(int(float(m.group(1))*10000)), t)
    t = re.sub(r'(\d+(?:\.\d+)?)\s*千', lambda m: str(int(float(m.group(1))*1000)), t)
    return t

def _fallback_propose(text, con):
    t = _cn_num(text.strip())
    # 兼容规则
    codes = CODE_RE.findall(t.upper())
    if len(codes) >= 2:
        neg = any(k in t for k in ["不能", "不兼容", "装不上", "配不", "不行"])
        return {"action": "add_compat", "code_a": codes[0], "code_b": codes[1],
                "verdict": "no" if neg else "yes",
                "reason": t, "summary": f"记录 {codes[0]} 与 {codes[1]} {'不兼容' if neg else '兼容'}",
                "_engine": "fallback"}
    # 客户加成
    m = re.search(r'([A-Za-z])\s*(?:客户|档|级)?.{0,6}加成.{0,6}?(\d+(?:\.\d+)?)\s*%?', t)
    if not m:
        m2 = re.search(r'加成.{0,6}?(\d+(?:\.\d+)?)\s*%', t)
        if m2:
            tm = re.search(r'([A-Za-z])\s*(?:客户|档|级)', t)
            return {"action": "set_markup", "tier": (tm.group(1).upper() if tm else "A"),
                    "markup_pct": float(m2.group(1)), "summary": f"设 {(tm.group(1).upper() if tm else 'A')} 档加成为 +{m2.group(1)}%",
                    "_engine": "fallback"}
    if m:
        return {"action": "set_markup", "tier": m.group(1).upper(), "markup_pct": float(m.group(2)),
                "summary": f"设 {m.group(1).upper()} 档加成为 +{m.group(2)}%", "_engine": "fallback"}
    # 工艺费
    fm = re.search(r'(烫金|普通印刷|印刷|蒙砂|门杀)\D{0,6}?([\d.]+)', t)
    if fm:
        name = "普通印刷" if fm.group(1) == "印刷" else ("蒙砂/门杀" if fm.group(1) in ("蒙砂", "门杀") else fm.group(1))
        return {"action": "set_fee", "process": name, "fee": float(fm.group(2)), "unit": "每次",
                "summary": f"设 {name} 费为 ¥{fm.group(2)}/次", "_engine": "fallback"}
    # 数量档折扣
    qm = re.search(r'(\d[\d,]*)\s*个?(?:以上|\+).{0,8}?(\d+(?:\.\d+)?)\s*%', t)
    if qm:
        mn = int(qm.group(1).replace(",", ""))
        return {"action": "set_qty_discount", "min_qty": mn, "discount_pct": float(qm.group(2)),
                "note": t, "summary": f"设 ≥{mn} 档折扣为 -{qm.group(2)}%", "_engine": "fallback"}
    return {"action": "clarify", "summary": "没听懂",
            "clarification": "可以说：'B客户加成改成28%' / '烫金费改成0.3' / '2万个以上打5%折' / 'CC20945和CC20793不兼容'。",
            "_engine": "fallback"}

def propose(con, text):
    """返回 {proposal, preview}。preview 含 before/after，供确认。"""
    if LLM_API_KEY:
        try:
            p = _ai_propose(con, text)
        except Exception as e:
            p = _fallback_propose(text, con); p["_engine"] = f"fallback(ai错误:{type(e).__name__})"
    else:
        p = _fallback_propose(text, con)
    return {"proposal": p, "preview": _preview(con, p)}

def _preview(con, p):
    a = p.get("action")
    if a == "set_markup":
        r = con.execute("SELECT markup_pct FROM customer_markups WHERE tier=?", (p.get("tier"),)).fetchone()
        return {"table": "customer_markups", "key": f"{p.get('tier')} 档",
                "before": (f"+{r[0]}%" if r else "（新增）"), "after": f"+{p.get('markup_pct')}%"}
    if a == "set_fee":
        r = con.execute("SELECT fee,unit FROM surface_fees WHERE process=?", (p.get("process"),)).fetchone()
        return {"table": "surface_fees", "key": p.get("process"),
                "before": (f"¥{r[0]}/{r[1]}" if r else "（新增）"), "after": f"¥{p.get('fee')}/{p.get('unit') or '每次'}"}
    if a == "set_qty_discount":
        r = con.execute("SELECT discount_pct FROM qty_discount_tiers WHERE min_qty=?", (p.get("min_qty"),)).fetchone()
        return {"table": "qty_discount_tiers", "key": f"≥{p.get('min_qty')}",
                "before": (f"-{r[0] or 0}%" if r else "（新增档）"), "after": f"-{p.get('discount_pct')}%"}
    if a == "add_compat":
        return {"table": "compat_overrides", "key": f"{p.get('code_a')} ⇄ {p.get('code_b')}",
                "before": "（无人工规则）", "after": ("✅ 兼容" if p.get("verdict") == "yes" else "❌ 不兼容")}
    return {"table": None, "key": None, "before": None, "after": None}

def apply_change(con, p, actor):
    a = p.get("action")
    prev = _preview(con, p)
    if a == "set_markup":
        con.execute("""INSERT INTO customer_markups(tier,markup_pct,note,confirmed) VALUES(?,?,?,1)""",
                    (p["tier"], p["markup_pct"], "AI副驾录入")) if not con.execute(
            "SELECT 1 FROM customer_markups WHERE tier=?", (p["tier"],)).fetchone() else \
            con.execute("UPDATE customer_markups SET markup_pct=?,confirmed=1 WHERE tier=?", (p["markup_pct"], p["tier"]))
    elif a == "set_fee":
        if con.execute("SELECT 1 FROM surface_fees WHERE process=?", (p["process"],)).fetchone():
            con.execute("UPDATE surface_fees SET fee=?,unit=?,confirmed=1 WHERE process=?",
                        (p["fee"], p.get("unit") or "每次", p["process"]))
        else:
            con.execute("INSERT INTO surface_fees(process,fee,unit,note,confirmed) VALUES(?,?,?,?,1)",
                        (p["process"], p["fee"], p.get("unit") or "每次", "AI副驾录入"))
    elif a == "set_qty_discount":
        if con.execute("SELECT 1 FROM qty_discount_tiers WHERE min_qty=?", (p["min_qty"],)).fetchone():
            con.execute("UPDATE qty_discount_tiers SET discount_pct=?,confirmed=1 WHERE min_qty=?",
                        (p["discount_pct"], p["min_qty"]))
        else:
            con.execute("INSERT INTO qty_discount_tiers(min_qty,note,discount_pct,confirmed) VALUES(?,?,?,1)",
                        (p["min_qty"], p.get("note") or "AI副驾录入", p["discount_pct"]))
    elif a == "add_compat":
        con.execute("""INSERT INTO compat_overrides(code_a,code_b,verdict,reason,author,ts)
                       VALUES(?,?,?,?,?,datetime('now'))""",
                    (p["code_a"].upper(), p["code_b"].upper(), p["verdict"], p.get("reason") or "AI副驾录入", actor))
    else:
        raise ValueError("无法应用该改动")
    audit(con, actor, f"copilot:{a}", prev.get("key"), prev.get("before"), prev.get("after"), source="copilot")
    con.commit()
    return prev
