/* STONKD-forsiden. Samme mekanisme som stonked.app: velg par, utbetaling og mottaker,
   og fortsett til lanseringen der. Dataene kommer fra stonked.app sitt API, som
   vercel.json sender videre fra /api, slik at nettleseren ser alt som samme side. */

const LAUNCH = 'https://stonked.app/create';
const COIN = 'https://stonked.app/coin';
const CA = '63vCoVhdkjDvcAxcuDA4p8xgLN5ws8yHk4kDrqdQPBet';
const SOL_MINT = 'So11111111111111111111111111111111111111112';

/* ------------------------------------------------------------- hjelpere */
const $ = (id) => document.getElementById(id);

const api = async (path) => {
  const res = await fetch(path);
  const data = await res.json().catch(() => ({ ok: false, error: 'The server sent something unreadable.' }));
  if (!data.ok) throw new Error(data.error || 'unknown error');
  return data;
};

const el = (html) => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const usd = (n, d) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  const abs = Math.abs(n);
  const dec = d !== undefined ? d : (abs >= 1000 ? 0 : abs >= 1 ? 2 : 4);
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
};
const sol = (n, d = 4) => (n === null || n === undefined || isNaN(n)) ? '-'
  : Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) + ' SOL';

const ago = (ts) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 3600) return Math.floor(s / 60) + 'm';
  if (s < 86400) return Math.floor(s / 3600) + 'h';
  return Math.floor(s / 86400) + 'd';
};

const shortAddr = (a) => (a ? a.slice(0, 4) + '…' + a.slice(-4) : '');

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove('show'), 1400);
}

/* ------------------------------------------------------------- mottakere */
const KIND_NAME = { x: 'X profile', github: 'GitHub account', wallet: 'Wallet', holders: 'Holders' };
const KIND_WORD = { x: 'an X profile', github: 'a GitHub account', wallet: 'a Solana wallet', holders: 'the holders' };
const KIND_PH = { x: '@handle', github: 'GitHub username', wallet: 'Wallet address', holders: '' };

function routeAvatar(r, size = 38) {
  const s = `width:${size}px;height:${size}px`;
  if (r.kind === 'holders') return `<span class="rav blank" style="${s}"><img src="/assets/holders.svg" alt=""
    style="width:55%;height:55%"></span>`;
  if (r.kind === 'x') return `<img class="rav" style="${s}" alt="" loading="lazy"
    src="https://unavatar.io/x/${encodeURIComponent(r.target)}?fallback=false"
    onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'rav blank',style:'${s}',textContent:'X'}))">`;
  if (r.kind === 'github') return `<img class="rav" style="${s}" alt="" loading="lazy"
    src="https://github.com/${encodeURIComponent(r.target)}.png?size=${size * 2}">`;
  return `<span class="rav blank" style="${s}">SOL</span>`;
}

function routeLabel(r) {
  if (r.kind === 'holders') return 'Holders';
  if (r.kind === 'x') return '@' + r.target;
  if (r.kind === 'github') return r.target;
  return shortAddr(r.target);
}

/* ------------------------------------------------------------- par */
let allPairs = [];
let xsNames = {};
const PREBAKED = new Set(['SOL']);
const CAT_ORDER = ['xstock', 'prestock', 'tessera', 'backpack', 'currency', 'leverage', 'collectible', 'solana', 'custom'];
const MAX_BASKET = 5;
let platformPct = 10;
let pcat = 'xstock', pq = '', gcat = 'all', gq = '', gshow = 48, bcat = 'xstock', bq = '';
let pick = { symbol: 'APPLX', name: 'Apple', mint: '', kind: 'x', target: '', found: null, avatar: null, basket: [] };

const pairBy = (mint) => allPairs.find((p) => p.mint === mint);
const symOf = (p) => (p.mint === SOL_MINT ? 'SOL' : p.symbol);

const cleanName = (n) => String(n || '').replace(/\s*xStock$/i, '').replace(/^SP500$/, 'the S&P 500')
  .replace(/^Nasdaq$/, 'the Nasdaq 100').replace(/^Gold$/, 'gold');

function niceName(p) {
  if (!p) return '';
  if (p.mint === SOL_MINT) return 'SOL';
  if (xsNames[p.symbol]) return cleanName(xsNames[p.symbol]);
  const n = String(p.name || p.symbol || '');
  if (n.toUpperCase() === String(p.symbol || '').toUpperCase()) return p.symbol;
  if (n.length > 3 && n === n.toUpperCase() && /[A-Z]/.test(n)) {
    return n.toLowerCase().replace(/(^|[\s-])([a-z])/g, (m, a, b) => a + b.toUpperCase());
  }
  return n;
}

const pairLogo = (p) => p.mint === SOL_MINT ? '/assets/sol.png'
  : PREBAKED.has(p.symbol) ? '/assets/xstocks/' + p.symbol + '.png' : p.logo;
const catLabel = (p) => (p.category === 'backpack' ? 'Sunrise' : p.categoryLabel);

function catsOf(rows) {
  const counts = {}, label = {};
  rows.forEach((p) => { counts[p.category] = (counts[p.category] || 0) + 1; label[p.category] = p.categoryLabel; });
  label.backpack = 'Sunrise';
  return CAT_ORDER.filter((c) => counts[c]).concat(Object.keys(counts).filter((c) => !CAT_ORDER.includes(c)))
    .map((c) => ({ id: c, label: label[c] || c, n: counts[c] }));
}

const logoImg = (p) => `<img src="${esc(pairLogo(p))}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
const matches = (p, term) => (p.symbol + ' ' + p.name + ' ' + niceName(p)).toLowerCase().includes(term);

/* ------------------------------------------------------------- kvitteringen */
function basketWords() {
  const b = pick.basket;
  if (!b.length) return 'SOL';
  const names = b.map((mint) => { const p = pairBy(mint) || {}; return b.length <= 2 ? niceName(p) : symOf(p); });
  return names.length === 1 ? names[0] : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
}

function headline() {
  $('h1stock').textContent = pick.symbol === 'SOL' ? 'SOL' : pick.name;
  const who = pick.kind === 'holders' ? KIND_WORD.holders : pick.found ? routeLabel(pick.found) : KIND_WORD[pick.kind];
  $('h1who').textContent = who;
  $('h1basket').textContent = basketWords();
  $('bcount').textContent = pick.basket.length
    ? pick.basket.length + ' of ' + MAX_BASKET + ' · ' + (Math.round(1000 / pick.basket.length) / 10) + '% each'
    : pick.kind === 'holders' ? 'SOL' : 'SOL · pick Holders for other tokens';

  const q = new URLSearchParams();
  if (pick.mint) q.set('quote', pick.mint);
  q.set('kind', pick.kind);
  if (pick.found && pick.kind !== 'holders') q.set('target', pick.found.target);
  if (pick.basket.length) q.set('payout', pick.basket.join(','));
  $('go').href = LAUNCH + '?' + q.toString();

  const cur = pairBy(pick.mint);
  $('rpair').innerHTML = cur ? logoImg(cur) : `<span>${esc(pick.symbol.slice(0, 4))}</span>`;
  $('rwho').innerHTML = pick.found ? routeAvatar(pick.found, 56)
    : `<span>${pick.kind === 'x' ? 'X' : pick.kind === 'github' ? 'GH' : pick.kind === 'holders' ? 'ALL' : 'SOL'}</span>`;

  const rest = 100 - platformPct;
  const to = pick.kind === 'holders' ? 'the holders' : pick.found ? routeLabel(pick.found) : 'the recipient';
  const as = pick.basket.length
    ? `<div><dt>Paid out as</dt><dd>${pick.basket.map((m) => esc(symOf(pairBy(m) || {}))).join(' · ')}</dd></div>` : '';
  emitPick(cur);
  $('split').innerHTML = `
    <div><dt>Of every 1 SOL in fees</dt><dd>1.0000 SOL</dd></div>
    <div><dt>To ${esc(to)}</dt><dd>${(rest / 100).toFixed(4)} SOL</dd></div>
    <div><dt>Platform</dt><dd>${(platformPct / 100).toFixed(4)} SOL</dd></div>${as}`;
}

/* 3D-myntene (coins.js) foelger valgene. Bare naar noe faktisk har endret seg. */
let lastPick = '';
function emitPick(cur) {
  const coinOf = (p) => ({ symbol: symOf(p), logo: pairLogo(p) });
  const detail = {
    pair: cur ? coinOf(cur) : { symbol: pick.symbol, logo: '' },
    kind: pick.kind,
    avatar: pick.found && pick.kind !== 'holders' ? pick.avatar : null,
    basket: pick.basket.map(pairBy).filter(Boolean).map(coinOf),
  };
  const key = JSON.stringify(detail);
  if (key === lastPick) return;
  lastPick = key;
  window.PICK = detail;
  dispatchEvent(new CustomEvent('pick', { detail }));
}

/* ------------------------------------------------------------- velgerne */
function drawStocks() {
  const cats = $('pcats');
  cats.innerHTML = '';
  catsOf(allPairs).forEach((c) => {
    const b = el(`<button class="${c.id === pcat && !pq ? 'on' : ''}">${esc(c.label)}</button>`);
    b.onclick = () => { pcat = c.id; pq = ''; $('psearch').value = ''; drawStocks(); };
    cats.append(b);
  });
  const host = $('stocks');
  host.innerHTML = '';
  const term = pq.trim().toLowerCase();
  let rows = term ? allPairs.filter((p) => matches(p, term)) : allPairs.filter((p) => p.category === pcat);
  const cur = pairBy(pick.mint);
  if (cur && !rows.includes(cur)) rows = [cur, ...rows];
  rows.slice(0, 80).forEach((p) => {
    const b = el(`<button class="${p.mint === pick.mint ? 'on' : ''}" title="${esc(niceName(p))}">${logoImg(p)}${esc(symOf(p))}</button>`);
    b.onclick = () => choosePair(p, b);
    host.append(b);
  });
  if (!rows.length) host.append(el('<span class="none">No pair by that name</span>'));
}

function choosePair(p, btn) {
  pick.symbol = symOf(p);
  pick.name = niceName(p);
  pick.mint = p.mint;
  drawStocks(); headline();
  if (btn) btn.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
}

/* Utbetalingen: SOL, eller opptil fem tokens med lik andel. Bare for coins som betaler holderne. */
function drawBasket() {
  const locked = pick.kind !== 'holders';
  const cats = $('bcats');
  cats.innerHTML = '';
  catsOf(allPairs.filter((p) => p.mint !== SOL_MINT)).forEach((c) => {
    const b = el(`<button class="${c.id === bcat && !bq ? 'on' : ''}">${esc(c.label)}</button>`);
    b.onclick = () => { bcat = c.id; bq = ''; $('bsearch').value = ''; drawBasket(); };
    cats.append(b);
  });
  const host = $('basket');
  host.innerHTML = '';
  const solBtn = el(`<button class="${pick.basket.length ? '' : 'on'}" title="Paid out in SOL"><img src="/assets/sol.png" alt="">SOL</button>`);
  solBtn.onclick = () => { pick.basket = []; drawBasket(); headline(); };
  host.append(solBtn);
  const term = bq.trim().toLowerCase();
  let rows = allPairs.filter((p) => p.mint !== SOL_MINT && (term ? matches(p, term) : p.category === bcat));
  const chosen = pick.basket.map(pairBy).filter(Boolean);
  rows = [...chosen, ...rows.filter((p) => !pick.basket.includes(p.mint))];
  rows.slice(0, 80).forEach((p) => {
    const on = pick.basket.includes(p.mint);
    const full = !on && pick.basket.length >= MAX_BASKET;
    const b = el(`<button class="${on ? 'on' : ''} ${full || locked ? 'dim' : ''}"
      title="${locked ? 'Pick Holders to choose other tokens' : esc(niceName(p))}">${logoImg(p)}${esc(symOf(p))}</button>`);
    b.onclick = () => {
      if (locked) { toast('Pick Holders to pay out in other tokens'); return; }
      if (on) pick.basket = pick.basket.filter((x) => x !== p.mint);
      else if (!full) pick.basket = [...pick.basket, p.mint];
      drawBasket(); headline();
    };
    host.append(b);
  });
}

/* Mottakeren: samme oppslag som paa launch-siden. */
let lookTimer = null, lookSeq = 0;
function lookup() {
  clearTimeout(lookTimer);
  const box = $('found');
  pick.target = $('target').value.trim();
  pick.found = null;
  pick.avatar = null;
  box.className = 'found';
  if (pick.kind === 'holders') {
    pick.found = { kind: 'holders', target: 'holders' };
    box.textContent = 'Paid to everyone holding the coin, by how much each one holds.';
    headline();
    return;
  }
  if (!pick.target) {
    box.textContent = pick.kind === 'wallet' ? 'Paste the address the fees should go to.'
      : 'Type a ' + (pick.kind === 'x' ? 'handle' : 'username') + ' to see who it is.';
    headline();
    return;
  }
  box.textContent = 'Looking it up';
  const seq = ++lookSeq;
  lookTimer = setTimeout(async () => {
    try {
      const d = await api('/api/lookup?kind=' + pick.kind + '&target=' + encodeURIComponent(pick.target));
      if (seq !== lookSeq) return;
      if (!d.exists) {
        box.className = 'found bad';
        box.textContent = (pick.kind === 'x' ? '@' : '') + d.route.target + ' does not exist.';
      } else {
        pick.found = d.route;
        const p = d.profile || {};
        pick.avatar = p.avatar ? p.avatar.replace('_normal.', '_400x400.') : null;
        box.innerHTML = `${routeAvatar(d.route, 22)}<span><b>${esc(p.name || routeLabel(d.route))}</b>
          ${pick.kind === 'wallet' ? '' : ' · ' + esc(routeLabel(d.route))}${p.followers != null
            ? ' · ' + Number(p.followers).toLocaleString('en-US') + ' followers' : ''}</span>`;
      }
    } catch (e) {
      if (seq !== lookSeq) return;
      box.className = 'found bad';
      box.textContent = e.message;
    }
    headline();
  }, 450);
}

/* X, GitHub og en lommebok faar SOL og bare SOL. Aksjer i utbetalingen betyr at holderne faar dem. */
function setKind(k) {
  pick.kind = k;
  document.querySelectorAll('#kinds button').forEach((x) => x.classList.toggle('on', x.dataset.v === k));
  const inp = $('target');
  inp.value = '';
  inp.placeholder = KIND_PH[k];
  inp.hidden = k === 'holders';
  if (k !== 'holders') pick.basket = [];
  drawBasket();
  headline();
  lookup();
}

/* ------------------------------------------------------------- alle par */
function drawPairs() {
  const cats = $('gcats');
  cats.innerHTML = '';
  [{ id: 'all', label: 'All', n: allPairs.length }, ...catsOf(allPairs)].forEach((c) => {
    const b = el(`<button class="${c.id === gcat ? 'on' : ''}">${esc(c.label)}<span class="n">${c.n}</span></button>`);
    b.onclick = () => { gcat = c.id; gshow = 48; drawPairs(); };
    cats.append(b);
  });
  const term = gq.trim().toLowerCase();
  const rows = allPairs.filter((p) => (gcat === 'all' || p.category === gcat) && (!term || matches(p, term)));
  const host = $('pgrid');
  host.innerHTML = '';
  rows.slice(0, gshow).forEach((p) => {
    const card = el(`<a class="pcard" href="#launch"><div class="disc">${logoImg(p)}</div>
      <b>${esc(symOf(p))}</b><small>${esc(niceName(p))}</small><em>${esc(catLabel(p))}</em></a>`);
    card.onclick = () => { pcat = p.category; choosePair(p); };
    host.append(card);
  });
  if (!rows.length) host.append(el('<div class="empty">No pair by that name.</div>'));
  const more = $('gmore');
  more.hidden = rows.length <= gshow;
  more.textContent = 'Show more (' + (rows.length - gshow) + ')';
  more.onclick = () => { gshow += 96; drawPairs(); };
  if (allPairs.length) {
    $('pcount').textContent = allPairs.length + ' pairs StonkFun launches against: tokenized stocks, pre-IPO shares, '
      + 'currencies, SOL and Solana tokens. Pick one to start a launch.';
  }
}

/* ------------------------------------------------------------- tall */
async function nums() {
  const s = await api('/api/stats');
  $('strip').innerHTML = `
    <div><dt>Coins launched</dt><dd>${s.coins}</dd></div>
    <div><dt>Fees collected</dt><dd>${usd(s.feesUsd, 0)}</dd></div>
    <div><dt>Recipients</dt><dd>${s.recipients}</dd></div>`;
  $('nums').innerHTML = `
    <div><p class="k">Coins launched</p><p class="v">${s.coins}</p><p class="s">on StonkFun through STONKD</p></div>
    <div><p class="k">Fees collected</p><p class="v">${usd(s.feesUsd, 0)}</p><p class="s">${sol(s.feesSol, 2)}</p></div>
    <div><p class="k">Paid out</p><p class="v">${usd(s.paidUsd, 0)}</p><p class="s">${sol(s.paidSol, 2)}</p></div>
    <div><p class="k">Recipients</p><p class="v">${s.recipients}</p><p class="s">${s.kinds.x} X · ${s.kinds.github} GitHub · ${s.kinds.wallet} wallets · ${s.kinds.holders || 0} holder coins</p></div>`;
}

/* ------------------------------------------------------------- coins */
const KINDS = [['all', 'All'], ['x', 'X'], ['github', 'GitHub'], ['wallet', 'Wallet'], ['holders', 'Holders']];
const SORTS = [['newest', 'Newest'], ['fees', 'Most fees']];
const state = { kind: 'all', sort: 'newest', q: '', coins: null };

function chips(host, items, key, after) {
  host.innerHTML = '';
  items.forEach(([id, label]) => {
    const b = el(`<button class="${state[key] === id ? 'on' : ''}">${label}</button>`);
    b.onclick = () => { state[key] = id; chips(host, items, key, after); after(); };
    host.append(b);
  });
}

function coinCard(c) {
  const r = c.route;
  const img = c.image ? `<img class="cimg" src="${esc(c.image)}" alt="" loading="lazy">`
    : `<div class="avatar">${esc(c.ticker.slice(0, 3))}</div>`;
  const paid = ['wallet', 'holders'].includes(r.kind) ? '<span class="tag">Paid automatically</span>' : '';
  return el(`<a class="card" href="${COIN}?mint=${encodeURIComponent(c.mint)}">
    <div class="card-top">${img}
      <div style="min-width:0"><div class="card-name">${esc(c.name)}</div>
        <div class="card-sub">${esc(c.ticker)} · ${esc(c.quoteSymbol || 'SOL')} pair · ${ago(c.createdAt)} old</div></div>
      ${paid}</div>
    <div class="wire"><span class="fee">${usd(c.feesUsd, 2)} fees</span><span class="line"></span>
      <div class="who">${routeAvatar(r, 30)}<div><b>${esc(routeLabel(r))}</b><small>${KIND_NAME[r.kind]}</small></div></div></div>
  </a>`);
}

function drawCoins() {
  const grid = $('grid');
  if (!state.coins) return;
  const term = state.q.trim().toLowerCase();
  const rows = state.coins.filter((c) => (state.kind === 'all' || c.route.kind === state.kind)
    && (!term || (c.name + ' ' + c.ticker + ' ' + c.route.target).toLowerCase().includes(term)));
  grid.innerHTML = '';
  if (!rows.length) {
    grid.append(el(state.coins.length ? '<div class="empty">No coin matches that filter.</div>'
      : '<div class="empty">Nothing has launched here yet. <a href="#launch" style="color:var(--accent-2)">Launch the first one</a>.</div>'));
    return;
  }
  rows.forEach((c) => grid.append(coinCard(c)));
}

async function loadCoins() {
  try {
    state.coins = (await api('/api/coins?sort=' + state.sort)).coins;
    drawCoins();
  } catch (e) {
    $('grid').innerHTML = `<div class="empty">Could not load coins: ${esc(e.message)}</div>`;
  }
}

/* ------------------------------------------------------------- oppstart */
async function boot() {
  const [list, cfg, pairs] = await Promise.allSettled([
    fetch('/assets/xstocks/_list.json').then((r) => r.json()), api('/api/config'), api('/api/pairs?limit=1000')]);
  if (list.status === 'fulfilled') {
    list.value.filter((s) => s.symbol).forEach((s) => { xsNames[s.symbol] = s.name; PREBAKED.add(s.symbol); });
  }
  if (pairs.status === 'fulfilled') allPairs = pairs.value.pairs || [];
  else $('stocks').innerHTML = '<span class="none">Could not load the pairs. Reload the page to try again.</span>';
  const first = allPairs.find((p) => p.symbol === pick.symbol);
  if (first) { pick.name = niceName(first); pick.mint = first.mint; }
  if (cfg.status === 'fulfilled') platformPct = cfg.value.config.platformBps / 100;
  drawStocks(); drawBasket(); drawPairs(); headline();
}

$('cav').textContent = CA.slice(0, 4) + '…' + CA.slice(-5);
$('ca').onclick = async () => {
  try { await navigator.clipboard.writeText(CA); toast('Contract address copied'); } catch (e) { toast(CA); }
};
document.querySelectorAll('#kinds button').forEach((b) => { b.onclick = () => setKind(b.dataset.v); });
$('target').oninput = lookup;
$('psearch').oninput = (e) => { pq = e.target.value; drawStocks(); };
$('bsearch').oninput = (e) => { bq = e.target.value; drawBasket(); };
$('gq').oninput = (e) => { gq = e.target.value; gshow = 48; drawPairs(); };
$('q').oninput = (e) => { state.q = e.target.value; drawCoins(); };
chips($('kindchips'), KINDS, 'kind', drawCoins);
chips($('sorts'), SORTS, 'sort', loadCoins);

/* Radene med valg rulles sidelengs med vanlig musehjul ogsaa. */
document.querySelectorAll('.row, .cats').forEach((row) => {
  row.addEventListener('wheel', (e) => {
    if (Math.abs(e.deltaY) <= Math.abs(e.deltaX) || row.scrollWidth <= row.clientWidth) return;
    const max = row.scrollWidth - row.clientWidth;
    if ((e.deltaY < 0 && row.scrollLeft <= 0) || (e.deltaY > 0 && row.scrollLeft >= max)) return;
    row.scrollLeft += e.deltaY;
    e.preventDefault();
  }, { passive: false });
});

const nav = $('nav');
const onScroll = () => nav.classList.toggle('solid', scrollY > 24);
addEventListener('scroll', onScroll, { passive: true });
onScroll();

headline();
boot();
nums().catch(() => {});
loadCoins();
setInterval(() => { loadCoins(); nums().catch(() => {}); }, 30000);
