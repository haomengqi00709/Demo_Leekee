#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容性骨架 (阶段4-L1/L2)：在 pricing.db 上建 part_specs / compat_overrides，
把每个编码抽成“接口指纹”(角色 role + 牙口 neck + 直径 ∮ + 容量)，
兼容性 = 属性匹配(SQL) + 同套系兜底 + 人工override。运行: python3 build_compat.py
"""
import sqlite3, os, re, json
from collections import Counter, defaultdict
D = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(D,'pricing.db')); c = con.cursor()

# ---------- 牙口 / 直径 / 容量 解析 ----------
NECK_RES = [
    (re.compile(r'(\d{2})\s*/\s*(4\d{2})'), 'gcmi'),   # 20/410 22/410 18/410
    (re.compile(r'(\d{2})\s*口?牙'),        'ya'),      # 20牙 18口牙
    (re.compile(r'(\d{2})\s*口径'),          'kj'),      # 20口径 18口径
]
DIA_RE = re.compile(r'[∮φΦ]\s*(\d+\.?\d*)')
VOL_RE = re.compile(r'(\d+\.?\d*)\s*(ml|ML|毫升)')
WT_RE  = re.compile(r'(\d+\.?\d*)\s*(g|G|克)')

def parse_neck(text):
    """返回 (neck_dia:int|None, forms:set) —— dia 取出现最多的口径数字"""
    dias = Counter(); forms = set()
    for rx, kind in NECK_RES:
        for m in rx.finditer(text):
            d = int(m.group(1)); dias[d]+=1
            forms.add(m.group(0).replace(' ',''))
    if not dias: return None, forms
    return dias.most_common(1)[0][0], forms

def role_of(text, prefix):
    t = text
    if any(k in t for k in ['滴管','滴泵','滴圈']): return 'dropper'
    if any(k in t for k in ['泵头','泵身','压嘴','泵圈','按压','按头']): return 'pump'
    if '外罩' in t or ('罩' in t and '外' in t): return 'cover'
    if '肩套' in t or '套筒' in t: return 'sleeve'
    if any(k in t for k in ['外盖','内盖','盖子','内牙','旋盖','顶片','面盖','中盖','盖']): return 'cap'
    if '内塞' in t: return 'plug'
    if '手拉' in t or '垫' in t: return 'liner'
    if '瓶' in t: return 'bottle'
    if prefix == 'CA': return 'cap'
    if prefix == 'CB': return 'bottle'
    return 'other'

# ---------- 建表 ----------
c.executescript("""
DROP TABLE IF EXISTS part_specs;
CREATE TABLE part_specs(
    code        TEXT PRIMARY KEY,
    prefix      TEXT,
    role        TEXT,           -- pump/cap/cover/dropper/bottle/sleeve/plug/liner/other
    roles_all   TEXT,           -- 该编码文本里命中的全部角色(可能是组合件)
    neck_dia    INTEGER,        -- 牙口径 mm (20/18/22...)；20牙≈20口径≈20/410(牙型待Winnie确认)
    neck_forms  TEXT,           -- 原始写法集合 "20/410;20口径"
    diameter_mm REAL,           -- ∮ 卡扣直径(外罩/肩套用)
    volume_ml   TEXT,           -- 容量(可多值)
    series_list TEXT,           -- 出现过的套系
    spec_source TEXT,           -- parsed | series-only
    confidence  TEXT            -- high | medium | low
);
DROP TABLE IF EXISTS compat_overrides;
CREATE TABLE compat_overrides(
    code_a  TEXT, code_b TEXT,
    verdict TEXT,               -- yes | no
    reason  TEXT,
    author  TEXT,
    ts      TEXT
);
""")

# ---------- 汇总每个编码的文本，抽取指纹 ----------
rows = c.execute("""SELECT product_code, component, process_desc, supplier_model, remark, capacity, series_code, raw_json
                    FROM price_items WHERE product_code IS NOT NULL""").fetchall()
agg = defaultdict(lambda: dict(text=[], caps=set(), series=set(), prefix=''))
for code, comp, proc, sm, rmk, cap, ser, raw in rows:
    a = agg[code]
    for x in (comp, proc, sm, rmk, cap):
        if x: a['text'].append(str(x))
    if raw: a['text'].append(raw)
    if cap: a['caps'].add(str(cap))
    if ser: a['series'].add(ser)
    if not a['prefix']:
        m = re.match(r'([A-Z]{1,3})', code); a['prefix'] = m.group(1) if m else ''

ins = 0
for code, a in agg.items():
    blob = ' '.join(a['text'])
    neck_dia, forms = parse_neck(blob)
    dia_m = DIA_RE.search(blob); diameter = float(dia_m.group(1)) if dia_m else None
    vols = sorted({m.group(0) for m in VOL_RE.finditer(' '.join(a['caps']) or blob)})
    # 角色：主 + 全部
    roles = []
    for seg in a['text']:
        r = role_of(seg, a['prefix'])
        if r != 'other' and r not in roles: roles.append(r)
    primary = roles[0] if roles else role_of(blob, a['prefix'])
    src = 'parsed' if (neck_dia or diameter) else 'series-only'
    conf = 'high' if any('/' in f for f in forms) else ('medium' if neck_dia or diameter else 'low')
    c.execute("""INSERT OR REPLACE INTO part_specs
        (code,prefix,role,roles_all,neck_dia,neck_forms,diameter_mm,volume_ml,series_list,spec_source,confidence)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (code, a['prefix'], primary, ';'.join(roles), neck_dia, ';'.join(sorted(forms)) or None,
         diameter, ';'.join(vols) or None, ';'.join(sorted(a['series'])) or None, src, conf))
    ins += 1

# ---------- 视图：同口径可互换(L2) ----------
c.executescript("""
DROP VIEW IF EXISTS v_substitute;
CREATE VIEW v_substitute AS
SELECT a.code AS code, b.code AS sub_code, a.neck_dia AS neck_dia, a.role AS role_a, b.role AS role_b
FROM part_specs a JOIN part_specs b
  ON a.neck_dia = b.neck_dia AND a.neck_dia IS NOT NULL AND a.code <> b.code;
""")
con.commit()

# ---------- 覆盖率报告 ----------
def q(s): return c.execute(s).fetchone()[0]
tot = q("SELECT COUNT(*) FROM part_specs")
print("=== 兼容性骨架 build 完成 ===")
print("part_specs 编码数     :", tot)
print("  有牙口(neck_dia)    :", q("SELECT COUNT(*) FROM part_specs WHERE neck_dia IS NOT NULL"),
      f"({q('SELECT COUNT(*) FROM part_specs WHERE neck_dia IS NOT NULL')*100//tot}%)")
print("  有∮直径             :", q("SELECT COUNT(*) FROM part_specs WHERE diameter_mm IS NOT NULL"))
print("  仅靠套系(无规格)     :", q("SELECT COUNT(*) FROM part_specs WHERE spec_source='series-only'"))
print("\n角色分布:")
for r,n in c.execute("SELECT role,COUNT(*) FROM part_specs GROUP BY role ORDER BY 2 DESC"):
    print(f"   {r:10} {n}")
print("\n牙口分布:")
for d,n in c.execute("SELECT neck_dia,COUNT(*) FROM part_specs WHERE neck_dia IS NOT NULL GROUP BY neck_dia ORDER BY 2 DESC"):
    print(f"   口径{d}  × {n}")
print("\nL1 同套系可配套的编码对(估算):",
      q("""SELECT COALESCE(SUM(n*(n-1)/2),0) FROM
            (SELECT series_code, COUNT(DISTINCT product_code) n FROM price_items
             WHERE series_code IS NOT NULL AND product_code IS NOT NULL GROUP BY series_code)"""))
print("L2 同口径可互换对(v_substitute):", q("SELECT COUNT(*)/2 FROM v_substitute"))
print("\n样例 part_specs:")
for r in c.execute("SELECT code,role,neck_dia,neck_forms,diameter_mm,volume_ml,confidence FROM part_specs WHERE neck_dia IS NOT NULL LIMIT 8"):
    print("   ", r)
con.close()
