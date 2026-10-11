// A shared research context. Changing tools never starts an analysis request.
let workspaceTicker = '';
let workspaceEpoch = 0;
let workspaceView = 'overview';
const workspaceRequests = {kline: 0, snapshot: 0, backtest: 0};
let notificationSaved = null;
let notificationLoadVersion = 0;
let notificationSaveVersion = 0;
let notificationAccount = null;
let notificationCandidate = '';

function validWorkspaceTicker(value) {
  const raw = String(value || '').trim().toUpperCase();
  if (!/^\d{4,6}[A-Z]?(?:\.(?:TW|TWO))?$/.test(raw)) return '';
  return raw.includes('.') ? raw : raw + '.TW';
}

function setWorkspaceTicker(value) {
  const ticker = validWorkspaceTicker(value);
  if (!ticker) { showToast('請輸入有效台股代號，例如 2330.TW 或 6488.TWO', 'warning'); return false; }
  if (ticker !== workspaceTicker) {
    workspaceTicker = ticker;
    workspaceEpoch++;
    if (klineChart) { klineChart.dispose(); klineChart = null; }
    currentKlineData = null;
    currentKlineTicker = '';
    document.getElementById('kline-chart-title').textContent = `${displayTicker(ticker)} · 請載入圖表並執行既有分析`;
    document.getElementById('kline-signals').replaceChildren();
    document.getElementById('kline-fundamentals').style.display = 'none';
    document.getElementById('stock-snapshot-result').textContent = '股票已切換，請產生摘要以讀取這檔股票的資料。';
    document.getElementById('stock-snapshot-status').textContent = '尚未讀取';
    document.getElementById('backtest-result').textContent = '股票已切換；確認期間與成本後，執行回測。';
    document.getElementById('btn-stock-snapshot').disabled = false;
    document.getElementById('btn-backtest').disabled = false;
  }
  ['stock-snapshot-ticker', 'kline-ticker', 'backtest-ticker', 'screener-target-input'].forEach(id => { document.getElementById(id).value = ticker; });
  renderWorkspace();
  return true;
}

function renderWorkspace() {
  document.querySelectorAll('.workspace-identity').forEach(el => { el.textContent = workspaceTicker ? displayTicker(workspaceTicker) : '選擇一檔股票，開始研究'; });
  document.querySelectorAll('.workspace-ticker-input').forEach(el => { el.value = workspaceTicker; });
  document.querySelectorAll('.workspace-tools button').forEach(el => {
    const activePage = document.querySelector('.page.active')?.id.replace('page-', '');
    const selected = el.dataset.tool === (activePage === 'insights' ? workspaceView : activePage);
    if (selected) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  });
}

function switchWorkspaceTicker(event) {
  event.preventDefault();
  setWorkspaceTicker(event.currentTarget.querySelector('input').value);
}

function switchWorkspaceTool(tool) {
  if (['overview', 'holders', 'stock-news'].includes(tool)) {
    workspaceView = tool;
    navigateTo('insights');
    applySnapshotView();
  } else if (['kline', 'backtest', 'screener'].includes(tool)) navigateTo(tool);
  renderWorkspace();
}

function openWorkspaceKline(ticker) {
  if (!setWorkspaceTicker(ticker)) return false;
  navigateTo('kline');
  const selectedTicker = workspaceTicker;
  const selectedEpoch = workspaceEpoch;
  // An explicit result click keeps its original chart/analysis action. A later
  // stock selection cancels this queued action rather than analyzing that stock.
  setTimeout(() => {
    if (workspaceTicker === selectedTicker && workspaceEpoch === selectedEpoch) fetchKline();
  }, 100);
  return true;
}

function applySnapshotView() {
  document.getElementById('stock-snapshot-result').dataset.view = workspaceView;
  document.querySelectorAll('#stock-snapshot-result [data-snapshot-section]').forEach(el => {
    el.hidden = workspaceView !== 'overview' && el.dataset.snapshotSection !== (workspaceView === 'holders' ? 'ownership' : 'news');
  });
}

function researchRequest(kind) {
  return {kind, ticker: workspaceTicker, epoch: workspaceEpoch, version: ++workspaceRequests[kind]};
}

function researchRequestCurrent(request) {
  return request.epoch === workspaceEpoch && request.ticker === workspaceTicker && request.version === workspaceRequests[request.kind];
}

function initWorkspace() {
  document.title = '市場總覽 - 股金往來';
  revealHomeOnce();
  ['insights', 'kline', 'backtest', 'screener'].forEach(page => {
    const section = document.createElement('section'); section.className = 'workspace'; section.setAttribute('aria-label', '共用個股研究工作台');
    section.innerHTML = `<p class="workspace-kicker">STOCK WORKSPACE / 個股研究</p><div class="workspace-heading"><div><h3 class="workspace-identity">選擇一檔股票，開始研究</h3><p class="workspace-note">同代號切換工具。資料與分析由你主動載入。</p></div><form class="workspace-form"><label for="workspace-ticker-${page}">目前研究股票</label><input class="input workspace-ticker-input" id="workspace-ticker-${page}" placeholder="2330.TW / 6488.TWO" autocomplete="off"><button type="submit" class="btn-outline">切換股票</button></form></div><nav class="workspace-tools" aria-label="個股研究工具">${[['overview','概覽'],['kline','K 線'],['holders','籌碼'],['stock-news','個股新聞'],['backtest','回測'],['screener','關聯選股']].map(([tool,label]) => `<button type="button" data-tool="${tool}">${label}</button>`).join('')}</nav><div class="workspace-footer"><button type="button" class="btn-outline workspace-notify">加入通知草稿</button><span class="workspace-note">只帶入候選股票；通知設定另行儲存。</span></div>`;
    section.querySelector('form').addEventListener('submit', switchWorkspaceTicker);
    section.querySelectorAll('[data-tool]').forEach(el => el.addEventListener('click', () => switchWorkspaceTool(el.dataset.tool)));
    section.querySelector('.workspace-notify').addEventListener('click', () => {
      if (!workspaceTicker) { showToast('請先選擇研究股票', 'warning'); return; }
      notificationCandidate = workspaceTicker;
      navigateTo('volume-settings');
    });
    const target = document.getElementById('page-' + page);
    // Move the original field into the shared header so there is one ticker
    // editor per tool, while retaining every existing ID and request handler.
    const originalId = {insights: 'stock-snapshot-ticker', kline: 'kline-ticker', backtest: 'backtest-ticker'}[page];
    if (originalId) {
      const input = document.getElementById(originalId);
      const originalParent = input.parentElement;
      input.classList.add('workspace-ticker-input');
      input.removeAttribute('onkeydown');
      section.querySelector('input').replaceWith(input);
      section.querySelector('label').htmlFor = originalId;
      if (page === 'backtest') originalParent.remove();
    }
    target.querySelector('.page-header').after(section);
  });
  renderWorkspace();
  document.querySelectorAll('#tech-data-table th[onclick]').forEach(th => {
    th.tabIndex = 0; th.setAttribute('role', 'button');
    th.setAttribute('aria-label', th.textContent + '，點擊排序');
    th.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); th.click(); } });
  });
  ['volume-tickers','volume-webhook','volume-remove-webhook'].forEach(id => document.getElementById(id).addEventListener('input', () => {
    document.getElementById('volume-draft-state').textContent = '有尚未儲存的草稿。上方進度仍依伺服器已儲存設定顯示。';
  }));
  window.addEventListener('resize', resizeWorkspaceCharts);
}

function resizeWorkspaceCharts() {
  if (typeof echarts === 'undefined') return;
  document.querySelectorAll('.page.active [id]').forEach(el => { const instance = echarts.getInstanceByDom(el); if (instance) instance.resize(); });
}

function resetNotificationAccount() {
  notificationLoadVersion++;
  notificationSaveVersion++;
  notificationSaved = null;
  notificationAccount = currentUser?.id || currentUser?.email || null;
  document.getElementById('volume-tickers').value = '';
  document.getElementById('volume-webhook').value = '';
  document.getElementById('volume-remove-webhook').checked = false;
  document.getElementById('volume-webhook-state').textContent = '';
  document.getElementById('volume-draft-state').textContent = '';
  document.getElementById('volume-settings-form').style.display = 'none';
  document.getElementById('volume-save-btn').disabled = false;
  renderNotificationProgress();
}

function renderNotificationProgress() {
  const saved = notificationSaved;
  document.getElementById('volume-step-stocks').textContent = saved ? `已儲存 ${saved.tickers.length} / 20 檔` : '尚未讀取已儲存清單';
  document.getElementById('volume-step-discord').textContent = !saved ? '尚未讀取' : saved.webhook_readable === false ? '需要恢復設定' : saved.webhook_configured ? '已儲存 Webhook（未驗證頻道）' : '尚未設定 Webhook';
  const missing = !saved ? [] : [!saved.tickers.length ? '股票清單' : '', !saved.webhook_configured || saved.webhook_readable === false ? '可讀取的 Webhook' : ''].filter(Boolean);
  document.getElementById('volume-step-complete').textContent = !saved
    ? currentUser ? '設定尚未讀取，請重新載入' : '登入並讀取設定後確認'
    : missing.length ? `仍需${missing.join('與')}` : '設定已儲存；不代表通知已送達';
}

function openNotificationSettings() {
  const account = currentUser?.id || currentUser?.email || null;
  if (notificationSaved && account === notificationAccount && document.getElementById('volume-settings-form').style.display === 'block') {
    // Tool and About navigation preserve this account's unsaved editor.
    renderNotificationProgress();
    applyNotificationCandidate();
  } else loadVolumeSettings();
}

function applyNotificationCandidate() {
  if (!notificationCandidate || !notificationSaved) return;
  const candidate = notificationCandidate;
  notificationCandidate = '';
  const tickers = document.getElementById('volume-tickers').value.split(',').map(item => item.trim()).filter(Boolean);
  if (tickers.includes(candidate)) { document.getElementById('volume-draft-state').textContent = `${candidate} 已在清單內；未自動儲存。`; return; }
  if (tickers.length >= 20) { document.getElementById('volume-draft-state').textContent = `已達 20 檔上限；未加入 ${candidate}。請先移除一檔，再加入草稿。`; return; }
  document.getElementById('volume-tickers').value = [...tickers, candidate].join(',');
  document.getElementById('volume-draft-state').textContent = `${candidate} 已加入未儲存草稿。確認股票與 Discord 設定後，按儲存。`;
}

function openAbout() {
  const landing = document.getElementById('landing');
  const app = document.querySelector('.app');
  landing.hidden = false; landing.style.display = 'block'; landing.style.removeProperty('opacity'); landing.style.removeProperty('transform');
  app.classList.remove('active');
  app.hidden = true;
  app.inert = true;
  app.style.display = 'none';
  document.getElementById('sidebar').classList.remove('open');
  const overlay = document.getElementById('sidebar-overlay');
  overlay.classList.remove('visible');
  overlay.style.display = 'none';
  document.getElementById('mobile-toggle').setAttribute('aria-expanded', 'false');
  chatOpen = false;
  document.getElementById('chat-panel').classList.remove('open');
  document.getElementById('chat-fab').setAttribute('aria-expanded', 'false');
  document.getElementById('mobile-toggle').hidden = true;
  document.getElementById('chat-fab').hidden = true;
  document.title = '關於股金往來';
  landing.scrollTop = 0;
  document.getElementById('landing-cta').focus();
}

function closeAbout() {
  document.getElementById('landing').hidden = true;
  document.getElementById('landing').style.display = 'none';
  const app = document.querySelector('.app');
  app.hidden = false;
  app.inert = false;
  app.style.removeProperty('display');
  app.classList.add('active');
  document.getElementById('mobile-toggle').hidden = false;
  document.getElementById('chat-fab').hidden = false;
  navigateTo('war');
  revealHomeOnce();
  const heading = document.querySelector('#page-war .home-intro h2');
  heading.tabIndex = -1;
  heading.focus({preventScroll: true});
}

// Contain keyboard focus while a dialog is open and return it on dismissal.
const modalReturnFocus = new Map();
document.addEventListener('keydown', event => {
  if (event.key !== 'Tab') return;
  const modal = document.querySelector('.modal-backdrop.open');
  if (!modal) return;
  const controls = Array.from(modal.querySelectorAll('button, a[href], input, select, [tabindex="0"]')).filter(el => !el.disabled && !el.hidden && el.getClientRects().length);
  if (!controls.length) return;
  const first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && (document.activeElement === first || !modal.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && (document.activeElement === last || !modal.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
});
