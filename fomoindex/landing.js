(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

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
        ? `At <b>${every(cur)}</b> the index tracks your traders almost tick for tick and pays <b>${l.bps / 100}%</b> on each swap for it. Only worth it if your traders move fast and you want to be in on the first candle.`
        : cur <= 60
          ? `At <b>${every(cur)}</b> you follow intraday moves closely while the 2.5% threshold filters out noise. <b>${l.bps / 100}%</b> per swap, charged only when the index actually trades.`
          : `At <b>${every(cur)}</b> the index catches real position changes without reacting to every wiggle. <b>${l.bps / 100}%</b> per swap, only when it trades. Quiet rounds cost nothing.`;
      [...pick.querySelectorAll('button'), ...ladder.querySelectorAll('.lstep')].forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.m; paint(); }));
    };
    paint();
  }

  /* traders, live from the api */
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
})();
