// Production workspace helpers against an offline DOM and deferred API replies.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('static/workspace.js', 'utf8');
const html = fs.readFileSync('static/index.html', 'utf8');
const css = fs.readFileSync('static/workspace.css', 'utf8');
const plain = x => JSON.parse(JSON.stringify(x));

class Element {
  constructor(id, owner) {
    this.id = id; this.owner = owner; this.value = ''; this.disabled = false;
    this.required = false; this.dataset = {}; this.style = {}; this.listeners = {};
    this.attributes = {}; this._html = ''; this._text = ''; this.children = [];
    this.classList = {add() {}, remove() {}, contains: () => false};
  }
  set innerHTML(value) {this._html = String(value); this._text = '';}
  get innerHTML() {return this._html;}
  set textContent(value) {this._text = String(value); this._html = ''; this.children = [];}
  get textContent() {return this._text;}
  replaceChildren(...nodes) {this.textContent = ''; this.children = nodes;}
  setAttribute(key, value) {this.attributes[key] = String(value);}
  removeAttribute(key) {delete this.attributes[key];}
  addEventListener(name, fn) {this.listeners[name] = fn;}
  after() {} remove() {} replaceWith() {}
  querySelector(selector) {
    this.local ||= new Map();
    if (!this.local.has(selector)) this.local.set(selector, new Element(selector, this.owner));
    return this.local.get(selector);
  }
  querySelectorAll(selector) {
    if (selector !== '[data-tool]') return [];
    return [...this._html.matchAll(/data-tool="([^"]+)"/g)].map(match => {
      const node = new Element('tool', this.owner); node.dataset.tool = match[1]; return node;
    });
  }
  reset() {
    const ids = this.id === 'valuation-current-form'
      ? ['valuation-pe-low', 'valuation-pe-mid', 'valuation-pe-high']
      : ['bear', 'base', 'bull'].flatMap(name => [`valuation-${name}-eps`, `valuation-${name}-pe`]);
    ids.forEach(id => {this.owner.getElementById(id).value = '';});
    if (this.id === 'valuation-current-form') this.owner.getElementById('valuation-mode').value = 'auto';
  }
}

function harness() {
  const nodes = new Map(), calls = [], navigation = [];
  const document = {
    listeners: {},
    addEventListener(name, fn) {(this.listeners[name] ||= []).push(fn);},
    getElementById(id) {
      if (!nodes.has(id)) {
        const node = new Element(id, this);
        node.parentElement = new Element('parent', this);
        nodes.set(id, node);
      }
      return nodes.get(id);
    },
    createElement(tag) {return new Element(tag, this);},
    querySelector(selector) {return selector === '.page.active' ? {id: 'page-valuation'} : null;},
    querySelectorAll(selector) {
      if (selector === '.workspace-identity') return [this.getElementById('workspace-identity')];
      if (selector === '.workspace-ticker-input') return ['stock-snapshot-ticker', 'kline-ticker', 'backtest-ticker', 'workspace-ticker-valuation'].map(id => this.getElementById(id));
      return [];
    },
  };
  const ctx = {document, console, URL, Date, Intl, setTimeout, clearTimeout,
    window: {addEventListener() {}},
    klineChart: null, currentKlineData: null, currentKlineTicker: '',
    showToast() {}, displayTicker: x => x, revealHomeOnce() {},
    navigateTo: page => navigation.push(page),
    response: async () => ({status: 'error', message: 'offline fixture unavailable'}),
    apiCall: async (url, method = 'GET', body) => {
      calls.push({url, method, body: body && plain(body)});
      return ctx.response(url, method, body);
    },
  };
  vm.createContext(ctx);
  const start = html.indexOf('function escapeRoutingText(');
  const end = html.indexOf('function renderTechTable(', start);
  assert.ok(start >= 0 && end > start);
  vm.runInContext(source + '\n' + html.slice(start, end), ctx);
  const run = code => vm.runInContext(code, ctx);
  document.getElementById('valuation-mode').value = 'auto';
  ctx.initWorkspace();
  return {ctx, run, calls, navigation, el: id => document.getElementById(id)};
}

function payload(code = '2330', market = 'TW') {
  return {status: 'partial', ticker: `${code}.${market}`, data: {
    identity: {code, ticker: `${code}.${market}`, name: `${code} fixture`, market, ordinary: true},
    quote: {value: 100, freshness: 'fresh', as_of: '2026-10-23', source: 'official fixture', source_url: 'https://example.invalid/quote'},
    eps_ttm: {value: 5, status: 'available', basis: 'diluted', period_start: '2025-07-01', period_end: '2026-06-30', warnings: ['quarter_sum_approximation']},
    official_pe: {value: 22, as_of: '2026-10-23'}, official_ytd_eps: {value: 49.33}, vendor_ttm_eps: {value: 99, currency: 'TWD'},
    calculated_pe: 20, peer_reference: {status: 'unavailable', reason_code: 'insufficient_peers', count: 0},
    current_model: {status: 'unavailable', reason_code: 'pe_assumptions_required'},
    scenarios: [], forward_pe: null,
    eps_period_start: '2026-10-26', eps_period_end: '2027-10-25', horizon_end: '2027-10-26',
  }};
}
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done;}); return {resolve, promise};};
async function load(h, code = '2330', market = 'TW') {
  h.ctx.setWorkspaceTicker(`${code}.${market}`);
  h.ctx.response = async () => payload(code, market);
  await h.ctx.fetchValuation();
}

function availableModel(origin = 'industry_percentiles') {
  const out = payload();
  out.data.current_model = origin === 'user_assumption'
    ? {status: 'available', origin, low: 150, mid: 175, high: 200, pe_low: 30, pe_mid: 35, pe_high: 40, classification: 'below'}
    : {status: 'available', origin, low: 60, mid: 100, high: 140, pe_low: 12, pe_mid: 20, pe_high: 28, classification: 'within'};
  return out;
}

function selectManual(h, values = ['30', '35', '40']) {
  h.el('valuation-mode').value = 'manual';
  h.el('valuation-mode').listeners.change();
  ['low', 'mid', 'high'].forEach((key, index) => {h.el('valuation-pe-' + key).value = values[index];});
}

function enterScenarios(h) {
  [['bear', '4', '15'], ['base', '5.5', '20'], ['bull', '7', '25']].forEach(([name, eps, pe]) => {
    h.el(`valuation-${name}-eps`).value = eps;
    h.el(`valuation-${name}-pe`).value = pe;
  });
}

function withScenarios(out) {
  out.data.scenarios = [{name: 'bear', eps: 4, pe: 15, price: 60, price_change_pct: -40}, {name: 'base', eps: 5.5, pe: 20, price: 110, price_change_pct: 10}, {name: 'bull', eps: 7, pe: 25, price: 175, price_change_pct: 75}];
  out.data.forward_pe = 100 / 5.5;
  return out;
}

(async () => {
  // Static contracts: new tool is integrated; no synthetic/live claims or opinions panel.
  assert.match(html, /data-page="valuation"/);
  assert.match(html, /id="page-valuation"/);
  assert.match(source, /\['valuation','價格檢視'\]/);
  assert.match(html, /<script src="\/static\/workspace\.js\?v=price-inspector-20261026-2"><\/script>/);
  assert.match(css, /@media[^\n]*600[^\n]*valuation-scenarios/);
  const page = html.slice(html.indexOf('id="page-valuation"'), html.indexOf('id="page-insights"'));
  assert.doesNotMatch(page, /DEMO|範例公司|意見雷達/);
  for (const match of page.matchAll(/<input\b[^>]*>/g)) assert.doesNotMatch(match[0], /\bvalue=/);
  assert.match(page, /aria-live="polite"/);
  assert.match(page, /<label>[^<]+<input/);

  const h = harness();
  h.ctx.switchWorkspaceTool('valuation');
  assert.equal(h.navigation.at(-1), 'valuation');
  assert.equal(h.el('valuation-mode').value, 'auto');
  h.ctx.setWorkspaceTicker('2330.TW');
  assert.equal(h.el('valuation-mode').value, 'auto');
  for (const id of ['valuation-pe-low', 'valuation-pe-mid', 'valuation-pe-high', ...['bear', 'base', 'bull'].flatMap(n => [`valuation-${n}-eps`, `valuation-${n}-pe`])]) assert.equal(h.el(id).value, '');
  assert.ok(h.el('valuation-pe-low').disabled);
  h.el('valuation-mode').value = 'manual'; h.ctx.updateValuationMode();
  assert.equal(h.el('valuation-pe-low').disabled, false);
  assert.equal(h.el('valuation-pe-low').required, true);

  // GET A late success/error cannot replace B or leave B's buttons disabled.
  for (const staleReply of [payload('2330'), {status: 'error', message: 'old-A-error'}]) {
    const a = deferred(), b = deferred();
    const race = harness(); race.ctx.setWorkspaceTicker('2330.TW');
    race.ctx.response = url => url.includes('2330') ? a.promise : b.promise;
    const pendingA = race.ctx.fetchValuation();
    race.ctx.setWorkspaceTicker('6488.TWO');
    const pendingB = race.ctx.fetchValuation();
    b.resolve(payload('6488', 'TWO')); await pendingB;
    const before = race.el('valuation-metrics').innerHTML;
    a.resolve(staleReply); await pendingA;
    assert.equal(race.run('workspaceTicker'), '6488.TWO');
    assert.equal(race.el('valuation-metrics').innerHTML, before);
    assert.match(race.el('valuation-status').textContent, /6488/);
    assert.equal(race.el('btn-valuation').disabled, false);
    assert.equal(race.run('valuationSnapshot.identity.code'), '6488');
  }

  // Same-ticker repeated refresh obeys request version and canonical OTC resolution.
  const same = harness(); same.ctx.setWorkspaceTicker('6488.TW');
  const first = deferred(), second = deferred(); let count = 0;
  same.ctx.response = () => (++count === 1 ? first.promise : second.promise);
  const old = same.ctx.fetchValuation(), latest = same.ctx.fetchValuation();
  second.resolve(payload('6488', 'TWO')); await latest;
  first.resolve({status: 'error', message: 'old-refresh-error'}); await old;
  assert.equal(same.run('workspaceTicker'), '6488.TWO');
  assert.match(same.el('valuation-status').textContent, /6488/);

  // Switching stock clears every assumption/output and invalidates an in-flight POST.
  await load(h);
  for (const id of ['valuation-pe-low', 'valuation-pe-mid', 'valuation-pe-high', ...['bear', 'base', 'bull'].flatMap(n => [`valuation-${n}-eps`, `valuation-${n}-pe`])]) h.el(id).value = '42';
  const delayed = deferred(); h.ctx.response = () => delayed.promise;
  const oldCalc = h.ctx.calculateValuationRequest({current_pe: {low: 16, mid: 20, high: 24}}, 'valuation-current-result', 'btn-valuation-current');
  h.ctx.setWorkspaceTicker('6488.TWO');
  const cleared = h.el('valuation-current-result').textContent;
  delayed.resolve(payload('2330')); await oldCalc;
  assert.equal(h.el('valuation-current-result').textContent, cleared);
  assert.equal(h.run('valuationSnapshot'), null);
  assert.equal(h.el('valuation-base-eps').value, '');
  assert.equal(h.el('valuation-pe-mid').value, '');
  assert.equal(h.el('valuation-mode').value, 'auto');
  assert.equal(h.el('btn-valuation-current').disabled, false);
  assert.equal(h.el('btn-valuation-scenarios').disabled, false);
  assert.equal(h.el('valuation-metrics').innerHTML, '');

  // Editing assumptions invalidates an outstanding calculation, including its error.
  for (const response of [payload(), {status: 'error', message: 'old-assumption-error'}]) {
    const edit = harness(); await load(edit);
    const wait = deferred(); edit.ctx.response = () => wait.promise;
    const work = edit.ctx.calculateValuationRequest({scenarios: []}, 'valuation-scenario-result', 'btn-valuation-scenarios');
    edit.el('page-valuation').listeners.input({target: {closest: () => true}});
    const text = edit.el('valuation-scenario-result').textContent;
    wait.resolve(response); await work;
    assert.equal(edit.el('valuation-scenario-result').textContent, text);
    assert.match(text, /已變更/);
    assert.equal(edit.el('btn-valuation-scenarios').disabled, false);
  }

  // Future scenarios must keep the selected current manual model and its exact inputs.
  const manual = harness(); await load(manual);
  selectManual(manual); enterScenarios(manual);
  manual.ctx.response = async () => availableModel('user_assumption');
  await manual.ctx.submitCurrentValuation({preventDefault() {}});
  assert.match(manual.el('valuation-current-result').innerHTML, /低於假設區間/);
  manual.ctx.response = async (url, method, body) => withScenarios(availableModel(body.current_pe ? 'user_assumption' : 'industry_percentiles'));
  await manual.ctx.submitValuationScenarios({preventDefault() {}});
  assert.deepEqual(manual.calls.at(-1).body.current_pe, {low: 30, mid: 35, high: 40});
  assert.deepEqual(manual.calls.at(-1).body.scenarios, [{eps: 4, pe: 15}, {eps: 5.5, pe: 20}, {eps: 7, pe: 25}]);
  assert.equal(manual.el('valuation-mode').value, 'manual');
  assert.deepEqual(['low', 'mid', 'high'].map(key => manual.el('valuation-pe-' + key).value), ['30', '35', '40']);
  for (const text of ['150.00', '200.00', '低於假設區間', '使用者手動倍數', '30.00／35.00／40.00']) assert.ok(manual.el('valuation-current-result').innerHTML.includes(text), text);
  assert.doesNotMatch(manual.el('valuation-current-result').innerHTML, /官方同產業倍數分位|相對本模型：區間內/);
  assert.match(manual.el('valuation-scenario-result').innerHTML, /175.00/);

  // An unrelated invalid current draft cannot block future scenarios or display an auto classification.
  for (const draft of [['', '', ''], ['30', '', '40'], ['40', '35', '30'], ['30', 'NaN', '40'], ['30', '35', '10001']]) {
    const independent = harness(); await load(independent);
    selectManual(independent, draft); enterScenarios(independent);
    independent.ctx.response = async () => withScenarios(availableModel());
    await independent.ctx.submitValuationScenarios({preventDefault() {}});
    assert.equal(independent.calls.at(-1).method, 'POST');
    assert.equal(Object.hasOwn(independent.calls.at(-1).body, 'current_pe'), false);
    assert.match(independent.el('valuation-scenario-result').innerHTML, /110.00/);
    assert.match(independent.el('valuation-current-result').textContent, /尚未套用.*手動輸入.*檢視今日區間/);
    assert.equal(independent.el('valuation-current-result').innerHTML, '');
    assert.deepEqual(['low', 'mid', 'high'].map(key => independent.el('valuation-pe-' + key).value), draft);
    assert.equal(independent.el('btn-valuation-current').disabled, false);
    assert.equal(independent.el('btn-valuation-scenarios').disabled, false);
  }

  // Refresh preserves the manual draft while clearing the old classification until reapplication.
  const refreshing = deferred(); manual.ctx.response = () => refreshing.promise;
  const refreshWork = manual.ctx.fetchValuation();
  assert.match(manual.el('valuation-scenario-result').textContent, /資料更新中/);
  refreshing.resolve(availableModel()); await refreshWork;
  assert.match(manual.el('valuation-scenario-result').textContent, /資料已更新.*手動假設.*計算三種情境/);
  assert.doesNotMatch(manual.el('valuation-scenario-result').textContent, /資料更新中/);
  assert.equal(manual.el('valuation-mode').value, 'manual');
  assert.deepEqual(['low', 'mid', 'high'].map(key => manual.el('valuation-pe-' + key).value), ['30', '35', '40']);
  assert.match(manual.el('valuation-current-result').textContent, /尚未套用.*檢視今日區間/);
  assert.equal(manual.el('valuation-current-result').innerHTML, '');
  manual.ctx.response = async () => availableModel('user_assumption');
  await manual.ctx.submitCurrentValuation({preventDefault() {}});
  assert.deepEqual(manual.calls.at(-1).body, {current_pe: {low: 30, mid: 35, high: 40}});
  assert.match(manual.el('valuation-current-result').innerHTML, /使用者手動倍數/);
  assert.match(manual.el('valuation-current-result').innerHTML, /低於假設區間/);

  // A mode change invalidates a pending auto calculation, including its error and button state.
  for (const response of [availableModel(), {status: 'error', message: 'late-auto-error'}]) {
    const modeRace = harness(); await load(modeRace);
    const late = deferred(); modeRace.ctx.response = () => late.promise;
    const work = modeRace.ctx.submitCurrentValuation({preventDefault() {}});
    assert.equal(modeRace.el('btn-valuation-current').disabled, true);
    selectManual(modeRace);
    const pendingText = modeRace.el('valuation-current-result').textContent;
    const pendingScenario = modeRace.el('valuation-scenario-result').textContent;
    assert.match(pendingText, /來源已變更/);
    assert.equal(modeRace.el('btn-valuation-current').disabled, false);
    late.resolve(response); await work;
    assert.equal(modeRace.el('valuation-current-result').textContent, pendingText);
    assert.equal(modeRace.el('valuation-scenario-result').textContent, pendingScenario);
    assert.equal(modeRace.el('valuation-current-result').innerHTML, '');
    assert.equal(modeRace.el('valuation-mode').value, 'manual');
    assert.equal(modeRace.el('btn-valuation-current').disabled, false);
    assert.equal(modeRace.el('btn-valuation-scenarios').disabled, false);
  }

  // Failure + retry and wrong-stock envelopes recover without stale metrics.
  const retry = harness(); retry.ctx.setWorkspaceTicker('2330.TW');
  retry.ctx.response = async () => ({status: 'unavailable', message: 'fixture down'});
  await retry.ctx.fetchValuation();
  assert.match(retry.el('valuation-status').textContent, /fixture down/);
  assert.equal(retry.el('btn-valuation').disabled, false);
  retry.ctx.response = async () => payload('6488', 'TWO');
  await retry.ctx.fetchValuation();
  assert.match(retry.el('valuation-status').textContent, /不符/);
  assert.equal(retry.run('valuationSnapshot'), null);
  retry.ctx.response = async () => payload(); await retry.ctx.fetchValuation();
  assert.equal(retry.run('valuationSnapshot.identity.code'), '2330');

  // Stale comparison dates, Forward PE vs exit multiple, and source escaping.
  const scenario = harness(); await load(scenario);
  const out = payload(); out.data.quote.freshness = 'stale'; out.data.quote.as_of = '2026-10-22';
  out.data.scenarios = [{name: 'bear', eps: 4, pe: 15, price: 60, price_change_pct: -40}, {name: 'base', eps: 5.5, pe: 20, price: 110, price_change_pct: 10}, {name: 'bull', eps: 7, pe: 25, price: 175, price_change_pct: 75}];
  out.data.forward_pe = 100 / 5.5;
  out.data.current_model = {status: 'unavailable', reason_code: 'quote_stale'};
  scenario.ctx.response = async () => out;
  await scenario.ctx.calculateValuationRequest({scenarios: [{eps: 4, pe: 15}, {eps: 5.5, pe: 20}, {eps: 7, pe: 25}]}, 'valuation-scenario-result', 'btn-valuation-scenarios');
  const rendered = scenario.el('valuation-scenario-result').innerHTML;
  for (const text of ['60.00', '110.00', '175.00', '2026-10-22', '過期', '18.18', 'Forward P/E']) assert.ok(rendered.includes(text), text);
  assert.match(scenario.el('valuation-status').textContent, /停止今日分類/);
  const malicious = payload(); malicious.data.quote.source = '<img src=x onerror=alert(1)>';
  malicious.data.quote.source_url = 'javascript:alert(1)';
  scenario.ctx.renderValuation(malicious.data);
  assert.match(scenario.el('valuation-sources').innerHTML, /&lt;img/);
  assert.doesNotMatch(scenario.el('valuation-sources').innerHTML, /<img|href="javascript:/);
  const closure = payload();
  closure.data.quote.as_of = '2026-10-22';
  closure.data.quote.calendar_evidence = {expected_completed_trading_day: '2026-10-22', exception_version: 'offline-closure-v1', methodology: '年度休市加有來源的臨時休市',
    used_exceptions: [{date: '2026-10-23', market_scope: ['TW'], reason: '離線休市證據', announced_at: '2026-10-22', verified_at: '2026-10-26',
      sources: [{market_scope: ['TW'], source_url: 'https://www.twse.com.tw/fixture/notice.pdf'}]}]};
  scenario.ctx.renderValuation(closure.data);
  assert.match(scenario.el('valuation-status').textContent, /已納入有來源的臨時休市/);
  for (const text of ['offline-closure-v1', '2026-10-22', '2026-10-23', '2026-10-26', '休市證據', 'https://www.twse.com.tw/fixture/notice.pdf']) assert.ok(scenario.el('valuation-sources').innerHTML.includes(text), text);
  console.log('PASS: valuation empty inputs, integrated navigation, GET/POST races, resets, retries, canonical suffix, source safety, stale scenario disclosure, manual/current scenario consistency and refresh/mode races');
})().catch(error => {console.error(error); process.exitCode = 1;});
