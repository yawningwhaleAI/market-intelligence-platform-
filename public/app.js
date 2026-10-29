const state = {
  step: 0, meta: null, suggestions: null, platforms: new Set(), locations: [],
  authenticated: false, authConfigured: false, authMode: 'signup', estimate: null,
  projectId: null, plan: null, scanId: null, scanTimer: null, scanKey: null,
  apifyConnected: false, retryRun: false, hydrating: false, saveTimer: null,
  savePromise: null, itemOffset: 0
};
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url, body, method = body ? 'POST' : 'GET') {
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body ? {'Content-Type':'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  let data = {};
  try { data = await response.json(); } catch {}
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong. Please try again.');
  return data;
}
function toast(message) {
  const el = $('#toast'); el.textContent = message; el.classList.add('show');
  clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}
function showDashboard() {
  $('#workspace').hidden = false; $('#wizard').hidden = true;
  $('#workspace-guest').hidden = state.authenticated;
  $('#workspace-home').hidden = !state.authenticated;
  $('#plan-detail').hidden = true;
}
function showWizard() {
  $('#workspace').hidden = true; $('#wizard').hidden = false;
  paintStep();
}
function openAuth(mode = 'signup') {
  state.authMode = mode;
  $('#auth-title').textContent = mode === 'signup' ? 'Create your account.' : 'Welcome back.';
  $('#auth-submit').textContent = mode === 'signup' ? 'Create account' : 'Sign in';
  $('#auth-mode').textContent = mode === 'signup' ? 'Already have an account? Sign in' : 'New to Scoutwise? Create account';
  $('#auth-password').autocomplete = mode === 'signup' ? 'new-password' : 'current-password';
  $('#auth-result').innerHTML = '';
  if (!$('#auth-dialog').open) $('#auth-dialog').showModal();
}
function paintStep() {
  $$('.step').forEach((el, index) => el.classList.toggle('active', index === state.step));
  $('#step-count').textContent = `STEP ${state.step + 1} OF 4`;
  $('#progress-label').textContent = ['Your product','Explore the category','Choose coverage','Review and run'][state.step];
  $('#progress-fill').style.width = `${(state.step + 1) * 25}%`;
  if (state.step === 3) loadEstimate();
}
function selectedQueries() { return $$('#phrases input:checked').map(el => el.value); }
function selectedSegments() { return $$('#segments input:checked').map(el => el.value); }
function suggestionMarkup(data) {
  return `<div class="category-tag">${esc(data.category_family || 'Suggested category')}</div>
    <p class="suggestion-note">${esc(data.summary || 'Review and edit these suggestions.')}</p>
    <h3>Explore product segments</h3>
    <div class="check-list" id="segments">${(data.suggested_segments || []).map((item, index) => `<label class="check-row"><input type="checkbox" value="${esc(item)}" ${index < 3 ? 'checked' : ''}><span>${esc(item)}</span></label>`).join('')}</div>
    <h3>Search phrases <small>Choose up to 10</small></h3>
    <div class="phrase-list" id="phrases">${(data.search_phrases || []).map((item, index) => `<label class="phrase"><input type="checkbox" value="${esc(item)}" ${index < 5 ? 'checked' : ''}><span>${esc(item)}</span></label>`).join('')}</div>
    <label class="field-label" for="custom-phrase">Add a phrase</label>
    <div class="inline-form"><input id="custom-phrase" class="text-input" placeholder="e.g. low sugar breakfast bar"><button type="button" class="outline" id="add-phrase">Add</button></div>
    <h3>Compare these attributes</h3><div class="attribute-row">${(data.comparison_attributes || []).map(item => `<span>${esc(item)}</span>`).join('')}</div>
    <p class="disclaimer">${esc(data.note || 'Suggestions are starting points, not evidence of demand.')}</p>`;
}
async function loadSuggestions() {
  const product = $('#product').value.trim();
  if (product.length < 2) { $('#product').focus(); toast('Add a little more about the product first.'); return false; }
  state.step = 1; paintStep(); $('#suggestion-area').innerHTML = '<div class="skeleton">Finding useful categories and search phrases…</div>';
  try {
    state.suggestions = await api('/api/suggestions', {product, industry:$('#industry').value.trim(), audience:$('#audience').value.trim()});
    $('#suggestion-area').innerHTML = suggestionMarkup(state.suggestions);
    $('#add-phrase').onclick = () => {
      const input = $('#custom-phrase'), value = input.value.trim(); if (!value) return;
      const wrap = $('#phrases');
      if ([...wrap.querySelectorAll('input')].some(item => item.value.toLowerCase() === value.toLowerCase())) return;
      if (wrap.querySelectorAll('input:checked').length >= 10) { toast('Choose up to 10 search phrases.'); return; }
      const label = document.createElement('label'); label.className = 'phrase';
      label.innerHTML = `<input type="checkbox" checked value="${esc(value)}"><span>${esc(value)}</span>`;
      wrap.append(label); input.value = ''; scheduleDraftSave();
    };
    $('#phrases').addEventListener('change', event => {
      if (event.target.checked && $('#phrases').querySelectorAll('input:checked').length > 10) {
        event.target.checked = false; toast('Choose up to 10 search phrases.');
      }
    });
    scheduleDraftSave(); return true;
  } catch (error) { toast(error.message); return false; }
}
function getCityGroups() {
  const data = state.meta?.locations || [];
  return Array.isArray(data) ? data : Object.entries(data).map(([id, value]) => ({id, name:value.name || id, localities:value.localities || []}));
}
function loadCityOptions() {
  const groups = getCityGroups(), city = $('#city');
  city.innerHTML = groups.map(group => `<option value="${esc(group.id || group.name)}">${esc(group.name || group.id)}</option>`).join('');
  city.onchange = () => { loadLocalityOptions(); scheduleDraftSave(); }; loadLocalityOptions();
}
function loadLocalityOptions() {
  const groups = getCityGroups();
  const group = groups.find(item => (item.id || item.name) === $('#city').value) || groups[0];
  $('#locality').innerHTML = (group?.localities || []).map(item => `<option value="${esc(JSON.stringify({...item, city:item.city || group.name}))}">${esc(item.name)}</option>`).join('');
}
function addLocation(location) {
  if (state.locations.some(item => item.name === location.name && item.city === location.city)) return;
  if (state.locations.length >= 10) { toast('Choose up to 10 localities.'); return; }
  state.locations.push(location); drawLocations(); scheduleDraftSave();
}
function drawLocations() {
  const target = $('#selected-locations');
  target.innerHTML = state.locations.map((location, index) => `<span class="chip">${esc(location.name)}, ${esc(location.city)} <button type="button" aria-label="Remove ${esc(location.name)}" data-remove="${index}">×</button></span>`).join('');
  target.querySelectorAll('[data-remove]').forEach(button => button.onclick = () => { state.locations.splice(+button.dataset.remove, 1); drawLocations(); scheduleDraftSave(); });
}
function drawPlatforms() {
  const labels = {blinkit:'Blinkit', zepto:'Zepto', instamart:'Instamart', amazon:'Amazon', flipkart:'Flipkart'};
  $('#platforms').innerHTML = state.meta.platforms.map(platform => `<label class="platform-card"><input type="checkbox" value="${esc(platform.id)}" ${['blinkit','zepto','instamart'].includes(platform.id) ? 'checked' : ''}><span class="platform-icon">${esc((labels[platform.id] || platform.name)[0])}</span><span><b>${esc(labels[platform.id] || platform.name)}</b><small>${esc(platform.scope === 'national' ? 'National coverage' : 'City & locality')}</small></span></label>`).join('');
  $('#platforms').onchange = () => {
    state.platforms = new Set($$('#platforms input:checked').map(item => item.value));
    $('#location-block').hidden = ![...state.platforms].some(item => ['blinkit','zepto','instamart'].includes(item));
    scheduleDraftSave();
  };
}
async function loadEstimate() {
  const phrases = selectedQueries(), platforms = $$('#platforms input:checked').map(item => item.value);
  if (!phrases.length || !platforms.length) {
    $('#estimate-card').innerHTML = '<div class="notice warn">Select at least one marketplace and one search phrase to see an estimate.</div>';
    $('#create-plan').disabled = true; return;
  }
  $('#estimate-card').innerHTML = '<div class="skeleton">Calculating your estimate…</div>';
  try {
    const result = await api('/api/estimate', {platforms, queries:phrases, locations:state.locations, max_items_per_query:+$('#depth').value, spend_cap_usd:+$('#budget').value});
    state.estimate = result;
    $('#estimate-card').innerHTML = `<div class="estimate-top"><div><small>ESTIMATED ACTOR COST</small><strong>$${Number(result.estimated_cost_usd).toFixed(2)}</strong><span>Buffered estimate: $${Number(result.buffered_estimate_usd).toFixed(2)}</span></div><div class="budget-state ${result.within_cap ? 'ok' : 'over'}">${result.within_cap ? 'Within' : 'Over'} your $${Number(result.spend_cap_usd).toFixed(2)} cap</div></div><div class="estimate-lines">${result.platforms.map(platform => `<div><span>${esc(platform.platform)} <small>${esc(platform.scope)} · ${platform.queries} phrases × ${platform.locations} area${platform.locations === 1 ? '' : 's'}</small></span><b>$${Number(platform.buffered_estimate_usd).toFixed(2)}</b></div>`).join('')}</div><p class="estimate-note">${esc(result.cost_basis)} ${esc(result.coverage_note)}</p>${!result.within_cap ? '<div class="notice warn">Try fewer localities, fewer phrases, or a lower result depth to bring the estimate under budget.</div>' : ''}`;
    $('#create-plan').disabled = !result.within_cap;
  } catch (error) { $('#estimate-card').innerHTML = `<div class="notice warn">${esc(error.message)}</div>`; $('#create-plan').disabled = true; }
}
function currentPlanPayload() {
  const product = $('#product').value.trim();
  const platforms = $$('#platforms input:checked').map(item => item.value);
  const queries = selectedQueries();
  return {
    name: product || state.plan?.name || 'New market research',
    brief: {product, industry:$('#industry').value.trim(), audience:$('#audience').value.trim()},
    scope: {
      category_family: state.suggestions?.category_family || '',
      segments: selectedSegments(), queries,
      suggested_segments: state.suggestions?.suggested_segments || [],
      search_phrases: state.suggestions?.search_phrases || [],
      suggestions: state.suggestions,
      platforms, locations:state.locations,
      max_items_per_query:+$('#depth').value || 20,
      spend_cap_usd:+$('#budget').value || 5,
      estimate:state.estimate, current_step:state.step
    }
  };
}
function scheduleDraftSave() {
  if (!state.projectId || state.hydrating || !state.authenticated) return;
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => persistDraft().catch(error => toast(`Draft not saved: ${error.message}`)), 800);
}
async function persistDraft() {
  if (!state.projectId || state.hydrating) return;
  clearTimeout(state.saveTimer); state.saveTimer = null;
  if (state.savePromise) await state.savePromise;
  const body = currentPlanPayload();
  state.savePromise = api(`/api/plans/${state.projectId}`, body, 'PUT');
  try {
    await state.savePromise;
    state.plan = {...state.plan, ...body, updated_at:new Date().toISOString()};
    return true;
  } finally { state.savePromise = null; }
}
async function flushDraft() {
  if (state.saveTimer || state.savePromise) return persistDraft();
  return state.projectId ? persistDraft() : false;
}
function statusLabel(value) {
  return ({draft:'Draft',ready:'Ready',running:'Running',queued:'Queued',completed:'Complete',succeeded:'Complete',partial:'Partial results',failed:'Failed'})[value] || 'Draft';
}
function renderPlanList(plans) {
  const list = $('#plan-list');
  if (!plans.length) { list.innerHTML = '<div class="empty-plans">No research saved yet. Start a plan and Scoutwise will keep your progress here.</div>'; return; }
  list.innerHTML = plans.map(plan => {
    const product = plan.brief?.product || plan.name || 'Untitled research';
    const details = [plan.scope?.platforms?.length ? `${plan.scope.platforms.length} marketplaces` : '', plan.scope?.locations?.length ? `${plan.scope.locations.length} locations` : '', plan.updated_at ? new Date(plan.updated_at).toLocaleDateString() : ''].filter(Boolean).join(' · ');
    return `<button type="button" class="plan-card" data-plan="${esc(plan.id)}"><span><b>${esc(product)}</b><small>${esc(details || 'Continue setting up this research')}</small></span><span class="status-pill ${esc(plan.lifecycle_status || 'draft')}">${esc(statusLabel(plan.lifecycle_status))}</span></button>`;
  }).join('');
  list.querySelectorAll('[data-plan]').forEach(button => button.onclick = () => openPlan(button.dataset.plan));
}
async function loadWorkspace() {
  showDashboard();
  if (!state.authenticated) return;
  try {
    const [data, connection] = await Promise.all([api('/api/plans'), api('/api/apify/status')]);
    state.apifyConnected = connection.connected;
    $('#apify-status').textContent = connection.connected ? `Connected to ${connection.account_label || 'your Apify account'}.` : 'Connect your Apify account before launching a scan.';
    renderPlanList(data.plans || []);
  } catch (error) { toast(error.message); }
}
async function createDraft() {
  const body = {name:'New market research', brief:{product:'', industry:'', audience:''}, scope:{platforms:[], queries:[], locations:[], max_items_per_query:20, spend_cap_usd:5, current_step:0}};
  const result = await api('/api/plans', body);
  state.projectId = result.id; state.plan = {...body, id:result.id}; state.step = 0; state.suggestions = null; state.locations = []; state.estimate = null; state.scanId = null;
  clearWizard(); showWizard(); toast('Draft started. Scoutwise will save your progress automatically.');
}
function clearWizard() {
  state.hydrating = true;
  $('#product').value = ''; $('#industry').value = ''; $('#audience').value = '';
  $('#suggestion-area').innerHTML = '<div class="skeleton">Your category suggestions will appear here.</div>';
  state.locations = []; drawLocations(); $('#budget').value = '5'; $('#depth').value = '20';
  $('#platforms').querySelectorAll('input').forEach(input => { input.checked = ['blinkit','zepto','instamart'].includes(input.value); });
  state.platforms = new Set($$('#platforms input:checked').map(input => input.value));
  $('#location-block').hidden = false; state.hydrating = false;
}
function restorePlan(plan) {
  state.hydrating = true;
  state.projectId = plan.id; state.plan = plan;
  const brief = plan.brief || {}, scope = plan.scope || {};
  $('#product').value = brief.product || ''; $('#industry').value = brief.industry || ''; $('#audience').value = brief.audience || '';
  state.suggestions = scope.suggestions || {
    category_family:scope.category_family || 'Suggested category',
    suggested_segments:scope.suggested_segments || scope.segments || [],
    search_phrases:scope.search_phrases || scope.queries || [],
    comparison_attributes:[], summary:'Your saved research scope.', note:'Edit these suggestions before running the scan.'
  };
  $('#suggestion-area').innerHTML = suggestionMarkup(state.suggestions);
  const segmentSet = new Set(scope.segments || []), querySet = new Set(scope.queries || []);
  $('#segments').querySelectorAll('input').forEach(input => input.checked = segmentSet.has(input.value));
  $('#phrases').querySelectorAll('input').forEach(input => input.checked = querySet.has(input.value));
  restoreSuggestionsHandlers();
  state.locations = scope.locations || []; drawLocations();
  const selectedPlatforms = new Set(scope.platforms || []);
  $('#platforms').querySelectorAll('input').forEach(input => input.checked = selectedPlatforms.has(input.value));
  state.platforms = selectedPlatforms;
  $('#location-block').hidden = ![...selectedPlatforms].some(item => ['blinkit','zepto','instamart'].includes(item));
  $('#depth').value = String(scope.max_items_per_query || 20); $('#budget').value = String(scope.spend_cap_usd || scope.estimate?.spend_cap_usd || 5);
  state.estimate = scope.estimate || null; state.step = Math.min(Math.max(Number(scope.current_step || 0), 0), 3);
  state.hydrating = false;
}
async function openPlan(projectId) {
  clearInterval(state.scanTimer); state.scanTimer = null;
  try {
    const data = await api(`/api/plans/${projectId}`);
    state.plan = data.plan; state.projectId = projectId;
    $('#workspace-home').hidden = true; $('#plan-detail').hidden = false;
    $('#detail-name').textContent = data.plan.brief?.product || data.plan.name;
    const scope = data.plan.scope || {};
    $('#detail-summary').textContent = `${(scope.platforms || []).join(', ') || 'No marketplaces selected'} · ${(scope.queries || []).length} search phrases · ${(scope.locations || []).length} localities`;
    const scans = data.scans || [];
    $('#scan-list').innerHTML = scans.length ? `<h3>Past scans</h3>${scans.map(scan => `<div class="scan-card"><span><b>${esc(statusLabel(scan.status))}</b><small>${esc(new Date(scan.created_at).toLocaleString())}</small></span><button type="button" class="outline" data-scan="${esc(scan.id)}">View results</button></div>`).join('')}` : '<div class="empty-plans">Your plan is saved. Start a scan when it is ready.</div>';
    $('#scan-list').querySelectorAll('[data-scan]').forEach(button => button.onclick = () => openScan(button.dataset.scan));
    $('#scan-results').hidden = true;
    if (scans.length) openScan(scans[0].id);
  } catch (error) { toast(error.message); }
}
function money(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? `₹${number.toLocaleString('en-IN', {maximumFractionDigits:2})}` : String(value);
}
function productLink(url) {
  try { const parsed = new URL(url); return parsed.protocol === 'https:' ? parsed.href : ''; } catch { return ''; }
}
function renderScan(data, append = false) {
  const target = $('#scan-results'); target.hidden = false;
  const scan = data.scan;
  const stateText = data.active ? 'Scanning marketplaces… results will appear here as Apify finishes.' : (data.item_count ? 'Results are saved to your Scoutwise account.' : 'The selected actors finished without returning product rows.');
  const errorRuns = data.runs.filter(run => run.error_message);
  const items = data.items || [];
  const resultRows = items.map(item => {
    const fields = item.normalized || {}, local = item.run_scope?.location;
    const coverage = Array.isArray(local) ? local.map(place => `${place.name}, ${place.city}`).join(' · ') : local ? `${local.name}, ${local.city}` : 'National';
    const name = fields.product_name_raw || fields.title || 'Product';
    const url = productLink(item.source_url);
    return `<tr><td>${esc(item.platform)}</td><td>${esc(coverage)}</td><td>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(name)}</a>` : esc(name)}</td><td>${esc(fields.brand_raw || '—')}</td><td>${esc(fields.pack_size_raw || '—')}</td><td>${esc(money(fields.price_raw))}</td><td>${esc(money(fields.mrp_raw))}</td><td>${esc(fields.rating_raw ?? '—')}</td><td>${esc(fields.stock_status_raw ?? '—')}</td></tr>`;
  }).join('');
  const table = items.length ? `<div class="results-wrap"><table class="results-table"><thead><tr><th>Platform</th><th>Coverage</th><th>Product</th><th>Brand</th><th>Pack</th><th>Price</th><th>MRP</th><th>Rating</th><th>Stock</th></tr></thead><tbody>${resultRows}</tbody></table></div>` : `<div class="result-empty">${esc(stateText)}</div>`;
  const errors = errorRuns.length ? `<ul class="run-errors">${errorRuns.map(run => `<li>${esc(run.platform)}: ${esc(run.error_message)} ${run.actor_run_id ? `<a href="https://console.apify.com/actors/runs/${esc(run.actor_run_id)}" target="_blank" rel="noopener noreferrer">Open Apify run</a>` : ''}</li>`).join('')}</ul>` : '';
  const nextOffset = data.offset + items.length;
  const more = data.items_total > nextOffset ? `<button class="outline" id="load-more" type="button">Load more results</button>` : '';
  target.innerHTML = `<h3>Scan results <span class="status-pill ${esc(scan.status)}">${esc(statusLabel(scan.status))}</span></h3><div class="scan-summary">${esc(stateText)} ${data.item_count} product rows saved · estimated $${Number(scan.estimate?.estimated_cost_usd || 0).toFixed(2)} · actual Apify charge so far $${Number(data.actual_cost_usd || 0).toFixed(2)}.</div>${errors}${table}<div class="actions">${data.items_total > 0 ? `<span class="action-note">Showing ${Math.min(nextOffset, data.items_total)} of ${data.items_total} saved results</span>` : '<span></span>'}${more}</div>`;
  const loadMore = $('#load-more');
  if (loadMore) loadMore.onclick = async () => { state.itemOffset = nextOffset; await refreshScan(false); };
  if (data.active) {
    clearTimeout(state.scanTimer); state.scanTimer = setTimeout(() => refreshScan(false), 5000);
  } else { clearTimeout(state.scanTimer); state.scanTimer = null; }
}
async function openScan(scanId) {
  state.scanId = scanId; state.itemOffset = 0; $('#scan-results').hidden = false;
  $('#scan-results').innerHTML = '<div class="skeleton">Checking Apify run status and loading saved results…</div>';
  await refreshScan(false);
}
async function refreshScan(append = false) {
  if (!state.scanId) return;
  try {
    const data = await api(`/api/scans/${state.scanId}?offset=${state.itemOffset}&limit=200`);
    renderScan(data, append);
    if (data.scan.status === 'succeeded' || data.scan.status === 'partial') {
      const title = state.plan?.brief?.product || state.plan?.name;
      if (title) $('#detail-name').textContent = title;
    }
  } catch (error) {
    $('#scan-results').innerHTML = `<div class="notice warn">${esc(error.message)}</div>`;
    clearTimeout(state.scanTimer); state.scanTimer = setTimeout(() => refreshScan(false), 10000);
  }
}
async function beginScan() {
  if (!state.authenticated) { openAuth('signup'); return; }
  if (!state.projectId) { toast('Start a research plan first.'); return; }
  if (state.saveTimer || state.savePromise) await flushDraft();
  if (!state.apifyConnected) { state.retryRun = true; $('#apify-dialog').showModal(); return; }
  const button = $('#create-plan'); button.disabled = true; button.textContent = 'Starting scan…';
  try {
    if (!state.scanKey) state.scanKey = crypto.randomUUID();
    const result = await api(`/api/plans/${state.projectId}/scans`, {idempotency_key:state.scanKey});
    state.scanKey = null; state.plan = {...state.plan, lifecycle_status:'running'};
    toast(result.started ? `${result.started} Apify actor job${result.started === 1 ? '' : 's'} started.` : 'Apify could not start any actor jobs. Check the saved run details.');
    await openPlan(state.projectId);
  } catch (error) {
    toast(error.message);
    if (error.message.toLowerCase().includes('connect your apify')) { state.retryRun = true; $('#apify-dialog').showModal(); }
  } finally { button.disabled = false; button.innerHTML = 'Save plan & run scan <span>→</span>'; }
}
async function connectApify(event) {
  event.preventDefault(); const button = $('#validate-token'); button.disabled = true; button.textContent = 'Checking…'; $('#apify-result').textContent = '';
  try {
    const result = await api('/api/apify/validate', {token:$('#apify-token').value});
    state.apifyConnected = Boolean(result.saved); $('#apify-result').innerHTML = `<div class="notice success">Connected to ${esc(result.account_name)}. ${esc(result.message)}</div>`;
    $('#apify-token').value = ''; $('#apify-status').textContent = result.message; $('#connect-apify').textContent = 'Reconnect Apify';
    $('#apify-dialog').close(); toast(result.saved ? 'Apify connected and saved securely.' : 'Token validated. Sign in to save it.');
    if (state.retryRun && result.saved) { state.retryRun = false; setTimeout(beginScan, 0); }
  } catch (error) { $('#apify-result').innerHTML = `<div class="notice warn">${esc(error.message)}</div>`; }
  finally { button.disabled = false; button.textContent = 'Validate token'; }
}
function restoreSuggestionsHandlers() {
  const add = $('#add-phrase');
  if (!add) return;
  add.onclick = () => {
    const input = $('#custom-phrase'), value = input.value.trim(); if (!value) return;
    const wrap = $('#phrases');
    if (wrap.querySelectorAll('input:checked').length >= 10) { toast('Choose up to 10 search phrases.'); return; }
    if ([...wrap.querySelectorAll('input')].some(item => item.value.toLowerCase() === value.toLowerCase())) return;
    const label = document.createElement('label'); label.className = 'phrase'; label.innerHTML = `<input type="checkbox" checked value="${esc(value)}"><span>${esc(value)}</span>`;
    wrap.append(label); input.value=''; scheduleDraftSave();
  };
}
function restorePlanIntoWizard(plan) {
  restorePlan(plan); showWizard();
}
async function finishEmailConfirmation() {
  if (window.location.pathname !== '/auth/callback') return;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const query = new URLSearchParams(window.location.search);
  for (const key of ['access_token', 'refresh_token', 'error_description', 'error']) {
    if (!params.has(key) && query.has(key)) params.set(key, query.get(key));
  }
  const error = params.get('error_description') || params.get('error');
  const access = params.get('access_token'), refresh = params.get('refresh_token');
  history.replaceState(null, '', '/auth/callback');
  if (error) { history.replaceState(null, '', '/'); toast(`Email confirmation failed: ${error}`); return; }
  if (!access || !refresh) { history.replaceState(null, '', '/'); toast('Email confirmed. Sign in to continue.'); return; }
  try { await api('/api/auth/session', {access_token:access, refresh_token:refresh}); history.replaceState(null, '', '/'); toast('Email confirmed. You’re signed in.'); }
  catch (problem) { history.replaceState(null, '', '/'); toast(problem.message); }
}
async function boot() {
  try {
    await finishEmailConfirmation();
    state.meta = await api('/api/meta'); loadCityOptions(); drawPlatforms();
    const [session, integrations] = await Promise.all([api('/api/session'), api('/api/integrations')]);
    state.authenticated = session.authenticated; state.authConfigured = session.auth_configured;
    $('#signin').textContent = session.authenticated ? 'My research' : 'Sign in';
    if (!session.auth_configured) $('#signin').title = 'Supabase Auth is not configured yet';
    const providers = integrations.ai_providers || [];
    $('#integration-note').textContent = providers.length ? `AI suggestions are routed through ${providers.join(' → ')}. Built-in suggestions remain available as a fallback.` : 'Suggestions use Scoutwise’s built-in category templates.';
    showDashboard();
    if (state.authenticated) await loadWorkspace();
  } catch { toast('Could not load your workspace. Refresh the page to try again.'); }
}

$$('[data-next]').forEach(button => button.onclick = async () => {
  if (state.step === 0) { await loadSuggestions(); return; }
  if (state.step === 1) {
    if (!selectedQueries().length) { toast('Choose at least one search phrase.'); return; }
    state.step = 2; paintStep(); await flushDraft(); return;
  }
  if (state.step === 2) {
    const selected = $$('#platforms input:checked').map(input => input.value);
    if (!selected.length) { toast('Choose at least one marketplace.'); return; }
    if (selected.some(item => ['blinkit','zepto','instamart'].includes(item)) && !state.locations.length) { toast('Add at least one locality for quick-commerce scans.'); return; }
    state.step = 3; paintStep(); await flushDraft();
  }
});
$$('[data-back]').forEach(button => button.onclick = () => { state.step = Math.max(0, state.step - 1); paintStep(); scheduleDraftSave(); });
$('#add-location').onclick = () => { try { addLocation(JSON.parse($('#locality').value)); } catch {} };
$$('[data-pick]').forEach(button => button.onclick = () => {
  const count = +button.dataset.pick;
  for (const group of getCityGroups()) for (const location of group.localities || []) {
    if (state.locations.length >= count) break;
    addLocation({...location, city:location.city || group.name});
  }
});
$('#depth').onchange = () => { loadEstimate(); scheduleDraftSave(); };
$('#budget').oninput = () => { clearTimeout(window.budgetTimer); window.budgetTimer = setTimeout(() => { loadEstimate(); scheduleDraftSave(); }, 250); };
$('#wizard-form').addEventListener('input', scheduleDraftSave);
$('#wizard-form').addEventListener('change', scheduleDraftSave);
$('#workspace-auth').onclick = () => openAuth('signup');
$('#new-research').onclick = async () => {
  if (!state.authenticated) { openAuth('signup'); return; }
  try { await createDraft(); } catch (error) { toast(error.message); }
};
$('#signin').onclick = () => state.authenticated ? loadWorkspace() : openAuth('login');
$('#signout').onclick = async () => {
  try { await api('/api/auth/logout', {}); state.authenticated = false; state.projectId = null; $('#signin').textContent = 'Sign in'; showDashboard(); toast('Signed out.'); }
  catch (error) { toast(error.message); }
};
$('#auth-mode').onclick = () => openAuth(state.authMode === 'signup' ? 'login' : 'signup');
$('#auth-close').onclick = () => $('#auth-dialog').close();
$('#auth-form').onsubmit = async event => {
  event.preventDefault(); const button = $('#auth-submit'); button.disabled = true; button.textContent = 'Please wait…';
  try {
    const result = await api(`/api/auth/${state.authMode}`, {email:$('#auth-email').value, password:$('#auth-password').value});
    if (result.confirmation_required) {
      $('#auth-result').innerHTML = '<div class="notice info">Check your email to confirm your account. The link will return you to Scoutwise. Already confirmed? Choose “Sign in”.</div>';
      return;
    }
    state.authenticated = true; $('#signin').textContent = 'My research'; $('#auth-dialog').close();
    toast(state.authMode === 'signup' ? 'Account created.' : 'Welcome back.'); await loadWorkspace();
  } catch (error) { $('#auth-result').innerHTML = `<div class="notice warn">${esc(error.message)}</div>`; }
  finally { button.disabled = false; button.textContent = state.authMode === 'signup' ? 'Create account' : 'Sign in'; }
};
$('#create-plan').onclick = beginScan;
$('#save-draft').onclick = async () => { try { await flushDraft(); await loadWorkspace(); toast('Research draft saved. You can continue later.'); } catch (error) { toast(error.message); } };
$('#wizard-exit').onclick = async () => { try { await flushDraft(); await loadWorkspace(); } catch (error) { toast(error.message); } };
$('#detail-back').onclick = () => loadWorkspace();
$('#edit-plan').onclick = async () => {
  try { const data = await api(`/api/plans/${state.projectId}`); restorePlanIntoWizard(data.plan); }
  catch (error) { toast(error.message); }
};
$('#detail-connect-apify').onclick = () => $('#apify-dialog').showModal();
$('#run-plan').onclick = async () => {
  if (!state.projectId) return;
  if (!state.apifyConnected) { state.retryRun = true; $('#apify-dialog').showModal(); return; }
  try {
    if (!state.scanKey) state.scanKey = crypto.randomUUID();
    const result = await api(`/api/plans/${state.projectId}/scans`, {idempotency_key:state.scanKey});
    state.scanKey = null; toast(result.started ? `${result.started} Apify actor job${result.started === 1 ? '' : 's'} started.` : 'Apify could not start any actor jobs. Check the saved run details.');
    await openPlan(state.projectId);
  } catch (error) {
    toast(error.message);
    if (error.message.toLowerCase().includes('connect your apify')) { state.retryRun = true; $('#apify-dialog').showModal(); }
  }
};
$('#connect-apify').onclick = () => $('#apify-dialog').showModal();
$('#apify-form').onsubmit = connectApify;
$('#apify-close').onclick = () => $('#apify-dialog').close();
$('#apify-cancel').onclick = () => $('#apify-dialog').close();
boot();
