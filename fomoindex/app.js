(() => {
  'use strict';
  const view = document.getElementById('view');
  const toastEl = document.getElementById('toast');
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const usd = (n, d = 2) => (n < 0 ? '-' : '') + '$' + Math.abs(Number(n) || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sol = (n, d = 3) => (Number(n) || 0).toFixed(d) + ' SOL';
  const pct = (w) => Math.round((Number(w) || 0) * 100) + '%';
  const short = (a) => (a ? a.slice(0, 4) + '…' + a.slice(-4) : '');
  const ago = (ts) => { if (!ts) return 'never'; const m = Math.round((Date.now() - new Date(ts)) / 60000); return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.round(m / 60) + ' h ago' : Math.round(m / 1440) + ' d ago'; };
  const SOL_MINT = 'So11111111111111111111111111111111111111112';
  const RULES = { minWeight: 2, minLiquidity: 50000, maxTokens: 12 };
  const LADDER = [{ m: 1, bps: 250 }, { m: 5, bps: 200 }, { m: 15, bps: 150 }, { m: 30, bps: 100 }, { m: 60, bps: 75 }, { m: 120, bps: 50 }, { m: 360, bps: 40 }, { m: 1440, bps: 30 }];
  const every = (m) => m < 60 ? `${m} min` : m < 1440 ? `${m / 60} h` : '24 h';
  const feeOf = (m) => (LADDER.find((l) => l.m === m) || LADDER[5]).bps / 100;
  let toastT; const toast = (m) => { toastEl.textContent = m; toastEl.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove('show'), 2200); };

  /* ---------- api ---------- */
  async function api(path, opts = {}) {
    const r = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(S.token ? { Authorization: 'Bearer ' + S.token } : {}) }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(j.error || 'request failed'); e.status = r.status; throw e; }
    return j;
  }

  /* ---------- wallet ---------- */
  const S = { wallet: null, token: sessionStorage.getItem('fi_token') || null, provider: null, traders: [], selected: new Map(), name: '', amount: 1, interval: 120, preview: null };
  const B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  function b58(bytes) { const d = [0]; for (const b of bytes) { let c = b; for (let j = 0; j < d.length; j++) { c += d[j] << 8; d[j] = c % 58; c = (c / 58) | 0; } while (c) { d.push(c % 58); c = (c / 58) | 0; } } let s = ''; for (const b of bytes) { if (b) break; s += '1'; } for (let j = d.length - 1; j >= 0; j--) s += B58[d[j]]; return s; }
  function providers() {
    const l = [];
    if (window.phantom?.solana?.isPhantom) l.push({ name: 'Phantom', p: window.phantom.solana });
    if (window.solflare?.isSolflare) l.push({ name: 'Solflare', p: window.solflare });
    if (window.backpack?.isBackpack) l.push({ name: 'Backpack', p: window.backpack });
    if (!l.length && window.solana) l.push({ name: 'Wallet', p: window.solana });
    return l;
  }
  async function connect() {
    const list = providers();
    if (!list.length) { modal(`<h3>No wallet found</h3><p class="note">Install Phantom, Solflare or Backpack, or open this page in your wallet's browser on mobile.</p><a class="btn primary" href="https://phantom.app" target="_blank" rel="noopener">Get Phantom</a>`); return; }
    const chosen = list.length === 1 ? list[0] : await pick(list);
    if (!chosen) return;
    try {
      const r = await chosen.p.connect();
      const pub = (r?.publicKey || chosen.p.publicKey).toString();
      S.provider = chosen.p; S.wallet = pub;
      const { nonce, message } = await api('/api/auth/nonce', { method: 'POST', body: { wallet: pub } });
      const signed = await chosen.p.signMessage(new TextEncoder().encode(message), 'utf8');
      const sigBytes = signed.signature || signed;
      const v = await api('/api/auth/verify', { method: 'POST', body: { wallet: pub, nonce, signature: b58(sigBytes) } });
      S.token = v.token; sessionStorage.setItem('fi_token', v.token);
      paintWallet(); toast('Signed in'); route();
    } catch (e) { toast(e.message || 'Could not connect'); }
  }
  function pick(list) {
    return new Promise((res) => modal(`<h3>Choose a wallet</h3>${list.map((w, i) => `<button class="btn ghost" data-i="${i}">${w.name}</button>`).join('')}`, (el) => { el.querySelectorAll('[data-i]').forEach((b) => b.addEventListener('click', () => { closeModal(); res(list[+b.dataset.i]); })); }, () => res(null)));
  }
  async function restore() {
    try { const me = await api('/api/auth/me'); if (me.wallet) { S.wallet = me.wallet; const p = providers()[0]; if (p) { try { await p.p.connect({ onlyIfTrusted: true }); S.provider = p.p; } catch (e) { /* user will reconnect when sending */ } } } } catch (e) { /* offline */ }
    paintWallet();
  }
  function paintWallet() {
    const b = document.getElementById('walletBtn');
    b.innerHTML = S.wallet ? `<i></i>${short(S.wallet)}` : 'Connect wallet';
    b.onclick = S.wallet ? () => modal(`<h3>${short(S.wallet)}</h3><p class="note">Signed in with this wallet. Withdrawals from your indexes go here.</p><button class="btn ghost" id="signout">Sign out</button>`, (el) => el.querySelector('#signout').addEventListener('click', async () => { await api('/api/auth/me', { method: 'DELETE' }); S.wallet = null; S.token = null; sessionStorage.removeItem('fi_token'); closeModal(); paintWallet(); route(); })) : connect;
  }

  /* ---------- modal ---------- */
  function modal(html, bind, onClose) {
    closeModal();
    const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.id = 'modal';
    bg.innerHTML = `<div class="modal">${html}</div>`;
    bg.addEventListener('click', (e) => { if (e.target === bg) { closeModal(); onClose && onClose(); } });
    document.body.appendChild(bg); bind && bind(bg);
  }
  function closeModal() { document.getElementById('modal')?.remove(); }

  /* ---------- routing ---------- */
  function route() {
    const h = location.hash.replace(/^#/, '') || 'build';
    document.querySelectorAll('#tabs a').forEach((a) => a.classList.toggle('on', h.startsWith(a.dataset.tab) || (h.startsWith('ix/') && a.dataset.tab === 'mine')));
    if (h.startsWith('ix/')) return renderIndex(h.slice(3));
    if (h === 'mine') return renderMine();
    return renderBuild();
  }
  addEventListener('hashchange', route);

  /* ---------- build ---------- */
  async function renderBuild() {
    if (!S.traders.length) { view.innerHTML = `<div class="app-head"><div><h1>Build an index</h1><p>Loading the leaderboard…</p></div></div>`; try { S.traders = (await api('/api/traders')).traders || []; } catch (e) { S.traders = []; } }
    view.innerHTML = `
      <div class="app-head"><div><h1>Build an index</h1><p>Pick traders, set the weights, fund it. Takes two minutes.</p></div></div>
      <div class="steps" id="steps">
        <div class="on"><b>1</b>Pick traders</div><div><b>2</b>Set weights</div><div><b>3</b>Name &amp; fund</div>
      </div>
      <div class="build">
        <div>
          <div class="toolbar">
            <div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="q" placeholder="Search traders by name or handle"></div>
            <select class="input" id="sort" style="width:auto"><option value="rank">By rank</option><option value="pnl">By 7d PnL</option><option value="recent">Recently active</option></select>
          </div>
          <div class="traders-grid" id="grid"></div>
        </div>
        <aside class="panel" id="panel"></aside>
      </div>`;
    const grid = document.getElementById('grid');
    const paintGrid = () => {
      const qv = (document.getElementById('q').value || '').toLowerCase();
      const sort = document.getElementById('sort').value;
      let list = S.traders.filter((t) => !qv || (t.handle + ' ' + (t.name || '')).toLowerCase().includes(qv));
      list.sort((a, b) => sort === 'pnl' ? (Number(b.pnl_7d) || -1e18) - (Number(a.pnl_7d) || -1e18) : sort === 'recent' ? new Date(b.positions_at || 0) - new Date(a.positions_at || 0) : (a.rank || 1e9) - (b.rank || 1e9));
      grid.innerHTML = list.length ? list.map((t) => `<div class="tcard ${S.selected.has(t.handle) ? 'on' : ''} ${t.has_wallet ? '' : 'nowallet'}" data-h="${esc(t.handle)}" title="${t.has_wallet ? '' : 'No wallet on file yet, cannot be mirrored'}">
          <span class="rank">#${t.rank || '–'}</span>
          <div class="top"><div class="ava">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : esc((t.name || t.handle).slice(0, 1).toUpperCase())}</div><div><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}</small></div></div>
          <div class="pnl ${Number(t.pnl_7d) < 0 ? 'neg' : 'pos'}">${t.pnl_7d != null ? (Number(t.pnl_7d) >= 0 ? '+' : '') + usd(Number(t.pnl_7d), 0) : '—'}<small>7 day pnl</small></div>
          <div class="holds">${(t.top || []).map((x) => `<span>${esc(x.symbol)} ${pct(x.weight)}</span>`).join('') || `<span>${t.has_wallet ? 'all in SOL right now' : 'wallet pending'}</span>`}</div>
          <div class="check"><svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg></div></div>`).join('')
        : `<div class="empty" style="grid-column:1/-1">No traders yet. The leaderboard syncs from fomo; traders appear here once their wallet is known.</div>`;
      grid.querySelectorAll('.tcard:not(.nowallet)').forEach((c) => c.addEventListener('click', () => toggle(c.dataset.h)));
    };
    document.getElementById('q').addEventListener('input', paintGrid); document.getElementById('sort').addEventListener('change', paintGrid);
    paintGrid(); paintPanel();
  }
  function toggle(handle) {
    if (S.selected.has(handle)) S.selected.delete(handle);
    else { if (S.selected.size >= 10) return toast('Ten traders is the maximum'); S.selected.set(handle, { weight: 1 }); }
    document.querySelectorAll('.tcard').forEach((c) => c.classList.toggle('on', S.selected.has(c.dataset.h)));
    paintPanel(); loadPreview();
  }
  function weights() { const tot = [...S.selected.values()].reduce((s, v) => s + v.weight, 0) || 1; return [...S.selected.entries()].map(([h, v]) => ({ handle: h, weight: v.weight / tot })); }
  function paintPanel() {
    const panel = document.getElementById('panel'); if (!panel) return;
    const n = S.selected.size;
    const step = !n ? 0 : S.name ? 2 : 1;
    document.querySelectorAll('#steps div').forEach((d, i) => { d.classList.toggle('on', i === step); d.classList.toggle('done', i < step); });
    if (!n) { panel.innerHTML = `<div class="card"><div class="kicker">Your index</div><p class="note">Tap traders on the left to add them. Up to ten. You can weight them in the next step.</p>
      <div class="hint-list"><span><b>1</b>Pick 3 to 6 traders with different styles</span><span><b>2</b>Weight the ones you trust most</span><span><b>3</b>Pick a tempo, 2 h is the sweet spot</span><span><b>4</b>Fund with 0.2 SOL or more</span></div></div>`; return; }
    const ws = weights();
    const tr = (h) => S.traders.find((t) => t.handle === h) || { handle: h };
    panel.innerHTML = `
      <div class="card">
        <div class="kicker">Your index · ${n} trader${n > 1 ? 's' : ''}</div>
        <div style="display:flex;gap:16px;align-items:center">
          <svg class="donut" id="donut" viewBox="0 0 42 42"></svg>
          <div class="squad">${ws.map((w) => { const t = tr(w.handle); return `<div class="ava" title="${esc(t.handle)}">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : esc((t.name || t.handle).slice(0, 1).toUpperCase())}</div>`; }).join('')}</div>
        </div>
        <div class="kicker" style="margin-top:16px">Weights</div>
        <div class="weights">${ws.map((w) => { const t = tr(w.handle); return `<div class="wrow" data-h="${esc(w.handle)}"><div class="ava">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : esc((t.name || t.handle).slice(0, 1).toUpperCase())}</div><div><b>${esc(t.name || t.handle)}</b><br><input type="range" min="1" max="10" value="${S.selected.get(w.handle).weight}"></div><span class="pct">${pct(w.weight)}</span><button class="x" title="Remove">×</button></div>`; }).join('')}</div>
        <div class="actions" style="margin-top:12px"><button class="btn ghost sm" id="equal">Equal split</button></div>
      </div>
      <div class="card preview" id="preview"><div class="kicker">What it would hold right now</div><p class="note">Reading your traders' wallets…</p></div>
      <div class="card">
        <div class="kicker">Name &amp; fund</div>
        <div class="field"><label>Index name</label><input class="input" id="name" maxlength="40" placeholder="e.g. Legends only" value="${esc(S.name)}"></div>
        <div class="field" style="margin-top:12px"><label>How often it mirrors your traders</label>
          <div class="amounts" id="ivl">${LADDER.map((l) => `<button data-m="${l.m}" class="${S.interval === l.m ? 'on' : ''}" title="${feeOf(l.m)}% fee per trade">${every(l.m)}</button>`).join('')}</div>
          <p class="note" id="feeNote">Every <b>${every(S.interval)}</b> · fee <b>${feeOf(S.interval)}%</b> of each trade. Faster mirroring costs more; 2 h is the sweet spot for most.</p></div>
        <div class="field" style="margin-top:12px"><label>Amount to fund</label><div class="amounts">${[0.25, 0.5, 1, 2, 5].map((a) => `<button data-a="${a}" class="${S.amount === a ? 'on' : ''}">${a} SOL</button>`).join('')}</div></div>
        <input class="input" id="amount" type="number" min="0.1" step="0.05" style="margin-top:10px" value="${S.amount}">
        <button class="btn accent lg" id="create" style="width:100%;margin-top:14px">${S.wallet ? 'Create index' : 'Connect wallet to create'}</button>
        <p class="note" style="margin-top:10px">You will get a deposit address next. The index starts trading on its first cycle after the SOL arrives.</p>
      </div>`;
    donut(ws);
    panel.querySelectorAll('.wrow input').forEach((r) => r.addEventListener('input', () => { S.selected.get(r.closest('.wrow').dataset.h).weight = +r.value; const ws2 = weights(); panel.querySelectorAll('.wrow').forEach((row) => { row.querySelector('.pct').textContent = pct(ws2.find((w) => w.handle === row.dataset.h).weight); }); donut(ws2); schedulePreview(); }));
    panel.querySelectorAll('.wrow .x').forEach((b) => b.addEventListener('click', () => toggle(b.closest('.wrow').dataset.h)));
    panel.querySelector('#equal').addEventListener('click', () => { for (const v of S.selected.values()) v.weight = 1; paintPanel(); schedulePreview(); });
    panel.querySelectorAll('#ivl button').forEach((b) => b.addEventListener('click', () => { S.interval = +b.dataset.m; panel.querySelectorAll('#ivl button').forEach((o) => o.classList.toggle('on', o === b)); panel.querySelector('#feeNote').innerHTML = `Every <b>${every(S.interval)}</b> · fee <b>${feeOf(S.interval)}%</b> of each trade. Faster mirroring costs more; 2 h is the sweet spot for most.`; }));
    panel.querySelector('#name').addEventListener('input', (e) => { S.name = e.target.value; const step = !S.selected.size ? 0 : S.name ? 2 : 1; document.querySelectorAll('#steps div').forEach((d, i) => { d.classList.toggle('on', i === step); d.classList.toggle('done', i < step); }); });
    panel.querySelectorAll('.amounts button').forEach((b) => b.addEventListener('click', () => { S.amount = +b.dataset.a; panel.querySelector('#amount').value = S.amount; panel.querySelectorAll('.amounts button').forEach((o) => o.classList.toggle('on', o === b)); }));
    panel.querySelector('#amount').addEventListener('input', (e) => { S.amount = +e.target.value || 0; panel.querySelectorAll('.amounts button').forEach((o) => o.classList.toggle('on', +o.dataset.a === S.amount)); });
    panel.querySelector('#create').addEventListener('click', create);
    if (S.preview) paintPreview();
  }
  const COLS = ['#516af6', '#8a92ff', '#21c95e', '#ffc74f', '#ff622e', '#c084fc', '#38bdf8', '#f472b6', '#a3e635', '#fb923c', '#7c8aa8', '#e879f9'];
  function donutSvg(parts, label) {
    let off = 0;
    return parts.map((p, i) => { const len = Math.max(0, Math.min(100, p.weight * 100)); const x = `<circle cx="21" cy="21" r="15.9" fill="none" stroke="${p.color || COLS[i % COLS.length]}" stroke-width="5" stroke-dasharray="${len} ${100 - len}" stroke-dashoffset="${25 - off}"/>`; off += len; return x; }).join('') + `<circle cx="21" cy="21" r="15.9" fill="none" stroke="rgba(203,208,235,.08)" stroke-width="5" stroke-dasharray="${Math.max(0, 100 - off)} ${Math.min(100, off)}" stroke-dashoffset="${25 - off}"/>` + (label == null ? '' : `<text x="21" y="22.5" text-anchor="middle" font-size="5" fill="#EAEDFF" font-family="Geist Mono">${esc(label)}</text>`);
  }
  function donut(ws) {
    const el = document.getElementById('donut'); if (!el) return;
    el.innerHTML = donutSvg(ws, ws.length);
  }
  let countT;
  function countdown(el, due) {
    clearInterval(countT); if (!el) return;
    const tick = () => { const left = due - Date.now(); if (left <= 0) { el.textContent = 'due now'; return; } const h = Math.floor(left / 3600e3), m = Math.floor((left % 3600e3) / 60e3), sec = Math.floor((left % 60e3) / 1e3); el.textContent = h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`; };
    tick(); countT = setInterval(tick, 1000);
  }
  let previewT; const schedulePreview = () => { clearTimeout(previewT); previewT = setTimeout(loadPreview, 400); };
  async function loadPreview() {
    const handles = [...S.selected.keys()]; if (!handles.length) return;
    try {
      const ports = await Promise.all(handles.map((h) => api(`/api/traders/${encodeURIComponent(h)}/positions`).catch(() => null)));
      S.preview = { ports: Object.fromEntries(handles.map((h, i) => [h, ports[i]])) };
      paintPreview();
    } catch (e) { /* ignore */ }
  }
  function blend() {
    const ws = weights(); const t = new Map(); const info = new Map();
    for (const w of ws) {
      const p = S.preview?.ports?.[w.handle]; if (!p) continue;
      for (const r of p.rows) {
        if (r.mint === SOL_MINT) continue;
        if (r.weight * 100 < RULES.minWeight || (r.liquidity_usd || 0) < RULES.minLiquidity) continue;
        t.set(r.mint, (t.get(r.mint) || 0) + w.weight * r.weight); info.set(r.mint, r);
      }
    }
    const rows = [...t.entries()].sort((a, b) => b[1] - a[1]).slice(0, RULES.maxTokens).map(([mint, w]) => ({ mint, weight: w, ...info.get(mint) }));
    const cash = Math.max(0, 1 - rows.reduce((s, r) => s + r.weight, 0));
    return { rows, cash };
  }
  function paintPreview() {
    const el = document.getElementById('preview'); if (!el || !S.preview) return;
    const { rows, cash } = blend();
    el.innerHTML = `<div class="kicker">What it would hold right now</div>
      <div class="bar-row"><span>SOL</span><div class="bar"><i class="sol" style="width:${cash * 100}%"></i></div><small>${pct(cash)}</small></div>
      ${rows.map((r) => `<div class="bar-row"><span title="${esc(r.name || '')}">${esc(r.symbol || r.mint.slice(0, 4))}</span><div class="bar"><i style="width:${r.weight * 100}%"></i></div><small>${pct(r.weight)}</small></div>`).join('')}
      <p class="note" style="margin-top:10px">${rows.length ? `${rows.length} token${rows.length > 1 ? 's' : ''} plus SOL as cash. Updates as your traders trade.` : 'Your traders are sitting in SOL right now. The index will buy as soon as they do.'}</p>`;
  }
  async function create() {
    if (!S.wallet) return connect();
    if (!S.selected.size) return toast('Pick at least one trader');
    const btn = document.getElementById('create'); btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const r = await api('/api/ix', { method: 'POST', body: { name: S.name || 'My index', traders: weights(), interval_min: S.interval } });
      S.selected.clear(); S.name = ''; S.preview = null;
      location.hash = 'ix/' + r.id;
      setTimeout(() => depositModal(r.id, r.deposit, S.amount), 300);
    } catch (e) { toast(e.message); btn.disabled = false; btn.textContent = 'Create index'; }
  }

  /* ---------- deposit ---------- */
  function depositModal(id, addr, amount) {
    const url = `solana:${addr}?amount=${amount || 1}&label=FOMOINDEX`;
    modal(`<h3>Fund your index</h3>
      <p class="note">Send SOL to this address from any wallet. Scan with your phone's wallet or pay directly from the wallet you signed in with.</p>
      <div class="qr" id="qr"></div>
      <div class="addr" id="addr" title="Click to copy">${esc(addr)}</div>
      <div class="field"><label>Amount</label><input class="input" id="damt" type="number" min="0.05" step="0.05" value="${amount || 1}"></div>
      <button class="btn accent lg" id="pay">Send with wallet</button>
      <div class="mini-steps"><span><b>1</b>SOL lands in the index wallet</span><span><b>2</b>Next cycle buys the basket</span><span><b>3</b>It mirrors your traders from then on</span></div>
      <details><summary class="note" style="cursor:pointer">I sent it from another wallet</summary><div class="field" style="margin-top:10px"><label>Paste the transaction signature so the index can count it</label><input class="input" id="sig" placeholder="5Kd…"><button class="btn ghost sm" id="sigbtn" style="margin-top:8px">Record deposit</button></div></details>`,
      (el) => {
        try { const q = qrcode(0, 'M'); q.addData(url); q.make(); el.querySelector('#qr').innerHTML = q.createSvgTag({ cellSize: 4, margin: 0, scalable: true }); } catch (e) { /* no qr */ }
        el.querySelector('#addr').addEventListener('click', async () => { try { await navigator.clipboard.writeText(addr); toast('Address copied'); } catch (e) { /* ignore */ } });
        el.querySelector('#pay').addEventListener('click', () => pay(id, addr, +el.querySelector('#damt').value || 0, el.querySelector('#pay')));
        el.querySelector('#sigbtn').addEventListener('click', async () => { const sig = el.querySelector('#sig').value.trim(); if (!sig) return; try { const r = await api(`/api/ix/${id}/deposit`, { method: 'POST', body: { sig } }); toast(`Deposit of ${r.sol?.toFixed(3) || ''} SOL recorded`); closeModal(); renderIndex(id); } catch (e) { toast(e.message); } });
      });
  }
  async function pay(id, addr, amount, btn) {
    if (!(amount > 0)) return toast('Enter an amount');
    if (!S.provider) { const p = providers()[0]; if (!p) return toast('No wallet in this browser'); try { await p.p.connect(); S.provider = p.p; } catch (e) { return toast('Wallet did not connect'); } }
    btn.disabled = true; btn.textContent = 'Confirm in wallet…';
    try {
      const w3 = window.solanaWeb3; const conn = new w3.Connection('https://api.mainnet-beta.solana.com', 'confirmed');
      const from = new w3.PublicKey(S.provider.publicKey.toString());
      const tx = new w3.Transaction().add(w3.SystemProgram.transfer({ fromPubkey: from, toPubkey: new w3.PublicKey(addr), lamports: Math.round(amount * w3.LAMPORTS_PER_SOL) }));
      const { blockhash } = await conn.getLatestBlockhash('confirmed'); tx.recentBlockhash = blockhash; tx.feePayer = from;
      const r = await S.provider.signAndSendTransaction(tx);
      const sig = r.signature || r;
      btn.textContent = 'Confirming…';
      for (let i = 0; i < 30; i++) { const st = await conn.getSignatureStatuses([sig]); const s = st.value[0]; if (s && (s.confirmationStatus === 'confirmed' || s.confirmationStatus === 'finalized')) break; await new Promise((r2) => setTimeout(r2, 1500)); }
      const rec = await api(`/api/ix/${id}/deposit`, { method: 'POST', body: { sig } });
      toast(`${rec.sol?.toFixed(3) || amount} SOL deposited`); closeModal(); renderIndex(id);
    } catch (e) { toast(e.message || 'Payment cancelled'); btn.disabled = false; btn.textContent = 'Send with wallet'; }
  }

  /* ---------- my indexes ---------- */
  async function renderMine() {
    if (!S.wallet) { view.innerHTML = `<div class="app-head"><div><h1>My indexes</h1><p>Sign in with your wallet to see them.</p></div></div><div class="empty"><button class="btn primary" id="c2">Connect wallet</button></div>`; document.getElementById('c2').addEventListener('click', connect); return; }
    view.innerHTML = `<div class="app-head"><div><h1>My indexes</h1><p>Everything you have built, live.</p></div><a class="btn primary" href="#build">New index</a></div><div class="ix-grid" id="list"><div class="ix skel" style="height:140px"></div><div class="ix skel" style="height:140px"></div></div>`;
    try {
      const { indexes } = await api('/api/ix');
      document.getElementById('list').innerHTML = indexes.length ? indexes.map((ix) => { const dep = Number(ix.deposited_sol) || 0; const nav = Number(ix.nav_sol) || 0; const chg = dep ? ((nav + Number(ix.withdrawn_sol || 0)) / dep - 1) : 0; return `<a class="ix" href="#ix/${esc(ix.id)}">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h3>${esc(ix.name)}</h3><span class="pill ${esc(ix.status)}"><i></i>${esc(ix.status)}</span></div>
          <div class="navv">${nav ? sol(nav) : '—'}<small>${ix.nav_usd ? usd(ix.nav_usd, 0) : 'awaiting deposit'}</small></div>
          <div style="display:flex;justify-content:space-between;margin-top:10px;font-size:13px;color:var(--muted)"><span>${(ix.traders || []).length} traders · every ${every(ix.interval_min || 120)}</span><span class="${chg >= 0 ? 'pos' : 'neg'}" style="font-family:var(--mono)">${dep ? (chg >= 0 ? '+' : '') + (chg * 100).toFixed(1) + '%' : ''}</span></div></a>`; }).join('')
        : `<div class="empty-state" style="grid-column:1/-1"><div class="ico"><svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 9v6M9 12h6"/></svg></div><b>No indexes yet</b><p>Pick a few traders from the leaderboard, set the pace, and fund it with SOL. Takes about two minutes.</p><a class="btn accent" href="#build">Build your first index →</a></div>`;
    } catch (e) { document.getElementById('list').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  /* ---------- index detail ---------- */
  let refreshT;
  async function renderIndex(id) {
    clearInterval(refreshT);
    if (!S.wallet) return renderMine();
    if (!document.getElementById('ixroot')) view.innerHTML = `<div id="ixroot"><div class="app-head"><div><h1 class="skel">Loading index</h1></div></div></div>`;
    let d;
    try { d = await api('/api/ix/' + encodeURIComponent(id)); } catch (e) { view.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const dep = d.deposited_sol || 0; const chg = dep ? ((d.nav_sol + (d.withdrawn_sol || 0)) / dep - 1) : null;
    const targetOf = (mint) => d.target.find((t) => t.mint === mint)?.weight || 0;
    const rows = [...d.holdings];
    for (const t of d.target) if (!rows.find((r) => r.mint === t.mint)) rows.push({ mint: t.mint, symbol: t.symbol, icon: t.icon, amount: 0, usd: 0, weight: 0 });
    rows.sort((a, b) => Math.max(b.weight, targetOf(b.mint)) - Math.max(a.weight, targetOf(a.mint)));
    document.getElementById('ixroot').innerHTML = `
      <div class="app-head"><div><div class="kicker"><a href="#mine">← My indexes</a></div><h1>${esc(d.name)} <span class="pill ${esc(d.status)}" style="vertical-align:middle;margin-left:8px"><i></i>${esc(d.status)}</span></h1>
        <p>Mirrors ${d.traders.map((t) => '@' + esc(t.handle) + ' ' + pct(t.weight)).join(' · ')}</p></div>
        <div class="actions" style="margin:0">
          ${d.status === 'closed' ? '' : `<button class="btn ghost" id="depBtn">Deposit</button><button class="btn ghost" id="pauseBtn">${d.status === 'paused' ? 'Resume' : 'Pause'}</button><button class="btn danger" id="wdBtn">Withdraw all</button>`}
        </div></div>
      <div class="detail">
        <div>
          <div class="card">
            <div class="stat-row">
              <div class="stat"><b>${sol(d.nav_sol)}</b><small>Index value</small></div>
              <div class="stat"><b>${usd(d.nav_usd, 0)}</b><small>In USD</small></div>
              <div class="stat"><b class="${chg == null ? '' : chg >= 0 ? 'pos' : 'neg'}">${chg == null ? '—' : (chg >= 0 ? '+' : '') + (chg * 100).toFixed(1) + '%'}</b><small>Since deposit</small></div>
              <div class="stat"><b id="nextRb" style="font-size:${d.status === 'active' && dep ? 20 : 15}px">${d.status !== 'active' ? d.status : !dep ? 'after deposit' : '…'}</b><small>Next rebalance</small></div>
            </div>
            <div class="meta-row"><span class="pill"><i></i>every ${every(d.interval_min || 120)}</span><span>Fee <b>${(d.fee_bps || 0) / 100}%</b> per trade</span><span><b>${sol(d.fees_paid_sol || 0, 4)}</b> paid in fees</span><span>Last cycle <b>${ago(d.last_rebalance)}</b></span></div>
            ${dep ? `<canvas class="chart" id="chart" width="800" height="220"></canvas>` : `
            <div class="next-steps">
              <div class="ns-head"><b>Waiting for your first deposit</b><p>The index wallet is ready. Here is what happens once SOL lands in it.</p></div>
              <ol>
                <li><b>Send SOL</b><span>Any amount from 0.2 SOL, from any wallet, to the index wallet on the right.</span></li>
                <li><b>First cycle buys the basket</b><span>Within ${every(d.interval_min || 120)} the index swaps into what your traders hold, blended by weight.</span></li>
                <li><b>Then it mirrors</b><span>Every ${every(d.interval_min || 120)} it checks your traders and trades only what has drifted more than 2.5%.</span></li>
              </ol>
              ${d.status === 'closed' ? '' : '<button class="btn accent" id="depBtn2">Deposit SOL</button>'}
            </div>`}
          </div>
          <div class="card" style="margin-top:16px">
            <div class="hold-head"><div><div class="kicker">Holdings</div><p class="note">${d.nav_usd > 0 ? `${d.holdings.filter((r) => r.mint !== SOL_MINT && r.usd > 0.5).length} tokens plus SOL as cash` : 'Target basket, bought on the first cycle'}</p></div>
              <div class="comp"><svg viewBox="0 0 42 42">${donutSvg((d.holdings.length && d.nav_usd > 0 ? rows.filter((r) => r.weight > 0).map((r, i) => ({ weight: r.weight, color: r.mint === SOL_MINT ? '#7c8aa8' : COLS[i % COLS.length] })) : [...d.target.map((t, i) => ({ weight: t.weight, color: COLS[i % COLS.length] })), { weight: Math.max(0, 1 - d.target.reduce((s2, t) => s2 + t.weight, 0)), color: '#7c8aa8' }]), null)}</svg>
                <div class="legend">${(d.holdings.length && d.nav_usd > 0 ? rows.filter((r) => r.weight > 0).map((r, i) => ({ s: r.symbol || short(r.mint), w: r.weight, c: r.mint === SOL_MINT ? '#7c8aa8' : COLS[i % COLS.length] })) : [...d.target.map((t, i) => ({ s: t.symbol || short(t.mint), w: t.weight, c: COLS[i % COLS.length] })), { s: 'SOL', w: Math.max(0, 1 - d.target.reduce((s2, t) => s2 + t.weight, 0)), c: '#7c8aa8' }]).slice(0, 6).map((l) => `<span><i style="background:${l.c}"></i>${esc(l.s)} ${pct(l.w)}</span>`).join('')}</div></div>
            </div>
            ${rows.length ? `<table><thead><tr><th>Token</th><th class="r">Now</th><th class="r">Target</th><th class="r">Value</th></tr></thead><tbody>
            ${rows.map((r) => `<tr><td><div class="tok"><i>${r.icon ? `<img src="${esc(r.icon)}" alt="">` : ''}</i><b>${esc(r.symbol || r.mint.slice(0, 4))}</b><small>${r.mint === SOL_MINT ? 'cash' : short(r.mint)}</small></div></td><td class="r">${pct(r.weight)}</td><td class="r" style="color:var(--muted)">${r.mint === SOL_MINT ? pct(Math.max(0, 1 - d.target.reduce((s, t) => s + t.weight, 0))) : pct(targetOf(r.mint))}</td><td class="r">${usd(r.usd)}</td></tr>`).join('')}
            </tbody></table>` : `<div class="empty">Waiting for the first deposit.</div>`}
            <p class="note" style="margin-top:12px">Target is what your traders hold right now, blended by weight. The index trades toward it every ${every(d.interval_min || 120)} when a position is more than 2.5% off.</p>
          </div>
        </div>
        <div>
          <div class="card"><div class="kicker">Traders</div>
            ${d.traders.map((t) => `<div class="trader-chip" style="margin-bottom:8px"><div class="ava">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : esc((t.name || t.handle).slice(0, 1).toUpperCase())}</div><div><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}${t.rank ? ' · #' + t.rank : ''}</small></div><span class="w">${pct(t.weight)}</span></div>`).join('')}
          </div>
          <div class="card" style="margin-top:16px"><div class="kicker">Index wallet</div>
            <div class="addr" id="addr2" title="Click to copy">${esc(d.deposit)}</div>
            <div class="kv" style="margin-top:10px"><span>Deposited</span><b>${sol(dep)}</b></div><div class="kv"><span>Withdrawn</span><b>${sol(d.withdrawn_sol || 0)}</b></div>
            <a class="note" href="https://solscan.io/account/${esc(d.deposit)}" target="_blank" rel="noopener" style="color:var(--accent-hi)">View on Solscan ↗</a>
          </div>
          <div class="card" style="margin-top:16px"><div class="kicker">Activity</div>
            <div class="log">${[...d.trades.map((t) => ({ ts: t.ts, text: t.side === 'deposit' ? `Deposit ${sol(t.amount_sol)}` : t.side === 'fee' ? `Fee ${sol(t.amount_sol, 4)}` : `${t.side === 'buy' ? 'Bought' : 'Sold'} ${esc(t.symbol || short(t.mint))} for ${sol(t.amount_sol)}${t.note === 'withdraw' ? ' (withdraw)' : ''}`, sig: t.sig })), ...d.events.filter((e) => e.level !== 'info' || /created|withdrew|paused|active/.test(e.message)).map((e) => ({ ts: e.ts, text: esc(e.message) }))].sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 30).map((x) => `<div><time>${ago(x.ts)}</time><span>${x.text}</span>${x.sig ? `<a href="https://solscan.io/tx/${esc(x.sig)}" target="_blank" rel="noopener">tx ↗</a>` : '<span></span>'}</div>`).join('') || '<div class="note">Nothing yet.</div>'}</div>
          </div>
        </div>
      </div>`;
    chart(document.getElementById('chart'), d.history);
    if (d.status === 'active' && dep) countdown(document.getElementById('nextRb'), (d.last_rebalance ? new Date(d.last_rebalance).getTime() : Date.now()) + (d.interval_min || 120) * 60e3);
    document.getElementById('depBtn2')?.addEventListener('click', () => depositModal(d.id, d.deposit, 1));
    document.getElementById('addr2').addEventListener('click', async () => { try { await navigator.clipboard.writeText(d.deposit); toast('Address copied'); } catch (e) { /* ignore */ } });
    document.getElementById('depBtn')?.addEventListener('click', () => depositModal(d.id, d.deposit, 1));
    document.getElementById('pauseBtn')?.addEventListener('click', async () => { try { await api(`/api/ix/${d.id}/status`, { method: 'POST', body: { status: d.status === 'paused' ? 'active' : 'paused' } }); toast(d.status === 'paused' ? 'Index resumed' : 'Index paused'); renderIndex(id); } catch (e) { toast(e.message); } });
    document.getElementById('wdBtn')?.addEventListener('click', () => modal(`<h3>Withdraw everything?</h3><p class="note">Every token is sold to SOL through Jupiter and the SOL is sent to ${short(S.wallet)}. This closes the index. It takes a minute.</p><button class="btn danger lg" id="wd2">Sell all and withdraw</button><button class="btn ghost" id="wd3">Keep it</button>`, (el) => { el.querySelector('#wd3').addEventListener('click', closeModal); el.querySelector('#wd2').addEventListener('click', async () => { el.querySelector('#wd2').disabled = true; el.querySelector('#wd2').textContent = 'Selling and sending…'; try { const r = await api(`/api/ix/${d.id}/withdraw`, { method: 'POST' }); toast(`${r.sol?.toFixed(4) || 0} SOL sent to your wallet`); closeModal(); renderIndex(id); } catch (e) { toast(e.message); closeModal(); } }); }));
    refreshT = setInterval(() => { if (location.hash === '#ix/' + id) renderIndex(id); }, 60000);
  }
  function chart(c, hist) {
    if (!c) return; const ctx = c.getContext('2d'); const W = c.width, H = c.height;
    ctx.clearRect(0, 0, W, H);
    const pts = (hist || []).map((h) => Number(h.nav_sol) || 0).filter((v) => v >= 0);
    if (pts.length < 2) { ctx.fillStyle = 'rgba(203,208,235,.4)'; ctx.font = '13px Geist Mono, monospace'; ctx.fillText(pts.length ? 'The chart fills in as the index rebalances.' : 'No data yet.', 12, 30); return; }
    const min = Math.min(...pts) * 0.98, max = Math.max(...pts) * 1.02 || 1;
    const x = (i) => 10 + (i / (pts.length - 1)) * (W - 20), y = (v) => H - 14 - ((v - min) / (max - min || 1)) * (H - 34);
    const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, 'rgba(81,106,246,.45)'); g.addColorStop(1, 'rgba(81,106,246,0)');
    ctx.beginPath(); ctx.moveTo(x(0), H); pts.forEach((v, i) => ctx.lineTo(x(i), y(v))); ctx.lineTo(x(pts.length - 1), H); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); pts.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)))); ctx.strokeStyle = pts[pts.length - 1] >= pts[0] ? '#21c95e' : '#ff622e'; ctx.lineWidth = 2.2; ctx.lineJoin = 'round'; ctx.stroke();
    ctx.fillStyle = 'rgba(203,208,235,.5)'; ctx.font = '11px Geist Mono, monospace'; ctx.fillText(pts[pts.length - 1].toFixed(3) + ' SOL', W - 90, y(pts[pts.length - 1]) - 8);
  }

  restore().then(route);
})();
