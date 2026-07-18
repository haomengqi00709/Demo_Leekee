#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容性查询 (阶段4 骨架)
  python3 compat.py check CC20945 CC20831   # 两个编码兼容吗 -> 结论+理由+置信度
  python3 compat.py fits  CC20945           # 列出可配套(同套系)/可互换(同口径)的件
  python3 compat.py add   CC20945 CB20xxx yes "客户实测可装" 王工   # 人工override
解析优先级: 人工override > 同套系 > 同口径 > 未知
"""
import sqlite3, os, sys
D = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(D,'pricing.db')); c = con.cursor()

def spec(code):
    r = c.execute("SELECT code,role,neck_dia,neck_forms,series_list,volume_ml FROM part_specs WHERE code=?",(code,)).fetchone()
    return dict(code=r[0],role=r[1],neck=r[2],forms=r[3],series=(r[4] or '').split(';') if r[4] else [],vol=r[5]) if r else None

def resolve(a, b):
    sa, sb = spec(a), spec(b)
    if not sa or not sb:
        miss = a if not sa else b
        return ('unknown', f'编码 {miss} 不在库中', 'low')
    ov = c.execute("""SELECT verdict,reason,author FROM compat_overrides
                      WHERE (code_a=? AND code_b=?) OR (code_a=? AND code_b=?) LIMIT 1""",(a,b,b,a)).fetchone()
    if ov:
        return (ov[0], f'人工确认（{ov[2] or "?"}）：{ov[1]}', 'confirmed')
    common = set(sa['series']) & set(sb['series'])
    na, nb = sa['neck'], sb['neck']
    # 同套系但口径冲突：套系是“成套卖”，内含多规格；120ml的件配不上30ml的瓶
    if common and na and nb and na != nb:
        return ('caution', f'同属套系 {"/".join(sorted(common))} 但口径不同（{na} vs {nb}）——'
                            f'套系内不同规格的配件，需确认具体是哪一件', 'medium')
    if common:
        return ('yes', f'同套系 {"/".join(sorted(common))}（设计配套）', 'high')
    if na and nb:
        if na == nb:
            return ('likely', f'同口径 {na}（{sa["role"]}↔{sb["role"]}，接口可互换；牙型 410/415 待核对）', 'medium')
        return ('no', f'口径不同：{na} vs {nb}，无法互配', 'medium')
    return ('unknown', '缺牙口数据，建议人工确认（compat.py add 可补一条）', 'low')

ICON = {'yes':'✅ 兼容','likely':'🟡 大概率兼容','no':'❌ 不兼容','caution':'⚠️ 需确认','unknown':'❔ 未知'}

def check(a, b):
    v, reason, conf = resolve(a, b)
    print(f"\n  {a}  ⇄  {b}")
    print(f"  {ICON[v]}   （置信度 {conf}）")
    print(f"  理由：{reason}")
    for x in (a,b):
        s=spec(x)
        if s: print(f"    · {x}: role={s['role']} 口径={s['neck'] or '—'} 套系={'/'.join(s['series']) or '—'} 容量={s['vol'] or '—'}")

def fits(code):
    s = spec(code)
    if not s: print("  编码不在库中"); return
    print(f"\n== {code}  role={s['role']} 口径={s['neck'] or '—'} 套系={'/'.join(s['series']) or '—'} ==")
    print("\n  ▸ 同套系可配套（L1，设计配套 · 高可信）：")
    comp = c.execute("""SELECT DISTINCT pi.product_code, ps.role FROM price_items pi
                        JOIN part_specs ps ON ps.code=pi.product_code
                        WHERE pi.series_code IN (SELECT value FROM (
                            SELECT ? AS value) ) OR pi.series_code IN (%s)""" %
                     (','.join('?'*len(s['series'])) or "''"),
                     tuple([code]+s['series'])).fetchall() if s['series'] else []
    # 简化：直接取同套系其它编码
    comp = c.execute("""SELECT DISTINCT product_code FROM price_items
                        WHERE series_code IN (%s) AND product_code<>? AND product_code IS NOT NULL"""
                     % (','.join('?'*len(s['series'])) or "''"),
                     tuple(s['series']+[code])).fetchall() if s['series'] else []
    if comp:
        for (pc,) in comp[:20]:
            ps=spec(pc); print(f"      {pc:12} {ps['role'] if ps else ''}")
    else:
        print("      （无同套系记录）")
    print("\n  ▸ 同口径可互换（L2，牙型待核对 · 中可信）：")
    subs = c.execute("SELECT sub_code, role_b FROM v_substitute WHERE code=? LIMIT 20",(code,)).fetchall()
    if subs:
        for sc, rb in subs:
            print(f"      {sc:12} {rb}")
    else:
        print("      （无同口径记录 / 该件缺牙口数据）")

def add(a, b, verdict, reason, author='?'):
    c.execute("INSERT INTO compat_overrides(code_a,code_b,verdict,reason,author,ts) VALUES(?,?,?,?,?,datetime('now'))",
              (a,b,verdict,reason,author)); con.commit()
    print(f"  已记录人工规则：{a} ⇄ {b} = {verdict}（{reason}）")

if __name__ == '__main__':
    a = sys.argv[1:] or []
    if not a: print(__doc__); sys.exit()
    cmd = a[0]
    if cmd=='check' and len(a)>=3: check(a[1],a[2])
    elif cmd=='fits' and len(a)>=2: fits(a[1])
    elif cmd=='add' and len(a)>=5: add(a[1],a[2],a[3],a[4],a[5] if len(a)>5 else '?')
    else: print(__doc__)
    con.close()
