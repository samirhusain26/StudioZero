/**
 * StudioZero — Vanilla JS SPA
 *
 * Views: dashboard | setup | pipeline | finals
 * All communication via REST + WebSocket.
 */

const API = '';
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const main = () => document.getElementById('main');

// Pipeline step definitions (must match animation_pipeline.py)
const PRE_PROD_STEPS = ['writer', 'screenwriter', 'casting', 'world_builder'];
const EPISODE_STEPS  = ['director', 'scene_generator', 'editor'];
const STEP_LABELS    = {
  writer:          'Writer',
  screenwriter:    'Screenwriter',
  casting:         'Casting',
  world_builder:   'World Builder',
  director:        'Director',
  scene_generator: 'Scene Generator',
  editor:          'Editor',
};

// ── Router ──────────────────────────────────────────────────────────────────

const router = {
  go(view, data) {
    window._viewData = data;
    switch (view) {
      case 'dashboard': renderDashboard(); break;
      case 'setup':     renderSetup();     break;
      case 'pipeline':  renderPipeline(data); break;
      case 'finals':    renderFinals();    break;
      case 'settings':  renderSettings();  break;
      default:          renderDashboard();
    }
  }
};

// ── API helpers ──────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Status badge helper ──────────────────────────────────────────────────────

function statusClass(status) {
  return ({
    completed:    'bg-green-900 text-green-300',
    error:        'bg-red-900 text-red-300',
    running:      'bg-yellow-900 text-yellow-300',
    paused:       'bg-blue-900 text-blue-300',
    scene_failed: 'bg-orange-900 text-orange-300',
  })[status] || 'bg-gray-800 text-gray-400';
}

// ── Dashboard ────────────────────────────────────────────────────────────────

async function renderDashboard() {
  $('#header-subtitle').textContent = '';
  main().innerHTML = `
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-semibold">Projects</h2>
      <button onclick="router.go('setup')"
        class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
        + New Project
      </button>
    </div>
    <div id="project-list" class="text-gray-400 text-sm">Loading...</div>
  `;

  try {
    const projects = await api('GET', '/api/projects');
    const list = document.getElementById('project-list');
    if (!projects.length) {
      list.innerHTML = '<p class="text-gray-500 mt-8 text-center">No projects yet. Create one to get started.</p>';
      return;
    }
    list.innerHTML = projects.map(p => `
      <div class="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-3 flex items-center justify-between fade-in cursor-pointer hover:border-gray-700 transition"
           onclick="router.go('pipeline', '${p.id}')">
        <div class="min-w-0 flex-1">
          <div class="font-medium text-white">${esc(p.name)}</div>
          ${p.params?.brief ? `<div class="text-xs text-gray-400 mt-1 truncate max-w-lg" title="${esc(p.params.brief)}">${esc(p.params.brief)}</div>` : ''}
          <div class="text-xs text-gray-500 mt-1">
            ${p.mode}
            ${p.params?.num_episodes ? ` · ${p.params.num_episodes} ep` : ''}
            · ${new Date(p.created_at).toLocaleDateString()}
            ${p.current_step ? ` · step ${p.current_step}` : ''}
          </div>
        </div>
        <div class="flex gap-2 items-center flex-shrink-0 ml-4">
          ${p.status === 'running' ? '<span class="w-2 h-2 rounded-full bg-yellow-400 animate-pulse inline-block"></span>' : ''}
          <span class="inline-block px-2 py-0.5 rounded text-xs font-medium ${statusClass(p.status)}">${p.status}</span>
          <button onclick="event.stopPropagation(); deleteProject('${p.id}')"
            class="text-gray-600 hover:text-red-400 text-xs px-2 py-1">Delete</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    document.getElementById('project-list').innerHTML = `<p class="text-red-400">Error: ${esc(e.message)}</p>`;
  }
}

async function deleteProject(id) {
  if (!confirm('Delete this project and all its files?')) return;
  try {
    await api('DELETE', `/api/projects/${id}`);
    renderDashboard();
  } catch (e) {
    alert(e.message);
  }
}

// ── Setup ────────────────────────────────────────────────────────────────────

let _setupMode = null;       // 'movie' | 'animation-series'
let _movieSource = 'manual'; // 'manual' | 'sheet'

function renderSetup() {
  _setupMode = null;
  _movieSource = 'manual';
  $('#header-subtitle').textContent = 'New Project';
  main().innerHTML = `
    <div class="max-w-lg mx-auto">
      <h2 class="text-xl font-semibold mb-5">What are we making?</h2>
      <div class="grid grid-cols-2 gap-4">
        <button onclick="selectMode('movie')" id="mode-card-movie"
          class="mode-card group bg-gray-900 border-2 border-gray-800 rounded-xl p-5 text-left hover:border-indigo-500/50 transition-all">
          <div class="text-2xl mb-2">🎬</div>
          <div class="font-semibold text-white mb-1">Movie Recap</div>
          <div class="text-xs text-gray-500 leading-relaxed">AI-narrated recap video with stock footage, TTS, and karaoke subtitles.</div>
        </button>
        <button onclick="selectMode('animation-series')" id="mode-card-animation-series"
          class="mode-card group bg-gray-900 border-2 border-gray-800 rounded-xl p-5 text-left hover:border-indigo-500/50 transition-all">
          <div class="text-2xl mb-2">✨</div>
          <div class="font-semibold text-white mb-1">Animation Series</div>
          <div class="text-xs text-gray-500 leading-relaxed">Original animated episodes with AI-generated scenes, voices, and editing.</div>
        </button>
      </div>
      <div id="setup-form" class="mt-6"></div>
    </div>
  `;
}

function selectMode(mode) {
  _setupMode = mode;
  // Highlight selected card
  $$('.mode-card').forEach(el => {
    el.classList.remove('border-indigo-500', 'bg-indigo-950/30');
    el.classList.add('border-gray-800');
  });
  const card = $(`#mode-card-${mode}`);
  card.classList.remove('border-gray-800');
  card.classList.add('border-indigo-500', 'bg-indigo-950/30');

  if (mode === 'movie') renderMovieForm();
  else renderAnimationForm();
}

function renderMovieForm() {
  _movieSource = 'manual';
  $('#setup-form').innerHTML = `
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-6 fade-in">
      <label class="block text-sm font-medium text-gray-400 mb-3">Source</label>
      <div class="flex gap-3 mb-5">
        <button onclick="setMovieSource('manual')" id="src-manual"
          class="flex-1 px-4 py-3 rounded-lg border-2 text-sm font-medium transition-all
                 border-indigo-500 bg-indigo-950/30 text-white">
          <div class="font-medium mb-0.5">Enter Movie Name</div>
          <div class="text-xs text-gray-400 font-normal">Type a title or story idea</div>
        </button>
        <button onclick="setMovieSource('sheet')" id="src-sheet"
          class="flex-1 px-4 py-3 rounded-lg border-2 text-sm font-medium transition-all
                 border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600">
          <div class="font-medium mb-0.5">From Google Sheet</div>
          <div class="text-xs text-gray-500 font-normal">Pick up next pending movie</div>
        </button>
      </div>

      <div id="movie-source-fields"></div>

      <div id="s-error" class="text-red-400 text-sm mb-3 hidden"></div>
      <div class="flex gap-3 mt-4">
        <button onclick="router.go('dashboard')"
          class="px-4 py-2 rounded-lg text-sm border border-gray-700 text-gray-400 hover:text-white transition">Cancel</button>
        <button onclick="submitCreate()"
          class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">Create</button>
      </div>
    </div>
  `;
  renderMovieSourceFields();
}

function setMovieSource(src) {
  _movieSource = src;
  // Toggle button styles
  const manual = $('#src-manual');
  const sheet  = $('#src-sheet');
  if (src === 'manual') {
    manual.className = manual.className.replace('border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600',
      'border-indigo-500 bg-indigo-950/30 text-white');
    sheet.className = sheet.className.replace('border-indigo-500 bg-indigo-950/30 text-white',
      'border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600');
  } else {
    sheet.className = sheet.className.replace('border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600',
      'border-indigo-500 bg-indigo-950/30 text-white');
    manual.className = manual.className.replace('border-indigo-500 bg-indigo-950/30 text-white',
      'border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600');
  }
  renderMovieSourceFields();
}

function renderMovieSourceFields() {
  const container = $('#movie-source-fields');
  if (_movieSource === 'manual') {
    container.innerHTML = `
      <label class="block text-sm font-medium text-gray-400 mb-1">Movie Name</label>
      <input id="s-name" type="text" placeholder="e.g. Inception, The Matrix, Interstellar..."
        class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white mb-1 focus:outline-none focus:border-indigo-500" />
      <p class="text-xs text-gray-500 mb-3">Enter a movie title or a story idea. Unrecognizable input gets a random story.</p>
    `;
  } else {
    container.innerHTML = `
      <div class="px-4 py-3 bg-gray-800/50 border border-gray-700/50 rounded-lg">
        <p class="text-sm text-gray-300 mb-1">Next pending movie will be fetched from your Google Sheet.</p>
        <p class="text-xs text-gray-500">Configure the sheet URL in <a onclick="router.go('settings')" class="text-indigo-400 hover:text-indigo-300 cursor-pointer">Settings</a>.</p>
      </div>
    `;
  }
}

function renderAnimationForm() {
  $('#setup-form').innerHTML = `
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-6 fade-in">
      <div class="flex items-center justify-between mb-1">
        <label class="block text-sm font-medium text-gray-400">Project Name</label>
        <button onclick="generateRandomIdea()" id="btn-random"
          class="text-xs px-3 py-1 rounded-lg border border-gray-700 text-gray-400 hover:text-indigo-300 hover:border-indigo-500/50 transition-all">
          Surprise me
        </button>
      </div>
      <input id="s-name" type="text" placeholder="e.g. Kitchen Wars, The Last Kettle..."
        class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white mb-4 focus:outline-none focus:border-indigo-500" />

      <label class="block text-sm font-medium text-gray-400 mb-1">Story Brief</label>
      <textarea id="s-brief" rows="3" placeholder="A brave teapot leads a rebellion against the tyrannical blender who controls the kitchen..."
        class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white mb-1 focus:outline-none focus:border-indigo-500"></textarea>
      <p class="text-xs text-gray-500 mb-4">1-3 sentences. The Writer agent expands this into a full story, characters, and world.</p>

      <label class="block text-sm font-medium text-gray-400 mb-1">Number of Episodes</label>
      <input id="s-episodes" type="number" value="1" min="1" max="10"
        class="w-24 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white mb-1 focus:outline-none focus:border-indigo-500" />
      <p class="text-xs text-gray-500 mb-4">Each episode = 4-8 Veo scenes generated sequentially.</p>

      <div id="s-error" class="text-red-400 text-sm mb-3 hidden"></div>
      <div class="flex gap-3 mt-4">
        <button onclick="router.go('dashboard')"
          class="px-4 py-2 rounded-lg text-sm border border-gray-700 text-gray-400 hover:text-white transition">Cancel</button>
        <button onclick="submitCreate()"
          class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">Create</button>
      </div>
    </div>
  `;
}

async function generateRandomIdea() {
  const btn = $('#btn-random');
  const origText = btn.textContent;
  btn.textContent = 'Thinking...';
  btn.disabled = true;
  btn.classList.add('opacity-50');
  try {
    const data = await api('GET', '/api/generate-random-idea');
    if (data.name) $('#s-name').value = data.name;
    if (data.brief) $('#s-brief').value = data.brief;
  } catch (e) {
    const errEl = $('#s-error');
    if (errEl) { errEl.textContent = e.message; errEl.classList.remove('hidden'); }
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
    btn.classList.remove('opacity-50');
  }
}

async function submitCreate() {
  const mode = _setupMode;
  const errEl = $('#s-error');
  if (!errEl) return;
  errEl.classList.add('hidden');

  if (mode === 'movie' && _movieSource === 'sheet') {
    // Fetch next pending from sheet
    try {
      const result = await api('POST', '/api/projects/from-sheet');
      router.go('pipeline', result.id);
    } catch (e) {
      errEl.textContent = e.message;
      errEl.classList.remove('hidden');
    }
    return;
  }

  const name = $('#s-name')?.value?.trim();
  if (!name) { errEl.textContent = 'Name is required'; errEl.classList.remove('hidden'); return; }

  const params = {};
  if (mode === 'animation-series') {
    params.project_title = name;
    params.brief = $('#s-brief')?.value?.trim() || '';
    params.num_episodes = parseInt($('#s-episodes')?.value || '1');
  }

  try {
    const project = await api('POST', '/api/projects', { name, mode, params });
    router.go('pipeline', project.id);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  }
}

// ── Pipeline View ────────────────────────────────────────────────────────────

let _ws               = null;
let _railState        = null;
let _lastActivity     = null;
let _activityTimer    = null;
let _logFilter        = 'all';
let _currentProjectId = null;
let _terminalReceived = false; // scene_failed or error already rendered — skip done re-render

async function renderPipeline(projectId) {
  if (_ws) { _ws.close(); _ws = null; }
  if (_activityTimer) { clearInterval(_activityTimer); _activityTimer = null; }
  _logFilter = 'all';
  _currentProjectId = projectId;

  const project      = await api('GET', `/api/projects/${projectId}`);
  const numEpisodes  = project.params?.num_episodes || 1;
  const isAnimSeries = project.mode === 'animation-series';

  // Load persisted pipeline state for the step rail
  let pipelineState = {};
  if (isAnimSeries) {
    try { pipelineState = await api('GET', `/api/projects/${projectId}/state`); } catch {}
  }
  _railState = isAnimSeries ? buildRailState(pipelineState, numEpisodes) : null;

  $('#header-subtitle').textContent = project.name;

  main().innerHTML = `
    <div class="flex gap-3 mb-2 items-center flex-wrap">
      <button onclick="router.go('dashboard')" class="text-gray-500 hover:text-white text-sm">← Back</button>
      <h2 class="text-xl font-semibold flex-1 min-w-0 truncate">${esc(project.name)}</h2>
      <span id="status-badge" class="text-xs px-2 py-0.5 rounded flex-shrink-0 ${statusClass(project.status)}">${project.status}</span>
      ${project.status === 'running' ? '<span class="w-2 h-2 rounded-full bg-yellow-400 animate-pulse flex-shrink-0 inline-block"></span>' : ''}
      <span id="last-activity" class="text-xs text-gray-600 flex-shrink-0"></span>
    </div>
    ${project.params?.brief ? `<p class="text-sm text-gray-400 mb-4 italic">${esc(project.params.brief)}</p>` : ''}
    ${project.error ? `<div class="mb-4 px-4 py-3 rounded-lg bg-red-950 border border-red-800 text-red-300 text-sm"><span class="font-medium">Error:</span> ${esc(project.error)}</div>` : ''}

    <!-- Controls bar -->
    <div id="controls" class="mb-4 flex gap-2 flex-wrap items-center"></div>

    <!-- Review Gate (hidden by default) -->
    <div id="review-gate" class="hidden mb-4 bg-gray-900 border border-indigo-800 rounded-xl p-5">
      <h3 class="text-lg font-semibold text-indigo-300 mb-2">Review Required</h3>
      <p id="review-message" class="text-sm text-gray-400 mb-3"></p>
      <div id="review-content"></div>
      <div class="flex gap-3 mt-4">
        <button onclick="approveAndContinue('${projectId}')"
          class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
          Approve &amp; Continue
        </button>
      </div>
    </div>

    <!-- Two-column layout: left = progress + logs, right = media -->
    <div class="flex gap-4" style="align-items: flex-start;">

      <!-- Left column -->
      <div class="flex-1 min-w-0 space-y-4">

        ${isAnimSeries ? stepRailHTML(numEpisodes) : ''}

        <!-- Log panel -->
        <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div class="px-4 py-2 border-b border-gray-800 flex items-center justify-between">
            <span class="text-xs text-gray-500 font-medium">Pipeline Logs</span>
            <div class="flex gap-1">
              <button onclick="setLogFilter('all')"    id="filter-all"    class="log-filter active-filter   text-xs px-2 py-0.5 rounded">All</button>
              <button onclick="setLogFilter('steps')"  id="filter-steps"  class="log-filter inactive-filter text-xs px-2 py-0.5 rounded">Steps</button>
              <button onclick="setLogFilter('errors')" id="filter-errors" class="log-filter inactive-filter text-xs px-2 py-0.5 rounded">Errors</button>
            </div>
          </div>
          <div id="log-panel" class="p-3 max-h-96 overflow-y-auto space-y-0.5"></div>
        </div>
      </div>

      <!-- Right column: project info -->
      <div class="w-72 flex-shrink-0 space-y-3">
        <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div class="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">Project Info</div>
          <div id="meta-panel" class="p-4 space-y-3 text-xs">
            ${_buildMetaPanel(project, pipelineState)}
          </div>
        </div>
        <a onclick="router.go('finals')" href="#"
          class="block text-center text-xs text-indigo-500 hover:text-indigo-400 transition py-1">
          View Finals Library →
        </a>
      </div>
    </div>
  `;

  // Inject filter button styles (can't use Tailwind @apply in CDN mode easily)
  applyFilterStyles();

  // Render controls for current status
  renderControls(project, projectId);

  // No longer restoring media sidebar — replaced by project info panel

  // Restore scene-failed dialog if applicable
  if (project.status === 'scene_failed' && project.step_data?.failed_scene) {
    showSceneFailedDialog({ data: project.step_data.failed_scene }, projectId);
  }

  // Reconnect WS if already running (e.g. page refresh mid-run)
  if (project.status === 'running') {
    connectWs(projectId);
    startActivityTimer();
  }

  // Apply initial rail state from loaded pipeline_state.json
  if (_railState) applyRailStateToDOM(_railState);
}

// ── Project Meta Panel ──────────────────────────────────────────────────────

function _buildMetaPanel(project, pipelineState) {
  const rows = [];

  rows.push(`<div><span class="text-gray-500">Mode</span><div class="text-gray-300 mt-0.5">${esc(project.mode)}</div></div>`);

  if (project.params?.num_episodes) {
    rows.push(`<div><span class="text-gray-500">Episodes</span><div class="text-gray-300 mt-0.5">${project.params.num_episodes}</div></div>`);
  }

  rows.push(`<div><span class="text-gray-500">Created</span><div class="text-gray-300 mt-0.5">${new Date(project.created_at).toLocaleString()}</div></div>`);
  rows.push(`<div><span class="text-gray-500">Updated</span><div class="text-gray-300 mt-0.5">${new Date(project.updated_at).toLocaleString()}</div></div>`);

  // Count completed steps and total duration
  let completedSteps = 0;
  let totalSteps = 0;
  let totalDurationMs = 0;

  if (pipelineState.series_steps) {
    for (const [, s] of Object.entries(pipelineState.series_steps)) {
      totalSteps++;
      if (s.completed) {
        completedSteps++;
        if (s.started_at && s.completed_at) {
          totalDurationMs += new Date(s.completed_at) - new Date(s.started_at);
        }
      }
    }
  }
  if (pipelineState.episodes) {
    for (const [, ep] of Object.entries(pipelineState.episodes)) {
      for (const [, s] of Object.entries(ep.steps || {})) {
        totalSteps++;
        if (s.completed) {
          completedSteps++;
          if (s.started_at && s.completed_at) {
            totalDurationMs += new Date(s.completed_at) - new Date(s.started_at);
          }
        }
      }
    }
  }

  if (totalSteps > 0) {
    rows.push(`<div><span class="text-gray-500">Progress</span><div class="text-gray-300 mt-0.5">${completedSteps}/${totalSteps} steps</div></div>`);
  }
  if (totalDurationMs > 0) {
    rows.push(`<div><span class="text-gray-500">Total Time</span><div class="text-gray-300 mt-0.5">${fmtDuration(totalDurationMs)}</div></div>`);
  }

  // Count generated files
  let videoCount = 0;
  let imageCount = 0;
  if (pipelineState.series_steps) {
    for (const [, s] of Object.entries(pipelineState.series_steps)) {
      for (const p of (s.artifact_paths || [])) {
        if (p.endsWith('.mp4')) videoCount++;
        if (p.endsWith('.png') || p.endsWith('.jpg')) imageCount++;
      }
    }
  }
  if (pipelineState.episodes) {
    for (const [, ep] of Object.entries(pipelineState.episodes)) {
      for (const [, s] of Object.entries(ep.steps || {})) {
        for (const p of (s.artifact_paths || [])) {
          if (p.endsWith('.mp4')) videoCount++;
          if (p.endsWith('.png') || p.endsWith('.jpg')) imageCount++;
        }
      }
    }
  }
  if (videoCount || imageCount) {
    const parts = [];
    if (videoCount) parts.push(`${videoCount} video${videoCount > 1 ? 's' : ''}`);
    if (imageCount) parts.push(`${imageCount} image${imageCount > 1 ? 's' : ''}`);
    rows.push(`<div><span class="text-gray-500">Generated</span><div class="text-gray-300 mt-0.5">${parts.join(', ')}</div></div>`);
  }

  return rows.join('');
}

function fmtDuration(ms) {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// ── Step Rail ────────────────────────────────────────────────────────────────

function buildRailState(pipelineState, numEpisodes) {
  const pre = {};
  PRE_PROD_STEPS.forEach(s => { pre[s] = { status: 'pending' }; });
  const eps = {};
  for (let i = 1; i <= numEpisodes; i++) {
    eps[i] = {};
    EPISODE_STEPS.forEach(s => { eps[i][s] = { status: 'pending' }; });
  }

  function _stepInfo(s) {
    const status = s.completed ? 'done' : s.error ? 'error' : s.started_at ? 'running' : 'pending';
    let duration = null;
    if (s.started_at && s.completed_at) {
      duration = Math.round((new Date(s.completed_at) - new Date(s.started_at)) / 1000);
    }
    return { status, duration, error: s.error || null };
  }

  if (pipelineState.series_steps) {
    for (const step of PRE_PROD_STEPS) {
      const s = pipelineState.series_steps[step];
      if (!s) continue;
      pre[step] = _stepInfo(s);
    }
  }

  if (pipelineState.episodes) {
    for (const [epNumStr, epState] of Object.entries(pipelineState.episodes)) {
      const epNum = parseInt(epNumStr);
      if (!eps[epNum]) eps[epNum] = {};
      for (const step of EPISODE_STEPS) {
        const s = epState.steps?.[step];
        if (!s) continue;
        eps[epNum][step] = _stepInfo(s);
      }
    }
  }

  return { preProduction: pre, episodes: eps, numEpisodes };
}

function applyRailStateToDOM(railState) {
  for (const [step, info] of Object.entries(railState.preProduction)) {
    setStepDom('preprod', step, info.status, info);
  }
  for (const [epNumStr, steps] of Object.entries(railState.episodes)) {
    const epNum = parseInt(epNumStr);
    for (const [step, info] of Object.entries(steps)) {
      setStepDom(`ep${epNum}`, step, info.status, info);
    }
    refreshEpIcon(epNum);
  }
}

function stepRailHTML(numEpisodes) {
  const preRows = PRE_PROD_STEPS.map(s => stepRowHTML('preprod', s)).join('');
  const epSections = Array.from({ length: numEpisodes }, (_, i) => i + 1).map(epNum => `
    <div class="border border-gray-800 rounded-lg overflow-hidden">
      <div class="px-3 py-1.5 bg-gray-900 flex items-center gap-2 text-xs font-medium text-gray-400">
        <span id="ep-icon-${epNum}" class="w-2.5 h-2.5 rounded-full bg-gray-700 flex-shrink-0"></span>
        Episode ${epNum}
        <span id="ep-label-${epNum}" class="ml-auto text-gray-700 font-normal"></span>
      </div>
      <div class="px-3 pb-2 pt-1 space-y-1">
        ${EPISODE_STEPS.map(s => stepRowHTML(`ep${epNum}`, s)).join('')}
      </div>
    </div>
  `).join('');

  return `
    <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div class="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">Pipeline Progress</div>
      <div class="p-4 space-y-4">
        <div>
          <div class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Phase 1 — Pre-Production</div>
          <div class="space-y-1">${preRows}</div>
        </div>
        <div>
          <div class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Phase 2 — Production</div>
          <div class="space-y-2">${epSections}</div>
        </div>
      </div>
    </div>
  `;
}

function stepRowHTML(prefix, stepName) {
  return `
    <div id="rail-${prefix}-${stepName}" class="step-row flex flex-wrap items-center gap-2 text-xs py-0.5">
      <span class="step-dot w-2 h-2 rounded-full bg-gray-700 flex-shrink-0"></span>
      <span class="step-label text-gray-600">${STEP_LABELS[stepName] || stepName}</span>
      <span class="step-status ml-auto text-gray-700"></span>
    </div>
  `;
}

const _DOT_CLASSES = {
  pending: 'bg-gray-700',
  running: 'bg-yellow-400 animate-pulse',
  done:    'bg-green-500',
  error:   'bg-red-500',
};
const _LABEL_CLASSES = {
  pending: 'text-gray-600',
  running: 'text-yellow-300 font-medium',
  done:    'text-gray-300',
  error:   'text-red-400',
};
const _STATUS_TEXT = { pending: '', running: 'running…', done: '✓', error: '✗' };
const _STATUS_CLASSES = {
  pending: 'text-gray-700',
  running: 'text-yellow-500',
  done:    'text-green-600',
  error:   'text-red-500',
};

function setStepDom(prefix, stepName, status, info) {
  const el = document.getElementById(`rail-${prefix}-${stepName}`);
  if (!el) return;
  el.querySelector('.step-dot').className   = `step-dot w-2 h-2 rounded-full flex-shrink-0 ${_DOT_CLASSES[status] || _DOT_CLASSES.pending}`;
  el.querySelector('.step-label').className = `step-label ${_LABEL_CLASSES[status] || _LABEL_CLASSES.pending}`;
  const st = el.querySelector('.step-status');

  // Build status text with duration
  let statusText = _STATUS_TEXT[status] || '';
  if (status === 'done' && info?.duration != null) {
    statusText = `${fmtElapsed(info.duration)}`;
  }
  st.textContent = statusText;
  st.className   = `step-status ml-auto ${_STATUS_CLASSES[status] || _STATUS_CLASSES.pending}`;

  // Remove existing error tooltip
  el.querySelector('.step-error')?.remove();

  // Show error details inline
  if (status === 'error' && info?.error) {
    const errDiv = document.createElement('div');
    errDiv.className = 'step-error text-red-400 text-xs mt-0.5 pl-4 truncate';
    errDiv.textContent = info.error;
    errDiv.title = info.error;
    el.appendChild(errDiv);
  }

  // Make completed steps clickable to open artifact modal
  if (status === 'done') {
    el.style.cursor = 'pointer';
    el.title = `Click to view ${STEP_LABELS[stepName] || stepName} output`;
    el.classList.add('hover:bg-gray-800', 'rounded', 'px-1', '-mx-1', 'transition');
    const epMatch = prefix.match(/^ep(\d+)$/);
    const epNum   = epMatch ? parseInt(epMatch[1]) : null;
    const pid     = _currentProjectId;
    el.onclick = () => openStepModal(pid, stepName, epNum);

    if (!el.querySelector('.view-hint')) {
      const hint = document.createElement('span');
      hint.className = 'view-hint text-gray-700 hover:text-indigo-400 text-xs ml-1 transition';
      hint.textContent = '↗';
      el.querySelector('.step-status')?.after(hint);
    }
  } else {
    el.style.cursor = '';
    el.onclick = null;
  }
}

function refreshEpIcon(epNum) {
  if (!_railState?.episodes?.[epNum]) return;
  const vals = Object.values(_railState.episodes[epNum]).map(v => v.status || v);
  const icon  = document.getElementById(`ep-icon-${epNum}`);
  const label = document.getElementById(`ep-label-${epNum}`);
  if (!icon) return;

  let cls, txt;
  if (vals.every(s => s === 'done'))        { cls = 'bg-green-500';  txt = 'Complete'; }
  else if (vals.some(s => s === 'error'))   { cls = 'bg-red-500';    txt = 'Error'; }
  else if (vals.some(s => s === 'running')) { cls = 'bg-yellow-400 animate-pulse'; txt = 'In Progress'; }
  else if (vals.some(s => s === 'done'))    { cls = 'bg-indigo-500'; txt = ''; }
  else                                      { cls = 'bg-gray-700';   txt = ''; }

  icon.className  = `w-2.5 h-2.5 rounded-full flex-shrink-0 ${cls}`;
  if (label) label.textContent = txt;
}

// Parse a WS status message to extract step name, phase, and status
function parseStepInfo(message) {
  // Episode step: [ep1/director] Starting... or Complete...
  const epMatch = message.match(/\[ep(\d+)\/([\w_]+)\]\s+(\S+)/);
  if (epMatch) {
    const [, epNum, step, word] = epMatch;
    const status = word.startsWith('Starting') ? 'running'
                 : word.startsWith('Complete') ? 'done'
                 : word.startsWith('Failed')   ? 'error'
                 : word.startsWith('Already')  ? 'done'   // "Already completed"
                 : null;
    return status ? { phase: `ep${epNum}`, step, status, epNum: parseInt(epNum) } : null;
  }

  // Pre-production step: [writer] Starting...
  const preMatch = message.match(/\[([\w_]+)\]\s+(\S+)/);
  if (preMatch) {
    const [, step, word] = preMatch;
    if (!PRE_PROD_STEPS.includes(step)) return null;
    const status = word.startsWith('Starting') ? 'running'
                 : word.startsWith('Complete') ? 'done'
                 : word.startsWith('Failed')   ? 'error'
                 : word.startsWith('Already')  ? 'done'
                 : null;
    return status ? { phase: 'preprod', step, status, epNum: null } : null;
  }

  return null;
}

// ── Controls ────────────────────────────────────────────────────────────────

function renderControls(project, projectId) {
  const controls = document.getElementById('controls');
  if (!controls) return;

  if (['created', 'paused', 'error', 'scene_failed'].includes(project.status)) {
    controls.innerHTML = `
      <button onclick="startPipeline('${projectId}')"
        class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
        ${project.status === 'created' ? 'Start Pipeline' : 'Continue Pipeline'}
      </button>
    `;
  } else if (project.status === 'running') {
    controls.innerHTML = runningControlsHTML(projectId);
  } else if (project.status === 'completed') {
    controls.innerHTML = `
      <button onclick="router.go('finals')"
        class="bg-green-700 hover:bg-green-800 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
        View Finals Library
      </button>
    `;
  }
}

function runningControlsHTML(projectId) {
  return `
    <button onclick="pausePipeline('${projectId}')"
      class="bg-yellow-700 hover:bg-yellow-800 text-white px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-1.5">
      <span>⏸</span> Pause
    </button>
    <div id="veo-badge" class="hidden items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-950 border border-indigo-700 text-indigo-300 text-xs font-mono">
      <span class="w-2 h-2 rounded-full bg-indigo-400 animate-pulse inline-block"></span>
      <span id="veo-badge-text"></span>
    </div>
  `;
}

async function startPipeline(projectId) {
  document.getElementById('review-gate')?.classList.add('hidden');
  const controls = document.getElementById('controls');
  if (controls) controls.innerHTML = runningControlsHTML(projectId);
  setBadge('running');

  try {
    await api('POST', `/api/projects/${projectId}/run`);
  } catch (e) {
    appendLog(`Error starting pipeline: ${e.message}`, 'error');
    return;
  }

  connectWs(projectId);
  startActivityTimer();
}

async function pausePipeline(projectId) {
  const controls = document.getElementById('controls');
  if (controls) controls.innerHTML = `<span class="text-gray-400 text-sm">Pausing…</span>`;

  try {
    await api('POST', `/api/projects/${projectId}/pause`);
    appendLog(`[${ts()}] Pipeline paused — progress is saved.`, 'step');
    setBadge('paused');
    if (controls) controls.innerHTML = `
      <button onclick="startPipeline('${projectId}')"
        class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
        Continue Pipeline
      </button>
    `;
    if (_activityTimer) { clearInterval(_activityTimer); _activityTimer = null; }
  } catch (e) {
    appendLog(`Pause failed: ${e.message}`, 'error');
  }
}

function setBadge(status) {
  const badge = document.getElementById('status-badge');
  if (badge) { badge.textContent = status; badge.className = `text-xs px-2 py-0.5 rounded flex-shrink-0 ${statusClass(status)}`; }
}

// ── WebSocket ────────────────────────────────────────────────────────────────

function connectWs(projectId) {
  if (_ws) _ws.close();
  _terminalReceived = false;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  _ws = new WebSocket(`${proto}://${location.host}/ws/${projectId}`);
  _ws.onmessage = (evt) => {
    _lastActivity = Date.now();
    handleWsMessage(JSON.parse(evt.data), projectId);
  };
  _ws.onclose = () => { _ws = null; };
  _ws.onerror = () => appendLog('WebSocket error', 'error');
}

function startActivityTimer() {
  if (_activityTimer) clearInterval(_activityTimer);
  _lastActivity = Date.now();
  _activityTimer = setInterval(() => {
    const el = document.getElementById('last-activity');
    if (!el) { clearInterval(_activityTimer); return; }
    const s = Math.floor((Date.now() - _lastActivity) / 1000);
    el.textContent = s < 5 ? '' : `Last update: ${s}s ago`;
  }, 1000);
}

function handleWsMessage(msg, projectId) {
  switch (msg.type) {

    case 'status': {
      const isErr  = msg.is_error;
      const parsed = parseStepInfo(msg.message);
      const logType = isErr ? 'error' : parsed ? 'step' : 'normal';
      appendLog(`[${ts()}] ${msg.message}`, logType);

      // Update step rail
      if (_railState && parsed) {
        const { phase, step, status, epNum } = parsed;
        const info = { status, duration: null, error: null };
        if (phase === 'preprod') {
          _railState.preProduction[step] = info;
        } else if (epNum && _railState.episodes[epNum]) {
          _railState.episodes[epNum][step] = info;
          refreshEpIcon(epNum);
        }
        setStepDom(phase, step, status, info);
      }

      // Episode video ready — no longer shown in sidebar, visible in finals library
      break;
    }

    case 'paused':
      appendLog(`[${ts()}] Paused at step ${msg.step} — review required.`, 'step');
      showReviewGate(msg, projectId);
      break;

    case 'completed':
      clearVeo();
      appendLog(`[${ts()}] Pipeline completed!`, 'step');
      if (_activityTimer) { clearInterval(_activityTimer); _activityTimer = null; }
      setTimeout(() => renderPipeline(projectId), 500);
      break;

    case 'done':
      if (_activityTimer) { clearInterval(_activityTimer); _activityTimer = null; }
      // If scene_failed or error already rendered their UI, skip the full re-render
      // (re-rendering wipes the log panel and the scene-failed dialog).
      if (!_terminalReceived) {
        setTimeout(() => renderPipeline(projectId), 500);
      }
      break;

    case 'scene_failed':
      _terminalReceived = true;
      clearVeo();
      setBadge('scene_failed');
      if (_activityTimer) { clearInterval(_activityTimer); _activityTimer = null; }
      appendLog(`[${ts()}] Scene ${msg.data?.scene_id} failed — action required.`, 'error');
      showSceneFailedDialog(msg, projectId);
      {
        const controls = document.getElementById('controls');
        if (controls) controls.innerHTML = `
          <button onclick="startPipeline('${projectId}')"
            class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
            Continue Pipeline
          </button>
        `;
      }
      break;

    case 'error':
      _terminalReceived = true;
      clearVeo();
      setBadge('error');
      if (_activityTimer) { clearInterval(_activityTimer); _activityTimer = null; }
      appendLog(`[${ts()}] Pipeline error: ${msg.message}`, 'error');
      {
        const controls = document.getElementById('controls');
        if (controls) controls.innerHTML = `
          <button onclick="startPipeline('${projectId}')"
            class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
            Retry
          </button>
        `;
      }
      break;

    case 'veo_polling':
      updateVeoBadge(msg.scene_id, msg.elapsed);
      updateVeoLogIndicator(msg.scene_id, msg.elapsed);
      break;

    case 'info':
      appendLog(`[${ts()}] ${msg.message}`, 'normal');
      break;
  }
}

// ── Veo polling indicators ───────────────────────────────────────────────────

function updateVeoBadge(sceneId, elapsed) {
  const badge = document.getElementById('veo-badge');
  const text  = document.getElementById('veo-badge-text');
  if (!badge || !text) return;
  text.textContent = `Veo scene ${sceneId} — ${fmtElapsed(elapsed)}`;
  badge.classList.remove('hidden');
  badge.classList.add('flex');
}

function updateVeoLogIndicator(sceneId, elapsed) {
  let el = document.getElementById('veo-log-indicator');
  if (!el) {
    el = document.createElement('div');
    el.id = 'veo-log-indicator';
    el.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-950 border border-indigo-700 text-indigo-300 text-xs font-mono mt-1';
    el.innerHTML = `<span class="w-2 h-2 rounded-full bg-indigo-400 animate-pulse inline-block"></span><span id="veo-log-text"></span>`;
    const panel = document.getElementById('log-panel');
    if (panel) panel.appendChild(el);
  }
  document.getElementById('veo-log-text').textContent = `Veo generating scene ${sceneId} — polling (${fmtElapsed(elapsed)})`;
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearVeo() {
  const badge = document.getElementById('veo-badge');
  if (badge) { badge.classList.add('hidden'); badge.classList.remove('flex'); }
  document.getElementById('veo-log-indicator')?.remove();
}

function fmtElapsed(secs) {
  const m = Math.floor(secs / 60), s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ── Media Panel (removed — replaced by project info sidebar) ────────────────

// ── Review Gate ──────────────────────────────────────────────────────────────

function showReviewGate(msg, projectId) {
  const gate = document.getElementById('review-gate');
  gate.classList.remove('hidden');
  document.getElementById('review-message').textContent =
    `Step ${msg.step} complete. Review the output below and approve to continue.`;

  const content = document.getElementById('review-content');
  const data = msg.data || {};

  if (data.script) {
    content.innerHTML = `
      <label class="block text-sm font-medium text-gray-400 mb-1">Generated Script (editable)</label>
      <textarea id="edit-script" rows="16"
        class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-indigo-500"
      >${esc(JSON.stringify(data.script, null, 2))}</textarea>
    `;
  } else {
    content.innerHTML = `
      <pre class="bg-gray-800 rounded-lg p-3 text-xs text-gray-300 max-h-64 overflow-auto">${esc(JSON.stringify(data, null, 2))}</pre>
    `;
  }

  const controls = document.getElementById('controls');
  if (controls) controls.innerHTML = '';
}

async function approveAndContinue(projectId) {
  const editArea = document.getElementById('edit-script');
  if (editArea) {
    try {
      const edited = JSON.parse(editArea.value);
      await api('PUT', `/api/projects/${projectId}/script`, { script: edited });
    } catch (e) {
      appendLog(`Invalid JSON in script edit: ${e.message}`, 'error');
      return;
    }
  }
  document.getElementById('review-gate').classList.add('hidden');
  startPipeline(projectId);
}

// ── Scene Failed Dialog ──────────────────────────────────────────────────────

function showSceneFailedDialog(msg, projectId) {
  const data    = msg.data || {};
  const sceneId = data.scene_id ?? '?';
  const epNum   = data.episode_number ?? '?';
  const prompt  = data.veo_prompt || '';
  const dialogId = `scene-fail-dialog-${sceneId}`;

  const logEl = document.getElementById('log-panel');
  if (!logEl || document.getElementById(dialogId)) return;

  const div = document.createElement('div');
  div.id = dialogId;
  div.className = 'mt-3 border border-red-800 rounded-lg p-4 bg-gray-950 fade-in';
  div.innerHTML = `
    <p class="text-red-400 font-semibold mb-1 text-sm">Episode ${epNum}, Scene ${sceneId} — action required</p>
    <div class="mb-3">
      <label class="block text-xs text-gray-500 mb-1">Veo Prompt (${prompt.trim().split(/\s+/).length} words)</label>
      <textarea id="scene-prompt-edit-${sceneId}" rows="5"
        class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 font-mono focus:outline-none focus:border-indigo-500"
      >${esc(prompt)}</textarea>
    </div>
    <p id="scene-edit-err-${sceneId}" class="text-red-400 text-xs mb-2 hidden"></p>
    <div class="flex gap-2 flex-wrap">
      <button onclick="retryScene('${projectId}', ${JSON.stringify(sceneId)}, 'retry')"
        class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs px-3 py-1.5 rounded transition">
        Retry same prompt
      </button>
      <button onclick="retryScene('${projectId}', ${JSON.stringify(sceneId)}, 'edit')"
        class="bg-yellow-600 hover:bg-yellow-700 text-white text-xs px-3 py-1.5 rounded transition">
        Save edits &amp; retry
      </button>
      <button onclick="retryScene('${projectId}', ${JSON.stringify(sceneId)}, 'skip')"
        class="bg-gray-700 hover:bg-gray-600 text-white text-xs px-3 py-1.5 rounded transition">
        Skip scene
      </button>
    </div>
  `;
  logEl.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth' });

  const controls = document.getElementById('controls');
  if (controls) controls.innerHTML = '';
}

async function retryScene(projectId, sceneId, action) {
  const newPrompt = action === 'edit'
    ? (document.getElementById(`scene-prompt-edit-${sceneId}`)?.value?.trim() || '')
    : '';

  if (action === 'edit' && !newPrompt) {
    const errEl = document.getElementById(`scene-edit-err-${sceneId}`);
    if (errEl) { errEl.textContent = 'Prompt cannot be empty.'; errEl.classList.remove('hidden'); }
    return;
  }

  const dialogEl = document.getElementById(`scene-fail-dialog-${sceneId}`);
  if (dialogEl) dialogEl.innerHTML = `<p class="text-yellow-400 text-sm">Sending: ${action}…</p>`;

  try {
    await api('POST', `/api/projects/${projectId}/retry-scene`, { action, new_prompt: newPrompt });
    appendLog(`[${ts()}] Scene ${sceneId}: ${action} submitted — resuming…`, 'step');
    connectWs(projectId);
    startActivityTimer();
    // Restore pause button
    const controls = document.getElementById('controls');
    if (controls) controls.innerHTML = runningControlsHTML(projectId);
  } catch (e) {
    appendLog(`Failed to send retry action: ${e.message}`, 'error');
  }
}

// ── Finals Library ───────────────────────────────────────────────────────────

async function renderFinals() {
  $('#header-subtitle').textContent = 'Finals';
  main().innerHTML = `
    <div class="flex items-center gap-3 mb-6">
      <button onclick="router.go('dashboard')" class="text-gray-500 hover:text-white text-sm">← Back</button>
      <h2 class="text-2xl font-semibold">Finals Library</h2>
    </div>
    <div id="finals-grid" class="text-gray-400 text-sm">Loading…</div>
  `;

  try {
    const finals = await api('GET', '/api/finals');
    const grid = document.getElementById('finals-grid');

    if (!finals.length) {
      grid.innerHTML = `
        <div class="text-center mt-16 space-y-2">
          <p class="text-gray-500">No final videos yet.</p>
          <p class="text-gray-600 text-xs">Complete an animation series pipeline run — each episode is saved here automatically.</p>
        </div>
      `;
      return;
    }

    grid.innerHTML = `
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        ${finals.map(f => `
          <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden fade-in hover:border-gray-700 transition">
            <div class="bg-black" style="aspect-ratio: 16/9;">
              <video controls muted preload="metadata" class="w-full h-full object-contain">
                <source src="/api/finals/${encodeURIComponent(f.filename)}" type="video/mp4">
              </video>
            </div>
            <div class="p-3">
              <div class="font-medium text-sm text-white truncate" title="${esc(f.filename)}">${esc(f.filename)}</div>
              <div class="text-xs text-gray-500 mt-0.5">${f.size_mb} MB · ${new Date(f.created_at).toLocaleDateString()}</div>
              <a href="/api/finals/${encodeURIComponent(f.filename)}" download
                class="mt-2 flex items-center justify-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition border border-indigo-900 hover:border-indigo-700 rounded-lg py-1.5">
                ↓ Download
              </a>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    document.getElementById('finals-grid').innerHTML = `<p class="text-red-400">Error: ${esc(e.message)}</p>`;
  }
}

// ── Log panel ────────────────────────────────────────────────────────────────

function appendLog(text, type = 'normal') {
  const panel = document.getElementById('log-panel');
  if (!panel) return;

  const colorMap = { normal: 'text-gray-400', step: 'text-indigo-300', error: 'text-red-400' };
  const el = document.createElement('div');
  el.className  = `log-entry ${colorMap[type] || 'text-gray-400'} fade-in`;
  el.dataset.type = type;
  el.textContent  = text;

  applyFilterToEntry(el);
  panel.appendChild(el);
  panel.scrollTop = panel.scrollHeight;
}

function setLogFilter(filter) {
  _logFilter = filter;
  // Update button styles
  $$('.log-filter').forEach(btn => {
    const isActive = btn.id === `filter-${filter}`;
    btn.className = `log-filter ${isActive ? 'active-filter' : 'inactive-filter'} text-xs px-2 py-0.5 rounded`;
  });
  applyFilterStyles();
  // Re-apply to existing entries
  $$('#log-panel .log-entry').forEach(applyFilterToEntry);
}

function applyFilterToEntry(el) {
  if (_logFilter === 'all')    { el.style.display = ''; return; }
  if (_logFilter === 'errors') { el.style.display = el.dataset.type === 'error' ? '' : 'none'; return; }
  if (_logFilter === 'steps')  { el.style.display = el.dataset.type === 'step'  ? '' : 'none'; return; }
}

function applyFilterStyles() {
  // Inject inline style for active/inactive filter buttons since Tailwind CDN
  // doesn't support arbitrary dynamic class application reliably across re-renders
  document.querySelectorAll('.active-filter').forEach(btn => {
    btn.style.cssText = 'background:#374151; color:#d1d5db;';
  });
  document.querySelectorAll('.inactive-filter').forEach(btn => {
    btn.style.cssText = 'background:transparent; color:#6b7280;';
  });
}

// ── Step Artifact Modal ──────────────────────────────────────────────────────

function openStepModal(projectId, stepName, epNum) {
  // Build a full-screen modal overlay
  const existing = document.getElementById('step-modal');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'step-modal';
  overlay.className = 'fixed inset-0 z-50 flex items-start justify-center bg-black bg-opacity-75 p-4 overflow-y-auto';
  overlay.innerHTML = `
    <div class="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-3xl mt-8 mb-8 overflow-hidden shadow-2xl">
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <div>
          <h3 id="modal-title" class="text-lg font-semibold text-white"></h3>
          <p id="modal-subtitle" class="text-xs text-gray-500 mt-0.5"></p>
        </div>
        <button onclick="document.getElementById('step-modal').remove()"
          class="text-gray-500 hover:text-white text-xl leading-none px-2">✕</button>
      </div>
      <div id="modal-body" class="p-6">
        <div class="flex items-center gap-2 text-gray-500 text-sm">
          <span class="w-2 h-2 rounded-full bg-indigo-400 animate-pulse inline-block"></span>
          Loading artifacts…
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  // Close on backdrop click
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  const label = STEP_LABELS[stepName] || stepName;
  document.getElementById('modal-title').textContent = label;
  document.getElementById('modal-subtitle').textContent = epNum != null
    ? `Episode ${epNum} · ${stepName}`
    : `Pre-production step`;

  // Fetch artifacts
  const qs = epNum != null ? `?step=${stepName}&episode=${epNum}` : `?step=${stepName}`;
  api('GET', `/api/projects/${projectId}/step-artifacts${qs}`)
    .then(({ artifacts }) => renderModalArtifacts(artifacts, stepName, projectId))
    .catch(e => {
      document.getElementById('modal-body').innerHTML =
        `<p class="text-red-400 text-sm">Failed to load artifacts: ${esc(e.message)}</p>`;
    });
}

async function renderModalArtifacts(artifacts, stepName, projectId) {
  const body = document.getElementById('modal-body');
  if (!body) return;

  if (!artifacts.length) {
    body.innerHTML = '<p class="text-gray-500 text-sm">No artifacts found for this step.</p>';
    return;
  }

  // Separate by type
  const jsonFiles = artifacts.filter(a => a.ext === '.json');
  const imgFiles  = artifacts.filter(a => a.ext === '.png' || a.ext === '.jpg' || a.ext === '.jpeg');
  const vidFiles  = artifacts.filter(a => a.ext === '.mp4');

  let html = '';

  // ── JSON artifacts ─────────────────────────────────────────────────────────
  for (const artifact of jsonFiles) {
    try {
      const res = await fetch(artifact.url);
      const data = await res.json();
      html += `<div class="mb-6">${renderJsonArtifact(artifact.filename, data, stepName)}</div>`;
    } catch {
      html += `<p class="text-yellow-400 text-xs mb-4">Could not load ${esc(artifact.filename)}</p>`;
    }
  }

  // ── Image artifacts ────────────────────────────────────────────────────────
  if (imgFiles.length) {
    html += `<div class="mb-6">
      <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Reference Images (${imgFiles.length})
      </div>
      <div class="grid grid-cols-2 gap-3">
        ${imgFiles.map(img => `
          <div class="bg-gray-800 rounded-xl overflow-hidden">
            <img src="${img.url}" alt="${esc(img.filename)}" class="w-full object-cover" loading="lazy" />
            <div class="px-3 py-2 text-xs text-gray-500 truncate">${esc(img.filename)} · ${img.size_kb} KB</div>
          </div>
        `).join('')}
      </div>
    </div>`;
  }

  // ── Video artifacts ────────────────────────────────────────────────────────
  if (vidFiles.length) {
    html += `<div class="mb-6">
      <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Video Clips (${vidFiles.length})
      </div>
      <div class="space-y-3">
        ${vidFiles.map(vid => `
          <div class="bg-gray-800 rounded-xl overflow-hidden">
            <video controls muted preload="metadata" class="w-full" style="max-height: 280px;">
              <source src="${vid.url}" type="video/mp4">
            </video>
            <div class="px-3 py-2 text-xs text-gray-500">${esc(vid.filename)} · ${vid.size_kb} KB</div>
          </div>
        `).join('')}
      </div>
    </div>`;
  }

  body.innerHTML = html || '<p class="text-gray-500 text-sm">No renderable artifacts.</p>';
}

function renderJsonArtifact(filename, data, stepName) {
  // Render different JSON shapes in a human-readable way
  const base = filename.replace(/\.json$/, '');

  if (filename === 'story.json') {
    return renderStoryJson(data);
  }
  if (filename === 'all_episodes.json') {
    return renderAllEpisodesJson(data);
  }
  if (base.endsWith('_sheet')) {
    return renderCharacterSheetJson(data);
  }
  if (filename === 'director_shots.json') {
    return renderDirectorShotsJson(data);
  }
  if (base.endsWith('_layout')) {
    return renderWorldLayoutJson(data);
  }
  // Fallback: pretty-print
  return `
    <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">${esc(filename)}</div>
    <pre class="bg-gray-800 rounded-lg p-4 text-xs text-gray-300 overflow-auto max-h-96 leading-relaxed">${esc(JSON.stringify(data, null, 2))}</pre>
  `;
}

function renderStoryJson(d) {
  const chars = (d.character_seeds || []).map(c => `
    <div class="bg-gray-800 rounded-lg p-3 space-y-1">
      <div class="font-medium text-white text-sm">${esc(c.display_name)} <span class="text-gray-500 font-normal text-xs">(${esc(c.base_object)})</span></div>
      <div class="text-xs text-indigo-300">${esc(c.role_in_story)}</div>
      <div class="text-xs text-gray-400">${esc(c.visual_description)}</div>
      <div class="text-xs text-gray-500 italic">Voice: ${esc(c.voice_profile)}</div>
    </div>
  `).join('');

  const episodes = (d.episode_outlines || []).map(ep => `
    <div class="border-l-2 border-indigo-800 pl-3">
      <div class="text-sm font-medium text-white">Ep ${ep.episode_number}: ${esc(ep.title)}</div>
      <div class="text-xs text-gray-400 mt-0.5">${esc(ep.summary)}</div>
      <div class="text-xs text-yellow-500 mt-1">↳ Hook: ${esc(ep.opening_hook)}</div>
    </div>
  `).join('');

  return `
    <div class="space-y-5">
      <div>
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Story</div>
        <div class="text-xl font-bold text-white">${esc(d.project_title)}</div>
        <div class="text-sm text-indigo-300 mt-1 italic">${esc(d.logline)}</div>
        <div class="text-xs text-gray-400 mt-2">${esc(d.setting)}</div>
        <div class="text-xs text-gray-500 mt-1">Tone: ${esc(d.tone)}</div>
      </div>

      ${d.series_arc ? `
      <div>
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Series Arc</div>
        <p class="text-sm text-gray-300">${esc(d.series_arc)}</p>
      </div>` : ''}

      ${d.world_rules?.length ? `
      <div>
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">World Rules</div>
        <ul class="space-y-1">
          ${d.world_rules.map(r => `<li class="text-xs text-gray-300 flex gap-2"><span class="text-indigo-500 flex-shrink-0">▸</span>${esc(r)}</li>`).join('')}
        </ul>
      </div>` : ''}

      ${chars ? `
      <div>
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Characters</div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${chars}</div>
      </div>` : ''}

      ${episodes ? `
      <div>
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Episode Outlines</div>
        <div class="space-y-3">${episodes}</div>
      </div>` : ''}
    </div>
  `;
}

function renderAllEpisodesJson(d) {
  const episodes = (d.episodes || []).map(ep => {
    const scenes = (ep.scenes || []).map(s => `
      <div class="bg-gray-800 rounded-lg p-3 space-y-1">
        <div class="flex items-center gap-2">
          <span class="text-xs font-mono text-indigo-400">Scene ${s.scene_id}</span>
          <span class="text-xs text-gray-500">@ ${esc(s.location_slug)}</span>
          <span class="text-xs text-gray-600 ml-auto">${esc(s.mood)}</span>
        </div>
        <div class="text-xs text-gray-300 italic">"${esc(s.dialogue)}"</div>
        <div class="text-xs text-gray-500">${esc(s.visual_context)}</div>
        <div class="text-xs text-yellow-600">Beat: ${esc(s.beat_note)}</div>
      </div>
    `).join('');

    return `
      <div class="border border-gray-800 rounded-xl overflow-hidden">
        <div class="px-4 py-3 bg-gray-800 bg-opacity-50">
          <div class="font-medium text-white">Ep ${ep.episode_number}: ${esc(ep.episode_title)}</div>
          <div class="text-xs text-yellow-400 mt-0.5 italic">${esc(ep.cold_open_hook)}</div>
        </div>
        <div class="p-4 space-y-2">${scenes}</div>
        <div class="px-4 py-2 border-t border-gray-800 text-xs text-gray-500 italic">
          Ending: ${esc(ep.episode_ending)}
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="space-y-4">
      <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider">All Episode Scripts</div>
      ${episodes}
    </div>
  `;
}

function renderCharacterSheetJson(d) {
  return `
    <div class="bg-gray-800 rounded-xl p-4 space-y-3">
      <div>
        <div class="text-lg font-bold text-white">${esc(d.display_name)}</div>
        <div class="text-xs text-indigo-300">${esc(d.role_in_story)} · ${esc(d.base_object)}</div>
      </div>
      ${d.personality_traits?.length ? `
      <div class="flex gap-1.5 flex-wrap">
        ${d.personality_traits.map(t => `<span class="text-xs px-2 py-0.5 rounded-full bg-indigo-900 text-indigo-300">${esc(t)}</span>`).join('')}
      </div>` : ''}
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Visual Description</div>
        <p class="text-xs text-gray-300 leading-relaxed">${esc(d.visual_description)}</p>
      </div>
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Voice Profile</div>
        <p class="text-xs text-gray-300 italic">${esc(d.voice_profile)}</p>
      </div>
      ${d.signature_gesture ? `
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Signature Gesture</div>
        <p class="text-xs text-gray-300">${esc(d.signature_gesture)}</p>
      </div>` : ''}
      ${d.emotional_range ? `
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Emotional Range</div>
        <p class="text-xs text-gray-300">${esc(d.emotional_range)}</p>
      </div>` : ''}
    </div>
  `;
}

function renderDirectorShotsJson(d) {
  const shots = (d.shots || []).map(s => `
    <div class="border border-gray-800 rounded-xl overflow-hidden">
      <div class="px-4 py-2 bg-gray-800 bg-opacity-40 flex items-center gap-3">
        <span class="text-xs font-mono text-indigo-400">Shot ${s.scene_id}</span>
        <span class="text-xs text-gray-500">${esc(s.shot_type)} · ${esc(s.camera_angle)}</span>
        <span class="text-xs text-gray-600 ml-auto">${esc(s.camera_movement)}</span>
      </div>
      <div class="p-4 space-y-3">
        <div>
          <div class="text-xs text-gray-500 mb-1">Veo Prompt</div>
          <p class="text-xs text-gray-200 leading-relaxed bg-gray-800 rounded-lg p-3 font-mono">${esc(s.veo_prompt)}</p>
        </div>
        <div class="flex gap-4">
          <div class="flex-1">
            <div class="text-xs text-gray-500 mb-0.5">Dialogue</div>
            <p class="text-xs text-yellow-300 italic">"${esc(s.dialogue)}"</p>
          </div>
          <div class="flex-1">
            <div class="text-xs text-gray-500 mb-0.5">Voice</div>
            <p class="text-xs text-gray-400">${esc(s.voice_profile)}</p>
          </div>
        </div>
      </div>
    </div>
  `).join('');

  return `
    <div class="space-y-3">
      <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider">
        Director Shots — Episode ${d.episode_number} (${d.shots?.length || 0} shots)
      </div>
      ${shots}
    </div>
  `;
}

function renderWorldLayoutJson(d) {
  return `
    <div class="bg-gray-800 rounded-xl p-4 space-y-3">
      <div>
        <div class="text-lg font-bold text-white">${esc(d.display_name || d.location_id)}</div>
        <div class="text-xs text-indigo-300 font-mono">${esc(d.location_id)}</div>
      </div>
      ${d.visual_description ? `
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Visual</div>
        <p class="text-xs text-gray-300 leading-relaxed">${esc(d.visual_description)}</p>
      </div>` : ''}
      ${d.atmosphere ? `
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Atmosphere</div>
        <p class="text-xs text-gray-300">${esc(d.atmosphere)}</p>
      </div>` : ''}
      ${d.lighting_notes ? `
      <div>
        <div class="text-xs text-gray-500 mb-0.5">Lighting</div>
        <p class="text-xs text-gray-300">${esc(d.lighting_notes)}</p>
      </div>` : ''}
      ${d.color_palette?.length ? `
      <div>
        <div class="text-xs text-gray-500 mb-1">Color Palette</div>
        <div class="flex gap-1.5 flex-wrap">
          ${d.color_palette.map(c => `<span class="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">${esc(c)}</span>`).join('')}
        </div>
      </div>` : ''}
    </div>
  `;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function ts() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map(n => String(n).padStart(2, '0')).join(':');
}

function esc(str) {
  if (str == null) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

// ── Settings ──────────────────────────────────────────────────────────────────

const LLM_MODELS = [
  { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash-Lite (fastest / cheapest)' },
  { value: 'gemini-2.5-flash',      label: 'Gemini 2.5 Flash (best price-performance) ★ default' },
  { value: 'gemini-2.5-pro',        label: 'Gemini 2.5 Pro (most capable)' },
  { value: 'gemini-3.1-pro-preview',label: 'Gemini 3.1 Pro Preview (latest)' },
];

const IMAGE_MODELS = [
  { value: 'gemini-2.5-flash-image',        label: 'Gemini 2.5 Flash Image / Nano Banana (fastest / cheapest) ★ default' },
  { value: 'gemini-3.1-flash-image-preview', label: 'Gemini 3.1 Flash Image / Nano Banana 2 (high efficiency)' },
  { value: 'gemini-3-pro-image-preview',    label: 'Gemini 3 Pro Image / Nano Banana Pro (studio quality)' },
];

const VIDEO_MODELS = [
  { value: 'veo-3.1-lite-generate-preview', label: 'Veo 3.1 Lite (lowest cost) ★ default' },
  { value: 'veo-3.1-generate-preview',      label: 'Veo 3.1 (full cinematic quality + native audio)' },
];

const TTS_MODELS = [
  { value: 'gemini-2.5-flash-preview-tts', label: 'Gemini 2.5 Flash TTS (fast / cheap) ★ default' },
  { value: 'gemini-2.5-pro-preview-tts',   label: 'Gemini 2.5 Pro TTS (higher fidelity)' },
];

function selectOpts(models, current) {
  return models.map(m =>
    `<option value="${esc(m.value)}" ${m.value === current ? 'selected' : ''}>${esc(m.label)}</option>`
  ).join('');
}

async function renderSettings() {
  $('#header-subtitle').textContent = 'Settings';
  main().innerHTML = `<div class="text-gray-400 text-sm">Loading...</div>`;

  let data = { credentials: {}, models: {} };
  try { data = await api('GET', '/api/settings'); } catch {}

  const c = data.credentials || {};
  const m = data.models || {};

  main().innerHTML = `
    <div class="max-w-2xl mx-auto space-y-6">

      <!-- Credentials -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 class="text-lg font-semibold mb-1">API Credentials</h2>
        <p class="text-xs text-gray-500 mb-4">Saved to <code>output/settings.json</code> (overrides .env). Leave blank to keep existing.</p>

        ${[
          ['GEMINI_API_KEY',    'Gemini API Key',           'https://aistudio.google.com/apikey'],
          ['GROQ_API_KEY',      'Groq API Key (optional)',  'https://console.groq.com/keys'],
          ['TMDB_API_KEY',      'TMDB API Key (movie mode)','https://www.themoviedb.org/settings/api'],
          ['PEXELS_API_KEY',    'Pexels API Key (movie mode)','https://www.pexels.com/api/'],
          ['VERTEX_PROJECT_ID', 'Vertex AI Project ID',     ''],
          ['VERTEX_LOCATION',   'Vertex AI Location',       ''],
        ].map(([key, label, link]) => `
          <div class="mb-3">
            <label class="block text-sm font-medium text-gray-400 mb-1">
              ${esc(label)}${link ? ` <a href="${link}" target="_blank" class="text-indigo-500 text-xs ml-1">Get key →</a>` : ''}
            </label>
            <input id="cred-${key}" type="password" autocomplete="off"
              placeholder="${esc(c[key] || '')}"
              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              value="" />
          </div>
        `).join('')}
      </div>

      <!-- Integrations -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 class="text-lg font-semibold mb-1">Integrations</h2>
        <p class="text-xs text-gray-500 mb-4">External service connections for batch processing.</p>

        <div class="mb-3">
          <label class="block text-sm font-medium text-gray-400 mb-1">Google Sheet URL (Movie Recap Batch)</label>
          <input id="int-BATCH_SHEET_URL" type="text" autocomplete="off"
            placeholder="${esc(data.integrations?.BATCH_SHEET_URL || '')}"
            class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
            value="" />
          <div class="mt-2 px-3 py-2.5 bg-gray-800/50 border border-gray-700/50 rounded-lg">
            <p class="text-xs text-gray-500 leading-relaxed">
              Your sheet needs a <strong class="text-gray-400">movie_title</strong> (or Movie Name) column and a
              <strong class="text-gray-400">Status</strong> column in row 1.
              Set Status to <strong class="text-gray-400">pending</strong> for each movie you want processed.
              The pipeline updates Status to Done/Failed and fills in output columns automatically.
              Requires a Google service account with editor access
              (configured via <code class="text-gray-400">GOOGLE_SERVICE_ACCOUNT_FILE</code> in .env).
            </p>
          </div>
        </div>
      </div>

      <!-- Model selection -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 class="text-lg font-semibold mb-1">Model Selection</h2>
        <p class="text-xs text-gray-500 mb-4">Choose which Gemini model to use at each pipeline stage.</p>

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-400 mb-1">LLM (Writing / Direction / Casting)</label>
          <select id="model-llm"
            class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500">
            ${selectOpts(LLM_MODELS, m.llm_model || 'gemini-2.5-flash')}
          </select>
        </div>

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-400 mb-1">Image Generation (Character / World art)</label>
          <select id="model-image"
            class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500">
            ${selectOpts(IMAGE_MODELS, m.image_model || 'gemini-2.5-flash-image')}
          </select>
        </div>

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-400 mb-1">Video Generation (Veo — scene clips)</label>
          <select id="model-video"
            class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500">
            ${selectOpts(VIDEO_MODELS, m.video_model || 'veo-3.1-lite-generate-preview')}
          </select>
        </div>

        <div class="mb-2">
          <label class="block text-sm font-medium text-gray-400 mb-1">Text-to-Speech (Voice lines)</label>
          <select id="model-tts"
            class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500">
            ${selectOpts(TTS_MODELS, m.tts_model || 'gemini-2.5-flash-preview-tts')}
          </select>
        </div>
      </div>

      <!-- Save -->
      <div id="settings-msg" class="text-sm hidden"></div>
      <div class="flex gap-3">
        <button onclick="router.go('dashboard')"
          class="px-4 py-2 rounded-lg text-sm border border-gray-700 text-gray-400 hover:text-white transition">Cancel</button>
        <button onclick="saveSettings()"
          class="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition">Save Settings</button>
      </div>
    </div>
  `;
}

async function saveSettings() {
  const cred_keys = ['GEMINI_API_KEY','GROQ_API_KEY','TMDB_API_KEY','PEXELS_API_KEY','VERTEX_PROJECT_ID','VERTEX_LOCATION'];
  const credentials = {};
  for (const k of cred_keys) {
    const el = document.getElementById(`cred-${k}`);
    if (el && el.value.trim()) credentials[k] = el.value.trim();
  }

  const integrations = {};
  const sheetUrl = document.getElementById('int-BATCH_SHEET_URL');
  if (sheetUrl && sheetUrl.value.trim()) integrations.BATCH_SHEET_URL = sheetUrl.value.trim();

  const models = {
    llm_model:   document.getElementById('model-llm').value,
    image_model: document.getElementById('model-image').value,
    video_model: document.getElementById('model-video').value,
    tts_model:   document.getElementById('model-tts').value,
  };

  const msgEl = document.getElementById('settings-msg');
  try {
    await api('PUT', '/api/settings', { credentials, models, integrations });
    msgEl.textContent = 'Settings saved. Restart the server to apply credential changes.';
    msgEl.className = 'text-sm text-green-400';
    msgEl.classList.remove('hidden');
  } catch (e) {
    msgEl.textContent = 'Error: ' + e.message;
    msgEl.className = 'text-sm text-red-400';
    msgEl.classList.remove('hidden');
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────

router.go('dashboard');
