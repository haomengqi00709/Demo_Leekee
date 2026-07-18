# -*- coding: utf-8 -*-
"""服务端兼容性判定（与 compat.py / 前端逻辑一致）：override > 同套系 > 同口径 > 未知。"""

def _spec(con, code):
    r = con.execute("SELECT code,role,neck_dia,series_list,volume_ml FROM part_specs WHERE code=?", (code,)).fetchone()
    if not r: return None
    return dict(code=r[0], role=r[1], neck=r[2],
                series=(r[3].split(';') if r[3] else []), vol=r[4])

def resolve(con, a, b):
    a, b = a.strip().upper(), b.strip().upper()
    sa, sb = _spec(con, a), _spec(con, b)
    if not sa or not sb:
        miss = a if not sa else b
        return dict(verdict="unknown", confidence="low", reason=f"编码 {miss} 不在库中", a=sa, b=sb)
    ov = con.execute("""SELECT verdict,reason,author FROM compat_overrides
                        WHERE (code_a=? AND code_b=?) OR (code_a=? AND code_b=?) LIMIT 1""",
                     (a,b,b,a)).fetchone()
    if ov:
        return dict(verdict=("yes" if ov[0]=="yes" else "no"), confidence="confirmed",
                    reason=f"人工确认（{ov[2] or '?'}）：{ov[1]}", a=sa, b=sb)
    common = sorted(set(sa["series"]) & set(sb["series"]))
    na, nb = sa["neck"], sb["neck"]
    if common and na and nb and na != nb:
        return dict(verdict="caution", confidence="medium",
                    reason=f"同属套系 {'/'.join(common)} 但口径不同（{na} vs {nb}）——套系内不同规格，需确认具体件", a=sa, b=sb)
    if common:
        return dict(verdict="yes", confidence="high", reason=f"同套系 {'/'.join(common)}（设计配套）", a=sa, b=sb)
    if na and nb:
        if na == nb:
            return dict(verdict="likely", confidence="medium",
                        reason=f"同口径 {na}（{sa['role']}↔{sb['role']}，接口可互换；牙型待核对）", a=sa, b=sb)
        return dict(verdict="no", confidence="medium", reason=f"口径不同：{na} vs {nb}，无法互配", a=sa, b=sb)
    return dict(verdict="unknown", confidence="low", reason="缺牙口数据，建议人工确认", a=sa, b=sb)
