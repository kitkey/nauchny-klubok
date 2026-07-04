// ============================================================================
// Граф знаний R&D — приложение (граф, поиск, аналитика, ИИ-чат)
// Данные подключаются из data.js (NODES, EDGES, PROPS, GROUPS, G_RU, ET_RU)
// ============================================================================

// ── Конфиг бэкенда (чат/поиск идут в наш API по полному графу) ────────────
const P2KG_API = '';   // тот же origin
const P2KG_GID = new URLSearchParams(location.search).get('gid') || 'd1d829a8c132';

// ── Индексы ──────────────────────────────────────────────────────────────
const N_BY_ID = Object.create(null);
NODES.forEach(n => { N_BY_ID[n.id] = n; });
const ADJ = Object.create(null);
EDGES.forEach((e, i) => {
  if (!ADJ[e.from]) ADJ[e.from] = [];
  if (!ADJ[e.to])   ADJ[e.to]   = [];
  ADJ[e.from].push({to: e.to, type: e.type, eid: i, dir:'out'});
  ADJ[e.to].push({to: e.from, type: e.type, eid: i, dir:'in'});
});

// ── Тематические кластеры (для «папок» на графе и дашборда географии) ────
// Кластер кодируется в id публикаций (pub_a1, pub_b1, ...) и в поле
// PROPS[id].source остальных узлов (обычно совпадает с id публикации).
const CLUSTER_DEFS = [
  {key:'A', label:'Электроэкстракция Ni/Cu'},
  {key:'B', label:'Штейн/шлак — Au, Ag, МПГ'},
  {key:'C', label:'Кучное выщелачивание'},
  {key:'D', label:'Очистка шахтных вод'},
  {key:'E', label:'Сульфаты Ni/Co, SO2, шлаки'},
  {key:'F', label:'Переработка штейнов'}
];
const CLUSTER_LABEL = Object.fromEntries(CLUSTER_DEFS.map(d=>[d.key,d.label]));
CLUSTER_LABEL.X = 'Прочее';
function nodeFolderKey(n){
  const m1 = /^pub_([a-f])\d*$/.exec(n.id);
  if(m1) return m1[1].toUpperCase();
  const src = (PROPS[n.id]||{}).source || '';
  const m2 = /pub_([a-f])\d*/.exec(src);
  return m2 ? m2[1].toUpperCase() : 'X';
}
NODES.forEach(n => { n._folder = nodeFolderKey(n); });

// ── vis-network ──────────────────────────────────────────────────────────
const EDGE_COLORS = {
  USES_MATERIAL:'#ff9f0a', OPERATES_AT_CONDITION:'#ffd60a', PRODUCES_OUTPUT:'#30d158',
  DESCRIBED_IN:'#8e8e93', VALIDATED_BY:'#64d2ff', CONTRADICTS:'#d70c1e',
  HAS_PROPERTY:'#5e5ce6', USES_EQUIPMENT:'#0290f0', AUTHORED_BY:'#ff375f',
  WORKS_AT:'#ac8e68', PART_OF:'#8d6e63', MENTIONS:'#4fc3f7', APPLIES_TO:'#bf5af2'
};
const nodesDS = new vis.DataSet(NODES);
const edgesDS = new vis.DataSet(EDGES.map((e, i) => ({id: i, ...e, color:{color:(EDGE_COLORS[e.type]||'#888')+'55', highlight:EDGE_COLORS[e.type]||'#fff', hover:EDGE_COLORS[e.type]||'#fff'}, width: e.type==='CONTRADICTS'?2.5:1})));
const net = new vis.Network(document.getElementById('net'), {nodes: nodesDS, edges: edgesDS}, {
  groups: GROUPS,
  nodes: {font: {color: '#fff', size: 12, face: '-apple-system,Inter,sans-serif'}, borderWidth:2},
  edges: {
    arrows: 'to', smooth: {type: 'continuous'}, color:{color:'rgba(255,255,255,0.18)', highlight:'#0290f0', hover:'#3fb0ff'},
    font: {size: 0, color: 'rgba(235,235,245,0.5)', strokeWidth: 0, face: '-apple-system,sans-serif'}, label: ''
  },
  physics: {
    barnesHut: {gravitationalConstant: -9000, springLength: 130, avoidOverlap: 0.35},
    stabilization: {iterations: 250, updateInterval: 10}, adaptiveTimestep: true
  },
  interaction: {hover: true, tooltipDelay: 180, dragNodes: true}
});

net.on('stabilizationProgress', p => {
  const pct = Math.round(p.iterations / p.total * 100);
  document.getElementById('loading-bar').style.width = pct + '%';
  document.getElementById('loading-text').textContent = 'Выстраиваю граф... ' + pct + '%';
});
net.once('stabilizationIterationsDone', () => {
  document.getElementById('loading').style.display = 'none';
  net.setOptions({physics: false});
  physicsOn = false;
  document.getElementById('btn-phy').classList.remove('on');
});

// ── Состояние ────────────────────────────────────────────────────────────
let physicsOn = true, mentionsOn = true, edgeLabelsOn = false;
let currentNodeId = null, clusterActive = false, _st = null;
let geoFilter = 'all'; // 'all' | 'RU' | 'world'
const hiddenET = new Set(), activeGF = new Set();
let compareList = [];

// ── Утилиты ──────────────────────────────────────────────────────────────
function esc(s) { return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function nodeColor(id) { return GROUPS[N_BY_ID[id]?.group]?.color?.background || '#888'; }
function nodeName(id) { const n=N_BY_ID[id], pr=PROPS[id]||{}; return n?.label||pr.name||pr.statement||id; }
function nodeGeo(id) { return (PROPS[id]||{}).geography || ''; }
function geoLabel(g){ return g==='RU'?'РФ':g==='world'?'Мир':g==='RU+world'?'РФ + мир':g||'—'; }
function geoBadgeColor(g){ return g==='RU'?'#30d158':g==='world'?'#0290f0':g==='RU+world'?'#bf5af2':'#8e8e93'; }
function confColor(c){
  if(c==='подтверждено') return '#30d158';
  if(c==='предварительно') return '#ffd60a';
  if(c==='гипотеза') return '#ff9f0a';
  if(c==='противоречиво') return '#d70c1e';
  return '#8e8e93';
}
function fmtRange(pr){
  if(pr.min!=null && pr.max!=null) return pr.min+'–'+pr.max+(pr.unit?' '+pr.unit:'');
  if(pr.value!=null) return pr.value+(pr.unit?' '+pr.unit:'');
  return '';
}

// ── Контролы графа ───────────────────────────────────────────────────────
function togglePhysics() {
  physicsOn = !physicsOn;
  net.setOptions({physics: {enabled: physicsOn}});
  document.getElementById('btn-phy').classList.toggle('on', physicsOn);
}
function fitGraph() { net.fit({animation:{duration:600,easingFunction:'easeInOutQuad'}}); }
function toggleMentions() {
  mentionsOn=!mentionsOn;
  const upd=[];
  edgesDS.forEach(e=>{ if(e.type==='MENTIONS') upd.push({id:e.id,hidden:!mentionsOn}); });
  edgesDS.update(upd);
  document.getElementById('btn-men').classList.toggle('on',mentionsOn);
}
function toggleEdgeLabels() {
  edgeLabelsOn=!edgeLabelsOn;
  const btn=document.getElementById('btn-elbl');
  btn.classList.toggle('on',edgeLabelsOn);
  btn.innerHTML=icon('tag')+' Обновляю...';
  setTimeout(()=>{
    const upd=[];
    edgesDS.forEach(e=>{ upd.push({id:e.id,label:edgeLabelsOn?(ET_RU[e.type]||e.type):''}); });
    edgesDS.update(upd);
    net.setOptions({edges:{font:{size:edgeLabelsOn?9:0}}});
    btn.innerHTML=icon('tag')+' '+(edgeLabelsOn?'Скрыть подписи':'Подписи рёбер');
  },10);
}
function toggleET(row) {
  const et=row.dataset.et;
  if(hiddenET.has(et)){hiddenET.delete(et);row.classList.remove('off');}
  else{hiddenET.add(et);row.classList.add('off');}
  const hide=hiddenET.has(et);
  const upd=[];
  edgesDS.forEach(e=>{ if(e.type===et) upd.push({id:e.id,hidden:hide}); });
  edgesDS.update(upd);
}

// ── Фильтры (тип узла + география) ──────────────────────────────────────
function passesGeo(id){
  if(geoFilter==='all') return true;
  const g = nodeGeo(id);
  if(!g) return true;
  return g===geoFilter || g==='RU+world';
}
function applyNF() {
  nodesDS.update(NODES.map(n=>{
    const typeHidden = activeGF.size>0 && !activeGF.has(n.group);
    const geoHidden = !passesGeo(n.id);
    const hidden = typeHidden||geoHidden;
    // Hidden nodes must be pulled out of the physics solver too, otherwise
    // BarnesHut keeps computing forces on off-screen nodes and perturbs the
    // visible layout the next time physics runs.
    return {id:n.id, hidden, physics: !hidden};
  }));
}
function toggleGF(group,chip) {
  if(activeGF.has(group)){activeGF.delete(group);chip.classList.remove('on');chip.classList.add('dim');}
  else{activeGF.add(group);chip.classList.add('on');chip.classList.remove('dim');}
  applyNF();
}
function setGeoFilter(g, btn){
  geoFilter = g;
  document.querySelectorAll('.geo-chip').forEach(c=>c.classList.remove('on'));
  btn.classList.add('on');
  applyNF();
}
function clearAll() {
  activeGF.clear(); geoFilter='all';
  document.querySelectorAll('.fc').forEach(c=>c.classList.remove('on','dim'));
  document.querySelectorAll('.geo-chip').forEach(c=>c.classList.remove('on'));
  document.getElementById('geo-all')?.classList.add('on');
  document.getElementById('q').value='';
  nodesDS.update(NODES.map(n=>({id:n.id,hidden:false,physics:true,size:undefined,color:undefined})));
}

// ── Поиск ────────────────────────────────────────────────────────────────
function onSearch(val) { clearTimeout(_st); _st=setTimeout(()=>_applySearch(val),260); }
function _applySearch(val) {
  const t=val.trim().toLowerCase();
  if(!t){nodesDS.update(NODES.map(n=>({id:n.id,size:undefined,color:undefined}))); return;}
  nodesDS.update(NODES.map(n=>{
    const hit=(n.label||'').toLowerCase().includes(t)||((PROPS[n.id]?.name||PROPS[n.id]?.statement||'')).toLowerCase().includes(t);
    return hit?{id:n.id,size:20,color:undefined}:{id:n.id,size:4,color:{background:'rgba(255,255,255,0.04)',border:'rgba(255,255,255,0.07)'}};
  }));
}
function jumpSearch() {
  const t=(document.getElementById('q').value||'').trim().toLowerCase();
  if(!t) return;
  const hit=NODES.find(n=>(n.label||'').toLowerCase().includes(t)||((PROPS[n.id]?.name||PROPS[n.id]?.statement||'')).toLowerCase().includes(t));
  if(hit) showNode(hit.id,true);
}

// ── Детали узла ──────────────────────────────────────────────────────────
function resolveSource(src){
  if(!src) return '';
  // source may be a single node id, a comma-separated list of node ids, or a literal citation string
  const parts = src.split(',').map(s=>s.trim());
  const resolved = parts.map(p=>{
    if(PROPS[p]){
      const pr=PROPS[p]; const code=pr.code?(' ('+pr.code+')'):'';
      return (pr.name||p)+code;
    }
    return p;
  });
  return resolved.join('; ');
}
function verificationBadgeHTML(pr){
  if(!pr.confidence && !pr.source) return '';
  const cc = confColor(pr.confidence);
  const gg = geoBadgeColor(pr.geography);
  return '<div class="verif-row">' +
    (pr.confidence?'<span class="vbadge" style="background:'+cc+'22;color:'+cc+';border-color:'+cc+'55">'+esc(pr.confidence)+(pr.n_sources?' · '+pr.n_sources+' ист.':'')+'</span>':'') +
    (pr.geography?'<span class="vbadge" style="background:'+gg+'22;color:'+gg+';border-color:'+gg+'55">'+esc(geoLabel(pr.geography))+'</span>':'') +
    (pr.date?'<span class="vbadge vb-date">'+esc(pr.date)+'</span>':'') +
    '</div>' +
    (pr.source?'<div class="src-line">Источник: '+esc(resolveSource(pr.source))+'</div>':'');
}
function showNode(id, focus) {
  const pr=PROPS[id]; if(!pr) return;
  currentNodeId=id;
  net.selectNodes([id]);
  if(focus) net.focus(id,{scale:1.25,animation:{duration:500,easingFunction:'easeInOutQuad'}});
  const n=N_BY_ID[id], grp=n?.group||'', color=GROUPS[grp]?.color?.background||'#888', grpRu=G_RU[grp]||grp;
  const badge=document.getElementById('nc-badge');
  badge.style.cssText='display:inline;background:'+color+'22;color:'+color;
  badge.textContent=grpRu;
  const name=nodeName(id);
  const subtitle=[pr.kind,pr.role,pr.owner].filter(Boolean).join(' · ');
  const SKIP=new Set(['name','statement','definition','kind','confidence','geography','date','source','n_sources','role','owner','is_gap']);
  const rangeStr = fmtRange(pr);
  const descText = pr.statement || pr.definition || '';
  const descHTML = descText ? '<div class="pv" style="margin:6px 0 10px;font-size:12.5px">'+esc(descText)+'</div>' : '';
  const propsHTML = descHTML + (rangeStr?('<div class="pl">Диапазон</div><div class="pv" style="font-weight:700">'+esc(rangeStr)+'</div>'):'') +
    Object.entries(pr).filter(([k,v])=>!SKIP.has(k)&&!['min','max','unit','value'].includes(k)&&v!=null&&String(v).trim()!==''&&v!==false)
    .map(([k,v])=>{const val=Array.isArray(v)?v.join(', '):String(v);return '<div class="pl">'+esc(k)+'</div><div class="pv">'+esc(val.length>500?val.slice(0,500)+'...':val)+'</div>';}).join('');
  document.getElementById('ne').style.display='none';
  document.getElementById('nd').style.display='block';
  document.getElementById('nd').innerHTML =
    '<div class="ntc" style="background:'+color+'22;color:'+color+';border:1px solid '+color+'44"><span style="width:7px;height:7px;border-radius:50%;background:'+color+';display:inline-block"></span>'+esc(grpRu)+
      (pr.is_gap?'<span class="gap-flag">ПРОБЕЛ</span>':'')+'</div>'+
    '<div class="nt">'+esc(name)+'</div>'+(subtitle?'<div class="ns">'+esc(subtitle)+'</div>':'')+
    verificationBadgeHTML(pr) + propsHTML +
    '<div class="nd-actions">'+
      '<button class="mini-btn" onclick="toggleCompare(\''+id+'\')" id="cmp-btn-'+id+'">'+(compareList.includes(id)?icon('check')+' В сравнении':'+ Сравнить')+'</button>'+
      '<button class="mini-btn sum-btn" onclick="showSummary()">'+icon('document')+' Резюме</button>'+
      '<button class="export-btn" onclick="exportSubgraph()" title="Скачать подграф узла как JSON">'+icon('download')+' JSON</button>'+
    '</div>'+
    '<div id="nd-sum" style="display:none"></div>';
  const adj=ADJ[id]||[];
  const uniq=[...new Map(adj.map(a=>[a.to,a])).values()];
  document.getElementById('nb-cnt').textContent='('+uniq.length+')';
  document.getElementById('nbl').innerHTML=uniq.slice(0,30).map(a=>{
    const nc=nodeColor(a.to),nm=esc(nodeName(a.to)),ng=G_RU[N_BY_ID[a.to]?.group]||'';
    return '<div class="ni" onclick="showNode(\''+a.to+'\',true)"><div class="nd" style="background:'+nc+'"></div><span class="nn">'+nm+'</span><span class="ng">'+ng+'</span></div>';
  }).join('')+(uniq.length>30?'<div style="font-size:11px;color:rgba(235,235,245,0.22);text-align:center;padding:8px 0">...ещё '+(uniq.length-30)+' узлов</div>':'');
  document.getElementById('nbc').style.display=uniq.length?'block':'none';
}
net.on('click',p=>{if(p.nodes.length) showNode(p.nodes[0]);});

function toggleCompare(id){
  const i = compareList.indexOf(id);
  if(i>=0) compareList.splice(i,1); else { if(compareList.length>=4){ compareList.shift(); } compareList.push(id); }
  const btn = document.getElementById('cmp-btn-'+id);
  if(btn) btn.innerHTML = compareList.includes(id) ? icon('check')+' В сравнении' : '+ Сравнить';
  const pill = document.getElementById('cmp-pill');
  if(pill){ pill.style.display = compareList.length? 'flex':'none'; pill.querySelector('.cmp-count').textContent = compareList.length; }
}
function clearCompare(){ compareList=[]; document.getElementById('cmp-pill').style.display='none'; }

// ── Суммаризация узла (граф-анализ соседей, без ИИ) ─────────────────────
function showSummary(){
  if(!currentNodeId) return;
  const sumDiv=document.getElementById('nd-sum');
  if(!sumDiv) return;
  if(sumDiv.style.display==='block'){ sumDiv.style.display='none'; return; }
  const id=currentNodeId, n=N_BY_ID[id], adj=ADJ[id]||[];
  const byType={};
  adj.forEach(a=>{ (byType[a.type]=byType[a.type]||new Set()).add(a.to); });
  const contrIds=[...(byType['CONTRADICTS']||[])];
  const srcIds=[...new Set([...(byType['DESCRIBED_IN']||[]),...(byType['VALIDATED_BY']||[])])];
  const gaps=[];
  if(!srcIds.length) gaps.push('нет привязки к источнику');
  if(!byType['OPERATES_AT_CONDITION'] && !['Condition','Publication','Expert','Facility'].includes(n?.group)) gaps.push('не указаны условия');
  if(adj.length<=1) gaps.push('слабо связан с графом (≤1 связь)');
  if(contrIds.length) gaps.push('есть противоречия — см. карту противоречий');

  let html='<div style="border-top:1px solid rgba(255,255,255,0.06);margin-top:12px;padding-top:12px">'
    +'<div class="ct" style="margin-bottom:8px">Суммаризация</div>';
  Object.entries(byType).forEach(([type,idsSet])=>{
    const ids=[...idsSet];
    html+='<div class="gap-ok gap-item" style="margin-bottom:6px"><div class="gap-name">'+esc(ET_RU[type]||type)+' ('+ids.length+')</div><div class="gap-desc">'+ids.slice(0,5).map(x=>esc(nodeName(x))).join(', ')+(ids.length>5?' …':'')+'</div></div>';
  });
  html += gaps.length
    ? '<div class="gap-item" style="margin-bottom:6px;background:rgba(255,159,10,0.08);border-color:rgba(255,159,10,0.22)"><div class="gap-name" style="color:#ff9f0a">Требует внимания</div><div class="gap-desc">'+gaps.join(' · ')+'</div></div>'
    : '<div class="gap-ok gap-item" style="margin-bottom:6px"><div class="gap-name">Хорошо изучен</div><div class="gap-desc">ключевые связи присутствуют, противоречий нет</div></div>';
  html += '<button class="mini-btn" style="background:rgba(118,118,128,0.15);color:rgba(235,235,245,0.5)" onclick="document.getElementById(\'nd-sum\').style.display=\'none\'">Скрыть</button>';
  html += '</div>';
  sumDiv.innerHTML=html;
  sumDiv.style.display='block';
}

// ── Экспорт подграфа выбранного узла в JSON ─────────────────────────────
function exportSubgraph(){
  if(!currentNodeId){ alert('Сначала выберите узел на графе'); return; }
  const id=currentNodeId, n=N_BY_ID[id], pr=PROPS[id]||{};
  const adjNodes=(ADJ[id]||[]).map(a=>({id:a.to, name:nodeName(a.to), group:N_BY_ID[a.to]?.group, edgeType:a.type}));
  const data={
    center:{id, name:nodeName(id), group:n?.group, properties:pr},
    neighbors:adjNodes,
    edges:(ADJ[id]||[]).map(a=>({from:id, to:a.to, type:a.type}))
  };
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url; a.download='subgraph_'+nodeName(id).replace(/[^a-zа-я0-9]/gi,'_').slice(0,30)+'.json';
  a.click();
  URL.revokeObjectURL(url);
}

// ── Табы ─────────────────────────────────────────────────────────────────
function switchTab(t) {
  csClose();
  document.getElementById('pane-graph').style.display=t==='graph'?'':'none';
  document.getElementById('pane-research').style.display=t==='research'?'':'none';
  document.getElementById('pane-analytics').style.display=t==='analytics'?'':'none';
  ['g','r','an'].forEach(k=>document.getElementById('tab-'+k)?.classList.remove('on'));
  const map={graph:'tab-g',research:'tab-r',analytics:'tab-an'};
  document.getElementById(map[t])?.classList.add('on');
  if(t==='research') initResearchOptions();
}
function toggleChatWidget() {
  const w=document.getElementById('chat-widget'), f=document.getElementById('chat-fab');
  const show=!w.classList.contains('show');
  w.classList.toggle('show',show);
  f.classList.toggle('on',show);
  if(show) setTimeout(()=>document.getElementById('chat-q')?.focus(),50);
}

// ── Инициализация UI (статистика, легенда, чипы) ────────────────────────
function initUI() {
  hydrateIcons();
  document.getElementById('s-n').textContent=NODES.length.toLocaleString('ru');
  document.getElementById('s-e').textContent=EDGES.length.toLocaleString('ru');
  document.getElementById('s-g').textContent=Object.keys(GROUPS).length;
  const cnt={};
  NODES.forEach(n=>{cnt[n.group]=(cnt[n.group]||0)+1;});
  const lgr=document.getElementById('lgr');
  lgr.innerHTML='';
  Object.entries(GROUPS).forEach(([g,cfg])=>{
    const c=cfg.color.background,el=document.createElement('div');
    el.className='lr';
    el.innerHTML='<div class="ld" style="background:'+c+'"></div><span class="ll">'+(G_RU[g]||g)+'</span><span class="lc">'+(cnt[g]||0)+'</span>';
    lgr.appendChild(el);
  });
  const fchips=document.getElementById('fchips');
  fchips.innerHTML='';
  Object.entries(GROUPS).forEach(([g,cfg])=>{
    const c=cfg.color.background,chip=document.createElement('div');
    chip.className='fc';
    chip.style.cssText='background:'+c+'22;color:'+c+';border-color:'+c+'66';
    chip.textContent=G_RU[g]||g;
    chip.title=(cnt[g]||0)+' узлов';
    chip.onclick=()=>toggleGF(g,chip);
    fchips.appendChild(chip);
  });
}

// ── МОДАЛЬНОЕ ОКНО ───────────────────────────────────────────────────────
function openModal(f) { document.getElementById('modal').classList.add('show'); modalBuilders[f]&&modalBuilders[f](); }
function closeModal() { document.getElementById('modal').classList.remove('show'); }
const modalBuilders = {
  gaps: buildGaps, contradictions: buildContradictions,
  compare: buildCompare, heatmap: buildHeatmap,
  geogaps: buildGeoGaps, experts: buildExpertMap
};

// ══════════════════════════════════════════════════════════════════════════
// ВКЛАДКА «ИССЛЕДОВАНИЕ» — конструктор многопараметрических запросов
// ══════════════════════════════════════════════════════════════════════════
function initResearchOptions(){
  const matSel=document.getElementById('rq-material'), procSel=document.getElementById('rq-process'), condSel=document.getElementById('rq-condition');
  if(matSel.dataset.init) return;
  matSel.dataset.init='1';
  const opt=(sel,v,label)=>{const o=document.createElement('option');o.value=v;o.textContent=label;sel.appendChild(o);};
  opt(matSel,'','— любой —'); opt(procSel,'','— любой —'); opt(condSel,'','— любое —');
  NODES.filter(n=>n.group==='Material').sort((a,b)=>nodeName(a.id).localeCompare(nodeName(b.id),'ru')).forEach(n=>opt(matSel,n.id,nodeName(n.id)));
  NODES.filter(n=>n.group==='Process').sort((a,b)=>nodeName(a.id).localeCompare(nodeName(b.id),'ru')).forEach(n=>opt(procSel,n.id,nodeName(n.id)));
  NODES.filter(n=>n.group==='Condition').sort((a,b)=>nodeName(a.id).localeCompare(nodeName(b.id),'ru')).forEach(n=>opt(condSel,n.id,nodeName(n.id)));
}
function runResearchQuery(){
  const matId=document.getElementById('rq-material').value;
  const procId=document.getElementById('rq-process').value;
  const condId=document.getElementById('rq-condition').value;
  const numMin=parseFloat(document.getElementById('rq-num-min').value);
  const numMax=parseFloat(document.getElementById('rq-num-max').value);
  const geo=document.getElementById('rq-geo').value;
  const hasNumFilter=!isNaN(numMin)||!isNaN(numMax);

  let candidateIds = new Set(NODES.map(n=>n.id));
  function neighborsOf(id){ return new Set((ADJ[id]||[]).map(a=>a.to).concat([id])); }

  if(matId) candidateIds = intersect(candidateIds, neighborsOf(matId));
  if(procId) candidateIds = intersect(candidateIds, neighborsOf(procId));
  if(condId) candidateIds = intersect(candidateIds, neighborsOf(condId));

  let results = [...candidateIds].filter(id=>{
    const pr=PROPS[id]||{};
    if(geo && pr.geography && pr.geography!==geo && pr.geography!=='RU+world') return false;
    if(hasNumFilter){
      const lo = pr.min!=null?pr.min:pr.value; const hi = pr.max!=null?pr.max:pr.value;
      if(lo==null) return false;
      if(!isNaN(numMin) && hi<numMin) return false;
      if(!isNaN(numMax) && lo>numMax) return false;
    }
    return true;
  });
  // exclude the query nodes themselves from result listing at top, but keep for context
  const focusSet=new Set([matId,procId,condId].filter(Boolean));
  results.sort((a,b)=>(ADJ[b]||[]).length-(ADJ[a]||[]).length);

  const res=document.getElementById('rq-results');
  if(!results.length){res.innerHTML='<div class="empty-hint">Ничего не найдено по заданным параметрам. Попробуйте ослабить условия.</div>';return;}
  const hitIds=new Set(results);
  nodesDS.update(NODES.map(n=>hitIds.has(n.id)?{id:n.id,size:focusSet.has(n.id)?26:16,color:undefined}:{id:n.id,size:4,color:{background:'rgba(255,255,255,0.04)',border:'rgba(255,255,255,0.07)'}}));
  res.innerHTML='<div style="font-size:11px;color:rgba(235,235,245,0.4);margin-bottom:10px">Найдено '+results.length+' связанных узлов · клик — перейти на граф</div>'+
    results.slice(0,60).map(id=>{
      const pr=PROPS[id]||{}, c=nodeColor(id), rangeStr=fmtRange(pr);
      return '<div class="sr-item" onclick="goNode(\''+id+'\')">'+
        '<div class="sr-dot" style="background:'+c+'"></div>'+
        '<div style="flex:1;min-width:0"><div class="sr-name">'+esc(nodeName(id))+'</div>'+
        '<div style="font-size:10px;color:rgba(235,235,245,0.35)">'+esc(G_RU[N_BY_ID[id]?.group]||'')+(rangeStr?' · '+esc(rangeStr):'')+(pr.geography?' · '+esc(geoLabel(pr.geography)):'')+'</div></div>'+
        (pr.confidence?'<span class="vbadge" style="background:'+confColor(pr.confidence)+'22;color:'+confColor(pr.confidence)+';border-color:'+confColor(pr.confidence)+'55;flex-shrink:0">'+esc(pr.confidence)+'</span>':'')+
      '</div>';
    }).join('');
}
function intersect(a,b){ return new Set([...a].filter(x=>b.has(x))); }
function goNode(id){ switchTab('graph'); showNode(id,true); }
function resetResearch(){
  document.getElementById('rq-material').value='';
  document.getElementById('rq-process').value='';
  document.getElementById('rq-condition').value='';
  document.getElementById('rq-num-min').value='';
  document.getElementById('rq-num-max').value='';
  document.getElementById('rq-geo').value='';
  ['rq-material','rq-process','rq-condition','rq-geo'].forEach(csSyncLabel);
  document.getElementById('rq-results').innerHTML='';
  nodesDS.update(NODES.map(n=>({id:n.id,size:undefined,color:undefined})));
}

// ── Кастомный выпадающий список (замена нативного <select>, единый стиль) ──
let csOpenId=null;
function csSyncLabel(id){
  const sel=document.getElementById(id), label=document.getElementById('cs-'+id+'-label');
  if(sel && label) label.textContent = sel.options[sel.selectedIndex]?.textContent || '';
}
function csToggle(id){
  if(csOpenId===id){ csClose(); return; }
  csClose();
  const sel=document.getElementById(id), wrap=document.getElementById('cs-'+id);
  if(!sel||!wrap) return;
  const rect=wrap.getBoundingClientRect();
  const panel=document.createElement('div');
  panel.className='cs-panel';
  panel.id='cs-panel-'+id;
  panel.style.left=Math.round(rect.left)+'px';
  panel.style.top=Math.round(rect.bottom+6)+'px';
  panel.style.width=Math.round(rect.width)+'px';
  [...sel.options].forEach(opt=>{
    const row=document.createElement('div');
    row.className='cs-opt'+(opt.value===sel.value?' sel':'');
    row.textContent=opt.textContent;
    row.onclick=(e)=>{
      e.stopPropagation();
      sel.value=opt.value;
      document.getElementById('cs-'+id+'-label').textContent=opt.textContent;
      csClose();
    };
    panel.appendChild(row);
  });
  document.body.appendChild(panel);
  wrap.classList.add('open');
  csOpenId=id;
  setTimeout(()=>document.addEventListener('click',csOutsideClick),0);
}
function csClose(){
  if(!csOpenId) return;
  document.getElementById('cs-panel-'+csOpenId)?.remove();
  document.getElementById('cs-'+csOpenId)?.classList.remove('open');
  csOpenId=null;
  document.removeEventListener('click',csOutsideClick);
}
function csOutsideClick(e){
  if(!e.target.closest('.cs-panel') && !e.target.closest('.cs')) csClose();
}
window.addEventListener('resize',csClose);

// ══════════════════════════════════════════════════════════════════════════
// ВКЛАДКА «АНАЛИТИКА»
// ══════════════════════════════════════════════════════════════════════════

// 1. Пробелы в знаниях
function buildGaps() {
  document.getElementById('mtitle').textContent='Пробелы в знаниях';
  const explicitGaps = NODES.filter(n=>n.group==='Finding' && (PROPS[n.id]||{}).is_gap);
  const materials=NODES.filter(n=>n.group==='Material');
  const sparse=[];
  materials.forEach(n=>{
    const deg=(ADJ[n.id]||[]).length;
    const procLinks=(ADJ[n.id]||[]).filter(a=>N_BY_ID[a.to]?.group==='Process').length;
    const condLinks=(ADJ[n.id]||[]).filter(a=>N_BY_ID[a.to]?.group==='Condition').length;
    if(deg<=1) sparse.push({n,procLinks,condLinks,deg});
  });
  let html = '<div class="ct" style="margin-bottom:8px">Явные пробелы (отмечены в источниках)</div>';
  html += explicitGaps.map(n=>{
    const pr=PROPS[n.id];
    return '<div class="gap-item" onclick="goNode(\''+n.id+'\')"><div class="gap-name">'+esc(pr.statement.slice(0,90))+(pr.statement.length>90?'…':'')+'</div><div class="gap-desc">'+esc(resolveSource(pr.source)||'')+'</div></div>';
  }).join('') || '<div class="empty-hint">—</div>';
  html += '<div class="ct" style="margin:14px 0 8px">Слабо связанные материалы (≤1 связь)</div>';
  html += sparse.length ? sparse.map(({n,deg})=>'<div class="gap-item" onclick="goNode(\''+n.id+'\')"><div class="gap-name">'+esc(nodeName(n.id))+'</div><div class="gap-desc">'+deg+' связ.</div></div>').join('') : '<div class="gap-ok gap-item">Все материалы достаточно связаны</div>';
  document.getElementById('mbody').innerHTML = html;
}

// 1b. География: РФ vs мир — по всему графу и по тематическим кластерам
function buildGeoGaps(){
  document.getElementById('mtitle').textContent='География: РФ vs мир';
  const counts = {RU:0, world:0, 'RU+world':0, '':0};
  NODES.forEach(n=>{ const g=(PROPS[n.id]||{}).geography||''; counts[g]=(counts[g]||0)+1; });
  let html = '<div class="ct" style="margin-bottom:8px">Всего по графу</div>'
    + '<div class="sr" style="margin-bottom:14px">'
      + '<div class="sb"><div class="sn" style="color:#30d158">'+counts.RU+'</div><div class="sl">РФ</div></div>'
      + '<div class="sb"><div class="sn" style="color:#0290f0">'+counts.world+'</div><div class="sl">Мир</div></div>'
      + '<div class="sb"><div class="sn" style="color:#bf5af2">'+(counts['RU+world']||0)+'</div><div class="sl">РФ + мир</div></div>'
    + '</div>';

  html += '<div class="ct" style="margin-bottom:8px">По тематическим кластерам</div>';
  CLUSTER_DEFS.forEach(def=>{
    const members = NODES.filter(n=>n._folder===def.key);
    if(!members.length) return;
    const ru = members.filter(n=>{const g=(PROPS[n.id]||{}).geography; return g==='RU'||g==='RU+world';}).length;
    const world = members.filter(n=>{const g=(PROPS[n.id]||{}).geography; return g==='world'||g==='RU+world';}).length;
    const zeroRu = ru===0;
    html += '<div class="gap-item'+(zeroRu?'':' gap-ok')+'" style="margin-bottom:7px">'
      + '<div class="gap-name">'+esc(def.label)+(zeroRu?' <span class="lit-warn">— 0% РФ</span>':'')+'</div>'
      + '<div class="gap-desc">'+members.length+' узлов · РФ-присутствие: '+ru+' · мировой опыт: '+world+'</div>'
    + '</div>';
  });

  const matProc = NODES.filter(n=>['Material','Process'].includes(n.group));
  const pureRu = matProc.filter(n=>(PROPS[n.id]||{}).geography==='RU').length;
  html += '<div class="gap-item" style="margin-top:10px"><div class="gap-name">Вывод</div><div class="gap-desc">Ни один материал или процесс в графе не имеет чисто российского происхождения ('+pureRu+' из '+matProc.length+') — отечественный опыт присутствует только в комбинации «РФ + мир» либо в узлах Условие/Эксперт/Предприятие.</div></div>';

  if(N_BY_ID['find_ru_heap_leach_gap']){
    html += '<div class="gap-item" onclick="goNode(\'find_ru_heap_leach_gap\')" style="cursor:pointer"><div class="gap-name">Пример из источников</div><div class="gap-desc">'+esc(nodeName('find_ru_heap_leach_gap'))+' — открыть на графе</div></div>';
  }
  document.getElementById('mbody').innerHTML = html;
}

// 1c. Институциональная память — связность экспертов, риск потери экспертизы
function buildExpertMap(){
  document.getElementById('mtitle').textContent='Институциональная память';
  const experts = NODES.filter(n=>n.group==='Expert');
  const totalAuthored = EDGES.filter(e=>e.type==='AUTHORED_BY').length;
  const rows = experts.map(n=>{
    const adj = ADJ[n.id]||[];
    const authored = adj.filter(a=>a.type==='AUTHORED_BY').length;
    const worksAt = adj.filter(a=>a.type==='WORKS_AT').length;
    return {n, authored, worksAt, total: authored+worksAt};
  }).sort((a,b)=>b.total-a.total);
  const AVATAR_COLORS = ['#0290f0','#30d158','#ff9f0a','#bf5af2','#ff375f','#ffd60a','#64d2ff'];
  const hashColor = id => { let h=0; for(let i=0;i<id.length;i++) h=(h*31+id.charCodeAt(i))>>>0; return AVATAR_COLORS[h%AVATAR_COLORS.length]; };
  const initials = name => { const parts=(name||'').trim().split(/\s+/); return ((parts[0]?.[0]||'')+(parts[1]?.[0]||parts[0]?.[1]||'')).toUpperCase(); };

  const connected = rows.filter(r=>r.total>0);
  const orphaned = rows.filter(r=>r.total===0);
  let html = connected.map(({n,authored,worksAt})=>{
    const pr=PROPS[n.id]||{};
    const share = totalAuthored ? Math.round(authored/totalAuthored*100) : 0;
    const risky = share>=50;
    const c = hashColor(n.id);
    return '<div class="gap-item'+(risky?'':' gap-ok')+'" onclick="goNode(\''+n.id+'\')" style="display:flex;gap:12px;align-items:flex-start;cursor:pointer">'
      + '<div style="width:36px;height:36px;border-radius:50%;background:'+c+'22;color:'+c+';border:1.5px solid '+c+'55;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0">'+esc(initials(pr.name))+'</div>'
      + '<div style="flex:1;min-width:0">'
        + '<div class="gap-name">'+esc(pr.name||n.id)+(risky?' <span class="lit-warn">'+icon('warning')+' риск потери экспертизы</span>':'')+'</div>'
        + '<div class="gap-desc">'+esc(pr.role||'')+(pr.org?' · '+esc(pr.org):'')+'<br>Публикаций: '+authored+' ('+share+'% от всех) · связей с организацией: '+worksAt+'</div>'
      + '</div>'
    + '</div>';
  }).join('');

  if(orphaned.length){
    html += '<div class="ct" style="margin:14px 0 8px">Нет связей в графе (данные не оцифрованы)</div>';
    html += orphaned.map(({n})=>{
      const pr=PROPS[n.id]||{};
      return '<div class="gap-item" onclick="goNode(\''+n.id+'\')" style="cursor:pointer"><div class="gap-name">'+esc(pr.name||n.id)+'</div><div class="gap-desc">'+esc(pr.role||'')+(pr.org?' · '+esc(pr.org):'')+'</div></div>';
    }).join('');
  }
  document.getElementById('mbody').innerHTML = html || '<div class="empty-hint">Эксперты не найдены</div>';
}

// 2. Противоречия
function buildContradictions(){
  document.getElementById('mtitle').textContent='Карта противоречий';
  const contrEdges = EDGES.filter(e=>e.type==='CONTRADICTS');
  if(!contrEdges.length){ document.getElementById('mbody').innerHTML='<div class="empty-hint">Противоречий не обнаружено</div>'; return; }
  document.getElementById('mbody').innerHTML = contrEdges.map(e=>{
    const a=PROPS[e.from]||{}, b=PROPS[e.to]||{};
    return '<div class="contr-card">'+
      '<div class="contr-side" onclick="goNode(\''+e.from+'\')"><div class="contr-label">'+esc(nodeName(e.from))+'</div><div class="contr-stmt">'+esc((a.statement||a.definition||'').slice(0,180))+'</div></div>'+
      '<div class="contr-vs">'+icon('warning')+' противоречит</div>'+
      '<div class="contr-side" onclick="goNode(\''+e.to+'\')"><div class="contr-label">'+esc(nodeName(e.to))+'</div><div class="contr-stmt">'+esc((b.statement||b.definition||'').slice(0,180))+'</div></div>'+
    '</div>';
  }).join('');
}

// 3. Сравнительная таблица
function buildCompare(){
  document.getElementById('mtitle').textContent='Сравнение технологий/решений';
  if(compareList.length<2){ document.getElementById('mbody').innerHTML='<div class="empty-hint">Выберите минимум 2 узла кнопкой «+ Сравнить» в карточке узла (вкладка Граф), затем откройте сравнение снова.</div>'; return; }
  const allKeys = new Set();
  compareList.forEach(id=>{ Object.keys(PROPS[id]||{}).forEach(k=>{ if(!['is_gap'].includes(k)) allKeys.add(k); }); });
  const priority=['name','kind','definition','statement','geography','confidence','date','min','max','value','unit','composition','purity','capacity','source'];
  const keys=[...priority.filter(k=>allKeys.has(k)), ...[...allKeys].filter(k=>!priority.includes(k))];
  let html='<div class="hm-wrap"><table class="hm-table"><thead><tr><th>Параметр</th>'+compareList.map(id=>'<th>'+esc(nodeName(id).slice(0,26))+'</th>').join('')+'</tr></thead><tbody>';
  keys.forEach(k=>{
    let vals = compareList.map(id=>(PROPS[id]||{})[k]);
    if(vals.every(v=>v==null||v==='')) return;
    if(k==='source') vals = vals.map(v=>v?resolveSource(v):v);
    html+='<tr><td style="text-align:left;font-weight:700;color:rgba(235,235,245,0.6)">'+esc(k)+'</td>'+vals.map(v=>'<td>'+esc(v==null?'—':String(v))+'</td>').join('')+'</tr>';
  });
  html+='</tbody></table></div><div style="margin-top:12px"><button class="aib" style="background:rgba(215,12,30,0.2);color:#ff5c4d" onclick="clearCompare();closeModal()">Очистить список сравнения</button></div>';
  document.getElementById('mbody').innerHTML=html;
}

// 4. Литературный обзор (синтез по теме) — используется чат-виджетом (кнопка "книги")
function buildLitReviewHTML(q){
  const tokens=q.toLowerCase().split(/[\s,]+/).filter(t=>t.length>1);
  function scoreNode(n){
    const pr=PROPS[n.id]||{};
    const fields=[n.label||'',pr.name||'',pr.statement||'',pr.definition||'',pr.kind||''].join(' ').toLowerCase();
    return tokens.reduce((s,t)=>s+(fields.split(t).length-1),0);
  }
  const pubs = NODES.filter(n=>n.group==='Publication').map(n=>({n,score:scoreNode(n)})).filter(x=>x.score>0);
  const findings = NODES.filter(n=>n.group==='Finding').map(n=>({n,score:scoreNode(n)})).filter(x=>x.score>0);
  const related = NODES.filter(n=>['Material','Process','Condition'].includes(n.group)).map(n=>({n,score:scoreNode(n)})).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,10);
  // pull in publications/findings connected to top related nodes too
  const seedIds = new Set(related.map(x=>x.n.id));
  const linkedPubs = new Set();
  seedIds.forEach(id=>(ADJ[id]||[]).forEach(a=>{ if(N_BY_ID[a.to]?.group==='Publication') linkedPubs.add(a.to); if(N_BY_ID[a.to]?.group==='Finding') linkedPubs.add(a.to); }));
  const allPubIds = new Set([...pubs.map(x=>x.n.id), ...findings.map(x=>x.n.id), ...linkedPubs]);
  if(!allPubIds.size) return '<div class="empty-hint">В разобранном графе источников не найдено.</div>' + corpusHitsHTML(q);
  // group by geography
  const byGeo={RU:[],world:[],'RU+world':[],'':[]};
  [...allPubIds].forEach(id=>{ const pr=PROPS[id]||{}; (byGeo[pr.geography]||byGeo['']).push(id); });
  const contrIds = new Set();
  EDGES.filter(e=>e.type==='CONTRADICTS' && (allPubIds.has(e.from)||allPubIds.has(e.to))).forEach(e=>{contrIds.add(e.from);contrIds.add(e.to);});
  let html = '<div style="font-size:11px;color:rgba(235,235,245,0.5);margin-bottom:10px">Найдено <strong style="color:#fff">'+allPubIds.size+'</strong> источников/выводов по теме «'+esc(q)+'»</div>';
  for(const [geo,ids] of Object.entries(byGeo)){
    if(!ids.length) continue;
    html += '<div class="ct" style="margin-top:10px">'+esc(geoLabel(geo)||'Без указания географии')+' ('+ids.length+')</div>';
    html += ids.map(id=>{
      const pr=PROPS[id]||{}, isContr=contrIds.has(id);
      const txt = pr.statement || pr.definition || pr.name;
      return '<div class="lit-item'+(isContr?' lit-contr':'')+'" onclick="goNode(\''+id+'\')">'+
        '<div class="lit-title">'+esc(nodeName(id))+(isContr?' <span class="lit-warn">'+icon('warning')+' есть противоречие</span>':'')+'</div>'+
        (pr.date?'<span class="lit-date">'+esc(pr.date)+'</span>':'')+
        '<div class="lit-txt">'+esc((txt||'').slice(0,200))+'</div></div>';
    }).join('');
  }
  return html + corpusHitsHTML(q);
}
function sendLitReview(){
  const input=document.getElementById('chat-q'), q=input.value.trim();
  if(!q) return;
  input.value='';
  const msgs=document.getElementById('chat-msgs');
  msgs.innerHTML+='<div class="msg-u">'+icon('books')+' '+esc(q)+'</div><div class="msg-a">'+buildLitReviewHTML(q)+'</div>';
  msgs.scrollTop=msgs.scrollHeight;
}

// 5. Тепловая карта Материал × Условие
function buildHeatmap() {
  document.getElementById('mtitle').textContent='Карта пробелов: Материал × Условие';
  document.getElementById('mbody').innerHTML='<div class="thinking">Строю матрицу...</div>';
  setTimeout(()=>{
    const mats = NODES.filter(n=>n.group==='Material').slice(0,20);
    const conds = NODES.filter(n=>n.group==='Condition').slice(0,18);
    if(!mats.length||!conds.length){document.getElementById('mbody').innerHTML='<div class="empty-hint">Недостаточно данных</div>';return;}
    const cell=(mid,cid)=>{
      if((ADJ[mid]||[]).some(a=>a.to===cid)) return 3;
      const nb=new Set((ADJ[mid]||[]).map(a=>a.to));
      if((ADJ[cid]||[]).some(a=>nb.has(a.to))) return 2;
      let found=false;
      (ADJ[mid]||[]).slice(0,10).forEach(a=>{if((ADJ[a.to]||[]).some(b=>b.to===cid))found=true;});
      return found?1:0;
    };
    const condNames=conds.map(c=>nodeName(c.id));
    document.getElementById('mbody').innerHTML='<div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;font-size:11px;font-weight:600"><span style="color:#ff5c4d">-- нет связи</span><span style="color:#ff9f0a">○ через 2 узла</span><span style="color:#34c759">◎ через 1 узел</span><span style="color:#3fb0ff">● прямая</span></div><div class="hm-wrap"><table class="hm-table"><thead><tr><th>Материал / Условие</th>'+condNames.map(cn=>'<th title="'+esc(cn)+'">'+esc(cn.slice(0,10))+'</th>').join('')+'</tr></thead><tbody>'+mats.map(m=>'<tr><td style="font-weight:600;color:rgba(235,235,245,0.7);text-align:left;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px" title="'+esc(nodeName(m.id))+'">'+esc(nodeName(m.id).slice(0,18))+'</td>'+conds.map(c=>{const v=cell(m.id,c.id);return '<td class="hm-'+v+'">'+(v===0?'--':v===3?'●':v===2?'◎':'○')+'</td>';}).join('')+'</tr>').join('')+'</tbody></table></div><div style="font-size:11px;color:rgba(235,235,245,0.3);margin-top:10px">Первые 20 материалов и 18 условий</div>';
  },20);
}

// ══════════════════════════════════════════════════════════════════════════
// ЧАТ (Graph-RAG: 2-hop обход графа + бесплатный LLM Pollinations, без ключа)
// ══════════════════════════════════════════════════════════════════════════
const CHAT_KEY='nnGraphChatHistory_v1';
let chatSession=null, chatHistoryAll=[];
function chatLoad(){try{chatHistoryAll=JSON.parse(localStorage.getItem(CHAT_KEY)||'[]');}catch(e){chatHistoryAll=[];}}
function chatSave(){try{localStorage.setItem(CHAT_KEY,JSON.stringify(chatHistoryAll.slice(0,25)));}catch(e){}}
chatLoad();

function graphRetrieve(q){
  const tokens=q.toLowerCase().split(/[\s,?«»]+/).filter(t=>t.length>2);
  const scored=NODES.map(n=>{
    const pr=PROPS[n.id]||{};
    const txt=[(n.label||''),(pr.name||''),(pr.statement||''),(pr.definition||''),(pr.kind||'')].join(' ').toLowerCase();
    return {n,score:tokens.reduce((s,t)=>s+(txt.split(t).length-1),0)};
  }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,8);
  // expand 1-hop
  const seedIds = scored.map(x=>x.n.id);
  const expanded = new Map(scored.map(x=>[x.n.id,x.score]));
  seedIds.forEach(id=>{ (ADJ[id]||[]).slice(0,6).forEach(a=>{ if(!expanded.has(a.to)) expanded.set(a.to, 0.3); }); });
  return [...expanded.keys()].map(id=>({id, score:expanded.get(id)})).sort((a,b)=>b.score-a.score).slice(0,16);
}
function buildCtx(ids) {
  return ids.slice(0,14).map(id=>{
    const pr=PROPS[id]||{}, n=N_BY_ID[id];
    return {
      name: pr.name||pr.statement||id, type: G_RU[n?.group]||n?.group,
      def: (pr.definition||pr.statement||'').slice(0,220),
      range: fmtRange(pr), geo: pr.geography, confidence: pr.confidence, source: pr.source
    };
  });
}
// ── Поиск по полному каталогу источников (1453 файла, метаданные из CORPUS) ──
function searchCorpus(q, limit){
  if (typeof CORPUS === 'undefined') return [];
  const tokens = q.toLowerCase().split(/[\s,?«»]+/).filter(t=>t.length>2);
  if(!tokens.length) return [];
  return CORPUS.map(d=>{
    const text = (d.name+' '+d.cat).toLowerCase();
    return {d, score: tokens.reduce((s,t)=>s+(text.includes(t)?1:0),0)};
  }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0, limit||6).map(x=>x.d);
}
function corpusHitsHTML(q){
  const hits = searchCorpus(q, 6);
  if(!hits.length) return '';
  return '<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.08)">'
    + '<div style="font-size:10px;font-weight:700;color:var(--text-faint);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Также в общем каталоге источников ('+CORPUS.length+' файлов)</div>'
    + hits.map(d=>'<div style="font-size:11px;color:rgba(235,235,245,0.55);padding:2px 0">· '+esc(d.name)+' <span style="color:var(--text-faint)">— '+esc(d.cat)+(d.year?', '+esc(d.year):'')+'</span></div>').join('')
    + '</div>';
}
async function sendChat() {
  const input=document.getElementById('chat-q'),q=input.value.trim();
  if(!q) return;
  input.value='';
  const msgs=document.getElementById('chat-msgs');
  msgs.innerHTML+='<div class="msg-u">'+esc(q)+'</div><div class="msg-a thinking" id="thinking">Обхожу граф...</div>';
  msgs.scrollTop=msgs.scrollHeight;
  const hits=graphRetrieve(q);
  let answer;
  try {
    // Наш бэкенд: ответ по ПОЛНОМУ графу (вектор + PageRank + ленивая верификация), суверенно (без внешних LLM)
    const resp = await fetch(P2KG_API+'/api/graphs/'+encodeURIComponent(P2KG_GID)+'/ask', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question:q})
    });
    if(!resp.ok) throw new Error('bad status');
    const d = await resp.json();
    answer = d.answer || graphAnswer(hits,q);
    if(d.sources && d.sources.length){
      answer += '\n\n**Источники:** ' + d.sources.map(s=>s.file+' ('+s.facts+')').join(', ');
    }
  } catch(e){ answer = graphAnswer(hits,q); }
  document.getElementById('thinking').outerHTML='<div class="msg-a">'+(answer.includes('<')?answer:esc(answer).replace(/\n/g,'<br>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>'))+corpusHitsHTML(q)+'</div>';
  msgs.scrollTop=msgs.scrollHeight;
  if(!chatSession) chatSession={id:Date.now(),date:new Date().toISOString(),messages:[]};
  chatSession.messages.push({role:'user',content:q},{role:'assistant',content:answer});
}
function graphAnswer(hits,q) {
  if(!hits.length) return 'По запросу «'+esc(q)+'» узлов не найдено. Попробуйте другие ключевые слова — материал, процесс или предприятие.';
  const groups={};
  hits.forEach(({id})=>{const n=N_BY_ID[id];const g=G_RU[n.group]||n.group||'Прочее';if(!groups[g])groups[g]=[];groups[g].push(id);});
  let html='Найдено <strong>'+hits.length+' связанных узлов</strong> по запросу «'+esc(q)+'»:<br><br>';
  Object.entries(groups).forEach(([g,ids])=>{html+='<strong>'+g+':</strong><ul>'+ids.slice(0,5).map(id=>{
    const pr=PROPS[id]||{}; const range=fmtRange(pr);
    return '<li>'+esc(nodeName(id))+(range?' — '+esc(range):'')+(pr.confidence?' <em style="opacity:.6">('+esc(pr.confidence)+')</em>':'')+'</li>';
  }).join('')+'</ul>';});
  return html;
}

// ── Загрузка легенды/рёбер, автозапуск ──────────────────────────────────
initUI();
setTimeout(()=>document.getElementById('chat-q')?.focus(),300);
document.getElementById('pb').addEventListener('scroll',csClose);
document.getElementById('chat-widget-body')?.addEventListener('scroll',csClose);
