const $ = id => document.getElementById(id);
const state = {builds: [], file: null, report: null, proof: null, busy: false};
const titles = {
  verify: ['Verify artifact', 'Verify before you deploy', 'Follow an artifact from its registered origin to the bytes in your hands.'],
  lab: ['Tampering lab', 'See exactly how it gets caught', 'Change the evidence. Understand why the verifier refuses to trust it.'],
  merkle: ['Merkle explorer', 'One field. A verifiable path', 'Explore how a small proof connects a manifest entry to an immutable root.'],
  ledger: ['Build ledger', 'A history you can check', 'Every registration leaves an on-chain record. No silent overwrites.']
};
const initialSteps = [
  ['Registry lookup', 'Find the registered artifact hash on-chain.'],
  ['Pipeline authorization', 'Confirm the builder is still authorized.'],
  ['Artifact fingerprint', 'Compare the actual bytes using SHA-256.'],
  ['Manifest integrity', 'Recompute the recorded Merkle root.'],
  ['Signer identity', 'Recover and check the pipeline signer.']
];
function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
function clear(node) { node.replaceChildren(); return node; }
function short(text, n = 12) { return text ? text.slice(0, n) + '…' + text.slice(-6) : '—'; }
function formatBytes(n) { return n < 1024 ? `${n} B` : n < 1048576 ? `${(n/1024).toFixed(1)} KiB` : `${(n/1048576).toFixed(1)} MiB`; }
function notify(text, error = false) { $('notice').hidden = false; $('notice').className = error ? 'error' : ''; $('notice').textContent = text; }
function tab(name) {
  document.querySelectorAll('.view').forEach(view => view.hidden = view.id !== 'view-' + name);
  document.querySelectorAll('.nav').forEach(button => button.classList.toggle('active', button.dataset.tab === name));
  $('breadcrumb').textContent = titles[name][0]; $('page-title').replaceChildren(document.createTextNode(titles[name][1]), el('span', '.'));
  $('page-description').textContent = titles[name][2];
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Request failed'); return data;
}
async function task(fn, message) {
  if (state.busy) return;
  state.busy = true; document.body.classList.add('busy');
  const buttons = [...document.querySelectorAll('button')]; buttons.forEach(b => b.disabled = true);
  if (message) notify(message);
  try { await fn(); } catch (error) { notify(error.message, true); }
  finally { state.busy = false; document.body.classList.remove('busy'); buttons.forEach(b => b.disabled = false); }
}
async function refreshStatus() {
  const status = await api('/api/status');
  for (const service of ['chain', 'ipfs']) { $(service + '-dot').classList.toggle('live', status[service]); $(service + '-state').textContent = status[service] ? 'Online' : 'Offline'; }
  $('chain-id').textContent = 'CHAIN ' + (status.chain_id || '—');
  if (status.errors.length) notify(status.errors.join(' · '), true);
}
async function refreshBuilds(selectHash) {
  state.builds = (await api('/api/builds')).builds;
  for (const id of ['build-select', 'lab-build', 'proof-build']) {
    const previous = selectHash || $(id).value;
    const first = id === 'build-select' ? 'Look up by uploaded artifact hash' : 'Choose a registered build';
    clear($(id)).append(new Option(first, ''));
    for (const build of state.builds.filter(b => id !== 'lab-build' || b.local)) $(id).append(new Option(`${build.name} · ${build.hash.slice(0, 8)}`, build.hash));
    if ([...$(id).options].some(o => o.value === previous)) $(id).value = previous;
  }
  renderLedger();
}
function renderFlow(steps) {
  const flow = clear($('verification-flow'));
  steps.forEach((step, i) => {
    const node = el('div', undefined, 'flow-step ' + (step.state || ''));
    node.append(el('div', step.state === 'pass' ? '✓' : step.state === 'fail' ? '×' : String(i + 1).padStart(2, '0'), 'flow-icon'),
      el('h3', step.title), el('p', step.detail), el('span', step.state === 'pass' ? 'VERIFIED' : step.state === 'fail' ? 'FAILED' : step.state === 'skipped' ? 'NOT REACHED' : 'AWAITING ARTIFACT', 'flow-state'));
    flow.append(node);
  });
}
function showReport(report) {
  state.report = report; tab('verify');
  const passed = report.result.passed, content = clear($('verdict-content'));
  content.className = 'verdict-result';
  content.append(el('span', passed ? '✓  DEPLOYMENT ALLOWED' : '×  DEPLOYMENT BLOCKED', 'status-pill' + (passed ? '' : ' fail')),
    el('h3', passed ? 'The evidence holds.' : 'Something doesn’t match.'), el('p', report.result.reason), el('div', report.artifact_name, 'result-file'));
  const counter = el('div', undefined, 'check-counter'); counter.append(el('span', 'Independent checks passed'), el('strong', `${report.steps.filter(s => s.state === 'pass').length} / 5`)); content.append(counter);
  if (report.explanation) content.append(el('div', (report.simulation ? 'TEACHING SIMULATION · ' : 'CONTROLLED FILE CHANGE · ') + report.explanation, 'reason-banner'));
  if (!report.comparison && !passed) content.append(el('div', 'To locate changed ZIP members, select an approved build whose original is available locally. A hash mismatch alone cannot locate the change.', 'reason-banner'));
  renderFlow(report.steps);
  $('trace-note').textContent = passed ? 'All checks agree. The received artifact matches the provenance registered by the authorized pipeline.' : report.result.reason + '. Checks marked “not reached” were not completed; they are not evidence of tampering.';
  $('comparison-panel').hidden = !report.comparison;
  if (report.comparison) renderComparison(report.comparison);
  $('evidence-panel').hidden = false;
  const evidence = clear($('evidence-content'));
  const rows = [['Received SHA-256', report.actual_hash], ['Approved SHA-256', report.expected_hash], ['Computed root', report.computed_root], ['On-chain root', report.record?.merkle_root], ['IPFS CID', report.record?.cid], ['Pipeline address', report.record?.pipeline]];
  rows.forEach(([label, value]) => { const row = el('div', undefined, 'evidence-row'); row.append(el('span', label), el('code', value || 'Not available')); evidence.append(row); });
  $('manifest-content').textContent = report.manifest ? JSON.stringify(report.manifest, null, 2) : 'No authenticated manifest was retrieved.';
  notify(passed ? 'Verification complete. All five checks passed.' : 'Verification complete. Deployment was blocked.', !passed);
}
function table(headers) { const node = el('table'), head = el('thead'), row = el('tr'), body = el('tbody'); headers.forEach(h => row.append(el('th', h))); head.append(row); node.append(head, body); return {node, body}; }
function renderComparison(comparison) {
  $('byte-offset').textContent = comparison.first_changed_byte === null ? 'IDENTICAL BYTES' : `FIRST CHANGE · BYTE ${comparison.first_changed_byte.toLocaleString()}`;
  const content = clear($('comparison-content'));
  const {node, body} = table(['FILE IN ARCHIVE', 'STATUS', 'ORIGINAL HASH → RECEIVED HASH']);
  comparison.files.forEach(file => { const row = el('tr'), status = el('td'); status.append(el('span', file.status, 'file-status ' + file.status)); const hashes = el('td'); hashes.append(el('code', `${short(file.before?.hash, 8)} → ${short(file.after?.hash, 8)}`)); row.append(el('td', file.name), status, hashes); body.append(row); });
  const wrap = el('div', undefined, 'table-wrap'); wrap.append(node);
  if (comparison.files.length) content.append(wrap);
  comparison.files.filter(file => file.diff).forEach(file => {
    const details = el('details'); details.open = true;
    details.append(el('summary', `See changed lines / ${file.name}`), el('pre', file.diff + (file.diff_truncated ? '\n… diff truncated at 120 lines' : ''))); content.append(details);
  });
  content.append(el('div', `${formatBytes(comparison.original_size)} original → ${formatBytes(comparison.candidate_size)} received. ${comparison.note}`, 'comparison-note'));
}
function renderLedger() {
  $('build-count').textContent = state.builds.length;
  const content = clear($('ledger-content'));
  if (!state.builds.length) { content.append(el('p', 'No builds registered yet. Create a sample build to begin.', 'muted')); return; }
  const {node, body} = table(['ARTIFACT / HASH', 'REGISTERED', 'STORAGE', 'BLOCK', '']);
  state.builds.forEach(build => {
    const row = el('tr'), name = el('td'); name.append(el('span', build.name, 'ledger-name'), el('span', short(build.hash), 'ledger-meta'));
    const date = el('td', new Date(build.timestamp * 1000).toLocaleString());
    const storage = el('td'); storage.append(el('code', short(build.cid, 9)), el('div', build.local ? 'Original available locally' : 'No local original', 'muted'));
    const action = el('td'), button = el('button', build.local ? 'Verify ↗' : 'Inspect proof ↗', 'text-button');
    button.addEventListener('click', () => task(async () => { if (build.local) { $('build-select').value = build.hash; showReport(await api('/api/verify', {expected_hash: build.hash})); } else { $('proof-build').value = build.hash; tab('merkle'); await loadProof(0); } }, 'Retrieving registered evidence…'));
    action.append(button); row.append(name, date, storage, el('td', String(build.block)), action); body.append(row);
  }); content.append(node);
}
function chooseFile(file) {
  if (!file) return;
  if (file.size === 0 || file.size > 12 * 1024 * 1024) { notify('Choose a nonempty artifact up to 12 MiB.', true); return; }
  state.file = file; $('file-label').textContent = file.name; $('file-description').textContent = formatBytes(file.size) + ' · ready for verification';
}
async function fileData() {
  if (!state.file) throw new Error('Choose an artifact file first.');
  const bytes = new Uint8Array(await state.file.arrayBuffer());
  let binary = ''; for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
  return {name: state.file.name, content: btoa(binary)};
}
async function loadProof(index) {
  const hash = $('proof-build').value; if (!hash) { clear($('proof-entries')).append(el('p', 'Choose a registered build.', 'muted')); clear($('proof-path')); return; }
  const proof = await api(`/api/proof?hash=${encodeURIComponent(hash)}&index=${index}`); state.proof = proof;
  const entries = clear($('proof-entries'));
  proof.entries.forEach((entry, i) => { const b = el('button', undefined, 'entry-button' + (i === index ? ' active' : '')); b.append(el('small', String(i).padStart(2, '0')), el('span', entry[0] === 'dependency' ? entry[1].name : entry[0]), el('code', typeof entry[1] === 'string' ? entry[1] : entry[1].version)); b.addEventListener('click', () => task(() => loadProof(i), 'Checking inclusion proof…')); entries.append(b); });
  const path = clear($('proof-path'));
  function node(label, hash, cls = '') { const n = el('div', undefined, 'proof-node ' + cls); n.append(el('strong', label), el('code', hash)); return n; }
  path.append(node(`Selected leaf / ${proof.entries[index][0]}`, proof.leaf));
  proof.siblings.forEach(([hash, side], i) => { path.append(el('div', '↓  SHA-256', 'proof-arrow'), node(`Level ${i + 1} · sibling on the ${side}`, hash)); });
  path.append(el('div', '↓', 'proof-arrow'), node('Trusted on-chain root', proof.root, 'root'), el('div', proof.valid ? '✓ Inclusion proof matches the registered root.' : '× Proof does not match the registered root.', 'proof-result'));
  notify(proof.valid ? 'Inclusion proof verified against the on-chain root.' : 'Inclusion proof failed.', !proof.valid);
}
document.querySelectorAll('.nav').forEach(b => b.addEventListener('click', () => tab(b.dataset.tab)));
$('artifact-file').addEventListener('change', event => chooseFile(event.target.files[0]));
for (const type of ['dragover', 'dragleave', 'drop']) $('dropzone').addEventListener(type, event => { event.preventDefault(); $('dropzone').classList.toggle('dragging', type === 'dragover'); if (type === 'drop') chooseFile(event.dataTransfer.files[0]); });
$('verify-button').addEventListener('click', () => task(async () => { const body = await fileData(); body.expected_hash = $('build-select').value || null; showReport(await api('/api/verify', body)); }, 'Hashing the artifact and checking registered evidence…'));
$('use-original').addEventListener('click', () => task(async () => { const hash = $('build-select').value; if (!hash) throw new Error('Select a registered build first.'); showReport(await api('/api/verify', {expected_hash: hash})); }, 'Checking the registered original…'));
$('sample-button').addEventListener('click', () => task(async () => { const result = await api('/api/sample', {}); await refreshBuilds(result.artifact_hash); showReport(await api('/api/verify', {expected_hash: result.artifact_hash})); notify('Sample build registered on-chain and verified. Its commit is illustrative demo metadata.'); }, 'Building sample → signing root → uploading to IPFS → registering on-chain…'));
document.querySelectorAll('[data-attack]').forEach(b => b.addEventListener('click', () => task(async () => { const hash = $('lab-build').value; if (!hash) throw new Error('Choose a trusted baseline build first.'); showReport(await api('/api/lab', {expected_hash: hash, attack: b.dataset.attack})); }, 'Preparing controlled attack and running the verifier…')));
$('refresh').addEventListener('click', () => task(async () => { await refreshStatus(); await refreshBuilds(); }, 'Checking local services…'));
$('refresh-builds').addEventListener('click', () => task(() => refreshBuilds(), 'Reading contract events…'));
$('proof-build').addEventListener('change', () => task(() => loadProof(0), 'Fetching manifest and building proof…'));
$('register-button').addEventListener('click', () => { if (!state.file) { notify('Upload an artifact before registering it.', true); return; } $('register-dialog').showModal(); });
$('cancel-register').addEventListener('click', () => $('register-dialog').close());
$('register-form').addEventListener('submit', event => { event.preventDefault(); task(async () => { const body = await fileData(); body.commit = $('commit-input').value.trim(); body.dependencies = JSON.parse($('dependencies-input').value || '[]'); const result = await api('/api/register', body); $('register-dialog').close(); await refreshBuilds(result.artifact_hash); showReport(await api('/api/verify', {expected_hash: result.artifact_hash})); notify('Uploaded artifact signed, registered, and verified.'); }, 'Signing and registering the exact uploaded bytes…'); });
$('download-report').addEventListener('click', () => { if (!state.report) return; const url = URL.createObjectURL(new Blob([JSON.stringify(state.report, null, 2)], {type: 'application/json'})); const a = el('a'); a.href = url; a.download = 'provenance-report.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
renderFlow(initialSteps.map(([title, detail]) => ({title, detail})));
task(async () => { await refreshStatus(); await refreshBuilds(); }, 'Connecting to your local provenance ledger…').then(() => { if (!$('notice').classList.contains('error')) $('notice').hidden = true; });
