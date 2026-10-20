(() => {
  'use strict';

  /* the star field: two seamless tiles drawn at the screen's pixel density, so the stars stay sharp */
  (() => {
    const el = document.getElementById('stars'); if (!el) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const tile = (size, count, bright) => {
      const c = document.createElement('canvas'); c.width = c.height = size * dpr;
      const g = c.getContext('2d'); if (!g) return null; g.scale(dpr, dpr);
      for (let i = 0; i < count; i++) {
        const d = Math.random(), r = d < .82 ? .5 : d < .97 ? .85 : 1.35, m = r + 1;
        g.globalAlpha = (.10 + d * .55) * bright; g.fillStyle = d > .97 ? '#d9e0ff' : '#ffffff';
        g.beginPath(); g.arc(m + Math.random() * (size - 2 * m), m + Math.random() * (size - 2 * m), r, 0, 6.283); g.fill();
      }
      return c.toDataURL('image/png');
    };
    const a = tile(560, 520, .9), b = tile(900, 420, .6); if (!a) return;
    el.style.backgroundImage = `url(${a}),url(${b})`; el.style.backgroundSize = '560px 560px,900px 900px';
  })();
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* tempo picker */
  const LADDER = [{ m: 1, bps: 100, for: 'Scalpers' }, { m: 5, bps: 80, for: 'Fast movers' }, { m: 15, bps: 60, for: 'Active traders' }, { m: 30, bps: 50, for: 'Active traders' }, { m: 60, bps: 40, for: 'Day to day' }, { m: 120, bps: 30, for: 'Most people' }, { m: 360, bps: 25, for: 'Patient holders' }, { m: 1440, bps: 20, for: 'Set and forget' }];
  const every = (m) => m < 60 ? `${m} min` : m < 1440 ? `${m / 60} h` : '24 h';
  const pick = $('#tempoPick'); const ladder = $('#ladder');
  if (pick) {
    let cur = 120;
    const paint = () => {
      pick.innerHTML = LADDER.map((l) => `<button class="${l.m === cur ? 'on' : ''}" data-m="${l.m}"><b>${every(l.m)}</b><small>${l.bps / 100}%</small></button>`).join('');
      ladder.innerHTML = LADDER.map((l) => `<div class="lstep ${l.m === cur ? 'on' : ''}" data-m="${l.m}"><i style="height:${(l.bps / 100) * 100}%"></i><b>${l.bps / 100}%</b><small>${every(l.m)}</small></div>`).join('');
      const l = LADDER.find((x) => x.m === cur);
      $('#tEvery').textContent = 'every ' + every(cur); $('#tFee').textContent = l.bps / 100 + '%'; $('#tChecks').textContent = Math.round(1440 / cur).toLocaleString('en-US'); $('#tFor').textContent = l.for;
      $('#tNote').innerHTML = cur <= 5
        ? `At <b>${every(cur)}</b> the index tracks your traders almost tick for tick and pays <b>${l.bps / 100}%</b> on each swap for it. Only worth it if your traders move fast and you want to be in on the first candle.`
        : cur <= 60
          ? `At <b>${every(cur)}</b> you follow intraday moves closely while the 2.5% threshold filters out noise. <b>${l.bps / 100}%</b> per swap, charged only when the index actually trades.`
          : `At <b>${every(cur)}</b> the index catches real position changes without reacting to every wiggle. <b>${l.bps / 100}%</b> per swap, only when it trades. Quiet rounds cost nothing.`;
      [...pick.querySelectorAll('button'), ...ladder.querySelectorAll('.lstep')].forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.m; paint(); }));
    };
    paint();
  }

  /* the leaderboard and weights cards: real traders from the api; until the board has synced they keep their placeholders */
  (async () => {
    const board = $('#vizBoard'); if (!board) return;
    const fmt = (n) => (n < 0 ? '-' : '+') + '$' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
    try {
      const j = await (await fetch('/api/traders')).json();
      const list = (j.traders || []).filter((t) => t.has_wallet).slice(0, 4);
      if (!list.length) return;
      const medal = ['g', 's', 'br', ''];
      board.innerHTML = list.map((t, i) => `<div class="row"><span class="medal ${medal[i]}">${t.rank || i + 1}</span>
        <i class="ava">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : ''}</i>
        <div class="who"><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}</small></div>
        <em class="${Number(t.pnl_7d) < 0 ? 'neg' : ''}">${t.pnl_7d != null ? fmt(Number(t.pnl_7d)) : ''}</em></div>`).join('');
      const names = [...$('#vizWeights').querySelectorAll('.wt span')];
      list.slice(0, 3).forEach((t, i) => { if (names[i]) names[i].textContent = t.name || '@' + t.handle; });
    } catch (e) { /* placeholders stay */ }
  })();

  /* traders table, live from the api */
  (async () => {
    const tb = $('#tradersTbl tbody'); const meta = $('#tradersMeta'); if (!tb) return;
    const fmt = (n) => (n < 0 ? '-' : '+') + '$' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
    try {
      const r = await fetch('/api/traders'); const j = await r.json();
      const list = (j.traders || []).filter((t) => t.has_wallet).slice(0, 8);
      if (!list.length) throw new Error('none');
      meta.textContent = `${(j.traders || []).length} on the board`;
      tb.innerHTML = list.map((t, i) => `<tr class="row" onclick="location.href='/app#build/${encodeURIComponent(t.handle)}'">
        <td class="rk ${i < 3 ? 'p' : ''}">${i < 3 ? `<span>${t.rank || i + 1}</span>` : (t.rank || i + 1)}</td>
        <td><div class="tn"><div class="ava">${t.avatar ? `<img src="${esc(t.avatar)}" alt="">` : esc((t.name || t.handle).slice(0, 2).toUpperCase())}</div><div><b>${esc(t.name || t.handle)}</b><small>@${esc(t.handle)}</small></div></div></td>
        <td class="hide-s"><div class="chips">${(t.top || []).slice(0, 3).map((x) => `<span>${esc(x.symbol)} ${Math.round(x.weight * 100)}%</span>`).join('') || '<span>all in SOL</span>'}</div></td>
        <td class="r ${Number(t.pnl_7d) < 0 ? 'down' : 'up'}">${t.pnl_7d != null ? fmt(Number(t.pnl_7d)) : '—'}</td></tr>`).join('');
    } catch (e) {
      meta.textContent = 'syncing';
      tb.innerHTML = `<tr><td colspan="4"><div class="empty"><b>The leaderboard is syncing</b>Traders appear here as soon as their wallets are confirmed on fomo. Open the app to see the live list.</div></td></tr>`;
    }
  })();

  /* footer status */
  (async () => {
    const el = $('#status'); if (!el) return;
    try { const r = await fetch('/api/health'); const j = await r.json(); el.className = 'status ' + (j.ok ? 'ok' : 'warn'); el.querySelector('span').textContent = j.ok ? `all systems live${j.sol_usd ? ' · SOL $' + Math.round(j.sol_usd) : ''}` : 'setting up · trading not live yet'; }
    catch (e) { el.className = 'status warn'; el.querySelector('span').textContent = 'status unavailable'; }
  })();

  /* the hero card: three real fomo traders join an example index, the weights fill, the value line draws. On a loop. */
  (async () => {
    const card = $('#heroCard'); if (!card) return;
    const W = [0.45, 0.35, 0.2];
    const faces = [...card.querySelectorAll('.hc-faces i')], rows = [...card.querySelectorAll('.hc-r')];
    const line = $('.line', card), area = $('.area', card), dot = $('.dot', card), n = $('#hcN');
    rows.forEach((r, i) => r.style.setProperty('--w', W[i]));
    try {
      const j = await (await fetch('/api/traders?limit=30')).json();
      const pick = (j.traders || []).filter((t) => t.has_wallet && t.avatar).slice(0, 3);
      pick.forEach((t, i) => {
        faces[i].innerHTML = `<img src="${esc(t.avatar)}" alt="">`;
        rows[i].querySelector('i').innerHTML = `<img src="${esc(t.avatar)}" alt="">`;
        rows[i].querySelector('b').textContent = '@' + t.handle;
      });
    } catch (e) { /* the card still plays with blank faces */ }
    // a fresh example line every round: drifts up with a few dips, never a real trader's numbers
    const drawLine = () => {
      const pts = []; let y = 80;
      for (let i = 0; i <= 24; i++) { y = Math.max(10, Math.min(84, y - (Math.random() * 8 - 2.3))); pts.push([i * 12.5, y]); }
      const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
      line.setAttribute('d', d); area.setAttribute('d', d + ' L300 92 L0 92 Z');
      const [lx, ly] = pts[pts.length - 1]; dot.setAttribute('cx', lx); dot.setAttribute('cy', ly);
    };
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { drawLine(); card.dataset.n = 3; card.classList.add('fill', 'draw'); n.textContent = 3; return; }
    for (;;) {
      card.classList.remove('fill', 'draw'); card.dataset.n = 0; n.textContent = 0; drawLine();   // reset while faded out
      await wait(450); card.classList.remove('out');
      await wait(500);
      for (let i = 1; i <= 3; i++) { card.dataset.n = i; n.textContent = i; await wait(650); }
      card.classList.add('fill'); await wait(900);
      card.classList.add('draw'); await wait(4200);
      card.classList.add('out'); await wait(600);
    }
  })();
})();
