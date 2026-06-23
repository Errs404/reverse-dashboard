const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const reverseConfig = window.reverseConfig || {};

function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

function basename(path) {
  return String(path || '').split(/[\\/]/).filter(Boolean).pop() || path || '';
}

function statusClass(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9_-]/g, '') || 'unknown';
}

function setText(sel, value) {
  const el = $(sel);
  if (el) el.textContent = value;
}

function icon(name) {
  return `<span class="material-symbols-outlined">${esc(name)}</span>`;
}

function pathSegments(path) {
  const value = String(path || '');
  const normalized = value.replace(/\\/g, '/');
  const drive = /^[A-Za-z]:/.exec(normalized)?.[0] || '';
  const rawParts = normalized.replace(/^[A-Za-z]:/, '').split('/').filter(Boolean);
  return { root: drive || '/', parts: rawParts };
}

function renderFileBreadcrumb(path) {
  const el = $('#fileBreadcrumb');
  if (!el) return;
  const { root, parts } = pathSegments(path);
  let accumulated = root === '/' ? '/' : `${root}/`;
  const crumbs = [`<button type="button" data-breadcrumb="${esc(accumulated)}">${icon('home_storage')}<span>${esc(root)}</span></button>`];
  parts.forEach((part, index) => {
    accumulated = root === '/'
      ? `/${parts.slice(0, index + 1).join('/')}`
      : `${root}/${parts.slice(0, index + 1).join('/')}`;
    crumbs.push(`<i>/</i><button type="button" data-breadcrumb="${esc(accumulated)}"><span>${esc(part)}</span></button>`);
  });
  el.innerHTML = crumbs.join('');
  $$('[data-breadcrumb]').forEach(btn => btn.onclick = () => loadFiles(btn.dataset.breadcrumb));
}

function miniBars(seed, count = 14) {
  return sparkValues(seed, count, 16, 94).map(v => `<i style="--h:${Math.round(v)}%"></i>`).join('');
}

const dashboardTrend = { cpu: [], ram: [], disk: [], net: [] };

function durationHuman(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds || 0));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function setWidth(sel, value) {
  const el = $(sel);
  if (el) el.style.width = `${Math.min(100, Math.max(0, Number(value || 0)))}%`;
}

function pushTrend(key, value, max = 24) {
  dashboardTrend[key].push(Math.max(0, Math.min(100, Number(value || 0))));
  if (dashboardTrend[key].length > max) dashboardTrend[key].shift();
}

function trendPath(values, width = 720, height = 240) {
  if (!values.length) return '';
  const padded = values.length === 1 ? [values[0], values[0]] : values;
  return padded.map((v, i) => {
    const x = Math.round((width / (padded.length - 1)) * i);
    const y = Math.round(height - (v / 100) * (height - 24));
    return `${i === 0 ? 'M' : 'L'}${x} ${y}`;
  }).join(' ');
}

function chipClass(value) {
  const n = Number(value || 0);
  if (n >= 90) return 'critical';
  if (n >= 75) return 'warning';
  return 'success';
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(message, danger = false) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = message;
  el.style.borderColor = danger ? 'var(--danger)' : 'var(--line)';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2600);
}

function pct(id, value) {
  const text = $(`#${id}Percent`);
  const bar = $(`#${id}Bar`);
  if (text) text.textContent = `${Math.round(value)}%`;
  if (bar) bar.style.width = `${Math.min(100, Math.max(0, value))}%`;
}

function sparkValues(seed, count, min, max) {
  const values = [];
  let current = Math.max(min, Math.min(max, seed));
  for (let i = 0; i < count; i++) {
    current += Math.sin((Date.now() / 9000) + i) * 5 + (Math.random() - 0.5) * 6;
    current = Math.max(min, Math.min(max, current));
    values.push(current);
  }
  return values;
}

function updateDashboardVisuals(stats, procs) {
  const cpu = Number(stats.cpu?.percent || 0);
  const ram = Number(stats.memory?.percent || 0);
  const disk = Number(stats.disk?.percent || 0);
  const processCount = procs.processes?.length || 0;

  setText('#uptimeMetric', durationHuman(stats.uptime_seconds));
  setText('#bootMetric', `${Math.round((Number(stats.uptime_seconds || 0) / 86400) * 10) / 10} days online`);
  setText('#monitoringMetric', cpu > 85 || ram > 90 || disk > 90 ? 'Alert' : 'Live');
  setText('#monitoringIntervalMetric', `4s refresh · ${processCount} processes`);
  setText('#ramMetric', `${Math.round(ram)}%`);
  setText('#ramMetricDetail', `${stats.memory?.used_human || '-'} / ${stats.memory?.total_human || '-'}`);
  setText('#diskMetric', `${Math.round(disk)}%`);
  setText('#diskMetricDetail', `${stats.disk?.used_human || '-'} / ${stats.disk?.total_human || '-'}`);
  setText('#networkMetric', stats.network?.recv_human || '-');
  setText('#networkMetricDetail', `RX ${stats.network?.recv_human || '-'} · TX ${stats.network?.sent_human || '-'}`);
  setText('#cpuMetric', `${Math.round(cpu)}%`);
  setText('#cpuMetricDetail', `${stats.cpu?.cores || '-'} cores · load ${(stats.cpu?.load || []).slice(0, 3).join(' / ')}`);
  setWidth('#ramMetricBar', ram);
  setWidth('#diskMetricBar', disk);
  setWidth('#cpuMetricBar', cpu);

  pushTrend('cpu', cpu);
  pushTrend('ram', ram);
  pushTrend('disk', disk);
  pushTrend('net', Math.min(100, ((stats.network?.recv || 0) + (stats.network?.sent || 0)) / 1024 / 1024 / 20));
  $('#cpuTrendPath')?.setAttribute('d', trendPath(dashboardTrend.cpu));
  $('#ramTrendPath')?.setAttribute('d', trendPath(dashboardTrend.ram));
  $('#diskTrendPath')?.setAttribute('d', trendPath(dashboardTrend.disk));
  const networkSpark = $('#networkSpark');
  if (networkSpark) networkSpark.innerHTML = dashboardTrend.net.map(v => `<i style="--h:${Math.max(8, Math.round(v))}%"></i>`).join('');

  const health = Math.max(0, Math.round(100 - ((cpu * 0.34) + (ram * 0.33) + (disk * 0.23) + (processCount > 10 ? 5 : 0))));
  setText('#healthScore', `${health}%`);
  const ring = $('#healthRing');
  if (ring) ring.style.setProperty('--score', health);
  const status = health >= 75 ? 'Healthy' : health >= 55 ? 'Watch' : 'Critical';
  setText('#healthStatusText', `${status}: this single server is being monitored from live host telemetry.`);
  setText('#healthStatusDetail', `CPU ${Math.round(cpu)}%, RAM ${Math.round(ram)}%, Disk ${Math.round(disk)}%, ${processCount} processes sampled.`);
  [ ['#cpuCheck', 'CPU', cpu], ['#ramCheck', 'RAM', ram], ['#diskCheck', 'Disk', disk] ].forEach(([sel, label, value]) => {
    const el = $(sel);
    if (el) { el.textContent = `${label} ${Math.round(value)}%`; el.className = `status-chip ${chipClass(value)}`; }
  });
  const proc = $('#processCheck');
  if (proc) { proc.textContent = `Processes ${processCount}`; proc.className = `status-chip ${processCount > 10 ? 'warning' : 'success'}`; }
  setText('#networkRxMetric', stats.network?.recv_human || '-');
  setText('#networkTxMetric', stats.network?.sent_human || '-');
}

function initLogin() {
  $('#loginForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget));
    try { await api('/api/login', { method: 'POST', body: JSON.stringify(body) }); location.href = '/dashboard'; }
    catch (err) { toast(err.message, true); }
  });
}

function initSetup() {
  $('#setupForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget));
    try { await api('/api/setup', { method: 'POST', body: JSON.stringify(body) }); location.href = '/dashboard'; }
    catch (err) { toast(err.message, true); }
  });
}

$$('[data-logout]').forEach(btn => btn.addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' }).catch(() => null);
  location.href = '/login';
}));

async function loadDashboard() {
  try {
    const [stats, info, procs] = await Promise.all([api('/api/stats'), api('/api/system'), api('/api/processes?limit=12')]);
    pct('cpu', stats.cpu.percent); pct('ram', stats.memory.percent); pct('disk', stats.disk.percent);
    setText('#ramDetail', `Memory ${stats.memory.used_human} / ${stats.memory.total_human}`);
    setText('#diskDetail', `Disk ${stats.disk.used_human} / ${stats.disk.total_human}`);
    setText('#netDetail', `Network RX/TX ${stats.network.recv_human} / ${stats.network.sent_human}`);
    const systemInfo = $('#systemInfo');
    if (systemInfo) systemInfo.innerHTML = Object.entries(info).map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v || '-')}</dd>`).join('');
    const rows = $('#processRows');
    if (rows) rows.innerHTML = procs.processes.map(p => `<tr><td>${esc(p.pid)}</td><td>${esc(p.name)}</td><td>${esc(p.cpu)}%</td><td>${esc(p.memory)}%</td></tr>`).join('');
    updateDashboardVisuals(stats, procs);
  } catch (err) { toast(err.message, true); }
}
function initDashboard() { loadDashboard(); setInterval(loadDashboard, 4000); }

let currentFilePath = reverseConfig.fileRoot || '/';
let editorPath = null;
async function loadFiles(path = reverseConfig.fileRoot || '/') {
  try {
    const data = await api(`/api/files/list?path=${encodeURIComponent(path)}`);
    currentFilePath = data.current_path;
    if ($('#pathInput')) $('#pathInput').value = currentFilePath;
    renderFileBreadcrumb(currentFilePath);
    setText('#fileCountSummary', `${data.total} items · page ${data.page}`);
    if ($('#upBtn')) $('#upBtn').onclick = () => data.parent && loadFiles(data.parent);
    const rows = $('#fileRows');
    if (rows) rows.innerHTML = data.items.map(item => `<tr>
      <td class="mono"><span class="file-icon ${item.is_dir ? 'dir' : 'file'}">${icon(item.is_dir ? 'folder' : 'description')}</span><a href="#" data-open="${encodeURIComponent(item.path)}" data-dir="${item.is_dir}">${esc(item.name)}</a></td>
      <td>${esc(item.size_human)}</td><td>${esc(item.mode)}</td>
      <td><button class="ghost" data-edit="${encodeURIComponent(item.path)}" ${item.is_dir ? 'disabled' : ''}>${icon(reverseConfig.filesWritable === false ? 'visibility' : 'edit')}${reverseConfig.filesWritable === false ? 'View' : 'Edit'}</button> ${item.is_dir ? '' : `<a class="ghost download-link" href="/api/files/download?path=${encodeURIComponent(item.path)}">${icon('download')}Download</a>`} ${reverseConfig.filesWritable === false ? '' : `<button class="ghost danger" data-delete="${encodeURIComponent(item.path)}">${icon('delete')}Delete</button>`}</td>
    </tr>`).join('');
    $$('[data-open]').forEach(a => a.onclick = (e) => { e.preventDefault(); if (a.dataset.dir === 'true') loadFiles(decodeURIComponent(a.dataset.open)); else openEditor(decodeURIComponent(a.dataset.open)); });
    $$('[data-edit]').forEach(b => b.onclick = () => openEditor(decodeURIComponent(b.dataset.edit)));
    $$('[data-delete]').forEach(b => b.onclick = () => deletePath(decodeURIComponent(b.dataset.delete)));
  } catch (err) { toast(err.message, true); }
}
async function openEditor(path) {
  try { const data = await api(`/api/files/content?path=${encodeURIComponent(path)}`); editorPath = path; setText('#editorTitle', path); $('#editorContent').value = data.content; $('#editor').showModal(); }
  catch (err) { toast(err.message, true); }
}
async function deletePath(path) { const expected = basename(path); const typed = prompt(`Ketik nama ini untuk hapus permanen:\n${expected}`); if (typed !== expected) return; try { await api('/api/files/action', {method:'POST', body:JSON.stringify({action:'delete', path})}); toast('Deleted'); loadFiles(currentFilePath); } catch(err){toast(err.message,true);} }
async function newFolder(){ const name=prompt('Folder path', `${currentFilePath}/new-folder`); if(!name)return; await api('/api/files/action',{method:'POST',body:JSON.stringify({action:'mkdir',path:name})}).then(()=>loadFiles(currentFilePath)).catch(e=>toast(e.message,true)); }
async function newFile(){ const name=prompt('File path', `${currentFilePath}/new-file.txt`); if(!name)return; await api('/api/files/action',{method:'POST',body:JSON.stringify({action:'touch',path:name})}).then(()=>loadFiles(currentFilePath)).catch(e=>toast(e.message,true)); }
function initFiles(){ loadFiles(reverseConfig.fileRoot || '/'); $('#saveEditor')?.addEventListener('click', async (e)=>{ e.preventDefault(); try{ await api('/api/files/content',{method:'POST',body:JSON.stringify({path:editorPath,content:$('#editorContent').value})}); $('#editor').close(); toast('Saved'); }catch(err){toast(err.message,true);} }); $('#uploadForm')?.addEventListener('submit', uploadFiles); }

async function uploadFiles(e){
  e.preventDefault();
  const form = e.currentTarget;
  const fd = new FormData(form);
  fd.set('path', currentFilePath);
  fd.set('overwrite', form.querySelector('[name=overwrite]')?.checked ? '1' : '0');
  try {
    const res = await fetch('/api/files/upload', {method:'POST', body:fd});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    toast(`Uploaded ${data.uploaded?.length || 0} file(s)`);
    $('#uploadDialog')?.close();
    form.reset();
    loadFiles(currentFilePath);
  } catch(err) { toast(err.message, true); }
}

async function loadDocker() {
  try {
    const status = await api('/api/docker/status');
    setText('#dockerStatus', status.available ? 'Docker connected' : 'Docker unavailable');
    setText('#dockerSummaryStatus', status.available ? 'Connected' : 'Unavailable');
    if (!status.available) {
      setText('#dockerContainerCount', '0');
      const grid = $('#dockerCardGrid');
      if (grid) grid.innerHTML = `<article class="docker-mini-card empty"><span class="material-symbols-outlined">cloud_off</span><strong>Docker unavailable</strong><small>${esc(status.reason || 'Docker unavailable')}</small><code>${esc(status.fix || 'Check Docker daemon and permissions')}</code></article>`;
      return;
    }
    const [data, imageData, networkData] = await Promise.all([
      api('/api/docker/containers'),
      api('/api/docker/images').catch(() => ({images: []})),
      api('/api/docker/networks').catch(() => ({networks: []})),
    ]);
    setText('#dockerContainerCount', String(data.containers.length));
    setText('#dockerImageCount', String(imageData.images.length));
    const grid = $('#dockerCardGrid');
    if (grid) {
      grid.innerHTML = data.containers.length ? data.containers.slice(0, 6).map((c, index) => {
        const seed = c.status === 'running' ? 62 + (index * 7) : 18 + (index * 3);
        return `<article class="docker-mini-card ${statusClass(c.status)}">
          <div class="docker-mini-head"><span class="material-symbols-outlined">deployed_code</span><span class="status-pill ${statusClass(c.status)}">${esc(c.status)}</span></div>
          <strong>${esc(c.name)}</strong>
          <small class="mono">${esc(c.image)}</small>
          <div class="mini-spark" aria-hidden="true">${miniBars(seed)}</div>
          <div class="docker-mini-foot"><span>${esc(c.ports?.length || 0)} ports</span><button class="ghost" onclick="showLogs('${esc(c.id)}')">${icon('article')}Logs</button></div>
        </article>`;
      }).join('') : `<article class="docker-mini-card empty"><span class="material-symbols-outlined">inventory_2</span><strong>No containers</strong><small>Docker is connected but no containers were returned.</small></article>`;
    }
    $('#dockerRows').innerHTML = data.containers.map(c => `<tr><td>${esc(c.name)}</td><td class="mono">${esc(c.image)}</td><td><span class="status-pill ${statusClass(c.status)}">${esc(c.status)}</span></td><td>${c.ports.map(p=>`${esc(p.host_port)}-&gt;${esc(p.container)}`).join('<br>') || '-'}</td><td><button class="ghost" onclick="dockerAction('${esc(c.id)}','restart')">${icon('restart_alt')}Restart</button><button class="ghost" onclick="dockerAction('${esc(c.id)}','stop')">${icon('stop_circle')}Stop</button><button class="ghost" onclick="dockerAction('${esc(c.id)}','start')">${icon('play_circle')}Start</button><button class="ghost" onclick="showLogs('${esc(c.id)}')">${icon('article')}Logs</button><button class="ghost danger" onclick="removeContainer('${esc(c.id)}','${esc(c.name)}')">${icon('delete')}Delete</button></td></tr>`).join('');
    const imageRows = $('#dockerImageRows');
    if (imageRows) imageRows.innerHTML = imageData.images.length ? imageData.images.map(img => `<tr><td class="mono">${esc((img.tags || []).join(', '))}</td><td class="mono">${esc(img.id)}</td><td>${esc(img.size_human)}</td><td>${esc(img.created || '-')}</td><td><button class="ghost danger" onclick="removeDockerImage('${esc((img.tags || [img.id])[0])}')">${icon('delete')}Delete</button></td></tr>`).join('') : `<tr><td colspan="5">No local images found.</td></tr>`;
    const networkRows = $('#dockerNetworkRows');
    if (networkRows) networkRows.innerHTML = networkData.networks.length ? networkData.networks.map(n => `<tr><td>${esc(n.name)}</td><td class="mono">${esc(n.id)}</td><td>${esc(n.driver || '-')}</td><td>${esc(n.scope || '-')}</td><td>${esc(n.containers)}</td></tr>`).join('') : `<tr><td colspan="5">No Docker networks found.</td></tr>`;
  } catch (err) { toast(err.message, true); }
}
async function dockerAction(id, action){ try{ await api(`/api/docker/containers/${id}/action`,{method:'POST',body:JSON.stringify({action})}); toast(`${action} sent`); loadDocker(); }catch(err){toast(err.message,true);} }
async function showLogs(id){ try{ const data=await api(`/api/docker/containers/${id}/logs?lines=300`); $('#logContent').textContent=data.logs; $('#logDialog').showModal(); }catch(err){toast(err.message,true);} }
async function removeContainer(id, name){ const typed = prompt(`Ketik nama container untuk hapus permanen:\n${name}`); if (typed !== name) return; await dockerAction(id, 'remove'); }
async function removeDockerImage(image){ const typed = prompt(`Ketik image untuk hapus:\n${image}`); if (typed !== image) return; try{ await api('/api/docker/images/remove',{method:'POST',body:JSON.stringify({image, force:true})}); toast('Image removed'); loadDocker(); }catch(err){toast(err.message,true);} }
async function pullDockerImage(e){ e.preventDefault(); const image = new FormData(e.currentTarget).get('image'); try{ await api('/api/docker/images/pull',{method:'POST',body:JSON.stringify({image})}); toast(`Pulled ${image}`); e.currentTarget.reset(); loadDocker(); }catch(err){toast(err.message,true);} }
async function createDockerContainer(e){ e.preventDefault(); const body = Object.fromEntries(new FormData(e.currentTarget)); try{ const result = await api('/api/docker/containers',{method:'POST',body:JSON.stringify(body)}); toast(`Container created: ${result.name}`); $('#dockerCreateDialog')?.close(); e.currentTarget.reset(); loadDocker(); }catch(err){toast(err.message,true);} }
function initDocker(){ loadDocker(); $('#dockerPullForm')?.addEventListener('submit', pullDockerImage); $('#dockerCreateForm')?.addEventListener('submit', createDockerContainer); }

async function loadSettings(){
  try{ const s=await api('/api/settings'); $('[name=server_name]').value=s.general.server_name; $('[name=timezone]').value=s.general.timezone; $('[name=stats_interval_ms]').value=s.monitoring.stats_interval_ms; setText('#settingsInterval', `${s.monitoring.stats_interval_ms}ms`); const users=await api('/api/users').catch(()=>({users:[]})); setText('#settingsUserCount', String(users.users.length)); $('#userList').innerHTML=users.users.map(u=>`<div class="list-item"><span>${icon('person')}${esc(u.username)}</span><strong>${esc(u.role)}</strong></div>`).join(''); }catch(err){toast(err.message,true);}
}
function initSettings(){ loadSettings(); $('#settingsForm')?.addEventListener('submit',async e=>{e.preventDefault(); const f=new FormData(e.currentTarget); const body={general:{server_name:f.get('server_name'),timezone:f.get('timezone')},monitoring:{stats_interval_ms:Number(f.get('stats_interval_ms'))}}; try{await api('/api/settings',{method:'POST',body:JSON.stringify(body)}); toast('Settings saved'); loadSettings();}catch(err){toast(err.message,true);}}); $('#userForm')?.addEventListener('submit',async e=>{e.preventDefault(); const body=Object.fromEntries(new FormData(e.currentTarget)); try{await api('/api/users',{method:'POST',body:JSON.stringify(body)}); toast('User added'); e.currentTarget.reset(); loadSettings();}catch(err){toast(err.message,true);}}); }

async function loadAudit(){ try{ const data=await api('/api/audit?lines=300'); setText('#auditLineCount', String(data.logs.length)); $('#auditLogs').textContent=data.logs.join('') || 'No audit logs yet.'; }catch(err){toast(err.message,true);} }
function initAudit(){ loadAudit(); }

async function loadNetwork(){
  try {
    const data = await api('/api/network');
    setText('#networkTotalRx', data.total.recv_human);
    setText('#networkTotalTx', data.total.sent_human);
    setText('#networkIfaceCount', String(data.interfaces.length));
    const cards = $('#networkCards');
    if (cards) cards.innerHTML = data.interfaces.slice(0, 6).map(iface => `<article class="phase-card ${iface.is_up ? 'online' : 'offline'}">
      <div class="phase-card-head"><span class="material-symbols-outlined">${iface.is_up ? 'settings_ethernet' : 'portable_wifi_off'}</span><span class="status-pill ${iface.is_up ? 'success' : 'error'}">${iface.is_up ? 'UP' : 'DOWN'}</span></div>
      <strong>${esc(iface.name)}</strong><small class="mono">${esc((iface.addresses || []).join(', ') || 'No address')}</small>
      <div class="phase-metrics"><span>RX <b>${esc(iface.recv_human)}</b></span><span>TX <b>${esc(iface.sent_human)}</b></span></div>
    </article>`).join('');
    $('#networkRows').innerHTML = data.interfaces.map(iface => `<tr><td class="mono">${esc(iface.name)}</td><td><span class="status-pill ${iface.is_up ? 'success' : 'error'}">${iface.is_up ? 'UP' : 'DOWN'}</span></td><td class="mono">${esc((iface.addresses || []).join(', ') || '-')}</td><td>${esc(iface.recv_human)}</td><td>${esc(iface.sent_human)}</td><td>${esc(iface.errors)} / ${esc(iface.drops)}</td></tr>`).join('');
  } catch(err) { toast(err.message, true); }
}
function initNetwork(){ loadNetwork(); setInterval(loadNetwork, 6000); $('#openPortForm')?.addEventListener('submit', e=>{ e.preventDefault(); const f=new FormData(e.currentTarget); openFirewallPort(f.get('port'), f.get('protocol')); }); }

async function openFirewallPort(port, protocol){
  const out = $('#firewallOutput');
  if (out) out.textContent = `Opening ${port}/${protocol}...`;
  try {
    const result = await api('/api/network/open-port',{method:'POST',body:JSON.stringify({port:Number(port), protocol})});
    if (out) out.textContent = `${result.tool || 'firewall'}\n${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}\n[exit ${result.code}]`;
    toast(result.success ? `Port ${port}/${protocol} opened` : 'Open port failed', !result.success);
  } catch(err) { if (out) out.textContent = err.message; toast(err.message,true); }
}

async function loadStorage(){
  try {
    const data = await api('/api/storage');
    const root = data.root;
    setText('#storageRootUsed', root.used_human);
    setText('#storageRootFree', root.free_human);
    setText('#storagePartitionCount', String(data.partition_count));
    setText('#storageRootPercent', `${Math.round(root.percent)}%`);
    setText('#storageRootDetail', `${root.used_human} used of ${root.total_human}. ${root.free_human} free.`);
    $('#storageRootRing')?.style.setProperty('--score', Math.round(root.percent));
    setWidth('#storageRootBar', root.percent);
    $('#storageRows').innerHTML = data.partitions.map(part => `<tr><td class="mono">${esc(part.device || '-')}</td><td class="mono">${esc(part.mountpoint)}</td><td>${esc(part.fstype || '-')}</td><td>${esc(part.used_human)}</td><td>${esc(part.total_human)}</td><td><span class="table-meter"><i style="width:${Math.min(100, Math.max(0, part.percent))}%"></i></span>${esc(part.percent)}%</td></tr>`).join('');
  } catch(err) { toast(err.message, true); }
}
function initStorage(){ loadStorage(); setInterval(loadStorage, 8000); }

async function loadSecurity(){
  try {
    const [summary, audit] = await Promise.all([api('/api/security/summary'), api('/api/audit?lines=80').catch(()=>({logs:[]}))]);
    setText('#securityUserTotal', String(summary.users_total));
    setText('#securityTimeout', durationHuman(summary.session_timeout));
    setText('#securityLocked', String(summary.locked_sources));
    $('#securityPosture').innerHTML = `<div class="posture-row"><span>Setup complete</span><strong>${summary.setup_complete ? 'Yes' : 'No'}</strong></div><div class="posture-row"><span>Max login attempts</span><strong>${summary.max_login_attempts}</strong></div><div class="posture-row"><span>Lockout duration</span><strong>${durationHuman(summary.lockout_seconds)}</strong></div><div class="posture-row"><span>Attempt records</span><strong>${summary.active_attempt_records}</strong></div>`;
    const roles = summary.roles || {};
    $('#roleCards').innerHTML = ['owner','admin','operator','readonly'].map(role => `<article class="role-card"><span class="material-symbols-outlined">${role === 'owner' ? 'workspace_premium' : role === 'admin' ? 'admin_panel_settings' : role === 'operator' ? 'engineering' : 'visibility'}</span><strong>${esc(roles[role] || 0)}</strong><small>${esc(role)}</small></article>`).join('');
    $('#securityAuditLogs').textContent = audit.logs.join('') || 'No audit logs yet.';
  } catch(err) { toast(err.message, true); }
}
function initSecurity(){ loadSecurity(); }

async function loadDatabase(){
  try {
    const data = await api('/api/database/status');
    setText('#databaseAvailable', data.available ? 'Detected' : 'Not found');
    setText('#databaseHostControl', data.host_control ? 'Enabled' : 'Disabled');
    setText('#databaseNotice', data.enabled ? 'Database module enabled' : 'Database module disabled');
    const rows = $('#databaseRows');
    if (rows) rows.innerHTML = (data.services || []).map(db => `<tr><td><strong>${esc(db.label)}</strong><br><small class="mono">${esc(db.binary || 'not installed')}</small></td><td><span class="status-pill ${db.installed ? 'success' : 'warning'}">${db.installed ? 'yes' : 'no'}</span></td><td>${esc(db.service_state || '-')}</td><td class="mono">${esc(db.version || '-')}</td><td><code>${esc(db.install_hint || '-')}</code></td><td>${['mysql','mariadb','postgresql'].includes(db.key) ? `<button class="ghost" onclick="databaseAction('${esc(db.key)}','restart')">${icon('restart_alt')}Restart</button><button class="ghost" onclick="databaseAction('${esc(db.key)}','start')">${icon('play_circle')}Start</button><button class="ghost" onclick="databaseAction('${esc(db.key)}','stop')">${icon('stop_circle')}Stop</button>` : '<span class="notice">embedded</span>'}</td></tr>`).join('');
    const notes = $('#databaseNotes');
    if (notes && data.notes?.length) notes.innerHTML = `<span class="material-symbols-outlined">info</span><div><strong>Database module notes</strong>${data.notes.map(note => `<small>${esc(note)}</small>`).join('')}<code>Next: create database/user, SQL import/export, containerized DB deploy.</code></div>`;
  } catch(err) { toast(err.message, true); }
}

function databaseCredentials(){
  const form = $('#databaseConnectionForm');
  return form ? Object.fromEntries(new FormData(form)) : {engine:'mysql', username:'root'};
}

async function databaseList(e){
  e?.preventDefault();
  const out = $('#databaseOutput');
  if (out) out.textContent = 'Loading databases...';
  try {
    const data = await api('/api/database/list', {method:'POST', body:JSON.stringify(databaseCredentials())});
    if (out) out.textContent = `${data.stdout || ''}${data.stderr ? `\n${data.stderr}` : ''}\n[exit ${data.code}]`;
    const list = $('#databaseList');
    if (list) list.innerHTML = data.databases.length ? data.databases.map(name => `<div class="list-item"><span>${icon('database')}${esc(name)}</span><strong><button class="ghost" onclick="exportDatabase('${esc(name)}')">${icon('download')}Export</button></strong></div>`).join('') : '<div class="list-item"><span>No database returned.</span><strong>-</strong></div>';
  } catch(err) { if (out) out.textContent = err.message; toast(err.message, true); }
}

async function createDatabase(e){
  e.preventDefault();
  const body = {...databaseCredentials(), ...Object.fromEntries(new FormData(e.currentTarget))};
  try { const result = await api('/api/database/create', {method:'POST', body:JSON.stringify(body)}); toast(result.success ? `Database created: ${result.database}` : 'Create database failed', !result.success); databaseList(); }
  catch(err){ toast(err.message, true); }
}

async function createDatabaseUser(e){
  e.preventDefault();
  const body = {...databaseCredentials(), ...Object.fromEntries(new FormData(e.currentTarget))};
  try { const result = await api('/api/database/user', {method:'POST', body:JSON.stringify(body)}); toast(result.success ? `User created: ${result.username}` : 'Create user failed', !result.success); }
  catch(err){ toast(err.message, true); }
}

async function importDatabase(e){
  e.preventDefault();
  const fd = new FormData(e.currentTarget);
  Object.entries(databaseCredentials()).forEach(([k,v]) => fd.set(k, v));
  const out = $('#databaseOutput');
  if (out) out.textContent = 'Importing SQL...';
  try {
    const res = await fetch('/api/database/import', {method:'POST', body:fd});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    if (out) out.textContent = `${data.stdout || ''}${data.stderr ? `\n${data.stderr}` : ''}\n[exit ${data.code}]`;
    toast(data.success ? 'SQL imported' : 'Import failed', !data.success);
  } catch(err) { if (out) out.textContent = err.message; toast(err.message, true); }
}

async function exportDatabase(name){
  const body = {...databaseCredentials(), database:name};
  try {
    const res = await fetch('/api/database/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (!res.ok) { const data = await res.json().catch(() => ({})); throw new Error(data.error || `HTTP ${res.status}`); }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.sql`;
    a.click();
    URL.revokeObjectURL(url);
    toast(`Exported ${name}`);
  } catch(err) { toast(err.message, true); }
}

async function exportDatabaseFromForm(e){ e.preventDefault(); const name = new FormData(e.currentTarget).get('database'); if (name) exportDatabase(name); }

async function databaseAction(service, action){
  try {
    const result = await api('/api/database/action', {method:'POST', body:JSON.stringify({service, action})});
    toast(result.success ? `${service} ${action} sent` : (result.stderr || 'Database action failed'), !result.success);
    loadDatabase();
  } catch(err) { toast(err.message, true); }
}

function initDatabase(){ loadDatabase(); $('#databaseConnectionForm')?.addEventListener('submit', databaseList); $('#databaseCreateForm')?.addEventListener('submit', createDatabase); $('#databaseUserForm')?.addEventListener('submit', createDatabaseUser); $('#databaseImportForm')?.addEventListener('submit', importDatabase); $('#databaseExportForm')?.addEventListener('submit', exportDatabaseFromForm); }

function installHintHtml(status, label) {
  if (status.installed) return `<div class="empty-inline"><span class="material-symbols-outlined">check_circle</span><strong>${esc(label)} detected</strong><small>${esc(status.pm2_path || status.nginx_path || '')}</small></div>`;
  return `<div class="install-copy"><span class="material-symbols-outlined">download</span><div><strong>${esc(label)} not installed</strong><small>Linux install helper is available. Run this on the server during deployment:</small><code>${esc(status.install_command || 'sudo bash scripts/install-runtime-tools.sh')}</code></div></div>`;
}

async function loadPM2(){
  try {
    const [status, data] = await Promise.all([api('/api/pm2/status'), api('/api/pm2/processes').catch(()=>({processes:[]}))]);
    setText('#pm2Installed', status.installed ? 'Yes' : 'No');
    setText('#nodeInstalled', status.node_path ? 'Yes' : 'No');
    setText('#pm2ProcessCount', String(data.processes.length));
    $('#pm2InstallHint').innerHTML = installHintHtml(status, 'PM2');
    $('#pm2Rows').innerHTML = data.processes.length ? data.processes.map(p => `<tr><td>${esc(p.name)}</td><td>${esc(p.pm_id)}</td><td><span class="status-pill ${statusClass(p.status)}">${esc(p.status)}</span></td><td>${esc(p.cpu)}%</td><td>${esc(p.memory_human)}</td><td>${esc(p.restart_time)}</td><td><button class="ghost" onclick="pm2Action('${esc(p.name)}','restart')">${icon('restart_alt')}Restart</button><button class="ghost" onclick="pm2Action('${esc(p.name)}','reload')">${icon('sync')}Reload</button></td></tr>`).join('') : `<tr><td colspan="7">No PM2 processes found.</td></tr>`;
  } catch(err) { toast(err.message, true); }
}
async function pm2Action(name, action){ try{ const result = await api('/api/pm2/action',{method:'POST',body:JSON.stringify({name, action})}); toast(result.success ? `PM2 ${action} sent` : (result.stderr || 'PM2 action failed'), !result.success); loadPM2(); }catch(err){toast(err.message,true);} }
function initPM2(){ loadPM2(); setInterval(loadPM2, 8000); }

async function installPM2(){
  const out = $('#pm2InstallOutput');
  if (out) out.textContent = 'Installing PM2...';
  try { const result = await api('/api/pm2/install',{method:'POST',body:JSON.stringify({})}); if(out) out.textContent = `${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}\n[exit ${result.code}]`; toast(result.success ? 'PM2 install completed' : 'PM2 install failed', !result.success); loadPM2(); }
  catch(err){ if(out) out.textContent = err.message; toast(err.message,true); }
}

async function loadNginx(){
  try {
    const [status, test, siteData] = await Promise.all([api('/api/nginx/status'), api('/api/nginx/test').catch(()=>({success:false, stderr:'Unable to test config'})), api('/api/nginx/sites').catch(()=>({sites:[]}))]);
    setText('#nginxInstalled', status.installed ? 'Yes' : 'No');
    setText('#nginxState', status.service_state || 'unknown');
    setText('#nginxTestState', test.success ? 'Valid' : 'Check');
    $('#nginxInstallHint').innerHTML = installHintHtml(status, 'Nginx');
    $('#nginxTestOutput').textContent = [status.version, test.stdout, test.stderr].filter(Boolean).join('\n') || 'No output.';
    $('#nginxConfigPaths').innerHTML = (status.config_paths || []).map(item => `<div class="list-item"><span>${icon(item.type === 'dir' ? 'folder' : 'description')}${esc(item.path)}</span><strong>${item.exists ? 'exists' : 'missing'}</strong></div>`).join('');
    const rows = $('#nginxSiteRows');
    if (rows) rows.innerHTML = siteData.sites.length ? siteData.sites.map(site => `<tr><td class="mono">${esc(site.name)}</td><td>${esc((site.server_names || []).join(', ') || '-')}</td><td class="mono">${esc((site.proxy_passes || []).join(', ') || '-')}</td><td><span class="status-pill ${site.ssl ? 'success' : 'warning'}">${site.ssl ? 'yes' : 'no'}</span></td><td><span class="status-pill ${site.enabled ? 'success' : 'warning'}">${site.enabled ? 'enabled' : 'disabled'}</span></td><td><button class="ghost" onclick="editNginxSite('${esc(site.name)}')">${icon('edit')}Edit</button><button class="ghost" onclick="nginxSiteAction('${esc(site.name)}','${site.enabled ? 'disable' : 'enable'}')">${icon(site.enabled ? 'toggle_off' : 'toggle_on')}${site.enabled ? 'Disable' : 'Enable'}</button><button class="ghost" onclick="issueNginxSsl('${esc((site.server_names || [site.name])[0])}')">${icon('lock')}SSL</button><button class="ghost danger" onclick="deleteNginxSite('${esc(site.name)}')">${icon('delete')}Delete</button></td></tr>`).join('') : '<tr><td colspan="6">No sites found.</td></tr>';
  } catch(err) { toast(err.message, true); }
}
async function nginxAction(action){ try{ const result = await api('/api/nginx/action',{method:'POST',body:JSON.stringify({action})}); toast(result.success ? `Nginx ${action} sent` : (result.stderr || 'Nginx action failed'), !result.success); loadNginx(); }catch(err){toast(err.message,true);} }
function initNginx(){ loadNginx(); $('#nginxSiteForm')?.addEventListener('submit', createNginxSite); $('#nginxEditForm')?.addEventListener('submit', saveNginxSite); $('#nginxSslForm')?.addEventListener('submit', submitNginxSsl); }

async function createNginxSite(e){
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.currentTarget));
  body.ssl_redirect = Boolean(body.ssl_redirect);
  try { const result = await api('/api/nginx/sites/proxy',{method:'POST',body:JSON.stringify(body)}); toast(`Site created: ${result.name}`); $('#nginxSiteDialog')?.close(); e.currentTarget.reset(); loadNginx(); }
  catch(err){ toast(err.message,true); }
}

async function editNginxSite(name){
  try { const data = await api(`/api/nginx/sites/${encodeURIComponent(name)}`); $('#nginxEditTitle').textContent = `Edit ${data.name}`; $('#nginxEditForm [name=name]').value = data.name; $('#nginxEditContent').value = data.content; $('#nginxEditDialog')?.showModal(); }
  catch(err){ toast(err.message,true); }
}

async function saveNginxSite(e){
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.currentTarget));
  body.enable = true;
  try { await api('/api/nginx/sites',{method:'POST',body:JSON.stringify(body)}); toast('Site saved and config valid'); $('#nginxEditDialog')?.close(); loadNginx(); }
  catch(err){ toast(err.message,true); }
}

async function nginxSiteAction(name, action){ try{ await api(`/api/nginx/sites/${encodeURIComponent(name)}/action`,{method:'POST',body:JSON.stringify({action})}); toast(`${name} ${action}`); loadNginx(); }catch(err){toast(err.message,true);} }
async function deleteNginxSite(name){ const typed = prompt(`Ketik nama site untuk delete:\n${name}`); if (typed !== name) return; nginxSiteAction(name, 'delete'); }
async function issueNginxSsl(domain){ if (!domain) return; const ok = confirm(`Issue SSL untuk ${domain}? Domain harus sudah mengarah ke server ini.`); if (!ok) return; try{ const result = await api('/api/nginx/ssl',{method:'POST',body:JSON.stringify({domain})}); toast(result.success ? `SSL issued for ${domain}` : (result.stderr || 'SSL failed'), !result.success); loadNginx(); }catch(err){toast(err.message,true);} }
async function submitNginxSsl(e){ e.preventDefault(); const domain = new FormData(e.currentTarget).get('domain'); await issueNginxSsl(domain); $('#nginxSslDialog')?.close(); }

async function installNginx(){
  const out = $('#nginxInstallOutput');
  if (out) out.textContent = 'Installing Nginx...';
  try { const result = await api('/api/nginx/install',{method:'POST',body:JSON.stringify({})}); if(out) out.textContent = `${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}\n[exit ${result.code}]`; toast(result.success ? 'Nginx install completed' : 'Nginx install failed', !result.success); loadNginx(); }
  catch(err){ if(out) out.textContent = err.message; toast(err.message,true); }
}

function dateHuman(ts){ try { return new Date(Number(ts) * 1000).toLocaleString(); } catch { return '-'; } }
async function loadBackup(){
  try {
    const [status, data] = await Promise.all([api('/api/backup/status'), api('/api/backup/list')]);
    setText('#backupCount', String(status.count));
    setText('#backupLatest', status.latest ? status.latest.name : 'None');
    setText('#backupDir', status.backup_dir || '-');
    const gd = status.gdrive || {};
    $('#gdriveStatus').innerHTML = `<div class="install-copy"><span class="material-symbols-outlined">cloud_sync</span><div><strong>${gd.configured ? 'Google Drive configured' : 'Google Drive not configured'}</strong><small>rclone: ${esc(gd.rclone || 'not installed')} · remote: ${esc(gd.remote || 'set GDRIVE_REMOTE')}</small><code>ENABLE_GDRIVE_BACKUP=1 GDRIVE_REMOTE=gdrive:reverse-dashboard-backups</code></div></div>`;
    $('#backupRows').innerHTML = data.backups.length ? data.backups.map(b => `<tr><td class="mono">${esc(b.name)}</td><td>${esc(b.size_human)}</td><td>${esc(dateHuman(b.created))}</td><td><a class="ghost download-link" href="/api/backup/download/${encodeURIComponent(b.name)}">${icon('download')}Download</a> <button class="ghost" onclick="uploadBackupGDrive('${esc(b.name)}')">${icon('cloud_upload')}GDrive</button></td></tr>`).join('') : `<tr><td colspan="4">No backups yet.</td></tr>`;
  } catch(err) { toast(err.message, true); }
}
async function createBackup(){ try{ const result = await api('/api/backup/create',{method:'POST',body:JSON.stringify({})}); toast(`Backup created: ${result.name}`); loadBackup(); }catch(err){toast(err.message,true);} }
function initBackup(){ loadBackup(); }

async function uploadBackupGDrive(name){
  const out = $('#gdriveOutput');
  if (out) out.textContent = `Uploading ${name} to Google Drive...`;
  try { const result = await api(`/api/backup/gdrive/${encodeURIComponent(name)}`, {method:'POST', body:JSON.stringify({})}); if(out) out.textContent = `${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}\nremote: ${result.remote || '-'}\n[exit ${result.code}]`; toast(result.success ? 'Uploaded to Google Drive' : 'Google Drive upload failed', !result.success); }
  catch(err){ if(out) out.textContent = err.message; toast(err.message,true); }
}

async function loadTerminalStatus(){
  try {
    const status = await api('/api/terminal/status');
    setText('#terminalAvailable', status.available ? 'Enabled' : 'Disabled');
    setText('#terminalCwd', status.cwd || '-');
    setText('#terminalGuard', status.mode === 'full_shell' ? 'Full shell' : `${(status.allowed_commands || []).length} commands`);
    setText('#terminalSessionTitle', status.available ? 'root@linux-server' : 'guarded@disabled');
    const pill = $('#terminalStatusPill');
    if (pill) {
      pill.textContent = status.available ? 'enabled' : 'disabled';
      pill.className = `status-chip ${status.available ? 'success' : 'warning'}`;
    }
    const output = $('#terminalOutput');
    if (output && output.textContent.includes('Connecting to guarded terminal')) {
      output.textContent = status.available
        ? `Terminal enabled in full shell mode.\n\nType a command or click a quick command above. Commands are audited.`
        : `Terminal disabled.\n\n${status.warning}\n\nEnable on Linux server with:\nENABLE_TERMINAL=1`;
    }
  } catch(err) { toast(err.message, true); }
}

let terminalSocket = null;
let terminalLive = false;

function appendTerminal(data){
  const output = $('#terminalOutput');
  if (!output) return;
  output.textContent += data;
  output.scrollTop = output.scrollHeight;
}

function terminalWrite(data){
  if (terminalSocket && terminalLive) {
    terminalSocket.emit('terminal_input', {data});
    return true;
  }
  return false;
}

function startInteractiveTerminal(){
  if (typeof io !== 'function') return;
  const output = $('#terminalOutput');
  if (output) output.textContent = 'Opening interactive PTY session...\r\n';
  terminalSocket = io('/terminal', {transports: ['websocket', 'polling']});
  terminalSocket.on('connect', () => {
    terminalLive = true;
    terminalSocket.emit('terminal_start', {rows: 34, cols: 120});
    setText('#terminalSessionTitle', 'root@interactive-pty');
    const pill = $('#terminalStatusPill');
    if (pill) { pill.textContent = 'live'; pill.className = 'status-chip success'; }
  });
  terminalSocket.on('terminal_output', payload => appendTerminal(payload.data || ''));
  terminalSocket.on('terminal_status', payload => {
    terminalLive = Boolean(payload.connected);
    const pill = $('#terminalStatusPill');
    if (pill) { pill.textContent = terminalLive ? 'live' : 'closed'; pill.className = `status-chip ${terminalLive ? 'success' : 'warning'}`; }
  });
  terminalSocket.on('connect_error', err => {
    terminalLive = false;
    appendTerminal(`\r\nSocket error: ${err.message || err}\r\n`);
  });
  terminalSocket.on('disconnect', () => {
    terminalLive = false;
    appendTerminal('\r\n[terminal disconnected]\r\n');
  });
}

function restartTerminalSession(){
  if (terminalSocket) {
    terminalSocket.emit('terminal_stop');
    terminalSocket.disconnect();
  }
  terminalSocket = null;
  terminalLive = false;
  startInteractiveTerminal();
}

async function runTerminalCommand(command){
  if (terminalWrite(`${command}\n`)) return;
  const output = $('#terminalOutput');
  if (output) output.textContent = `$ ${command}\nRunning...`;
  try {
    const result = await api('/api/terminal/run', {method:'POST', body:JSON.stringify({command, timeout:20})});
    if (output) output.textContent = `$ ${result.command}\n\n${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}\n\n[exit ${result.code}]`;
  } catch(err) {
    if (output) output.textContent = `$ ${command}\n\n${err.message}`;
    toast(err.message, true);
  }
}

function initTerminal(){
  loadTerminalStatus();
  startInteractiveTerminal();
  $$('#terminalForm [data-command], [data-command]').forEach(btn => {
    btn.addEventListener('click', () => {
      const command = btn.dataset.command || '';
      const input = $('#terminalCommand');
      if (input) input.value = command;
      if (!$('#terminalReadOnly')?.checked) runTerminalCommand(command);
    });
  });
  $('#terminalFontSize')?.addEventListener('change', e => {
    const output = $('#terminalOutput');
    if (output) output.style.fontSize = e.currentTarget.value;
  });
  $('#terminalReadOnly')?.addEventListener('change', e => {
    const input = $('#terminalCommand');
    if (input) input.disabled = e.currentTarget.checked;
  });
  $('#terminalForm')?.addEventListener('submit', e => {
    e.preventDefault();
    if ($('#terminalReadOnly')?.checked) return;
    const command = $('#terminalCommand')?.value.trim();
    if (command) runTerminalCommand(command);
    if ($('#terminalCommand')) $('#terminalCommand').value = '';
  });
  $('#terminalOutput')?.addEventListener('keydown', e => {
    if (!terminalLive || $('#terminalReadOnly')?.checked) return;
    if (e.key === 'Enter') { terminalWrite('\n'); e.preventDefault(); return; }
    if (e.key === 'Backspace') { terminalWrite('\x7f'); e.preventDefault(); return; }
    if (e.key === 'Tab') { terminalWrite('\t'); e.preventDefault(); return; }
    if (e.ctrlKey && e.key.length === 1) { terminalWrite(String.fromCharCode(e.key.toUpperCase().charCodeAt(0) - 64)); e.preventDefault(); return; }
    if (!e.ctrlKey && !e.metaKey && e.key.length === 1) { terminalWrite(e.key); e.preventDefault(); }
  });
  renderCustomTerminalCommands();
  $('#saveTerminalCommands')?.addEventListener('click', e => {
    e.preventDefault();
    localStorage.setItem('reverseTerminalCommands', $('#terminalCustomCommands')?.value || '');
    $('#terminalCommandsDialog')?.close();
    renderCustomTerminalCommands();
    toast('Custom commands saved');
  });
}

function openTerminalCommands(){
  const text = localStorage.getItem('reverseTerminalCommands') || '';
  const area = $('#terminalCustomCommands');
  if (area) area.value = text;
  $('#terminalCommandsDialog')?.showModal();
}

function renderCustomTerminalCommands(){
  const text = localStorage.getItem('reverseTerminalCommands') || '';
  const rows = text.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const idx = line.indexOf('=');
    if (idx < 1) return null;
    return { name: line.slice(0, idx).trim(), command: line.slice(idx + 1).trim() };
  }).filter(Boolean);
  let row = $('#terminalCustomRow');
  const panel = $('.quick-command-panel');
  if (!panel) return;
  if (!rows.length) { row?.remove(); return; }
  if (!row) {
    row = document.createElement('div');
    row.id = 'terminalCustomRow';
    row.className = 'quick-row';
    panel.appendChild(row);
  }
  row.innerHTML = `<span class="quick-label"><span class="material-symbols-outlined">star</span>Custom</span>` + rows.map(item => `<button data-command="${esc(item.command)}">${esc(item.name)}</button>`).join('');
  row.querySelectorAll('[data-command]').forEach(btn => btn.addEventListener('click', () => {
    const command = btn.dataset.command || '';
    const input = $('#terminalCommand');
    if (input) input.value = command;
    if (!$('#terminalReadOnly')?.checked) runTerminalCommand(command);
  }));
}
