// Execute production helpers with a deliberately offline fake DOM/API.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('static/index.html', 'utf8');
const workspace = fs.readFileSync('static/workspace.js', 'utf8');
const css = fs.readFileSync('static/workspace.css', 'utf8');
const slice = (start, end) => {
  const a = html.indexOf(start), b = html.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, `missing production seam: ${start}`);
  return html.slice(a, b);
};
class Element {
  constructor(id = '') {
    this.id = id; this.value = ''; this.checked = false; this.disabled = false;
    this.hidden = false; this.inert = false; this.dataset = {}; this.children = [];
    this.attributes = {}; this.listeners = {}; this._text = ''; this._html = '';
    this.style = {removeProperty(name) {delete this[name];}};
    const classes = new Set();
    this.classList = {
      add: (...names) => names.forEach(name => classes.add(name)),
      remove: (...names) => names.forEach(name => classes.delete(name)),
      contains: name => classes.has(name),
      toggle: (name, force) => { const enabled = force ?? !classes.has(name); enabled ? classes.add(name) : classes.delete(name); return enabled; }
    };
  }
  set textContent(value) {this._text = String(value); this._html = ''; this.children = [];}
  get textContent() {return this._text + this.children.map(child => child.textContent).join('');}
  set innerHTML(value) {
    this._html = String(value); this._text = ''; this.children = [];
    this.sections = [...this._html.matchAll(/data-snapshot-section="([^"]+)"/g)].map(match => {
      const node = new Element(); node.dataset.snapshotSection = match[1]; return node;
    });
    this.rows = [...this._html.matchAll(/<tr(?:\s[^>]*)?>/g)].map(() => {
      const row = new Element(); row.owner = this.owner;
      row.cells = Array.from({length: 6}, () => new Element()); return row;
    });
    this.stockLinks = [...this._html.matchAll(/data-screener-ticker="([^"]+)"/g)].map(match => {
      const node = new Element(); node.owner = this.owner;
      node.dataset.screenerTicker = match[1]; return node;
    });
  }
  get innerHTML() {return this._html;}
  appendChild(node) {this.children.push(node); return node;}
  append(...nodes) {nodes.forEach(node => this.appendChild(node));}
  replaceChildren(...nodes) {this.textContent = ''; this.append(...nodes);}
  reset() {
    // Model the standard HTMLFormElement reset now used by the shared workspace.
    const ids = this.id === 'valuation-current-form'
      ? ['valuation-pe-low', 'valuation-pe-mid', 'valuation-pe-high']
      : ['bear', 'base', 'bull'].flatMap(name => [`valuation-${name}-eps`, `valuation-${name}-pe`]);
    ids.forEach(id => {this.owner.getElementById(id).value = '';});
    if (this.id === 'valuation-current-form') this.owner.getElementById('valuation-mode').value = 'auto';
  }
  setAttribute(name, value) {this.attributes[name] = String(value);}
  removeAttribute(name) {delete this.attributes[name];}
  addEventListener(name, fn) {this.listeners[name] = fn;}
  focus() {this.owner.activeElement = this;}
  getClientRects() {return this.hidden ? [] : [{}];}
  querySelector(selector) {return this.child || (this.child = new Element(selector));}
  querySelectorAll(selector) {return selector === '[data-screener-ticker]' ? this.stockLinks || [] : [];}
}
const routes = ['war', 'stress', 'tech', 'kline', 'backtest', 'news', 'sentiment', 'insights', 'screener', 'volume-settings'];
function harness() {
  const nodes = new Map(), events = {}, calls = [], toasts = [], charts = [], timers = [];
  const document = {
    activeElement: null, title: '',
    getElementById(id) {if (!nodes.has(id)) {const node = new Element(id); node.owner = this; nodes.set(id, node);} return nodes.get(id);},
    createElement(tag) {const node = new Element(tag); node.owner = this; return node;},
    createTextNode(text) {const node = this.createElement('#text'); node.textContent = text; return node;},
    addEventListener(name, fn) {(events[name] ||= []).push(fn);},
    querySelector(selector) {
      if (selector === '.modal-backdrop.open') return this.modal || null;
      if (selector === '.page.active') return routes.map(page => this.getElementById('page-' + page)).find(node => node.classList.contains('active'));
      return this.getElementById(selector);
    },
    querySelectorAll(selector) {
      if (selector === '.page') return routes.map(page => this.getElementById('page-' + page));
      if (selector === '#nav .nav-btn[data-page]') return nav;
      if (selector === '.workspace-tools button') return tools;
      if (selector === '.workspace-ticker-input') return ['stock-snapshot-ticker', 'kline-ticker', 'backtest-ticker', 'workspace-ticker-screener'].map(id => this.getElementById(id));
      if (selector === '#tech-table tr') return this.getElementById('tech-table').rows || [];
      if (selector === '#stock-snapshot-result [data-snapshot-section]') return this.getElementById('stock-snapshot-result').sections || [];
      if (selector === '.page.active [id]') return [this.getElementById('kline-chart')];
      return [];
    }
  };
  const nav = routes.map(page => {const node = document.createElement('button'); node.dataset.page = page; return node;});
  const tools = ['overview', 'holders', 'stock-news', 'kline', 'backtest', 'screener'].map(tool => {const node = document.createElement('button'); node.dataset.tool = tool; return node;});
  const ctx = {
    document, URL, Date, Intl, console, currentUser: null, klineChart: null,
    currentKlineData: null, currentKlineTicker: '', klineDays: 180, stockNames: {},
    screenerTargets: ['original.TW'], chatOpen: true, positions: [],
    fmt: (value, digits = 2) => Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}),
    displayTicker: value => value, showToast: (...args) => toasts.push(args),
    showAuthModal: mode => calls.push({auth: mode}), renderPositions() {}, updateAuthUI() {},
    fetchMarketInsights: () => calls.push({market: true}), revealHomeOnce() {},
    apiCall: async (endpoint, method = 'GET', body) => {calls.push({endpoint, method, body}); return ctx.response(endpoint, method, body);},
    response: () => ({status: 'error', message: 'fake unavailable'}),
    requestAnimationFrame: fn => fn(), window: {innerWidth: 1440, matchMedia: () => ({matches: false}), addEventListener() {}},
    setTimeout: (fn, delay) => {timers.push({fn, delay}); return timers.length;},
    echarts: {
      init() {const chart = {options: [], disposed: false, resized: 0,
        setOption(option) {this.options.push(option);}, getOption() {return this.options[0];},
        dispose() {this.disposed = true;}, resize() {this.resized++;}}; charts.push(chart); return chart;},
      getInstanceByDom: () => ctx.klineChart
    }
  };
  vm.createContext(ctx);
  vm.runInContext(workspace
    + slice('const pageTitles = {', '// ============================\n// MOBILE SIDEBAR')
    + slice('async function loadVolumeSettings()', '// ============================\n// POSITIONS')
    + slice('async function logout()', 'function updateAuthUI()')
    + slice('function escapeRoutingText(', 'function renderTechTable(')
    + slice('function renderTechTable(', 'function sortTechTable(')
    + slice('function renderStockListHTML(', 'function insightNumber(')
    + slice('function safeNewsUrl(', 'async function fetchMarketInsights(')
    + slice('function insightNumber(', 'function safeNewsUrl(')
    + slice('function snapshotMeta(', 'function homeIndicatorHtml(')
    + slice('function setKlineDays(', '// ============================\n// NEWS ANALYSIS')
    + slice('async function fetchFundamentalsAndChips(', '// ============================\n// MODALS'), ctx);
  document.getElementById('page-war').classList.add('active');
  ctx.resetBacktestCosts(); document.getElementById('backtest-days').value = '365';
  document.getElementById('sub-indicator-select').value = 'volume';
  return {ctx, document, el: id => document.getElementById(id), calls, toasts, charts, tools, nav, events, timers,
    run: code => vm.runInContext(code, ctx), emit: event => (events[event.type || 'keydown'] || []).forEach(fn => fn(event))};
}
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done;}); return {promise, resolve};};
const flush = async () => {await Promise.resolve(); await Promise.resolve();};
const snapshot = (ticker = '6488.TWO') => ({status: 'partial', data: {
  identity: {ticker, symbol: ticker, name: '<img src=x>', market: '上櫃'},
  price: {available: true, close: 100, previous_close: 99, change: 1, change_percent: 1, as_of: '2026-10-09', source: 'fake official', methodology: 'daily'},
  industry_context: {available: false, code: 'industry_not_applicable', source: 'fixture'},
  ownership: {available: true, large_holder_ratio: 42, large_holder_accounts: 10, small_holder_ratio: 20, breakdown: [{label: '400張', ratio: 42}], as_of: '2026-10-08', source: '集保 fixture', methodology: 'weekly'},
  news_attention: {available: true, articles: [{title: '<script>news</script>', link: 'javascript:bad', source: 'fixture', published: '2026-10-09'}], mention_count: 1, source_count: 1, source: 'RSS fixture', methodology: '72h'}
}, warnings: [{code: 'fixture-limitation'}]});
const candles = ticker => ({status: 'success', ticker, candles: [{time: 1700000000, open: 10, close: 11, low: 9, high: 12}], ma5: [], ma20: [], ma60: [], volumes: [{value: 1000, color: '#26a69a'}], macd: [], macd_signal: [], macd_hist: [], kd_k: [], kd_d: [], rsi: []});

(async () => {
  // AC01/02/03/08/12: entry, routes, script ordering and original control contracts.
  assert.match(html, /id="landing"[^>]*hidden/);
  assert.match(html, /class="app active"/); assert.match(html, /id="page-war"[^>]*class="page active"|class="page active"[^>]*id="page-war"/);
  assert.equal((html.match(/class="nav-section"/g) || []).length, 4);
  for (const route of routes) assert.match(html, new RegExp(`data-page="${route}"`));
  assert.ok(html.indexOf('src="/static/workspace.js"') < html.indexOf('const pageTitles ='));
  assert.match(html, /typeof initWorkspace === 'function'/);
  assert.match(html, /全市場技術分析/); assert.match(html, /全市場新聞/);
  for (const days of [30, 90, 180, 365]) assert.match(html, new RegExp(`data-days="${days}"`));
  for (const indicator of ['volume', 'macd', 'kd', 'rsi']) assert.match(html, new RegExp(`value="${indicator}"`));
  for (const id of ['stress-result', 'btn-stress', 'btn-news', 'btn-sentiment', 'btn-screener', 'auth-modal', 'stress-history-modal', 'chat-panel']) assert.ok(html.includes(`id="${id}"`), id);
  assert.match(css, /\.table-scroll\{[^}]*overflow(?:-x)?:\s*auto/); assert.match(css, /@media[^\n]*768/); assert.match(css, /prefers-reduced-motion/);
  assert.match(html, /'1': 'war'.*'9': 'screener'/); assert.match(html, /e.key === '\/'/);
  const clearChatButton = html.match(/<button\b[^>]*onclick="clearChat\(\)"[^>]*>([\s\S]*?)<\/button>/);
  assert.ok(clearChatButton, 'original clear-chat action retained');
  assert.ok(clearChatButton[1].replace(/<[^>]*>/g, '').trim(), 'clear-chat action must have a visible label');

  // Reviewer regression: invoke BOTH actual click handlers with the real moved
  // input selector membership, rather than testing only the shared helper.
  for (const entry of ['technical', 'screener']) {
    for (const initial of ['', '6488.TWO']) {
      const click = harness();
      if (initial) click.ctx.setWorkspaceTicker(initial);
      const clickedStock = {ticker: '2330.TW', name: 'fixture', price: 100, score: 50,
        advice: 'fixture', valuation: 'fixture', signals: [], pct_5d: 1};
      if (entry === 'technical') {
        click.ctx.renderTechTable([clickedStock]);
        click.el('tech-table').rows[0].listeners.click();
      } else {
        click.ctx.response = () => ({status: 'success', data: [{
          target: {ticker: '6488.TWO'}, supply_chain: {}, evaluated_stocks: [clickedStock]
        }]});
        await click.ctx.runScreener();
        click.calls.length = 0;
        click.el('screener-result').stockLinks[0].listeners.click();
      }
      assert.equal(click.run('workspaceTicker'), '2330.TW', `${entry}: clicked ticker overrides ${initial || 'empty'} context`);
      for (const id of ['stock-snapshot-ticker', 'kline-ticker', 'backtest-ticker', 'workspace-ticker-screener']) assert.equal(click.el(id).value, '2330.TW');
      assert.ok(click.el('page-kline').classList.contains('active'));
      assert.equal(click.calls.length, 0, 'manual result load remains deferred');
      const queued = click.timers.find(timer => timer.delay === 100);
      assert.ok(queued, 'actual result click queues original chart/analysis action');
      click.ctx.response = endpoint => endpoint.startsWith('/kline/') ? candles('2330.TW') : {status: 'error'};
      queued.fn(); for (let turn = 0; turn < 5; turn++) await flush();
      assert.equal(click.calls.filter(call => call.endpoint === '/kline/2330.TW?days=180').length, 1);
      const analysis = click.calls.filter(call => call.endpoint === '/analyze');
      assert.equal(analysis.length, 1); assert.equal(analysis[0].body.targets[0].id, '2330.TW');
    }
  }
  for (const nextTicker of ['6488.TWO', '2330.TW']) {
    const rapid = harness(); rapid.ctx.openWorkspaceKline('2330.TW');
    rapid.ctx.setWorkspaceTicker('6488.TWO');
    if (nextTicker === '2330.TW') rapid.ctx.setWorkspaceTicker(nextTicker);
    rapid.timers.find(timer => timer.delay === 100).fn(); await flush();
    assert.equal(rapid.calls.length, 0, 'changed epoch cancels deferred action even after selecting the original ticker again');
  }

  const h = harness(), {ctx, el, run, calls} = h;
  // About isolation, focus, and drafts retained without GSAP or an API request.
  el('volume-tickers').value = '2330.TW,draft'; el('volume-webhook').value = 'test-only draft';
  ctx.openAbout(); assert.equal(el('.app').hidden, true); assert.equal(el('.app').inert, true); assert.equal(el('.app').style.display, 'none');
  assert.equal(h.document.activeElement, el('landing-cta')); assert.equal(el('chat-fab').hidden, true);
  ctx.closeAbout(); assert.equal(el('.app').hidden, false); assert.equal(el('.app').inert, false); assert.equal(el('landing').hidden, true);
  assert.equal(h.document.activeElement, el('#page-war .home-intro h2')); assert.equal(el('volume-webhook').value, 'test-only draft');
  assert.equal(calls.length, 0);
  for (const route of routes) {ctx.navigateTo(route); assert.ok(el('page-' + route).classList.contains('active')); assert.ok(h.document.title.endsWith(' - 股金往來'));}
  calls.length = 0;
  // AC05/07: validation and context transfer never start paid/tool analysis or mutate screener list.
  for (const invalid of ['', ' ', 'bad', '2330.US', '<img>', '2330.TW.TWO']) assert.equal(ctx.setWorkspaceTicker(invalid), false);
  assert.equal(ctx.setWorkspaceTicker(' 6488.two '), true);
  for (const id of ['stock-snapshot-ticker', 'kline-ticker', 'backtest-ticker', 'screener-target-input']) assert.equal(el(id).value, '6488.TWO');
  assert.equal(ctx.validWorkspaceTicker('2330'), '2330.TW'); assert.equal(ctx.validWorkspaceTicker('0050.TW'), '0050.TW');
  run('marketInsightsLoaded = true');
  for (const tool of ['overview', 'holders', 'stock-news', 'kline', 'backtest', 'screener']) ctx.switchWorkspaceTool(tool);
  assert.equal(calls.length, 0); assert.deepEqual(ctx.screenerTargets, ['original.TW']);
  const stale = ctx.researchRequest('snapshot'); ctx.setWorkspaceTicker('2330.TW'); assert.equal(ctx.researchRequestCurrent(stale), false);
  const older = ctx.researchRequest('snapshot'); ctx.researchRequest('snapshot'); assert.equal(ctx.researchRequestCurrent(older), false);
  // AC06: real snapshot renders source/date/method, partial/ETF restriction, signs and safe articles.
  ctx.setWorkspaceTicker('6488.TWO'); ctx.response = () => snapshot(); await ctx.fetchStockSnapshot();
  assert.match(el('stock-snapshot-result').innerHTML, /6488.TWO.*&lt;img/s);
  assert.match(el('stock-snapshot-result').innerHTML, /\+1.00.*red-400|red-400.*\+1.00/s);
  for (const text of ['2026-10-09', 'fake official', 'daily', '不適用', 'ETF', 'fixture-limitation', '集保 fixture', 'RSS fixture', '&lt;script&gt;']) assert.ok(el('stock-snapshot-result').innerHTML.includes(text), text);
  assert.doesNotMatch(el('stock-snapshot-result').innerHTML, /<script>|<img|href="javascript:/);
  ctx.switchWorkspaceTool('holders'); assert.deepEqual(el('stock-snapshot-result').sections.map(node => node.hidden), [true, true, false, true]);
  ctx.switchWorkspaceTool('stock-news'); assert.deepEqual(el('stock-snapshot-result').sections.map(node => node.hidden), [true, true, true, false]);
  ctx.switchWorkspaceTool('overview'); assert.ok(el('stock-snapshot-result').sections.every(node => !node.hidden));
  // Late snapshot responses and wrong-server identities cannot paint a newly chosen stock.
  const slow = deferred(); ctx.response = () => slow.promise; const pending = ctx.fetchStockSnapshot();
  ctx.setWorkspaceTicker('2330.TW'); const cleared = el('stock-snapshot-result').textContent;
  slow.resolve(snapshot('6488.TWO')); await pending; assert.equal(el('stock-snapshot-result').textContent, cleared); assert.equal(el('btn-stock-snapshot').disabled, false);
  ctx.response = () => snapshot('6488.TWO'); await ctx.fetchStockSnapshot(); assert.match(el('stock-snapshot-result').textContent, /不符/); assert.equal(el('btn-stock-snapshot').disabled, false);
  const s1 = deferred(), s2 = deferred(); let count = 0; ctx.response = () => (++count === 1 ? s1 : s2).promise;
  const p1 = ctx.fetchStockSnapshot(), p2 = ctx.fetchStockSnapshot(); s2.resolve(snapshot('2330.TW')); await p2;
  const newest = el('stock-snapshot-result').innerHTML; s1.resolve({status: 'error'}); await p1; assert.equal(el('stock-snapshot-result').innerHTML, newest);
  ctx.response = () => ({status: 'error'}); await ctx.fetchStockSnapshot(); assert.equal(el('btn-stock-snapshot').disabled, false);
  // AC05/08: Kline manual analysis, price/chips, subcharts, periods and every race seam.
  ctx.setWorkspaceTicker('6488.TWO'); calls.length = 0;
  ctx.response = endpoint => endpoint.startsWith('/kline/') ? candles('6488.TWO') : endpoint === '/analyze' ? {status: 'success', data: [{price: 123.4, advice: '<img>', score: 60, valuation: 'fixture', signals: ['safe']}]} : endpoint.startsWith('/api/fundamentals/') ? {status: 'success', data: {eps: 7, pe: 20, dividendYield: 0.03}} : {data: {'6488.TWO': {Foreign: 2000, Trust: -1000, as_of: '2026-10-09', market: '上櫃', source: 'https://example.invalid'}}};
  await ctx.fetchKline(); await flush();
  assert.ok(calls.some(call => call.endpoint === '/kline/6488.TWO?days=180')); assert.equal(calls.filter(call => call.endpoint === '/analyze').length, 1);
  assert.match(el('kline-signals').innerHTML, /123.40.*&lt;img&gt;/s); assert.equal(el('fund-eps').textContent, '7');
  assert.match(el('chip-content').innerHTML, /\+2.00.*-1.00.*2026-10-09.*1,000/s);
  for (const indicator of ['volume', 'macd', 'kd', 'rsi']) {el('sub-indicator-select').value = indicator; ctx.updateSubChart(); assert.ok(ctx.klineChart.options.at(-1).series.length > 4);}
  const lateAnalysis = deferred(), lateFund = deferred(), lateChip = deferred();
  ctx.response = endpoint => endpoint.startsWith('/kline/') ? candles('6488.TWO') : endpoint === '/analyze' ? lateAnalysis.promise : endpoint.startsWith('/api/fundamentals/') ? lateFund.promise : lateChip.promise;
  const oldKline = ctx.fetchKline(); await flush(); ctx.setWorkspaceTicker('2330.TW');
  const clearSignals = el('kline-signals').innerHTML, clearTitle = el('kline-chart-title').textContent;
  lateAnalysis.resolve({status: 'success', data: [{price: 999}]}); lateFund.resolve({status: 'success', data: {eps: 999}}); lateChip.resolve({data: {'6488.TWO': {Foreign: 999000}}});
  await oldKline; await flush(); assert.equal(el('kline-signals').innerHTML, clearSignals); assert.equal(el('kline-chart-title').textContent, clearTitle); assert.notEqual(el('fund-eps').textContent, '999'); assert.doesNotMatch(el('chip-content').innerHTML, /999.00/);
  const lateChart = deferred(); ctx.response = endpoint => endpoint.startsWith('/kline/') ? lateChart.promise : {status: 'error'};
  const oldChart = ctx.fetchKline(); ctx.setWorkspaceTicker('6488.TWO'); const title = el('kline-chart-title').textContent;
  lateChart.resolve(candles('2330.TW')); await oldChart; assert.equal(el('kline-chart-title').textContent, title);
  ctx.response = () => ({status: 'error'}); await ctx.fetchKline(); await flush();
  for (const id of ['fund-eps', 'fund-pe', 'fund-yield', 'fund-rev', 'fund-cap']) assert.equal(el(id).textContent, '來源暫缺');
  delete ctx.echarts; ctx.response = endpoint => endpoint.startsWith('/kline/') ? candles('6488.TWO') : {status: 'error'}; await ctx.fetchKline(); assert.match(el('kline-chart-title').textContent, /元件暫缺/);
  // Backtest retains costs/performance/trades/limitations and discards late output.
  const bt = {status: 'success', ticker: '6488.TWO', strategy_return: 5, buy_hold_return: 2, outperformance: 3, max_drawdown: -2, win_rate: 50, trades: [{action: 'BUY', date: '2026-10-01', shares: 10, price: 100, commission: 20, tax: 0}], costs: {commission_rate: 0.001425, min_commission: 20, sell_tax_rate: 0.003}, limitations: ['test limit'], initial_capital: 100000};
  ctx.response = () => bt; await ctx.runBacktest(); assert.match(el('backtest-result').innerHTML, /買入持有.*NT\$.*BUY.*test limit/s); assert.equal(el('btn-backtest').disabled, false);
  const lastCall = calls.at(-1); assert.equal(lastCall.method, 'POST'); assert.equal(lastCall.body.ticker, '6488.TWO'); assert.equal(lastCall.body.min_commission, 20);
  const oldBt = deferred(); ctx.response = () => oldBt.promise; const oldRun = ctx.runBacktest(); ctx.setWorkspaceTicker('2330.TW'); const reset = el('backtest-result').textContent;
  oldBt.resolve(bt); await oldRun; assert.equal(el('backtest-result').textContent, reset); assert.equal(el('btn-backtest').disabled, false);
  ctx.response = () => ({status: 'error', message: '<img>'}); await ctx.runBacktest(); assert.match(el('backtest-result').innerHTML, /&lt;img&gt;/); assert.equal(el('btn-backtest').disabled, false);

  // AC09/10/11: actual notifications, saved GET state vs unsaved drafts, recovery and races.
  const n = harness(), nc = n.ctx, ne = n.el, nr = n.run;
  await nc.loadVolumeSettings(); assert.match(ne('volume-settings-state').textContent, /登入/); assert.equal(ne('volume-settings-form').style.display, 'none');
  ne('volume-settings-state').children[0].listeners.click(); assert.deepEqual(n.calls.at(-1), {auth: 'login'});
  nc.currentUser = {id: 'test-account-a'}; nc.resetNotificationAccount();
  const saved = {status: 'success', tickers: ['2330.TW'], webhook_configured: true, webhook_readable: true};
  nc.response = () => saved; await nc.loadVolumeSettings(); assert.match(ne('volume-step-stocks').textContent, /1 \/ 20/); assert.match(ne('volume-step-discord').textContent, /未驗證/); assert.match(ne('volume-step-complete').textContent, /不代表通知已送達/);
  nr("notificationCandidate = '6488.TWO'"); n.calls.length = 0; nc.applyNotificationCandidate();
  assert.equal(ne('volume-tickers').value, '2330.TW,6488.TWO'); assert.match(ne('volume-draft-state').textContent, /未儲存/); assert.match(ne('volume-step-stocks').textContent, /1 \/ 20/); assert.equal(n.calls.length, 0);
  nr("notificationCandidate = '6488.TWO'"); nc.applyNotificationCandidate(); assert.equal(ne('volume-tickers').value, '2330.TW,6488.TWO');
  ne('volume-webhook').value = 'test-only draft'; nc.openAbout(); nc.closeAbout(); nc.openNotificationSettings(); assert.equal(ne('volume-webhook').value, 'test-only draft'); assert.equal(n.calls.length, 0);
  const twenty = Array.from({length: 20}, (_, i) => `${1000 + i}.TW`);
  ne('volume-tickers').value = twenty.join(','); nr("notificationCandidate = '6488.TWO'"); nc.applyNotificationCandidate(); assert.equal(ne('volume-tickers').value, twenty.join(',')); assert.match(ne('volume-draft-state').textContent, /20/);
  ne('volume-tickers').value += ',6488.TWO'; await nc.saveVolumeSettings(); assert.equal(n.calls.length, 0); assert.match(ne('volume-settings-state').textContent, /最多 20/);
  // Empty URL preserves it: null means no replacement; removal is an explicit independent flag.
  ne('volume-tickers').value = twenty.join(','); ne('volume-webhook').value = ''; ne('volume-remove-webhook').checked = false;
  const confirm = deferred(); nc.response = (_endpoint, method) => method === 'PUT' ? {status: 'success'} : confirm.promise;
  const saving = nc.saveVolumeSettings(); await flush(); assert.equal(n.calls[0].method, 'PUT'); assert.equal(n.calls[0].body.webhook, null); assert.equal(n.calls[0].body.remove_webhook, false);
  assert.equal(n.calls[1].method, 'GET'); assert.match(ne('volume-step-stocks').textContent, /1 \/ 20/); assert.equal(ne('volume-save-btn').disabled, true);
  confirm.resolve({...saved, tickers: twenty}); await saving; assert.match(ne('volume-step-stocks').textContent, /20 \/ 20/); assert.equal(ne('volume-save-btn').disabled, false);
  ne('volume-webhook').value = 'https://example.invalid/test-only'; ne('volume-remove-webhook').checked = true;
  nc.response = (_endpoint, method) => method === 'PUT' ? {status: 'success'} : {...saved, webhook_configured: false}; await nc.saveVolumeSettings();
  const put = n.calls.filter(call => call.method === 'PUT').at(-1); assert.equal(put.body.webhook, 'https://example.invalid/test-only'); assert.equal(put.body.remove_webhook, true); assert.equal(ne('volume-webhook').value, '');
  for (const reason of ['encryption_not_configured', 'decryption_failed']) {
    nc.response = () => ({...saved, webhook_readable: false, recovery_reason: reason}); await nc.loadVolumeSettings(); assert.match(ne('volume-step-discord').textContent, /恢復/); assert.match(ne('volume-webhook-state').textContent, reason === 'encryption_not_configured' ? /管理員.*加密/ : /重新輸入.*移除/); assert.equal(ne('volume-settings-form').style.display, 'block'); assert.equal(ne('volume-webhook').value, '');
  }
  nc.response = () => ({...saved, tickers: [], webhook_configured: false}); await nc.loadVolumeSettings(); assert.match(ne('volume-settings-state').textContent, /空/); assert.match(ne('volume-step-complete').textContent, /股票清單.*Webhook/);
  nc.response = () => ({status: 'error', message: '<script>test failure</script>'}); await nc.loadVolumeSettings(); assert.equal(ne('volume-settings-state').innerHTML, ''); assert.equal(ne('volume-settings-state').children[0].textContent, '重新載入');
  nc.response = () => saved; await ne('volume-settings-state').children[0].listeners.click(); assert.equal(ne('volume-settings-form').style.display, 'block');
  nc.response = () => ({status: 'error', message: 'fake save failed'}); await nc.saveVolumeSettings(); assert.match(ne('volume-settings-state').textContent, /fake save failed/); assert.equal(ne('volume-save-btn').disabled, false);
  nc.response = () => Promise.reject(new Error('fake transport rejection')); await assert.rejects(nc.saveVolumeSettings(), /fake transport/); assert.equal(ne('volume-save-btn').disabled, false);
  // A pending prior-account GET/PUT cannot leak draft, settings or progress after reset/logout.
  const accountGet = deferred(); nc.response = () => accountGet.promise; const loading = nc.loadVolumeSettings();
  nc.currentUser = {id: 'test-account-b'}; nc.resetNotificationAccount(); accountGet.resolve(saved); await loading; assert.equal(ne('volume-tickers').value, ''); assert.equal(nr('notificationSaved'), null);
  nc.response = () => saved; await nc.loadVolumeSettings(); ne('volume-webhook').value = 'test-only draft';
  const accountPut = deferred(); nc.response = () => accountPut.promise; const pendingSave = nc.saveVolumeSettings();
  nc.currentUser = null; nc.resetNotificationAccount(); accountPut.resolve({status: 'success'}); await pendingSave; assert.equal(ne('volume-webhook').value, ''); assert.equal(nr('notificationSaved'), null); assert.equal(ne('volume-save-btn').disabled, false);
  nc.currentUser = {id: 'test-account-a'}; nc.response = () => saved; await nc.loadVolumeSettings(); ne('volume-webhook').value = 'test-only draft';
  nc.response = () => ({status: 'error'}); await nc.logout(); assert.ok(nc.currentUser); assert.equal(ne('volume-webhook').value, 'test-only draft');
  nc.response = () => ({status: 'success'}); await nc.logout(); assert.equal(nc.currentUser, null); assert.equal(ne('volume-webhook').value, ''); assert.equal(ne('volume-tickers').value, '');
  // AC12: real focus trap wraps both directions; disabled/hidden controls excluded.
  const first = n.document.createElement('button'), last = n.document.createElement('input');
  n.document.modal = {querySelectorAll: () => [first, last], contains: node => [first, last].includes(node)};
  let prevented = 0; n.document.activeElement = last; n.emit({key: 'Tab', preventDefault: () => prevented++}); assert.equal(n.document.activeElement, first);
  n.emit({key: 'Tab', shiftKey: true, preventDefault: () => prevented++}); assert.equal(n.document.activeElement, last); assert.equal(prevented, 2);
  console.log('Integrated UI AC01-12 offline checks passed: routes/About/focus, shared ticker/manual tools, snapshot/charts/analysis/chips/backtest races, saved notification drafts/recovery/account isolation.');
})().catch(error => {console.error(error); process.exitCode = 1;});
