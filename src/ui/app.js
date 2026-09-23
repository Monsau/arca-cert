// Portal-aware base paths. Priority: the composed document (portal
// /module/<key> page) injects window.__ARCA_MODULE_BASE__; standalone
// dev behind the Suite proxy uses the /m/<module-key>/ location prefix.
// The browser never carries a token — the portal attaches the SSO Bearer
// server-side on every proxied call.
const _injected = window.__ARCA_MODULE_BASE__;
const _pm = window.location.pathname.match(/^\/m\/([^/]+)\//);
const BASE = _injected || (_pm ? '/m/' + _pm[1] + '/' : '/');
const API = BASE + 'api/v1';

function $(sel) { return document.querySelector(sel); }

function statusClass(level) {
  return 'tag status-' + level.toLowerCase().replace(/_/g, '-');
}

// Security by design: the Suite portal attaches the SSO access token
// server-side on every proxied call, so the UI never sends credentials.
async function getJSON(path) {
  const res = await fetch(path);
  return res.ok ? res.json() : { error: res.statusText };
}

async function postJSON(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.ok ? res.json() : { error: await res.text() };
}

// Navigation
document.querySelectorAll('nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    $(`#${btn.dataset.view}-view`).classList.add('active');
    if (btn.dataset.view === 'packages') loadPackages();
    if (btn.dataset.view === 'readiness') loadReadiness();
    if (btn.dataset.view === 'soc') loadSOC();
  });
});

async function loadPackages() {
  const data = await getJSON(`${API}/packages`);
  const container = $('#package-list');
  container.innerHTML = '';
  (data.packages || []).forEach(pkg => {
    const d = pkg.dossier;
    const card = document.createElement('div');
    card.className = 'panel';
    card.innerHTML = `
      <h3>${d.target}</h3>
      <span class="${statusClass(d.status)}">${d.status}</span>
      <p>Level: <strong>${pkg.assessment.level}</strong></p>
      <p>Score: ${pkg.assessment.overall_score}</p>
      <p>Valid until: ${new Date(d.validUntil).toLocaleDateString()}</p>
      <button onclick="showPackage('${pkg.id}')">View Report</button>
    `;
    container.appendChild(card);
  });
}

window.showPackage = async function(id) {
  const pkg = await getJSON(`${API}/packages/${id}`);
  const detail = $('#package-detail');
  detail.classList.remove('hidden');
  detail.innerHTML = `
    <div class="panel">
      <h3>Report: ${pkg.dossier.target}</h3>
      <p>Status: <span class="${statusClass(pkg.dossier.status)}">${pkg.dossier.status}</span></p>
      <p>Seal: <code>${pkg.dossier.seal || 'n/a'}</code></p>
      <p>Seal valid: ${pkg.dossier.seal ? 'yes' : 'n/a'}</p>
      <h4>Scores</h4>
      <pre>${JSON.stringify(pkg.dossier.scores, null, 2)}</pre>
      <h4>Evidence Binder (${pkg.binder.count})</h4>
      <pre>${JSON.stringify(pkg.binder.evidence, null, 2)}</pre>
      <h4>Readiness</h4>
      <pre>${JSON.stringify(pkg.assessment, null, 2)}</pre>
    </div>
  `;
};

$('#build-form').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {
    target: $('#target').value,
    scores: JSON.parse($('#scores').value),
    evidence: JSON.parse($('#evidence').value || '[]'),
    threshold: parseFloat($('#threshold').value),
  };
  const result = await postJSON(`${API}/packages`, body);
  $('#build-result').textContent = JSON.stringify(result, null, 2);
  loadPackages();
});

async function loadReadiness() {
  const data = await getJSON(`${API}/readiness`);
  const container = $('#readiness-list');
  container.innerHTML = '';
  (Array.isArray(data) ? data : []).forEach(a => {
    const card = document.createElement('div');
    card.className = 'panel';
    card.innerHTML = `
      <h3>${a.target}</h3>
      <span class="${statusClass(a.level)}">${a.level}</span>
      <p>Overall: ${a.overall_score}</p>
      <p>Failing: ${a.failing_dimensions.join(', ') || 'none'}</p>
    `;
    container.appendChild(card);
  });
}

async function loadSOC() {
  const health = await getJSON(BASE + 'healthz');
  $('#soc-health').textContent = JSON.stringify(health, null, 2);
  $('#soc-risk').textContent = 'Risk scoring is computed from audit events collected by the embedded SOC.';
  $('#soc-events').textContent = 'Events are available via the SOC collector API.';
}

loadPackages();
