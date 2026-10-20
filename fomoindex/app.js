(() => {
  'use strict';
  const view = document.getElementById('view');
  const toastEl = document.getElementById('toast');
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const usd = (n, d = 2) => (n < 0 ? '-' : '') + '$' + Math.abs(Number(n) || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const pnl = (n) => n == null ? '—' : (Number(n) >= 0 ? '+' : '') + usd(Number(n), 0);
  const sol = (n, d = 3) => (Number(n) || 0).toFixed(d) + ' SOL';
  const pct = (w) => Math.round((Number(w) || 0) * 100) + '%';
  const chg = (x) => x == null ? '–' : (Number(x) >= 0 ? '+' : '') + (Number(x) * 100).toFixed(1) + '%';
  const MAX_TRADERS = 5;
  const short = (a) => (a ? a.slice(0, 4) + '…' + a.slice(-4) : '');
  const ago = (ts) => { if (!ts) return 'never'; const m = Math.round((Date.now() - new Date(ts)) / 60000); return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.round(m / 60) + ' h ago' : Math.round(m / 1440) + ' d ago'; };
  const ini = (t) => esc((t.name || t.handle || '?').slice(0, 2).toUpperCase());
  const avatar = (t, cls = 'ava') => `<div class="${cls}">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : (cls === 'tbox-art' ? `<b>${ini(t)}</b>` : ini(t))}</div>`;
  const SOL_MINT = 'So11111111111111111111111111111111111111112';
  const RULES = { minWeight: 2, minLiquidity: 50000, maxTokens: 12 };
  const LADDER = [{ m: 1, bps: 100 }, { m: 5, bps: 80 }, { m: 15, bps: 60 }, { m: 30, bps: 50 }, { m: 60, bps: 40 }, { m: 120, bps: 30 }, { m: 360, bps: 25 }, { m: 1440, bps: 20 }];
  const every = (m) => m < 60 ? `${m} min` : m < 1440 ? `${m / 60} h` : '24 h';
  const feeOf = (m) => (LADDER.find((l) => l.m === m) || LADDER[5]).bps / 100;
  const ARROW = '<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
  let toastT; const toast = (m) => { toastEl.textContent = m; toastEl.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove('show'), 2200); };

  /* ---------- api ---------- */
  async function api(path, opts = {}) {
    const r = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(S.token ? { Authorization: 'Bearer ' + S.token } : {}) }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(j.error || 'request failed'); e.status = r.status; throw e; }
    return j;
  }

  /* ---------- wallet ---------- */
  const S = { wallet: null, token: sessionStorage.getItem('fi_token') || null, provider: null, traders: [], known: new Map(), total: 0, q: '', selected: new Map(), name: '', amount: 1, interval: 120, preview: null, focus: null, ports: {} };
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
    if (!list.length) { modal(`<h3>No wallet found</h3><p class="note">Install Phantom, Solflare or Backpack, or open this page in your wallet's browser on mobile.</p><a class="btn btn-ink" href="https://phantom.app" target="_blank" rel="noopener">Get Phantom</a>`); return; }
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
    return new Promise((res) => modal(`<h3>Choose a wallet</h3>${list.map((w, i) => `<button class="btn" data-i="${i}">${w.name}</button>`).join('')}`, (el) => { el.querySelectorAll('[data-i]').forEach((b) => b.addEventListener('click', () => { closeModal(); res(list[+b.dataset.i]); })); }, () => res(null)));
  }
  async function restore() {
    try { const me = await api('/api/auth/me'); if (me.wallet) { S.wallet = me.wallet; const p = providers()[0]; if (p) { try { await p.p.connect({ onlyIfTrusted: true }); S.provider = p.p; } catch (e) { /* user will reconnect when sending */ } } } } catch (e) { /* offline */ }
    paintWallet();
  }
  function paintWallet() {
    const b = document.getElementById('walletBtn');
    b.innerHTML = S.wallet ? `<i></i><span class="mono">${short(S.wallet)}</span>` : 'Connect';
    b.className = S.wallet ? 'btn wallet-btn' : 'btn btn-ink wallet-btn';
    b.onclick = S.wallet ? () => modal(`<h3>${short(S.wallet)}</h3><p class="note">Signed in with this wallet. Withdrawals from your indexes go here.</p><button class="btn" id="signout">Sign out</button>`, (el) => el.querySelector('#signout').addEventListener('click', async () => { await api('/api/auth/me', { method: 'DELETE' }); S.wallet = null; S.token = null; sessionStorage.removeItem('fi_token'); closeModal(); paintWallet(); route(); })) : connect;
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
    document.querySelectorAll('#tabs a, #mtabs a').forEach((a) => a.classList.toggle('on', h.startsWith(a.dataset.tab) || (h.startsWith('ix/') && a.dataset.tab === 'mine')));
    if (h.startsWith('ix/')) return renderIndex(h.slice(3));
    if (h === 'mine') return renderMine();
    if (h.startsWith('build/')) S.focus = decodeURIComponent(h.slice(6));
    return renderBuild();
  }
  addEventListener('hashchange', route);

  /* ---------- build ---------- */
  async function renderBuild() {
    if (!S.traders.length) { view.innerHTML = `<div class="app-h"><div><h1>Build an index</h1><p>Loading fomo traders…</p></div></div>`; await loadTraders('', 0); }
    if (document.getElementById('grid')) { paintGrid(); paintSide(); return; }
    view.innerHTML = `
      <div class="app-h"><div><h1>Build an index</h1><p>Tap a trader to see everything we know about them. Add the ones you want, set the weights, fund it.</p></div>
        <div class="steps" id="steps"><div class="on"><b>1</b>Pick traders</div><div><b>2</b>Set weights</div><div><b>3</b>Name &amp; fund</div></div></div>
      <div class="build">
        <div class="panel">
          <div class="panel-h"><b>Traders</b><span class="sp"></span><small id="tcount">${(S.total || S.traders.length).toLocaleString('en-US')} fomo traders</small></div>
          <div class="toolbar">
            <div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="q" placeholder="Search fomo usernames"></div>
            <select class="sel" id="sort"><option value="rank">Most popular</option><option value="recent">Recently read</option></select>
          </div>
          <table class="tbl" id="grid"><thead><tr><th>#</th><th>Trader</th><th class="hide-s">Holds now</th><th></th></tr></thead><tbody></tbody></table>
          <div class="panel-b" id="more" style="display:flex;justify-content:center;border-top:1px solid var(--line)"></div>
        </div>
        <aside class="side" id="side"></aside>
      </div>`;
    let qt = null;
    document.getElementById('q').addEventListener('input', (e) => { clearTimeout(qt); qt = setTimeout(async () => { await loadTraders(e.target.value, 0); paintGrid(); }, 220); });
    document.getElementById('sort').addEventListener('change', paintGrid);
    paintGrid(); paintSide();
  }
  // the whole fomo directory lives on the server: search and page it there, keep what we have seen in S.known
  async function loadTraders(q, offset) {
    try {
      const r = await api(`/api/traders?q=${encodeURIComponent(q || '')}&offset=${offset}&limit=60`);
      S.total = r.total; S.q = q || '';
      for (const t of r.traders || []) S.known.set(t.handle, t);
      S.traders = offset ? [...S.traders, ...(r.traders || [])] : (r.traders || []);
    } catch (e) { if (!offset) S.traders = []; }
  }
  function paintGrid() {
    const grid = document.querySelector('#grid tbody'); if (!grid) return;
    const sort = document.getElementById('sort').value;
    let list = [...S.traders];
    if (sort === 'recent') list.sort((a, b) => new Date(b.positions_at || 0) - new Date(a.positions_at || 0));
    const tc = document.getElementById('tcount'); if (tc) tc.textContent = `${(S.total || 0).toLocaleString('en-US')} ${S.q ? 'matching' : 'fomo traders'}`;
    const more = document.getElementById('more');
    if (more) {
      more.innerHTML = S.traders.length < (S.total || 0) ? `<button class="btn" id="moreBtn">Show more traders</button>` : '';
      document.getElementById('moreBtn')?.addEventListener('click', async () => { await loadTraders(S.q, S.traders.length); paintGrid(); });
    }
    grid.innerHTML = list.length ? list.map((t, i) => `<tr class="row ${S.selected.has(t.handle) ? 'on' : ''} ${t.has_wallet ? '' : 'nowallet'}" data-h="${esc(t.handle)}" title="${t.has_wallet ? '' : 'Trading wallet not confirmed yet, cannot be mirrored'}">
        <td class="rk ${(t.rank || t.pop) <= 3 ? 'p' : ''}">${(t.rank || t.pop) <= 3 ? `<span>${t.rank || t.pop}</span>` : (t.rank || t.pop || '–')}</td>
        <td><div class="tn">${avatar(t)}<div><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}</small></div></div></td>
        <td class="hide-s"><div class="chips">${(t.top || []).slice(0, 3).map((x) => `<span>${esc(x.symbol)} ${pct(x.weight)}</span>`).join('') || `<span>${!t.has_wallet ? 'not confirmed' : !t.positions_at ? 'tap to read' : t.value_usd ? 'all in SOL' : 'empty wallet'}</span>`}</div></td>
        <td style="width:40px"><div class="chk" title="Add to index"><svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg></div></td></tr>`).join('')
      : `<tr><td colspan="4"><div class="empty">${S.q ? '<b>No trader called that</b>Try part of their fomo username.' : '<b>Could not load the traders</b>Try again in a moment.'}</div></td></tr>`;
    grid.querySelectorAll('tr.row').forEach((r) => {
      r.addEventListener('click', () => focusTrader(r.dataset.h));
      const c = r.querySelector('.chk'); if (c) c.addEventListener('click', (e) => { e.stopPropagation(); toggle(r.dataset.h); });
    });
  }
  function focusTrader(handle) {
    S.focus = handle; history.replaceState(null, '', '#build/' + encodeURIComponent(handle));
    paintSide(); document.getElementById('side')?.scrollTo({ top: 0 }); loadPort(handle).then(() => { if (S.focus === handle) paintBox(); });
    if (innerWidth <= 1040) document.getElementById('side')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  // a trader's holdings, read again once they are a minute old, so an open card follows the trader live
  async function loadPort(handle) {
    const c = S.ports[handle];
    if (c && Date.now() - (c._at || 0) < 60000) return c;
    try { S.ports[handle] = await api(`/api/traders/${encodeURIComponent(handle)}/positions`); } catch (e) { S.ports[handle] = c && !c.error ? c : { error: e.message }; }
    S.ports[handle]._at = Date.now();
    return S.ports[handle];
  }
  setInterval(() => { const h = S.focus; if (h && document.visibilityState === 'visible' && document.getElementById('box')) loadPort(h).then(() => { if (S.focus === h) paintBox(); }); }, 60000);
  function toggle(handle) {
    const t = S.known.get(handle); if (t && !t.has_wallet) return toast('Trading wallet not confirmed yet');
    if (S.selected.has(handle)) S.selected.delete(handle);
    else { if (S.selected.size >= MAX_TRADERS) return toast('Five traders is the maximum'); S.selected.set(handle, { weight: 1 }); }
    document.querySelectorAll('#grid tr.row').forEach((c) => c.classList.toggle('on', S.selected.has(c.dataset.h)));
    paintPanel(); paintBox(); loadPreview();
  }
  function weights() { const tot = [...S.selected.values()].reduce((s, v) => s + v.weight, 0) || 1; return [...S.selected.entries()].map(([h, v]) => ({ handle: h, weight: v.weight / tot })); }
  function paintSide() {
    const side = document.getElementById('side'); if (!side) return;
    side.innerHTML = `<div id="box"></div><div class="panel" id="panel"></div>`;
    paintBox(); paintPanel();
  }

  /* the trader box: everything we know about one fomo account, in the Black Swan finish */
  function paintBox() {
    const el = document.getElementById('box'); if (!el) return;
    const t = S.known.get(S.focus);
    if (!t) {
      el.innerHTML = '';
      if (S.focus && !S.looking) {           // a deep link to a trader that is not on the loaded page yet
        S.looking = S.focus;
        api(`/api/traders?q=${encodeURIComponent(S.focus)}&limit=5`).then((r) => { for (const x of r.traders || []) S.known.set(x.handle, x); })
          .catch(() => {}).finally(() => { S.looking = null; if (S.known.get(S.focus)) { paintBox(); loadPort(S.focus).then(paintBox); } });
      }
      return;
    }
    const p = S.ports[t.handle]; const on = S.selected.has(t.handle);
    const tk = p?.track || null;
    const c24 = tk?.change_24h ?? t.change_24h;
    const spark = (() => {
      const h = (tk?.history || []).map((x) => x.idx).filter((v) => v > 0);
      if (h.length < 2) return '';
      const mn = Math.min(...h), mx = Math.max(...h), W = 260, H = 40;
      const pts = h.map((v, i) => `${(i / (h.length - 1) * W).toFixed(1)},${(H - 3 - ((v - mn) / (mx - mn || 1)) * (H - 6)).toFixed(1)}`).join(' ');
      return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:40px;display:block;margin-top:8px"><polyline points="${pts}" fill="none" stroke="${h[h.length - 1] >= h[0] ? '#118a4f' : '#c9412f'}" stroke-width="2"/></svg>`;
    })();
    const rows = p?.rows ? p.rows.filter((r) => r.mint !== SOL_MINT && r.weight > 0).slice(0, 5) : null;
    const solRow = p?.rows?.find((r) => r.mint === SOL_MINT);
    el.innerHTML = `<div class="tbox"><div class="tbox-in">
      <div class="tbox-top"><img src="assets/mark-navy.svg" alt=""><span class="s">${t.rank ? '#' + t.rank : 'fomo'}</span><button class="x" id="boxClose" title="Close"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
      <div class="tbox-hero">${avatar(t, 'tbox-art')}<div class="tbox-h"><b>@${esc(t.handle)}</b><small>${esc(t.name && t.name !== t.handle ? t.name : 'fomo trader')}</small>${t.rank ? `<span class="rank">#${t.rank} on fomo</span>` : ''}</div></div>
      <div class="tbox-stats">
        <div><small>Tracked 24h</small><b class="${Number(c24) < 0 ? 'down' : Number(c24) > 0 ? 'up' : ''}">${chg(c24)}</b></div>
        <div><small>Since tracked</small><b class="${Number(tk?.change_all) < 0 ? 'down' : Number(tk?.change_all) > 0 ? 'up' : ''}">${chg(tk?.change_all)}</b></div>
      </div>
      ${spark ? `<div class="tbox-sec"><div class="lbl">Tracked return${tk?.since ? ' since ' + new Date(tk.since).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : ''}</div>${spark}</div>` : ''}
      ${!t.has_wallet ? `<div class="tbox-wait">We have not confirmed the wallet this trader trades from yet, so it cannot be mirrored. It lights up as soon as it is confirmed.</div>`
        : !p ? `<div class="tbox-wait">Reading the wallet on-chain…</div>`
        : p.error ? `<div class="tbox-wait">${esc(p.error)}</div>`
        : `<div class="tbox-stats" style="padding-top:0"><div><small>Portfolio</small><b>${usd(p.total_usd, 0)}</b></div><div><small>In SOL</small><b>${pct(solRow?.weight || 0)}</b></div><div><small>Tokens</small><b>${p.rows.filter((r) => r.mint !== SOL_MINT && r.usd > 1).length}</b></div></div>
          <div class="tbox-sec"><div class="lbl">Holds right now</div>
          ${rows.length ? `<div class="tbox-hold">${rows.map((r) => `<div><i>${r.icon ? `<img src="${esc(r.icon)}" alt="">` : ''}</i><b title="${esc(r.name || '')}">${esc(r.symbol || short(r.mint))}</b><div class="bar"><em style="width:${Math.min(100, r.weight * 100)}%"></em></div><small>${pct(r.weight)}</small></div>`).join('')}</div>`
            : `<div class="tbox-wait" style="padding:0 0 6px">${p.total_usd ? 'All in SOL right now. The index buys as soon as they do.' : 'This wallet is empty right now. The index buys as soon as they trade again.'}</div>`}</div>`}
      <div class="tbox-foot"><div class="meta">${t.wallet ? `<a href="https://solscan.io/account/${esc(t.wallet)}" target="_blank" rel="noopener">${short(t.wallet)} ↗</a><br>` : ''}${t.positions_at ? 'wallet read ' + ago(t.positions_at) : 'fomo.family'}</div>
        <button class="btn ${on ? 'off' : ''}" id="boxToggle" ${t.has_wallet ? '' : 'disabled'}>${on ? 'Remove from index' : 'Add to index'}</button></div>
    </div></div>`;
    el.querySelector('#boxClose').addEventListener('click', () => { S.focus = null; history.replaceState(null, '', '#build'); paintBox(); });
    el.querySelector('#boxToggle').addEventListener('click', () => toggle(t.handle));
  }

  function paintPanel() {
    const panel = document.getElementById('panel'); if (!panel) return;
    const n = S.selected.size;
    const step = !n ? 0 : S.name ? 2 : 1;
    document.querySelectorAll('#steps div').forEach((d, i) => { d.classList.toggle('on', i === step); d.classList.toggle('done', i < step); });
    if (!n) { panel.innerHTML = `<div class="panel-h"><b>Your index</b><span class="sp"></span><small>0 / 5 picked</small></div><div class="panel-b"><p class="note">Tap a trader to open their box, then add the ones you want. One to five fomo traders. You weight them in the next step.</p>
      <div class="hint-list" style="margin-top:14px"><span><b>1</b>Pick 1 to 5 fomo traders</span><span><b>2</b>Weight the ones you trust most</span><span><b>3</b>Pick a tempo, 2 h is the sweet spot</span><span><b>4</b>Fund with 0.2 SOL or more</span></div></div>`; return; }
    const ws = weights();
    const tr = (h) => S.known.get(h) || { handle: h };
    panel.innerHTML = `
      <div class="panel-h"><b>Your index</b><span class="sp"></span><small>${n} / 5 picked</small></div>
      <div class="panel-b">
        <div style="display:flex;gap:16px;align-items:center"><svg class="donut" id="donut" viewBox="0 0 42 42"></svg><div class="squad">${ws.map((w) => avatar(tr(w.handle))).join('')}</div></div>
        <div class="field" style="margin-top:16px"><label>Weights</label></div>
        <div class="weights" style="margin-top:8px">${ws.map((w) => { const t = tr(w.handle); return `<div class="wrow" data-h="${esc(w.handle)}">${avatar(t)}<div><b>${esc(t.name || t.handle)}</b><br><input type="range" min="1" max="10" value="${S.selected.get(w.handle).weight}"></div><span class="pct">${pct(w.weight)}</span><button class="x" title="Remove">×</button></div>`; }).join('')}</div>
        <div style="margin-top:12px"><button class="btn sm" id="equal">Equal split</button></div>
      </div>
      <div class="panel-b" id="preview" style="border-top:1px solid var(--line)"><div class="field"><label>What it would hold right now</label></div><p class="note" style="margin-top:8px">Reading your traders' wallets…</p></div>
      <div class="panel-b" style="border-top:1px solid var(--line);display:grid;gap:14px">
        <div class="field"><label>Index name</label><input class="input" id="name" maxlength="40" placeholder="e.g. Legends only" value="${esc(S.name)}"></div>
        <div class="field"><label>How often it mirrors your traders</label>
          <div class="amounts" id="ivl">${LADDER.map((l) => `<button data-m="${l.m}" class="${S.interval === l.m ? 'on' : ''}" title="${feeOf(l.m)}% fee per trade">${every(l.m)}</button>`).join('')}</div>
          <p class="note" id="feeNote">Every <b>${every(S.interval)}</b> · fee <b>${feeOf(S.interval)}%</b> of each trade. Faster costs more; 2 h is the sweet spot for most.</p></div>
        <div class="field"><label>Amount to fund</label><div class="amounts">${[0.25, 0.5, 1, 2, 5].map((a) => `<button data-a="${a}" class="${S.amount === a ? 'on' : ''}">${a} SOL</button>`).join('')}</div>
          <input class="input" id="amount" type="number" min="0.1" step="0.05" value="${S.amount}"></div>
        <button class="btn btn-ink btn-lg" id="create" style="width:100%">${S.wallet ? 'Create index' : 'Connect wallet to create'} ${ARROW}</button>
        <p class="note">You get a deposit address next. The index starts trading on its first cycle after the SOL arrives.</p>
      </div>`;
    donut(ws);
    panel.querySelectorAll('.wrow input').forEach((r) => r.addEventListener('input', () => { S.selected.get(r.closest('.wrow').dataset.h).weight = +r.value; const ws2 = weights(); panel.querySelectorAll('.wrow').forEach((row) => { row.querySelector('.pct').textContent = pct(ws2.find((w) => w.handle === row.dataset.h).weight); }); donut(ws2); schedulePreview(); }));
    panel.querySelectorAll('.wrow .x').forEach((b) => b.addEventListener('click', () => toggle(b.closest('.wrow').dataset.h)));
    panel.querySelector('#equal').addEventListener('click', () => { for (const v of S.selected.values()) v.weight = 1; paintPanel(); schedulePreview(); });
    panel.querySelectorAll('#ivl button').forEach((b) => b.addEventListener('click', () => { S.interval = +b.dataset.m; panel.querySelectorAll('#ivl button').forEach((o) => o.classList.toggle('on', o === b)); panel.querySelector('#feeNote').innerHTML = `Every <b>${every(S.interval)}</b> · fee <b>${feeOf(S.interval)}%</b> of each trade. Faster costs more; 2 h is the sweet spot for most.`; }));
    panel.querySelector('#name').addEventListener('input', (e) => { S.name = e.target.value; const st = !S.selected.size ? 0 : S.name ? 2 : 1; document.querySelectorAll('#steps div').forEach((d, i) => { d.classList.toggle('on', i === st); d.classList.toggle('done', i < st); }); });
    panel.querySelectorAll('.amounts button[data-a]').forEach((b) => b.addEventListener('click', () => { S.amount = +b.dataset.a; panel.querySelector('#amount').value = S.amount; panel.querySelectorAll('.amounts button[data-a]').forEach((o) => o.classList.toggle('on', o === b)); }));
    panel.querySelector('#amount').addEventListener('input', (e) => { S.amount = +e.target.value || 0; panel.querySelectorAll('.amounts button[data-a]').forEach((o) => o.classList.toggle('on', +o.dataset.a === S.amount)); });
    panel.querySelector('#create').addEventListener('click', create);
    if (S.preview) paintPreview();
  }
  const COLS = ['#606af7', '#8a92ff', '#35d07f', '#f0b445', '#ff6b5e', '#c084fc', '#38bdf8', '#f472b6', '#a3e635', '#fb923c', '#8b939d', '#e879f9'];
  function donutSvg(parts, label) {
    let off = 0;
    return parts.map((p, i) => { const len = Math.max(0, Math.min(100, p.weight * 100)); const x = `<circle cx="21" cy="21" r="15.9" fill="none" stroke="${p.color || COLS[i % COLS.length]}" stroke-width="5" stroke-dasharray="${len} ${100 - len}" stroke-dashoffset="${25 - off}"/>`; off += len; return x; }).join('') + `<circle cx="21" cy="21" r="15.9" fill="none" stroke="#cbd0eb14" stroke-width="5" stroke-dasharray="${Math.max(0, 100 - off)} ${Math.min(100, off)}" stroke-dashoffset="${25 - off}"/>` + (label == null ? '' : `<text x="21" y="22.5" text-anchor="middle" font-size="5" fill="#f7f7f7" font-family="Geist Mono">${esc(label)}</text>`);
  }
  function donut(ws) { const el = document.getElementById('donut'); if (el) el.innerHTML = donutSvg(ws, ws.length); }
  let countT;
  function countdown(el, due) {
    clearInterval(countT); if (!el) return;
    const tick = () => { const left = due - Date.now(); if (left <= 0) { el.textContent = 'due now'; return; } const h = Math.floor(left / 3600e3), m = Math.floor((left % 3600e3) / 60e3), sec = Math.floor((left % 60e3) / 1e3); el.textContent = h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`; };
    tick(); countT = setInterval(tick, 1000);
  }
  let previewT; const schedulePreview = () => { clearTimeout(previewT); previewT = setTimeout(loadPreview, 400); };
  async function loadPreview() {
    const handles = [...S.selected.keys()]; if (!handles.length) return;
    await Promise.all(handles.map(loadPort));
    S.preview = { ports: Object.fromEntries(handles.map((h) => [h, S.ports[h]?.rows ? S.ports[h] : null])) };
    paintPreview();
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
    el.innerHTML = `<div class="field"><label>What it would hold right now</label></div><div style="margin-top:8px">
      <div class="bar-row"><span>SOL</span><div class="bar"><i class="sol" style="width:${cash * 100}%"></i></div><small>${pct(cash)}</small></div>
      ${rows.map((r) => `<div class="bar-row"><span title="${esc(r.name || '')}">${esc(r.symbol || r.mint.slice(0, 4))}</span><div class="bar"><i style="width:${r.weight * 100}%"></i></div><small>${pct(r.weight)}</small></div>`).join('')}</div>
      <p class="note" style="margin-top:10px">${rows.length ? `${rows.length} token${rows.length > 1 ? 's' : ''} plus SOL as cash. Updates as your traders trade.` : 'Your traders are sitting in SOL right now. The index buys as soon as they do.'}</p>`;
  }
  async function create() {
    if (!S.wallet) return connect();
    if (!S.selected.size) return toast('Pick at least one trader');
    const btn = document.getElementById('create'); btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const r = await api('/api/ix', { method: 'POST', body: { name: S.name || 'My index', traders: weights(), interval_min: S.interval } });
      S.selected.clear(); S.name = ''; S.preview = null; S.focus = null;
      location.hash = 'ix/' + r.id;
      setTimeout(() => depositModal(r.id, r.deposit, S.amount), 300);
    } catch (e) { toast(e.message); btn.disabled = false; btn.innerHTML = 'Create index ' + ARROW; }
  }

  /* ---------- deposit ---------- */
  function depositModal(id, addr, amount) {
    const url = `solana:${addr}?amount=${amount || 1}&label=FOMOINDEX`;
    modal(`<h3>Fund your index</h3>
      <p class="note">Send SOL to this address from any wallet. Scan with your phone's wallet or pay directly from the wallet you signed in with.</p>
      <div class="qr" id="qr"></div>
      <div class="addr" id="addr" title="Click to copy">${esc(addr)}</div>
      <div class="field"><label>Amount</label><input class="input" id="damt" type="number" min="0.05" step="0.05" value="${amount || 1}"></div>
      <button class="btn btn-ink btn-lg" id="pay">Send with wallet</button>
      <div class="mini-steps"><span><b>1</b>SOL lands in the index wallet</span><span><b>2</b>Next cycle buys the basket</span><span><b>3</b>It mirrors your traders from then on</span></div>
      <details><summary class="note" style="cursor:pointer">I sent it from another wallet</summary><div class="field" style="margin-top:10px"><label>Transaction signature</label><input class="input" id="sig" placeholder="5Kd…"><button class="btn sm" id="sigbtn" style="margin-top:8px;justify-self:start">Record deposit</button></div></details>`,
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
      const w3 = window.solanaWeb3; const conn = new w3.Connection(location.origin + '/api/rpc', 'confirmed');   // Solana's public RPC blocks web pages
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
    if (!S.wallet) { view.innerHTML = `<div class="app-h"><div><h1>My indexes</h1><p>Sign in with your wallet to see them.</p></div></div><div class="panel"><div class="empty"><b>Not signed in</b>Connect a wallet to see the indexes you have built.<br><button class="btn btn-ink" id="c2" style="margin-top:14px">Connect wallet</button></div></div>`; document.getElementById('c2').addEventListener('click', connect); return; }
    view.innerHTML = `<div class="app-h"><div><h1>My indexes</h1><p>Everything you have built, live.</p></div><a class="btn btn-ink" href="#build">New index ${ARROW}</a></div><div class="ix-grid" id="list"><div class="panel sk" style="height:140px"></div><div class="panel sk" style="height:140px"></div></div>`;
    try {
      const { indexes } = await api('/api/ix');
      document.getElementById('list').innerHTML = indexes.length ? indexes.map((ix) => { const dep = Number(ix.deposited_sol) || 0; const nav = Number(ix.nav_sol) || 0; const chg = dep ? ((nav + Number(ix.withdrawn_sol || 0)) / dep - 1) : 0; return `<a class="panel ix" href="#ix/${esc(ix.id)}">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h3>${esc(ix.name)}</h3><span class="pill ${esc(ix.status)}"><i></i>${esc(ix.status)}</span></div>
          <div class="navv">${nav ? sol(nav) : '—'}<small>${ix.nav_usd ? usd(ix.nav_usd, 0) : 'awaiting deposit'}</small></div>
          <div style="display:flex;justify-content:space-between;margin-top:10px;font-size:.82rem;color:var(--muted)"><span>${(ix.traders || []).length} traders · every ${every(ix.interval_min || 120)}</span><span class="${chg >= 0 ? 'up' : 'down'} mono">${dep ? (chg >= 0 ? '+' : '') + (chg * 100).toFixed(1) + '%' : ''}</span></div></a>`; }).join('')
        : `<div class="panel" style="grid-column:1/-1"><div class="empty"><b>No indexes yet</b>Pick a few traders from the leaderboard, set the pace, and fund it with SOL. Takes about two minutes.<br><a class="btn btn-ink" href="#build" style="margin-top:14px">Build your first index ${ARROW}</a></div></div>`;
    } catch (e) { document.getElementById('list').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; }
  }

  /* ---------- index detail ---------- */
  let refreshT;
  async function renderIndex(id) {
    clearInterval(refreshT);
    if (!S.wallet) return renderMine();
    if (!document.getElementById('ixroot')) view.innerHTML = `<div id="ixroot"><div class="app-h"><div><h1 class="sk">Loading index</h1></div></div></div>`;
    let d;
    try { d = await api('/api/ix/' + encodeURIComponent(id)); } catch (e) { view.innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
    const dep = d.deposited_sol || 0; const chg = dep ? ((d.nav_sol + (d.withdrawn_sol || 0)) / dep - 1) : null;
    const targetOf = (mint) => d.target.find((t) => t.mint === mint)?.weight || 0;
    const rows = [...d.holdings];
    for (const t of d.target) if (!rows.find((r) => r.mint === t.mint)) rows.push({ mint: t.mint, symbol: t.symbol, icon: t.icon, amount: 0, usd: 0, weight: 0 });
    rows.sort((a, b) => Math.max(b.weight, targetOf(b.mint)) - Math.max(a.weight, targetOf(a.mint)));
    const solTarget = Math.max(0, 1 - d.target.reduce((s2, t) => s2 + t.weight, 0));
    const compParts = d.nav_usd > 0 ? rows.filter((r) => r.weight > 0).map((r, i) => ({ s: r.symbol || short(r.mint), weight: r.weight, color: r.mint === SOL_MINT ? '#8b939d' : COLS[i % COLS.length] })) : [...d.target.map((t, i) => ({ s: t.symbol || short(t.mint), weight: t.weight, color: COLS[i % COLS.length] })), { s: 'SOL', weight: solTarget, color: '#8b939d' }];
    document.getElementById('ixroot').innerHTML = `
      <div class="app-h"><div><div class="k"><a href="#mine">← My indexes</a></div><h1 style="margin-top:6px">${esc(d.name)} <span class="pill ${esc(d.status)}" style="vertical-align:middle;margin-left:8px"><i></i>${esc(d.status)}</span></h1>
        <p>Mirrors ${d.traders.map((t) => '@' + esc(t.handle) + ' ' + pct(t.weight)).join(' · ')}</p></div>
        <div class="actions">${d.status === 'closed' ? '' : `<button class="btn" id="depBtn">Deposit</button><button class="btn" id="pauseBtn">${d.status === 'paused' ? 'Resume' : 'Pause'}</button><button class="btn danger" id="wdBtn">Withdraw all</button>`}</div></div>
      <div class="detail">
        <div style="display:grid;gap:16px">
          <div class="panel"><div class="panel-b">
            <div class="stat-row">
              <div class="stat"><b>${sol(d.nav_sol)}</b><small>Index value</small></div>
              <div class="stat"><b>${usd(d.nav_usd, 0)}</b><small>In USD</small></div>
              <div class="stat"><b class="${chg == null ? '' : chg >= 0 ? 'up' : 'down'}">${chg == null ? '—' : (chg >= 0 ? '+' : '') + (chg * 100).toFixed(1) + '%'}</b><small>Since deposit</small></div>
              <div class="stat"><b id="nextRb" style="font-size:${d.status === 'active' && dep ? '1.15rem' : '.9rem'}">${d.status !== 'active' ? d.status : !dep ? 'after deposit' : '…'}</b><small>Next rebalance</small></div>
            </div>
            <div class="meta-row"><span class="pill"><i></i>every ${every(d.interval_min || 120)}</span><span>Fee <b>${(d.fee_bps || 0) / 100}%</b> per trade</span><span><b>${sol(d.fees_paid_sol || 0, 4)}</b> paid in fees</span><span>Last cycle <b>${ago(d.last_rebalance)}</b></span></div>
            ${dep ? `<canvas class="chart" id="chart" width="800" height="200"></canvas>` : `
            <div class="next-steps"><div class="ns-head"><b>Waiting for your first deposit</b><p>The index wallet is ready. Here is what happens once SOL lands in it.</p></div>
              <ol><li><b>Send SOL</b><span>Any amount from 0.2 SOL, from any wallet, to the index wallet on the right.</span></li>
              <li><b>First cycle buys the basket</b><span>Within ${every(d.interval_min || 120)} the index swaps into what your traders hold, blended by weight.</span></li>
              <li><b>Then it mirrors</b><span>Every ${every(d.interval_min || 120)} it checks your traders and trades only what has drifted more than 2.5%.</span></li></ol>
              ${d.status === 'closed' ? '' : '<button class="btn btn-ink" id="depBtn2">Deposit SOL</button>'}</div>`}
          </div></div>
          <div class="panel">
            <div class="hold-head"><div><b style="font-weight:600">Holdings</b><p class="note">${d.nav_usd > 0 ? `${d.holdings.filter((r) => r.mint !== SOL_MINT && r.usd > 0.5).length} tokens plus SOL as cash` : 'Target basket, bought on the first cycle'}</p></div>
              <div class="comp"><svg viewBox="0 0 42 42">${donutSvg(compParts, null)}</svg><div class="legend">${compParts.slice(0, 6).map((l) => `<span><i style="background:${l.color}"></i>${esc(l.s)} ${pct(l.weight)}</span>`).join('')}</div></div></div>
            ${rows.length ? `<table class="tbl"><thead><tr><th>Token</th><th class="r">Now</th><th class="r">Target</th><th class="r">Value</th></tr></thead><tbody>
            ${rows.map((r) => `<tr><td><div class="tok"><i>${r.icon ? `<img src="${esc(r.icon)}" alt="">` : ''}</i><b>${esc(r.symbol || r.mint.slice(0, 4))}</b><small>${r.mint === SOL_MINT ? 'cash' : short(r.mint)}</small></div></td><td class="r">${pct(r.weight)}</td><td class="r" style="color:var(--muted)">${r.mint === SOL_MINT ? pct(solTarget) : pct(targetOf(r.mint))}</td><td class="r">${usd(r.usd)}</td></tr>`).join('')}
            </tbody></table>` : `<div class="empty">Waiting for the first deposit.</div>`}
            <div class="panel-b" style="border-top:1px solid var(--line)"><p class="note">Target is what your traders hold right now, blended by weight. The index trades toward it every ${every(d.interval_min || 120)} when a position is more than 2.5% off.</p></div>
          </div>
        </div>
        <div style="display:grid;gap:16px">
          <div class="panel"><div class="panel-h"><b>Traders</b></div><div class="panel-b">
            ${d.traders.map((t) => `<div class="trader-chip">${avatar(t)}<div><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}${t.rank ? ' · #' + t.rank : ''}</small></div><span class="w">${pct(t.weight)}</span></div>`).join('')}
          </div></div>
          <div class="panel"><div class="panel-h"><b>Index wallet</b></div><div class="panel-b">
            <div class="addr" id="addr2" title="Click to copy">${esc(d.deposit)}</div>
            <div class="kv" style="margin-top:10px"><span>Deposited</span><b>${sol(dep)}</b></div><div class="kv"><span>Withdrawn</span><b>${sol(d.withdrawn_sol || 0)}</b></div>
            <a class="note" href="https://solscan.io/account/${esc(d.deposit)}" target="_blank" rel="noopener" style="color:var(--accent-hi)">View on Solscan ↗</a>
          </div></div>
          <div class="panel"><div class="panel-h"><b>Activity</b></div><div class="panel-b">
            <div class="log">${[...d.trades.map((t) => ({ ts: t.ts, text: t.side === 'deposit' ? `Deposit ${sol(t.amount_sol)}` : t.side === 'fee' ? `Fee ${sol(t.amount_sol, 4)}` : `${t.side === 'buy' ? 'Bought' : 'Sold'} ${esc(t.symbol || short(t.mint))} for ${sol(t.amount_sol)}${t.note === 'withdraw' ? ' (withdraw)' : ''}`, sig: t.sig })), ...d.events.filter((e) => e.level !== 'info' || /created|withdrew|paused|active/.test(e.message)).map((e) => ({ ts: e.ts, text: esc(e.message) }))].sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 30).map((x) => `<div><time>${ago(x.ts)}</time><span>${x.text}</span>${x.sig ? `<a href="https://solscan.io/tx/${esc(x.sig)}" target="_blank" rel="noopener">tx ↗</a>` : '<span></span>'}</div>`).join('') || '<div class="note">Nothing yet.</div>'}</div>
          </div></div>
        </div>
      </div>`;
    chart(document.getElementById('chart'), d.history);
    if (d.status === 'active' && dep) countdown(document.getElementById('nextRb'), (d.last_rebalance ? new Date(d.last_rebalance).getTime() : Date.now()) + (d.interval_min || 120) * 60e3);
    document.getElementById('depBtn2')?.addEventListener('click', () => depositModal(d.id, d.deposit, 1));
    document.getElementById('addr2').addEventListener('click', async () => { try { await navigator.clipboard.writeText(d.deposit); toast('Address copied'); } catch (e) { /* ignore */ } });
    document.getElementById('depBtn')?.addEventListener('click', () => depositModal(d.id, d.deposit, 1));
    document.getElementById('pauseBtn')?.addEventListener('click', async () => { try { await api(`/api/ix/${d.id}/status`, { method: 'POST', body: { status: d.status === 'paused' ? 'active' : 'paused' } }); toast(d.status === 'paused' ? 'Index resumed' : 'Index paused'); renderIndex(id); } catch (e) { toast(e.message); } });
    document.getElementById('wdBtn')?.addEventListener('click', () => modal(`<h3>Withdraw everything?</h3><p class="note">Every token is sold to SOL through Jupiter and the SOL is sent to ${short(S.wallet)}. This closes the index. It takes a minute.</p><button class="btn danger btn-lg" id="wd2">Sell all and withdraw</button><button class="btn" id="wd3">Keep it</button>`, (el) => { el.querySelector('#wd3').addEventListener('click', closeModal); el.querySelector('#wd2').addEventListener('click', async () => { el.querySelector('#wd2').disabled = true; el.querySelector('#wd2').textContent = 'Selling and sending…'; try { const r = await api(`/api/ix/${d.id}/withdraw`, { method: 'POST' }); toast(`${r.sol?.toFixed(4) || 0} SOL sent to your wallet`); closeModal(); renderIndex(id); } catch (e) { toast(e.message); closeModal(); } }); }));
    refreshT = setInterval(() => { if (location.hash === '#ix/' + id) renderIndex(id); }, 60000);
  }
  function chart(c, hist) {
    if (!c) return; const ctx = c.getContext('2d'); const W = c.width, H = c.height;
    ctx.clearRect(0, 0, W, H);
    const pts = (hist || []).map((h) => Number(h.nav_sol) || 0).filter((v) => v >= 0);
    if (pts.length < 2) { ctx.fillStyle = 'rgba(203,208,235,.4)'; ctx.font = '13px Geist Mono, monospace'; ctx.fillText(pts.length ? 'The chart fills in as the index rebalances.' : 'No data yet.', 12, 30); return; }
    const min = Math.min(...pts) * 0.98, max = Math.max(...pts) * 1.02 || 1;
    const x = (i) => 10 + (i / (pts.length - 1)) * (W - 20), y = (v) => H - 14 - ((v - min) / (max - min || 1)) * (H - 34);
    const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, 'rgba(96,106,247,.45)'); g.addColorStop(1, 'rgba(96,106,247,0)');
    ctx.beginPath(); ctx.moveTo(x(0), H); pts.forEach((v, i) => ctx.lineTo(x(i), y(v))); ctx.lineTo(x(pts.length - 1), H); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); pts.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)))); ctx.strokeStyle = pts[pts.length - 1] >= pts[0] ? '#35d07f' : '#ff6b5e'; ctx.lineWidth = 2.2; ctx.lineJoin = 'round'; ctx.stroke();
    ctx.fillStyle = 'rgba(203,208,235,.5)'; ctx.font = '11px Geist Mono, monospace'; ctx.fillText(pts[pts.length - 1].toFixed(3) + ' SOL', W - 90, y(pts[pts.length - 1]) - 8);
  }

  restore().then(route);
})();
