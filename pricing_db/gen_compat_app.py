#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 compat_app.html —— 可视化兼容性检查（Artifact body）。逻辑与 compat.py 一致，全部前端计算。"""
import sqlite3, os, json
D = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(D,'pricing.db')); c = con.cursor()

parts = {}
for code, role, neck, forms, series, vol in c.execute(
        "SELECT code,role,neck_dia,neck_forms,series_list,volume_ml FROM part_specs"):
    parts[code] = {'r':role,'n':neck,'f':forms,'s':(series.split(';') if series else []),'v':vol}
ov = [[a,b,v,r,au] for a,b,v,r,au in c.execute(
        "SELECT code_a,code_b,verdict,reason,author FROM compat_overrides")]

# 统计
n_series_pairs = c.execute("""SELECT COALESCE(SUM(n*(n-1)/2),0) FROM
    (SELECT series_code,COUNT(DISTINCT product_code) n FROM price_items
     WHERE series_code IS NOT NULL AND product_code IS NOT NULL GROUP BY series_code)""").fetchone()[0]
n_sub = c.execute("SELECT COUNT(*)/2 FROM v_substitute").fetchone()[0]
n_neck = c.execute("SELECT COUNT(*) FROM part_specs WHERE neck_dia IS NOT NULL").fetchone()[0]
con.close()

DATA = {'parts':parts,'overrides':ov,
        'stat':{'n':len(parts),'series':int(n_series_pairs),'sub':int(n_sub),'neck':n_neck}}
data_json = json.dumps(DATA, ensure_ascii=False, separators=(',',':'))

TEMPLATE = r'''<title>李记包装 · 兼容性检查</title>
<style>
:root{--bg:#f3f4f6;--surface:#fff;--surface2:#eceef2;--ink:#191c21;--ink2:#5c626c;--line:#dbdee4;
  --accent:#b06a2c;--accent2:#8a5220;--soft:rgba(176,106,44,.11);--good:#2f7d5b;--warn:#b5791f;--bad:#b23a2e;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;}
@media (prefers-color-scheme:dark){:root{--bg:#131519;--surface:#1b1e23;--surface2:#22262d;--ink:#e6e8ec;--ink2:#98a0ab;--line:#2c313a;--accent:#d8964f;--accent2:#e6ac6c;--soft:rgba(216,150,79,.14);--good:#54ab82;--warn:#d3a24a;--bad:#dd6a5c;}}
:root[data-theme="dark"]{--bg:#131519;--surface:#1b1e23;--surface2:#22262d;--ink:#e6e8ec;--ink2:#98a0ab;--line:#2c313a;--accent:#d8964f;--accent2:#e6ac6c;--soft:rgba(216,150,79,.14);--good:#54ab82;--warn:#d3a24a;--bad:#dd6a5c;}
:root[data-theme="light"]{--bg:#f3f4f6;--surface:#fff;--surface2:#eceef2;--ink:#191c21;--ink2:#5c626c;--line:#dbdee4;--accent:#b06a2c;--accent2:#8a5220;--soft:rgba(176,106,44,.11);--good:#2f7d5b;--warn:#b5791f;--bad:#b23a2e;}
*{box-sizing:border-box}
.wrap{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;padding:clamp(14px,3vw,34px);min-height:100vh;-webkit-font-smoothing:antialiased}
.inner{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.eyebrow{font-family:var(--mono);font-size:.7rem;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-size:clamp(1.5rem,3vw,2.1rem);margin:.1em 0 0;letter-spacing:-.01em;font-weight:680}
.lede{color:var(--ink2);margin:.2em 0 0;font-size:.92rem;max-width:72ch}
.head-row{border-bottom:1px solid var(--line);padding-bottom:12px}
.statline{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.pill{font-family:var(--mono);font-size:.72rem;background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:3px 11px;color:var(--ink2)}
.pill b{color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:13px;overflow:hidden}
.card>h2{font-size:.95rem;margin:0;padding:13px 16px;border-bottom:1px solid var(--line);background:var(--surface2);display:flex;justify-content:space-between;align-items:center}
.card>h2 .k{font-family:var(--mono);font-size:.68rem;color:var(--ink2);letter-spacing:.08em;font-weight:400}
.body{padding:16px;display:flex;flex-direction:column;gap:14px}
label.f{display:flex;flex-direction:column;gap:4px;font-size:.7rem;color:var(--ink2);font-family:var(--mono);letter-spacing:.04em;text-transform:uppercase}
input{font-family:var(--mono);font-size:.92rem;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:9px 11px}
input:focus{outline:2px solid var(--accent);outline-offset:0}
.pair{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:end}
.pair .vs{font-family:var(--mono);color:var(--ink2);padding-bottom:10px}
@media(max-width:640px){.pair{grid-template-columns:1fr;}.pair .vs{text-align:center;padding:0}}
.verdict{border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;gap:8px;border:1px solid var(--line);background:var(--surface)}
.verdict .badge{font-size:1.35rem;font-weight:700;display:flex;align-items:center;gap:10px}
.verdict .conf{font-family:var(--mono);font-size:.68rem;padding:2px 8px;border-radius:20px;border:1px solid currentColor}
.verdict .reason{font-size:.92rem}
.verdict .specs{display:flex;gap:18px;flex-wrap:wrap;font-size:.76rem;color:var(--ink2);border-top:1px dashed var(--line);padding-top:8px}
.verdict .specs b{color:var(--ink);font-family:var(--mono)}
.v-yes{border-left:4px solid var(--good)} .v-yes .badge{color:var(--good)}
.v-likely{border-left:4px solid var(--accent)} .v-likely .badge{color:var(--accent2)}
.v-caution{border-left:4px solid var(--warn)} .v-caution .badge{color:var(--warn)}
.v-no{border-left:4px solid var(--bad)} .v-no .badge{color:var(--bad)}
.v-unknown{border-left:4px solid var(--ink2)} .v-unknown .badge{color:var(--ink2)}
.exp-meta{font-size:.82rem;color:var(--ink2)}
.exp-meta b{color:var(--ink);font-family:var(--mono)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:720px){.cols{grid-template-columns:1fr}}
.col h3{font-size:.8rem;margin:0 0 8px;display:flex;align-items:center;gap:7px}
.col h3 .dot{width:9px;height:9px;border-radius:50%}
.list{display:flex;flex-direction:column;gap:7px;max-height:340px;overflow-y:auto}
.item{display:flex;justify-content:space-between;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:8px 11px;cursor:pointer;font-size:.82rem}
.item:hover{border-color:var(--accent)}
.item .c{font-family:var(--mono);font-weight:600}
.item .meta{font-size:.7rem;color:var(--ink2);font-family:var(--mono)}
.item .b{font-size:.9rem}
.empty{color:var(--ink2);font-size:.82rem;padding:14px;text-align:center}
.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.leg{display:flex;gap:9px;align-items:flex-start;font-size:.78rem;background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:10px 12px}
.leg .bd{font-size:1rem;flex:none}
.leg .t b{display:block}
.leg .t span{color:var(--ink2)}
.note{font-size:.76rem;color:var(--ink2);background:var(--soft);border:1px dashed var(--accent);border-radius:9px;padding:11px 14px}
footer{color:var(--ink2);font-size:.74rem;text-align:center;padding-top:4px}
</style>
<div class="wrap"><div class="inner">
  <div class="head-row">
    <span class="eyebrow">李记包装 · 兼容性检查 — Compatibility</span>
    <h1>这个能配那个吗？</h1>
    <p class="lede">销售最常问"这个泵能不能配这个瓶 / 这个盖能不能配这个泵"。这里输两个编号立刻给结论 + 理由 + 置信度，
       或选一个件看它能配套/能互换什么。判定逻辑：<b>人工确认 > 同套系 > 同口径 > 未知</b>。</p>
    <div class="statline">
      <span class="pill"><b id="s-n"></b> 个件建了接口指纹</span>
      <span class="pill">同套系可配套 <b id="s-series"></b> 对</span>
      <span class="pill">同口径可互换 <b id="s-sub"></b> 对</span>
      <span class="pill">已解析牙口 <b id="s-neck"></b> 个</span>
    </div>
  </div>

  <datalist id="allcodes"></datalist>

  <!-- 配对检查 -->
  <section class="card">
    <h2>① 配对检查 <span class="k">A ⇄ B</span></h2>
    <div class="body">
      <div class="pair">
        <label class="f">件 A <input id="pa" list="allcodes" placeholder="如 CC20945" autocomplete="off"></label>
        <span class="vs">⇄</span>
        <label class="f">件 B <input id="pb" list="allcodes" placeholder="如 CC20831" autocomplete="off"></label>
      </div>
      <div id="verdict"></div>
    </div>
  </section>

  <!-- 单件浏览 -->
  <section class="card">
    <h2>② 看一个件能配什么 <span class="k">FITS</span></h2>
    <div class="body">
      <label class="f">选一个件<input id="exp" list="allcodes" placeholder="如 CC20945，看它的配套 / 互换件" autocomplete="off"></label>
      <div class="exp-meta" id="exp-meta"></div>
      <div class="cols">
        <div class="col"><h3><span class="dot" style="background:var(--good)"></span>同套系可配套（设计配套 · 高可信）</h3>
          <div class="list" id="companions"></div></div>
        <div class="col"><h3><span class="dot" style="background:var(--accent)"></span>同口径可互换（牙型待核对 · 中可信）</h3>
          <div class="list" id="subs"></div></div>
      </div>
      <div class="note">点任意一个件，会自动填到上面①做配对检查。灰色「未知」的件目前缺牙口数据——正是要跟李记补的部分（显式牙口仅覆盖约 7%）。</div>
    </div>
  </section>

  <section class="card">
    <h2>判定说明 <span class="k">LEGEND</span></h2>
    <div class="body"><div class="legend">
      <div class="leg"><span class="bd">✅</span><span class="t"><b>兼容</b><span>同套系，设计上就配好的</span></span></div>
      <div class="leg"><span class="bd">🟡</span><span class="t"><b>大概率兼容</b><span>同口径，接口能互换（牙型 410/415 待确认）</span></span></div>
      <div class="leg"><span class="bd">⚠️</span><span class="t"><b>需确认</b><span>同套系但口径不同——套系里含多规格</span></span></div>
      <div class="leg"><span class="bd">❌</span><span class="t"><b>不兼容</b><span>口径不同，拧不上</span></span></div>
      <div class="leg"><span class="bd">❔</span><span class="t"><b>未知</b><span>缺牙口数据，需人工确认（可沉淀成规则）</span></span></div>
    </div></div>
  </section>
  <footer>逻辑与 compat.py 一致 · 全部前端计算 · 自包含离线可用 · 阶段4 兼容性骨架</footer>
</div></div>
<script>
const DB = /*__DATA__*/;
const P = DB.parts;
const RL = {pump:'泵头',cap:'盖',cover:'外罩',dropper:'滴管/滴泵',sleeve:'肩套',plug:'内塞',liner:'垫片',bottle:'瓶',other:'其他'};
const $=id=>document.getElementById(id);
$('s-n').textContent=DB.stat.n; $('s-series').textContent=DB.stat.series.toLocaleString();
$('s-sub').textContent=DB.stat.sub; $('s-neck').textContent=DB.stat.neck;

// datalist
const codes=Object.keys(P).sort();
const dl=$('allcodes');
codes.forEach(c=>{const o=document.createElement('option');o.value=c;
  o.label=`${RL[P[c].r]||P[c].r}${P[c].n?' · 口径'+P[c].n:''}${P[c].v?' · '+P[c].v:''}`;dl.appendChild(o);});

function ovLookup(a,b){for(const o of DB.overrides){if((o[0]===a&&o[1]===b)||(o[0]===b&&o[1]===a))return o;}return null;}
function resolve(a,b){
  const sa=P[a],sb=P[b];
  if(!sa||!sb)return{v:'unknown',c:'low',r:'编码不在库中（检查是否输错）'};
  const o=ovLookup(a,b);
  if(o)return{v:o[2]==='yes'?'yes':'no',c:'confirmed',r:`人工确认（${o[4]||'?'}）：${o[3]}`};
  const common=sa.s.filter(x=>sb.s.includes(x));
  const na=sa.n,nb=sb.n;
  if(common.length&&na&&nb&&na!==nb)return{v:'caution',c:'medium',r:`同属套系 ${common.join('/')} 但口径不同（${na} vs ${nb}）——套系内不同规格的配件，需确认具体是哪一件`};
  if(common.length)return{v:'yes',c:'high',r:`同套系 ${common.join('/')}（设计配套）`};
  if(na&&nb){if(na===nb)return{v:'likely',c:'medium',r:`同口径 ${na}（${RL[sa.r]}↔${RL[sb.r]}，接口可互换；牙型 410/415 待核对）`};
    return{v:'no',c:'medium',r:`口径不同：${na} vs ${nb}，无法互配`};}
  return{v:'unknown',c:'low',r:'缺牙口数据，建议人工确认（可沉淀成规则）'};
}
const BADGE={yes:'✅ 兼容',likely:'🟡 大概率兼容',caution:'⚠️ 需确认',no:'❌ 不兼容',unknown:'❔ 未知'};
function specLine(code){const s=P[code];if(!s)return '';
  return `<b>${code}</b> · ${RL[s.r]||s.r} · 口径 ${s.n||'—'} · 套系 ${s.s.join('/')||'—'} · ${s.v||''}`;}

function renderCheck(){
  const a=$('pa').value.trim().toUpperCase(), b=$('pb').value.trim().toUpperCase();
  const box=$('verdict');
  if(!a||!b){box.innerHTML='<div class="empty">输入两个编号（或从下面②点选）后显示结论。</div>';return;}
  const r=resolve(a,b);
  box.innerHTML=`<div class="verdict v-${r.v}">
     <div class="badge">${BADGE[r.v]}<span class="conf">置信度 ${r.c}</span></div>
     <div class="reason">${r.r}</div>
     <div class="specs"><span>${specLine(a)||('未找到 '+a)}</span><span>${specLine(b)||('未找到 '+b)}</span></div></div>`;
}
$('pa').addEventListener('input',renderCheck);
$('pb').addEventListener('input',renderCheck);

function renderExplore(){
  const a=$('exp').value.trim().toUpperCase();
  const s=P[a];
  if(!s){$('exp-meta').textContent=a?('未找到编码 '+a):'';$('companions').innerHTML='';$('subs').innerHTML='';return;}
  $('exp-meta').innerHTML=`已选 ${specLine(a)}`;
  // 候选：同套系 companions + 同口径 subs
  const comp=[],sub=[];
  for(const code of codes){if(code===a)continue;const t=P[code];
    if(t.s.some(x=>s.s.includes(x))) comp.push(code);
    if(s.n&&t.n===s.n) sub.push(code);}
  const card=(code)=>{const r=resolve(a,code);const t=P[code];
    return `<div class="item" data-code="${code}"><span><span class="c">${code}</span>
      <span class="meta"> ${RL[t.r]||t.r}${t.n?' · 口径'+t.n:''}${t.v?' · '+t.v:''}</span></span>
      <span class="b" title="${r.r}">${BADGE[r.v].split(' ')[0]}</span></div>`;};
  $('companions').innerHTML=comp.length?comp.map(card).join(''):'<div class="empty">无同套系记录</div>';
  $('subs').innerHTML=sub.length?sub.map(card).join(''):'<div class="empty">无同口径记录（该件缺牙口数据）</div>';
  document.querySelectorAll('#companions .item,#subs .item').forEach(el=>el.addEventListener('click',()=>{
    $('pa').value=a;$('pb').value=el.dataset.code;renderCheck();
    $('verdict').scrollIntoView({behavior:'smooth',block:'center'});}));
}
$('exp').addEventListener('input',renderExplore);

// 示例开局
$('pa').value='CC20945';$('pb').value='CC20831';renderCheck();
$('exp').value='CC20945';renderExplore();
</script>'''

html = TEMPLATE.replace('/*__DATA__*/', data_json)
open(os.path.join(D,'compat_app.html'),'w',encoding='utf-8').write(html)
print("written", len(html), "bytes ·", len(parts), "parts ·", len(ov), "overrides")
