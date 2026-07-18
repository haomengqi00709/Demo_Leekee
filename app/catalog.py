# -*- coding: utf-8 -*-
"""从 pricing.db 现场构建报价前端所需的 catalog（含规则 + 兼容指纹），供 /quote 注入 & /api/catalog。"""
import os, re, base64

def infer_group(proc):
    p = proc or ''
    if '外罩' in p: return '外罩'
    if any(k in p for k in ['泵头','泵身','压嘴','泵圈']): return '泵头'
    if '滴' in p: return '滴管/滴泵'
    if any(k in p for k in ['外盖','内盖','盖子','内牙','顶片','中盖','面盖','旋盖']): return '盖'
    if any(k in p for k in ['手拉','垫']): return '垫片'
    if any(k in p for k in ['肩套','套筒']): return '肩套'
    return '主体'
GORD = {'主体':0,'瓶身':0,'外罩':1,'泵头':2,'滴管/滴泵':2,'肩套':3,'盖':4,'垫片':5}

def _clean(s): return re.sub(r'\s+',' ',str(s)).strip() if s is not None else None

def _build_entries(rows):
    best = {}
    for r in rows:
        code, cap, comp, proc, price, sup, yr, fid = r
        if not code or price is None or not proc: continue
        g = _clean(comp) if (comp and str(comp).strip()) else infer_group(proc)
        key = (code, g, _clean(proc)); rank = (yr or 0, fid or 0)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, dict(code=code, cap=_clean(cap), g=g, proc=_clean(proc),
                                    price=round(float(price),4), sup=_clean(sup)))
    prods = {}
    for _, r in best.values():
        p = prods.setdefault(r['code'], dict(code=r['code'], cap=None, sup=None, groups={}))
        if r['cap'] and not p['cap']: p['cap']=r['cap']
        if r['sup'] and not p['sup']: p['sup']=r['sup']
        p['groups'].setdefault(r['g'], []).append({'d':r['proc'],'p':r['price']})
    out = []
    for code, p in prods.items():
        groups = [{'name':g,'opts':sorted(p['groups'][g], key=lambda o:o['p'])}
                  for g in sorted(p['groups'], key=lambda g:(GORD.get(g,9),g))]
        out.append({'code':code,'cap':p['cap'],'sup':p['sup'],'groups':groups})
    out.sort(key=lambda e:e['code'])
    return out

def build_catalog(con):
    c = con.cursor()
    series = [r[0] for r in c.execute(
        "SELECT DISTINCT series_code FROM price_items WHERE series_code IS NOT NULL ORDER BY series_code")]
    products, collections = {}, []
    for s in series:
        rows = c.execute("""SELECT product_code,capacity,component,process_desc,unified_price,
                                   supplier,price_year,source_file_id
                            FROM price_items WHERE series_code=? AND unified_price IS NOT NULL""",(s,)).fetchall()
        ent = _build_entries([tuple(r) for r in rows])
        if not ent: continue
        sup = next((e['sup'] for e in ent if e['sup']), '')
        products[s] = ent
        collections.append({'id':s,'label':s,'sup':sup,'n':len(ent)})
    srows = c.execute("""SELECT pi.product_code,pi.capacity,pi.component,pi.process_desc,pi.unified_price,
                                pi.supplier,pi.price_year,pi.source_file_id
                         FROM price_items pi JOIN source_files sf ON sf.id=pi.source_file_id
                         WHERE sf.category='single' AND pi.unified_price IS NOT NULL""").fetchall()
    sing = _build_entries([tuple(r) for r in srows])
    if sing:
        products['__single__'] = sing
        collections.append({'id':'__single__','label':'单品报价','sup':'','n':len(sing)})

    used = {e['code'] for ents in products.values() for e in ents}
    # 图片
    IMGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pricing_db')
    imgmap = {}
    for code, path in c.execute("""SELECT product_code,saved_path FROM images
            WHERE mapped=1 AND product_code GLOB '[A-Z][A-Z][0-9]*' ORDER BY product_code"""):
        if code in imgmap or code not in used: continue
        full = os.path.join(IMGDIR, path)
        if not os.path.exists(full) or os.path.getsize(full) > 48000: continue
        ext = os.path.splitext(full)[1].lstrip('.').replace('jpg','jpeg')
        imgmap[code] = f"data:image/{ext};base64," + base64.b64encode(open(full,'rb').read()).decode()
        if len(imgmap) >= 70: break
    # 兼容指纹 + override
    specs, ovr = {}, []
    try:
        for code, role, neck, ser in c.execute("SELECT code,role,neck_dia,series_list FROM part_specs"):
            if code in used:
                specs[code] = {'r':role,'n':neck,'s':(ser.split(';') if ser else [])}
        ovr = [[a,b,v] for a,b,v in c.execute("SELECT code_a,code_b,verdict FROM compat_overrides")]
    except Exception:
        pass
    rules = build_rules(con)
    return dict(collections=collections, products=products, imgmap=imgmap,
                specs=specs, overrides=ovr, rules=rules)

def build_rules(con):
    c = con.cursor()
    markups = [{'tier':t,'pct':m} for t,m in c.execute("SELECT tier,markup_pct FROM customer_markups ORDER BY markup_pct")]
    try:
        qty = [{'min':mn,'note':n,'discount_pct':(d or 0)} for mn,n,d in
               c.execute("SELECT min_qty,note,discount_pct FROM qty_discount_tiers ORDER BY min_qty")]
    except Exception:
        qty = [{'min':mn,'note':n,'discount_pct':0} for mn,n in
               c.execute("SELECT min_qty,note FROM qty_discount_tiers ORDER BY min_qty")]
    fees = {p:{'fee':f,'unit':u} for p,f,u in c.execute("SELECT process,fee,unit FROM surface_fees")}
    return {'markups':markups,'qty':qty,'fees':fees}
