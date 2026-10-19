(() => {
  'use strict';

  /* ---------- where the backends plug in ----------
     spendApi:       the spend.family checkout engine (quote + pay). null = checkout is shown, payment is "coming soon".
     fantasyUrl:     the fomofantasy app. null = the page explains the game and says when it opens.
     leaderboardApi: a server route that proxies fomo's leaderboard with a token (see api/leaderboard.mjs). */
  const CONFIG = { spendApi: null, fantasyUrl: null, leaderboardApi: 'api/leaderboard' };
  const FOMO = 'https://fomo.family';

  const view = document.getElementById('view');
  const flood = document.getElementById('flood');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem('fomohub:' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('fomohub:' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const fmtUsd = (n, d = 2) => (n < 0 ? '-' : '') + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmtBig = (n) => n >= 1e9 ? (n / 1e9).toFixed(2) + 'B' : n >= 1e6 ? (n / 1e6).toFixed(2) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : String(Math.round(n));

  /* ---------- the six things around the mascot ---------- */
  const NODES = [
    { key: 'spend', label: 'FOMO<b>SPEND</b>', title: 'FOMOSPEND', angle: 220 },
    { key: 'leaderboard', label: 'LEADER<b>BOARD</b>', title: 'Leaderboard', angle: 180 },
    { key: 'fantasy', label: 'FOMO<b>FANTASY</b>', title: 'FOMOFANTASY', angle: 140 },
    { key: 'predict', label: 'FOMO<b>PREDICT</b>', title: 'FOMOPREDICT', angle: 320 },
    { key: 'quests', label: 'FOMO<b>QUESTS</b>', title: 'FOMOQUESTS', angle: 0 },
    { key: 'radar', label: 'FOMO<b>RADAR</b>', title: 'FOMORADAR', angle: 40 },
  ];
  const ICON_SIZE = { spend: 1.06, leaderboard: 1.0, fantasy: 0.96, predict: 0.92, quests: 1.04, radar: 1.0 };

  const brand = () => `<a class="brand" href="#/" aria-label="FOMOHUB home"><img src="assets/fomo-mark.svg" alt=""><span>FOMOHUB<small>everything fomo</small></span></a>`;
  const page = (key, title, kicker, lead, body, status = '') => `
    <section class="page" data-page="${key}">
      ${brand()}
      <div class="head">
        <img src="assets/icons/${key}.png" alt="">
        <div><div class="kicker">${kicker} ${status}</div><h1>${title}</h1><p class="lead">${lead}</p></div>
      </div>
      <div class="wrap">${body}</div>
    </section>`;
  const soon = (t = 'coming soon') => `<span class="status"><i></i>${t}</span>`;
  const live = (t = 'live') => `<span class="status live"><i></i>${t}</span>`;

  /* ---------- routes ---------- */
  const ROUTES = {
    '/': { title: 'FOMOHUB', render: () => `
      <section class="hub">
        ${brand()}
        <div class="stage" id="stage">
          <div class="mascot" id="mascot" aria-label="fomo">
            <div class="tilt" id="tilt">
              <img class="body" src="assets/mascot/body.png" alt="the fomo mark" draggable="false">
              <div class="eyes" id="eyes"></div>
            </div>
          </div>
          ${NODES.map((n) => `
            <a class="node" href="#/${n.key}" data-key="${n.key}" aria-label="${n.title}" style="--s:${ICON_SIZE[n.key] || 1}">
              <div class="bob" style="animation-delay:${-Math.random() * 6}s"><div class="art"><img src="assets/icons/${n.key}.png" alt="" draggable="false"></div></div>
              <span class="tag">${n.label}</span>
            </a>`).join('')}
          <div class="tagline" id="tagline">everything fomo, in one place</div>
          <a class="pill" id="pill" href="#/about">What is FOMOHUB <span>&rarr;</span></a>
        </div>
      </section>` },

    '/about': { title: 'About', render: () => `
      <section class="page" data-page="about">
        ${brand()}
        <div class="head"><img src="assets/fomo-mark.svg" alt="" style="width:110px;height:auto"><div><div class="kicker">the hub</div><h1>What is FOMOHUB</h1>
        <p class="lead">A place for fomo users to hang out between trades. Everything that is fomo but is not the trading itself: spending, competing, predicting, collecting.</p></div></div>
        <div class="wrap">
          <div class="cols">
            ${[['FOMOSPEND', 'Turn crypto into balance at real shops, with the spend.family engine.'],
               ['Leaderboard', 'The fomo leaderboard, straight from fomo.family.'],
               ['FOMOFANTASY', 'Draft a squad of fomo traders. Their real PnL is your score.'],
               ['FOMOPREDICT', 'Call SOL higher or lower in sixty seconds. Keep the streak alive.'],
               ['FOMOQUESTS', 'Daily quests, points and a level. Small things to do every day.'],
               ['FOMORADAR', 'What the degens are aping right now, with one tap into fomo.']]
              .map(([t, d]) => `<div class="card"><h2>${t}</h2><p>${d}</p></div>`).join('')}
          </div>
          <div class="card"><h2>The mark</h2><p>The two eyes in the middle are the official fomo mark, rendered in 3D and path traced. The whole mark leans toward your pointer, so wherever you go on the page, fomo is looking your way.</p>
          <p>FOMOHUB is a community project and is not affiliated with FOMO Labs Inc.</p></div>
        </div>
      </section>` },

    '/spend': { title: 'FOMOSPEND', render: () => page('spend', 'FOMOSPEND', 'spend crypto at real shops',
      'Top up your balance at Uber Eats, Nike, Netflix and hundreds of other shops, paid from your Solana wallet. Your wallet pays the supplier directly. No account, nothing held for you.',
      `<div class="card">
        <div class="n">01 &nbsp;PICK A SHOP</div>
        <div class="shops" id="shops">${SHOPS.map((s) => `<button class="shop" type="button" data-shop="${s.id}"><b>${s.name}</b><small>${s.cat}</small></button>`).join('')}</div>
      </div>
      <div class="card">
        <div class="n">02 &nbsp;PICK AN AMOUNT</div>
        <div class="amounts" id="amounts">${[10, 25, 50, 100, 250].map((a) => `<button type="button" data-amt="${a}">$${a}</button>`).join('')}</div>
      </div>
      <div class="card">
        <div class="n">03 &nbsp;PAY FROM YOUR WALLET</div>
        <div id="quote">
          <div class="quote"><span>Shop</span><b id="qShop">&mdash;</b></div>
          <div class="quote"><span>Balance you get</span><b id="qAmt">&mdash;</b></div>
          <div class="quote"><span>You pay</span><b id="qPay">&mdash;</b></div>
        </div>
        <div class="actions">
          <button class="btn accent" id="payBtn" type="button" disabled>Pay with SOL</button>
          <button class="btn ghost" id="payUsdc" type="button" disabled>Pay with USDC</button>
          <a class="btn ghost" href="https://spend.family" target="_blank" rel="noopener">Open spend.family &rarr;</a>
        </div>
        <p class="note" id="spendNote" style="margin-top:14px">${CONFIG.spendApi ? 'Live quotes from the spend engine.' : 'The checkout runs on the spend.family engine. The payment step connects when the engine is wired to this hub; until then you can pay on spend.family.'}</p>
      </div>`, CONFIG.spendApi ? live() : soon('engine pending')) },

    '/leaderboard': { title: 'Leaderboard', render: () => page('leaderboard', 'Leaderboard', 'become a legend',
      'The fomo leaderboard: the traders with the biggest PnL on fomo, by day, week, month and all time.',
      `<div class="card">
        <div class="actions" style="margin:0 0 10px;justify-content:space-between">
          <div class="tabs" id="lbTabs">${[['24h', '24h'], ['7d', '7 days'], ['30d', '30 days'], ['all-time', 'all time']].map(([k, t], i) => `<button type="button" data-range="${k}" class="${i === 0 ? 'on' : ''}">${t}</button>`).join('')}</div>
          <a class="btn ghost" href="${FOMO}/leaderboard" target="_blank" rel="noopener">Open on fomo &rarr;</a>
        </div>
        <div class="rows" id="lbRows">${skeleton(6)}</div>
        <p class="note" id="lbNote" style="margin-top:14px"></p>
      </div>`) },

    '/fantasy': { title: 'FOMOFANTASY', render: () => page('fantasy', 'FOMOFANTASY', 'fantasy league for traders',
      'Draft a squad of fomo traders. Their real trading results are your points. Weekly leagues, one winner, bragging rights for a week.',
      `<div class="cols">
        <div class="card"><div class="n">01</div><h2>Draft</h2><p>Pick five traders from the fomo leaderboard under a salary cap. The hotter the trader, the more they cost.</p></div>
        <div class="card"><div class="n">02</div><h2>Lock</h2><p>Squads lock when the week starts. From then on their PnL on fomo is your score, live.</p></div>
        <div class="card"><div class="n">03</div><h2>Climb</h2><p>A league table for every week and a season table on top. Top of the season gets the FOMOFANTASY badge.</p></div>
      </div>
      <div class="card">
        <h2>Season one</h2>
        <p>The game engine comes from our fantasy project and is being connected to the hub. When it is in, the draft opens here.</p>
        <div class="actions">${CONFIG.fantasyUrl ? `<a class="btn accent" href="${esc(CONFIG.fantasyUrl)}">Open the draft &rarr;</a>` : `<button class="btn" type="button" disabled>Draft opens soon</button>`}<a class="btn ghost" href="${FOMO}/leaderboard" target="_blank" rel="noopener">Scout the leaderboard &rarr;</a></div>
      </div>`, CONFIG.fantasyUrl ? live() : soon('season one soon')) },

    '/predict': { title: 'FOMOPREDICT', render: () => page('predict', 'FOMOPREDICT', 'higher or lower',
      'Where is SOL in sixty seconds? Make the call, hold your breath, keep the streak alive. No money, only pride.',
      `<div class="card">
        <div class="kicker">SOL / USD <span id="pSrc" class="status live"><i></i>live</span></div>
        <div class="price" id="price">&mdash;<small id="priceSub"></small></div>
        <div class="calls"><button class="call up" id="callUp" type="button">&uarr; Higher</button><button class="call down" id="callDown" type="button">&darr; Lower</button></div>
        <div class="meter"><i id="meter"></i></div>
        <div class="verdict" id="verdict">Make your call.</div>
        <div class="stats">
          <div class="stat"><b id="sStreak">0</b><small>streak</small></div>
          <div class="stat"><b id="sBest">0</b><small>best</small></div>
          <div class="stat"><b id="sRate">&ndash;</b><small>hit rate</small></div>
        </div>
      </div>
      <div class="card"><h2>How it scores</h2><p>The price is the SOL spot price. A call is right when the price sixty seconds later is on your side of the price at the moment you called. A tie counts for nobody. Streaks live in your browser.</p></div>`) },

    '/quests': { title: 'FOMOQUESTS', render: () => page('quests', 'FOMOQUESTS', 'daily quests',
      'Small things to do every day. Each one is worth points, points make levels, and the quests reset at midnight.',
      `<div class="card">
        <div class="xp"><div class="lvl" id="lvl">&mdash;</div><div class="bar"><i id="xpBar"></i></div><div class="pts" id="xpPts"></div></div>
      </div>
      <div class="card"><div class="rows" id="questRows"></div></div>
      <div class="card"><h2>Levels</h2><p>${LEVELS.map((l) => `<b>${l.name}</b> from ${l.at} points`).join(' &middot; ')}</p></div>`) },

    '/radar': { title: 'FOMORADAR', render: () => page('radar', 'FOMORADAR', 'what the degens are aping',
      'The tokens getting the most attention on Solana right now. Tap one to open it on fomo.',
      `<div class="card">
        <div class="kicker">top boosted on solana <span class="status live" id="rSrc"><i></i>live</span></div>
        <div id="radarRows">${skeleton(8)}</div>
        <p class="note" id="radarNote" style="margin-top:14px"></p>
      </div>
      <div class="card"><h2>Not advice</h2><p>Attention is not a signal. These are the tokens people are paying to promote on DexScreener, which is exactly what makes them loud. Do your own research, and trade on fomo if you must.</p></div>`) },
  };

  function skeleton(n) {
    return Array.from({ length: n }, (_, i) => `<div class="row skel"><div class="rank">${i + 1}</div><div class="ava"></div><div class="who"><b>&nbsp;</b><small>&nbsp;</small></div><div class="pnl">&nbsp;</div></div>`).join('');
  }

  const SHOPS = [
    { id: 'ubereats', name: 'Uber Eats', cat: 'food' }, { id: 'nike', name: 'Nike', cat: 'fashion' }, { id: 'netflix', name: 'Netflix', cat: 'streaming' },
    { id: 'amazon', name: 'Amazon', cat: 'shopping' }, { id: 'spotify', name: 'Spotify', cat: 'music' }, { id: 'steam', name: 'Steam', cat: 'gaming' },
    { id: 'airbnb', name: 'Airbnb', cat: 'travel' }, { id: 'doordash', name: 'DoorDash', cat: 'food' }, { id: 'apple', name: 'Apple', cat: 'tech' },
    { id: 'playstation', name: 'PlayStation', cat: 'gaming' }, { id: 'starbucks', name: 'Starbucks', cat: 'coffee' }, { id: 'uber', name: 'Uber', cat: 'rides' },
  ];
  const LEVELS = [{ name: 'Paper hands', at: 0 }, { name: 'Degen', at: 60 }, { name: 'Diamond hands', at: 160 }, { name: 'Legend', at: 320 }];
  const QUESTS = [
    { id: 'leaderboard', t: 'Check the leaderboard', d: 'See who is printing today.', xp: 10, auto: true },
    { id: 'predict', t: 'Make a prediction', d: 'One call on FOMOPREDICT.', xp: 15, auto: true },
    { id: 'radar', t: 'Scan the radar', d: 'Open FOMORADAR once.', xp: 10, auto: true },
    { id: 'fomo', t: 'Open fomo', d: 'Visit fomo.family from the hub.', xp: 10, href: FOMO },
    { id: 'share', t: 'Share FOMOHUB', d: 'Copy the link and send it to a friend.', xp: 20, copy: true },
    { id: 'streak3', t: 'Hit a streak of 3', d: 'Three right calls in a row on FOMOPREDICT.', xp: 40, auto: true },
    { id: 'spend', t: 'Spend a gift card', d: 'Buy balance at a shop with FOMOSPEND.', xp: 50, auto: true, locked: !CONFIG.spendApi },
  ];

  /* ---------- the mascot: pupils follow the pointer ---------- */
  const M = window.FOMO_MASCOT || { w: 1600, h: 1100, pupils: [], hull: [] };
  const ptr = { x: innerWidth / 2, y: innerHeight * 0.4, last: 0, inside: false };
  addEventListener('pointermove', (e) => { ptr.x = e.clientX; ptr.y = e.clientY; ptr.last = performance.now(); ptr.inside = true; }, { passive: true });
  addEventListener('touchstart', (e) => { const t = e.touches[0]; if (t) { ptr.x = t.clientX; ptr.y = t.clientY; ptr.last = performance.now(); ptr.inside = true; } }, { passive: true });
  document.addEventListener('pointerleave', () => { ptr.inside = false; });

  let mascot = null;
  function setupMascot() {
    const el = document.getElementById('mascot');
    if (!el) { mascot = null; return; }
    el.style.setProperty('--ar', (M.w / M.h).toFixed(4));
    const eyes = document.getElementById('eyes');
    eyes.innerHTML = M.pupils.map((p, i) => `<img class="pupil" src="assets/mascot/pupil_${i ? 'r' : 'l'}.png" alt="" draggable="false"
      style="left:${(p.crop[0] * 100).toFixed(3)}%;top:${(p.crop[1] * 100).toFixed(3)}%;width:${(p.crop[2] * 100).toFixed(3)}%">`).join('');
    mascot = { el, tilt: document.getElementById('tilt'),
      pupils: [...eyes.querySelectorAll('.pupil')].map((img, i) => ({ img, c: M.pupils[i].center, x: 0, y: 0, s: 1 })),
      rx: 0, ry: 0, blinkAt: performance.now() + 2500 + Math.random() * 3000 };
  }

  function lookTarget(now) {
    const idle = !ptr.inside || now - ptr.last > 6000;
    if (!idle) return [ptr.x, ptr.y];
    const t = now / 1000;
    return [innerWidth * (0.5 + 0.34 * Math.sin(t * 0.37)), innerHeight * (0.42 + 0.24 * Math.sin(t * 0.53 + 1))];
  }

  function updateMascot(now) {
    if (!mascot || !mascot.el.isConnected) return;
    const r = mascot.el.getBoundingClientRect();
    if (!r.width) return;
    const [tx, ty] = lookTarget(now);
    // how far a pupil may travel inside its socket (it may ride onto the bevel, never onto the face)
    const maxX = 0.03 * r.width, maxY = 0.046 * r.height;
    for (const p of mascot.pupils) {
      const sx = r.left + p.c[0] * r.width, sy = r.top + p.c[1] * r.height;
      const dx = tx - sx, dy = ty - sy;
      const d = Math.hypot(dx, dy) || 1;
      const k = Math.min(1, d / (r.width * 0.9));
      const gx = (dx / d) * maxX * k, gy = (dy / d) * maxY * k;
      p.x += (gx - p.x) * 0.16; p.y += (gy - p.y) * 0.16;
      p.img.style.transform = `translate(${p.x.toFixed(2)}px, ${p.y.toFixed(2)}px) scaleY(${p.s})`;
    }
    // the whole mark leans a little toward the pointer
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const nx = clamp((tx - cx) / innerWidth, -0.5, 0.5), ny = clamp((ty - cy) / innerHeight, -0.5, 0.5);
    if (!reduced) mascot.tilt.style.transform = `rotateY(${(nx * 18).toFixed(2)}deg) rotateX(${(-ny * 12).toFixed(2)}deg)`;
    // blink: the pupils squash for a moment
    if (now > mascot.blinkAt) {
      mascot.pupils.forEach((p) => { p.s = 0.12; });
      setTimeout(() => mascot && mascot.pupils.forEach((p) => { p.s = 1; }), 130);
      mascot.blinkAt = now + 2600 + Math.random() * 4500 + (Math.random() < 0.2 ? -2000 : 0);
    }
  }

  /* ---------- home layout: the mark in the middle, the six things in a ring around it ---------- */
  let hub = null;
  function setupHub() {
    const stage = document.getElementById('stage');
    if (!stage) { hub = null; return; }
    const nodes = [...stage.querySelectorAll('.node')];
    hub = { stage, nodes, pill: document.getElementById('pill'), tagline: document.getElementById('tagline') };
    layoutHub();
    nodes.forEach((n) => {
      const on = () => { stage.classList.add('focus'); nodes.forEach((o) => o.classList.toggle('on', o === n)); };
      const off = () => { stage.classList.remove('focus'); n.classList.remove('on'); };
      n.addEventListener('pointerenter', on); n.addEventListener('pointerleave', off);
      n.addEventListener('focus', on); n.addEventListener('blur', off);
    });
  }
  function layoutHub() {
    if (!hub || !mascot) return;
    const W = innerWidth, H = innerHeight;
    const narrow = W <= 720;
    if (narrow) { hub.nodes.forEach((n) => { n.style.width = ''; }); return; }
    const avail = H - 70;
    const m = clamp(Math.min(W * 0.4, avail * 0.64, 680), 300, 680);   // width of the mark
    const n = clamp(Math.min(W * 0.115, 165), 92, 165);                  // size of the icons
    const cx = W / 2, cy = 52 + avail * 0.46;
    const rx = clamp(m * 0.5 + n * 0.7 + 40, 0, W / 2 - n * 0.6 - 22);
    const ry = clamp(avail * 0.44, m * 0.4, avail * 0.46);
    mascot.el.style.left = cx + 'px'; mascot.el.style.top = cy + 'px'; mascot.el.style.width = m + 'px';
    hub.nodes.forEach((node) => {
      const a = (NODES.find((x) => x.key === node.dataset.key).angle * Math.PI) / 180;
      node.style.left = cx + Math.cos(a) * rx + 'px';
      node.style.top = cy + Math.sin(a) * ry + 'px';
      node.style.width = n + 'px';
    });
    const bottom = cy + m / (M.w / M.h) / 2;
    hub.tagline.style.top = bottom + 26 + 'px';
    hub.pill.style.left = cx + 'px'; hub.pill.style.top = Math.min(bottom + 86, H - 92) + 'px';
  }

  /* ---------- stars ---------- */
  const starsC = document.getElementById('stars');
  const sctx = starsC.getContext('2d');
  let stars = [];
  function sizeStars() {
    const dpr = Math.min(2, devicePixelRatio || 1);
    starsC.width = innerWidth * dpr; starsC.height = innerHeight * dpr; sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.round((innerWidth * innerHeight) / 9000);
    stars = Array.from({ length: count }, () => ({ x: Math.random() * innerWidth, y: Math.random() * innerHeight, r: Math.random() < 0.12 ? 1.4 : 0.8, a: 0.2 + Math.random() * 0.6, w: Math.random() * 6.28, v: 0.3 + Math.random() * 0.8, z: 0.3 + Math.random() * 0.7 }));
  }
  function drawStars(t) {
    sctx.clearRect(0, 0, innerWidth, innerHeight);
    const px = (ptr.x / innerWidth - 0.5), py = (ptr.y / innerHeight - 0.5);
    for (const s of stars) {
      const tw = reduced ? 1 : 0.65 + 0.35 * Math.sin(t * s.v + s.w);
      sctx.globalAlpha = s.a * tw;
      sctx.fillStyle = s.r > 1 ? '#b9c2ff' : '#e6e9ff';
      sctx.beginPath(); sctx.arc(s.x - px * 18 * s.z, s.y - py * 18 * s.z, s.r, 0, 6.283); sctx.fill();
    }
    sctx.globalAlpha = 1;
  }

  /* ---------- pages: spend ---------- */
  const SOL_FEED = async () => {
    try {
      const r = await fetch('https://api.coinbase.com/v2/prices/SOL-USD/spot', { cache: 'no-store' });
      const j = await r.json(); const p = Number(j.data.amount); if (p > 0) return p;
    } catch (e) { /* fall through */ }
    const r = await fetch('https://api.dexscreener.com/tokens/v1/solana/So11111111111111111111111111111111111111112', { cache: 'no-store' });
    const j = await r.json(); const p = Number((j[0] || {}).priceUsd); if (!(p > 0)) throw new Error('no price'); return p;
  };
  let solPrice = 0;
  function bindSpend(root) {
    let shop = null, amt = 0;
    const qShop = root.querySelector('#qShop'), qAmt = root.querySelector('#qAmt'), qPay = root.querySelector('#qPay');
    const pay = root.querySelector('#payBtn'), payU = root.querySelector('#payUsdc');
    const update = () => {
      qShop.textContent = shop ? shop.name : '—';
      qAmt.textContent = amt ? fmtUsd(amt, 0) + ' balance' : '—';
      const fee = amt * 0.015;
      qPay.textContent = amt ? (solPrice ? `${((amt + fee) / solPrice).toFixed(4)} SOL` : fmtUsd(amt + fee)) + ` (${fmtUsd(amt + fee)})` : '—';
      const ready = !!(shop && amt);
      pay.disabled = !ready || !CONFIG.spendApi; payU.disabled = !ready || !CONFIG.spendApi;
      pay.textContent = ready && !CONFIG.spendApi ? 'Pay with SOL (soon)' : 'Pay with SOL';
    };
    root.querySelectorAll('.shop').forEach((b) => b.addEventListener('click', () => {
      shop = SHOPS.find((s) => s.id === b.dataset.shop);
      root.querySelectorAll('.shop').forEach((o) => o.classList.toggle('on', o === b)); update();
    }));
    root.querySelectorAll('#amounts button').forEach((b) => b.addEventListener('click', () => {
      amt = +b.dataset.amt; root.querySelectorAll('#amounts button').forEach((o) => o.classList.toggle('on', o === b)); update();
    }));
    SOL_FEED().then((p) => { solPrice = p; update(); }).catch(() => {});
    update();
  }

  /* ---------- pages: leaderboard ---------- */
  function bindLeaderboard(root) {
    const rows = root.querySelector('#lbRows'), note = root.querySelector('#lbNote');
    let range = '24h', seq = 0;
    const load = async () => {
      const my = ++seq;
      rows.innerHTML = skeleton(6); note.textContent = '';
      try {
        const r = await fetch(`${CONFIG.leaderboardApi}?range=${encodeURIComponent(range)}`, { cache: 'no-store' });
        if (!r.ok) throw new Error('status ' + r.status);
        const j = await r.json();
        const list = Array.isArray(j) ? j : j.leaderboard || j.responseObject?.leaderboard || [];
        if (my !== seq) return;
        if (!list.length) throw new Error('empty');
        rows.innerHTML = list.slice(0, 25).map((u, i) => {
          const name = u.displayName || u.name || u.handle || 'trader', handle = u.handle || u.username || u.name || '';
          const pnl = Number(u.pnl ?? u.pnlUsd ?? 0), rank = u.rank || i + 1;
          const img = u.profilePictureLink || u.avatar || u.imageUrl;
          return `<a class="row" href="${FOMO}/u/${encodeURIComponent(handle)}" target="_blank" rel="noopener">
            <div class="rank r${rank}">${rank}</div>
            <div class="ava">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : `<span>${esc(name.slice(0, 1).toUpperCase())}</span>`}</div>
            <div class="who"><b>${esc(name)}</b><small>${handle ? '@' + esc(handle) : ''}</small></div>
            <div class="pnl ${pnl < 0 ? 'neg' : ''}">${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)}</div></a>`;
        }).join('');
        note.textContent = 'Live from fomo.';
        completeQuest('leaderboard');
      } catch (e) {
        if (my !== seq) return;
        rows.innerHTML = skeleton(5);
        note.innerHTML = `The live board is served by fomo's API, which needs a fomo session token on the server (see <code>api/leaderboard.mjs</code>). Until it is set, open the board on fomo.`;
        completeQuest('leaderboard');
      }
    };
    root.querySelectorAll('#lbTabs button').forEach((b) => b.addEventListener('click', () => {
      range = b.dataset.range; root.querySelectorAll('#lbTabs button').forEach((o) => o.classList.toggle('on', o === b)); load();
    }));
    load();
  }

  /* ---------- pages: predict ---------- */
  function bindPredict(root) {
    const priceEl = root.querySelector('#price'), sub = root.querySelector('#priceSub'), verdict = root.querySelector('#verdict');
    const up = root.querySelector('#callUp'), down = root.querySelector('#callDown'), meter = root.querySelector('#meter');
    const st = store.get('predict', { streak: 0, best: 0, calls: 0, hits: 0 });
    const paint = () => {
      root.querySelector('#sStreak').textContent = st.streak; root.querySelector('#sBest').textContent = st.best;
      root.querySelector('#sRate').textContent = st.calls ? Math.round((st.hits / st.calls) * 100) + '%' : '–';
    };
    let price = 0, timer = 0, busy = false, alive = true;
    const show = (p) => { price = p; priceEl.firstChild.textContent = fmtUsd(p); };
    const tick = async () => {
      try { const p = await SOL_FEED(); if (alive && !busy) show(p); sub.textContent = ''; }
      catch (e) { sub.textContent = 'price feed unavailable'; }
    };
    tick(); timer = setInterval(tick, 8000);
    const call = async (dir) => {
      if (busy || !price) return;
      busy = true; up.disabled = down.disabled = true;
      const start = price, t0 = Date.now();
      verdict.className = 'verdict'; verdict.textContent = `Called ${dir === 1 ? 'higher' : 'lower'} at ${fmtUsd(start)}. Sixty seconds.`;
      completeQuest('predict');
      meter.style.transition = 'none'; meter.style.width = '0'; meter.getBoundingClientRect();
      meter.style.transition = 'width 60s linear'; meter.style.width = '100%';
      const cd = setInterval(() => { if (!alive) return; const left = Math.max(0, 60 - Math.round((Date.now() - t0) / 1000)); sub.textContent = `${left}s`; }, 500);
      await wait(60000);
      clearInterval(cd); sub.textContent = '';
      if (!alive) return;
      let end = start;
      try { end = await SOL_FEED(); } catch (e) { /* keep start, a tie */ }
      show(end);
      const diff = (end - start) * dir;
      st.calls++;
      if (diff > 0) { st.hits++; st.streak++; st.best = Math.max(st.best, st.streak); verdict.className = 'verdict win'; verdict.textContent = `Right. ${fmtUsd(start)} → ${fmtUsd(end)}. Streak ${st.streak}.`; if (st.streak >= 3) completeQuest('streak3'); }
      else if (diff < 0) { st.streak = 0; verdict.className = 'verdict lose'; verdict.textContent = `Wrong. ${fmtUsd(start)} → ${fmtUsd(end)}. Streak reset.`; }
      else { verdict.className = 'verdict'; verdict.textContent = 'Flat. Nobody wins a tie.'; }
      store.set('predict', st); paint();
      meter.style.transition = 'width .4s ease'; meter.style.width = '0';
      busy = false; up.disabled = down.disabled = false;
    };
    up.addEventListener('click', () => call(1)); down.addEventListener('click', () => call(-1));
    paint();
    return () => { alive = false; clearInterval(timer); };
  }

  /* ---------- pages: quests ---------- */
  const today = () => new Date().toISOString().slice(0, 10);
  function questState() {
    const s = store.get('quests', { day: today(), done: [], total: 0 });
    if (s.day !== today()) { s.day = today(); s.done = []; }
    return s;
  }
  function completeQuest(id) {
    const q = QUESTS.find((x) => x.id === id); if (!q || q.locked) return;
    const s = questState(); if (s.done.includes(id)) return;
    s.done.push(id); s.total += q.xp; store.set('quests', s);
    const root = document.querySelector('[data-page="quests"]'); if (root) paintQuests(root);
  }
  function paintQuests(root) {
    const s = questState();
    const lvl = [...LEVELS].reverse().find((l) => s.total >= l.at) || LEVELS[0];
    const next = LEVELS[LEVELS.indexOf(lvl) + 1];
    root.querySelector('#lvl').textContent = lvl.name;
    root.querySelector('#xpBar').style.width = next ? ((s.total - lvl.at) / (next.at - lvl.at)) * 100 + '%' : '100%';
    root.querySelector('#xpPts').textContent = next ? `${s.total} / ${next.at} pts` : `${s.total} pts · max level`;
    root.querySelector('#questRows').innerHTML = QUESTS.map((q) => `
      <div class="quest ${s.done.includes(q.id) ? 'done' : ''} ${q.locked ? 'locked' : ''}" data-q="${q.id}" role="button" tabindex="0">
        <div class="box"><svg viewBox="0 0 16 16" fill="none" stroke="#06110a" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3 3 7-7"/></svg></div>
        <div class="t"><b>${q.t}</b><small>${q.locked ? 'Opens with FOMOSPEND.' : q.d}</small></div>
        <div class="xpv">+${q.xp}</div>
      </div>`).join('');
    root.querySelectorAll('.quest').forEach((el) => el.addEventListener('click', async () => {
      const q = QUESTS.find((x) => x.id === el.dataset.q);
      if (!q || q.locked) return;
      if (q.href) { open(q.href, '_blank', 'noopener'); completeQuest(q.id); return; }
      if (q.copy) { try { await navigator.clipboard.writeText(location.origin + location.pathname); } catch (e) { /* ignore */ } completeQuest(q.id); el.querySelector('small').textContent = 'Link copied.'; return; }
      go('#/' + (q.id === 'streak3' ? 'predict' : q.id));
    }));
  }

  /* ---------- pages: radar ---------- */
  async function bindRadar(root) {
    const rows = root.querySelector('#radarRows'), note = root.querySelector('#radarNote');
    try {
      const boosts = await (await fetch('https://api.dexscreener.com/token-boosts/top/v1', { cache: 'no-store' })).json();
      const sol = boosts.filter((b) => b.chainId === 'solana').slice(0, 12);
      if (!sol.length) throw new Error('empty');
      const addrs = sol.map((b) => b.tokenAddress).join(',');
      const pairs = await (await fetch(`https://api.dexscreener.com/tokens/v1/solana/${addrs}`, { cache: 'no-store' })).json();
      const best = new Map();
      for (const p of pairs) {
        const a = p.baseToken?.address; if (!a) continue;
        if (!best.has(a) || (p.liquidity?.usd || 0) > (best.get(a).liquidity?.usd || 0)) best.set(a, p);
      }
      rows.innerHTML = sol.map((b) => {
        const p = best.get(b.tokenAddress) || {};
        const sym = p.baseToken?.symbol || '?', name = p.baseToken?.name || b.description?.slice(0, 40) || b.tokenAddress.slice(0, 6);
        const price = Number(p.priceUsd || 0), ch = Number(p.priceChange?.h24 ?? 0), mc = Number(p.marketCap || p.fdv || 0), vol = Number(p.volume?.h24 || 0);
        const icon = p.info?.imageUrl || (b.icon && b.icon.startsWith('http') ? b.icon : '');
        return `<a class="tok" href="${FOMO}/tokens/solana/${esc(b.tokenAddress)}" target="_blank" rel="noopener">
          <div class="ico">${icon ? `<img src="${esc(icon)}" alt="" loading="lazy" onerror="this.remove()">` : esc(sym.slice(0, 2))}</div>
          <div class="who"><b>${esc(sym)} <span style="font-weight:400;color:var(--muted)">${esc(name)}</span></b><small>${mc ? 'mc ' + fmtBig(mc) : ''}${vol ? ' · vol ' + fmtBig(vol) : ''} · ${b.totalAmount || b.amount || 0} boosts</small></div>
          <div class="num"><b>${price ? '$' + (price < 0.01 ? price.toPrecision(3) : price.toFixed(price < 1 ? 4 : 2)) : '—'}</b><small class="${ch >= 0 ? 'pos' : 'neg'}">${ch >= 0 ? '+' : ''}${ch.toFixed(1)}% 24h</small></div>
        </a>`;
      }).join('');
      note.textContent = 'Boosts from DexScreener, prices from the deepest pool. Tap a token to open it on fomo.';
    } catch (e) {
      rows.innerHTML = '';
      note.textContent = 'The radar could not reach DexScreener right now. Try again in a moment.';
    }
    completeQuest('radar');
  }

  /* ---------- router with the flood transition ---------- */
  let busy = false, pendingPop = false, teardown = null;
  const FLOOD_DOWN = 'translateY(calc(100% + 60px))';
  const pathOf = () => (location.hash.replace(/^#/, '') || '/').replace(/\/+$/, '') || '/';

  function render(path) {
    if (teardown) { teardown(); teardown = null; }
    const route = ROUTES[path] || ROUTES['/'];
    view.innerHTML = route.render();
    document.title = path === '/' || !ROUTES[path] ? 'FOMOHUB' : `${route.title} · FOMOHUB`;
    document.body.classList.toggle('on-page', path !== '/');
    setupMascot(); setupHub();
    const root = view.querySelector('[data-page]');
    if (!root) return;
    const key = root.dataset.page;
    if (key === 'spend') bindSpend(root);
    if (key === 'leaderboard') bindLeaderboard(root);
    if (key === 'predict') teardown = bindPredict(root);
    if (key === 'quests') paintQuests(root);
    if (key === 'radar') bindRadar(root);
  }

  async function go(hash) {
    if (busy) return;
    const path = hash.replace(/^#/, '') || '/';
    if (path === pathOf()) return;
    busy = true;
    flood.style.transition = 'none'; flood.style.transform = FLOOD_DOWN; flood.getBoundingClientRect();
    flood.style.transition = 'transform .5s cubic-bezier(.55,0,.85,.35)'; flood.style.transform = 'translateY(0)';
    await wait(reduced ? 0 : 520);
    suppressPop = true; location.hash = hash;
    render(path); scrollTo(0, 0);
    await wait(90); await drain();
    busy = false;
    if (pendingPop) { pendingPop = false; onHash(); }
  }
  async function drain() {
    flood.style.transition = 'transform .8s cubic-bezier(.25,.75,.3,1)'; flood.style.transform = FLOOD_DOWN;
    await wait(reduced ? 0 : 820);
  }
  let suppressPop = false;
  function onHash() {
    if (suppressPop) { suppressPop = false; return; }
    if (busy) { pendingPop = true; return; }
    busy = true;
    (async () => {
      flood.style.transition = 'none'; flood.style.transform = FLOOD_DOWN; flood.getBoundingClientRect();
      flood.style.transition = 'transform .5s cubic-bezier(.55,0,.85,.35)'; flood.style.transform = 'translateY(0)';
      await wait(reduced ? 0 : 520);
      render(pathOf()); scrollTo(0, 0);
      await wait(90); await drain(); busy = false;
      if (pendingPop) { pendingPop = false; onHash(); }
    })();
  }
  addEventListener('hashchange', onHash);
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="#/"]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault(); go(a.getAttribute('href'));
  });

  /* ---------- main loop ---------- */
  function frame(now) { drawStars(now / 1000); updateMascot(now); requestAnimationFrame(frame); }
  let resizing = 0;
  addEventListener('resize', () => { cancelAnimationFrame(resizing); resizing = requestAnimationFrame(() => { sizeStars(); layoutHub(); }); });

  sizeStars();
  render(pathOf());
  requestAnimationFrame(frame);
  wait(150).then(drain);
})();
