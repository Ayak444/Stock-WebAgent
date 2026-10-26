// A shared research context. Changing tools never starts an analysis request.
let workspaceTicker = '';
let workspaceEpoch = 0;
let workspaceView = 'overview';
const workspaceRequests = {kline: 0, snapshot: 0, backtest: 0, valuation: 0, valuationcalc: 0};
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
    resetValuation();
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
  } else if (['kline', 'backtest', 'screener', 'valuation'].includes(tool)) navigateTo(tool);
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
  ['insights', 'kline', 'backtest', 'screener', 'valuation'].forEach(page => {
    const section = document.createElement('section'); section.className = 'workspace'; section.setAttribute('aria-label', '共用個股研究工作台');
    section.innerHTML = `<p class="workspace-kicker">STOCK WORKSPACE / 個股研究</p><div class="workspace-heading"><div><h3 class="workspace-identity">選擇一檔股票，開始研究</h3><p class="workspace-note">同代號切換工具。資料與分析由你主動載入。</p></div><form class="workspace-form"><label for="workspace-ticker-${page}">目前研究股票</label><input class="input workspace-ticker-input" id="workspace-ticker-${page}" placeholder="2330.TW / 6488.TWO" autocomplete="off"><button type="submit" class="btn-outline">切換股票</button></form></div><nav class="workspace-tools" aria-label="個股研究工具">${[['overview','概覽'],['kline','K 線'],['valuation','價格檢視'],['holders','籌碼'],['stock-news','個股新聞'],['backtest','回測'],['screener','關聯選股']].map(([tool,label]) => `<button type="button" data-tool="${tool}">${label}</button>`).join('')}</nav><div class="workspace-footer"><button type="button" class="btn-outline workspace-notify">加入通知草稿</button><span class="workspace-note">只帶入候選股票；通知設定另行儲存。</span></div>`;
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
  document.getElementById('valuation-mode').addEventListener('change', updateValuationMode);
  document.getElementById('page-valuation').addEventListener('input', event => {
    if (!event.target.closest('#valuation-current-form, #valuation-scenario-form')) return;
    workspaceRequests.valuationcalc++;
    ['btn-valuation-current','btn-valuation-scenarios'].forEach(id => { document.getElementById(id).disabled = false; });
    document.getElementById('valuation-current-result').textContent = '假設已變更，請重新檢視今日區間。';
    document.getElementById('valuation-scenario-result').textContent = '假設已變更，請重新計算情境。';
  });
  updateValuationMode();
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

// Price inspection shares the stock identity and request-generation guards.
let valuationSnapshot = null;

function resetValuation() {
  valuationSnapshot = null;
  workspaceRequests.valuation++;
  workspaceRequests.valuationcalc++;
  if (!document.getElementById('valuation-status')) return;
  document.getElementById('valuation-status').textContent = '股票已切換；請更新價格與財報。';
  document.getElementById('valuation-metrics').replaceChildren();
  document.getElementById('valuation-current-form').reset();
  document.getElementById('valuation-scenario-form').reset();
  ['valuation-current-result','valuation-peer-source','valuation-sources'].forEach(id => { document.getElementById(id).textContent = '尚未載入這檔股票的資料。'; });
  document.getElementById('valuation-scenario-result').textContent = '等待手動輸入；尚未產生預測。';
  document.getElementById('valuation-horizon').textContent = 'NTM 獲利期間與價格觀察終點將在載入資料後顯示。';
  ['btn-valuation','btn-valuation-current','btn-valuation-scenarios'].forEach(id => { document.getElementById(id).disabled = false; });
  updateValuationMode();
}

function valuationNumber(value, decimals = 2) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('zh-TW', {maximumFractionDigits: decimals, minimumFractionDigits: decimals}) : '無法取得';
}

function valuationReason(code) {
  const messages = {
    four_quarters_unavailable:'尚無完整四季 EPS，暫停 TTM 估值', quarter_gap:'季度不連續，無法加總',
    eps_basis_incomplete:'基本／稀釋 EPS 口徑或季度資料不完整', quarter_periods_unverified:'季度期間無法核對',
    corporate_actions_unverified:'公司行動尚未核對', corporate_action_in_period:'期間內有拆股／公司行動，股數基準待核對',
    material_share_change:'加權平均股數變動超過 1%，停止季度加總估值', share_basis_unverified:'加權平均股數資料不完整',
    eps_currency_unverified:'財報幣別未確認為台幣', quote_currency_unverified:'報價幣別未確認為台幣',
    eps_period_stale_or_future:'季度資料過期或日期異常', not_ordinary_stock:'未確認為適用的普通股',
    insufficient_peers:'同產業有效同日樣本少於 5 檔，可改用手動倍數',
    peer_context_unverified:'日期、產業或新鮮度未通過核對，無法提供產業分位',
    valuation_inputs_ineligible:'需有效普通股、正值季度 EPS 估算與最新收盤價；目前無法分類',
    pe_assumptions_required:'尚無可用產業倍數，請選手動模式填寫三個倍數',
    cumulative_not_ttm:'年初至當季累計，不能當作 TTM',
    vendor_period_and_basis_incomplete:'供應商參考值；完整四季期間與基本／稀釋口徑未驗證，不作估值',
    quote_unavailable:'收盤價格暫缺', official_pe_unavailable:'官方參考本益比暫缺', invalid_eps_total:'EPS 合計無效',
    quote_stale:'尚未確認收盤價符合最新完成交易日，暫停今日分類；需核對行情與是否有臨時休市。手動倍數無法解除限制，未來情境仍可獨立計算。',
    quote_freshness_unknown:'無法確認最新交易日，暫停今日價格分類；請待交易日曆與價格完成核對。未來情境仍可獨立計算。',
    eps_unavailable:'缺少可用季度 EPS 估算，暫停今日分類；可另外填寫未來情境。',
    nonpositive_eps:'季度 EPS 加總為零或負數，不適用今日本益比估值；正值的未來獲利假設可另外計算。',
    nonfinite_calculation:'數字超出有效計算範圍，無法估值'
  };
  return messages[code] || '資料暫缺或尚待核對';
}

function valuationSource(item) {
  const e = escapeRoutingText;
  const link = typeof item.source_url === 'string' && item.source_url.startsWith('https://')
    ? `<a href="${e(item.source_url)}" target="_blank" rel="noopener noreferrer">原始來源</a>` : '來源未提供';
  const calendar = item.calendar_evidence;
  const calendarInfo = calendar ? `<p>交易日核對：${e(calendar.expected_completed_trading_day || '無法確認')} · 休市資料版本 ${e(calendar.exception_version || '年度表，無採用特殊休市紀錄')}</p><p>${e(calendar.methodology || '')}</p>${(calendar.used_exceptions || []).map(record => `<p class="valuation-warning">已採用 ${e(record.date)} 臨時休市（${e((record.market_scope || []).join('／'))}）：${e(record.reason)}。公告 ${e(record.announced_at)}，核對 ${e(record.verified_at)}。${(record.sources || []).map(source => `<a href="${e(source.source_url)}" target="_blank" rel="noopener noreferrer">休市證據（${e(source.market_scope.join('／'))}）</a>`).join(' · ')}</p>`).join('')}` : '';
  return `<p>${e(item.source || '來源尚未取得')} · ${link}</p><p>資料日：${e(item.as_of || item.period_end || '未知')} · 抓取：${e(item.fetched_at || '未知')} · 公布：${e(item.published_at || '未知，未假造')}</p><p>${e(item.methodology || '')}</p>${calendarInfo}`;
}

function renderValuationModel(model) {
  const box = document.getElementById('valuation-current-result');
  if (model?.status !== 'available') { box.textContent = valuationReason(model?.reason_code); return; }
  const classification = {below:'低於假設區間', within:'區間內', above:'高於假設區間'}[model.classification];
  box.innerHTML = `<strong class="valuation-range">TWD ${valuationNumber(model.low)} — ${valuationNumber(model.high)}</strong><p>相對本模型：${classification} · 中位參考 ${valuationNumber(model.mid)} 元</p><p class="workspace-note">${model.origin === 'user_assumption' ? '使用者手動倍數' : '官方同產業倍數分位'}：${valuationNumber(model.pe_low)}／${valuationNumber(model.pe_mid)}／${valuationNumber(model.pe_high)} 倍。等於邊界屬區間內；使用季度加總 EPS 估算，不是客觀合理價。</p>`;
}

function renderValuation(data) {
  const e = escapeRoutingText;
  const quote = data.quote || {}, eps = data.eps_ttm || {}, ytd = data.official_ytd_eps || {}, vendor = data.vendor_ttm_eps || {};
  const freshLabel = {fresh:'符合已核對的最新完成交易日', stale:'尚未確認符合最新交易日，停止今日分類', unknown:'無法確認最新交易日，停止今日分類'}[quote.freshness];
  const ordinary = data.identity?.ordinary;
  document.getElementById('valuation-status').textContent = `${data.identity?.name || workspaceTicker} · ${data.identity?.market === 'TWO' ? '上櫃' : '上市'} · ${ordinary ? freshLabel : '不適用或未確認為普通股'}。${quote.calendar_evidence?.used_exceptions?.length ? '已納入有來源的臨時休市紀錄，詳見資料來源。' : ''}各來源日期可能不同。`;
  const metrics = [
    ['最新可得收盤價', valuationNumber(quote.value), `TWD／每股 · ${quote.as_of || '日期未知'} · 非即時`],
    ['季度加總 EPS 估算', valuationNumber(eps.value), eps.status === 'available' ? `${eps.basis === 'diluted' ? '稀釋' : '基本'} · ${eps.period_start} — ${eps.period_end}` : valuationReason(eps.reason_code)],
    ['自算 TTM P/E', valuationNumber(data.calculated_pe), '收盤價 ÷ 季度 EPS 加總估算；非正 EPS 不計'],
    ['官方公告參考 P/E', valuationNumber(data.official_pe?.value), `${data.official_pe?.as_of || '日期未知'} · 官方口徑獨立呈現`],
    ['官方累計基本 EPS', valuationNumber(ytd.value), `${ytd.period_start || '未知'} — ${ytd.period_end || '未知'} · 非 TTM、不年化`],
    ['供應商 TTM EPS 參考', valuationNumber(vendor.value), `Yahoo trailingEps · ${vendor.currency || '幣別未知'}；期間／口徑未驗證，不用作估值`]
  ];
  document.getElementById('valuation-metrics').innerHTML = `<div class="valuation-metric-grid">${metrics.map(([title,value,meta]) => `<article class="stat-card"><h3>${e(title)}</h3><p class="valuation-value">${e(value)}</p><p class="workspace-note">${e(meta)}</p></article>`).join('')}</div>`;
  const peer = data.peer_reference || {};
  document.getElementById('valuation-peer-source').innerHTML = `<p>${peer.status === 'available' ? '可用' : e(valuationReason(peer.reason_code))} · 樣本 ${peer.count || 0} 檔 · 產業代碼 ${e(peer.industry_code || '未知')} · ${e(peer.as_of || '日期未知')}</p><p>${e(peer.methodology || '')}</p><p class="valuation-peer-list">${(peer.peers || []).map(row => `${e(row.ticker)}：${valuationNumber(row.pe)} 倍`).join('；') || '尚無有效樣本'}</p><p>排除自身、同交易所／產業、同日正本益比，至少 5 檔；P25／P50／P75 為排序後 (n−1)×p 線性插值。</p>`;
  const warnings = [];
  if (eps.warnings?.includes('quarter_sum_approximation')) warnings.push('四個季度 EPS 相加僅為估算，包含原來源的四捨五入；非公司直接公布 TTM。');
  if (eps.warnings?.includes('small_weighted_share_variation_approximation')) warnings.push('加權平均股數有小幅變動；最大／最小不超過 1.01，仍標示近似。超過門檻則停止估值；1% 為保守工程檢查，不是會計規則。');
  if (eps.warnings?.includes('corporate_actions_unknown_approximation')) warnings.push('公司行動資料未完整確認；僅因四季加權平均股數穩定在 1% 內，允許有警示的近似估算，不代表已排除所有公司行動。');
  if (eps.warnings?.includes('vendor_trailing_eps_differs')) warnings.push('季度加總與供應商 trailingEps 不同；保留兩者、不強行調整一致。');
  document.getElementById('valuation-sources').innerHTML = `${warnings.map(w => `<p class="valuation-warning">${e(w)}</p>`).join('')}${[['收盤價格',quote],['季度 EPS 估算',eps],['官方累計基本 EPS',ytd],['官方參考 P/E',data.official_pe || {}],['供應商 TTM EPS',vendor]].map(([title,item]) => `<section class="valuation-source"><h3>${e(title)}</h3>${valuationSource(item)}${item.period_start ? `<p>涵蓋期：${e(item.period_start)} — ${e(item.period_end || '未知')}</p>` : ''}${item.exported_at ? `<p>資料匯出日 ${e(item.exported_at)}，不是財報公布日。</p>` : ''}${item.reason_code ? `<p>${e(valuationReason(item.reason_code))}</p>` : ''}${item.quarters?.length ? `<p>獨立季度：${item.quarters.map(q => `${e(q.period_end)}：${valuationNumber(q.eps, 6)} 元`).join('；')}</p>` : ''}</section>`).join('')}<p class="workspace-note">普通股適用性以公司基本資料同代號、四位公司代碼、產業代碼與排除 DR／特殊商品核對；無法確認時停止估值。</p>`;
  document.getElementById('valuation-horizon').textContent = `手動 NTM 獲利期間：${data.eps_period_start} — ${data.eps_period_end}；12 個月價格觀察終點：${data.horizon_end}。`;
  const model = data.current_model;
  const manual = document.getElementById('valuation-mode').value === 'manual';
  const selectedPe = manual ? manualValuationPe() : null;
  const matchesSelection = manual
    ? selectedPe && model?.origin === 'user_assumption' && ['low','mid','high'].every(key => model['pe_' + key] === selectedPe[key])
    : model?.origin !== 'user_assumption';
  if ((model?.status === 'available' && !matchesSelection) || (manual && model?.reason_code === 'pe_assumptions_required')) {
    document.getElementById('valuation-current-result').textContent = '目前選擇的倍數尚未套用至這次資料；請確認手動輸入後，按「檢視今日區間」重新計算。';
  } else renderValuationModel(model);
}

function manualValuationPe() {
  const values = ['low','mid','high'].map(key => Number(document.getElementById('valuation-pe-' + key).value));
  if (!values.every(value => Number.isFinite(value) && value > 0 && value <= 10000) || values[0] > values[1] || values[1] > values[2]) return null;
  return Object.fromEntries(['low','mid','high'].map((key, index) => [key, values[index]]));
}

function updateValuationMode() {
  const manual = document.getElementById('valuation-mode')?.value === 'manual';
  ['low','mid','high'].forEach(key => { const input = document.getElementById('valuation-pe-' + key); if (input) { input.disabled = !manual; input.required = manual; } });
  workspaceRequests.valuationcalc++;
  if (valuationSnapshot) {
    ['btn-valuation-current','btn-valuation-scenarios'].forEach(id => { document.getElementById(id).disabled = false; });
    document.getElementById('valuation-current-result').textContent = '倍數來源已變更，請重新檢視今日區間。';
    document.getElementById('valuation-scenario-result').textContent = '假設已變更，請重新計算情境。';
  }
}

async function fetchValuation() {
  if (!workspaceTicker) { document.getElementById('valuation-status').textContent = '請先在共用工作台輸入股票代號。'; return; }
  const request = researchRequest('valuation');
  workspaceRequests.valuationcalc++;
  valuationSnapshot = null;
  document.getElementById('valuation-metrics').replaceChildren();
  document.getElementById('valuation-status').textContent = '正在取得交易所與財報資料；缺失部分會個別標示。';
  document.getElementById('valuation-current-result').textContent = '資料更新中，舊分類已清除。';
  document.getElementById('valuation-scenario-result').textContent = '資料更新中；請於完成後重新計算。';
  document.getElementById('btn-valuation').disabled = true;
  ['btn-valuation-current','btn-valuation-scenarios'].forEach(id => { document.getElementById(id).disabled = false; });
  const response = await apiCall(`/api/valuation/${encodeURIComponent(workspaceTicker)}`);
  if (!researchRequestCurrent(request)) return;
  document.getElementById('btn-valuation').disabled = false;
  if (!['success','partial'].includes(response.status) || !response.data) { document.getElementById('valuation-status').textContent = response.detail || response.message || '價格資料目前無法取得，請稍後重試。'; return; }
  if (response.data.identity?.code !== request.ticker.split('.')[0]) { document.getElementById('valuation-status').textContent = '回傳股票與查詢不符，請重新更新。'; return; }
  if (response.ticker && response.ticker !== workspaceTicker) setWorkspaceTicker(response.ticker);
  valuationSnapshot = response.data;
  renderValuation(valuationSnapshot);
  document.getElementById('valuation-scenario-result').textContent = '資料已更新；請輸入或確認三種手動假設，再按「計算三種情境」。';
}

async function calculateValuationRequest(body, targetId, buttonId) {
  if (!valuationSnapshot) { document.getElementById(targetId).textContent = '請先更新這檔股票的價格與財報。'; return; }
  const request = researchRequest('valuationcalc');
  document.getElementById(buttonId).disabled = true;
  document.getElementById(targetId).textContent = '依來源資料與假設計算中…';
  const response = await apiCall(`/api/valuation/${encodeURIComponent(workspaceTicker)}/assumptions`, 'POST', body);
  if (!researchRequestCurrent(request)) return;
  ['btn-valuation-current','btn-valuation-scenarios'].forEach(id => { document.getElementById(id).disabled = false; });
  if (!['success','partial'].includes(response.status) || !response.data) { document.getElementById(targetId).textContent = response.detail || response.message || '目前無法計算。'; return; }
  if (response.data.identity?.code !== request.ticker.split('.')[0]) { document.getElementById(targetId).textContent = '回傳股票不符，請更新後重試。'; return; }
  valuationSnapshot = response.data;
  renderValuation(valuationSnapshot);
  if (body.scenarios) {
    const names = {bear:'悲觀',base:'基準',bull:'樂觀'};
    const quote = response.data.quote;
    const rows = response.data.scenarios || [];
    document.getElementById(targetId).innerHTML = `<div class="valuation-scenarios">${rows.map(row => `<article class="valuation-scenario-output"><h3>${names[row.name]}情境・手動</h3><p class="valuation-value">${valuationNumber(row.price)} 元</p><p>${valuationNumber(row.eps)} EPS × ${valuationNumber(row.pe)} 倍</p><p>${row.price_change_pct === null ? '無可用價格作比較' : `相對 ${escapeRoutingText(quote.as_of || '未知日期')} 收盤價 ${valuationNumber(quote.value)}：${valuationNumber(row.price_change_pct)}%`}</p></article>`).join('')}</div><p class="workspace-note">${quote.freshness === 'fresh' ? '' : '比較基準價格過期或新鮮度未知，不能視為今天的漲跌空間。'}今日 Forward P/E（基準手動 EPS）${valuationNumber(response.data.forward_pe)} 倍，與情境假設倍數不同；沒有發生機率保證。</p>`;
  }
}

function submitCurrentValuation(event) {
  event.preventDefault();
  const body = {};
  if (document.getElementById('valuation-mode').value === 'manual') body.current_pe = Object.fromEntries(['low','mid','high'].map(key => [key, Number(document.getElementById('valuation-pe-' + key).value)]));
  return calculateValuationRequest(body, 'valuation-current-result', 'btn-valuation-current');
}

function submitValuationScenarios(event) {
  event.preventDefault();
  const body = {scenarios:['bear','base','bull'].map(name => ({eps:Number(document.getElementById(`valuation-${name}-eps`).value), pe:Number(document.getElementById(`valuation-${name}-pe`).value)}))};
  // An incomplete current-range draft must not block independent future scenarios.
  const currentPe = document.getElementById('valuation-mode').value === 'manual' ? manualValuationPe() : null;
  if (currentPe) body.current_pe = currentPe;
  return calculateValuationRequest(body, 'valuation-scenario-result', 'btn-valuation-scenarios');
}
