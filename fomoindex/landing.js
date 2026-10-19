(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* nav: compact on scroll, burger on phones */
  const nav = $('#nav'); const burger = $('#burger'); const menu = $('#navMenu');
  const onScroll = () => nav.classList.toggle('scrolled', scrollY > 24);
  addEventListener('scroll', onScroll, { passive: true }); onScroll();
  burger.addEventListener('click', () => { const open = nav.classList.toggle('open'); burger.setAttribute('aria-expanded', open); });
  menu.querySelectorAll('a').forEach((a) => a.addEventListener('click', () => nav.classList.remove('open')));

  /* reveal on scroll */
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
  document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

  /* hero: live-looking countdown to the next 2 h cycle */
  const timer = $('#heroTimer');
  if (timer) { const tick = () => { const now = Date.now(); const period = 2 * 3600e3; const left = period - (now % period); const h = Math.floor(left / 3600e3), m = Math.floor((left % 3600e3) / 60e3), s = Math.floor((left % 60e3) / 1e3); timer.textContent = [h, m, s].map((n) => String(n).padStart(2, '0')).join(':'); }; tick(); setInterval(tick, 1000); }

  /* how-it-works vignette: a deterministic QR-looking pattern */
  const qr = $('#vigQr');
  if (qr) { let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }; const n = 13; let cells = ''; for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) { const finder = (x < 4 && y < 4) || (x > n - 5 && y < 4) || (x < 4 && y > n - 5); const ring = finder && ((x % (n - 1) === 0 || x === 3 || x === n - 4) || (y === 0 || y === 3 || y === n - 4 || y === n - 1)); const core = finder && !ring && (x === 1 || x === 2 || x === n - 3 || x === n - 2) && (y === 1 || y === 2 || y === n - 3 || y === n - 2); const on = finder ? (ring || core) && !((x === 1 || x === 2 || x === n - 2 || x === n - 3) && (y === 0 || y === 3 || y === n - 4 || y === n - 1)) : rnd() > .55; if (on) cells += `<i style="grid-area:${y + 1}/${x + 1}"></i>`; } qr.innerHTML = cells; }

  /* tempo picker */
  const LADDER = [{ m: 1, bps: 250, for: 'Scalpers' }, { m: 5, bps: 200, for: 'Fast movers' }, { m: 15, bps: 150, for: 'Active traders' }, { m: 30, bps: 100, for: 'Active traders' }, { m: 60, bps: 75, for: 'Day to day' }, { m: 120, bps: 50, for: 'Most people' }, { m: 360, bps: 40, for: 'Patient holders' }, { m: 1440, bps: 30, for: 'Set and forget' }];
  const every = (m) => m < 60 ? `${m} min` : m < 1440 ? `${m / 60} h` : '24 h';
  const pick = $('#tempoPick'); const ladder = $('#ladder');
  if (pick) {
    let cur = 120;
    const paint = () => {
      pick.innerHTML = LADDER.map((l) => `<button class="${l.m === cur ? 'on' : ''}" data-m="${l.m}"><b>${every(l.m)}</b><small>${l.bps / 100}%</small></button>`).join('');
      ladder.innerHTML = LADDER.map((l) => `<div class="lstep ${l.m === cur ? 'on' : ''}" data-m="${l.m}"><i style="height:${(l.bps / 250) * 100}%"></i><b>${l.bps / 100}%</b><small>${every(l.m)}</small></div>`).join('');
      const l = LADDER.find((x) => x.m === cur);
      $('#tEvery').textContent = 'every ' + every(cur); $('#tFee').textContent = l.bps / 100 + '%'; $('#tChecks').textContent = Math.round(1440 / cur).toLocaleString('en-US'); $('#tFor').textContent = l.for;
      $('#tNote').innerHTML = cur <= 5
        ? `At <b>${every(cur)}</b> the index tracks your traders almost tick for tick, and pays <b>${l.bps / 100}%</b> on each swap for it. Only worth it if your traders move fast and you want to be in on the first candle.`
        : cur <= 60
          ? `At <b>${every(cur)}</b> you follow intraday moves closely while the 2.5% threshold filters out noise. <b>${l.bps / 100}%</b> per swap, charged only when the index actually trades.`
          : `At <b>${every(cur)}</b> the index catches real position changes without reacting to every wiggle. <b>${l.bps / 100}%</b> per swap, only when it trades. Quiet rounds cost nothing.`;
      pick.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.m; paint(); }));
      ladder.querySelectorAll('.lstep').forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.m; paint(); }));
    };
    paint();
  }

  /* traders preview, live from the api */
  (async () => {
    const el = $('#tradersPreview'); if (!el) return;
    const fmt = (n) => (n < 0 ? '-' : '+') + '$' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
    try {
      const r = await fetch('/api/traders'); const j = await r.json();
      const list = (j.traders || []).filter((t) => t.has_wallet).slice(0, 8);
      if (!list.length) throw new Error('none');
      el.innerHTML = list.map((t) => `<a class="tcard" href="/app#build">
        <span class="rank">#${t.rank || '–'}</span>
        <div class="top"><div class="ava">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : esc((t.name || t.handle).slice(0, 1).toUpperCase())}</div><div><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}</small></div></div>
        <div class="pnl ${Number(t.pnl_7d) < 0 ? 'neg' : 'pos'}">${t.pnl_7d != null ? fmt(Number(t.pnl_7d)) : '—'}<small>7 day pnl</small></div>
        <div class="holds">${(t.top || []).map((x) => `<span>${esc(x.symbol)} ${Math.round(x.weight * 100)}%</span>`).join('') || '<span>all in SOL right now</span>'}</div></a>`).join('');
    } catch (e) {
      el.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
        <div class="ico"><svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 11-2.6-6.4"/><path d="M21 3v6h-6"/></svg></div>
        <b>The leaderboard is syncing</b>
        <p>Traders appear here as soon as their wallets are confirmed on fomo. Open the app to see the live list and build from it.</p>
        <a class="btn ghost sm" href="/app">Open the app →</a></div>`;
    }
  })();

  /* footer status */
  (async () => {
    const el = $('#status'); if (!el) return;
    try { const r = await fetch('/api/health'); const j = await r.json(); el.className = 'status ' + (j.ok ? 'ok' : 'warn'); el.querySelector('span').textContent = j.ok ? `All systems live${j.sol_usd ? ' · SOL $' + Math.round(j.sol_usd) : ''}` : 'Partial outage, trading paused'; }
    catch (e) { el.className = 'status warn'; el.querySelector('span').textContent = 'Status unavailable'; }
  })();
})();
