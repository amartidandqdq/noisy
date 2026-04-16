// app.js - Router (tabs) + WebSocket + REST handlers + keyboard shortcuts

let ws, rDelay = 1000;
let cfgLoaded = false, featLoaded = false, tldFilterLoaded = false;
let currentTab = 'live';

// ---- Tab routing ----
const TAB_HINTS = {
  live: 'aggregate metrics',
  users: 'virtual users + quick settings + config',
  stealth: 'feature toggles',
  dns: 'resolver + blocklist',
  domains: 'top domains, TLDs, categories',
  logs: 'request log + errors',
};
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.sb-item').forEach(t=>t.classList.remove('active'));
  const tab=document.getElementById('tab-'+name);
  const item=document.querySelector(`.sb-item[data-tab="${name}"]`);
  if (tab) tab.classList.add('active');
  if (item) item.classList.add('active');
  currentTab=name;
  const cur=document.getElementById('tbCurrentTab');
  const hint=document.getElementById('tbHint');
  if (cur) cur.textContent=name.toUpperCase();
  if (hint) hint.textContent=TAB_HINTS[name]||'';
  try { localStorage.setItem('noisy_tab', name); } catch(e){}
}
document.getElementById('sbNav').addEventListener('click', e=>{
  const it=e.target.closest('.sb-item');
  if (it && it.dataset.tab) switchTab(it.dataset.tab);
});

// ---- Keyboard shortcuts ----
const KEY_TO_TAB = ['live','users','stealth','dns','domains','logs'];
document.addEventListener('keydown', e=>{
  if (e.target.tagName==='INPUT' || e.target.tagName==='SELECT' || e.target.tagName==='TEXTAREA') return;
  if (e.metaKey||e.ctrlKey||e.altKey) return;
  const idx=parseInt(e.key)-1;
  if (idx>=0 && idx<KEY_TO_TAB.length) switchTab(KEY_TO_TAB[idx]);
  else if (e.key==='p'||e.key==='P') togglePause();
  else if (e.key==='t'||e.key==='T') toggleTheme();
  else if (e.key==='d'||e.key==='D') toggleDense();
});

// ---- WS ----
function setStatus(on) {
  const dot=document.getElementById('dot');
  const txt=document.getElementById('statusText');
  if (dot) dot.className='dot'+(on?'':' off');
  if (txt) txt.textContent=on?'live':'reconnecting';
}
function connect() {
  const p=location.protocol==='https:'?'wss:':'ws:';
  ws=new WebSocket(`${p}//${location.host}/ws/metrics`);
  ws.onopen=()=>{ setStatus(true); rDelay=1000; };
  ws.onmessage=e=>{
    try {
      const d=JSON.parse(e.data);
      update(d);
      if (!cfgLoaded && d.users) { cfgLoaded=true; loadConfig(); }
      if (!tldFilterLoaded) { tldFilterLoaded=true; loadTldFilter(); }
      if (!featLoaded) { featLoaded=true; loadFeatures(); }
    } catch(x) { console.error(x); }
  };
  ws.onclose=()=>{ setStatus(false); setTimeout(connect, rDelay); rDelay=Math.min(rDelay*1.5, 10000); };
  ws.onerror=()=>ws.close();
}

// ---- Topbar actions ----
function togglePause() {
  fetch('/api/'+(window._paused?'resume':'pause'), {method:'POST'});
}
function toggleTheme() {
  const r=document.documentElement;
  const light=r.classList.toggle('light');
  document.getElementById('btnTheme').textContent=light?'dark':'light';
  try { localStorage.setItem('noisy_theme', light?'light':'dark'); } catch(e){}
}
function toggleDense() {
  const r=document.documentElement;
  const dense=r.classList.toggle('dense');
  document.getElementById('btnDense').textContent=dense?'comfy':'dense';
  try { localStorage.setItem('noisy_dense', dense?'1':'0'); } catch(e){}
}
function exportMetrics() { window.open('/api/export', '_blank'); }

// ---- Config tab ----
async function loadConfig() {
  try {
    const r=await fetch('/api/config');
    const c=await r.json();
    const set=(id,v)=>{ const el=document.getElementById(id); if(el) el.value=v; };
    set('cfgMinSleep', c.min_sleep);
    set('cfgMaxSleep', c.max_sleep);
    set('cfgMaxDepth', c.max_depth);
    set('cfgDomainDelay', c.domain_delay);
    set('cfgMaxLinks', c.max_links_per_page);
  } catch(e) {}
}
async function applyConfig() {
  const get=id=>document.getElementById(id).value;
  const data={
    min_sleep: parseFloat(get('cfgMinSleep')),
    max_sleep: parseFloat(get('cfgMaxSleep')),
    max_depth: parseInt(get('cfgMaxDepth')),
    domain_delay: parseFloat(get('cfgDomainDelay')),
    max_links_per_page: parseInt(get('cfgMaxLinks')),
  };
  try {
    await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    document.getElementById('cfgStatus').textContent='applied!';
    setTimeout(()=>document.getElementById('cfgStatus').textContent='', 2000);
  } catch(e) { document.getElementById('cfgStatus').textContent='error'; }
}

// ---- Features ----
const GEO_LIST = ['','europe_fr','europe_de','europe_es','europe_it','europe_uk','europe_nl','europe_pl','europe_pt','europe_se',
  'americas_us','americas_br','americas_mx','americas_ca','asia_jp','asia_kr','asia_cn','asia_in',
  'middle_east_ae','middle_east_tr','africa_za','oceania_au'];
async function loadFeatures() {
  const sel=document.getElementById('featGeo');
  if (sel) sel.innerHTML=GEO_LIST.map(g=>`<option value="${g}">${g||'off'}</option>`).join('');
  try {
    const r=await fetch('/api/features');
    const f=await r.json();
    if (f.schedule) document.getElementById('featSchedule').value=f.schedule[0]+'-'+f.schedule[1];
    if (sel && f.geo_profiles && f.geo_profiles.length) sel.value=f.geo_profiles[0];
    const uc=document.getElementById('userCount');
    const total=Math.max(1, (f.mobile_count + (uc ? (parseInt(uc.textContent)||0) : 0)));
    document.getElementById('featMobile').value=f.mobile_count/total;
    document.getElementById('featSearch').value=f.search_workers||0;
  } catch(e) {}
}
async function applyFeatures() {
  const data={};
  const sched=document.getElementById('featSchedule').value.trim();
  data.schedule = sched && sched!=='off' ? sched : null;
  const geo=document.getElementById('featGeo').value;
  data.geo = geo || null;
  data.mobile_ratio = parseFloat(document.getElementById('featMobile').value)||0;
  data.search_workers = parseInt(document.getElementById('featSearch').value)||0;
  try {
    const r=await fetch('/api/features', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const d=await r.json();
    const st=document.getElementById('featStatus');
    if (d.error) { st.textContent=d.error; st.style.color='var(--fail)'; }
    else { st.textContent='applied!'; st.style.color='var(--accent)'; setTimeout(()=>st.textContent='', 2000); }
  } catch(e) { document.getElementById('featStatus').textContent='error'; }
}
async function toggleFeat(key, value) {
  const data={};
  data[key]=value;
  await fetch('/api/features', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  // Sync form inputs
  if (key==='schedule') document.getElementById('featSchedule').value=value||'off';
  if (key==='geo') document.getElementById('featGeo').value=value||'';
  if (key==='mobile_ratio') document.getElementById('featMobile').value=value;
  if (key==='search_workers') document.getElementById('featSearch').value=value;
}
async function resetFeatures() {
  document.getElementById('featSchedule').value='off';
  document.getElementById('featGeo').value='';
  document.getElementById('featMobile').value='0';
  document.getElementById('featSearch').value='0';
  await fetch('/api/features', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({schedule:null, geo:null, mobile_ratio:0, search_workers:0, diurnal:true})});
  document.getElementById('featStatus').textContent='reset!';
  setTimeout(()=>document.getElementById('featStatus').textContent='', 2000);
}

// ---- Users ----
async function addUser() {
  try {
    const r=await fetch('/api/users/add', {method:'POST'});
    const d=await r.json();
    if (d.error) alert(d.error);
  } catch(e) {}
}
async function removeUser() {
  try {
    const r=await fetch('/api/users/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
    const d=await r.json();
    if (d.error) alert(d.error);
  } catch(e) {}
}

// ---- TLD filter ----
async function loadTldFilter() {
  try {
    const r=await fetch('/api/tld-filter');
    const d=await r.json();
    const box=document.getElementById('regionCheckboxes');
    if (box) {
      box.innerHTML=d.available_regions.map(rg=>
        `<label class="region-cb"><input type="checkbox" value="${rg}" ${d.regions.includes(rg)?'checked':''}>${rg}</label>`
      ).join('');
    }
    const ct=document.getElementById('customTlds');
    if (ct) ct.value='';
    const status=document.getElementById('tldStatus');
    if (status && d.tld_filter.length) {
      status.innerHTML='Active: <span>'+d.tld_filter.join(', ')+'</span>';
    }
  } catch(e) {}
}
async function applyTldFilter() {
  const checks=document.querySelectorAll('#regionCheckboxes input:checked');
  const regions=Array.from(checks).map(c=>c.value);
  const raw=document.getElementById('customTlds').value;
  const custom=raw?raw.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean):[];
  try {
    const r=await fetch('/api/tld-filter', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({regions, custom_tlds:custom})});
    const d=await r.json();
    if (d.status==='ok') {
      document.getElementById('tldStatus').innerHTML=
        d.tld_filter && d.tld_filter.length
          ? 'Active: <span>'+d.tld_filter.join(', ')+'</span> ('+d.filtered+' sites)'
          : 'No filter (all sites)';
    }
  } catch(e) { document.getElementById('tldStatus').textContent='error'; }
}

// ---- Clear ----
function clearStats() {
  document.getElementById('topDomains').innerHTML='<div class="no-data">cleared</div>';
  document.getElementById('tldDist').innerHTML='<div class="no-data">cleared</div>';
  fetch('/api/clear-stats', {method:'POST'});
}
function clearLog() {
  document.getElementById('liveLog').innerHTML='<div class="no-data">cleared</div>';
  fetch('/api/clear-logs', {method:'POST'});
}
function clearErrors() {
  document.getElementById('errList').innerHTML='<div class="no-data">cleared</div>';
  fetch('/api/clear-logs', {method:'POST'});
}

// ---- Settings import/export ----
async function exportSettings() {
  try {
    const [feat, cfg, tld] = await Promise.all([
      fetch('/api/features').then(r=>r.json()),
      fetch('/api/config').then(r=>r.json()),
      fetch('/api/tld-filter').then(r=>r.json()),
    ]);
    const blob=new Blob([JSON.stringify({features:feat, config:cfg, tld_filter:tld}, null, 2)], {type:'application/json'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='noisy-settings.json';
    a.click();
  } catch(e) {}
}
async function importSettings(input) {
  if (!input.files[0]) return;
  const text=await input.files[0].text();
  try {
    const s=JSON.parse(text);
    if (s.features) await fetch('/api/features', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(s.features)});
    if (s.config) await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(s.config)});
    if (s.tld_filter && s.tld_filter.regions) await fetch('/api/tld-filter', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({regions:s.tld_filter.regions, custom_tlds:s.tld_filter.tld_filter||[]})});
    cfgLoaded=false; featLoaded=false; tldFilterLoaded=false;
  } catch(e) { alert('Invalid settings file'); }
  input.value='';
}

// ---- Boot ----
(function init() {
  // Restore persisted UI state
  try {
    const t=localStorage.getItem('noisy_theme');
    if (t==='light') {
      document.documentElement.classList.add('light');
      const bt=document.getElementById('btnTheme');
      if (bt) bt.textContent='dark';
    }
    const dn=localStorage.getItem('noisy_dense');
    if (dn==='1') {
      document.documentElement.classList.add('dense');
      const bd=document.getElementById('btnDense');
      if (bd) bd.textContent='comfy';
    }
    const tab=localStorage.getItem('noisy_tab');
    if (tab && KEY_TO_TAB.includes(tab)) switchTab(tab);
  } catch(e){}
  connect();
})();
