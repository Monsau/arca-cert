// Arca Cert — Certification Cockpit.
//
// API base contract (shared Arca Suite skin, see top of arcasuite-ui.css):
// inside the portal the module UI is composed into the /module/<key>
// document, so window.location is NOT the module prefix. Resolve API paths
// from window.__ARCA_MODULE_BASE__ (injected by the portal) with a
// /m/<module-key>/ location match as the standalone-dev fallback.
//
// Security by design: the Suite portal attaches the user's SSO Bearer header
// server-side on every proxied call, so this script never sends credentials.
// A 401/403 therefore means "open this module through the Suite portal".
const _injected = window.__ARCA_MODULE_BASE__;
const _pm = window.location.pathname.match(/^\/m\/([^/]+)\//);
const BASE = _injected || (_pm ? '/m/' + _pm[1] + '/' : '/');
const API = BASE + 'api/v1';

function $(sel) { return document.querySelector(sel); }

// Escape everything that comes from the API before it touches innerHTML.
function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function statusTag(status) {
  return `<span class="tag status-${esc(status)}">${esc(status)}</span>`;
}

// Evidence content-gate outcome: "passed" | "skipped" | absent (reference-only).
function validationTag(ev) {
  if (ev.validation === 'passed') return '<span class="tag ok">validated</span>';
  if (ev.validation === 'skipped') return '<span class="tag warn">not validated</span>';
  return '<span class="muted">reference-only</span>';
}

async function getJSON(path) {
  const res = await fetch(path);
  if (res.ok) return { ok: true, status: res.status, data: await res.json() };
  return { ok: false, status: res.status, data: await res.json().catch(() => null) };
}

async function postJSON(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) return { ok: true, status: res.status, data: await res.json() };
  return { ok: false, status: res.status, data: await res.json().catch(() => null) };
}

// Human-readable reason for a failed call, surfaced in a .message.error box.
function failureText(result, fallback) {
  if (result.status === 401 || result.status === 403) {
    return `The API refused the request (HTTP ${result.status}). ` +
      'Open this module through the Suite portal so your SSO session is ' +
      'attached to every call.';
  }
  const detail = result.data && (result.data.detail || result.data.error);
  return detail ? `${fallback}: ${detail}` : `${fallback} (HTTP ${result.status}).`;
}

function showMessage(container, kind, text) {
  const el = typeof container === 'string' ? $(container) : container;
  el.innerHTML = text ? `<div class="message ${kind}">${esc(text)}</div>` : '';
}

// ---- View switching --------------------------------------------------------

document.querySelectorAll('nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    $(`#${btn.dataset.view}-view`).classList.add('active');
    if (btn.dataset.view === 'dossiers') loadDossiers();
  });
});

// ---- Dossiers explorer -----------------------------------------------------

function renderDossierTable(dossiers) {
  const container = $('#dossier-list');
  if (!dossiers.length) {
    container.innerHTML = `
      <div class="panel">
        <h3>No certification dossiers yet</h3>
        <p>A dossier bundles a target's dimension scores, evidence references
           and a validity window into one auditable record.</p>
        <p>Create the first one with the <strong>New Dossier</strong> form in
           the header: you need a target name and at least one score
           (a dimension plus a value between 0 and 1). Evidence is optional.</p>
        <p class="muted">Reads and writes require your Suite portal SSO
           session — the portal attaches the token on every call.</p>
      </div>`;
    return;
  }
  const rows = dossiers.map(d => `
    <tr class="row-click" data-dossier-id="${esc(d.id)}">
      <td><code>${esc(d.id.slice(0, 8))}</code></td>
      <td>${esc(d.target)}</td>
      <td>${statusTag(d.status)}</td>
      <td>${esc(d.scores.map(s => `${s.dimension}=${s.value}`).join(', '))}</td>
      <td>${d.evidence.length}</td>
      <td>${esc(new Date(d.valid_until).toLocaleDateString())}</td>
    </tr>`).join('');
  container.innerHTML = `
    <table>
      <thead>
        <tr><th>ID</th><th>Target</th><th>Status</th><th>Scores</th>
            <th>Evidence</th><th>Valid until</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
  container.querySelectorAll('tr[data-dossier-id]').forEach(tr => {
    tr.addEventListener('click', () => showDossier(tr.dataset.dossierId));
  });
}

async function loadDossiers() {
  const container = $('#dossier-list');
  const target = $('#dossier-filter').value.trim();
  showMessage('#dossiers-message', '', '');
  container.innerHTML = '<p class="muted">Loading dossiers…</p>';
  const query = target ? `?target=${encodeURIComponent(target)}` : '';
  const result = await getJSON(`${API}/dossiers${query}`);
  if (!result.ok) {
    container.innerHTML = '';
    showMessage('#dossiers-message', 'error',
      failureText(result, 'Could not load dossiers'));
    return;
  }
  renderDossierTable(result.data.dossiers || []);
}

// ---- Dossier drill-down ----------------------------------------------------

async function showDossier(id) {
  const detail = $('#dossier-detail');
  detail.classList.remove('hidden');
  detail.innerHTML = '<p class="muted">Loading dossier…</p>';
  detail.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const [dossierResult, remediationResult] = await Promise.all([
    getJSON(`${API}/dossiers/${encodeURIComponent(id)}`),
    getJSON(`${API}/dossiers/${encodeURIComponent(id)}/remediation`),
  ]);
  if (!dossierResult.ok) {
    detail.innerHTML = '';
    showMessage('#dossiers-message', 'error',
      failureText(dossierResult, `Could not load dossier ${id}`));
    return;
  }
  const d = dossierResult.data;
  const plan = remediationResult.ok ? remediationResult.data : null;

  const scoreRows = (d.scores || []).map(s => `
    <tr><td>${esc(s.dimension)}</td><td>${esc(s.value)}</td></tr>`).join('');
  const evidenceRows = (d.evidence || []).map(e => `
    <tr>
      <td>${esc(e.source)}</td>
      <td><code>${esc(e.ref_id)}</code></td>
      <td>${esc(e.description || '—')}</td>
      <td>${validationTag(e)}</td>
    </tr>`).join('') || '<tr><td colspan="4" class="muted">No evidence attached.</td></tr>';
  const remediationItems = plan && plan.items ? plan.items.map(i => `
    <tr>
      <td>${esc(i.dimension || '—')}</td>
      <td>${esc(i.risk)}</td>
      <td>${esc(i.action)}</td>
      <td>${esc(i.owner)}</td>
      <td>${esc(i.due_days)}</td>
    </tr>`).join('') : '';

  detail.innerHTML = `
    <div class="panel">
      <div class="actions">
        <h3>Dossier <code>${esc(d.id)}</code></h3>
        <button type="button" id="back-to-list" class="secondary">← Back to list</button>
      </div>
      <p>Target: <strong>${esc(d.target)}</strong> ${statusTag(d.status)}
         ${d.is_expired ? '<span class="tag error">expired</span>' : ''}</p>
      <p>Reviewer: ${esc(d.reviewer || '—')} ·
         Valid until: ${esc(new Date(d.valid_until).toLocaleString())}</p>
      <p>Seal: <code>${esc(d.seal ? d.seal.slice(0, 16) + '…' : 'n/a')}</code>
         ${d.revoked_at ? `· Revoked: ${esc(new Date(d.revoked_at).toLocaleString())}
           (${esc(d.revocation_reason || 'no reason')})` : ''}</p>
    </div>
    <div class="mod-grid">
      <div class="panel">
        <h4>Dimension scores</h4>
        <table><thead><tr><th>Dimension</th><th>Value</th></tr></thead>
          <tbody>${scoreRows || '<tr><td colspan="2" class="muted">No scores.</td></tr>'}</tbody></table>
      </div>
      <div class="panel">
        <h4>Evidence (${(d.evidence || []).length})</h4>
        <table><thead><tr><th>Source</th><th>Ref</th><th>Description</th><th>Validation</th></tr></thead>
          <tbody>${evidenceRows}</tbody></table>
      </div>
    </div>
    ${remediationItems ? `
    <div class="panel">
      <h4>Remediation plan</h4>
      <table><thead><tr><th>Dimension</th><th>Risk</th><th>Action</th><th>Owner</th><th>Due (days)</th></tr></thead>
        <tbody>${remediationItems}</tbody></table>
    </div>` : ''}`;
  $('#back-to-list').addEventListener('click', () => {
    detail.classList.add('hidden');
    detail.innerHTML = '';
  });
}

// ---- Create dossier --------------------------------------------------------
// POST /api/v1/dossiers requires a target and at least one score; the domain
// has no separate "framework"/"candidate" fields — the target names the
// certified artifact and dimensions carry the framework aspects.

function addScoreRow(dimension = '', value = '') {
  const row = document.createElement('div');
  row.className = 'row score-row';
  row.innerHTML = `
    <label>Dimension
      <input type="text" class="score-dimension" placeholder="security"
             value="${esc(dimension)}" required>
    </label>
    <label>Value (0–1)
      <input type="number" class="score-value" step="0.01" min="0" max="1"
             value="${esc(value)}" required>
    </label>
    <button type="button" class="secondary remove-row">Remove</button>`;
  row.querySelector('.remove-row').addEventListener('click', () => row.remove());
  $('#score-rows').appendChild(row);
}

function addEvidenceRow() {
  const row = document.createElement('div');
  row.className = 'panel evidence-row';
  row.innerHTML = `
    <div class="row">
      <label>Source
        <input type="text" class="ev-source" placeholder="trust" required>
      </label>
      <label>Reference ID
        <input type="text" class="ev-ref" placeholder="ev-1" required>
      </label>
      <button type="button" class="secondary remove-row">Remove</button>
    </div>
    <label>Description
      <input type="text" class="ev-description" placeholder="what this evidence proves">
    </label>
    <details>
      <summary class="muted">Inline content (optional — triggers Arca Validate content gate)</summary>
      <label>Content
        <textarea class="ev-content" rows="3"
          placeholder="Turtle ontology, JSON/YAML manifest or workflow YAML"></textarea>
      </label>
      <label>MIME type
        <input type="text" class="ev-mime" placeholder="text/turtle">
      </label>
    </details>`;
  row.querySelector('.remove-row').addEventListener('click', () => row.remove());
  $('#evidence-rows').appendChild(row);
}

$('#add-score').addEventListener('click', () => addScoreRow());
$('#add-evidence').addEventListener('click', () => addEvidenceRow());

$('#create-form').addEventListener('submit', async e => {
  e.preventDefault();
  showMessage('#create-message', '', '');
  const body = {
    target: $('#cd-target').value.trim(),
    scores: [],
    evidence: [],
    threshold: parseFloat($('#cd-threshold').value),
  };
  document.querySelectorAll('#score-rows .score-row').forEach(row => {
    body.scores.push({
      dimension: row.querySelector('.score-dimension').value.trim(),
      value: parseFloat(row.querySelector('.score-value').value),
    });
  });
  document.querySelectorAll('#evidence-rows .evidence-row').forEach(row => {
    const evidence = {
      source: row.querySelector('.ev-source').value.trim(),
      ref_id: row.querySelector('.ev-ref').value.trim(),
      description: row.querySelector('.ev-description').value.trim(),
    };
    const content = row.querySelector('.ev-content').value;
    const mime = row.querySelector('.ev-mime').value.trim();
    if (content.trim()) { evidence.content = content; evidence.mime = mime; }
    body.evidence.push(evidence);
  });
  if (!body.target || !body.scores.length) {
    showMessage('#create-message', 'error',
      'A target and at least one score (dimension + value) are required.');
    return;
  }
  if (body.scores.some(s => !s.dimension || isNaN(s.value))) {
    showMessage('#create-message', 'error',
      'Every score needs a dimension name and a numeric value between 0 and 1.');
    return;
  }
  const result = await postJSON(`${API}/dossiers`, body);
  if (!result.ok) {
    showMessage('#create-message', 'error',
      failureText(result, 'Dossier was not created'));
    return;
  }
  const dossier = result.data.dossier || {};
  showMessage('#create-message', 'ok',
    `Dossier ${dossier.id} created for target "${dossier.target}" ` +
    `(status: ${dossier.status}). Remediation items: ` +
    `${result.data.remediation ? result.data.remediation.items.length : 0}.`);
  $('#create-form').reset();
  $('#score-rows').innerHTML = '';
  $('#evidence-rows').innerHTML = '';
  addScoreRow('security', '0.85');
  addScoreRow('compliance', '0.6');
});

// ---- Wiring ----------------------------------------------------------------

$('#refresh-dossiers').addEventListener('click', loadDossiers);
$('#dossier-filter').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); loadDossiers(); }
});

// Default form rows so the create view is usable on first open.
addScoreRow('security', '0.85');
addScoreRow('compliance', '0.6');
loadDossiers();
