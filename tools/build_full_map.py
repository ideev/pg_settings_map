"""Generate a self-contained map from pg_settings.json; Python standard library only."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = json.loads((root / 'pg_settings.json').read_text())
html = (root / 'tools/templates/map.html').read_text()
start = html.index('const palette=')
end = html.index('const canvas=', start)
model = r'''
const source = __DATA__;
const palette={}, data=[];
function convert(raw,parent=null,depth=0,branch=null,path='root'){
 const id=path,kind=depth===0?'root':raw.type==='parameter'?'parameter':depth===1?'group':'subgroup';
 if(depth===1){branch=id;palette[branch]=['#879a49','#b98260','#7695af','#a180a5','#57988d','#b79b48'][Object.keys(palette).length%6];}
 const n={...raw,id,parent,kind,branch,label:depth===0?'QHB':raw.name,type:raw.vartype,description:raw.short_desc,
 collapsed:kind!=='root'&&kind!=='parameter',x:0,y:0,autoX:0,autoY:0};
 data.push(n);(raw.children||[]).forEach((v,i)=>convert(v,id,depth+1,branch,path+'/'+i));
}
convert(source);
const byId=new Map(data.map(n=>[n.id,n]));
const defaultHiddenGroups=new Set(['Error Handling','Lock Management','QHB Options','Ungrouped','Developer Options']);
const hiddenGroups=new Set(data.filter(n=>n.kind==='group'&&defaultHiddenGroups.has(n.label)).map(n=>n.id));
function isHidden(n){return hiddenGroups.has(n.id)||(n.parent?isHidden(byId.get(n.parent)):false);}
const nodeHeights=new Map(),nodeWidths=new Map();
function measureNodes(){
 const probe=document.createElement('div');probe.style.cssText='position:absolute;left:-10000px;visibility:hidden';document.body.append(probe);
 for(const n of data){const el=document.createElement('div');el.className='node '+n.kind;const label=document.createElement('span');label.textContent=n.label;el.append(label);if(n.kind!=='parameter'){const toggle=document.createElement('span');toggle.className='toggle';toggle.textContent='+';el.append(toggle);}else{const dot=document.createElement('span');dot.className='leaf-dot';el.prepend(dot);}probe.append(el);nodeHeights.set(n.id,el.offsetHeight);nodeWidths.set(n.id,el.offsetWidth);el.remove();}probe.remove();
}
const childMap=new Map(data.map(n=>[n.id,[]]));
for(const n of data)if(n.parent)childMap.get(n.parent).push(n);
const children=id=>childMap.get(id)||[];
const descendants=id=>children(id).flatMap(n=>[n,...descendants(n.id)]);
// Names along the ancestry keep preferences stable when siblings are reordered.
const stateKey='pg_settings_map.state.v1';
const nodeKey=n=>JSON.stringify(n.parent?[...JSON.parse(nodeKey(byId.get(n.parent))),n.label]:[n.name]);
const stateKeys=new Map(data.map(n=>[n.id,nodeKey(n)]));
let stateReady=false,saveTimer;
function currentState(){
 const entries=data.map(n=>[stateKeys.get(n.id),{collapsed:n.collapsed,hidden:hiddenGroups.has(n.id),dx:n.x-n.autoX,dy:n.y-n.autoY}]);
 return {version:1,nodes:Object.fromEntries(entries)};
}
function saveState(){
 if(!stateReady)return;
 clearTimeout(saveTimer);
 try{localStorage.setItem(stateKey,JSON.stringify(currentState()));}catch{}
}
function scheduleSave(){if(stateReady){clearTimeout(saveTimer);saveTimer=setTimeout(saveState,150);}}
function restoreState(){
 let saved;
 try{saved=JSON.parse(localStorage.getItem(stateKey));}catch{}
 applyState(saved);
}
function applyState(saved){
 const entries=saved?.version===1&&saved.nodes&&typeof saved.nodes==='object'?saved.nodes:{};
 hiddenGroups.clear();
 for(const n of data){
  n.collapsed=n.kind!=='root'&&n.kind!=='parameter';
  if(n.kind==='group'&&defaultHiddenGroups.has(n.label))hiddenGroups.add(n.id);
 }
 for(const n of data){
  const entry=entries[stateKeys.get(n.id)];
  if(!entry||typeof entry!=='object')continue;
  if(typeof entry.collapsed==='boolean'&&n.kind!=='parameter')n.collapsed=entry.collapsed;
  if(n.kind==='group'&&typeof entry.hidden==='boolean'){
   if(entry.hidden)hiddenGroups.add(n.id);else hiddenGroups.delete(n.id);
  }
 }
 layout(true);
 for(const n of data){
  const entry=entries[stateKeys.get(n.id)];
  if(entry&&Number.isFinite(entry.dx)&&Number.isFinite(entry.dy)){
   n.x+=entry.dx;n.y+=entry.dy;
  }
 }
 for(const box of document.querySelectorAll('#group-list input'))box.checked=!hiddenGroups.has(box.dataset.group);
 updateGroupCount();stateReady=true;
}
window.addEventListener('pagehide',saveState);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')saveState();});
// Reflow visible branches; retain user offsets relative to the automatic layout.
function layout(reset=false){
 if(reset)for(const n of data){n.x=n.autoX;n.y=n.autoY;}
 const offsets=new Map(data.map(n=>[n.id,reset?{x:0,y:0}:{x:n.x-n.autoX,y:n.y-n.autoY}]));
 const height=n=>n.collapsed||!children(n.id).length?(nodeHeights.get(n.id)+(n.kind==='parameter'?8:22)):Math.max(nodeHeights.get(n.id)+16,children(n.id).reduce((s,c)=>s+height(c),0));
 function place(n,depth,side,top){
  const h=height(n),off=offsets.get(n.id);
  n.side=side;n.autoX=side<0?nodeWidths.get('root')-depth*370-nodeWidths.get(n.id):depth*370;n.autoY=top+(h-nodeHeights.get(n.id))/2;
  n.x=n.autoX+off.x;n.y=n.autoY+off.y;
  if(!n.collapsed){let y=top;for(const c of children(n.id)){place(c,depth+1,side,y);y+=height(c);}}
 }
 const root=data[0];root.autoX=0;root.autoY=-nodeHeights.get(root.id)/2;root.x=offsets.get(root.id).x;root.y=root.autoY+offsets.get(root.id).y;
 if(!root.collapsed){const branches=children(root.id).filter(n=>!hiddenGroups.has(n.id));for(const side of [-1,1]){const list=branches.filter((_,i)=>(i%2===0?-1:1)===side);let y=-list.reduce((s,n)=>s+height(n),0)/2;for(const n of list){place(n,1,side,y);y+=height(n);}}}
}
'''.replace('__DATA__',json.dumps(source,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029'))
html=html[:start]+model+html[end:]
html=html.replace("return !n.parent||", "return !hiddenGroups.has(n.id)&&(!n.parent||").replace("visible(byId.get(n.parent)));}", "visible(byId.get(n.parent))));}")
html=html.replace("selected='work_mem'","selected='root'")
html=html.replace("n.collapsed=!n.collapsed;render();","n.collapsed=!n.collapsed;layout();render();select(n.id);focusBranch(n.id);")
html=html.replace("b.textContent=n.collapsed?'+':'−';", "b.textContent=n.collapsed?'+':'−';b.title=`${descendants(n.id).filter(v=>v.kind==='parameter').length} параметров`;")
html=html.replace("const fields=[['По умолчанию',n.default],['Минимум',n.min],['Максимум',n.max],['Контекст',n.context]];if(n.values)fields.push(['Допустимые значения',n.values]);", "const format=v=>v===null||v===undefined?'—':v===''?'(пустая строка)':String(v);const fields=[['Значение в файле (setting)',format(n.setting)],['По умолчанию (boot_val)',format(n.boot_val)],['Единицы измерения',format(n.unit)],['Минимум',format(n.min_val)],['Максимум',format(n.max_val)],['Контекст',format(n.context)],['Источник',format(n.source)],['Ожидает перезапуска',n.pending_restart===true?'Да':n.pending_restart===false?'Нет':'—']];if(n.enumvals)fields.push(['Допустимые значения',Array.isArray(n.enumvals)?n.enumvals.join(' · '):String(n.enumvals)]);if(n.extra_desc)add('p',n.extra_desc);")
a=html.index("  add('div',({user:")
b=html.index("\n}",a)
html=html[:a]+r'''
  add('div',({internal:'Внутренний параметр: напрямую изменить нельзя.',user:'Можно менять командой SET для текущего сеанса.',superuser:'Изменение в сеансе требует прав суперпользователя или предоставленного права SET.',sighup:'Применяется после перечитывания конфигурации.',postmaster:'Для применения требуется перезапуск PostgreSQL.',backend:'Применяется при создании нового сеанса; в работающем сеансе не меняется.',superuser_backend:'Задаётся для нового сеанса с необходимыми правами; в работающем сеансе не меняется.'})[n.context]||`Контекст из исходного файла: ${n.context}`,'context');
 }else{
  add('p',`В этой ветке: ${descendants(n.id).filter(v=>v.kind==='parameter').length} параметров. Раскройте её кнопкой + или найдите параметр по имени. Узлы и целые ветки можно перемещать свободно.`);
  if(n.category)add('div',String(n.category),'context');
 }
 
''' + html[b:]
html=html.replace('Math.max(.12,Math.min(1,','Math.max(.005,Math.min(1,').replace('Math.max(.12,Math.min(2.5,','Math.max(.005,Math.min(2.5,')
html=html.replace("data.forEach(n=>n.collapsed=false);render();fit();", "data.forEach(n=>n.collapsed=false);layout();render();fit();")
html=html.replace("for(const p of originals)Object.assign(byId.get(p.id),p,{collapsed:false});render();fit();", "data.forEach(n=>n.collapsed=n.kind!=='root'&&n.kind!=='parameter');layout(true);select('root');render();fit();")
html=html.replace('new ResizeObserver(fit).observe(canvas);render();showDetails();fit();',r'''
const search=document.querySelector('#search'),results=document.querySelector('#results');
function reveal(id){const branch=byId.get(id).branch;if(branch){hiddenGroups.delete(branch);const box=document.querySelector(`#group-list input[data-group="${branch}"]`);if(box)box.checked=true;updateGroupCount();}let n=byId.get(id);while(n.parent){n=byId.get(n.parent);n.collapsed=false;}layout();render();select(id);const target=byId.get(id);zoom=1;pan={x:canvas.clientWidth/2-target.x-140,y:canvas.clientHeight/2-target.y};transform();results.replaceChildren();document.querySelector(`[data-id="${id}"]`).focus({preventScroll:true});}
search.addEventListener('input',()=>{
 results.replaceChildren();const q=search.value.trim().toLowerCase();if(!q)return;
 const matches=data.filter(n=>n.label.toLowerCase().includes(q));
 const count=document.createElement('div');count.className='search-count';count.textContent=`Найдено: ${matches.length}${matches.length>30?' · показаны первые 30':''}`;results.append(count);
 for(const n of matches.slice(0,30)){const b=document.createElement('button');b.type='button';b.textContent=n.label;b.onclick=()=>reveal(n.id);results.append(b);}
});
search.addEventListener('keydown',e=>{if(e.key==='Escape'){results.replaceChildren();search.value='';}if(e.key==='Enter')results.querySelector('button')?.click();});
document.querySelector('#collapse').onclick=()=>{data.forEach(n=>n.collapsed=n.kind!=='root'&&n.kind!=='parameter');layout();render();fit();};
const groupList=document.querySelector('#group-list');
function updateGroupCount(){document.querySelector('#group-count').textContent=`${children('root').filter(n=>!hiddenGroups.has(n.id)).length} / ${children('root').length}`;}
function setAllGroups(checked){
 for(const n of children('root')){
  if(checked)hiddenGroups.delete(n.id);else hiddenGroups.add(n.id);
 }
 for(const box of groupList.querySelectorAll('input'))box.checked=checked;
 if(isHidden(byId.get(selected)))select('root');
 layout();render();fit();updateGroupCount();search.dispatchEvent(new Event('input'));saveState();
}
document.querySelector('#groups-select-all').onclick=()=>setAllGroups(true);
document.querySelector('#groups-clear-all').onclick=()=>setAllGroups(false);
for(const n of children('root')){
 const label=document.createElement('label'),box=document.createElement('input'),text=document.createElement('span');
 box.type='checkbox';box.checked=true;box.dataset.group=n.id;text.textContent=n.label;label.append(box,text);groupList.append(label);
 box.addEventListener('change',()=>{
  if(box.checked)hiddenGroups.delete(n.id);else hiddenGroups.add(n.id);
  if(isHidden(byId.get(selected)))select('root');
  layout();render();fit();updateGroupCount();search.dispatchEvent(new Event('input'));
 });
}
updateGroupCount();measureNodes();restoreState();new ResizeObserver(fit).observe(canvas);render();showDetails();fit();
''')
html=html.replace('<title>pg_settings_map · живая карта PostgreSQL</title>', '<title>pg_settings_map · полная карта из JSON</title>')
html=html.replace('Визуальный прототип · 01', '436 параметров · данные из JSON')
html=html.replace('Всё связано с деталями.', 'Карта параметров PostgreSQL')
html=html.replace('<button id="expand">', '<button id="collapse">Свернуть всё</button><button id="expand">')
html=html.replace('<div class="topbar">','<div class="search-box"><label for="search">Поиск параметра</label><input id="search" type="search" placeholder="Например, work_mem" autocomplete="off"><div id="results" aria-live="polite"></div></div><div class="topbar">')
html=html.replace('<main class="layout">','<main class="layout"><aside class="groups-panel" aria-label="Видимость групп"><details open><summary>Группы <span id="group-count"></span></summary><p>Отметьте ветки, которые нужны на карте.</p><div class="group-actions"><button id="groups-select-all" type="button">Выбрать все</button><button id="groups-clear-all" type="button">Отменить все</button></div><div id="group-list"></div></details></aside>')
html=html.replace('</style>', '''
.node{max-width:310px;white-space:normal;width:max-content;min-height:38px}.node.group{font-size:17px;max-width:280px}.node.subgroup{font-size:15px;max-width:280px}.node.parameter{font-size:14px;overflow-wrap:anywhere;min-height:30px;padding:6px 11px 4px}.node .toggle{margin-left:4px}.node.root{white-space:nowrap}.search-box{position:absolute;top:94px;left:23px;z-index:5;width:270px;background:#fffefa;border:1px solid #dce1d8;border-radius:7px;padding:9px 12px}.search-box label{font-size:10px;display:block;color:#7d8779;margin-bottom:5px}.search-box input{border:0;background:transparent;width:100%;font:13px Arial;color:#29352e;padding:3px 0;outline-offset:3px}#results{max-height:280px;overflow:auto}#results button{display:block;width:100%;text-align:left;background:transparent;border:0;border-top:1px solid #e8eadf;padding:9px 2px;font:12px monospace;overflow-wrap:anywhere;color:#43533f}#results button:hover{background:#edf2e4}.search-count{font-size:11px;color:#7d8779;padding:9px 0}.topbar .toolbar{max-width:370px}@media(max-width:800px){.search-box{left:13px;top:119px;width:225px}.topbar .toolbar{max-width:170px}}
.layout{grid-template-columns:240px minmax(0,1fr) 310px}.groups-panel{border-left:0;border-right:1px solid #dce1d8;padding:24px 16px}.group-actions{display:flex;gap:6px;margin-bottom:10px}.group-actions button{border:1px solid #d9dfd2;background:#fffefa;border-radius:6px;padding:7px 8px;color:#53634f;font-size:11px;white-space:nowrap}.group-actions button:hover{background:#edf2e6}.groups-panel summary{font:18px Georgia,serif;cursor:pointer}.groups-panel summary span{font:11px Arial;color:#7d8779;margin-left:10px}.groups-panel p{font-size:11px;margin:15px 0;line-height:1.6}#group-list{display:grid;gap:4px}#group-list label{display:flex;gap:9px;align-items:start;padding:8px 5px;border-radius:5px;cursor:pointer;font-size:12px;line-height:1.5}#group-list label:hover{background:#edf2e4}#group-list input{accent-color:#637f48;margin:2px 0 0;flex-shrink:0}#group-list label:has(input:not(:checked)){color:#92998b}@media(max-width:1100px){.layout{grid-template-columns:200px minmax(0,1fr) 260px}.groups-panel{padding:20px 12px}.topbar{flex-wrap:wrap}.search-box{top:145px}}@media(max-width:800px){.layout{grid-template-columns:minmax(0,1fr) 260px;grid-template-rows:auto minmax(350px,1fr)}.groups-panel{grid-column:1/-1;max-height:180px;border-right:0;border-bottom:1px solid #dce1d8;padding:12px 16px}#group-list{grid-template-columns:repeat(3,minmax(0,1fr))}.groups-panel p{margin:8px 0}}@media(max-width:580px){.layout{grid-template-columns:1fr;grid-template-rows:auto minmax(400px,60dvh) auto}.groups-panel{max-height:180px}#group-list{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>''')
# Optional side panels: the map keeps the full width when panels are closed.
html=html.replace('<button id="collapse">','<button id="groups-toggle" aria-controls="groups-panel" aria-expanded="false">☰ Группы</button><button id="collapse">')
html=html.replace('<aside class="groups-panel"', '<aside id="groups-panel" class="groups-panel" inert')
html=html.replace('<aside id="details"', '<aside id="details" hidden')
html=html.replace('selected=id;showDetails();', "selected=id;if(byId.get(id).kind==='parameter'){showDetails();}else{closeDetails();}")
html=html.replace("select(n.id);render();}if(['ArrowLeft'", "select(n.id);if(n.kind==='parameter')openDetails(n.id);}if(['ArrowLeft'")
html=html.replace('canvas.setPointerCapture(e.pointerId);', '(el||canvas).setPointerCapture(e.pointerId);')
html=html.replace("if(gesture&&gesture.id===e.pointerId){gesture=null;", "if(gesture&&gesture.id===e.pointerId){if(e.type==='pointerup'&&!gesture.items&&Math.hypot(e.clientX-gesture.x,e.clientY-gesture.y)<5)closeDetails();gesture=null;")
html=html.replace("updateGroupCount();measureNodes();", r"""
function closeDetails(){document.querySelector('#details').hidden=true;}
function openDetails(id){select(id);document.querySelector('#details').hidden=false;}
canvas.addEventListener('dblclick',e=>{
 const el=e.target.closest('.node');if(!el||e.target.closest('button'))return;
 const n=byId.get(el.dataset.id);e.preventDefault();if(n.kind==='parameter'){openDetails(n.id);}else if(children(n.id).length){n.collapsed=!n.collapsed;layout();render();select(n.id);focusBranch(n.id);}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetails();});
const groupsToggle=document.querySelector('#groups-toggle'),groupsPanel=document.querySelector('#groups-panel');
groupsToggle.onclick=()=>{
 const open=groupsToggle.getAttribute('aria-expanded')!=='true';
 groupsToggle.setAttribute('aria-expanded',String(open));groupsPanel.inert=!open;
 document.querySelector('.layout').classList.toggle('groups-open',open);
 groupsToggle.textContent=open?'← Скрыть группы':'☰ Группы';
};
updateGroupCount();measureNodes();""")
html=html.replace('Фон — перемещение · колесо — масштаб · +/− — ветка', 'Двойной щелчок — справка · пустое место — закрыть<br>Фон — перемещение · колесо — масштаб')
html=html.replace('</style>', '''
.layout{position:relative;grid-template-columns:0 minmax(0,1fr);grid-template-rows:minmax(0,1fr);height:calc(100dvh - 78px);overflow:hidden;transition:grid-template-columns .2s ease}.layout.groups-open{grid-template-columns:240px minmax(0,1fr)}.groups-panel{grid-column:1;grid-row:1;width:240px;max-height:none;transform:translateX(-100%);visibility:hidden;transition:transform .2s ease,visibility .2s;overflow:auto;min-height:0}.groups-open .groups-panel{transform:translateX(0);visibility:visible}.workspace{grid-column:2;grid-row:1;min-width:0;min-height:0}#details{position:absolute;top:0;bottom:0;right:0;width:310px;max-width:90%;overflow:auto;border-left:1px solid #dce1d8;border-top:0;box-shadow:-8px 0 30px #29352e18;z-index:8}#details[hidden]{display:none}#group-list{grid-template-columns:1fr}.topbar .toolbar{max-width:500px}@media(max-width:1100px){.topbar{flex-wrap:wrap}.search-box{top:145px}}@media(max-width:800px){.layout{height:calc(100dvh - 65px)}.layout.groups-open{grid-template-columns:200px minmax(0,1fr)}.groups-panel{width:200px;padding:20px 12px;border-right:1px solid #dce1d8;border-bottom:0}.topbar .toolbar{max-width:100%}}@media(max-width:580px){.layout,.layout.groups-open{grid-template-columns:0 minmax(0,1fr)}.groups-panel{position:absolute;top:0;bottom:0;left:0;z-index:7;width:240px;box-shadow:6px 0 20px #29352e18}.groups-panel details{margin-top:42px}#groups-toggle{position:relative;z-index:9}.topbar{z-index:7}.topbar .toolbar{max-width:100%}.search-box{top:170px;z-index:5}#details{width:310px}}
@media(prefers-reduced-motion:reduce){.layout,.groups-panel{transition:none}}
</style>''')

# Keep all navigation in the application header, outside the map viewport.
search_start=html.index('<div class="search-box">')
search_end=html.index('<div class="topbar">',search_start)
search_markup=html[search_start:search_end]
nav_start=html.index('<nav class="toolbar"',search_end)
nav_end=html.index('</nav>',nav_start)+len('</nav>')
nav_markup=html[nav_start:nav_end]
html=html[:search_start]+html[nav_end+len('</div>'):]
header_start=html.index('<header>')
header_end=html.index('</header>',header_start)+len('</header>')
brand=html[header_start+len('<header>'):html.index('<span class="tag">',header_start)]
html=html[:header_start]+'<header>'+brand+'<div class="header-controls">'+search_markup+nav_markup+'</div></header>'+html[header_end:]
html=html.replace('(h-180)/(bottom-top)', '(h-100)/(bottom-top)').replace('y:95+(h-170-', 'y:35+(h-90-')
html=html.replace('</style>', '''
body{height:100dvh;display:flex;flex-direction:column;overflow:hidden}header{height:auto;min-height:78px;flex-shrink:0;gap:20px;padding:12px 28px;position:relative;z-index:20}.brand{flex-shrink:0}.header-controls{display:flex;align-items:center;justify-content:flex-end;gap:14px;flex:1;min-width:0}.header-controls .search-box{position:relative;top:auto;left:auto;width:240px;flex:0 1 240px;min-width:160px;padding:7px 11px;z-index:21}.header-controls .search-box label{margin-bottom:3px}.header-controls .toolbar{max-width:none;flex-wrap:wrap;align-items:center;gap:6px}.header-controls .toolbar button{white-space:nowrap}#results:not(:empty){position:absolute;top:calc(100% + 5px);left:0;width:max(100%,280px);max-width:90vw;padding:5px 12px;background:#fffefa;border:1px solid #dce1d8;border-radius:7px;box-shadow:0 8px 24px #29352e18}body .layout{height:auto;flex:1;min-height:0}.groups-panel details{margin-top:0}@media(max-width:1100px){header{flex-wrap:wrap;gap:12px;padding:12px 18px}.header-controls{flex-wrap:wrap;justify-content:flex-start}.header-controls .search-box{width:210px;flex-basis:210px}.brand strong{font-size:20px}}@media(max-width:700px){header{padding:10px 14px;gap:12px}.brand{width:100%}.header-controls{width:100%;gap:10px}.header-controls .search-box{flex:1 1 100%;width:100%}#results:not(:empty){width:100%}.header-controls .toolbar{justify-content:flex-start;max-width:100%}.header-controls .toolbar button{padding:7px 9px;font-size:11px}.brand small{font-size:9px}}
</style>''')

# Compact parameter properties: no decorative icon, label/value on one row.
html=html.replace("add('div',n.kind==='parameter'?'☷':'❧','panel-icon');", '')
html=html.replace('</style>', """
#details{padding:22px 20px}#details .panel-label{margin-bottom:14px}#details .breadcrumb{margin-bottom:10px}#details h2{font-size:23px;margin-bottom:10px}#details p{font-size:12px;line-height:1.55;margin-bottom:12px}#details .type{margin-bottom:12px}#details dl>div{display:flex;align-items:baseline;gap:10px;padding:8px 0}#details dt{font-size:11px;line-height:1.45;margin:0;flex:0 1 auto}#details dd{font-size:12px;line-height:1.45;margin:0 0 0 auto;min-width:0;max-width:58%;text-align:right;overflow-wrap:anywhere}#details .context{margin-top:12px;padding:10px;font-size:11px;line-height:1.55}#details .notice{margin-top:14px;font-size:10px;line-height:1.55}
</style>""")

html=html.replace("add('div','Паспорт узла','panel-label');", '')

# Focus the opened branch rather than shrinking the whole map.
html=html.replace('function fit(){', 'function fit(){stopCamera();')
html=html.replace('const z=Math.max(.005,Math.min(2.5,zoom*factor));', 'stopCamera();const z=Math.max(.005,Math.min(2.5,zoom*factor));')
html=html.replace("if(e.button!==0||e.target.closest('button'))return;", "if(e.button!==0||e.target.closest('button'))return;stopCamera();")
html=html.replace("function reveal(id){let n=", "function reveal(id){stopCamera();let n=")
html=html.replace("function closeDetails(){", r"""
let cameraFrame=null;
function stopCamera(){if(cameraFrame!==null){cancelAnimationFrame(cameraFrame);cameraFrame=null;}}
function moveCamera(target){
 stopCamera();
 if(matchMedia('(prefers-reduced-motion: reduce)').matches){zoom=target.zoom;pan={x:target.x,y:target.y};transform();return;}
 const from={zoom,x:pan.x,y:pan.y},start=performance.now();
 function step(now){
  const t=Math.min(1,(now-start)/280),ease=1-Math.pow(1-t,3);
  zoom=from.zoom+(target.zoom-from.zoom)*ease;
  pan={x:from.x+(target.x-from.x)*ease,y:from.y+(target.y-from.y)*ease};transform();
  cameraFrame=t<1?requestAnimationFrame(step):null;
 }
 cameraFrame=requestAnimationFrame(step);
}
function focusBranch(id){
 const n=byId.get(id),ids=new Set([id,...(n.collapsed?[]:children(id).filter(visible).map(c=>c.id))]);
 const els=[...nodes.children].filter(el=>ids.has(el.dataset.id));
 const left=Math.min(...els.map(el=>byId.get(el.dataset.id).x)),right=Math.max(...els.map(el=>byId.get(el.dataset.id).x+el.offsetWidth));
 const top=Math.min(...els.map(el=>byId.get(el.dataset.id).y)),bottom=Math.max(...els.map(el=>byId.get(el.dataset.id).y+el.offsetHeight));
 const w=canvas.clientWidth,h=canvas.clientHeight;
 // Keep text readable for long lists; the background can still be dragged.
 const widthFit=Math.max(.005,(w-60)/(right-left)),heightFit=(h-100)/(bottom-top);
 const z=n.collapsed?zoom:Math.min(1.15,widthFit,Math.max(.85,heightFit));
 moveCamera({zoom:z,x:w/2-(left+right)/2*z,y:(h-40)/2-(top+bottom)/2*z});
}
function closeDetails(){""")

# Mirror left-hand branch alignment while retaining actual top-left coordinates.
html=html.replace("el.dataset.id=n.id;", "el.classList.toggle('left-branch',n.side===-1);el.dataset.id=n.id;")
html=html.replace('</style>', '.node.left-branch{text-align:right;justify-content:flex-end}\n</style>')

# Compact help, available to mouse, keyboard, and touch users.
help_start=html.index('<div class="hint">')
help_end=html.index('</div>',help_start)+len('</div>')
html=html[:help_start]+'''<div class="help-wrap"><button id="help-button" type="button" aria-label="Как пользоваться картой" aria-describedby="help-tooltip" aria-controls="help-tooltip" aria-expanded="false">?</button><div id="help-tooltip" role="tooltip" hidden><div class="help-content"><strong>Как пользоваться картой</strong><ul><li>Тяните узел — его ветка следует за ним.</li><li>Тяните фон — карта перемещается.</li><li>Колесо и кнопки +/− меняют масштаб.</li><li>Двойной щелчок по группе или подгруппе раскрывает и сворачивает ветку.</li><li>Двойной щелчок по параметру открывает справку; щелчок по пустому месту закрывает её.</li></ul></div></div></div>'''+html[help_end:]
html=html.replace('</style>', '''
.bottom{justify-content:space-between}.help-wrap{position:relative;pointer-events:auto}#help-button{width:30px;height:30px;border:1px solid #c6d2ba;border-radius:50%;background:#fffefa;color:#637f48;font:18px Georgia,serif;box-shadow:0 2px 7px #29352e0a}#help-button:hover,#help-button[aria-expanded="true"]{background:#eaf0df;border-color:#8ca576}#help-tooltip{position:absolute;bottom:100%;left:0;width:300px;max-width:calc(100vw - 26px);padding-bottom:10px;color:#53634f;font-size:12px;line-height:1.6}#help-tooltip[hidden]{display:none}.help-content{background:#fffefa;border:1px solid #d9dfd2;border-radius:9px;padding:14px 16px;box-shadow:0 6px 24px #29352e18}.help-content strong{font-size:13px;font-weight:600}.help-content ul{padding-left:16px;margin:8px 0 0}.help-content li+li{margin-top:5px}
</style>''')
html=html.replace('</script>', r'''
const helpButton=document.querySelector('#help-button'),helpTip=document.querySelector('#help-tooltip'),helpWrap=document.querySelector('.help-wrap');
let helpPinned=false;
function showHelp(open){helpTip.hidden=!open;helpButton.setAttribute('aria-expanded',String(open));}
helpWrap.addEventListener('pointerenter',e=>{if(e.pointerType!=='touch')showHelp(true);});
helpWrap.addEventListener('pointerleave',()=>{if(!helpPinned&&document.activeElement!==helpButton)showHelp(false);});
helpButton.addEventListener('focus',()=>showHelp(true));
helpButton.addEventListener('blur',()=>{if(!helpPinned)showHelp(false);});
helpButton.addEventListener('click',()=>{helpPinned=!helpPinned;showHelp(helpPinned);});
document.addEventListener('pointerdown',e=>{if(!helpWrap.contains(e.target)){helpPinned=false;showHelp(false);}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){helpPinned=false;showHelp(false);}});
</script>''')

# Article references are data; links are validated and rendered without HTML injection.
html=html.replace('const palette={}, data=[];', r'''
function blogLinks(n){
 return Array.isArray(n.blog_links)?n.blog_links.filter(link=>{
  if(!link||typeof link.title!=='string'||!link.title.trim()||typeof link.url!=='string')return false;
  try{const u=new URL(link.url);return u.protocol==='https:'&&u.hostname==='thebuild.com'&&!u.username&&!u.password&&!u.port&&u.pathname.startsWith('/blog/');}catch{return false;}
 }):[];
}
function leafMarker(n){
 const dot=document.createElement('span');
 dot.className=blogLinks(n).length?'blog-star':'leaf-dot';
 if(blogLinks(n).length){dot.title='Есть статья в The Build';dot.setAttribute('role','img');dot.setAttribute('aria-label','Есть статья в The Build');}
 return dot;
}
const palette={}, data=[];''')
html=html.replace("const dot=document.createElement('span');dot.className='leaf-dot';el.prepend(dot);", 'el.prepend(leafMarker(n));')
# Add references after all parameter descriptions, at the bottom of the card.
html=html.replace("\n \n\n}", r'''
 if(n.kind==='parameter'&&blogLinks(n).length){
  const section=add('section','','blog-references');
  const heading=document.createElement('h3');heading.textContent='Из блога The Build';section.append(heading);
  for(const link of blogLinks(n)){
   const a=document.createElement('a');a.href=link.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=link.title;
   a.setAttribute('aria-label',link.title+' (открывается в новой вкладке)');section.append(a);
  }
 }
}
''')
html=html.replace('</style>', '''
.blog-star{display:inline-block;width:12px;height:12px;flex:0 0 12px;background:#bd1635;clip-path:polygon(50% 3.125%,61.875% 38.125%,96.875% 50%,61.875% 61.875%,50% 96.875%,38.125% 61.875%,3.125% 50%,38.125% 38.125%)}.blog-references{margin-top:16px;padding-top:12px;border-top:1px solid #e5e8de}.blog-references h3{font-size:11px;color:#7d8779;font-weight:normal;margin:0 0 8px}.blog-references a{display:block;font-size:12px;line-height:1.6;color:#9f1933;text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}.blog-references a+a{margin-top:8px}.blog-references a:hover{color:#c51d42}
</style>''')

# Official documentation links are separate from blog references and add no marker.
html=html.replace('function blogLinks(n){', r'''
function documentationLink(n){
 const link=n.documentation_link;
 if(!link||typeof link.title!=='string'||!link.title.trim()||typeof link.url!=='string')return null;
 try{
  const u=new URL(link.url);
  return u.protocol==='https:'&&u.hostname==='www.postgresql.org'&&!u.username&&!u.password&&!u.port&&u.pathname.startsWith('/docs/current/')&&u.pathname.endsWith('.html')&&u.hash?link:null;
 }catch{return null;}
}
function qhbDocumentationLink(n){
 const link=n.qhb_documentation_link;
 if(!link||typeof link.title!=='string'||!link.title.trim()||typeof link.url!=='string')return null;
 try{
  const u=new URL(link.url);
  return u.protocol==='https:'&&u.hostname==='repo.quantom.info'&&!u.username&&!u.password&&!u.port&&u.pathname.startsWith('/qhb/std-1/doc/1.5.3/ru/')&&u.pathname.endsWith('.html')&&u.hash?link:null;
 }catch{return null;}
}
function blogLinks(n){''')
html=html.replace(" if(n.kind==='parameter'&&blogLinks(n).length){", r'''
 const qhbDocumentation=n.kind==='parameter'?qhbDocumentationLink(n):null;
 if(qhbDocumentation){
  const section=add('section','','documentation-reference qhb-documentation-reference');
  const heading=document.createElement('h3');heading.textContent='Документация QHB';section.append(heading);
  const a=document.createElement('a');a.href=qhbDocumentation.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=qhbDocumentation.title;
  a.setAttribute('aria-label',qhbDocumentation.title+' (просмотр поверх карты)');section.append(a);
 }
 const documentation=n.kind==='parameter'?documentationLink(n):null;
 if(documentation){
  const section=add('section','','documentation-reference');
  const heading=document.createElement('h3');heading.textContent='Документация PostgreSQL';section.append(heading);
  const a=document.createElement('a');a.href=documentation.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=documentation.title;
  a.setAttribute('aria-label',documentation.title+' (открывается в новой вкладке)');section.append(a);
 }
 if(n.kind==='parameter'&&blogLinks(n).length){''')
html=html.replace('</style>', '''
.documentation-reference{margin-top:16px;padding-top:12px;border-top:1px solid #e5e8de}.documentation-reference h3{font-size:11px;color:#7d8779;font-weight:normal;margin:0 0 8px}.documentation-reference a{display:block;font-size:12px;line-height:1.6;color:#336791;text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}.documentation-reference a:hover{color:#214e75}
</style>''')

html=html.replace('<button id="reset">', '<button id="export-state">Экспорт</button><button id="import-state">Импорт</button><input id="state-file" type="file" accept=".json,application/json" hidden><button id="reset">')
html=html.replace('</header>', '</header><div id="state-status" role="status" hidden></div>')
html=html.replace('</style>', '#state-status{padding:8px 18px;background:#edf2e4;font-size:12px;flex-shrink:0}#state-status[data-error="true"]{background:#fbe9e7;color:#942e24}</style>')
html=html.replace('</script>', r'''
const stateFile=document.querySelector('#state-file'),stateStatus=document.querySelector('#state-status');
function reportState(message,error=false){
 stateStatus.textContent=message;stateStatus.dataset.error=String(error);stateStatus.hidden=false;
}
function validateState(value){
 if(!value||value.version!==1||!value.nodes||typeof value.nodes!=='object'||Array.isArray(value.nodes))throw new Error('Неверный формат или версия файла настроек.');
 const knownKeys=new Set(stateKeys.values());let matches=0;
 for(const [key,entry] of Object.entries(value.nodes)){
  if(!entry||typeof entry!=='object'||Array.isArray(entry)||typeof entry.collapsed!=='boolean'||typeof entry.hidden!=='boolean'||!Number.isFinite(entry.dx)||!Number.isFinite(entry.dy))throw new Error('В файле некорректные настройки узлов.');
  if(knownKeys.has(key))matches++;
 }
 if(!matches)throw new Error('В файле нет настроек для узлов этой карты.');
 return value;
}
document.querySelector('#export-state').onclick=()=>{
 const url=URL.createObjectURL(new Blob([JSON.stringify(currentState(),null,2)+'\n'],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='pg_settings_map.json';document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 reportState('Настройки экспортированы в pg_settings_map.json.');
};
document.querySelector('#import-state').onclick=()=>stateFile.click();
stateFile.onchange=async()=>{
 const file=stateFile.files[0];if(!file)return;
 try{
  if(file.size>2*1024*1024)throw new Error('Файл настроек слишком большой (максимум 2 МБ).');
  const saved=validateState(JSON.parse(await file.text()));
  applyState(saved);select('root');closeDetails();render();fit();
  search.value='';results.replaceChildren();saveState();
  reportState('Настройки импортированы и применены.');
 }catch(error){reportState(error instanceof SyntaxError?'Не удалось прочитать JSON. Выберите файл экспорта настроек.':error.message,true);}
 finally{stateFile.value='';}
};
</script>''')

# Keep action buttons on a single row; narrow viewports can scroll the row.
html=html.replace('</style>', '''
.header-controls .toolbar{flex-wrap:nowrap;justify-content:flex-start;min-width:0;overflow-x:auto;max-width:100%;padding:4px;scrollbar-width:thin}.header-controls .toolbar button{flex-shrink:0;font-size:11px;padding:7px 8px}.header-controls{gap:10px}.header-controls .search-box{flex-basis:180px;min-width:140px}@media(max-width:1100px){.header-controls{flex-wrap:nowrap}}@media(max-width:700px){.header-controls{flex-wrap:wrap}.header-controls .search-box{flex:1 1 100%}.header-controls .toolbar{width:100%}}
</style>''')

html=html.replace('</body>', (root / 'tools/templates/reference_viewer.html').read_text()+'\n</body>')

# The embedded JSON is data, never executable HTML. All visible fields use textContent.
(root / 'pg_settings_full.html').write_text(html)
print('Generated pg_settings_full.html')
