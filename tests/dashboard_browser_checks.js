// Exercise the real browser helpers with a fake DOM and no network.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const html = fs.readFileSync('static/index.html', 'utf8');
for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
  new vm.Script(match[1]);
}
const api = html.slice(html.indexOf('async function apiCall('), html.indexOf('// TOAST SYSTEM'));
const wrapper = html.slice(html.indexOf('const originalApiCall'), html.indexOf('// 初始化完成後自動訂閱'));
const costs = html.slice(html.indexOf('function readBacktestCosts()'), html.indexOf('async function runBacktest()'));
const values = {'backtest-commission': '0.1425', 'backtest-min-commission': '20', 'backtest-sell-tax': '0.3'};
let calls = 0;
const context = {API_BASE: '', AbortSignal, document: {getElementById: id => ({value: values[id]})},
  fetch: async () => {
    assert.ok(++calls <= 2, 'a read must stop after one retry');
    return {ok: false, status: 503, headers: {get: () => 'application/json'}, json: async () => ({detail: 'unavailable'})};
  }};
context.window = context;
vm.createContext(context);
vm.runInContext(api + wrapper + costs, context);
(async () => {
  assert.equal((await context.apiCall('/api/market-insights')).status, 'error');
  assert.equal(calls, 2);
  for (const [url, method] of [['/analyze','POST'], ['/auth/me','GET'], ['/api/account/volume-alerts','GET']]) {
    calls = 0;
    await context.apiCall(url, method);
    assert.equal(calls, 1);
  }
  const result = context.readBacktestCosts();
  assert.ok(Math.abs(result.commission_rate - 0.001425) < 1e-12);
  assert.equal(result.sell_tax_rate, 0.003);
  assert.equal(result.min_commission, 20);
  for (const invalid of ['59.76', '-1', '', 'NaN', 'Infinity']) {
    values['backtest-sell-tax'] = invalid;
    assert.throws(() => context.readBacktestCosts(), /賣出稅率/);
  }
  values['backtest-sell-tax'] = '0.1';
  assert.equal(context.readBacktestCosts().sell_tax_rate, 0.001);

  // Execute the source helpers and renderer, rather than copied implementations.
  const calendarCode = html.slice(html.indexOf('function calendarReadableSourceUrl('), html.indexOf('// Quick Search'));
  const escapeAndLinks = html.slice(html.indexOf('function escapeRoutingText('), html.indexOf('function renderTechTable('));
  const safeUrlCode = html.slice(html.indexOf('function safeNewsUrl('), html.indexOf('async function fetchMarketInsights('));
  const decodeAttribute = value => value.replace(/&(amp|lt|gt|quot|#39);/g,
    (_, entity) => ({amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'"})[entity]);
  const box = {
    children: [], links: [], markup: '',
    set innerHTML(value) {
      this.markup = value; this.children = [];
      this.links = [...value.matchAll(/<a\b[^>]*data-safe-url="([^"]*)"[^>]*>([\s\S]*?)<\/a>/g)].map(match => ({
        dataset: {safeUrl: decodeAttribute(match[1])}, textContent: match[2], attributes: {},
        setAttribute(name, value) {this.attributes[name] = value;},
        removeAttribute(name) {if (name === 'data-safe-url') delete this.dataset.safeUrl;},
        replaceWith(node) {this.replacement = node;}
      }));
    },
    get innerHTML() {return this.markup;},
    appendChild(node) {this.children.push(node);},
    querySelectorAll(selector) {assert.equal(selector, 'a[data-safe-url]'); return this.links;}
  };
  let response = {data: {items: []}};
  const calendar = {URL, apiCall: async endpoint => {
    assert.equal(endpoint, '/api/market-calendar'); return response;
  }, document: {
    getElementById: id => {assert.equal(id, 'market-calendar'); return box;},
    createElement: tag => ({tag, addEventListener(event, listener) {this.event = event; this.listener = listener;}}),
    createTextNode: text => ({textContent: text})
  }};
  vm.createContext(calendar);
  vm.runInContext(calendarCode + escapeAndLinks + safeUrlCode, calendar);
  const announcement = 'https://www.twse.com.tw/zh/announcement/ex-right/twt48u.html';
  const holiday = 'https://www.twse.com.tw/zh/trading/holiday.html';
  for (const [source, expected] of [
    ['https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL?date=20261003', announcement],
    ['https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule?format=json', holiday],
    ['https://example.invalid/events?date=20261003', 'https://example.invalid/events?date=20261003'],
    ['https://openapi.twse.com.tw.evil.invalid/v1/exchangeReport/TWT48U_ALL', 'https://openapi.twse.com.tw.evil.invalid/v1/exchangeReport/TWT48U_ALL'],
    ['https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL/other', 'https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL/other']
  ]) assert.equal(calendar.calendarReadableSourceUrl(source), expected);
  for (const unsafe of ['javascript:alert(1)', 'data:text/html,unsafe', 'ftp://example.invalid/x',
    'https://user:password@openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL', 'not a URL']) {
    assert.equal(calendar.calendarReadableSourceUrl(unsafe), '');
  }
  const events = Array.from({length: 8}, (_, index) => ({date: `2026-10-${String(index + 3).padStart(2, '0')}`,
    kind: 'official', title: `event-${index}`, source_url: 'https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL'}));
  events[0] = {date: '2026-10-03" onload="unsafe', kind: '<b>kind</b>', title: '<img src=x onerror="unsafe"> & source',
    source_url: 'https://example.invalid/events?q="unsafe"&date=20261003'};
  events[7].source_url = 'javascript:alert(1)';
  response = {data: {items: events, unavailable_sources: ['holiday']}};
  await calendar.fetchMarketCalendar();
  const rendered = box.innerHTML;
  assert.equal((rendered.split('<details')[0].match(/<li class="calendar-event">/g) || []).length, 6);
  assert.equal((rendered.split('<details')[1].match(/<li class="calendar-event">/g) || []).length, 2);
  assert.match(rendered, /<details class="calendar-more"><summary>/);
  assert.doesNotMatch(rendered, /<details[^>]*\bopen\b/);
  assert.match(rendered, /展開其餘 2 筆事件/);
  for (let index = 1; index < 8; index++) assert.equal(rendered.split(`event-${index}`).length - 1, 1);
  assert.ok(rendered.includes('&lt;img src=x onerror=&quot;unsafe&quot;&gt; &amp; source'));
  assert.ok(rendered.includes('datetime="2026-10-03&quot; onload=&quot;unsafe"'));
  assert.ok(rendered.includes('&lt;b&gt;kind&lt;/b&gt;'));
  assert.doesNotMatch(rendered, /<img|<b>kind/);
  assert.equal(box.links[1].attributes.href, announcement);
  assert.equal(box.links[0].attributes.href, 'https://example.invalid/events?q=%22unsafe%22&date=20261003');
  for (const link of box.links.slice(0, 7)) {
    assert.equal(link.attributes.target, '_blank'); assert.equal(link.attributes.rel, 'noopener noreferrer');
    assert.equal(link.dataset.safeUrl, undefined);
  }
  assert.equal(box.links[7].attributes.href, undefined);
  assert.ok(box.links[7].replacement.textContent.includes('查看官方公告'));
  assert.match(box.children[0].textContent, /台北日期.*部分來源暫缺/);
  assert.equal(box.children[1].event, 'click'); assert.equal(box.children[1].listener, calendar.fetchMarketCalendar);
  response = {data: {items: events.slice(0, 6)}};
  await calendar.fetchMarketCalendar();
  assert.doesNotMatch(box.innerHTML, /<details/);
  for (const empty of [{data: {items: []}}, {status: 'error', detail: 'unavailable'}]) {
    response = empty; await calendar.fetchMarketCalendar();
    assert.match(box.innerHTML, /目前沒有可驗證的近期事件/);
    assert.equal(box.links.length, 0); assert.equal(box.children[1].tag, 'button');
  }
  console.log('Browser syntax, retries, costs, calendar safe links, escaped disclosure and empty/error fallback passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
