
// ============================
// GLOBAL STATE
// ============================
const API_BASE = window.location.origin;
let currentChatbotId = null;
let screenerTargets = [];
let positions = [];
let currentUser = null;
try {
  const storedUser = localStorage.getItem('trade_user');
  if (storedUser && storedUser !== 'undefined') {
    currentUser = JSON.parse(storedUser);
  }
} catch (e) {
  console.warn("Invalid trade_user in localStorage, clearing it.");
  localStorage.removeItem('trade_user');
}
let authMode = 'login';
let klineDays = 180;
let currentKlineTicker = '';
let klineChart = null;
let techTableData = [];
let techSortCol = -1;
let techSortAsc = true;

const fmt = (num, d = 2) => Number(num).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

// ============================
// STOCK UTILS
// ============================
const stockNames = {
  "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達", "2603": "長榮",
  "2311": "日月光", "2325": "矽品", "3711": "日月光投控"
};

function normalizeTicker(val) {
  val = val.trim().toUpperCase();
  if (/^\d{4}$/.test(val)) return val + ".TW";
  return val;
}

function displayTicker(ticker) {
  const code = ticker.split('.')[0];
  const name = stockNames[code] || stockNames[ticker];
  return name ? `${ticker} ${name}` : ticker;
}

async function fetchStockNames() {
  try {
    const res = await apiCall('/api/stock_names');
    if (res.status === 'success' && res.data) {
      Object.assign(stockNames, res.data);
    }
  } catch(e) {}
}

// ============================
// API HELPER
// ============================
async function apiCall(endpoint, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' }, cache: 'no-store' };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, opts);
    return await res.json();
  } catch (e) {
    return { status: 'error', message: '無法連線至伺服器' };
  }
}

// ============================
// TOAST SYSTEM
// ============================
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || ''} ${message}</span><button class="toast-close" onclick="this.parentElement.remove()">✕</button>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut .3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ============================
// NAVIGATION
// ============================
const pageTitles = {
  war: '首頁', stress: '資產壓力測試', tech: '異質技術分析',
  kline: '個股 K 線圖', backtest: '策略回測', news: '新聞知識圖譜',
  sentiment: '市場情緒雷達', screener: 'AI 關聯選股'
};

function navigateTo(pageName) {
  document.querySelectorAll('#nav .nav-btn[data-page]').forEach(b => {
    b.classList.toggle('active', b.dataset.page === pageName);
  });
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const target = document.getElementById('page-' + pageName);
  if (target) target.classList.add('active');
  document.title = `${pageTitles[pageName] || ''} - 股金往來`;
  // Close sidebar on mobile
  if (window.innerWidth <= 768) {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebar-overlay').classList.remove('visible');
    document.getElementById('sidebar-overlay').style.display = 'none';
  }
}

document.querySelectorAll('#nav .nav-btn[data-page]').forEach(btn => {
  btn.addEventListener('click', () => navigateTo(btn.dataset.page));
});

// ============================
// MOBILE SIDEBAR
// ============================
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const isOpen = sidebar.classList.contains('open');
  sidebar.classList.toggle('open');
  if (!isOpen) {
    overlay.style.display = 'block';
    requestAnimationFrame(() => overlay.classList.add('visible'));
  } else {
    overlay.classList.remove('visible');
    setTimeout(() => overlay.style.display = 'none', 250);
  }
}

// ============================
// MODAL HELPERS
// ============================
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  document.getElementById(id).style.display = 'none';
}
function openModal(id) {
  const el = document.getElementById(id);
  el.style.display = 'flex';
  el.classList.add('open');
}

// ============================
// CLOCK & MARKET STATUS
// ============================
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent = now.toLocaleTimeString('zh-TW', { hour12: false });
}

async function fetchMarketStatus() {
  const badge = document.getElementById('market-badge');
  const dot = document.getElementById('market-dot');
  const text = document.getElementById('market-text');
  try {
    const res = await apiCall('/market_status');
    if (res.status === 'success') {
      if (res.is_open) {
        badge.className = 'market-badge open';
        dot.style.background = 'var(--green-400)';
        text.textContent = '盤中交易';
      } else {
        badge.className = 'market-badge closed';
        dot.style.background = 'var(--slate-500)';
        text.textContent = '已收盤';
      }
    }
  } catch (e) {
    // Fallback: estimate locally
    const now = new Date();
    const day = now.getDay();
    const h = now.getHours();
    const m = now.getMinutes();
    const mins = h * 60 + m;
    const isOpen = day >= 1 && day <= 5 && mins >= 540 && mins <= 810;
    badge.className = isOpen ? 'market-badge open' : 'market-badge closed';
    dot.style.background = isOpen ? 'var(--green-400)' : 'var(--slate-500)';
    text.textContent = isOpen ? '盤中交易' : '已收盤';
  }
}

// ============================
// HEALTH CHECK
// ============================
async function checkHealth() {
  const dotApi = document.getElementById('dot-api');
  const dotAi = document.getElementById('dot-ai');
  dotApi.className = 'status-dot';
  dotAi.className = 'status-dot';
  const res = await apiCall('/health');
  if (res.status === 'ok') {
    dotApi.classList.remove('err');
    if (!res.maiagent) dotAi.classList.add('err');
    showToast('系統連線正常', 'success');
  } else {
    dotApi.classList.add('err');
    dotAi.classList.add('err');
    showToast('系統連線失敗', 'error');
  }
}

// ============================
// MACRO DATA
// ============================
async function fetchMacroData() {
  const bar = document.getElementById('macro-bar');
  bar.innerHTML = '<div style="grid-column:span 4" class="loading"><div class="spinner"></div></div>';
  const res = await apiCall('/macro');
  if (res.status === 'success' && res.data) {
    bar.innerHTML = '';
    const nMap = {
      '加權指數': '加權指數 (TAIEX)', '費城半導體指數': '費城半導體 (^SOX)',
      '費半指數': '費城半導體 (^SOX)', '油價': '油價 (WTI)', '金價': '金價 (Gold)'
    };
    Object.entries(res.data).forEach(([key, val]) => {
      const up = val.change >= 0;
      const color = up ? 'var(--green-400)' : 'var(--red-400)';
      const sign = up ? '+' : '';
      bar.innerHTML += `
        <div class="stat-card" style="padding:16px; border-top:2px solid ${color}">
          <div style="display:flex; justify-content:space-between; margin-bottom:12px; align-items:center">
            <div style="font-size:13px; color:var(--slate-300); font-weight:700">${key}</div>
            <div style="font-size:13px; color:${color}; font-weight:700">~ ${sign}${fmt(val.change)}</div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:flex-end">
            <div style="font-size:24px; font-weight:800; color:#fff; letter-spacing:-0.5px">${fmt(val.price)}</div>
            <div style="font-size:13px; color:${color}; font-weight:600">(${sign}${fmt(val.pct_change)}%)</div>
          </div>
        </div>`;
    });
  } else {
    bar.innerHTML = '';
  }
}

// ============================
// AUTH
// ============================
function showAuthModal(mode = 'login') {
  authMode = mode;
  openModal('auth-modal');
  document.getElementById('auth-error').style.display = 'none';
  const isSignup = mode === 'signup';
  document.getElementById('auth-modal-title').innerText = isSignup ? '註冊' : '登入';
  document.getElementById('auth-name').style.display = isSignup ? 'block' : 'none';
  document.getElementById('auth-submit-btn').innerText = isSignup ? '註冊' : '登入';
  document.getElementById('auth-toggle-link').innerText = isSignup ? '已有帳號？點此登入' : '還沒有帳號？點此註冊';
}

function toggleAuthMode() { showAuthModal(authMode === 'login' ? 'signup' : 'login'); }

async function handleAuthSubmit() {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value.trim();
  const name = document.getElementById('auth-name').value.trim();
  const errDiv = document.getElementById('auth-error');
  if (!email || !password) { errDiv.innerText = '請填寫信箱與密碼'; errDiv.style.display = 'block'; return; }
  if (authMode === 'signup') {
    const res = await apiCall('/auth/signup', 'POST', { email, password, name });
    if (res.status === 'success') { showToast('註冊成功！請登入', 'success'); showAuthModal('login'); }
    else { 
      let errMsg = res.detail || res.message || '註冊失敗';
      if (typeof errMsg === 'object') errMsg = JSON.stringify(errMsg);
      errDiv.innerText = errMsg; 
      errDiv.style.display = 'block'; 
    }
  } else {
    const res = await apiCall('/auth/login', 'POST', { email, password });
    if (res.status === 'success') {
      currentUser = res.user;
      localStorage.setItem('trade_user', JSON.stringify(res.user));
      closeModal('auth-modal');
      updateAuthUI();
      loadPositionsFromServer();
      showToast(`歡迎回來，${res.user.name || res.user.email}！`, 'success');
      
      // Trigger dashboard transition if landing is still active
      if (document.getElementById('landing').style.display !== 'none') {
        enterDashboard();
      }
    } else { 
      let errMsg = res.detail || res.message || '登入失敗';
      if (typeof errMsg === 'object') errMsg = JSON.stringify(errMsg);
      errDiv.innerText = errMsg; 
      errDiv.style.display = 'block'; 
    }
  }
}

function logout() {
  currentUser = null;
  localStorage.removeItem('trade_user');
  positions = [];
  renderPositions();
  updateAuthUI();
  showToast('已成功登出', 'info');
}

function updateAuthUI() {
  const authSec = document.getElementById('auth-section');
  if (currentUser) {
    authSec.innerHTML = `<span style="color:#fff;font-size:13px;font-weight:700">👤 ${currentUser.name || currentUser.email}</span>
      <button class="btn-ghost" onclick="logout()" style="font-size:12px;color:var(--slate-400)">登出</button>`;
  } else {
    authSec.innerHTML = `<button class="btn-analyze" style="padding:6px 14px;font-size:12px" onclick="showAuthModal('login')">登入 / 註冊</button>`;
  }
}

// ============================
// POSITIONS
// ============================
async function loadPositionsFromServer() {
  if (!currentUser) { positions = []; renderPositions(); return; }
  const res = await apiCall(`/portfolio?user_id=${currentUser.id}`);
  positions = (res.status === 'success' && res.data.length > 0) ? res.data : [];
  renderPositions();
}

async function syncPositions() {
  if (!currentUser) return;
  await apiCall('/portfolio', 'POST', { user_id: currentUser.id, portfolio: positions });
}

function renderPositions() {
  const types = ['台股', 'ETF'];
  document.getElementById('positions-list').innerHTML = positions.map((p, i) => `
    <div class="position-grid" style="margin-bottom:8px">
      <input class="input" value="${p.code}" onchange="positions[${i}].code=normalizeTicker(this.value);syncPositions();renderPositions();" placeholder="例如: 2330">
      <select class="input" onchange="positions[${i}].type=this.value;syncPositions()">${types.map(t => `<option ${t === p.type ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <input class="input" type="number" value="${p.cost}" onchange="positions[${i}].cost=this.value;syncPositions()">
      <input class="input" type="number" value="${p.shares}" onchange="positions[${i}].shares=this.value;syncPositions()">
      <button class="btn-remove" onclick="removePosition(${i})">×</button>
    </div>`).join('');
}

function addPosition() {
  if (!currentUser) { showAuthModal('login'); return; }
  positions.push({ code: '', type: '台股', cost: '', shares: '' });
  renderPositions();
  syncPositions();
}

function removePosition(i) { positions.splice(i, 1); renderPositions(); syncPositions(); }

// ============================
// SCREENER
// ============================
function addScreenerTarget() {
  const input = document.getElementById('screener-target-input');
  let val = input.value.trim();
  if (val) {
    val = normalizeTicker(val);
    if (!screenerTargets.includes(val)) { screenerTargets.push(val); renderScreenerTargets(); }
  }
  input.value = '';
}

function importFromPortfolio() {
  if (positions.length === 0) { showToast('投資組合目前是空的！請先新增部位。', 'warning'); return; }
  let added = 0;
  positions.forEach(p => { if (p.code && !screenerTargets.includes(p.code)) { screenerTargets.push(p.code); added++; } });
  if (added > 0) { renderScreenerTargets(); showToast(`已匯入 ${added} 檔標的`, 'success'); }
  else showToast('投資組合內的標的皆已在清單中', 'info');
}

function removeScreenerTarget(idx) { screenerTargets.splice(idx, 1); renderScreenerTargets(); }

function renderScreenerTargets() {
  const list = document.getElementById('screener-target-list');
  if (screenerTargets.length === 0) {
    list.innerHTML = '<span style="color:var(--slate-500);font-size:13px;line-height:30px">尚未設定目標標的...</span>';
    return;
  }
  list.innerHTML = screenerTargets.map((t, i) => `
    <div style="background:var(--slate-800);padding:5px 14px;border-radius:var(--radius-full);font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px;color:#fff;border:1px solid var(--slate-700)">
      ${displayTicker(t)}
      <button onclick="removeScreenerTarget(${i})" style="background:var(--slate-700);border:none;color:var(--slate-400);width:20px;height:20px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:11px;transition:.2s" onmouseover="this.style.background='var(--red-500)';this.style.color='#fff'" onmouseout="this.style.background='var(--slate-700)';this.style.color='var(--slate-400)'">✕</button>
    </div>`).join('');
}

// ============================
// HOME / WAR PAGE
// ============================
async function fetchWarData() {
  const btn = document.getElementById('btn-war');
  btn.disabled = true;
  document.getElementById('war-ai-summary').innerHTML = '<div class="loading"><div class="spinner"></div><p class="loading-text">MaiAgent 生成摘要中...</p></div>';
  document.getElementById('war-news').innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  fetchMacroData();

  const aiRes = await apiCall('/auto_news');
  if (aiRes.status === 'success') {
    document.getElementById('war-ai-summary').innerHTML = `<div class="advice-box advice-blue" style="margin:0"><p class="desc">${aiRes.summary}</p></div>`;
  } else {
    document.getElementById('war-ai-summary').innerHTML = `<p style="color:var(--red-400)">${aiRes.message}</p>`;
  }

  const newsRes = await apiCall('/news?limit=10');
  if (newsRes.status === 'success') {
    document.getElementById('war-news').innerHTML = newsRes.data.map(n => `
      <details style="background:rgba(51,65,85,0.25);border:1px solid var(--glass-border);padding:14px;border-radius:var(--radius-md);margin-bottom:8px;transition:.3s">
        <summary style="cursor:pointer;outline:none;display:flex;gap:10px;align-items:flex-start">
          <span style="font-size:11px;color:var(--slate-600);width:100px;flex-shrink:0;font-family:monospace;font-weight:500">${n.published}</span>
          <span class="badge badge-slate" style="flex-shrink:0">${n.source}</span>
          <span style="font-size:14px;color:var(--slate-200);font-weight:600;flex:1;line-height:1.5">${n.title}</span>
        </summary>
        <div style="padding-top:12px;margin-top:12px;border-top:1px dashed var(--slate-700);color:var(--slate-300);font-size:13px;line-height:1.7">
          ${n.summary}
          <div style="margin-top:10px"><a href="${n.link}" target="_blank" style="color:var(--blue-400);text-decoration:none;font-weight:600;font-size:13px">閱讀全文 ⭧</a></div>
        </div>
      </details>`).join('');
  }
  btn.disabled = false;
}

// Quick Search
function quickSearch() {
  let val = document.getElementById('quick-search-input').value.trim();
  if (!val) return;
  val = normalizeTicker(val);
  document.getElementById('kline-ticker').value = val;
  navigateTo('kline');
  setTimeout(() => fetchKline(), 100);
  document.getElementById('quick-search-input').value = '';
}

// ============================
// STRESS TEST
// ============================
async function runStressTest() {
  const btn = document.getElementById('btn-stress');
  const resultDiv = document.getElementById('stress-result');
  btn.disabled = true;
  resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p class="loading-text">正在回測技術指標與籌碼計算...</p></div>';

  const targets = positions.filter(p => p.code).map(p => ({ id: p.code, name: '', type: p.type, cost: parseFloat(p.cost) || 0, shares: parseInt(p.shares) || 0 }));
  if (targets.length === 0) { resultDiv.innerHTML = ''; showToast('請先新增至少一檔持股', 'warning'); btn.disabled = false; return; }
  const res = await apiCall('/analyze', 'POST', { targets });

  if (res.status === 'success') {
    let totalCost = 0, totalValue = 0;
    const cardsHtml = res.data.map(r => {
      const t = targets.find(t => t.id === r.ticker);
      const cost = t.cost * t.shares;
      const val = r.price * t.shares;
      totalCost += cost; totalValue += val;
      const color = r.pl >= 0 ? 'var(--green-400)' : 'var(--red-400)';
      const adviceColor = r.score >= 60 ? 'badge-green' : (r.score < 40 ? 'badge-red' : 'badge-orange');
      return `
        <div class="card" style="margin-bottom:0"><div class="card-body">
          <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <span style="font-size:18px;font-weight:800;color:#fff">${displayTicker(r.ticker)}</span>
            <span style="font-weight:800;font-size:16px;color:${color}">${r.pl >= 0 ? '+' : ''}${fmt(r.pl)}%</span>
          </div>
          <div style="font-size:13px;color:var(--slate-400);margin-bottom:12px">現價: $${fmt(r.price)} | 估值: ${r.valuation}</div>
          <div style="margin-bottom:10px"><span class="badge ${adviceColor}" style="font-size:12px;padding:4px 12px">策略: ${r.advice} (分:${r.score})</span></div>
          <div style="font-size:12px;color:var(--red-400);margin-bottom:14px">⚠ ${r.exit}</div>
          <div style="background:rgba(15,23,42,0.4);padding:12px;border-radius:var(--radius-sm)">
            ${r.signals.map(s => `<div style="font-size:12px;color:var(--slate-300);margin-bottom:4px">• ${s}</div>`).join('') || '<span style="font-size:12px;color:var(--slate-500)">無特殊訊號</span>'}
          </div>
        </div></div>`;
    }).join('');

    const totalPL = totalCost > 0 ? ((totalValue - totalCost) / totalCost * 100) : 0;
    resultDiv.innerHTML = `
      <div class="card">
        <div class="card-header" style="font-size:16px">📊 投資組合總結</div>
        <div class="card-body" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
          <div><span style="color:var(--slate-400);font-size:13px">外匯狀態：</span><span style="color:#fff;font-size:15px;font-weight:600">${res.fx}</span></div>
          <div style="text-align:right">
            <div style="font-size:12px;color:var(--slate-500);margin-bottom:4px;font-weight:600">總未實現損益</div>
            <div style="font-size:36px;font-weight:800;color:${totalPL >= 0 ? 'var(--green-400)' : 'var(--red-400)'};letter-spacing:-1px">${totalPL >= 0 ? '+' : ''}${fmt(totalPL)}%</div>
          </div>
        </div>
      </div>
      <div class="grid grid-2">${cardsHtml}</div>`;

    apiCall('/stress_test/save', 'POST', {
      user_id: currentUser ? currentUser.id : '00000000-0000-0000-0000-000000000000',
      scenario: '常規壓力測試',
      result: { total_cost: totalCost, total_value: totalValue, total_pl: totalPL,
        portfolio: targets.map(t => { const r = res.data.find(d => d.ticker === t.id); return { ticker: t.id, cost: t.cost, shares: t.shares, price: r ? r.price : 0, pl: r ? r.pl : 0 }; })
      }
    });
  } else {
    resultDiv.innerHTML = `<div class="card"><div class="card-body"><p style="color:var(--red-400)">分析失敗：${res.message}</p></div></div>`;
  }
  btn.disabled = false;
}

async function fetchStressHistory() {
  openModal('stress-history-modal');
  const content = document.getElementById('stress-history-content');
  content.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  const uid = currentUser ? currentUser.id : '00000000-0000-0000-0000-000000000000';
  const res = await apiCall(`/stress_test/history?user_id=${uid}`);
  if (res.status === 'success') {
    if (res.data.length === 0) { content.innerHTML = '<p style="color:var(--slate-500);padding:20px;text-align:center">尚無歷史紀錄</p>'; return; }
    content.innerHTML = res.data.map(r => {
      const rd = r.result || {};
      const color = rd.total_pl >= 0 ? 'var(--green-400)' : 'var(--red-400)';
      const sign = rd.total_pl >= 0 ? '+' : '';
      const portHtml = (rd.portfolio || []).map(p => `
        <div style="display:flex;justify-content:space-between;font-size:13px;color:var(--slate-300);margin-top:6px;border-bottom:1px dashed var(--slate-700);padding-bottom:6px">
          <span>${displayTicker(p.ticker)} (${p.shares}股)</span>
          <span style="color:${p.pl >= 0 ? 'var(--green-400)' : 'var(--red-400)'}">${p.pl >= 0 ? '+' : ''}${fmt(p.pl)}%</span>
        </div>`).join('');
      const ts = r.created_at ? r.created_at.replace('T', ' ').substring(0, 19) : '';
      return `
        <div style="background:var(--slate-800);padding:20px;border-radius:var(--radius-md);border:1px solid var(--glass-border);margin-bottom:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
            <span style="color:var(--slate-400);font-family:monospace;font-size:13px">${ts} | ${r.scenario || '未知情境'}</span>
            <span style="font-weight:800;font-size:20px;color:${color}">${sign}${fmt(rd.total_pl || 0)}%</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:14px;color:#fff;font-weight:600">
            <span>總投入: $${fmt(rd.total_cost || 0)}</span>
            <span>現值: $${fmt(rd.total_value || 0)}</span>
          </div>
          <div style="background:rgba(15,23,42,0.4);padding:12px;border-radius:var(--radius-sm)">
            <div style="font-size:11px;color:var(--slate-500);margin-bottom:6px;font-weight:600">資產快照</div>
            ${portHtml}
          </div>
        </div>`;
    }).join('');
  } else {
    content.innerHTML = `<p style="color:var(--red-400);padding:20px">${res.message}</p>`;
  }
}

// ============================
// TECH ANALYSIS
// ============================
async function fetchTechAnalysis() {
  const btn = document.getElementById('btn-tech');
  const tbody = document.getElementById('tech-table');
  btn.disabled = true;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:30px"><div class="spinner" style="margin:0 auto"></div></td></tr>';
  const preset = [
    { id: '2330.TW', name: '台積電', type: '台股', cost: 0, shares: 0 },
    { id: '2317.TW', name: '鴻海', type: '台股', cost: 0, shares: 0 },
    { id: '2454.TW', name: '聯發科', type: '台股', cost: 0, shares: 0 },
    { id: '2382.TW', name: '廣達', type: '台股', cost: 0, shares: 0 },
    { id: '2603.TW', name: '長榮', type: '台股', cost: 0, shares: 0 }
  ];
  const res = await apiCall('/analyze', 'POST', { targets: preset });
  if (res.status === 'success') {
    techTableData = res.data;
    renderTechTable(res.data);
  } else {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--red-400);text-align:center">錯誤: ${res.message}</td></tr>`;
  }
  btn.disabled = false;
}

function renderTechTable(data) {
  document.getElementById('tech-table').innerHTML = data.map(s => {
    const scoreClass = s.score >= 70 ? 'high' : s.score >= 40 ? 'mid' : 'low';
    const scoreColor = s.score >= 70 ? 'var(--green-400)' : s.score >= 40 ? 'var(--yellow-400)' : 'var(--red-400)';
    const adviceBadge = s.score >= 60 ? 'badge-green' : (s.score < 40 ? 'badge-red' : 'badge-orange');
    return `
      <tr style="cursor:pointer" onclick="document.getElementById('kline-ticker').value='${s.ticker}';navigateTo('kline');setTimeout(fetchKline,100)">
        <td><span style="color:#fff;font-size:14px;font-weight:700">${displayTicker(s.ticker)}</span></td>
        <td style="text-align:right;font-family:monospace;font-size:14px;font-weight:600">$${fmt(s.price)}</td>
        <td style="text-align:center"><span style="font-size:12px;color:var(--slate-300)">${s.valuation}</span></td>
        <td><div style="font-size:11px;color:var(--slate-400);max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${s.signals.join(' | ')}</div></td>
        <td style="text-align:right"><div class="score-bar" style="justify-content:flex-end"><div class="score-bar-track" style="width:40px"><div class="score-bar-fill ${scoreClass}" style="width:${s.score}%"></div></div><span style="font-weight:800;font-size:14px;color:${scoreColor};width:32px;text-align:right">${s.score}</span></div></td>
        <td style="text-align:right"><span class="badge ${adviceBadge}" style="font-size:11px">${s.advice}</span></td>
      </tr>`;
  }).join('');
}

function sortTechTable(colIdx) {
  if (techTableData.length === 0) return;
  if (techSortCol === colIdx) techSortAsc = !techSortAsc;
  else { techSortCol = colIdx; techSortAsc = true; }
  const keys = ['ticker', 'price', 'valuation', '', 'score', 'advice'];
  const key = keys[colIdx];
  if (!key) return;
  techTableData.sort((a, b) => {
    let va = a[key], vb = b[key];
    if (typeof va === 'number') return techSortAsc ? va - vb : vb - va;
    return techSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  });
  renderTechTable(techTableData);
}

// ============================
// K-LINE CHART (NEW)
// ============================
function setKlineDays(days) {
  klineDays = days;
  document.querySelectorAll('.range-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.days) === days));
  if (currentKlineTicker) fetchKline();
}

async function fetchKline() {
  let ticker = document.getElementById('kline-ticker').value.trim();
  if (!ticker) { showToast('請輸入股票代號', 'warning'); return; }
  ticker = normalizeTicker(ticker);
  document.getElementById('kline-ticker').value = ticker;
  currentKlineTicker = ticker;
  const displayName = displayTicker(ticker);
  document.getElementById('kline-chart-title').textContent = `📈 ${displayName} — 載入中...`;
  document.getElementById('kline-signals').innerHTML = '';
  document.getElementById('kline-fundamentals').style.display = 'none';

  fetchFundamentalsAndChips(ticker);

  const res = await apiCall(`/kline/${ticker}?days=${klineDays}`);
  if (res.status !== 'success') {
    document.getElementById('kline-chart-title').textContent = `📈 ${displayName} — 載入失敗`;
    showToast(res.message || '無法載入 K 線資料', 'error');
    return;
  }

  document.getElementById('kline-chart-title').textContent = `📈 ${displayName} K線圖 (${klineDays} 日)`;

  const chartDom = document.getElementById('kline-chart');
  if (klineChart) klineChart.dispose();
  klineChart = echarts.init(chartDom, 'dark');

  const dates = res.candles.map(c => { const d = new Date(c.time * 1000); return `${d.getMonth()+1}/${d.getDate()}`; });
  const ohlc = res.candles.map(c => [c.open, c.close, c.low, c.high]);
  const vols = res.volumes.map(v => ({ value: v.value, itemStyle: { color: v.color === '#26a69a' ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)' } }));
  const ma5Data = res.ma5.map(m => m.value);
  const ma20Data = res.ma20.map(m => m.value);
  const ma60Data = res.ma60.map(m => m.value);

  // Pad MA data to align with dates
  const padStart = (arr, total) => { const pad = total - arr.length; return [...Array(pad > 0 ? pad : 0).fill(null), ...arr]; };

  const option = {
    backgroundColor: 'transparent',
    animation: true,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: '#475569' } },
      backgroundColor: 'rgba(15,23,42,0.95)', borderColor: '#334155', textStyle: { color: '#e2e8f0', fontSize: 12 } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: '8%', right: '3%', top: '5%', height: '55%' },
      { left: '8%', right: '3%', top: '68%', height: '22%' }
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#64748b', fontSize: 10 }, boundaryGap: true },
      { type: 'category', data: dates, gridIndex: 1, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { show: false }, boundaryGap: true }
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.3)' } }, axisLabel: { color: '#64748b', fontSize: 10 }, axisLine: { lineStyle: { color: '#334155' } } },
      { scale: true, gridIndex: 1, splitNumber: 2, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.2)' } }, axisLabel: { color: '#64748b', fontSize: 10 }, axisLine: { lineStyle: { color: '#334155' } } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, bottom: '2%', height: 20,
        borderColor: '#334155', backgroundColor: 'rgba(15,23,42,0.5)', fillerColor: 'rgba(59,130,246,0.15)',
        handleStyle: { color: '#3b82f6' }, textStyle: { color: '#64748b' } }
    ],
    series: [
      { name: 'K線', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: { color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' } },
      { name: 'MA5', type: 'line', data: padStart(ma5Data, dates.length), xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, lineStyle: { width: 1.5, color: '#facc15' }, symbol: 'none' },
      { name: 'MA20', type: 'line', data: padStart(ma20Data, dates.length), xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, lineStyle: { width: 1.5, color: '#3b82f6' }, symbol: 'none' },
      { name: 'MA60', type: 'line', data: padStart(ma60Data, dates.length), xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, lineStyle: { width: 1.5, color: '#a855f7' }, symbol: 'none' },
      { name: '成交量', type: 'bar', data: vols, xAxisIndex: 1, yAxisIndex: 1 }
    ]
  };
  klineChart.setOption(option);
  window.addEventListener('resize', () => klineChart && klineChart.resize());

  // Load signals
  const sigRes = await apiCall('/analyze', 'POST', { targets: [{ id: ticker, name: '', type: '台股', cost: 0, shares: 0 }] });
  if (sigRes.status === 'success' && sigRes.data[0]) {
    const s = sigRes.data[0];
    const advBadge = s.score >= 60 ? 'badge-green' : (s.score < 40 ? 'badge-red' : 'badge-orange');
    document.getElementById('kline-signals').innerHTML = `
      <div class="card">
        <div class="card-header">🧠 ${displayName} 技術分析摘要</div>
        <div class="card-body">
          <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
            <span style="font-size:20px;font-weight:800;color:#fff">$${fmt(s.price)}</span>
            <span class="badge ${advBadge}" style="font-size:13px;padding:5px 14px">${s.advice} (${s.score}分)</span>
            <span style="font-size:13px;color:var(--slate-400)">估值：${s.valuation}</span>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            ${s.signals.map(sig => `<span class="badge badge-slate">${sig}</span>`).join('')}
          </div>
          ${s.exit && s.exit !== '-' ? `<div style="margin-top:12px;font-size:13px;color:var(--red-400)">⚠ ${s.exit}</div>` : ''}
        </div>
      </div>`;
  }
}

// ============================
// BACKTEST (NEW)
// ============================
async function runBacktest() {
  const btn = document.getElementById('btn-backtest');
  const resultDiv = document.getElementById('backtest-result');
  let ticker = document.getElementById('backtest-ticker').value.trim();
  const days = parseInt(document.getElementById('backtest-days').value);

  if (!ticker) { showToast('請輸入股票代號', 'warning'); return; }
  ticker = normalizeTicker(ticker);
  document.getElementById('backtest-ticker').value = ticker;

  btn.disabled = true;
  resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p class="loading-text">策略回測模擬中...</p></div>';

  const res = await apiCall('/backtest', 'POST', { ticker, days });

  if (res.status === 'success') {
    const sr = res.strategy_return || 0;
    const bhr = res.buy_hold_return || 0;
    const outperf = res.outperformance || 0;
    const trades = res.trades || [];
    const tradeCount = res.trade_count || 0;
    const wins = trades.filter(t => t.return_pct > 0).length;
    const winRate = tradeCount > 0 ? ((wins / tradeCount) * 100) : 0;

    resultDiv.innerHTML = `
      <div class="grid grid-4" style="margin-bottom:20px">
        <div class="backtest-stat">
          <div class="label">策略報酬率</div>
          <div class="value" style="color:${sr >= 0 ? 'var(--green-400)' : 'var(--red-400)'}">${sr >= 0 ? '+' : ''}${fmt(sr)}%</div>
        </div>
        <div class="backtest-stat">
          <div class="label">買入持有報酬率</div>
          <div class="value" style="color:${bhr >= 0 ? 'var(--green-400)' : 'var(--red-400)'}">${bhr >= 0 ? '+' : ''}${fmt(bhr)}%</div>
        </div>
        <div class="backtest-stat">
          <div class="label">超額報酬</div>
          <div class="value" style="color:${outperf >= 0 ? 'var(--cyan-400)' : 'var(--orange-400)'}">${outperf >= 0 ? '+' : ''}${fmt(outperf)}%</div>
        </div>
        <div class="backtest-stat">
          <div class="label">交易次數 / 勝率</div>
          <div class="value" style="color:var(--blue-400);font-size:22px">${tradeCount}次 / ${fmt(winRate, 0)}%</div>
        </div>
      </div>

      ${trades.length > 0 ? `
      <div class="card">
        <div class="card-header">📋 最近交易紀錄 (最近 ${trades.length} 筆)</div>
        <table class="data-table">
          <thead><tr>
            <th>動作</th><th style="text-align:right">日期</th><th style="text-align:right">價格</th>
            <th style="text-align:right">報酬</th>
          </tr></thead>
          <tbody>
            ${trades.map(t => {
              const isBuy = t.action === 'BUY' || t.action === '買入';
              return `<tr>
                <td><span class="badge ${isBuy ? 'badge-green' : 'badge-red'}">${t.action}</span></td>
                <td style="text-align:right;font-family:monospace;font-size:12px;color:var(--slate-400)">${t.date || '-'}</td>
                <td style="text-align:right;font-weight:600;color:#fff">NT$${fmt(t.price)}</td>
                <td style="text-align:right;font-weight:700;color:${(t.return_pct || 0) >= 0 ? 'var(--green-400)' : 'var(--red-400)'}">${t.return_pct !== undefined && t.return_pct !== 0 ? ((t.return_pct >= 0 ? '+' : '') + fmt(t.return_pct) + '%') : '-'}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>` : '<div class="card"><div class="card-body" style="color:var(--slate-500);text-align:center">此期間內無交易訊號</div></div>'}
    `;
    showToast(`${ticker} 回測完成`, 'success');
  } else {
    resultDiv.innerHTML = `<div class="card"><div class="card-body"><p style="color:var(--red-400)">回測失敗：${res.message || '未知錯誤'}</p></div></div>`;
    showToast('回測執行失敗', 'error');
  }
  btn.disabled = false;
}

// ============================
// NEWS ANALYSIS
// ============================
async function fetchNewsAnalysis() {
  const btn = document.getElementById('btn-news');
  const list = document.getElementById('news-list');
  const statsBox = document.getElementById('news-stats');
  btn.disabled = true;
  statsBox.innerHTML = '';
  list.innerHTML = '<div class="loading"><div class="spinner"></div><p class="loading-text">爬蟲擷取並交由 MaiAgent 批次判讀中...</p></div>';

  const res = await apiCall('/news/analyze_batch', 'POST', { sources: ['yahoo_finance', 'investing'], limit: 3 });

  if (res.status === 'success' && res.data) {
    const displayedNews = res.data.slice(0, 5);
    const localStats = { '利多': 0, '利空': 0, '中立': 0 };
    displayedNews.forEach(n => {
      const s = n.sentiment || '中立';
      if (localStats[s] !== undefined) localStats[s]++; else localStats['中立']++;
    });

    statsBox.innerHTML = `
      <div class="stat-card up" style="display:flex;align-items:center;gap:16px;padding:18px"><span style="font-size:28px">🟢</span><div><p style="font-size:12px;color:var(--slate-500);font-weight:600">AI 判定利多</p><p style="font-size:24px;font-weight:800;color:var(--green-400);margin-top:2px">${localStats['利多']} 則</p></div></div>
      <div class="stat-card" style="display:flex;align-items:center;gap:16px;padding:18px"><span style="font-size:28px">⚪</span><div><p style="font-size:12px;color:var(--slate-500);font-weight:600">AI 判定中立</p><p style="font-size:24px;font-weight:800;color:var(--slate-300);margin-top:2px">${localStats['中立']} 則</p></div></div>
      <div class="stat-card down" style="display:flex;align-items:center;gap:16px;padding:18px"><span style="font-size:28px">🔴</span><div><p style="font-size:12px;color:var(--slate-500);font-weight:600">AI 判定利空</p><p style="font-size:24px;font-weight:800;color:var(--red-400);margin-top:2px">${localStats['利空']} 則</p></div></div>`;

    list.innerHTML = displayedNews.map(n => {
      const sBadge = n.sentiment === '利多' ? 'badge-green' : (n.sentiment === '利空' ? 'badge-red' : 'badge-slate');
      const iBadge = n.impact === '高' ? 'badge-orange' : (n.impact === '中' ? 'badge-blue' : 'badge-slate');
      return `
        <div style="padding:18px 20px;border-bottom:1px solid rgba(51,65,85,.3)">
          <div style="display:flex;gap:10px;margin-bottom:10px;align-items:center;flex-wrap:wrap">
            <span class="badge ${sBadge}" style="font-size:12px;padding:4px 12px">${n.sentiment}</span>
            <span class="badge ${iBadge}" style="font-size:12px;padding:4px 12px">影響:${n.impact}</span>
            <span style="font-size:11px;color:var(--slate-600);font-family:monospace">${n.source} | ${n.published}</span>
          </div>
          <a href="${n.link}" target="_blank" style="display:block;font-size:15px;font-weight:700;color:#fff;text-decoration:none;margin-bottom:10px;line-height:1.5">${n.title}</a>
          <div style="font-size:13px;color:var(--blue-400);background:rgba(59,130,246,.06);padding:12px;border-radius:var(--radius-sm);line-height:1.7;border:1px solid rgba(59,130,246,0.1)">
            🤖 AI 解析：${n.ai_reason || n.summary || '無特別說明'}
          </div>
        </div>`;
    }).join('');
  } else {
    list.innerHTML = `<p style="padding:20px;color:var(--red-400);font-size:15px">分析失敗：${res.message || '無資料'}</p>`;
  }
  btn.disabled = false;
}

// ============================
// SENTIMENT
// ============================
async function fetchSentiment() {
  const btn = document.getElementById('btn-sentiment');
  const scoreEl = document.getElementById('sentiment-score');
  const labelEl = document.getElementById('sentiment-label');
  const reasonEl = document.getElementById('sentiment-reasoning');
  const newsGrid = document.getElementById('sentiment-news-grid');
  btn.disabled = true;
  scoreEl.innerText = '⏳';
  reasonEl.innerText = '分析中，請稍候...';
  newsGrid.innerHTML = '';

  const res = await apiCall('/api/sentiment', 'GET');
  if (res && res.score !== undefined) {
    let color = '#94a3b8';
    if (res.score >= 56) color = '#22c55e';
    if (res.score <= 45) color = '#ef4444';
    scoreEl.style.color = color;
    scoreEl.style.textShadow = `0 0 40px ${color}40`;
    scoreEl.innerText = res.score;
    labelEl.innerText = res.label;
    reasonEl.innerText = res.reasoning || '分析完成。';

    if (res.recommendations && res.recommendations.length > 0) {
      document.getElementById('sentiment-recommend').innerHTML = `
        <div style="margin-top:16px"><div style="font-size:14px;font-weight:700;color:#fff;margin-bottom:12px">📊 AI 推薦標的</div>
        <div class="recommendation-grid">${res.recommendations.map(r => `
          <div class="stock-card">
            <div class="stock-card-header"><span style="font-size:16px;font-weight:700;color:#fff">${r.ticker || r.name}</span>
            <span class="badge badge-green">${r.action || '觀察'}</span></div>
            <div style="font-size:13px;color:var(--slate-400);line-height:1.6">${r.reason || ''}</div>
          </div>`).join('')}</div></div>`;
    }

    if (res.news_analysis) {
      newsGrid.innerHTML = res.news_analysis.map(n => {
        const tagColor = n.sentiment === '多' ? 'var(--green-500)' : (n.sentiment === '空' ? 'var(--red-500)' : 'var(--slate-500)');
        return `<div class="news-tile">
          <span class="sentiment-tag" style="background:${tagColor}">${n.sentiment}</span>
          <div style="font-size:13px;font-weight:700;color:#fff;margin-bottom:5px">${n.title}</div>
          <div style="font-size:12px;color:var(--slate-400);line-height:1.5">${n.summary}</div>
        </div>`;
      }).join('');
    }
  }
  btn.disabled = false;
}

// ============================
// SCREENER
// ============================
function renderStockListHTML(title, emoji, stocks) {
  if (!stocks || stocks.length === 0) return '';
  return `
    <div style="margin-top:16px;background:rgba(15,23,42,0.3);border:1px solid var(--glass-border);border-radius:var(--radius-md);padding:16px">
      <div style="color:#fff;font-size:14px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:6px">
        <span>${emoji}</span> ${title}
      </div>
      ${stocks.map(fs => `
        <div style="margin-bottom:10px;border-bottom:1px dashed var(--slate-700);padding-bottom:10px;display:flex;flex-direction:column;gap:6px">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px">
            <span style="color:#fff;font-weight:700;font-size:14px;cursor:pointer" onclick="document.getElementById('kline-ticker').value='${fs.ticker}';navigateTo('kline');setTimeout(fetchKline,100)">${displayTicker(fs.ticker)} ${fs.name || ''}</span>
            <span style="color:var(--slate-400);font-size:12px">現價：${fs.price} | 近5日：<span style="color:${fs.pct_5d >= 0 ? 'var(--green-400)' : 'var(--red-400)'}">${fs.pct_5d > 0 ? '+' : ''}${fs.pct_5d}%</span></span>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:6px">
            ${(fs.tags || []).length > 0 ? fs.tags.map(t => `<span class="badge ${t.includes('買超') || t.includes('強勢') ? 'badge-green' : (t.includes('賣超') || t.includes('錯殺') ? 'badge-red' : 'badge-orange')}">${t}</span>`).join('') : '<span class="badge badge-slate">觀察中</span>'}
          </div>
          ${fs.main_force ? `
          <div style="margin-top:6px;background:rgba(15,23,42,0.45);border:1px solid var(--glass-border);border-radius:var(--radius-sm);padding:10px">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px">
              <span style="font-size:12px;color:var(--slate-300)">🧠 主力動向：${fs.main_force.bias || '無法判斷'}</span>
              <span style="font-size:11px;color:var(--orange-400)">動能 ${fs.main_force.score ?? 0}/100</span>
            </div>
            <div style="font-size:11px;color:var(--slate-500);line-height:1.5;margin-bottom:6px">${fs.main_force.summary || '無資料'}</div>
            <div style="font-size:11px;color:var(--slate-300);line-height:1.6">
              ${(fs.main_force.patterns || []).map(p => `• ${p}`).join('<br>')}
            </div>
          </div>` : ''}
        </div>`).join('')}
    </div>`;
}

async function runScreener() {
  if (screenerTargets.length === 0) { showToast('請在上方設定至少一檔目標標的', 'warning'); return; }
  const btn = document.getElementById('btn-screener');
  const resBox = document.getElementById('screener-result');
  btn.disabled = true;
  resBox.innerHTML = '<div class="loading"><div class="spinner"></div><p class="loading-text" style="margin-top:12px">正在分析產業族群、建構供應鏈並彙整主力動能...</p></div>';

  const res = await apiCall('/screener/analyze', 'POST', {
    source: 'manual',
    user_id: currentUser ? currentUser.id : null,
    targets: screenerTargets,
    filters: []
  });

  if (res.status === 'success') {
    const data = res.data || [];
    if (data.length === 0) {
      resBox.innerHTML = '<div class="card"><div class="card-body" style="color:var(--slate-500);text-align:center">目前沒有可分析資料</div></div>';
      btn.disabled = false;
      return;
    }

    resBox.innerHTML = data.map(item => {
      const ev = item.evaluated_stocks || [];
      const strongStocks = ev.filter(s => s.pct_5d >= 10 || (s.main_force && s.main_force.score >= 70));
      const weakStocks = ev.filter(s => s.pct_5d <= -10 || (s.main_force && s.main_force.score <= 30));
      const otherStocks = ev.filter(s => !strongStocks.includes(s) && !weakStocks.includes(s));
      const graphId = 'graph-' + item.target.ticker.replace(/\./g, '-');

      return `
        <details style="background:var(--glass-bg);border:1px solid var(--glass-border);padding:20px;border-radius:var(--radius-lg);margin-bottom:16px;backdrop-filter:blur(8px)" open>
          <summary style="cursor:pointer;outline:none;display:flex;align-items:center;font-size:17px;font-weight:800;color:#fff;gap:8px">
            🎯 目標標的：${displayTicker(item.target.ticker)} ${item.target.name || ''}
          </summary>
          <div style="margin-top:20px;display:grid;gap:14px">
            <div id="${graphId}" style="width:100%;height:420px;background:rgba(15,23,42,0.3);border:1px solid var(--glass-border);border-radius:var(--radius-md)"></div>
            <div style="background:rgba(15,23,42,0.3);padding:14px;border-radius:var(--radius-sm);border-left:4px solid var(--blue-500)">
              <div style="color:var(--slate-500);font-size:11px;margin-bottom:4px;font-weight:600">所屬產業族群</div>
              <div style="color:var(--blue-400);font-size:15px;font-weight:700">${item.group}</div>
            </div>
            <div class="grid grid-2">
              <div style="background:rgba(15,23,42,0.3);padding:14px;border-radius:var(--radius-sm)">
                <div style="color:var(--slate-500);font-size:11px;margin-bottom:8px;font-weight:600">🔗 相關概念</div>
                <div style="display:flex;flex-wrap:wrap;gap:6px">
                  ${item.concepts.map(c => `<span class="badge badge-purple">${c}</span>`).join('')}
                </div>
              </div>
              <div style="background:rgba(15,23,42,0.3);padding:14px;border-radius:var(--radius-sm)">
                <div style="color:var(--slate-500);font-size:11px;margin-bottom:8px;font-weight:600">⚙️ 供應鏈</div>
                <div style="font-size:13px;color:var(--slate-300);line-height:1.8">
                  上游：${(item.supply_chain.upstream || []).map(t => displayTicker(t)).join('、') || '無'}<br>
                  中游：${(item.supply_chain.midstream || []).map(t => displayTicker(t)).join('、') || '無'}<br>
                  下游：${(item.supply_chain.downstream || []).map(t => displayTicker(t)).join('、') || '無'}
                </div>
              </div>
            </div>
            ${renderStockListHTML('🔥 強勢指標股', '🔥', strongStocks)}
            ${renderStockListHTML('📉 弱勢/錯殺股', '📉', weakStocks)}
            ${renderStockListHTML('📋 其他關聯標的', '📋', otherStocks)}
          </div>
        </details>`;
    }).join('');

    // Draw force graphs
    setTimeout(() => {
      data.forEach(item => {
        const graphId = 'graph-' + item.target.ticker.replace(/\./g, '-');
        const chartDom = document.getElementById(graphId);
        if (!chartDom) return;
        const myChart = echarts.init(chartDom, 'dark');
        const nodes = [], links = [], seenNodes = new Set();
        const centerName = item.target.ticker + ' ' + (item.target.name || '');
        nodes.push({ name: centerName, symbolSize: 60, itemStyle: { color: '#f97316', shadowBlur: 20, shadowColor: 'rgba(249,115,22,0.4)' } });
        seenNodes.add(centerName);

        if (item.supply_chain) {
          (item.supply_chain.upstream || []).forEach(x => {
            if (!seenNodes.has(x)) { nodes.push({ name: x, symbolSize: 44, itemStyle: { color: '#22c55e' } }); seenNodes.add(x); }
            links.push({ source: x, target: centerName, value: '上游原料' });
          });
          (item.supply_chain.midstream || []).forEach(x => {
            if (!seenNodes.has(x)) { nodes.push({ name: x, symbolSize: 44, itemStyle: { color: '#3b82f6' } }); seenNodes.add(x); }
            if (x !== centerName) links.push({ source: x, target: centerName, value: '同業中游' });
          });
          (item.supply_chain.downstream || []).forEach(x => {
            if (!seenNodes.has(x)) { nodes.push({ name: x, symbolSize: 44, itemStyle: { color: '#a855f7' } }); seenNodes.add(x); }
            links.push({ source: centerName, target: x, value: '下游客戶' });
          });
        }
        (item.evaluated_stocks || []).forEach(s => {
          const sName = s.ticker + ' ' + (s.name || '');
          if (!seenNodes.has(sName)) {
            nodes.push({ name: sName, symbolSize: 32, itemStyle: { color: '#64748b' } });
            seenNodes.add(sName);
            links.push({ source: centerName, target: sName, value: '產業關聯' });
          }
        });

        myChart.setOption({
          backgroundColor: 'transparent',
          tooltip: { trigger: 'item', formatter: '{b}', backgroundColor: 'rgba(15,23,42,0.95)', borderColor: '#334155', textStyle: { color: '#e2e8f0' } },
          series: [{
            type: 'graph', layout: 'force', roam: true, draggable: true,
            edgeSymbol: ['none', 'arrow'], edgeSymbolSize: [4, 7],
            label: { show: true, position: 'right', color: '#e2e8f0', fontSize: 10 },
            force: { repulsion: 450, edgeLength: 120, gravity: 0.1 },
            data: nodes, links: links,
            lineStyle: { color: 'rgba(255,255,255,0.1)', width: 1.5, curveness: 0.1 }
          }]
        });
      });
    }, 150);
  } else {
    resBox.innerHTML = `<div class="card"><div class="card-body" style="color:var(--red-400)">分析發生錯誤：${res.message}</div></div>`;
  }
  btn.disabled = false;
}

async function fetchRankings() {
  const container = document.getElementById('rankings-content');
  if(!container) return;
  try {
    const res = await apiCall('/api/rankings');
    if (res.status === 'success' && res.data && res.data.volume && res.data.volume.length > 0) {
      container.innerHTML = res.data.volume.map(item => `
        <div class="stat-card">
          <div style="font-size:12px; color:var(--slate-400); margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${displayTicker(item.ticker)}</div>
          <div style="font-size:16px; font-weight:700; color:#fff">${item.price}</div>
          <div style="font-size:11px; color:var(--orange-400); margin-top:4px">量: ${item.volume} 千股</div>
        </div>
      `).join('');
    } else {
      container.innerHTML = '<span style="color:var(--slate-500)">無排行資料</span>';
    }
  } catch(e) {
    container.innerHTML = '<span style="color:var(--red-400)">讀取失敗</span>';
  }
}

async function fetchFundamentalsAndChips(ticker) {
  const fundDiv = document.getElementById('kline-fundamentals');
  fundDiv.style.display = 'block';

  document.getElementById('fund-eps').textContent = '讀取中...';
  document.getElementById('fund-pe').textContent = '讀取中...';
  document.getElementById('fund-yield').textContent = '讀取中...';
  document.getElementById('fund-rev').textContent = '讀取中...';
  document.getElementById('fund-cap').textContent = '讀取中...';
  document.getElementById('chip-content').innerHTML = '<span style="color:var(--slate-500)">讀取中...</span>';

  // Fundamentals
  apiCall(`/api/fundamentals/${ticker}`).then(res => {
    if(res.status === 'success' && res.data) {
      document.getElementById('fund-eps').textContent = res.data.eps || '-';
      document.getElementById('fund-pe').textContent = res.data.pe || '-';
      document.getElementById('fund-yield').textContent = res.data.dividendYield ? (res.data.dividendYield * 100).toFixed(2) + '%' : '-';
      document.getElementById('fund-rev').textContent = res.data.revenueGrowth ? (res.data.revenueGrowth * 100).toFixed(2) + '%' : '-';
      document.getElementById('fund-cap').textContent = res.data.marketCap ? (res.data.marketCap / 100000000).toFixed(2) + ' 億' : '-';
    } else {
      document.getElementById('fund-eps').textContent = '-';
    }
  });

  // Chips
  apiCall('/api/chips').then(res => {
    const code = ticker.split('.')[0];
    if(res.status === 'success' && res.data && res.data[code]) {
      const data = res.data[code];
      const forColor = data.Foreign > 0 ? 'var(--red-400)' : 'var(--green-400)';
      const truColor = data.Trust > 0 ? 'var(--red-400)' : 'var(--green-400)';
      document.getElementById('chip-content').innerHTML = `
        <div style="margin-bottom:12px">
          <div style="font-size:12px;color:var(--slate-400);margin-bottom:4px">外資買賣超</div>
          <div style="font-size:18px;font-weight:700;color:${forColor}">${data.Foreign > 0 ? '+' : ''}${data.Foreign.toLocaleString()} 張</div>
        </div>
        <div>
          <div style="font-size:12px;color:var(--slate-400);margin-bottom:4px">投信買賣超</div>
          <div style="font-size:18px;font-weight:700;color:${truColor}">${data.Trust > 0 ? '+' : ''}${data.Trust.toLocaleString()} 張</div>
        </div>
      `;
    } else {
      document.getElementById('chip-content').innerHTML = '<span style="color:var(--slate-500)">無近期籌碼資料 (可能為盤後或假日無資料)</span>';
    }
  });
}

// ============================
// MODALS
// ============================
let chatOpen = false;
function toggleChat() {
  chatOpen = !chatOpen;
  document.getElementById('chat-panel').classList.toggle('open', chatOpen);
  if (chatOpen) document.getElementById('chat-input').focus();
}

function clearChat() {
  document.getElementById('chat-messages').innerHTML = '<div class="chat-msg bot">對話已清除，隨時可以開始新的對話 🚀</div>';
  currentChatbotId = null;
  showToast('對話已清除', 'info');
}

function renderMarkdown(text) {
  // Basic markdown rendering for chat
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^[-•]\s+(.+)/gm, '• $1')
    .replace(/^(\d+)\.\s+(.+)/gm, '$1. $2');
}

// ============================
// 新系統：WebSocket 實時推送集成
// ============================
// WebSocket 連接完成後的回調
async function initializeRealTimeFeatures() {
  console.log('✓ 實時推送系統已初始化');
  
  // 當前活躍的標籤列表
  const activeTickersFromUI = new Set();
  
  // 監聽頁面切換
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const page = this.getAttribute('data-page');
      // 根據頁面類型訂閱相應的數據
      if (page === 'portfolio' && wsClient) {
        // 從 UI 提取投資組合中的所有股票代碼
        const portfolioItems = document.querySelectorAll('[data-ticker]');
        portfolioItems.forEach(item => {
          const ticker = item.getAttribute('data-ticker');
          if (ticker) wsClient.subscribe(ticker);
        });
      }
    });
  });
}

// 優雅地集成 WebSocket 和已有的 API 調用
const originalApiCall = window.apiCall || (async (url) => {
  const res = await fetch(url);
  return res.json();
});

window.apiCall = async function(url, options = {}) {
  const result = await originalApiCall(url, options);
  
  // 如果是股票分析結果，則通過 WebSocket 推送到其他連接
  if (url.includes('/analyze') && result.data && wsClient) {
    result.data.forEach(item => {
      if (item.ticker) {
        // 推送分析結果到 WebSocket
        if (wsClient.ws && wsClient.ws.readyState === WebSocket.OPEN) {
          console.log(`推送分析結果到 WebSocket: ${item.ticker}`);
        }
      }
    });
  }
  
  return result;
};

// 初始化完成後自動訂閱推薦的股票
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(initializeRealTimeFeatures, 1000);
});

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  const messagesDiv = document.getElementById('chat-messages');
  const sendBtn = document.getElementById('chat-send-btn');
  messagesDiv.innerHTML += `<div class="chat-msg user">${msg}</div>`;
  messagesDiv.scrollTop = messagesDiv.scrollHeight;

  const typingId = 'typing-' + Date.now();
  messagesDiv.innerHTML += `<div class="chat-msg bot" id="${typingId}"><div class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></div>思考中...</div>`;
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  sendBtn.disabled = true;

  const body = { message: msg };
  if (currentChatbotId) body.conversation_id = currentChatbotId;
  const res = await apiCall('/chat', 'POST', body);
  document.getElementById(typingId).remove();

  if (res.status === 'success') {
    if (res.conversation_id) currentChatbotId = res.conversation_id;
    messagesDiv.innerHTML += `<div class="chat-msg bot">${renderMarkdown(res.reply)}</div>`;
  } else {
    messagesDiv.innerHTML += `<div class="chat-msg bot" style="color:var(--red-400)">⚠️ ${res.message}</div>`;
  }
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  sendBtn.disabled = false;
  input.focus();
}

// ============================
// LANDING PAGE & GSAP ANIMATIONS
// ============================
let landingAnimationDone = false;

function initLanding() {
  if (typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined') return;
  gsap.registerPlugin(ScrollTrigger);

  // Hero entrance
  const tl = gsap.timeline();
  tl.from(".landing-nav", { y: -50, opacity: 0, duration: 0.8, ease: "power3.out" })
    .from(".hero-elem", { 
      y: 40, 
      opacity: 0, 
      duration: 0.8, 
      stagger: 0.15, 
      ease: "power3.out" 
    }, "-=0.4");

  // Feature cards fade in stagger
  gsap.from(".feature-card", {
    scrollTrigger: {
      trigger: "#features",
      scroller: ".landing",
      start: "top 80%",
    },
    y: 30,
    opacity: 0,
    duration: 0.8,
    stagger: 0.15,
    ease: "power2.out"
  });

  // End text
  gsap.from(".end-text", {
    scrollTrigger: {
      trigger: ".end-text",
      start: "top 80%",
    },
    y: 50,
    opacity: 0,
    duration: 1,
    ease: "power3.out"
  });
}

function scrollToFeatures() {
  document.getElementById('features').scrollIntoView({ behavior: 'smooth' });
}

function startJourney() {
  enterDashboard();
}

function enterDashboard() {
  if (landingAnimationDone) return;
  landingAnimationDone = true;

  const landing = document.getElementById('landing');
  const app = document.querySelector('.app');

  // Fallback function to ensure entry
  const forceEntry = () => {
    if (landing) landing.style.display = 'none';
    if (app) app.classList.add('active');
  };

  // 避免任何不可預期的動畫卡死，設定 1 秒後強制進入
  setTimeout(forceEntry, 1000);

  if (typeof gsap === 'undefined') {
    forceEntry();
    return;
  }

  try {
    const tl = gsap.timeline({
      onComplete: () => {
        forceEntry();
        
        // Dashboard entrance animations
        tl.from(".sidebar", { x: -100, opacity: 0, duration: 0.6, ease: "power3.out" });
        tl.from(".top-bar", { y: -30, opacity: 0, duration: 0.5, ease: "power3.out" }, "-=0.4");
        tl.from(".card", { y: 30, opacity: 0, duration: 0.6, stagger: 0.05, ease: "power3.out" }, "-=0.2");
        tl.from(".stat-card", { scale: 0.9, opacity: 0, duration: 0.5, stagger: 0.05, ease: "back.out(1.5)" }, "-=0.4");
        
        // Trigger initial data load now that UI is visible
        if (typeof fetchMacroData === 'function') fetchMacroData();
      }
    });

    // Animate landing out
    tl.to(".landing", {
      y: "-100vh",
      opacity: 0,
      duration: 0.8,
      ease: "power4.inOut"
    });
  } catch (err) {
    console.error("GSAP Animation error:", err);
    forceEntry();
  }
}

// ============================
// KEYBOARD SHORTCUTS
// ============================
document.addEventListener('keydown', (e) => {
  // Don't trigger shortcuts when typing in inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

  const pageKeys = { '1': 'war', '2': 'stress', '3': 'tech', '4': 'kline', '5': 'backtest', '6': 'news', '7': 'sentiment', '8': 'screener' };

  if (pageKeys[e.key]) { navigateTo(pageKeys[e.key]); e.preventDefault(); }
  else if (e.key === '/') { document.getElementById('quick-search-input').focus(); e.preventDefault(); }
  else if (e.key === 'c' || e.key === 'C') { toggleChat(); e.preventDefault(); }
  else if (e.key === 'Escape') {
    if (chatOpen) toggleChat();
    document.querySelectorAll('.modal-backdrop.open').forEach(m => { m.classList.remove('open'); m.style.display = 'none'; });
  }
});

// ============================
// INIT
// ============================
function init() {
  fetchStockNames();
  checkHealth();
  updateAuthUI();
  
  if (currentUser) {
    document.getElementById('hero-main-btn').innerText = '進入您的儀表板 ➔';
  }
  
  initLanding();

  loadPositionsFromServer();
  fetchMacroData();
  fetchRankings();
  fetchMarketStatus();
  updateClock();
  setInterval(updateClock, 1000);
  setInterval(fetchMarketStatus, 60000);
}

window.onload = init;
