#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 db_overview.html（Artifact body 内容）——从 pricing.db 读取真实数据/图片。"""
import sqlite3, os, base64, html, re
D = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(D, 'pricing.db')); c = con.cursor()
def q(sql, args=()): return c.execute(sql, args).fetchall()
def one(sql, args=()): return c.execute(sql, args).fetchone()[0]
def esc(x): return html.escape('' if x is None else str(x))

# ---- 概览统计 ----
tables = ['source_files','price_items','price_item_code','products','glass_bottles',
          'inventory','images','invoices','invoice_lines','suppliers']
views  = ['v_price_latest','v_series_components','v_product_image']
counts = {t: one(f'SELECT COUNT(*) FROM {t}') for t in tables+views}
img_mapped = one("SELECT COUNT(*) FROM images WHERE mapped=1")

# ---- 每张表：列 + 样例行 ----
DISPLAY = {
 'source_files':['id','rel_path','category','file_date','sheet_count','image_count'],
 'price_items':['id','series_code','product_code','capacity','component','process_desc','unified_price','supplier','price_year'],
 'price_item_code':['price_item_id','code'],
 'products':['code','prefix','product_type','name','capacity','default_supplier'],
 'glass_bottles':['material_code','material_name','capacity','weight_g','bare_price','frosting_fee','unified_price'],
 'inventory':['material_code','stock_qty','description','bottle_weight','stock_days'],
 'images':['product_code','sheet_name','anchor_row','anchor_col','ext','mapped'],
 'invoices':['doc_type','buyer','incoterm','currency','payment_term','total_amount'],
 'invoice_lines':['line_no','description','product_codes','quantity','unit_price','amount'],
 'suppliers':['name','n_items'],
}
SAMPLE = {
 'price_items':"SELECT {c} FROM price_items WHERE product_code IS NOT NULL AND unified_price IS NOT NULL LIMIT 5",
 'glass_bottles':"SELECT {c} FROM glass_bottles WHERE bare_price IS NOT NULL LIMIT 5",
 'images':"SELECT {c} FROM images WHERE mapped=1 LIMIT 5",
 'suppliers':"SELECT {c} FROM suppliers ORDER BY n_items DESC LIMIT 6",
 'invoice_lines':"SELECT {c} FROM invoice_lines LIMIT 4",
}
def table_block(t):
    cols = DISPLAY[t]
    sql = SAMPLE.get(t, "SELECT {c} FROM %s LIMIT 4" % t).format(c=','.join(cols))
    rows = q(sql)
    th = ''.join(f'<th>{esc(x)}</th>' for x in cols)
    trs = ''
    for r in rows:
        tds = ''.join(f'<td>{esc(str(v)[:44])}</td>' for v in r)
        trs += f'<tr>{tds}</tr>'
    numeric = {'unified_price','bare_price','frosting_fee','weight_g','stock_qty','stock_days',
               'amount','unit_price','quantity','total_amount','n_items','sheet_count','image_count',
               'anchor_row','anchor_col','price_year','id','price_item_id'}
    cat = one("SELECT category FROM source_files WHERE 1=0") if False else None
    return f'''<article class="tbl">
      <div class="tbl-head"><span class="tname">{t}</span><span class="cnt">{counts[t]:,} 行</span></div>
      <div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>
    </article>'''

# ---- 英雄区：H563 价格叠加 ----
h563 = q("""SELECT product_code,capacity,component,process_desc,unified_price,supplier
            FROM price_items WHERE series_code='H563' AND unified_price IS NOT NULL ORDER BY row_index""")
h563_rows = ''.join(
    f'<tr><td class="mono">{esc(a)}</td><td class="mono dim">{esc(b)}</td><td>{esc(cc)}</td>'
    f'<td>{esc(dd)}</td><td class="mono num">¥{ee}</td><td class="dim">{esc(ff)}</td></tr>'
    for (a,b,cc,dd,ee,ff) in h563)

# ---- 图片画廊：真实抽取的产品图 + 价格 ----
cand = q("""SELECT i.product_code, i.saved_path, i.series_code
            FROM images i WHERE i.mapped=1 AND i.product_code GLOB '[A-Z][A-Z][0-9]*'
            AND i.product_code NOT LIKE '%'||char(10)||'%' ORDER BY i.id""")
gallery = []
seen=set()
for code, path, series in cand:
    if code in seen: continue
    full = os.path.join(D, path)
    if not os.path.exists(full): continue
    sz = os.path.getsize(full)
    if sz > 170000 or sz < 3000: continue
    # 找一个代表价格
    price = one("SELECT MIN(unified_price) FROM v_price_latest WHERE code=?", (code,)) if \
            one("SELECT COUNT(*) FROM v_price_latest WHERE code=?", (code,)) else None
    if price is None:
        gp = one("SELECT COUNT(*) FROM glass_bottles WHERE material_code=?", (code,))
        price = one("SELECT unified_price FROM glass_bottles WHERE material_code=? LIMIT 1",(code,)) if gp else None
    ext = os.path.splitext(full)[1].lstrip('.').replace('jpg','jpeg')
    b64 = base64.b64encode(open(full,'rb').read()).decode()
    gallery.append((code, series, price, f'data:image/{ext};base64,{b64}'))
    seen.add(code)
    if len(gallery) >= 8: break
gal_html = ''.join(
    f'''<figure class="card"><div class="ph"><img src="{src}" alt="{esc(code)}" loading="lazy"></div>
        <figcaption><span class="mono code">{esc(code)}</span>
        <span class="price">{('¥'+str(round(pr,2))+' 起') if pr is not None else '—'}</span>
        <span class="ser mono dim">{esc(series or '')}</span></figcaption></figure>'''
    for (code, series, pr, src) in gallery)

# 供应商条形（占比）
sup = q("SELECT name,n_items FROM suppliers ORDER BY n_items DESC LIMIT 10")
supmax = max(n for _,n in sup) if sup else 1
sup_html = ''.join(
    f'<div class="bar"><span class="bl">{esc(n)}</span><span class="btrack"><span class="bfill" style="width:{max(4,int(v/supmax*100))}%"></span></span><span class="bv mono">{v:,}</span></div>'
    for n,v in sup)

cat_html = ''.join(table_block(t) for t in tables)

# 规则表
rules = q("SELECT tier,markup_pct,note FROM customer_markups") + [('—','—','—')]
markups = q("SELECT tier,markup_pct FROM customer_markups")
qty = q("SELECT min_qty,note FROM qty_discount_tiers")
fees = q("SELECT process,fee,unit FROM surface_fees")

STAT = [
 ('数据表 / 视图', f"{len(tables)}<span class='u'> 表</span> + {len(views)}<span class='u'> 视图</span>"),
 ('价目明细行', f"{counts['price_items']:,}"),
 ('去重产品编码', f"{counts['products']:,}"),
 ('玻璃瓶单品', f"{counts['glass_bottles']:,}"),
 ('产品图(已映射)', f"{img_mapped}<span class='u'> / {counts['images']}</span>"),
 ('供应商', f"{counts['suppliers']}"),
]
stat_html = ''.join(f'<div class="stat"><div class="sv mono">{v}</div><div class="sl">{l}</div></div>' for l,v in STAT)
markup_html = ' · '.join(f"{esc(t)}档 +{int(m)}%" for t,m in markups)
qty_html = ' · '.join(f"≥{m:,}" for m,_ in qty)
fee_html = ' · '.join(f"{esc(p)} ¥{f}/{esc(u)}" for p,f,u in fees)

MERMAID = """erDiagram
  source_files ||--o{ price_items : "解析出"
  price_items  ||--o{ price_item_code : "多码拆分"
  price_items  ||--o{ images : "锚定行→编码"
  source_files ||--o{ glass_bottles : "玻璃瓶单品"
  source_files ||--o{ inventory : "库存"
  source_files ||--o{ invoices : "对外单据"
  invoices     ||--o{ invoice_lines : "明细行"
  products     }o--o{ price_item_code : "按编码汇聚"
"""

# --------------------------------------------------------------------------
OUT = f'''<title>李记包装 · 报价数据库 pricing.db</title>
<style>
:root{{
  --bg:#f3f4f6; --surface:#ffffff; --surface2:#eceef2; --ink:#191c21; --ink2:#5c626c;
  --line:#dbdee4; --accent:#b06a2c; --accent2:#8a5220; --soft:rgba(176,106,44,.11);
  --good:#2f7d5b; --warn:#a9812a; --blueprint:#f7f4ee; --blueink:#3a3630;
  --fs:16px; --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}}
@media (prefers-color-scheme:dark){{:root{{
  --bg:#131519; --surface:#1b1e23; --surface2:#22262d; --ink:#e6e8ec; --ink2:#98a0ab;
  --line:#2c313a; --accent:#d8964f; --accent2:#e6ac6c; --soft:rgba(216,150,79,.14);
  --good:#54ab82; --warn:#c99a44;
}}}}
:root[data-theme="dark"]{{
  --bg:#131519; --surface:#1b1e23; --surface2:#22262d; --ink:#e6e8ec; --ink2:#98a0ab;
  --line:#2c313a; --accent:#d8964f; --accent2:#e6ac6c; --soft:rgba(216,150,79,.14);
  --good:#54ab82; --warn:#c99a44;
}}
:root[data-theme="light"]{{
  --bg:#f3f4f6; --surface:#ffffff; --surface2:#eceef2; --ink:#191c21; --ink2:#5c626c;
  --line:#dbdee4; --accent:#b06a2c; --accent2:#8a5220; --soft:rgba(176,106,44,.11);
  --good:#2f7d5b; --warn:#a9812a;
}}
*{{box-sizing:border-box}}
.wrap{{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:var(--fs);
  line-height:1.5;padding:clamp(18px,4vw,52px);-webkit-font-smoothing:antialiased}}
.inner{{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:40px}}
.mono{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.dim{{color:var(--ink2)}} .num{{text-align:right}}
.eyebrow{{font-family:var(--mono);font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);font-weight:600}}
h1{{font-size:clamp(1.7rem,3.6vw,2.5rem);margin:.15em 0 .1em;letter-spacing:-.01em;text-wrap:balance;font-weight:680}}
h2{{font-size:1.18rem;margin:0;letter-spacing:-.005em;display:flex;align-items:baseline;gap:.6em}}
h2 .k{{font-family:var(--mono);font-size:.7rem;color:var(--ink2);letter-spacing:.1em}}
.lede{{color:var(--ink2);max-width:64ch;margin:.3em 0 0}}
.cmd{{font-family:var(--mono);font-size:.82rem;background:var(--surface2);border:1px solid var(--line);
  border-radius:7px;padding:.5em .8em;display:inline-flex;gap:.5em;align-items:center;color:var(--ink)}}
.cmd::before{{content:"$";color:var(--accent);font-weight:700}}
section{{display:flex;flex-direction:column;gap:16px}}
.head-row{{display:flex;flex-direction:column;gap:6px;border-bottom:1px solid var(--line);padding-bottom:8px}}

/* stat tiles */
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.stat{{background:var(--surface);padding:16px 18px;display:flex;flex-direction:column;gap:4px}}
.sv{{font-size:1.6rem;font-weight:600;letter-spacing:-.02em}}
.sv .u{{font-size:.85rem;color:var(--ink2);font-weight:400}}
.sl{{font-size:.78rem;color:var(--ink2)}}

/* blueprint diagram */
.blueprint{{background:var(--blueprint);color:var(--blueink);border:1px solid var(--line);
  border-radius:12px;padding:22px;overflow-x:auto}}
.blueprint .mermaid{{display:flex;justify-content:center;min-width:520px}}
.cap{{font-size:.8rem;color:var(--ink2);margin-top:2px}}

/* hero grid */
.hero{{display:grid;grid-template-columns:1.15fr .85fr;gap:22px}}
@media(max-width:820px){{.hero{{grid-template-columns:1fr}}}}
.panel{{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.panel .ph-h{{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;
  align-items:center;background:var(--surface2)}}
.panel .ph-h b{{font-weight:640}} .panel .ph-h .mono{{font-size:.72rem;color:var(--ink2)}}
table{{border-collapse:collapse;width:100%;font-size:.82rem}}
thead th{{text-align:left;font-family:var(--mono);font-weight:600;font-size:.7rem;letter-spacing:.03em;
  text-transform:uppercase;color:var(--ink2);padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap;background:var(--surface)}}
tbody td{{padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover td{{background:var(--soft)}}
td.mono{{font-family:var(--mono);font-size:.78rem}} td.num{{text-align:right;font-family:var(--mono)}}
.build td.num{{color:var(--accent2);font-weight:600}}
.scroll{{overflow-x:auto}}

/* image gallery */
.gal{{display:grid;grid-template-columns:repeat(auto-fill,minmax(122px,1fr));gap:12px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:0}}
.card .ph{{aspect-ratio:1;background:var(--surface2);display:flex;align-items:center;justify-content:center;overflow:hidden}}
.card img{{width:100%;height:100%;object-fit:cover}}
.card figcaption{{padding:8px 10px;display:flex;flex-direction:column;gap:2px}}
.card .code{{font-size:.74rem;font-weight:600}}
.card .price{{font-size:.8rem;color:var(--accent);font-weight:640;font-variant-numeric:tabular-nums}}
.card .ser{{font-size:.66rem}}

/* supplier bars */
.bars{{display:flex;flex-direction:column;gap:7px}}
.bar{{display:grid;grid-template-columns:88px 1fr 52px;align-items:center;gap:10px;font-size:.8rem}}
.bl{{color:var(--ink)}} .btrack{{height:9px;background:var(--surface2);border-radius:5px;overflow:hidden}}
.bfill{{display:block;height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:5px}}
.bv{{text-align:right;color:var(--ink2);font-size:.76rem}}

/* table catalog */
.catalog{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:820px){{.catalog{{grid-template-columns:1fr}}}}
.tbl{{background:var(--surface);border:1px solid var(--line);border-radius:11px;overflow:hidden;display:flex;flex-direction:column}}
.tbl-head{{display:flex;justify-content:space-between;align-items:center;padding:11px 14px;background:var(--surface2);border-bottom:1px solid var(--line)}}
.tname{{font-family:var(--mono);font-weight:640;font-size:.88rem;color:var(--ink)}}
.tname::before{{content:"▸ ";color:var(--accent)}}
.cnt{{font-family:var(--mono);font-size:.72rem;color:var(--ink2);background:var(--soft);padding:2px 8px;border-radius:20px}}

/* rules */
.rules{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.rule{{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:9px;padding:14px 16px;display:flex;flex-direction:column;gap:6px}}
.rule .t{{font-size:.72rem;font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--warn)}}
.rule .v{{font-size:.92rem}} .rule .n{{font-size:.72rem;color:var(--ink2)}}
.pend{{display:inline-block;font-size:.64rem;font-family:var(--mono);color:var(--warn);border:1px solid var(--warn);border-radius:20px;padding:1px 7px;margin-left:4px}}
footer{{border-top:1px solid var(--line);padding-top:16px;color:var(--ink2);font-size:.78rem;display:flex;flex-wrap:wrap;gap:6px 18px}}
footer .mono{{color:var(--ink)}}
.tag{{display:inline-block;font-size:.66rem;font-family:var(--mono);padding:1px 7px;border-radius:5px;background:var(--soft);color:var(--accent2)}}
</style>

<div class="wrap"><div class="inner">

  <header class="section">
    <span class="eyebrow">李记包装 · Leekee Packaging</span>
    <h1>报价数据库 <span style="color:var(--accent)">pricing.db</span></h1>
    <p class="lede">把 100 个玻璃化妆品包装报价 Excel，解析成一个可查询的 SQLite 数据库——
      产品编码、工艺档位价格、玻璃瓶成本、库存、对外单据，连内嵌产品图都映射到了编码上。这是它的样子。</p>
    <div><span class="cmd">python3 build_db.py</span> &nbsp;<span class="cap">一键从源 Excel 全量重建</span></div>
  </header>

  <section>
    <div class="stats">{stat_html}</div>
  </section>

  <section>
    <div class="head-row"><h2>数据模型 <span class="k">SCHEMA</span></h2>
      <p class="cap">10 张表 + 3 个视图。核心是 <b>price_items</b>（一行 = 一个 编码 × 工艺 × 价格），多码单元格拆进 price_item_code，图片按锚定行回连编码。</p></div>
    <div class="blueprint"><pre class="mermaid">{MERMAID}</pre></div>
  </section>

  <section>
    <div class="head-row"><h2>一个套系怎么定价 <span class="k">H563 · 派顿</span></h2>
      <p class="cap">同一个瓶/盖/泵，工艺不同、价格不同——这正是报价 agent 要叠加的逻辑。下面是数据库里 H563 的原样价目。</p></div>
    <div class="hero">
      <div class="panel">
        <div class="ph-h"><b>H563 价目明细</b><span class="mono">v_series · 11 行</span></div>
        <div class="scroll"><table class="build"><thead><tr><th>编码</th><th>容量</th><th>配件</th><th>工艺说明</th><th>统一价</th><th>供应商</th></tr></thead>
          <tbody>{h563_rows}</tbody></table></div>
      </div>
      <div class="panel">
        <div class="ph-h"><b>供应商分布</b><span class="mono">suppliers · top 10</span></div>
        <div style="padding:16px"><div class="bars">{sup_html}</div></div>
      </div>
    </div>
  </section>

  <section>
    <div class="head-row"><h2>产品图 ↔ 编码 <span class="k">IMAGES</span></h2>
      <p class="cap">从 Excel 内嵌图里抽出 {counts['images']} 张、按锚定行映射到编码（{img_mapped} 张已映射）。下面是真实抽取的图，配上该编码的最低统一价。</p></div>
    <div class="gal">{gal_html}</div>
  </section>

  <section>
    <div class="head-row"><h2>逐表速览 <span class="k">TABLES</span></h2>
      <p class="cap">每张表的真实样例行（价格单位 RMB；raw_json 等原始列已隐藏，仅用于回溯）。</p></div>
    <div class="catalog">{cat_html}</div>
  </section>

  <section>
    <div class="head-row"><h2>规则参数 <span class="k">阶段2 待核对</span></h2>
      <p class="cap">这些是报价叠加需要、但要跟 Winnie 核实真数的规则——已按通话口径先播种，标记待确认。</p></div>
    <div class="rules">
      <div class="rule"><span class="t">客户加成 <span class="pend">待核对</span></span><span class="v">{markup_html}</span><span class="n">customer_markups</span></div>
      <div class="rule"><span class="t">数量阶梯 <span class="pend">待核对</span></span><span class="v">{qty_html}</span><span class="n">qty_discount_tiers · 5000 起为基准价</span></div>
      <div class="rule"><span class="t">附加工艺费 <span class="pend">待核对</span></span><span class="v">{fee_html}</span><span class="n">surface_fees</span></div>
    </div>
  </section>

  <footer>
    <span>SQLite · <span class="mono">pricing.db</span></span>
    <span>源：100 个 Excel</span>
    <span>视图 <span class="mono">v_price_latest</span> / <span class="mono">v_series_components</span> / <span class="mono">v_product_image</span></span>
    <span>查询 <span class="mono">python3 query.py code CC20945</span></span>
    <span class="tag">阶段1 完成</span>
  </footer>

</div></div>'''

open(os.path.join(D,'db_overview.html'),'w',encoding='utf-8').write(OUT)
print("written", len(OUT), "bytes ·", len(gallery), "images embedded")
con.close()
