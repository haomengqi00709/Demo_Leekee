#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
李记包装报价库 · 命令行查询工具
用法:
  python3 query.py stats                 # 数据库概览
  python3 query.py code CC20945          # 某编码的全部工艺→价格 + 图片
  python3 query.py series H563           # 某套系的部件与价格
  python3 query.py bottle 乳液瓶 100     # 玻璃瓶单品按名称/容量搜索
  python3 query.py search 滴泵           # 关键词搜编码
"""
import sqlite3, sys, os
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pricing.db')
con = sqlite3.connect(DB); c = con.cursor()

def p(rows, headers):
    if not rows: print("  (无结果)"); return
    widths=[len(h) for h in headers]
    srows=[["" if x is None else str(x) for x in r] for r in rows]
    for r in srows:
        for i,x in enumerate(r): widths[i]=min(max(widths[i],len(x)),46)
    line="  "+" | ".join(h.ljust(widths[i]) for i,h in enumerate(headers)); print(line); print("  "+"-"*(len(line)-2))
    for r in srows:
        print("  "+" | ".join(x[:46].ljust(widths[i]) for i,x in enumerate(r)))

def stats():
    for t in ['source_files','price_items','products','glass_bottles','inventory','images','invoices','suppliers']:
        print(f"  {t:16}: {c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    print("\n  按品类:")
    p(c.execute("SELECT product_type,COUNT(*) FROM products GROUP BY 1 ORDER BY 2 DESC").fetchall(),['type','n'])

def code(x):
    print(f"\n== 编码 {x} ==")
    prod=c.execute("SELECT prefix,product_type,name,capacity,default_supplier FROM products WHERE code=?",(x,)).fetchone()
    if prod: print(f"  类型:{prod[1]}  名称:{prod[2] or ''}  容量:{prod[3] or ''}  供应商:{prod[4] or ''}")
    gb=c.execute("SELECT material_name,capacity,bare_price,frosting_fee,unified_price FROM glass_bottles WHERE material_code=?",(x,)).fetchone()
    if gb: print(f"  [玻璃瓶] {gb[0]} {gb[1]}  光瓶价:{gb[2]}  蒙砂:{gb[3]}  统一价:{gb[4]}")
    print("\n  最新工艺→价格:")
    p(c.execute("""SELECT process_desc,unified_price,supplier,series_code,price_year FROM v_price_latest
                   WHERE code=? ORDER BY unified_price""",(x,)).fetchall(),
      ['工艺说明','统一价','供应商','套系','年份'])
    img=c.execute("SELECT image_path,n_images FROM v_product_image WHERE product_code=?",(x,)).fetchone()
    print(f"\n  图片: {img[0]}  (共{img[1]}张)" if img else "\n  图片: 无")

def series(x):
    x=x.upper()
    print(f"\n== 套系 {x} 部件清单 ==")
    p(c.execute("SELECT product_code,capacity,components,n_process_options,price_min,price_max FROM v_series_components WHERE series_code=? ORDER BY product_code",(x,)).fetchall(),
      ['编码','容量','配件','工艺数','最低价','最高价'])
    print("\n  全部工艺→价格:")
    p(c.execute("SELECT product_code,process_desc,unified_price,supplier FROM price_items WHERE series_code=? AND unified_price IS NOT NULL ORDER BY product_code,unified_price",(x,)).fetchall(),
      ['编码','工艺','统一价','供应商'])

def bottle(*terms):
    where=" AND ".join(["(material_name LIKE ? OR capacity LIKE ? OR material_code LIKE ?)" for _ in terms])
    args=[]; [args.extend([f"%{t}%"]*3) for t in terms]
    p(c.execute(f"SELECT material_code,material_name,capacity,bare_price,frosting_fee,unified_price,sheet_name FROM glass_bottles WHERE {where} LIMIT 40",args).fetchall(),
      ['编码','名称','容量','光瓶价','蒙砂','统一价','表'])

def search(kw):
    p(c.execute("""SELECT DISTINCT pi.product_code,pi.component,pi.capacity,pi.supplier FROM price_items pi
                   WHERE pi.component LIKE ? OR pi.process_desc LIKE ? OR pi.product_code LIKE ? LIMIT 40""",
                (f"%{kw}%",f"%{kw}%",f"%{kw}%")).fetchall(),['编码','配件','容量','供应商'])

if __name__=='__main__':
    a=sys.argv[1:] or ['stats']
    cmd=a[0]
    {'stats':lambda:stats(),'code':lambda:code(a[1]),'series':lambda:series(a[1]),
     'bottle':lambda:bottle(*a[1:]),'search':lambda:search(a[1])}.get(cmd, lambda:print(__doc__))()
    con.close()
