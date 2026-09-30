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
  console.log('Browser syntax, bounded retries, percent conversion and input validation passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
