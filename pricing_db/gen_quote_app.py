#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 quote_app.html —— 自包含快速报价前端（Artifact body）。数据/规则从 pricing.db 嵌入。"""
import sqlite3, os, json, re
D = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(D,'pricing.db')); c = con.cursor()

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

def clean(s):
    return re.sub(r'\s+',' ',str(s)).strip() if s is not None else None

def build_entries(rows):
    """rows: (code,capacity,component,process,price,supplier,year,fid) -> entries list"""
    # dedup by (code, group, process) keep latest (year desc, fid desc)
    best = {}
    for code,cap,comp,proc,price,sup,yr,fid in rows:
        if not code or price is None or not proc: continue
        g = clean(comp) if (comp and str(comp).strip()) else infer_group(proc)
        key = (code, g, clean(proc))
        rank = (yr or 0, fid or 0)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, dict(code=code, cap=clean(cap), g=g, proc=clean(proc),
                                    price=round(float(price),4), sup=clean(sup)))
    # assemble
    prods = {}
    for _,r in best.values():
        p = prods.setdefault(r['code'], dict(code=r['code'], cap=None, sup=None, groups={}))
        if r['cap'] and not p['cap']: p['cap']=r['cap']
        if r['sup'] and not p['sup']: p['sup']=r['sup']
        p['groups'].setdefault(r['g'], []).append({'d':r['proc'],'p':r['price']})
    out = []
    for code,p in prods.items():
        groups = []
        for gname in sorted(p['groups'], key=lambda g:(GORD.get(g,9),g)):
            opts = sorted(p['groups'][gname], key=lambda o:o['p'])
            groups.append({'name':gname,'opts':opts})
        out.append({'code':code,'cap':p['cap'],'sup':p['sup'],'groups':groups})
    out.sort(key=lambda e:e['code'])
    return out

# 套系
series = [r[0] for r in c.execute("SELECT DISTINCT series_code FROM price_items WHERE series_code IS NOT NULL ORDER BY series_code")]
products = {}
collections = []
for s in series:
    rows = c.execute("""SELECT pi.product_code,pi.capacity,pi.component,pi.process_desc,pi.unified_price,
                               pi.supplier,pi.price_year,pi.source_file_id
                        FROM price_items pi WHERE pi.series_code=? AND pi.unified_price IS NOT NULL""",(s,)).fetchall()
    ent = build_entries(rows)
    if not ent: continue
    sup = next((e['sup'] for e in ent if e['sup']), '')
    products[s] = ent
    collections.append({'id':s,'label':s,'sup':sup,'n':len(ent)})

# 单品
srows = c.execute("""SELECT pi.product_code,pi.capacity,pi.component,pi.process_desc,pi.unified_price,
                            pi.supplier,pi.price_year,pi.source_file_id
                     FROM price_items pi JOIN source_files sf ON sf.id=pi.source_file_id
                     WHERE sf.category='single' AND pi.unified_price IS NOT NULL""").fetchall()
sing = build_entries(srows)
if sing:
    products['__single__'] = sing
    collections.append({'id':'__single__','label':'单品报价','sup':'','n':len(sing)})

# 附上牙口(口径) —— 来自 part_specs（若已 build_compat）
neckmap = {}
try:
    neckmap = {code: nd for code, nd in c.execute("SELECT code,neck_dia FROM part_specs WHERE neck_dia IS NOT NULL")}
except sqlite3.OperationalError:
    pass
for ents in products.values():
    for e in ents:
        if e['code'] in neckmap: e['neck'] = neckmap[e['code']]

# 图片: code -> data uri (仅嵌入被套系/单品引用到的、且不大的图，控制体积)
import base64
used_codes = set()
for ents in products.values():
    for e in ents: used_codes.add(e['code'])
# 只嵌入小体积原图(<=48KB)，保证页面秒开；每编码一张，最多 70 张
imgmap = {}
for code, path in c.execute("SELECT product_code,saved_path FROM images WHERE mapped=1 AND product_code GLOB '[A-Z][A-Z][0-9]*' ORDER BY product_code"):
    if code in imgmap or code not in used_codes: continue
    full = os.path.join(D, path)
    if not os.path.exists(full) or os.path.getsize(full) > 48000: continue
    ext = os.path.splitext(full)[1].lstrip('.').replace('jpg','jpeg')
    imgmap[code] = f"data:image/{ext};base64,"+base64.b64encode(open(full,'rb').read()).decode()
    if len(imgmap) >= 70: break

# 规则
markups = [{'tier':t,'pct':m} for t,m in c.execute("SELECT tier,markup_pct FROM customer_markups")]
qty = [{'min':m,'note':n} for m,n in c.execute("SELECT min_qty,note FROM qty_discount_tiers ORDER BY min_qty")]
fees = {p:{'fee':f,'unit':u} for p,f,u in c.execute("SELECT process,fee,unit FROM surface_fees")}

# 接口指纹 + 人工规则（供前端做兼容判定）——只带 catalog 内用到的编码
specs = {}; ovr = []
try:
    for code, role, neck, series in c.execute("SELECT code,role,neck_dia,series_list FROM part_specs"):
        if code in used_codes:
            specs[code] = {'r':role,'n':neck,'s':(series.split(';') if series else [])}
    ovr = [[a,b,v] for a,b,v in c.execute("SELECT code_a,code_b,verdict FROM compat_overrides")]
except sqlite3.OperationalError:
    pass

DATA = dict(collections=collections, products=products, imgmap=imgmap, specs=specs, overrides=ovr,
            rules=dict(markups=markups, qty=qty, fees=fees))
con.close()

data_json = json.dumps(DATA, ensure_ascii=False, separators=(',',':'))

TEMPLATE = r'''<title>李记包装 · 快速报价</title>
<style>
:root{
  --bg:#f3f4f6;--surface:#fff;--surface2:#eceef2;--ink:#191c21;--ink2:#5c626c;--line:#dbdee4;
  --accent:#b06a2c;--accent2:#8a5220;--soft:rgba(176,106,44,.11);--good:#2f7d5b;--warn:#a9812a;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;}
/* 强制浅色主题（报价单是要打印/发给客户的文档，始终用白底） */
:root[data-theme="dark"]{--bg:#131519;--surface:#1b1e23;--surface2:#22262d;--ink:#e6e8ec;--ink2:#98a0ab;--line:#2c313a;--accent:#d8964f;--accent2:#e6ac6c;--soft:rgba(216,150,79,.14);--good:#54ab82;--warn:#c99a44;}
:root[data-theme="light"]{--bg:#f3f4f6;--surface:#fff;--surface2:#eceef2;--ink:#191c21;--ink2:#5c626c;--line:#dbdee4;--accent:#b06a2c;--accent2:#8a5220;--soft:rgba(176,106,44,.11);--good:#2f7d5b;--warn:#a9812a;}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:var(--bg)}
.wrap{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;padding:clamp(14px,3vw,30px);min-height:100vh;-webkit-font-smoothing:antialiased}
.inner{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.eyebrow{font-family:var(--mono);font-size:.7rem;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-size:clamp(1.5rem,3vw,2.1rem);margin:.1em 0 0;letter-spacing:-.01em;font-weight:680}
.lede{color:var(--ink2);margin:.2em 0 0;font-size:.92rem;max-width:70ch}
.topbar{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:14px}
.globals{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
label.f{display:flex;flex-direction:column;gap:3px;font-size:.7rem;color:var(--ink2);font-family:var(--mono);letter-spacing:.04em;text-transform:uppercase}
select,input{font-family:var(--sans);font-size:.9rem;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:0}
select:focus,input:focus{outline:2px solid var(--accent);outline-offset:0}
input[type=number]{width:96px;font-family:var(--mono)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:13px;overflow:hidden}
.card>h2{font-size:.95rem;margin:0;padding:13px 16px;border-bottom:1px solid var(--line);background:var(--surface2);display:flex;justify-content:space-between;align-items:center}
.card>h2 .k{font-family:var(--mono);font-size:.68rem;color:var(--ink2);letter-spacing:.08em;font-weight:400}
.body{padding:16px;display:flex;flex-direction:column;gap:14px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.prodhead{display:flex;gap:12px;align-items:center}
.thumb{width:60px;height:60px;border-radius:8px;background:var(--surface2);object-fit:cover;flex:none;border:1px solid var(--line)}
.thumb.ph{display:flex;align-items:center;justify-content:center;color:var(--ink2);font-size:.6rem;font-family:var(--mono)}
.groups{display:flex;flex-direction:column;gap:10px}
.group{display:flex;flex-direction:column;gap:4px}
.group .gname{font-size:.72rem;font-family:var(--mono);color:var(--accent2);letter-spacing:.04em}
.group select{width:100%}
.opt-price{font-variant-numeric:tabular-nums}
.printrow{display:flex;gap:14px;flex-wrap:wrap;align-items:center;padding-top:2px}
.stepper{display:flex;align-items:center;gap:6px;font-size:.82rem}
.stepper b{font-family:var(--mono);min-width:18px;text-align:center}
.btn{font-family:var(--sans);font-size:.9rem;font-weight:600;border:1px solid var(--line);border-radius:9px;padding:9px 14px;background:var(--surface);color:var(--ink);cursor:pointer}
.btn:hover{border-color:var(--accent)}
.btn.pri{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.pri:hover{background:var(--accent2)}
.btn.sm{padding:5px 9px;font-size:.78rem;font-weight:500}
.btn:active{transform:translateY(1px)}
.mini{width:26px;height:26px;padding:0;font-size:1rem;line-height:1;display:flex;align-items:center;justify-content:center}
.preview{background:var(--soft);border:1px dashed var(--accent);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.preview .l{display:flex;justify-content:space-between;font-size:.82rem}
.preview .unit{font-size:1.5rem;font-weight:680;font-family:var(--mono);color:var(--accent2)}
.quote-lines{width:100%;border-collapse:collapse;font-size:.82rem}
.quote-lines th{text-align:left;font-family:var(--mono);font-size:.66rem;text-transform:uppercase;letter-spacing:.04em;color:var(--ink2);padding:8px 10px;border-bottom:1px solid var(--line)}
.quote-lines td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.quote-lines .num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.quote-lines .cfg{font-size:.72rem;color:var(--ink2)}
.quote-lines .x{color:var(--ink2);cursor:pointer;font-family:var(--mono)}
.quote-lines .x:hover{color:#c0392b}
.empty{padding:30px 16px;text-align:center;color:var(--ink2);font-size:.86rem}
.totals{display:flex;flex-direction:column;gap:6px;padding:14px 16px;border-top:2px solid var(--line);background:var(--surface2)}
.totals .l{display:flex;justify-content:space-between;font-size:.86rem}
.totals .l.big{font-size:1.15rem;font-weight:700}
.totals .l.big .v{font-family:var(--mono);color:var(--accent2)}
.terms{font-size:.72rem;color:var(--ink2);padding:10px 16px;display:flex;flex-direction:column;gap:3px;border-top:1px solid var(--line)}
.actions{display:flex;gap:8px;padding:12px 16px;flex-wrap:wrap}
.pend{font-size:.6rem;font-family:var(--mono);color:var(--warn);border:1px solid var(--warn);border-radius:20px;padding:0 6px;margin-left:5px;vertical-align:middle}
.note{font-size:.72rem;color:var(--ink2)}
.chip{display:inline-block;font-family:var(--mono);font-size:.68rem;background:var(--soft);color:var(--accent2);padding:1px 7px;border-radius:5px}
.compat-list{display:flex;flex-direction:column;gap:6px;max-height:186px;overflow-y:auto;margin-top:5px}
.crow{display:flex;justify-content:space-between;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:.8rem}
.crow:hover{border-color:var(--accent)}
.crow .c{font-family:var(--mono);font-weight:600}
.crow .m{font-size:.68rem;color:var(--ink2);font-family:var(--mono)}
.hint{font-size:.68rem;color:var(--ink2);margin-top:2px}
footer{color:var(--ink2);font-size:.74rem;text-align:center;padding-top:6px}
@media print{
  .wrap{background:#fff;padding:0}
  .noprint{display:none!important}
  .grid{grid-template-columns:1fr}
  .card{border:none}
}
</style>
<div class="wrap"><div class="inner">
  <div class="topbar">
    <div>
      <span class="eyebrow">李记包装 · Leekee — Quote Builder</span>
      <h1>快速报价</h1>
      <p class="lede">选套系 → 选产品 → 配工艺 → 出价。原来人工翻表 ~1 小时，这里几秒钟。<span class="chip" id="stat-coll"></span></p>
    </div>
    <div class="globals noprint">
      <label class="f">客户加成<select id="g-markup"></select></label>
      <label class="f">币种<select id="g-cur"><option value="CNY">¥ RMB</option><option value="USD">$ USD</option><option value="EUR">€ EUR</option></select></label>
      <label class="f" id="fx-wrap" style="display:none">汇率 1外币=<input type="number" id="g-fx" value="7.2" step="0.01" min="0.1"></label>
    </div>
  </div>

  <div class="grid">
    <!-- 配置 -->
    <section class="card noprint">
      <h2>配置产品 <span class="k">CONFIGURE</span></h2>
      <div class="body">
        <label class="f">搜索<input type="text" id="coll-search" autocomplete="off"
            placeholder="搜套系 / 产品编号 / 供应商 —— 如 H563、CC20918、伟诚"></label>
        <div class="row2">
          <label class="f">套系 / 类别<select id="sel-coll"></select></label>
          <label class="f">产品编号 / 规格<select id="sel-prod"></select></label>
        </div>
        <div class="prodhead"><img id="thumb" class="thumb ph" alt="">
          <div style="font-size:.8rem;color:var(--ink2)" id="prod-meta"></div></div>
        <div class="groups" id="groups"></div>
        <div>
          <div class="gname mono" style="font-size:.72rem;color:var(--accent2)">印刷 / 表面 <span class="pend">费率待核对</span></div>
          <div class="printrow" id="printrow"></div>
        </div>
        <div id="compat-panel" style="display:none">
          <div class="gname mono" style="font-size:.72rem;color:var(--accent2)">🔧 兼容参考 · 能替这个件用的（点一下切过去）</div>
          <div class="hint">✅同套系配套 · 🟡同口径可互换 · ⚠️需确认 —— 判定同 compat 逻辑</div>
          <div class="compat-list" id="compat-list"></div>
        </div>
        <div class="row2">
          <label class="f">数量 (个)<input type="number" id="q-qty" value="10000" step="1000" min="1"></label>
          <div class="preview" style="justify-content:center">
            <div class="l"><span>工厂基准单价</span><span class="mono" id="pv-base">—</span></div>
            <div class="l"><span>报价单价 (含加成)</span><span class="unit" id="pv-unit">—</span></div>
          </div>
        </div>
        <button class="btn pri" id="add-btn">＋ 加入报价单</button>
      </div>
    </section>

    <!-- 报价单 -->
    <section class="card" id="quote-card">
      <h2>报价单 <span class="k" id="q-count">0 项</span></h2>
      <div id="lines-wrap">
        <div class="empty" id="empty">还没有产品。左侧配置好后点「加入报价单」。</div>
        <table class="quote-lines" id="lines" style="display:none">
          <thead><tr><th>产品 / 配置</th><th class="num">数量</th><th class="num">单价</th><th class="num">金额</th><th></th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="totals" id="totals" style="display:none">
        <div class="l"><span>合计数量</span><span class="mono" id="t-qty">0</span></div>
        <div class="l"><span>加成前工厂价小计</span><span class="mono" id="t-factory">—</span></div>
        <div class="l big"><span>报价总额 <span id="t-cur">¥</span></span><span class="v" id="t-total">—</span></div>
      </div>
      <div class="terms" id="terms" style="display:none">
        <div>MOQ 5,000 起 · 价格随数量分档 (≥20,000 / ≥50,000 更优<span class="pend">待核对</span>)</div>
        <div>付款 30% 定金 / 70% T/T 见提单 · FOB 广州 · 报价有效期 30 天</div>
        <div>加成/数量折扣/印刷费为占位口径，正式报价前需与李记核对</div>
      </div>
      <div class="actions noprint" id="actions" style="display:none">
        <button class="btn pri" onclick="printQuote()">打印 / 导出 PDF</button>
        <button class="btn" id="copy-btn">复制文本报价</button>
        <button class="btn sm" id="clear-btn">清空</button>
      </div>
    </section>
  </div>
  <footer>数据源：pricing.db（100 个 Excel · <span id="stat-rows"></span>）· 自包含离线可用 · 阶段3 报价计算器 POC</footer>
</div></div>
<script>
const DB = /*__DATA__*/;
const CUR = {CNY:'¥',USD:'$',EUR:'€'};
const st = {coll:null, prod:null, sel:{}, print:{}, markup:DB.rules.markups[0], cur:'CNY', fx:7.2, cart:[]};

const $=id=>document.getElementById(id);
const money=(v)=>{ if(st.cur==='CNY') return '¥'+v.toFixed(2);
  const f=parseFloat($('g-fx').value)||1; return CUR[st.cur]+(v/f).toFixed(2); };

// init globals
DB.rules.markups.forEach((m,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${m.tier} 档 · +${m.pct}%`;$('g-markup').appendChild(o);});
$('stat-coll').textContent = DB.collections.length+' 个套系/类别';
let totalRows=0; Object.values(DB.products).forEach(a=>a.forEach(e=>e.groups.forEach(g=>totalRows+=g.opts.length)));
$('stat-rows').textContent = totalRows.toLocaleString()+' 条工艺报价';

// fees / print steppers
Object.entries(DB.rules.fees).forEach(([name,f])=>{
  st.print[name]=0;
  const w=document.createElement('div');w.className='stepper';
  w.innerHTML=`<span>${name} ¥${f.fee}/${f.unit}</span>
    <button class="btn mini" data-n="${name}" data-d="-1">−</button><b id="pc-${name}">0</b>
    <button class="btn mini" data-n="${name}" data-d="1">＋</button>`;
  $('printrow').appendChild(w);
});
$('printrow').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  const n=b.dataset.n; st.print[n]=Math.max(0,(st.print[n]||0)+ (+b.dataset.d)); $('pc-'+n).textContent=st.print[n]; renderPreview();});

// collections + 搜索
const codeIndex={};
Object.entries(DB.products).forEach(([cid,ents])=>ents.forEach(e=>{
  const k=e.code.toUpperCase();(codeIndex[k]=codeIndex[k]||[]).push(cid);}));
function renderCollOptions(f){
  f=(f||'').trim().toUpperCase();
  const sel=$('sel-coll');sel.innerHTML='';
  let list=DB.collections;
  if(f) list=DB.collections.filter(cl=>{
    if((cl.id+' '+cl.label+' '+(cl.sup||'')).toUpperCase().includes(f)) return true;
    return DB.products[cl.id].some(e=>e.code.toUpperCase().includes(f));
  });
  if(!list.length){const o=document.createElement('option');o.textContent='— 无匹配 —';sel.appendChild(o);
    $('groups').innerHTML='';$('prod-meta').textContent='';$('pv-base').textContent='—';$('pv-unit').textContent='—';st.prod=null;return;}
  list.forEach(cl=>{const o=document.createElement('option');o.value=cl.id;
    o.textContent=`${cl.label}${cl.sup?' · '+cl.sup:''} (${cl.n})`;sel.appendChild(o);});
  setColl(list[0].id, f);
}
function setColl(id, codeHint){st.coll=id;const ps=DB.products[id];$('sel-prod').innerHTML='';
  ps.forEach((e,i)=>{const o=document.createElement('option');o.value=i;
    o.textContent=`${e.code}${e.cap?' · '+e.cap:''}`;$('sel-prod').appendChild(o);});
  let pi=0;
  if(codeHint){const j=ps.findIndex(e=>e.code.toUpperCase().includes(codeHint));if(j>=0)pi=j;}
  $('sel-prod').value=pi;setProd(pi);}
function setProd(i){st.prod=DB.products[st.coll][i];st.sel={};
  const e=st.prod;
  const neck=e.neck?` · <span class="chip">口径 ${e.neck}</span>`:'';
  $('prod-meta').innerHTML=`<b class="mono">${e.code}</b> ${e.cap||''} ${e.sup?'· 供应商 '+e.sup:''} · ${e.groups.length} 个部件${neck}`;
  const img=DB.imgmap[e.code];const t=$('thumb');
  if(img){t.src=img;t.className='thumb';t.style.display='';}else{t.className='thumb ph';t.removeAttribute('src');t.textContent='无图';}
  const gc=$('groups');gc.innerHTML='';
  e.groups.forEach((g,gi)=>{st.sel[gi]=0;
    const d=document.createElement('div');d.className='group';
    const opts=g.opts.map((o,oi)=>`<option value="${oi}">${o.d} — ¥${o.p.toFixed(2)}</option>`).join('');
    d.innerHTML=`<span class="gname">${g.name}${g.opts.length>1?' · '+g.opts.length+'档':''}</span>
      <select data-gi="${gi}">${opts}</select>`;
    gc.appendChild(d);});
  gc.querySelectorAll('select').forEach(s=>s.addEventListener('change',ev=>{st.sel[ev.target.dataset.gi]=+ev.target.value;renderPreview();}));
  renderPreview(); renderCompat(e.code);}

// ---- 兼容性（逻辑与 compat.py 一致）----
const SP=DB.specs||{}, OV=DB.overrides||[];
const RLq={pump:'泵头',cap:'盖',cover:'外罩',dropper:'滴管',sleeve:'肩套',plug:'内塞',liner:'垫片',bottle:'瓶',other:'件'};
const BADc={yes:'✅',likely:'🟡',caution:'⚠️',no:'❌',unknown:'❔'}, RANKv={yes:0,likely:1,caution:2};
function ovL(a,b){for(const o of OV){if((o[0]===a&&o[1]===b)||(o[0]===b&&o[1]===a))return o;}return null;}
function resolveC(a,b){const sa=SP[a],sb=SP[b];if(!sa||!sb)return{v:'unknown'};
  const o=ovL(a,b);if(o)return{v:o[2]==='yes'?'yes':'no'};
  const common=sa.s.filter(x=>sb.s.includes(x)),na=sa.n,nb=sb.n;
  if(common.length&&na&&nb&&na!==nb)return{v:'caution'};
  if(common.length)return{v:'yes'};
  if(na&&nb)return na===nb?{v:'likely'}:{v:'no'};
  return{v:'unknown'};}
function renderCompat(code){
  const s=SP[code], panel=$('compat-panel'), box=$('compat-list');
  if(!s){panel.style.display='none';return;}
  const cand=[];
  Object.keys(SP).forEach(o=>{if(o===code||!codeIndex[o])return;const t=SP[o];
    const ser=t.s.some(x=>s.s.includes(x)), nk=s.n&&t.n===s.n;
    if(ser||nk){const r=resolveC(code,o);if(r.v in RANKv)cand.push({o,v:r.v});}});
  cand.sort((a,b)=>RANKv[a.v]-RANKv[b.v]);
  const top=cand.slice(0,8);
  if(!top.length){panel.style.display='none';return;}
  panel.style.display='';
  box.innerHTML=top.map(x=>{const t=SP[x.o],coll=codeIndex[x.o][0];
    return `<div class="crow" data-code="${x.o}"><span>${BADc[x.v]} <span class="c">${x.o}</span>
      <span class="m"> ${RLq[t.r]||''}${t.n?' 口径'+t.n:''} · ${coll==='__single__'?'单品':coll}</span></span>
      <span class="m">切换 ›</span></div>`;}).join('');
  box.querySelectorAll('.crow').forEach(el=>el.addEventListener('click',()=>{
    const cc=el.dataset.code; $('coll-search').value=cc; renderCollOptions(cc);
    document.querySelector('.card').scrollIntoView({behavior:'smooth',block:'start'});}));
}

function unitBase(){let s=0;st.prod.groups.forEach((g,gi)=>s+=g.opts[st.sel[gi]||0].p);return s;}
function printFee(){let s=0;Object.entries(st.print).forEach(([n,c])=>s+=c*(DB.rules.fees[n].fee));return s;}
function factory(){return unitBase()+printFee();}
function unitQuote(){return factory()*(1+st.markup.pct/100);}

function renderPreview(){
  if(!st.prod)return;
  $('pv-base').textContent=money(factory());
  $('pv-unit').textContent=money(unitQuote());
}

// cart
$('add-btn').addEventListener('click',()=>{
  if(!st.prod)return;
  const cfg=st.prod.groups.map((g,gi)=>g.opts[st.sel[gi]||0].d).join(' + ');
  const prints=Object.entries(st.print).filter(([n,c])=>c>0).map(([n,c])=>`${n}×${c}`).join(' ');
  st.cart.push({coll:st.coll,code:st.prod.code,cap:st.prod.cap,cfg,prints,
    base:factory(), qty:Math.max(1,parseInt($('q-qty').value)||1)});
  renderCart();
});
function renderCart(){
  const tb=$('lines').querySelector('tbody');tb.innerHTML='';
  const has=st.cart.length>0;
  $('empty').style.display=has?'none':'';$('lines').style.display=has?'':'none';
  ['totals','terms','actions'].forEach(k=>$(k).style.display=has?'':'none');
  $('q-count').textContent=st.cart.length+' 项';
  let tot=0,tq=0,tf=0;
  st.cart.forEach((l,idx)=>{
    const unit=l.base*(1+st.markup.pct/100), amt=unit*l.qty;
    tot+=amt;tq+=l.qty;tf+=l.base*l.qty;
    const collLabel=l.coll==='__single__'?'单品':l.coll;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><b class="mono">${collLabel} · ${l.code}</b> ${l.cap||''}
        <div class="cfg">${l.cfg}${l.prints?' · 印刷 '+l.prints:''}</div></td>
      <td class="num">${l.qty.toLocaleString()}</td>
      <td class="num">${money(unit)}</td>
      <td class="num">${money(amt)}</td>
      <td class="x" data-i="${idx}" title="删除">✕</td>`;
    tb.appendChild(tr);
  });
  $('t-qty').textContent=tq.toLocaleString();
  $('t-factory').textContent=money(tf);
  $('t-total').textContent=money(tot);
  $('t-cur').textContent=CUR[st.cur];
  tb.querySelectorAll('.x').forEach(x=>x.addEventListener('click',()=>{st.cart.splice(+x.dataset.i,1);renderCart();}));
}
$('lines').addEventListener('click',()=>{});

// global controls
$('coll-search').addEventListener('input',e=>renderCollOptions(e.target.value));
$('sel-coll').addEventListener('change',e=>setColl(e.target.value));
$('sel-prod').addEventListener('change',e=>setProd(+e.target.value));
$('g-markup').addEventListener('change',e=>{st.markup=DB.rules.markups[+e.target.value];renderPreview();renderCart();});
$('g-cur').addEventListener('change',e=>{st.cur=e.target.value;$('fx-wrap').style.display=st.cur==='CNY'?'none':'';renderPreview();renderCart();});
$('g-fx').addEventListener('input',()=>{renderPreview();renderCart();});
$('q-qty').addEventListener('input',renderPreview);
$('clear-btn').addEventListener('click',()=>{st.cart=[];renderCart();});
// 打印/导出：另开一个干净的报价单文档（CJK 安全字体，避免打印时中文丢失 & 版面乱）
function printQuote(){
  if(!st.cart.length){toast('报价单是空的，先加产品');return;}
  let rows='',tot=0,tq=0;
  st.cart.forEach((l,i)=>{
    const unit=l.base*(1+st.markup.pct/100), amt=unit*l.qty; tot+=amt; tq+=l.qty;
    const coll=l.coll==='__single__'?'单品':l.coll;
    rows+=`<tr><td class="c">${i+1}</td><td><b>${coll} · ${l.code}</b> ${l.cap||''}<div class="cfg">${l.cfg}${l.prints?' · 印刷 '+l.prints:''}</div></td><td class="n">${l.qty.toLocaleString()}</td><td class="n">${money(unit)}</td><td class="n">${money(amt)}</td></tr>`;
  });
  const dt=new Date(), pad=n=>String(n).padStart(2,'0');
  const today=`${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}`;
  const doc=`<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>李记包装报价单 ${today}</title><style>
*{box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB","Heiti SC",system-ui,sans-serif;color:#1a1c20;margin:0;padding:34px;font-size:13px;line-height:1.5}
.hd{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #b06a2c;padding-bottom:12px}
.co{font-size:21px;font-weight:800;color:#b06a2c;letter-spacing:.02em}
.co small{display:block;font-size:10px;color:#999;letter-spacing:.28em;font-weight:500;margin-top:3px}
.meta{text-align:right;font-size:12px;color:#555;line-height:1.9} .meta b{color:#1a1c20}
table.items{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:18px}
table.items th{text-align:left;background:#f6f2ea;border:1px solid #e6e0d5;padding:8px 10px;font-weight:700;font-size:11px;letter-spacing:.03em}
table.items td{border:1px solid #e6e0d5;padding:8px 10px;vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap} td.c{text-align:center;color:#999}
.cfg{color:#7a7a7a;font-size:11px;margin-top:3px}
.tot{margin-top:16px;display:flex;justify-content:flex-end}
.tot table{border-collapse:collapse} .tot td{padding:4px 12px;font-size:13px} .tot td.n{text-align:right}
.tot .big td{font-size:18px;font-weight:800;color:#b06a2c;border-top:2px solid #b06a2c;padding-top:9px}
.terms{margin-top:22px;font-size:11.5px;color:#666;line-height:1.9;border-top:1px solid #eee;padding-top:12px}
@media print{@page{margin:14mm}body{padding:0}}
</style></head><body>
<div class="hd"><div class="co">李记包装<small>LEEKEE PACKAGING</small></div>
<div class="meta">报价单 · QUOTATION<br>日期 <b>${today}</b><br>客户加成 <b>${st.markup.tier} 档 (+${st.markup.pct}%)</b></div></div>
<table class="items"><thead><tr><th class="c">#</th><th>产品 / 配置</th><th class="n">数量</th><th class="n">单价</th><th class="n">金额</th></tr></thead><tbody>${rows}</tbody></table>
<div class="tot"><table><tr><td>合计数量</td><td class="n">${tq.toLocaleString()} 件</td></tr>
<tr class="big"><td>报价总额</td><td class="n">${money(tot)}</td></tr></table></div>
<div class="terms">MOQ 5,000 起 · 价格随数量分档（≥20,000 / ≥50,000 更优）<br>
付款 30% 定金 / 70% T/T 见提单 · FOB 广州 · 报价有效期 30 天<br>
注：加成 / 数量折扣 / 印刷费为占位口径，正式报价前需与李记核对。</div>
</body></html>`;
  const w=window.open('','_blank');
  if(!w){toast('请允许弹出窗口以导出报价单');return;}
  w.document.write(doc); w.document.close(); w.focus();
  setTimeout(()=>{ w.print(); }, 300);
}

$('copy-btn').addEventListener('click',()=>{
  let t='李记包装 报价单\n客户加成: '+st.markup.tier+' 档 +'+st.markup.pct+'%\n\n';
  st.cart.forEach((l,i)=>{const unit=l.base*(1+st.markup.pct/100);
    t+=`${i+1}. ${l.coll==='__single__'?'单品':l.coll} ${l.code} ${l.cap||''}\n   ${l.cfg}\n   ${l.qty} 个 × ${money(unit)} = ${money(unit*l.qty)}\n`;});
  const tot=st.cart.reduce((s,l)=>s+l.base*(1+st.markup.pct/100)*l.qty,0);
  t+='\n总额: '+money(tot)+'\n付款 30/70 · FOB 广州 · 有效期30天';
  navigator.clipboard.writeText(t).then(()=>{$('copy-btn').textContent='已复制 ✓';setTimeout(()=>$('copy-btn').textContent='复制文本报价',1500);});
});

// boot
renderCollOptions('');
renderCart();
</script>'''

html = TEMPLATE.replace('/*__DATA__*/', data_json)
open(os.path.join(D,'quote_app.html'),'w',encoding='utf-8').write(html)
# 同时导出「服务端注入用模板」(保留 /*__DATA__*/ 占位)，供 app/main.py 现场注入实时数据
tpl_dir = os.path.join(os.path.dirname(D), 'app', 'templates')
if os.path.isdir(tpl_dir):
    open(os.path.join(tpl_dir, 'quote.tpl.html'), 'w', encoding='utf-8').write(TEMPLATE)
    print("template ->", os.path.join(tpl_dir, 'quote.tpl.html'))
print("written", len(html), "bytes ·", len(collections), "collections ·", len(imgmap), "imgs")
