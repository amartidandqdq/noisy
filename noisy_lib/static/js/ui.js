// ui.js - Render functions par section. Lecture seule du payload WS.

const H = 60, rpsH = [], visH = [];

function fmt(n) {
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return String(n);
}
function fmtB(b) {
  if (b >= 1e9) return (b/1e9).toFixed(1)+' GB';
  if (b >= 1e6) return (b/1e6).toFixed(1)+' MB';
  if (b >= 1e3) return (b/1e3).toFixed(1)+' KB';
  return b+' B';
}
function fmtUp(s) {
  const h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60;
  return [h,m,sec].map(v=>String(v).padStart(2,'0')).join(':');
}
function spark(el, data) {
  el.innerHTML='';
  const p=Math.max(...data,1);
  data.slice(-20).forEach(v=>{
    const b=document.createElement('div');b.className='spark-bar';
    b.style.height=Math.max(1,(v/p)*20)+'px';el.appendChild(b);
  });
}
function diurnalChart(curve, hour) {
  const svg=document.getElementById('diurnalSvg');
  if (!svg) return;
  const w=240, h=80;
  let pts=curve.map((c,i)=>[i*(w/23), h-c.weight*h]);
  let pathD='M'+pts.map(p=>p.join(',')).join('L');
  let areaD=pathD+'L'+w+','+h+'L0,'+h+'Z';
  const mx=hour*(w/23), my=h-curve[Math.min(23,Math.floor(hour))].weight*h;
  svg.innerHTML=`<path class="diurnal-area" d="${areaD}"/><path class="diurnal-line" d="${pathD}"/><circle class="diurnal-marker" cx="${mx}" cy="${my}" r="3"/>`;
}
function healthColor(v) { return v>=0.7?'var(--accent)':v>=0.4?'var(--warn)':'var(--fail)'; }
function fpColor(v) { return v>=0.6?'good':v>=0.3?'mid':'bad'; }

// ---- Render: header / live ----
function renderLive(d) {
  const a=d.aggregate;
  const set=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  set('visited', fmt(a.visited));
  set('failed', fmt(a.failed));
  set('failPct', a.fail_pct.toFixed(1)+'%');
  set('c4', fmt(a.client_errors));
  set('c5', fmt(a.server_errors));
  set('cn', fmt(a.network_errors));
  set('rps', a.rps.toFixed(1));
  set('queued', fmt(a.queued));
  set('uniqueUrls', fmt(a.unique_urls));
  set('activeDomains', fmt(a.active_domains));
  set('uptime', fmtUp(d.uptime_seconds));
  set('uptimeMini', fmtUp(d.uptime_seconds));
  set('bw', a.bandwidth_kbps.toFixed(0)+' KB/s');
  set('bwTotal', fmtB(a.total_bytes));

  // Sparklines
  rpsH.push(a.rps); if(rpsH.length>H) rpsH.shift();
  visH.push(a.visited); if(visH.length>H) visH.shift();
  spark(document.getElementById('rpsSpark'), rpsH);
  spark(document.getElementById('visitedSpark'), visH);

  // Diurnal
  if (d.diurnal_curve) diurnalChart(d.diurnal_curve, d.current_hour);

  // Fingerprint
  const fp=d.fingerprint;
  set('fpScore', (fp.overall*100).toFixed(0)+'%');
  const fpFill=document.getElementById('fpFill');
  if (fpFill) {
    fpFill.style.width=fp.overall*100+'%';
    fpFill.className='fp-fill '+fpColor(fp.overall);
  }
  set('fpLabel', fp.overall>=0.6?'natural':fp.overall>=0.3?'moderate':'uniform');

  // Fingerprint detail
  const fpd=document.getElementById('fpDetail');
  if (fpd) {
    fpd.innerHTML=['domain_diversity','tld_diversity','timing_variance'].map(k=>{
      const v=fp[k];
      return `<div class="fp-bar-wrap" style="margin:6px 0">
        <span style="min-width:140px;font-size:11px;color:var(--text-dim)">${k.replace('_',' ')}</span>
        <div class="fp-bar" style="width:120px"><div class="fp-fill ${fpColor(v)}" style="width:${v*100}%"></div></div>
        <span style="font-size:11px">${(v*100).toFixed(0)}%</span>
      </div>`;
    }).join('');
  }

  // Alert + pause state (global UI)
  const ab=document.getElementById('alertBanner');
  if (ab) ab.classList.toggle('show', a.alert_active);
  const dot=document.getElementById('dot');
  const btn=document.getElementById('btnPause');
  if (d.paused) {
    if (dot) dot.className='dot paused';
    if (btn) { btn.textContent='resume'; btn.classList.add('active'); }
  } else {
    if (dot) dot.className='dot';
    if (btn) { btn.textContent='pause'; btn.classList.remove('active'); }
  }
  window._paused = d.paused;
}

// ---- Render: users tab ----
function renderUsers(d) {
  if (!d.users) return;
  const nMobile=d.users.filter(u=>u.is_mobile).length;
  const nActive=d.users.filter(u=>u.active).length;
  const nGeo=new Set(d.users.map(u=>u.geo).filter(Boolean)).size;
  const set=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  set('userCount', d.users.length);
  let parts=[];
  if (nMobile) parts.push(nMobile+' mobile');
  parts.push((d.users.length-nMobile)+' desktop');
  if (nActive<d.users.length) parts.push(nActive+' active');
  if (nGeo) parts.push(nGeo+' geo');
  set('userBreakdown', parts.join(' · '));

  const tb=document.getElementById('usersBody');
  if (!tb) return;
  if (d.users.length) {
    tb.innerHTML=d.users.map(u=>`<tr>
      <td class="uid">U${u.id}</td>
      <td style="color:${u.is_mobile?'var(--warn)':'var(--info)'}">${u.is_mobile?'mobile':'desktop'}</td>
      <td style="color:var(--text-dim)">${u.geo||'-'}</td>
      <td><span style="color:${u.active?'var(--accent)':'var(--fail)'}">${u.active?'active':'sleep'}</span></td>
      <td>${fmt(u.visited)}</td><td>${fmt(u.failed)}</td>
      <td class="tc4">${fmt(u.client_errors)}</td><td class="tc5">${fmt(u.server_errors)}</td>
      <td class="tcn">${fmt(u.network_errors)}</td><td>${fmt(u.queued)}</td>
      <td>${fmtB(u.bytes)}</td>
      <td><div class="dbar-w"><div class="dbar"><div class="dfill" style="width:${u.diurnal_weight*100}%"></div></div><span class="dval">${u.diurnal_weight}</span></div></td>
      <td class="ua-cell" title="${u.ua}">${u.ua}</td>
    </tr>`).join('');
  }
}

// ---- Render: stealth toggles ----
const FEAT_GROUPS = [
  ['Core Stealth', [
    ['tls_rotation', 'TLS Rotation', 'JA3 cipher rotation toutes les 15-60 min'],
    ['realistic_depth', 'Realistic Depth', '50-70% bounce / 20-30% short / 10-25% deep (re-rolled per session)'],
    ['referer_chains', 'Referer Chains', 'Search/direct/social/cross-site referers'],
    ['asset_fetching', 'Asset Fetching', 'Partial download of images/CSS/JS'],
    ['bandwidth_throttle', 'Bandwidth Throttle', 'Token bucket (fiber/4G/ADSL)'],
    ['auto_pause', 'Auto-Pause', 'Pause auto si fail% > 50%'],
    ['diurnal', 'Diurnal Curve', 'Modèle 24h (pic midi, creux nuit)'],
  ]],
  ['DNS Stealth', [
    ['dns_optimized', 'DNS Optimized', 'Connection:close, 64KB max, skip assets'],
    ['dns_prefetch', 'DNS Prefetch', 'Browser-like DNS prefetch from page links'],
    ['thirdparty_burst', '3rd-Party Burst', 'CDN/tracker/ad DNS burst per page (iceberg)'],
    ['background_noise', 'Background Noise', 'NTP, Spotify, WhatsApp, Steam DNS chatter'],
    ['nxdomain_probes', 'NXDOMAIN Probes', 'Chrome intranet detector + captive portal'],
  ]],
  ['Anti-DPI', [
    ['ech', 'ECH (Encrypted SNI)', 'curl_cffi BoringSSL — masque le SNI du FAI'],
    ['stream_noise', 'Stream Noise', 'Long CDN connections simulating video'],
  ]],
];
function renderStealthToggles(features) {
  const box=document.getElementById('featToggles');
  if (!box || !features) return;
  let html='';
  for (const [groupName, items] of FEAT_GROUPS) {
    html += `<div class="feat-group-title">${groupName}</div>`;
    for (const [key, label, tip] of items) {
      // tls_rotation/realistic_depth/etc default to true (undefined === on)
      const defaultOn = ['tls_rotation','realistic_depth','referer_chains','asset_fetching','auto_pause','diurnal'].includes(key);
      const on = features[key] === true || (features[key] === undefined && defaultOn);
      html += `<div class="feat-row">
        <div class="feat-info"><div class="feat-name">${label}</div><div class="feat-tip">${tip}</div></div>
        <div class="toggle ${on?'on':''}" data-feat-key="${key}" data-feat-on="${on}"></div>
      </div>`;
    }
  }
  box.innerHTML=html;
  // Attach click handlers
  box.querySelectorAll('.toggle').forEach(t=>{
    t.onclick = ()=>{
      const k=t.dataset.featKey;
      const wasOn=t.dataset.featOn==='true';
      toggleFeat(k, !wasOn);
      t.classList.toggle('on');
      t.dataset.featOn = String(!wasOn);
    };
  });
}

// ---- Render: DNS tab ----
function renderDns(d) {
  const set=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  set('nsfwCount', d.nsfw_blocklist_size?fmt(d.nsfw_blocklist_size):'-');
  if (d.dns_servers && d.dns_servers.length) {
    set('dnsServer', d.dns_servers[0]);
    const extra=document.getElementById('dnsExtra');
    if (extra) {
      if (d.dns_servers.length>1) {
        extra.innerHTML=`<span style="cursor:pointer;text-decoration:underline" onclick="this.textContent='${d.dns_servers.join(' · ')}'">+ ${d.dns_servers.length-1} more</span>`;
      } else {
        extra.textContent='system';
      }
    }
  }
  // DNS active toggles
  if (d.features) {
    const dnsKeys=['dns_optimized','dns_prefetch','thirdparty_burst','background_noise','nxdomain_probes','ech','stream_noise'];
    const active=dnsKeys.filter(k=>d.features[k]===true);
    set('dnsActiveList', active.length?active.join(', '):'aucun (toggle dans Stealth)');
  }
}

// ---- Render: domains tab ----
function renderDomains(d) {
  const td=document.getElementById('topDomains');
  if (td && d.top_domains && d.top_domains.length) {
    td.innerHTML='<table><thead><tr><th>Domain</th><th>OK</th><th>Fail</th><th>Health</th><th>Data</th></tr></thead><tbody>'
      +d.top_domains.slice(0,15).map(dm=>`<tr>
        <td style="color:var(--info)">${dm.domain}</td><td>${dm.ok}</td><td>${dm.fail}</td>
        <td><span class="hbar"><span class="hfill" style="width:${dm.health*100}%;background:${healthColor(dm.health)}"></span></span>${(dm.health*100).toFixed(0)}%</td>
        <td>${fmtB(dm.bytes)}</td>
      </tr>`).join('')+'</tbody></table>';
  }
  const tl=document.getElementById('tldDist');
  if (tl && d.tld_distribution && d.tld_distribution.length) {
    const maxC=d.tld_distribution[0].count;
    tl.innerHTML=d.tld_distribution.map(t=>`<div class="tld-row">
      <span class="tld-name">${t.tld}</span>
      <div class="tld-bar"><div class="tld-fill" style="width:${(t.count/maxC)*100}%"></div></div>
      <span class="tld-count">${fmt(t.count)}</span>
    </div>`).join('');
  }
  const cd=document.getElementById('catDist');
  if (cd && d.category_distribution && d.category_distribution.length) {
    const maxCat=d.category_distribution[0].count;
    const colors={news:'#4fc3f7',social:'#e040fb',ecommerce:'#ffb74d',tech:'#00e676',
      education:'#7c4dff',finance:'#ffd740',entertainment:'#ff5252',travel:'#26c6da',
      health:'#66bb6a',sports:'#ff7043',government:'#78909c',other:'#546e7a'};
    cd.innerHTML=d.category_distribution.map(c=>`<div class="tld-row">
      <span class="tld-name" style="color:${colors[c.category]||'var(--info)'};min-width:100px">${c.category}</span>
      <div class="tld-bar"><div class="tld-fill" style="width:${(c.count/maxCat)*100}%;background:${colors[c.category]||'var(--info)'}"></div></div>
      <span class="tld-count">${fmt(c.count)}</span>
    </div>`).join('');
  }
}

// ---- Render: logs tab ----
function renderLogs(d) {
  const ll=document.getElementById('liveLog');
  if (ll && d.request_log && d.request_log.length) {
    ll.innerHTML=d.request_log.slice(-30).reverse().map(r=>{
      const t=new Date(r.ts*1000);
      const sc=r.status>=200&&r.status<400?'ok':'err';
      return `<div class="log-entry">
        <span class="log-ts">${t.toLocaleTimeString()}</span>
        <span class="log-status ${sc}">${r.status||'ERR'}</span>
        <span class="log-domain">${r.domain}</span>
        <span class="log-url">${r.url}</span>
      </div>`;
    }).join('');
  }
  const el=document.getElementById('errList');
  if (el) {
    if (d.recent_errors && d.recent_errors.length) {
      el.innerHTML=d.recent_errors.slice(-20).reverse().map(e=>{
        const t=new Date(e.ts*1000);
        return `<div class="err-entry">
          <span class="log-ts">${t.toLocaleTimeString()}</span>
          <span class="err-msg"> U${e.user_id} ${e.error}</span>
          <div class="err-url">${e.url}</div>
        </div>`;
      }).join('');
    } else {
      el.innerHTML='<div class="no-data">no errors</div>';
    }
  }
}

// ---- Master render ----
function update(d) {
  renderLive(d);
  renderUsers(d);
  renderDns(d);
  renderDomains(d);
  renderLogs(d);
  if (d.features) renderStealthToggles(d.features);
  const lu=document.getElementById('lastUpdate');
  if (lu) lu.textContent=new Date(d.timestamp).toLocaleTimeString();
}
