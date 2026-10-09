// Execute the actual homepage helpers using a fake DOM; no network or credentials.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('static/index.html', 'utf8');
for (const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) new vm.Script(script[1]);
const slice = (start, end) => {
  assert.ok(html.includes(start) && html.includes(end), 'source seams must exist');
  return html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start)));
};
const source = slice('let homeOverviewLoading', 'function calendarReadableSourceUrl(')
  + slice('function escapeRoutingText(', 'function renderTechTable(')
  + slice('function safeNewsUrl(', 'async function fetchMarketInsights(')
  + slice('function homeIndicatorHtml(', 'async function fetchFundamentalsAndChips(');
const decode = text => text.replace(/&(amp|lt|gt|quot|#39);/g, (_, key) => ({amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'"})[key]);
class Element {
  constructor(tag) {this.tag = tag; this.children = []; this.style = {}; this.dataset = {}; this.disabled = false; this.listeners = {}; this.markup = ''; this.text = '';}
  set textContent(value) {this.text = String(value); this.children = []; this.markup = '';}
  get textContent() {return this.text + this.children.map(child => child.textContent).join('');}
  set innerHTML(value) {this.markup = value; this.text = ''; this.children = [];}
  get innerHTML() {return this.markup;}
  appendChild(node) {this.children.push(node); return node;}
  append(...nodes) {nodes.forEach(node => this.appendChild(node));}
  replaceChildren(...nodes) {this.text = ''; this.markup = ''; this.children = []; this.append(...nodes);}
  addEventListener(event, callback) {this.listeners[event] = callback;}
  querySelectorAll(selector) {
    assert.equal(selector, 'button[data-home-ticker]');
    this.buttons = [...this.markup.matchAll(/data-home-ticker="([^"]*)"/g)].map(match => {
      const button = new Element('button'); button.dataset.homeTicker = decode(match[1]); return button;
    });
    return this.buttons;
  }
}
const elements = new Map();
const el = id => {if (!elements.has(id)) elements.set(id, new Element('div')); return elements.get(id);};
let responses = {}, calls = [], quickSearchCalls = 0;
const context = {URL, Date, Intl, console, fmt: value => Number(value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}),
  quickSearch: () => quickSearchCalls++,
  document: {getElementById: el, createElement: tag => new Element(tag), createTextNode: text => {const node = new Element('#text'); node.textContent = text; return node;}},
  apiCall: async endpoint => {calls.push(endpoint); const result = responses[endpoint]; return typeof result === 'function' ? result() : result || {status: 'error', message: 'fake unavailable'};}};
vm.createContext(context); vm.runInContext(source, context);
const allNodes = root => [root, ...root.children.flatMap(allNodes)];
const count = (text, pattern) => (text.match(pattern) || []).length;
(async () => {
  // AC-01/05: Missing prices stay unavailable; explicit dates remain Taipei.
  for (const bad of [null, undefined, '', ' ', false, 'NaN', 'Infinity']) assert.equal(context.homeFinite(bad), null);
  assert.equal(context.homeFinite('0'), 0);
  assert.equal(context.homeTimestamp('2026-02-30'), null);
  assert.equal(context.homeTimestamp('2025-01-01T12:00:00'), null);
  assert.equal(context.homeTimestamp('2999-01-01T12:00:00Z'), null);
  assert.match(context.homeDateLabel('2025-01-01T04:00:00Z'), /12:00 台北/);
  assert.equal(context.homeDateLabel('2025-01-01'), '2025-01-01');
  assert.equal(context.homeDateLabel(null), '日期未提供');
  const missing = context.homeIndicatorHtml('<img src=x>', {price: null, change: 0, pct_change: 0});
  assert.match(missing, /&lt;img src=x&gt;/); assert.match(missing, /行情暫缺/); assert.doesNotMatch(missing, /0\.00|<img/);
  const macro = Object.fromEntries(['台積電 ADR', '輝達 NVDA', '日經 225', '韓國綜合', '台灣加權', '費城半導體', 'S&P 500', 'VIX 恐慌'].map(name => [name, {price: 100, change: 1, pct_change: 1, as_of: '2025-01-01', source: 'fixture'}]));
  responses['/macro'] = {status: 'success', data: macro};
  await context.fetchRankings();
  const indicatorMarkup = el('rankings-content').innerHTML;
  assert.equal(count(indicatorMarkup.split('<details')[0], /<article/g), 4);
  assert.equal(count(indicatorMarkup.split('<details')[1], /<article/g), 4);
  assert.match(indicatorMarkup, /home-indicator primary/); assert.match(indicatorMarkup, /並非即時報價/);
  assert.doesNotMatch(indicatorMarkup, /<details[^>]*\bopen\b/);

  // AC-02/06: Top five from one overview, partial sources independent, no per-stock requests.
  const rows = Array.from({length: 7}, (_, index) => ({industry: `industry-${index}`, average_change: index, advancers: 2, company_count: 3}));
  rows[6].industry = '<img src=x onerror=evil>';
  const stocks = Array.from({length: 7}, (_, index) => ({ticker: `${2330 + index}.TW`, name: index ? 'stock' : '<script>evil</script>', mention_count: 7 - index}));
  responses['/api/market-insights'] = {status: 'partial', data: {industries: {items: rows, as_of: '2025-01-01', coverage: {excluded_markets: ['上櫃']}, market: '上市'}, trending: {items: stocks, sources: ['fixture'], unavailable_sources: ['missing']}}};
  calls = []; await context.fetchHomeOverview();
  assert.deepEqual(calls, ['/api/market-insights']);
  assert.equal(count(el('home-industries').innerHTML, /class="home-rank-row"/g), 5);
  assert.ok(el('home-industries').innerHTML.indexOf('+6.00%') < el('home-industries').innerHTML.indexOf('+5.00%'));
  assert.match(el('home-industries').innerHTML, /&lt;img/); assert.doesNotMatch(el('home-industries').innerHTML, /<img/);
  assert.match(el('home-industries').textContent, /部分市場未納入：上櫃/);
  assert.equal(el('home-trending').buttons.length, 5);
  assert.match(el('home-trending').innerHTML, /&lt;script&gt;/);
  assert.equal(quickSearchCalls, 0); el('home-trending').buttons[0].listeners.click();
  assert.equal(quickSearchCalls, 1); assert.equal(el('quick-search-input').value, '2330.TW');
  responses['/api/market-insights'].data.industries.items = [];
  await context.fetchHomeOverview();
  assert.match(el('home-industries').innerHTML, /沒有可用的產業行情/);
  assert.equal(el('home-trending').buttons.length, 5);
  let release;
  responses['/api/market-insights'] = () => new Promise(resolve => {release = resolve;});
  calls = []; const pending = context.fetchHomeOverview(); await context.fetchHomeOverview();
  assert.equal(calls.length, 1); release({status: 'error', message: '<script>fake failure</script>'}); await pending;
  assert.equal(el('home-industries').textContent, '<script>fake failure</script>'); assert.equal(el('home-industries').innerHTML, '');
  assert.equal(el('btn-home-overview').disabled, false);

  // AC-03/05: Bounded recent-first news, absent dates honest, links safe and update never invokes AI.
  const news = Array.from({length: 14}, (_, index) => ({title: `article-${index}`, source: 'fixture', summary: '<img src=x onerror=evil>', published: `2025-01-${String(index + 1).padStart(2, '0')}T04:00:00Z`, link: 'https://example.invalid/news'}));
  news[13].link = 'javascript:evil()';
  responses['/news?limit=10'] = {status: 'success', data: news};
  calls = []; await context.fetchHomeNews(); assert.deepEqual(calls, ['/news?limit=10']);
  assert.equal(el('war-news').children.length, 10);
  assert.match(el('war-news').children[0].textContent, /article-13/);
  assert.equal(allNodes(el('war-news').children[0]).filter(node => node.tag === 'a').length, 0);
  assert.equal(allNodes(el('war-news')).filter(node => node.tag === 'img' || node.tag === 'script').length, 0);
  const link = allNodes(el('war-news').children[1]).find(node => node.tag === 'a');
  assert.equal(link.rel, 'noopener noreferrer'); assert.equal(link.target, '_blank');
  responses['/news?limit=10'] = {status: 'success', data: [{title: 'missing date', link: 'https://user:pass@example.invalid/news'}]};
  await context.fetchHomeNews(); assert.match(el('war-news').textContent, /发布|發布時間未提供或無法確認/);
  assert.equal(allNodes(el('war-news')).filter(node => node.tag === 'a').length, 0);
  for (const response of [{status: 'error', message: '<script>news unavailable</script>'}, {status: 'success', data: []}]) {
    responses['/news?limit=10'] = response; await context.fetchHomeNews();
    assert.equal(el('btn-home-news').disabled, false); assert.equal(el('war-news').innerHTML, '');
    assert.ok(el('war-news').textContent.length > 0);
  }

  // AC-04/05: Three substantive blocks, native closed details, exact original, safe bold and no executable HTML.
  const original = '**市場**  \t\r\n第一段 **重點** <img src=x onerror=evil>\r\n\r\n# 產業  \r\n- 第二段\r\n- [危險](javascript:evil())\r\n\r\n## 風險\r\n第三段\r\n\r\n# 補充\r\n第四段<script>evil</script>';
  context.renderHomeAI(original, {generated_at: '2025-01-01T04:00:00Z', news_published_from: '2024-12-31T04:00:00Z', news_published_to: '2025-01-01T03:00:00Z', sources_used: ['fixture']});
  const ai = el('war-ai-summary'), preview = ai.children[0];
  assert.equal(preview.children[0].tag, 'h3'); assert.equal(preview.children[0].textContent, '市場');
  assert.equal(preview.children.filter(node => ['p', 'ul', 'ol'].includes(node.tag)).length, 3);
  assert.match(preview.textContent, /市場.*第一段.*產業.*第二段.*風險.*第三段/s);
  assert.doesNotMatch(preview.textContent, /第四段/);
  assert.equal(ai.children[1].tag, 'details'); assert.equal(ai.children[1].open, undefined);
  assert.equal(ai.children[1].children[1].textContent, original);
  assert.ok(allNodes(preview).some(node => node.tag === 'strong' && node.textContent === '重點'));
  assert.equal(allNodes(ai).filter(node => ['img', 'script', 'a'].includes(node.tag)).length, 0);
  assert.match(ai.children[2].textContent, /AI 產生：.*12:00 台北.*新聞發布範圍/s);
  responses['/auto_news'] = {status: 'success', summary: original};
  calls = []; await context.fetchWarData(); assert.deepEqual(calls, ['/auto_news']);
  responses['/auto_news'] = {status: 'error', message: '<img src=x onerror=evil>'};
  await context.fetchWarData(); assert.equal(ai.textContent, '<img src=x onerror=evil>'); assert.equal(ai.innerHTML, '');
  assert.equal(el('btn-war').disabled, false);

  // Initial load invokes news/overview independently and leaves AI manual.
  const initCalls = [];
  const initial = {setInterval: () => {}};
  ['fetchMarketCalendar', 'fetchHomeOverview', 'fetchHomeNews', 'fetchStockNames', 'checkHealth', 'updateAuthUI', 'restoreAuth', 'initLanding', 'fetchRankings', 'fetchMarketStatus', 'updateClock', 'fetchWarData'].forEach(name => {initial[name] = () => initCalls.push(name);});
  vm.createContext(initial); vm.runInContext(slice('function init() {', 'window.onload = init;'), initial); initial.init();
  assert.equal(initCalls.filter(name => name === 'fetchHomeOverview').length, 1);
  assert.equal(initCalls.filter(name => name === 'fetchHomeNews').length, 1);
  assert.ok(!initCalls.includes('fetchWarData'));
  // Execute actual motion/entry helpers. CDN failures and reduced motion cannot gate entry.
  const motionSource = slice('let landingAnimationDone = false;', '// KEYBOARD SHORTCUTS');
  for (const mode of ['no-gsap', 'reduced', 'active', 'throw', 'stalled']) {
    const landing = new Element('div'), app = new Element('main'), nodes = [new Element('div'), new Element('div')];
    let activations = 0; app.classList = {add: value => {assert.equal(value, 'active'); activations++;}};
    const removed = [];
    nodes.forEach(node => {node.style.removeProperty = name => removed.push(name);});
    const motions = [], timers = [], scrolls = [];
    const motion = {window: {matchMedia: () => ({matches: mode === 'reduced'})},
      setTimeout: (callback, delay) => {assert.equal(delay, 650); timers.push(callback);},
      document: {
        getElementById: id => id === 'landing' ? landing : id === 'features' ? {scrollIntoView: options => scrolls.push(options)} : nodes[0],
        querySelector: selector => {assert.equal(selector, '.app'); return app;},
        querySelectorAll: () => nodes
      },
      apiCall: () => assert.fail('motion must never trigger API requests'),
      fetch: () => assert.fail('motion must never trigger network requests')};
    if (mode !== 'no-gsap') motion.gsap = {
      matchMedia: () => ({add: (_query, callback) => callback()}),
      fromTo: (selector, from, to) => {
        if (mode === 'throw') throw new Error('fake animation failure');
        motions.push({selector, from, to});
      },
      to: (_element, options) => {
        if (mode === 'throw') throw new Error('fake animation failure');
        motions.push({to: options});
        if (mode !== 'stalled') options.onComplete();
      }
    };
    vm.createContext(motion); vm.runInContext(motionSource, motion);
    motion.initLanding(); motion.enterDashboard(); motion.enterDashboard();
    timers.forEach(callback => callback()); motion.revealHomeOnce(); motion.startJourney();
    assert.equal(landing.style.display, 'none'); assert.equal(activations, 1);
    motion.scrollToFeatures(); assert.equal(scrolls[0].behavior, mode === 'reduced' ? 'auto' : 'smooth');
    if (['no-gsap', 'reduced'].includes(mode)) {assert.equal(motions.length, 0); assert.equal(timers.length, 0);}
    if (mode === 'throw') assert.ok(removed.includes('opacity') && removed.includes('transform'));
    if (['active', 'stalled'].includes(mode)) {
      assert.equal(motions.length, 3); // Landing entrance, one exit, one home entrance.
      for (const {from, to} of motions) {
        assert.ok(to.duration >= 0.35 && to.duration <= 0.55);
        assert.ok(Math.abs(to.y) <= 16); assert.ok([0, 1].includes(to.opacity));
        assert.equal(to.scrollTrigger, undefined); assert.equal(to.repeat, undefined);
        if (from) assert.equal(to.clearProps, 'transform,opacity');
      }
    }
  }
  console.log('Homepage AC-01..06/08: indicator hierarchy, limits, independent loads, partial/error recovery, dates, manual stock entry, three-block safe AI and exact original passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
