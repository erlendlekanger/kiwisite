/* 3D-myntene paa STONKD-forsiden, tegnet i sanntid med three.js.

   Mynten er dreid (LatheGeometry) med en avrundet, hevet kant som paa den gamle
   siden. Flaten har dreid finish med ekte anisotropi, saa lyset trekker seg rundt
   sentrum slik det gjoer paa polert metall. Sidekanten er riflet. Logoen er hevet
   relieff, ekstrudert fra vektorformene i /assets/coins/shapes.json; par uten
   vektorlogo, og mottakere med profilbilde, faar et lakkert medaljong. STONKD-
   mynten er frostet glass med Stack-merket i emalje.

   To scener deler myntene: «How it works» (en mynt som foelger scrollingen og
   musen, og snur seg til et nytt motiv for hvert steg) og kvitteringen i
   launch-skjemaet (parmynten, mottakermynten og gebyrene som flyr mellom dem).
   Siden snakker med scenene gjennom hendelsen «pick» paa window. */
import * as THREE from 'three';

const SHAPES = await fetch('/assets/coins/shapes.json').then((r) => r.json()).catch(() => ({}));
const fine = matchMedia('(pointer: fine)').matches;
const DPR = Math.min(devicePixelRatio || 1, 2);

/* ------------------------------------------------------------- geometri (radius 1) */
const FIELD_R = 1.18 / 1.6, FACE_Z = 0.1 / 1.6;
const bodyGeo = new THREE.LatheGeometry([
  [0, .1], [1.18, .1], [1.195, .115], [1.22, .124], [1.245, .115], [1.26, .106], [1.29, .106],
  [1.32, .13], [1.36, .147], [1.5, .152], [1.565, .137], [1.595, .1], [1.6, .07],
  [1.6, -.07], [1.595, -.1], [1.565, -.137], [1.5, -.152], [1.36, -.147], [1.32, -.13], [1.29, -.106],
  [1.26, -.106], [1.245, -.115], [1.22, -.124], [1.195, -.115], [1.18, -.1], [0, -.1],
].map(([r, y]) => new THREE.Vector2(r / 1.6, y / 1.6)), 192);
const faceGeo = new THREE.CircleGeometry(FIELD_R, 128);
const edgeGeo = new THREE.CylinderGeometry(1.6015 / 1.6, 1.6015 / 1.6, 0.14 / 1.6, 256, 1, true);

/* ------------------------------------------------------------- teksturer */
function canvasTex(w, h, draw, srgb = false) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

/* Dreid finish: tette, konsentriske ringer i ruheten. */
const spunTex = canvasTex(1024, 1024, (g) => {
  g.fillStyle = '#6a6a6a';
  g.fillRect(0, 0, 1024, 1024);
  for (let r = 3; r < 512; r += 1.25) {
    g.strokeStyle = `rgba(${Math.random() > 0.5 ? '255,255,255' : '0,0,0'},${0.03 + Math.random() * 0.07})`;
    g.beginPath(); g.arc(512, 512, r, 0, Math.PI * 2); g.stroke();
  }
});

/* Retningen paa anisotropien: langs ringene (tangentialt), kodet i RG. */
const anisoTex = canvasTex(256, 256, (g, w, h) => {
  const img = g.createImageData(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const u = (x + 0.5) / w - 0.5, v = 1 - (y + 0.5) / h - 0.5;
      const l = Math.hypot(u, v) || 1;
      const i = (y * w + x) * 4;
      img.data[i] = (-v / l * 0.5 + 0.5) * 255;
      img.data[i + 1] = (u / l * 0.5 + 0.5) * 255;
      img.data[i + 2] = 255;
      img.data[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
});

/* Riflene i sidekanten. */
const reedTex = canvasTex(1024, 8, (g) => {
  for (let x = 0; x < 1024; x += 6) {
    const gr = g.createLinearGradient(x, 0, x + 6, 0);
    gr.addColorStop(0, '#000'); gr.addColorStop(0.5, '#fff'); gr.addColorStop(1, '#000');
    g.fillStyle = gr;
    g.fillRect(x, 0, 6, 8);
  }
});
reedTex.wrapS = reedTex.wrapT = THREE.RepeatWrapping;
reedTex.repeat.set(1.6, 1);

/* ------------------------------------------------------------- materialer */
const steel = (hex, o = {}) => new THREE.MeshPhysicalMaterial({ color: new THREE.Color(hex), metalness: 1, ...o });
const bodyMat = steel('#c9ccd0', { roughness: 0.26, clearcoat: 0.4, clearcoatRoughness: 0.2 });
const faceMat = steel('#bfc2c6', { roughness: 0.34, roughnessMap: spunTex, anisotropy: 0.75, anisotropyMap: anisoTex, clearcoat: 0.25, clearcoatRoughness: 0.3 });
const edgeMat = steel('#b9bcc0', { roughness: 0.28, bumpMap: reedTex, bumpScale: 2.2 });
const glyphSideMat = steel('#d6d8db', { roughness: 0.2, clearcoat: 0.7, clearcoatRoughness: 0.1 });

/* Frostet, blaatonet glass for STONKD-mynten. Lyset gjennom den hentes fra
   glorien bak myntene i scenen, saa glasset faar farge selv uten bakgrunn. */
const glass = (rough) => new THREE.MeshPhysicalMaterial({
  color: 0xffffff, metalness: 0, roughness: rough, transmission: 1, thickness: 0.4, ior: 1.5,
  attenuationColor: new THREE.Color('#52b9e2'), attenuationDistance: 0.55,
  clearcoat: 1, clearcoatRoughness: 0.04, specularIntensity: 1, envMapIntensity: 1.2,
});
const glassBody = glass(0.08);
const glassFace = glass(0.42);

const enamel = (hex) => new THREE.MeshPhysicalMaterial({
  color: new THREE.Color(hex), metalness: 0.1, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.04 });
const loader = new THREE.TextureLoader();
loader.setCrossOrigin('anonymous');

/* ------------------------------------------------------------- logoer */
const EXTRUDE = { depth: 0.022, bevelEnabled: true, bevelThickness: 0.012, bevelSize: 0.007, bevelSegments: 5, curveSegments: 10 };

/* Stack-merket: fem piller som tegner en S, samme maal som brand/build.py. */
const STACK = (() => {
  const H = 78, GAP = 28, W = 400, TALL = 5 * H + 4 * GAP, s = 1.08 / TALL;
  const ROWS = [[0.20, 1.00], [0.00, 0.45], [0.15, 0.85], [0.55, 1.00], [0.00, 0.80]];
  const COLS = ['#ccedf9', '#aee0f3', '#8fd3ee', '#70c6e8', '#52b9e2'];
  return ROWS.map(([a, b], i) => {
    const x0 = (a * W - W / 2) * s, y0 = (TALL / 2 - i * (H + GAP) - H) * s, w = (b - a) * W * s, r = H * s / 2;
    const sh = new THREE.Shape();
    sh.moveTo(x0 + r, y0); sh.lineTo(x0 + w - r, y0);
    sh.absarc(x0 + w - r, y0 + r, r, -Math.PI / 2, Math.PI / 2, false);
    sh.lineTo(x0 + r, y0 + 2 * r);
    sh.absarc(x0 + r, y0 + r, r, Math.PI / 2, Math.PI * 1.5, false);
    const m = enamel(COLS[i]);
    return { geo: new THREE.ExtrudeGeometry(sh, EXTRUDE), mats: [m, m] };
  });
})();

const glyphCache = new Map();
function glyph(name) {
  if (glyphCache.has(name)) return glyphCache.get(name);
  let parts = null;
  const spec = SHAPES[name];
  if (spec && spec.shapes && spec.shapes.length) {
    const shapes = spec.shapes.map((sh) => {
      const s = new THREE.Shape(sh.outer.map(([x, y]) => new THREE.Vector2(x, y)));
      sh.holes.forEach((h) => s.holes.push(new THREE.Path(h.map(([x, y]) => new THREE.Vector2(x, y)))));
      return s;
    });
    const geo = new THREE.ExtrudeGeometry(shapes, EXTRUDE);
    if (spec.mode === 'ink') {
      const t = loader.load('/assets/coins/' + name + '_ink.png');
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 8;
      t.repeat.set(0.5, 0.5);
      t.offset.set(0.5, 0.5);
      parts = [{ geo, mats: [new THREE.MeshPhysicalMaterial({ map: t, metalness: 0.1, roughness: 0.25, clearcoat: 1, clearcoatRoughness: 0.06 }), glyphSideMat] }];
    } else {
      const col = new THREE.Color(spec.color);
      const dark = col.getHSL({}).l < 0.3;
      const cap = dark ? steel(spec.color, { roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.08 }) : enamel(spec.color);
      parts = [{ geo, mats: [cap, cap] }];
    }
  }
  glyphCache.set(name, parts);
  return parts;
}

/* Medaljong: et bilde (parlogo eller profilbilde) under blank lakk. */
const medGeo = new THREE.CircleGeometry(0.62, 96);
const medRimGeo = new THREE.TorusGeometry(0.625, 0.018, 16, 128);
const medCache = new Map();
function medallion(url) {
  if (medCache.has(url)) return medCache.get(url);
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  g.fillStyle = '#0b1820';
  g.fillRect(0, 0, 512, 512);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  const mat = new THREE.MeshPhysicalMaterial({ map: t, metalness: 0.05, roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.05 });
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    const s = Math.max(512 / img.naturalWidth, 512 / img.naturalHeight);
    g.drawImage(img, 256 - img.naturalWidth * s / 2, 256 - img.naturalHeight * s / 2, img.naturalWidth * s, img.naturalHeight * s);
    t.needsUpdate = true;
  };
  img.src = url;
  medCache.set(url, mat);
  return mat;
}

function shadowed(m) { m.castShadow = true; m.receiveShadow = true; return m; }

/* Forsiden av en mynt. Noekkelen er et navn i SHAPES, «STONKD», eller «img:<url>». */
function face(key) {
  const g = new THREE.Group();
  if (key.startsWith('img:')) {
    const cap = new THREE.Mesh(medGeo, medallion(key.slice(4)));
    cap.position.z = FACE_Z + 0.012;
    const rim = new THREE.Mesh(medRimGeo, glyphSideMat);
    rim.position.z = FACE_Z + 0.008;
    g.add(shadowed(cap), shadowed(rim));
    return g;
  }
  const parts = key === 'STONKD' ? STACK : glyph(key);
  if (!parts) return face('STONKD');
  parts.forEach((p) => {
    const m = shadowed(new THREE.Mesh(p.geo, p.mats));
    m.position.z = FACE_Z;
    g.add(m);
  });
  return g;
}

/* Mynten: en ytre gruppe som glir mot maal, en indre som snurrer ved bytte. */
function coin(key, { glassy = false } = {}) {
  const outer = new THREE.Group();
  const spin = new THREE.Group();
  const body = shadowed(new THREE.Mesh(bodyGeo, glassy ? glassBody : bodyMat));
  body.rotation.x = Math.PI / 2;
  const edge = shadowed(new THREE.Mesh(edgeGeo, edgeMat));
  edge.rotation.x = Math.PI / 2;
  const f1 = shadowed(new THREE.Mesh(faceGeo, glassy ? glassFace : faceMat));
  f1.position.z = FACE_Z;
  spin.add(body, edge, f1);
  if (!glassy) {                       // glasset viser baksiden gjennom flaten, saa den faar ingen
    const f2 = shadowed(new THREE.Mesh(faceGeo, faceMat));
    f2.position.z = -FACE_Z;
    f2.rotation.y = Math.PI;
    const back = face('STONKD');
    back.rotation.y = Math.PI;
    spin.add(f2, back);
  }
  const front = face(key);
  spin.add(front);
  outer.add(spin);
  outer.scale.setScalar(0.0001);
  outer.userData = { spin, front, key, next: null, flip: 0 };
  return outer;
}

/* Bytter motiv med en hel omdreining; flaten byttes naar mynten staar paa kant. */
function setFace(c, key, animate = true) {
  const u = c.userData;
  if (u.key === key && !u.next) return;
  if (!animate || c.scale.x < 0.02) { swap(c, key); return; }
  u.next = key;
  u.flip = 0.0001;
}
function swap(c, key) {
  const u = c.userData;
  u.spin.remove(u.front);
  u.front = face(key);
  u.spin.add(u.front);
  u.key = key;
  u.next = null;
}
function stepFlip(c, dt) {
  const u = c.userData;
  if (!u.flip) return;
  u.flip = Math.min(1, u.flip + dt / 0.9);
  const e = 1 - Math.pow(1 - u.flip, 3);
  u.spin.rotation.y = e * Math.PI * 2;
  if (u.next && e > 0.25) swap(c, u.next);
  if (u.flip >= 1) { u.flip = 0; u.spin.rotation.y = 0; }
}

/* ------------------------------------------------------------- maal og gliding */
function mover() {
  const tgt = new Map();
  return {
    want(o, x, y, z, s, rx = 0, ry = 0, rz = 0) {
      let t = tgt.get(o);
      if (!t) { t = { p: new THREE.Vector3(x, y, z), s, r: new THREE.Vector3(rx, ry, rz) }; tgt.set(o, t); o.position.set(x, y, z); }
      t.p.set(x, y, z); t.s = s; t.r.set(rx, ry, rz);
    },
    glide(k) {
      tgt.forEach((t, o) => {
        o.position.lerp(t.p, k);
        const s = o.scale.x + (t.s - o.scale.x) * k;
        o.scale.setScalar(Math.max(0.0001, s));
        o.visible = s > 0.005;
        o.rotation.x += (t.r.x - o.rotation.x) * k;
        o.rotation.y += (t.r.y - o.rotation.y) * k;
        o.rotation.z += (t.r.z - o.rotation.z) * k;
      });
    },
  };
}
const smooth = (a, b, x) => { const t = THREE.MathUtils.clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

/* ------------------------------------------------------------- rendrer og studio */
function stage(canvas, { opaque = null, shadows = false, camZ = 11 } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: !opaque, powerPreference: 'high-performance' });
  renderer.setPixelRatio(DPR);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  if (opaque) renderer.setClearColor(opaque, 1); else renderer.setClearColor(0x000000, 0);
  renderer.shadowMap.enabled = shadows;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  /* Lyset er en produktfoto-rigg: brede og smale lysflater rundt mynten som
     metallet speiler, og et blaatt kantlys i STONKD-fargen. */
  const pmrem = new THREE.PMREMGenerator(renderer);
  const s = new THREE.Scene();
  s.background = new THREE.Color(0x000000);
  const panel = (form, color, intensity, pos, scale, rot) => {
    const geo = form === 'ring' ? new THREE.RingGeometry(0.3, 0.5, 64) : new THREE.PlaneGeometry(1, 1);
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      color: new THREE.Color(color).multiplyScalar(intensity), side: THREE.DoubleSide, toneMapped: false }));
    m.position.set(...pos);
    if (Array.isArray(scale)) m.scale.set(scale[0], scale[1], 1); else m.scale.setScalar(scale);
    if (rot) m.rotation.set(...rot); else m.lookAt(0, 0, 0);
    s.add(m);
  };
  panel('rect', '#ffffff', 3.2, [0, 5, 2], [10, 3], [Math.PI / 2.4, 0, 0]);
  panel('rect', '#ffffff', 2.4, [-5, 1, 1], [2, 8], [0, Math.PI / 2.2, 0]);
  panel('rect', '#52b9e2', 3.0, [5, 0, 1], [2, 8], [0, -Math.PI / 2.2, 0]);
  panel('rect', '#ffffff', 0.6, [0, -4, 3], [8, 1.5], [-Math.PI / 2.6, 0, 0]);
  panel('ring', '#ffffff', 1.4, [2, 2, 6], 2);
  panel('rect', '#cfe9f5', 0.35, [0, 0, 12], [14, 10]);
  panel('rect', '#ffffff', 1.6, [-3, 3.5, 9], [5, 2.5], [0, 0, -0.3]);
  panel('rect', '#8fd4f1', 0.9, [4, -3, 9], [4, 1.2], [0, 0, 0.4]);
  const env = pmrem.fromScene(s, 0, 0.1, 100).texture;

  const scene = new THREE.Scene();
  scene.environment = env;
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(3, 4, 6);
  if (shadows) {
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: 1, far: 30 });
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = 0.02;
    key.shadow.radius = 6;
  }
  scene.add(key, key.target, new THREE.HemisphereLight(0xffffff, 0x1a2630, 0.9));

  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 80);
  camera.position.set(0, 0, camZ);
  const st = { renderer, scene, camera, w: 1, h: 1, halfW: 1, halfH: 1, visible: true };
  const fit = () => {
    const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
    if (w === st.w && h === st.h) return;
    st.w = w; st.h = h;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    st.halfH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.position.z;
    st.halfW = st.halfH * camera.aspect;
  };
  new ResizeObserver(fit).observe(canvas);
  new IntersectionObserver(([e]) => { st.visible = e.isIntersecting; }, { rootMargin: '120px' }).observe(canvas);
  fit();
  return st;
}

/* Glorie bak myntene: en heldekkende flate som gaar fra blaatt i midten til sidens
   bakgrunnsfarge ute i kantene. Den er ugjennomsiktig med vilje, for glasset bryter
   bare ugjennomsiktige ting, og slik faar STONKD-mynten farge fra den. */
function backdrop(bg = '#050c10', color = '#1d5a75') {
  const t = canvasTex(1024, 1024, (g) => {
    g.fillStyle = bg;
    g.fillRect(0, 0, 1024, 1024);
    const gr = g.createRadialGradient(512, 512, 0, 512, 512, 330);
    gr.addColorStop(0, color);
    gr.addColorStop(0.45, '#0f3242');
    gr.addColorStop(1, bg);
    g.fillStyle = gr;
    g.fillRect(0, 0, 1024, 1024);
  }, true);
  return new THREE.Mesh(new THREE.PlaneGeometry(9, 9), new THREE.MeshBasicMaterial({ map: t, toneMapped: false }));
}

/* ------------------------------------------------------------- tilstand fra siden */
const DEFAULT_PAY = ['NVDAX', 'TSLAX', 'AMZNX'];
let pick = window.PICK || { pair: { symbol: 'APPLX', logo: '' }, kind: 'x', avatar: null, basket: [] };
const pairKey = (p) => (!p ? 'APPLX' : (p.symbol === 'SOL' || SHAPES[p.symbol]) ? p.symbol : p.logo ? 'img:' + p.logo : 'APPLX');
const whoKey = () => (pick.avatar && pick.kind !== 'holders' ? 'img:' + pick.avatar : 'R_' + pick.kind);
const payKeys = () => (pick.kind === 'holders' && pick.basket.length ? pick.basket.map(pairKey) : DEFAULT_PAY).slice(0, 3);

addEventListener('pick', (e) => { pick = e.detail; });   // foer scenene, saa de ser det nye valget

const pointer = { x: 0, y: 0, sx: 0, sy: 0 };
addEventListener('pointermove', (e) => {
  pointer.x = (e.clientX / innerWidth) * 2 - 1;
  pointer.y = -((e.clientY / innerHeight) * 2 - 1);
}, { passive: true });

const loops = [];

/* ============================================================= How it works
   Én mynt i fokus som staar fast mens stegene scroller forbi, vipper etter musen
   og snur seg til motivet for steget: STONKD-coinen med paret, gebyrene i par-
   tokenet, SOL, og til slutt mottakeren med aksjene holderne kan faa. */
function howStage() {
  const canvas = document.getElementById('hcanvas');
  const list = document.getElementById('hsteps');
  if (!canvas || !list) return;
  const st = stage(canvas, { opaque: 0x050c10 });
  const { scene } = st;
  const M = mover();
  const rig = new THREE.Group();
  scene.add(rig);
  const halo = backdrop();
  halo.position.z = -3;
  scene.add(halo);

  const main = coin('STONKD', { glassy: true });
  const pair = coin(pairKey(pick.pair));
  const sol = coin('SOL');
  const who = coin(whoKey());
  const fees = Array.from({ length: 7 }, () => coin(pairKey(pick.pair)));
  const pays = Array.from({ length: 3 }, (_, i) => coin(payKeys()[i] || DEFAULT_PAY[i]));
  rig.add(main, pair, sol, who, ...fees, ...pays);
  fees.forEach((c, i) => { c.userData.seed = i / fees.length; c.userData.x = ((i * 0.618) % 1) * 2 - 1; });

  let p = 0, step = 0;
  const steps = [...list.children];
  const measure = () => {
    const r = list.getBoundingClientRect();
    p = THREE.MathUtils.clamp((innerHeight * 0.5 - r.top) / r.height, 0, 0.999);
    const s = Math.floor(p * steps.length);
    if (s !== step) { step = s; }
    steps.forEach((el, i) => el.classList.toggle('on', i === step));
  };
  addEventListener('scroll', measure, { passive: true });
  addEventListener('resize', measure);
  measure();

  addEventListener('pick', () => {
    setFace(pair, pairKey(pick.pair));
    fees.forEach((c) => setFace(c, pairKey(pick.pair), false));
    setFace(who, whoKey());
    pays.forEach((c, i) => setFace(c, payKeys()[i] || DEFAULT_PAY[i]));
  });

  loops.push((time, dt) => {
    if (!st.visible) return;
    const k = Math.min(1, st.halfW / 2.1);      // smal skjerm: alt litt mindre
    const bob = (i) => Math.sin(time * 0.8 + i * 1.7) * 0.07;
    const sway = (i, a = 0.22) => Math.sin(time * 0.5 + i * 2.3) * a;
    const on = (i) => step === i;

    // steg 1: STONKD-coinen foran, paret bak
    M.want(main, on(0) ? -0.55 * k : -2.6 * k, on(0) ? 0.1 + bob(0) : 1.6, on(0) ? 0 : -3, on(0) ? 1.3 * k : 0, 0, 0.28 + sway(0), 0);
    const pairPos = on(0) ? [1.25 * k, 0.45 + bob(1), -1.3, 0.95 * k, -0.4 + sway(1)]
      : on(1) ? [0, 0.35 + bob(1), 0, 1.25 * k, sway(1)]
        : on(2) ? [-2.3 * k, 1.5, -3.2, 0.55 * k, 0.5]
          : [-2.6 * k, 2, -4, 0, 0];
    M.want(pair, pairPos[0], pairPos[1], pairPos[2], pairPos[3], 0, pairPos[4], 0);

    // steg 2: gebyrmynter faller forbi parmynten; steg 3: de trekkes inn i SOL
    fees.forEach((c, i) => {
      const t = (time * 0.22 + c.userData.seed) % 1;
      if (on(1)) {
        const x = c.userData.x * 2.3 * k, y = 2.9 - t * 5.8, z = 0.9 + (i % 3) * 0.35;
        const fade = smooth(0, 0.12, t) * (1 - smooth(0.85, 1, t));
        M.want(c, x, y, z, 0.42 * k * fade, time * 1.3 + i, time * 1.9 + i * 2, 0.3);
      } else if (on(2)) {
        const a = c.userData.seed * Math.PI * 2 + time * 0.4, r = (1 - t) * 2.7 * k;
        M.want(c, Math.cos(a) * r, 0.2 + Math.sin(a) * r * 0.6, 0.7 + (1 - t) * 0.6, 0.38 * k * (1 - smooth(0.75, 1, t)) * smooth(0, 0.1, t), 0.4, time * 2 + i, 0);
      } else {
        M.want(c, c.userData.x * 2 * k, 3.4, 0.5, 0, 0, 0, 0);
      }
    });

    M.want(sol, on(2) ? 0 : on(3) ? -1.55 * k : 0, on(2) ? 0.2 + bob(2) : on(3) ? 0.15 * k + bob(2) : -2.8,
      on(3) ? 0.4 : 0, on(2) ? 1.25 * k : on(3) ? 0.5 * k : 0, 0, on(3) ? 0.5 + sway(2) : sway(2), 0);

    // steg 4: mottakeren i midten, aksjene holderne kan faa i en bue under
    M.want(who, on(3) ? 0.15 * k : 1.8 * k, on(3) ? 0.6 * k + bob(3) : 2.6, on(3) ? 0 : -3, on(3) ? 1.05 * k : 0, 0, -0.15 + sway(3), 0);
    pays.forEach((c, i) => {
      const x = (i - 1) * 1.15 * k + 0.15 * k, y = -1.5 * k + Math.abs(i - 1) * 0.14 * k + bob(i + 5) * 0.5;
      M.want(c, x, on(3) ? y : -3.4, on(3) ? 0.7 : 0, on(3) ? 0.5 * k : 0, 0.15, -0.3 + sway(i + 4, 0.35), (i - 1) * -0.08);
    });

    pointer.sx += (pointer.x - pointer.sx) * Math.min(1, dt * 3);
    pointer.sy += (pointer.y - pointer.sy) * Math.min(1, dt * 3);
    rig.rotation.y = fine ? pointer.sx * 0.42 : Math.sin(time * 0.3) * 0.15;
    rig.rotation.x = fine ? -pointer.sy * 0.22 : 0;

    M.glide(1 - Math.exp(-dt * 5));
    [main, pair, sol, who, ...fees, ...pays].forEach((c) => stepFlip(c, dt));
    st.renderer.render(scene, st.camera);
  });
}

/* ============================================================= kvitteringen
   Parmynten til venstre, mottakeren til hoeyre, og gebyrene som smaa mynter i en
   lysende bue mellom dem. */
function receiptStage() {
  const canvas = document.getElementById('rcanvas');
  if (!canvas) return;
  const st = stage(canvas, { camZ: 7 });
  const { scene } = st;
  const M = mover();
  const pair = coin(pairKey(pick.pair));
  const who = coin(whoKey());
  const fees = Array.from({ length: 4 }, () => coin(pairKey(pick.pair)));
  scene.add(pair, who, ...fees);

  /* Buen: et lysende roer med pulser som gaar fra paret til mottakeren. */
  const beamMat = (radius, base, pulse) => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { time: { value: 0 }, color: { value: new THREE.Color('#8fd4f1') }, base: { value: base }, pulse: { value: pulse } },
    vertexShader: `varying vec2 vUv; varying vec3 vN; varying vec3 vV;
      void main() { vUv = uv; vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform float time; uniform vec3 color; uniform float base; uniform float pulse;
      varying vec2 vUv; varying vec3 vN; varying vec3 vV;
      void main() {
        float rim = pow(max(dot(vN, vV), 0.0), 1.5);
        float ends = smoothstep(0.0, 0.08, vUv.x) * smoothstep(1.0, 0.92, vUv.x);
        float p = fract(vUv.x * 2.5 - time * 0.55);
        float pul = smoothstep(0.0, 0.35, p) * smoothstep(0.55, 0.35, p);
        float a = (base + pulse * pul) * rim * ends;
        gl_FragColor = vec4(color * (0.6 + pul * 0.8), a);
      }`,
  });
  let curve = null, tube = null, haze = null;
  const core = beamMat(0, 0.55, 1.4), soft = beamMat(0, 0.12, 0.35);
  const build = (L, R, H) => {
    curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(-L + R * 0.8, 0.05, 0.1), new THREE.Vector3(0, H * 0.75, 0.9), new THREE.Vector3(L - R * 0.8, 0.05, 0.1));
    [tube, haze].forEach((m) => { if (m) { scene.remove(m); m.geometry.dispose(); } });
    tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 160, 0.022, 12), core);
    haze = new THREE.Mesh(new THREE.TubeGeometry(curve, 160, 0.09, 16), soft);
    scene.add(haze, tube);
  };
  let builtFor = 0;

  addEventListener('pick', () => {
    setFace(pair, pairKey(pick.pair));
    fees.forEach((c) => setFace(c, pairKey(pick.pair), false));
    setFace(who, whoKey());
  });

  const local = { x: 0, y: 0 };
  canvas.closest('.receipt')?.addEventListener('pointermove', (e) => {
    const r = canvas.getBoundingClientRect();
    local.x = THREE.MathUtils.clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1);
    local.y = THREE.MathUtils.clamp(-(((e.clientY - r.top) / r.height) * 2 - 1), -1, 1);
  });

  loops.push((time, dt) => {
    if (!st.visible) return;
    const R = Math.min(1.25, st.halfH * 0.74);
    const L = st.halfW - R * 1.14 - 0.12;            // plass til kanten naar mynten er vridd
    if (Math.abs(L - builtFor) > 0.01) { build(L, R, st.halfH); builtFor = L; }
    core.uniforms.time.value = soft.uniforms.time.value = time;
    const bob = (i) => Math.sin(time * 0.9 + i * 2) * 0.05;
    M.want(pair, -L, bob(0), 0, R, -local.y * 0.25, 0.38 + local.x * 0.35, 0);
    M.want(who, L, bob(1), 0, R, -local.y * 0.25, -0.38 + local.x * 0.35, 0);
    fees.forEach((c, i) => {
      const t = (time * 0.32 + i / fees.length) % 1;
      const pt = curve.getPoint(t);
      const s = Math.sin(Math.PI * t);
      c.position.copy(pt);
      c.scale.setScalar(Math.max(0.0001, 0.26 * R * s));
      c.rotation.set(0.2, time * 3 + i, 0.1);
      c.visible = s > 0.02;
    });
    M.glide(1 - Math.exp(-dt * 6));
    [pair, who, ...fees].forEach((c) => stepFlip(c, dt));
    st.renderer.render(scene, st.camera);
  });
  canvas.closest('.rstage')?.classList.add('gl');
}

/* ------------------------------------------------------------- oppstart */
try { howStage(); } catch (e) { console.warn('how stage', e); }
try { receiptStage(); } catch (e) { console.warn('receipt stage', e); }

const clock = new THREE.Clock();
let time = 0;
(function frame() {
  const dt = Math.min(0.05, clock.getDelta());
  time += dt;
  loops.forEach((f) => f(time, dt));
  requestAnimationFrame(frame);
})();
