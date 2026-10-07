/* FOMOCARD · get access.
   Virtual card: connect a wallet, claim (stored against the wallet), then shop
   through the SPEND checkout (Bitrefill balances paid from the wallet).
   Physical card: delivery details, stored for the operator.
   Every /api call goes to the SPEND backend (proxied by vercel.json). */
(() => {
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const short = a => a ? a.slice(0, 4) + '…' + a.slice(-4) : '';
const money = (n, c) => n == null ? '–' : new Intl.NumberFormat('en-US', {style: 'currency', currency: c || 'USD', maximumFractionDigits: 2}).format(n);
const tok = (n, d) => n == null ? '–' : Number(n).toLocaleString('en-US', {maximumFractionDigits: Math.min(d ?? 6, 6)});
const b64bytes = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const b64 = bytes => { let s = ''; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(s); };
const USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
const X = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';
const isPhone = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

const S = {cfg: null, wallet: null, card: null, tokens: [], payMint: USDC, country: null, catalog: null,
           q: '', cat: '', product: null, value: null, quote: null, busy: false};

async function J(u, o){ try { const r = await fetch(u, o); return await r.json(); } catch (e) { return {ok: false, error: 'Network error, try again.'}; } }
const post = (u, body) => J(u, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
let tt;
function toast(m){ const t = $('#toast'); t.textContent = m; t.classList.add('on'); clearTimeout(tt); tt = setTimeout(() => t.classList.remove('on'), 3600); }
const store = {
  get(k, d){ try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
};

/* ------------------------------------------------------------ views */
function view(){
  const v = (location.hash || '').replace('#', '');
  const name = ['virtual', 'physical'].includes(v) ? v : 'choose';
  $$('.ax-view').forEach(s => { s.hidden = s.dataset.view !== name; });
  if (name === 'virtual') paintClaim();
  if (name === 'physical') paintPhys();
  scrollTo({top: 0, behavior: 'instant'});
}
addEventListener('hashchange', view);
$$('.ax-opt').forEach(o => o.addEventListener('click', e => {
  if (!e.target.closest('a')) location.hash = o.dataset.go;
}));

/* card tilt, follows the pointer */
function tilt(root){
  root.querySelectorAll('.ax-tilt').forEach(t => {
    const host = t.closest('.ax-opt, .ax-stage, .ax-phys-l') || t;
    host.addEventListener('pointermove', e => {
      const r = host.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      t.style.transform = `rotateY(${x * 16}deg) rotateX(${-y * 12}deg) translateZ(10px)`;
    });
    host.addEventListener('pointerleave', () => { t.style.transform = ''; });
  });
}

/* ------------------------------------------------------------ wallet (Wallet Standard) */
const wallets = [];
try {
  const reg = {register: (...ws) => ws.forEach(w => { if (!wallets.includes(w)) wallets.push(w); })};
  addEventListener('wallet-standard:register-wallet', e => { try { e.detail(reg); } catch (x) {} });
  dispatchEvent(new CustomEvent('wallet-standard:app-ready', {detail: reg}));
} catch (e) {}
const okW = w => !!(w && w.features && w.features['standard:connect'] && w.features['solana:signTransaction']
  && Array.isArray(w.chains) && w.chains.some(c => String(c).startsWith('solana:')));
const phantom = () => wallets.find(w => /phantom/i.test(w.name || '') && okW(w)) || wallets.find(okW) || null;
async function account(){
  const w = wallets.find(x => (x.accounts || []).some(a => a.address === S.wallet) && okW(x)) || phantom();
  if (!w) return null;
  if (!(w.accounts || []).some(a => a.address === S.wallet)){ try { await w.features['standard:connect'].connect({silent: true}); } catch (e) {} }
  const acc = (w.accounts || []).find(a => a.address === S.wallet);
  return acc ? {w, acc} : null;
}
async function signAll(txs){
  const sa = await account();
  if (!sa) throw new Error('Your wallet did not expose an account. Reconnect and try again.');
  const f = sa.w.features['solana:signTransaction'];
  const inputs = txs.map(t => ({transaction: b64bytes(t), account: sa.acc, chain: 'solana:mainnet'}));
  try { const out = await f.signTransaction(...inputs); if (out.length === txs.length) return out.map(o => o.signedTransaction); }
  catch (e) { if (txs.length === 1 || /reject|cancel|denied/i.test(e.message || '')) throw e; }
  const res = []; for (const i of inputs){ const [o] = await f.signTransaction(i); res.push(o.signedTransaction); } return res;
}
async function connect(){
  // the wallet registers a moment after load, so give it a beat before saying it is missing
  if (!phantom()) await new Promise(r => setTimeout(r, 400));
  const w = phantom();
  if (!w){
    if (isPhone){
      location.href = `https://phantom.app/ul/browse/${encodeURIComponent(location.href)}?ref=${encodeURIComponent(location.origin)}`;
      return false;
    }
    sheet('No wallet found', `<div class="ax-sheet-b">
      <p>Install a Solana wallet in this browser, then come back to this page.</p>
      <a class="btn btn-light ax-block" href="https://phantom.com/download" target="_blank" rel="noopener">Get a wallet</a></div>`);
    return false;
  }
  try {
    await w.features['standard:connect'].connect();
    const pk = (w.accounts[0] || {}).address;
    if (!pk) throw new Error('no account');
    await setWallet(pk);
    return true;
  } catch (e) { toast('Connection cancelled'); return false; }
}
async function setWallet(pk){
  S.wallet = pk;
  try { sessionStorage.setItem('fc.w', pk); } catch (e) {}
  paintWallet();
  const d = await J('/api/fomocard/card?wallet=' + encodeURIComponent(pk));
  S.card = d.card || null;
  rememberMe();
  loadTokens();
  if (location.hash === '#virtual') paintClaim();
  if (location.hash === '#physical') paintLinked();
}
function disconnect(){
  S.wallet = null; S.card = null; S.tokens = []; S.payMint = USDC;
  try { sessionStorage.removeItem('fc.w'); } catch (e) {}
  rememberMe();
  paintWallet(); view();
}
function rememberMe(){
  if (S.wallet && S.card) store.set('fc.me', {wallet: S.wallet, last4: S.card.last4});
  else try { localStorage.removeItem('fc.me'); } catch (e) {}
  const m = $('#mypage'); if (m) m.hidden = !(S.wallet && S.card);
}
function paintWallet(){
  const b = $('#wallet');
  b.innerHTML = S.wallet ? `<span class="dot"></span>${esc(short(S.wallet))}` : 'Connect wallet';
}
$('#wallet').addEventListener('click', () => S.wallet ? disconnect() : connect());
async function loadTokens(){
  if (!S.wallet) return;
  const d = await J('/api/wallet?address=' + encodeURIComponent(S.wallet));
  S.tokens = d.tokens || [];
  const has = m => S.tokens.some(t => t.mint === m && t.raw > 0);
  if (!has(S.payMint)) S.payMint = has(USDC) ? USDC : (S.tokens.find(t => t.raw > 0) || {}).mint || USDC;
  if (S.product && $('#buy')) paintBuy();
}
const payToken = () => S.tokens.find(t => t.mint === S.payMint) || (S.payMint === USDC ? {mint: USDC, symbol: 'USDC', decimals: 6, amount: 0} : null);

/* ------------------------------------------------------------ the virtual card */
function myCard(c){
  return `<div class="ax-mycard">
    <img src="assets/card_virtual.png" alt="Your FOMOCARD Virtual" draggable="false">
    <div class="ax-print"><span class="ax-v">Virtual</span><span class="ax-no">•••• ${esc(c.last4)}</span>
      <span class="ax-holder">${esc(short(c.wallet))}</span></div>
    <div class="ax-shine"></div></div>`;
}
function paintClaim(){
  const box = $('#claim');
  if (S.card){
    const since = new Date((S.card.claimed_at || 0) * 1000).toLocaleDateString('en-US', {month: 'short', year: 'numeric'});
    box.innerHTML = `
      <div class="ax-stage"><div class="ax-tilt">${myCard(S.card)}</div></div>
      <div class="ax-claim-copy">
        <span class="ax-k">Your card</span>
        <h2>FOMOCARD<br>Virtual</h2>
        <p>Your card is tied to this wallet. Spend it at the shops below and pay straight from your wallet.</p>
        <div class="ax-stats">
          <div><small>Holder</small><b>${esc(short(S.card.wallet))}</b></div>
          <div><small>Card</small><b>•••• ${esc(S.card.last4)}</b></div>
          <div><small>Since</small><b>${esc(since)}</b></div>
        </div>
        <a class="btn btn-light" href="#virtual" onclick="document.getElementById('shop').scrollIntoView({behavior:'smooth'});return false">Start shopping</a>
      </div>`;
    $('#shop').hidden = false;
    initShop();
  } else {
    box.innerHTML = `
      <div class="ax-stage"><div class="ax-tilt"><img src="assets/card_virtual.png" alt="FOMOCARD Virtual" draggable="false"></div></div>
      <div class="ax-claim-copy">
        <span class="ax-k">01 · Virtual</span>
        <h2>Claim your<br>virtual card</h2>
        <p>${S.wallet ? 'Your wallet is connected. Claim the card and it is tied to this wallet for good.'
                      : 'Connect your wallet to claim. The card is tied to the wallet that claims it, and you shop with it right away.'}</p>
        <button class="btn btn-light" id="claim-btn" type="button">${S.wallet ? 'Claim card' : 'Connect wallet'}</button>
        <span class="ax-hint">Free to claim. 4% fee per purchase. By claiming you accept the <a href="/docs">terms</a>.</span>
      </div>`;
    $('#shop').hidden = true;
    $('#claim-btn').onclick = claim;
  }
  tilt(box);
}
async function claim(){
  if (!S.wallet && !(await connect())) return;
  if (S.card) return paintClaim();
  const b = $('#claim-btn');
  if (b){ b.disabled = true; b.textContent = 'Claiming…'; }
  const d = await post('/api/fomocard/claim', {wallet: S.wallet});
  if (!d.ok){ toast(d.error || 'Could not claim, try again.'); if (b){ b.disabled = false; b.textContent = 'Claim card'; } return; }
  S.card = d.card;
  rememberMe();
  // the page under the overlay is drawn first, so nothing swaps when it lifts
  paintClaim();
  await reveal(d.card);
}

/* The moment: the card flies in from the dark, turns over and lands. On
   "Start spending" it glides down into its place on the page while the dark
   lifts, and then the page moves on to the shops. Only transform and opacity
   are animated, so nothing repaints the page underneath. */
function reveal(c){
  return new Promise(done => {
    const r = $('#reveal');
    r.innerHTML = `<div class="ax-rv-glow"></div>
      <div class="ax-rv-card">
        <div class="ax-rv-face ax-rv-front">${myCard(c)}<div class="ax-rv-sweep"><i></i></div></div>
        <div class="ax-rv-face ax-rv-back"><img src="assets/mark.svg" alt=""></div>
      </div>
      <div class="ax-rv-text"><h2>Your card<br>is ready</h2><p>${esc(short(c.wallet))} · •••• ${esc(c.last4)}</p>
        <button class="btn btn-light" type="button">Start spending</button></div>`;
    r.hidden = false;
    document.documentElement.style.overflow = 'hidden';
    scrollTo({top: 0, behavior: 'instant'});
    requestAnimationFrame(() => r.classList.add('on'));
    const card = r.querySelector('.ax-rv-card'), glow = r.querySelector('.ax-rv-glow'), text = r.querySelector('.ax-rv-text');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const ease = 'cubic-bezier(.16,.84,.24,1)';
    const fly = card.animate(reduced ? [{opacity: 0}, {opacity: 1}] : [
      {transform: 'translate3d(0, 60vh, -900px) rotateX(70deg) rotateY(180deg) rotateZ(-14deg)', opacity: 0},
      {transform: 'translate3d(0, 8vh, -300px) rotateX(24deg) rotateY(320deg) rotateZ(-4deg)', opacity: 1, offset: .45},
      {transform: 'translate3d(0, -1vh, 40px) rotateX(-6deg) rotateY(372deg) rotateZ(1deg)', offset: .8},
      {transform: 'translate3d(0, 0, 0) rotateX(0deg) rotateY(360deg) rotateZ(0deg)', opacity: 1}
    ], {duration: reduced ? 300 : 2100, easing: ease, fill: 'forwards'});
    glow.animate([{opacity: 0, transform: 'scale(.6)'}, {opacity: 1, transform: 'scale(1)'}], {duration: 1600, delay: 700, fill: 'forwards', easing: 'ease-out'});
    fly.finished.then(() => {
      if (!reduced) r.querySelector('.ax-rv-sweep i').animate(
        [{transform: 'translateX(-120%) skewX(-18deg)'}, {transform: 'translateX(320%) skewX(-18deg)'}],
        {duration: 1100, easing: 'ease-in-out', fill: 'forwards'});
      text.classList.add('on');
    });
    const close = async () => {
      text.querySelector('button').disabled = true;
      const target = document.querySelector('#claim .ax-mycard');
      const from = card.getBoundingClientRect();
      const to = target ? target.getBoundingClientRect() : null;
      const dur = reduced ? 200 : 750;
      // fade the dark, the glow and the words; the card itself stays solid and lands
      r.classList.remove('on');
      text.animate([{opacity: 1}, {opacity: 0, transform: 'translateY(12px)'}], {duration: dur * .5, fill: 'forwards'});
      glow.animate([{opacity: 1}, {opacity: 0}], {duration: dur * .6, fill: 'forwards'});
      if (to && to.width && !reduced){
        if (target) target.style.visibility = 'hidden';
        const dx = (to.left + to.width / 2) - (from.left + from.width / 2);
        const dy = (to.top + to.height / 2) - (from.top + from.height / 2);
        const k = to.width / from.width;
        fly.cancel();
        await card.animate([{transform: 'translate3d(0,0,0) scale(1)'}, {transform: `translate3d(${dx}px, ${dy}px, 0) scale(${k})`}],
          {duration: dur, easing: 'cubic-bezier(.65,0,.25,1)', fill: 'forwards'}).finished;
        if (target) target.style.visibility = '';
      } else {
        await card.animate([{opacity: 1}, {opacity: 0}], {duration: dur, fill: 'forwards'}).finished;
      }
      r.hidden = true; r.innerHTML = '';
      document.documentElement.style.overflow = '';
      done();
      // a short beat on the landed card, then on to the shops
      setTimeout(() => { const s = $('#shop'); if (s && !s.hidden) s.scrollIntoView({behavior: 'smooth', block: 'start'}); }, reduced ? 0 : 350);
    };
    text.querySelector('button').onclick = close;
  });
}

/* ------------------------------------------------------------ shop */
function guessCountry(list){
  const saved = store.get('fc.country', null);
  if (saved && list.some(c => c.code === saved)) return saved;
  const langs = navigator.languages || [navigator.language || ''];
  for (const l of langs){
    const m = String(l).match(/-([A-Z]{2})$/i);
    if (m && list.some(c => c.code === m[1].toUpperCase())) return m[1].toUpperCase();
  }
  return 'US';
}
async function loadCfg(){
  if (!S.cfg) S.cfg = await J('/api/config');
  return S.cfg;
}
let shopReady = false;
async function initShop(){
  await loadCfg();
  if (!S.country) S.country = guessCountry(S.cfg.countries || []);
  paintCountry();
  if (!shopReady){
    shopReady = true;
    $('#country').onclick = openCountries;
    $('#orders-btn').onclick = openOrders;
    const q = $('#q');
    q.oninput = () => { S.q = q.value; paintGrid(); };
  }
  loadCatalog();
}
function countryName(code){ return ((S.cfg.countries || []).find(c => c.code === code) || {name: code}).name; }
function paintCountry(){ $('#country').innerHTML = `${esc(countryName(S.country))} <span class="cc">${esc(S.country)}</span>`; }
async function loadCatalog(){
  $('#grid').innerHTML = Array.from({length: 8}, () => '<div class="ax-skel"></div>').join('');
  $('#chips').innerHTML = '';
  const want = S.country;
  const d = await J('/api/catalog?country=' + encodeURIComponent(want));
  if (want !== S.country) return;
  S.catalog = d;
  const cats = d.categories || [];
  $('#chips').innerHTML = cats.length ? [`<button class="ax-chip ${S.cat ? '' : 'on'}" data-c="">All</button>`]
    .concat(cats.map(c => `<button class="ax-chip ${S.cat === c.key ? 'on' : ''}" data-c="${esc(c.key)}">${esc(c.label)}</button>`)).join('') : '';
  $$('#chips .ax-chip').forEach(b => b.onclick = () => { S.cat = b.dataset.c; $$('#chips .ax-chip').forEach(x => x.classList.toggle('on', x === b)); paintGrid(); });
  paintGrid();
}
function art(c){
  const mark = c.mark || c.image;
  return `<div class="ax-art${c.light ? ' light' : ''}" style="--brand:${esc(c.face || '#1c1c22')}">
    ${mark ? `<img src="${esc(mark)}" alt="${esc(c.name)}" loading="lazy" onerror="this.outerHTML='<span class=nm>${esc(c.name).replace(/'/g, '')}</span>'">` : `<span class="nm">${esc(c.name)}</span>`}
    ${c.in_stock ? '' : '<span class="ax-oos">Out of stock</span>'}</div>`;
}
function span(c){
  const r = c.range, p = c.packages || [];
  if (r) return `${money(r.min, c.currency)} to ${money(r.max, c.currency)}`;
  if (p.length) return p.length === 1 ? money(p[0].value, c.currency) : `${money(p[0].value, c.currency)} to ${money(p[p.length - 1].value, c.currency)}`;
  return '';
}
function paintGrid(){
  const g = $('#grid');
  let cards = (S.catalog && S.catalog.cards) || [];
  if (S.q) cards = cards.filter(c => (c.name || '').toLowerCase().includes(S.q.toLowerCase()));
  if (S.cat) cards = cards.filter(c => (c.categories || []).includes(S.cat));
  if (!cards.length){
    g.innerHTML = `<div class="ax-empty"><b>${S.catalog && (S.catalog.cards || []).length ? 'Nothing matches' : 'No shops in ' + esc(countryName(S.country)) + ' yet'}</b>${S.catalog && (S.catalog.cards || []).length ? 'Try another search or category.' : 'Pick another country.'}</div>`;
    return;
  }
  g.innerHTML = cards.map((c, i) => `<button class="ax-tile" type="button" data-i="${i}">${art(c)}
    <div class="ax-tile-b"><b>${esc(c.name)}</b><small>${esc(span(c))}${c.range ? ' · any amount' : ''}</small></div></button>`).join('');
  $$('#grid .ax-tile').forEach(t => t.onclick = () => openProduct(cards[+t.dataset.i]));
}
function openCountries(){
  const list = S.cfg.countries || [];
  sheet('Country', `<div class="ax-sheet-b">
    <label class="ax-search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="cq" placeholder="Search countries" autocomplete="off"></label>
    <div class="ax-list-opts" id="clist"></div></div>`);
  const paint = q => {
    q = (q || '').toLowerCase();
    const hit = list.filter(c => !q || c.name.toLowerCase().includes(q) || c.code.toLowerCase() === q || (c.currency || '').toLowerCase() === q).slice(0, 80);
    $('#clist').innerHTML = hit.map(c => `<button class="ax-pick ${c.code === S.country ? 'on' : ''}" data-c="${esc(c.code)}">
      <span class="ax-ic">${esc(c.code)}</span><span class="ax-pick-t"><b>${esc(c.name)}</b><small>${esc(c.currency || '')}</small></span></button>`).join('')
      || '<div class="ax-empty"><b>No country found</b></div>';
    $$('#clist .ax-pick').forEach(b => b.onclick = () => {
      S.country = b.dataset.c; S.cat = ''; store.set('fc.country', S.country);
      closeSheet(); paintCountry(); loadCatalog();
    });
  };
  paint('');
  const cq = $('#cq'); cq.oninput = () => paint(cq.value); setTimeout(() => cq.focus(), 350);
}

/* ------------------------------------------------------------ buy */
const validValue = (c, v) => v != null && !isNaN(v) && ((c.packages || []).some(p => Math.abs(p.value - v) < 1e-9)
  || !!(c.range && v >= c.range.min - 1e-9 && v <= c.range.max + 1e-9));
function openProduct(c){
  S.product = c; S.quote = null;
  const packs = c.packages || [];
  S.value = packs.length ? packs[Math.min(1, packs.length - 1)].value : (c.range ? c.range.min : null);
  sheet(esc(c.name), `<div class="ax-sheet-b">
    <div class="ax-hero-art">${art(c)}</div>
    <p style="font-size:14px">Top up your ${esc(c.name)} balance for ${esc(c.country_name || countryName(S.country))}. It arrives in seconds and you add it to your own ${esc(c.name)} account.</p>
    ${c.note ? `<div class="ax-note">${esc(c.note)}</div>` : ''}
    <div id="buy" style="display:grid;gap:18px"></div></div>`);
  paintBuy();
}
function paintBuy(){
  const c = S.product, r = c.range, packs = c.packages || [], t = payToken();
  $('#buy').innerHTML = `
    <div class="ax-label">Amount</div>
    ${packs.length ? `<div class="ax-amts">${packs.map(p => `<button class="ax-amt ${Math.abs(p.value - S.value) < 1e-9 ? 'on' : ''}" data-v="${p.value}">${money(p.value, c.currency)}</button>`).join('')}</div>` : ''}
    ${r ? `<label class="ax-field"><span class="cur">${esc(c.currency)}</span>
      <input id="val" type="number" inputmode="decimal" step="${r.step || 0.01}" min="${r.min}" max="${r.max}" value="${S.value ?? ''}">
      <span class="rng">${money(r.min, c.currency)} to ${money(r.max, c.currency)}</span></label>` : ''}
    <div class="ax-label">Pay with</div>
    <button class="ax-pick" id="paywith" type="button">
      <span class="ax-ic">${t && t.icon ? `<img src="${esc(t.icon)}" alt="">` : esc((t && t.symbol || 'USDC').slice(0, 4))}</span>
      <span class="ax-pick-t"><b>${esc(t && t.symbol || 'USDC')}</b><small>${S.wallet ? (t ? tok(t.amount, t.decimals) + ' in wallet' : 'not held') : 'connect to see your balance'}</small></span>
      <span class="ax-pick-v">${t && t.value_usd != null ? money(t.value_usd) : ''}</span></button>
    <div id="quote"></div>`;
  $$('#buy .ax-amt').forEach(b => b.onclick = () => setValue(parseFloat(b.dataset.v)));
  const v = $('#val');
  if (v) v.oninput = () => { const n = parseFloat(v.value); S.value = isNaN(n) ? null : n; $$('#buy .ax-amt').forEach(b => b.classList.toggle('on', Math.abs(parseFloat(b.dataset.v) - S.value) < 1e-9)); quoteNow(); };
  $('#paywith').onclick = openTokens;
  quoteNow();
}
function setValue(v){ S.value = v; const f = $('#val'); if (f) f.value = v; $$('#buy .ax-amt').forEach(b => b.classList.toggle('on', Math.abs(parseFloat(b.dataset.v) - v) < 1e-9)); quoteNow(); }
function openTokens(){
  if (!S.wallet){ connect(); return; }
  const list = S.tokens.filter(t => t.raw > 0);
  const back = S.product;
  sheet('Pay with', `<div class="ax-sheet-b">${list.length ? `
    <p style="font-size:14px">Any token here can pay. Anything that is not USDC is swapped for exactly what the invoice needs.</p>
    <div class="ax-list-opts">${list.map(t => `<button class="ax-pick ${t.mint === S.payMint ? 'on' : ''}" data-m="${esc(t.mint)}">
      <span class="ax-ic">${t.icon ? `<img src="${esc(t.icon)}" alt="">` : esc((t.symbol || '').slice(0, 4))}</span>
      <span class="ax-pick-t"><b>${esc(t.symbol || short(t.mint))}</b><small>${tok(t.amount, t.decimals)}</small></span>
      <span class="ax-pick-v">${t.value_usd != null ? money(t.value_usd) : ''}</span></button>`).join('')}</div>`
    : '<div class="ax-empty"><b>This wallet is empty</b>There is nothing in it to pay with.</div>'}</div>`);
  $$('#sheet .ax-pick').forEach(b => b.onclick = () => { S.payMint = b.dataset.m; openProduct(back); });
}
let qt;
function quoteNow(){
  clearTimeout(qt);
  const box = $('#quote'), c = S.product;
  if (!box) return;
  if (!validValue(c, S.value)){ box.innerHTML = '<div class="ax-note">Pick an amount this shop allows.</div>'; return; }
  box.innerHTML = '<div class="ax-rows"><div class="ax-row"><span>Working out the price…</span><span>–</span></div></div>';
  qt = setTimeout(async () => {
    const q = await J(`/api/quote?id=${encodeURIComponent(c.id)}&country=${encodeURIComponent(S.country)}&value=${S.value}&mint=${encodeURIComponent(S.payMint)}`);
    if (S.product !== c) return;
    S.quote = q; paintQuote(q);
  }, 450);
}
function paintQuote(q){
  const box = $('#quote'), c = S.product;
  if (!box) return;
  if (!q.ok){ box.innerHTML = `<div class="ax-note bad">${esc(q.error || 'Could not price this.')}</div>`; return; }
  if (q.total_usd == null){ box.innerHTML = `<div class="ax-note">This shop is priced in ${esc(q.product.currency)} and no exchange rate is available right now.</div>`; return; }
  const p = q.pay || {}, t = payToken(), err = p.error;
  const pay = S.payMint === USDC ? money(q.total_usd) : (p.route === 'price-estimate' ? '≈ ' : '') + tok(p.amount, p.decimals) + ' ' + (t && t.symbol || '');
  box.innerHTML = `
    <div class="ax-rows">
      <div class="ax-row"><span>Top-up</span><span>${money(q.face_value, c.currency)}</span></div>
      <div class="ax-row"><span>Price</span><span>${money(q.supplier_usd)}</span></div>
      <div class="ax-row"><span>Card fee · ${esc(q.markup_pct)}%</span><span>${money(q.fee_usd)}</span></div>
      <div class="ax-row big"><span>You pay</span><span>${err ? '–' : esc(pay)}</span></div>
    </div>
    ${err ? `<div class="ax-note bad" style="margin-top:12px">No route from that token right now: ${esc(err)}</div>` : ''}
    <button class="btn btn-light ax-block" style="margin-top:16px" id="pay" type="button" ${err ? 'disabled' : ''}>${S.wallet ? 'Pay ' + esc(pay) : 'Connect wallet to pay'}</button>
    <p class="ax-small" style="margin-top:10px">One signature. Your wallet pays the shop and the card fee in the same transaction. All sales are final, see the <a href="/docs#payments">terms</a>.${S.cfg && S.cfg.dry ? ' Test mode is on, so nothing leaves your wallet.' : ''}</p>`;
  $('#pay').onclick = startPay;
}
async function startPay(){
  if (!S.wallet){ if (await connect()) paintBuy(); return; }
  if (S.busy) return;
  const btn = $('#pay');
  const set = (t, d) => { if (btn){ btn.textContent = t; btn.disabled = !!d; } };
  S.busy = true;
  try {
    set('Getting an invoice…', true);
    const p = await post('/api/checkout/prepare', {wallet: S.wallet, product_id: S.product.id, country: S.country, value: S.value, mint: S.payMint});
    if (!p.ok) throw new Error(p.error);
    set('Confirm in your wallet…', true);
    const signed = await signAll(p.txs);
    set('Sending…', true);
    const r = await post('/api/checkout/send', {ref: p.ref, signed: signed.map(b64)});
    if (!r.ok) throw new Error(r.error);
    const all = store.get('fc.orders', []).filter(o => o.ref !== p.ref);
    all.unshift({ref: p.ref, name: S.product.name, value: S.value, currency: S.product.currency, country: S.country, at: Date.now()});
    store.set('fc.orders', all.slice(0, 100));
    openOrder(p.ref);
  } catch (e) {
    toast(/reject|cancel|denied/i.test(e.message || '') ? 'Cancelled in your wallet' : (e.message || 'Something went wrong'));
    if (S.quote) paintQuote(S.quote);
  } finally { S.busy = false; }
}

/* ------------------------------------------------------------ orders */
const CODE_LABEL = {code: 'Code', pin: 'PIN', card_number: 'Card number', cardNumber: 'Card number', serial: 'Serial',
                    claim_code: 'Claim code', voucher: 'Voucher', password: 'Password', account: 'Account'};
const CODE_HIDE = new Set(['link', 'url', 'other', 'extra_fields', 'instructions', 'redemption_url']);
function codeParts(info){
  if (!info) return {fields: [], link: null, note: null};
  if (typeof info === 'string') return {fields: [{label: 'Code', value: info}], link: null, note: null};
  const link = info.link || info.url || info.redemption_url || null, note = info.instructions || info.other || null, fields = [];
  const add = (k, v) => {
    if (v == null || v === '' || CODE_HIDE.has(k)) return;
    if (typeof v === 'object'){ Object.entries(v).forEach(([a, b]) => add(a, b)); return; }
    fields.push({label: CODE_LABEL[k] || k.replace(/[_-]/g, ' ').replace(/^./, x => x.toUpperCase()), value: String(v)});
  };
  const FIRST = ['code', 'card_number', 'cardNumber', 'claim_code', 'voucher', 'serial', 'pin', 'password'];
  const rank = k => { const i = FIRST.indexOf(k); return i < 0 ? FIRST.length : i; };
  Object.entries(info).sort((a, b) => rank(a[0]) - rank(b[0])).forEach(([k, v]) => add(k, v));
  return {fields, link, note};
}
async function openOrder(ref){
  sheet('Order', `<div class="ax-sheet-b"><div class="ax-steps"><div class="ax-step now"><i></i><div>Loading your order</div></div></div></div>`);
  const d = await J('/api/order?ref=' + encodeURIComponent(ref));
  if (!$('#sheet .ax-sheet') || $('#sheet').dataset.ref !== undefined && $('#sheet').dataset.ref !== ref) return;
  $('#sheet').dataset.ref = ref;
  if (!d.ok){ $('#sheet .ax-sheet-b').innerHTML = '<div class="ax-empty"><b>Order not found</b>Orders are kept for 30 days.</div>'; return; }
  const dry = d.dry || d.status === 'simulated', done = d.status === 'delivered' && d.code;
  const {fields, link, note} = codeParts(done ? d.code : null);
  const steps = [['Invoice created', true],
    [dry ? 'Payment simulated' : 'Payment sent', ['paid', 'simulated', 'delivered'].includes(d.status)],
    ['Balance issued', !!done]];
  const nowAt = steps.findIndex(s => !s[1]);
  $('#sheet .ax-sheet-b').innerHTML = `
    <div><div class="ax-label">${esc(d.country || '')} · ${esc(ref)}</div>
      <h2 style="font-size:32px;margin-top:10px">${esc(d.product || 'Order')}</h2>
      <p style="margin-top:8px">${money(d.value)} top-up</p></div>
    ${done ? fields.map(f => `<div class="ax-label">${esc(f.label)}</div><div class="ax-code">${esc(f.value)}</div>`).join('')
      + (link ? `<a class="btn btn-light ax-block" href="${esc(link)}" target="_blank" rel="noopener">Open the redemption page</a>` : '')
      + (note ? `<div class="ax-note">${esc(note)}</div>` : '') : ''}
    ${dry ? `<div class="ax-note ok">${esc(d.message || 'Test run finished. Nothing was sent.')}</div>` : ''}
    <div class="ax-steps">${steps.map(([t, ok], i) => `<div class="ax-step ${ok ? 'done' : (i === nowAt && !dry ? 'now' : '')}"><i></i><div>${esc(t)}</div></div>`).join('')}</div>
    <div class="ax-rows">
      <div class="ax-row"><span>Price</span><span>${money(d.invoice_usdc)} USDC</span></div>
      <div class="ax-row"><span>Card fee</span><span>${money(d.fee_usdc)} USDC</span></div>
      ${(d.signatures || []).map((s, i) => `<div class="ax-row"><span>Transaction ${i + 1}</span><span><a href="https://solscan.io/tx/${esc(s)}" target="_blank" rel="noopener" style="text-decoration:underline">${esc(short(s))}</a></span></div>`).join('')}
    </div>
    ${d.supplier_error ? `<div class="ax-note bad">${esc(d.supplier_error)}</div>` : ''}`;
  if (!done && !dry && d.status === 'paid') setTimeout(() => { if ($('#sheet').dataset.ref === ref && !$('#sheet').hidden) openOrder(ref); }, 4000);
}
function openOrders(){
  const all = store.get('fc.orders', []);
  sheet('Your orders', `<div class="ax-sheet-b">${all.length ? `<div class="ax-list-opts">${all.map(o => `
    <button class="ax-pick" data-r="${esc(o.ref)}"><span class="ax-pick-t"><b>${esc(o.name)}</b><small>${esc(new Date(o.at).toLocaleDateString())} · ${esc(o.country)}</small></span>
    <span class="ax-pick-v">${money(o.value, o.currency)}</span></button>`).join('')}</div>`
    : '<div class="ax-empty"><b>No orders yet</b>What you buy with your card shows up here.</div>'}</div>`);
  $$('#sheet .ax-pick').forEach(b => b.onclick = () => openOrder(b.dataset.r));
}

/* ------------------------------------------------------------ sheet */
function sheet(title, body){
  const w = $('#sheet');
  delete w.dataset.ref;
  w.innerHTML = `<div class="ax-sheet" role="dialog" aria-modal="true"><div class="ax-sheet-h"><b>${title}</b><button class="ax-x" type="button" aria-label="Close">${X}</button></div>${body}</div>`;
  w.hidden = false;
  requestAnimationFrame(() => w.classList.add('on'));
  w.querySelector('.ax-x').onclick = closeSheet;
  w.onclick = e => { if (e.target === w) closeSheet(); };
  document.body.style.overflow = 'hidden';
}
function closeSheet(){
  const w = $('#sheet');
  w.classList.remove('on');
  document.body.style.overflow = '';
  setTimeout(() => { if (!w.classList.contains('on')){ w.hidden = true; w.innerHTML = ''; } }, 450);
}
addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#sheet').hidden) closeSheet(); });

/* ------------------------------------------------------------ physical */
let physDone = false;
async function paintPhys(){
  tilt($('.ax-phys'));
  if (physDone) return;
  const box = $('#phys');
  await loadCfg();
  const list = S.cfg.countries || [];
  const here = guessCountry(list);
  const saved = store.get('fc.phys.draft', {});
  const v = k => esc(saved[k] || '');
  box.innerHTML = `<form class="ax-form" id="pform" novalidate>
    <div class="ax-sec">Contact</div>
    <label class="ax-in" data-f="name"><span>Full name</span><input name="name" autocomplete="name" value="${v('name')}" required></label>
    <div class="two">
      <label class="ax-in" data-f="email"><span>Email</span><input name="email" type="email" autocomplete="email" value="${v('email')}" required></label>
      <label class="ax-in" data-f="phone"><span>Phone <em>(optional)</em></span><input name="phone" type="tel" autocomplete="tel" value="${v('phone')}"></label>
    </div>
    <div class="ax-sec">Delivery address</div>
    <label class="ax-in" data-f="line1"><span>Address</span><input name="line1" autocomplete="address-line1" value="${v('line1')}" required></label>
    <label class="ax-in" data-f="line2"><span>Apartment, floor <em>(optional)</em></span><input name="line2" autocomplete="address-line2" value="${v('line2')}"></label>
    <div class="two">
      <label class="ax-in" data-f="city"><span>City</span><input name="city" autocomplete="address-level2" value="${v('city')}" required></label>
      <label class="ax-in" data-f="postal"><span>Postal code</span><input name="postal" autocomplete="postal-code" value="${v('postal')}" required></label>
    </div>
    <div class="two">
      <label class="ax-in" data-f="region"><span>State or region <em>(optional)</em></span><input name="region" autocomplete="address-level1" value="${v('region')}"></label>
      <label class="ax-in" data-f="country"><span>Country</span><select name="country" autocomplete="country">
        ${list.filter(c => c.code !== 'XI').map(c => `<option value="${esc(c.code)}" ${c.code === (saved.country || here) ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>
    </div>
    <div class="ax-sec">Wallet</div>
    <div id="linked"></div>
    <button class="btn btn-light ax-block" type="submit" id="psend">Request card</button>
    <p class="ax-small">1% fee on every top-up to the card. We only use these details to send your card. By requesting you accept the <a href="/docs">terms</a>, including that delivery is not guaranteed.</p>
  </form>`;
  paintLinked();
  const f = $('#pform');
  f.oninput = () => store.set('fc.phys.draft', Object.fromEntries(new FormData(f)));
  f.onsubmit = sendPhys;
}
function paintLinked(){
  const l = $('#linked');
  if (!l) return;
  l.innerHTML = S.wallet
    ? `<div class="ax-linked"><span>Linked to ${esc(short(S.wallet))}</span></div>`
    : `<div class="ax-linked"><span>Link your wallet so you can top up the card from it</span><button type="button" id="plink">Connect wallet</button></div>`;
  const b = $('#plink'); if (b) b.onclick = connect;
}
async function sendPhys(e){
  e.preventDefault();
  const f = $('#pform'), data = Object.fromEntries(new FormData(f));
  $$('#pform .ax-in').forEach(x => x.classList.remove('err'));
  const miss = ['name', 'email', 'line1', 'city', 'postal', 'country'].filter(k => !String(data[k] || '').trim());
  if (!miss.length && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email)) miss.push('email');
  if (miss.length){
    miss.forEach(k => { const x = $(`#pform .ax-in[data-f="${k}"]`); if (x) x.classList.add('err'); });
    toast(miss.includes('email') && data.email ? 'Check your email address.' : 'Please fill in the highlighted fields.');
    return;
  }
  const b = $('#psend'); b.disabled = true; b.textContent = 'Sending…';
  const d = await post('/api/fomocard/physical', {...data, wallet: S.wallet || ''});
  if (!d.ok){
    b.disabled = false; b.textContent = 'Request card';
    if (d.field){ const x = $(`#pform .ax-in[data-f="${d.field}"]`); if (x) x.classList.add('err'); }
    toast(d.error || 'Could not send, try again.');
    return;
  }
  physDone = true;
  store.set('fc.phys.draft', {});
  $('#phys').innerHTML = `<div class="ax-done"><div class="ax-tick"></div><h2>Card requested</h2>
    <p>You will be contacted on email when your card is on the way.</p>
    <span class="ax-k">Request ${esc(d.id)}</span></div>`;
}

/* ------------------------------------------------------------ start */
tilt(document);
view();
(async () => {
  let pk = null;
  try { pk = sessionStorage.getItem('fc.w'); } catch (e) {}
  if (!pk) pk = (store.get('fc.me', null) || {}).wallet || null;
  if (!pk) return;
  // only reuse a session the wallet still trusts, silently
  await new Promise(r => setTimeout(r, 300));
  const w = phantom();
  if (!w) return;
  try { await w.features['standard:connect'].connect({silent: true}); } catch (e) { return; }
  if ((w.accounts || []).some(a => a.address === pk)) setWallet(pk);
  else { try { localStorage.removeItem('fc.me'); } catch (e) {} const m = $('#mypage'); if (m) m.hidden = true; }
})();
})();
