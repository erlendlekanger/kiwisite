// FOMOCARD landing, two WebGL scenes laid out like moto-card.com:
//   .earth  pinned for 2.5 screens (no pin spacing), so the next section slides over it.
//           The night-side globe turns, shrinks and fades as it scrolls.
//   .card   a transparent 2.5-screen section that scrolls up over the earth. Its canvas
//           sticks to the viewport; the card rises in, turns 1.5 times to face you, and a tube
//           of shop gift cards circles it and travels upward with the scroll.
// Timings follow moto-card.com's own ScrollTrigger settings, in viewport heights.
import * as THREE from "three";
import { RoomEnvironment } from "./vendor/env/RoomEnvironment.js";

const { gsap, ScrollTrigger, Lenis } = window;
gsap.registerPlugin(ScrollTrigger);

const isMobile = matchMedia("(pointer: coarse)").matches;
const DPR = Math.min(window.devicePixelRatio, isMobile ? 1.5 : 2);
const loader = new THREE.TextureLoader();
const mouse = { x: 0, y: 0 };
addEventListener("pointermove", (e) => {
  mouse.x = e.clientX / innerWidth - 0.5;
  mouse.y = e.clientY / innerHeight - 0.5;
});

function makeRenderer(canvas, exposure, transparent = false) {
  const r = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: transparent, premultipliedAlpha: true });
  r.setPixelRatio(DPR);
  r.setClearColor(0x080808, transparent ? 0 : 1);
  r.toneMapping = THREE.ACESFilmicToneMapping;
  r.toneMappingExposure = exposure;
  return r;
}
// every texture, so the warm-up below can wait for all of them
const texReady = [];
function tex(renderer, url, srgb = true, onLoad) {
  let done;
  texReady.push(new Promise((r) => (done = r)));
  const fin = () => { done(); if (onLoad) onLoad(); };
  const t = loader.load(url, fin, undefined, fin);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return t;
}

// ============================================================ EARTH
const earthCanvas = document.getElementById("earth-canvas");
const eR = makeRenderer(earthCanvas, 1.16);
const eScene = new THREE.Scene();
const eCam = new THREE.PerspectiveCamera(25, 1, 0.1, 100);
eCam.position.set(0, 0.2, 5);
const SUN = new THREE.Vector3(0.26, 1.39, -3).normalize();
const eU = {
  uDay: { value: tex(eR, "assets/earth_day.jpg") },
  uNight: { value: tex(eR, "assets/earth_night.jpg") },
  uClouds: { value: tex(eR, "assets/earth_clouds.jpg", false) },
  uSun: { value: SUN },
  uDayAtmo: { value: new THREE.Color("#a3afbd") },
  uTwilight: { value: new THREE.Color("#47649e") },
  uOpacity: { value: 1 },
};
const earthVert = /* glsl */ `
  varying vec2 vUv; varying vec3 vN; varying vec3 vP;
  void main() {
    vUv = uv;
    vN = normalize(mat3(modelMatrix) * normal);
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vP = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }`;
const sphere = new THREE.SphereGeometry(1, 96, 96);
const globe = new THREE.Mesh(sphere, new THREE.ShaderMaterial({
  uniforms: eU, transparent: true, vertexShader: earthVert,
  fragmentShader: /* glsl */ `
    uniform sampler2D uDay, uNight, uClouds;
    uniform vec3 uSun, uDayAtmo, uTwilight; uniform float uOpacity;
    varying vec2 vUv; varying vec3 vN; varying vec3 vP;
    void main() {
      vec3 n = normalize(vN);
      vec3 v = normalize(cameraPosition - vP);
      float sunO = dot(n, uSun);
      vec4 brc = texture2D(uClouds, vUv);           // r: bump, g: roughness, b: clouds
      float cloud = smoothstep(0.2, 1.0, brc.b);
      vec3 day = mix(texture2D(uDay, vUv).rgb, vec3(1.0), clamp(cloud * 2.0, 0.0, 1.0));
      float lit = max(sunO, 0.0);
      vec3 h = normalize(uSun + v);
      float spec = pow(max(dot(n, h), 0.0), 60.0) * (1.0 - brc.g) * (1.0 - cloud) * lit;
      vec3 dayCol = day * (0.04 + 1.25 * lit) + spec * 0.8;
      vec3 night = texture2D(uNight, vUv).rgb * 1.6 * (1.0 - cloud * 0.8);
      vec3 col = mix(night, dayCol, smoothstep(-0.25, 0.5, sunO));
      float fres = 1.0 - abs(dot(v, n));
      vec3 atmo = mix(uTwilight, uDayAtmo, smoothstep(-0.25, 0.75, sunO));
      float reach = smoothstep(-0.0525, 0.2475, n.y);
      col = mix(col, atmo, clamp(smoothstep(-0.5, 1.0, sunO) * fres * fres * reach, 0.0, 1.0));
      gl_FragColor = vec4(col, uOpacity);
    }`,
}));
const atmosphere = new THREE.Mesh(sphere, new THREE.ShaderMaterial({
  uniforms: eU, side: THREE.BackSide, transparent: true, depthWrite: false, vertexShader: earthVert,
  fragmentShader: /* glsl */ `
    uniform vec3 uSun, uDayAtmo, uTwilight; uniform float uOpacity;
    varying vec3 vN; varying vec3 vP;
    void main() {
      vec3 n = normalize(vN);
      vec3 v = normalize(cameraPosition - vP);
      float fres = 1.0 - abs(dot(v, n));
      float sunO = dot(n, uSun);
      float a = pow(clamp(1.0 - (fres - 0.73) / 0.27, 0.0, 1.0), 3.0);
      a *= smoothstep(-0.5, 1.0, sunO) * smoothstep(-0.0525, 0.2475, n.y);
      vec3 atmo = mix(uTwilight, uDayAtmo, smoothstep(-0.25, 0.75, sunO));
      gl_FragColor = vec4(atmo, a * uOpacity);
    }`,
}));
atmosphere.scale.setScalar(1.04);
const earthGroup = new THREE.Group();
earthGroup.add(globe, atmosphere);
earthGroup.position.set(0, -1.32, 0);
const EARTH_SCALE = 1.3;
earthGroup.scale.setScalar(EARTH_SCALE);
eScene.add(earthGroup);
const ES = { rotY: -Math.PI / 1.4, scale: EARTH_SCALE };

// ============================================================ CARD + TUBE
const cardCanvas = document.getElementById("card-canvas");
// transparent: the card rises through the planet, which stays visible underneath
const cR = makeRenderer(cardCanvas, 1.0, true);
const cScene = new THREE.Scene();
const cCam = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
cCam.position.set(0, 0, 6.5);
const pmrem = new THREE.PMREMGenerator(cR);
cScene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
cScene.environmentIntensity = 0.35;

// tube of the shops' own gift cards, faint behind the FOMOCARD
const BRAND_COUNT = 45;
const TILE_OPACITY = 0.28;
const TUBE = { rows: 12, cols: 16, radius: 11.2, tileW: 2.4, tileH: 2.4 * 54 / 85.6, ySpacing: 2.45, travel: 13, baseSpeed: 0.08 };
const tube = new THREE.Group();
const tileMats = [];
const tileTextures = [];
const tilePromises = [];
for (let i = 0; i < BRAND_COUNT; i++) {
  tilePromises.push(new Promise((res) => tileTextures.push(tex(cR, `assets/brands/${String(i).padStart(2, "0")}.png`, true, res))));
}
const tileGeo = new THREE.PlaneGeometry(TUBE.tileW, TUBE.tileH);
const rows = [];
for (let r = 0; r < TUBE.rows; r++) {
  const row = new THREE.Group();
  row.position.y = (r - (TUBE.rows - 1) / 2) * TUBE.ySpacing;
  for (let c = 0; c < TUBE.cols; c++) {
    const m = new THREE.MeshBasicMaterial({ map: tileTextures[(r * 11 + c * 3) % BRAND_COUNT], color: 0x9a9a9a, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
    tileMats.push(m);
    const tile = new THREE.Mesh(tileGeo, m);
    const a = ((c + (r % 2) * 0.5) / TUBE.cols) * Math.PI * 2;
    tile.position.set(Math.sin(a) * TUBE.radius, 0, Math.cos(a) * TUBE.radius);
    tile.lookAt(0, 0, 0);
    row.add(tile);
  }
  const k = r % 5;
  row.userData.speed = (0.65 + 0.9 * (k / 4)) * (r % 2 ? -1 : 1);
  rows.push(row);
  tube.add(row);
}
cScene.add(tube);

// the card
const CARD_W = 2.8, CARD_H = 2.8 * 54 / 85.6, CARD_R = 0.11, CARD_T = 0.035;
function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}
const shape = roundedRect(CARD_W, CARD_H, CARD_R);
function faceGeometry() {
  const g = new THREE.ShapeGeometry(shape, 24);
  const p = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < p.count; i++) uv.setXY(i, (p.getX(i) + CARD_W / 2) / CARD_W, (p.getY(i) + CARD_H / 2) / CARD_H);
  return g;
}
// the print doubles as a bump map: logo and text sit engraved in the metal and catch
// the light on their edges, like a laser-etched metal card
const faceMat = (url) => {
  const bump = tex(cR, url, false);
  return new THREE.MeshPhysicalMaterial({
    map: tex(cR, url), bumpMap: bump, bumpScale: -2.2,
    metalness: 0.8, roughness: 0.26, clearcoat: 0.6, clearcoatRoughness: 0.08,
    clearcoatNormalMap: null, envMapIntensity: 1.6,
  });
};
const cardFrontMat = faceMat("assets/card_front.png?v=2");
const cardBackMat = faceMat("assets/card_back.png?v=2");
const cardBodyMat = new THREE.MeshPhysicalMaterial({ color: 0x0c0c0e, metalness: 0.9, roughness: 0.3 });
const cardEdgeMat = new THREE.MeshStandardMaterial({ color: 0x9aa0aa, metalness: 1, roughness: 0.25 });
const card = new THREE.Group();
const body = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: CARD_T, bevelEnabled: false, curveSegments: 24 }), [cardBodyMat, cardEdgeMat]);
body.position.z = -CARD_T / 2;
const front = new THREE.Mesh(faceGeometry(), cardFrontMat);
front.position.z = CARD_T / 2 + 0.0005;
const back = new THREE.Mesh(faceGeometry(), cardBackMat);
back.rotation.y = Math.PI;
back.position.z = -CARD_T / 2 - 0.0005;
card.add(body, front, back);
card.rotation.z = Math.PI / 2;   // hangs portrait, like moto's
const cardPivot = new THREE.Group();
cardPivot.add(card);
const CARD_Y = 0.31;
cardPivot.position.y = CARD_Y;
cScene.add(cardPivot);
const key = new THREE.DirectionalLight(0xffffff, 1.4);
key.position.set(2, 3, 5);
const rim = new THREE.DirectionalLight(0xbfd2ff, 1.2);
rim.position.set(-4, 1, -3);
cScene.add(key, rim);

// reflections: the tube of shop cards plus light strips, baked once and turned with the tube
const glossy = [cardFrontMat, cardBackMat, cardEdgeMat];
function bakeTubeEnv() {
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x050505);
  const copy = tube.clone(true);
  copy.position.y = 0;
  copy.traverse((o) => { if (o.isMesh) o.material = new THREE.MeshBasicMaterial({ map: o.material.map, transparent: true, side: THREE.DoubleSide }); });
  envScene.add(copy);
  const strip = new THREE.MeshBasicMaterial({ color: new THREE.Color(6, 6, 6) });
  for (const a of [0.4, 2.3, 4.1]) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 14), strip);
    m.position.set(Math.sin(a) * 9, 0, Math.cos(a) * 9);
    m.lookAt(0, 0, 0);
    envScene.add(m);
  }
  const env = pmrem.fromScene(envScene, 0.015).texture;
  for (const m of glossy) { m.envMap = env; m.needsUpdate = true; }
}
// WARM-UP. A WebGL scene is cheap to draw but expensive the first time: shaders
// compile and every texture is uploaded to the GPU on its first frame. Left alone,
// that happens the moment a section scrolls into view, which is the lag spike.
// So it all happens here, while the hero film is on screen and nothing is moving.
// The tube reflection is baked first because it changes the materials, and a
// changed material would compile again.
Promise.all(texReady).then(async () => {
  bakeTubeEnv();
  const upload = (r, t) => { if (t && t.isTexture) r.initTexture(t); };
  for (const [r, s, c] of [[eR, eScene, eCam], [cR, cScene, cCam]]) {
    s.traverse((o) => {
      for (const m of [].concat(o.material || [])) for (const k of ["map", "bumpMap", "envMap"]) upload(r, m[k]);
    });
    try { await r.compileAsync(s, c); } catch (e) { r.compile(s, c); }
  }
  for (const u of [eU.uDay, eU.uNight, eU.uClouds]) upload(eR, u.value);
  // one real frame of each scene, off screen, so the first visible frame has nothing left to do
  eR.render(eScene, eCam);
  cR.render(cScene, cCam);
});

// card-section animation state, driven by the scroll timeline below
const CS = { progress: 0.25, y: CARD_Y - 2, rotY: -1.5 * Math.PI, tubeAlpha: 0 };

// ============================================================ SCROLL (moto-card.com timings)
const lenis = new Lenis({ lerp: 0.09 });
lenis.on("scroll", ScrollTrigger.update);
gsap.ticker.add((t) => lenis.raf(t * 1000));
gsap.ticker.lagSmoothing(0);

// earth: pinned for 2.5 screens, the card section scrolls over it
const eTL = gsap.timeline({
  scrollTrigger: { trigger: ".earth", start: "top top", end: () => "+=" + 2.5 * innerHeight, pin: true, scrub: 1, pinSpacing: false, invalidateOnRefresh: true },
});
eTL.fromTo(ES, { rotY: -Math.PI / 1.4 }, { rotY: -Math.PI / 5, ease: "none", duration: 0.5 }, 0)
  .fromTo(ES, { scale: EARTH_SCALE }, { scale: 0.4 * EARTH_SCALE, duration: 0.9, ease: "power2.out" }, 0.1)
  .fromTo(eU.uOpacity, { value: 1 }, { value: 0, duration: 0.15, ease: "power2.out" }, 0.2)
  // slide the heading fully out of view, as moto's does, whatever its height
  .to(".earth-header", { y: () => { const h = document.querySelector(".earth-header"); return -(h.offsetTop + h.offsetHeight + 24); }, ease: "none", duration: 0.5 }, 0)
  .to(".earth-points li", { autoAlpha: 0, y: 24, duration: 0.25, stagger: { amount: 0.2, from: "random" }, ease: "none" }, 0)
  .set({}, {}, 1);

// card: from 10% above its top to 90% of its bottom
// opacity and transform only: an animated blur filter repaints the whole block every frame
gsap.set(".card-header", { opacity: 0, yPercent: 8 });
const cTL = gsap.timeline({
  scrollTrigger: { trigger: ".card", start: "top 10%", end: "bottom 90%", scrub: 1, invalidateOnRefresh: true },
});
cTL.to(CS, { progress: 1, ease: "none", duration: 1 }, 0)
  .fromTo(CS, { y: CARD_Y - 2 }, { y: CARD_Y, duration: 0.5, ease: "power3.out" }, 0)
  .fromTo(CS, { rotY: -1.5 * Math.PI }, { rotY: 0, duration: 0.7, ease: "power1.out" }, 0)
  .to(".card-header", { opacity: 1, yPercent: 0, duration: 0.2 }, 0.4)
  .fromTo(CS, { tubeAlpha: 0 }, { tubeAlpha: 1, duration: 0.2, ease: "none" }, 0.075);

// ============================================================ SCROLL CUE
// fades once the visitor has started scrolling; a click glides to the next section
const cue = document.querySelector(".scroll-cue");
if (cue) {
  lenis.on("scroll", ({ scroll }) => cue.classList.toggle("gone", scroll > 40));
  cue.addEventListener("click", (e) => { e.preventDefault(); lenis.scrollTo("#earth", { duration: 1.4 }); });
}

// ============================================================ HERO FILM
// intro once, then the seamless loop clip if one has been uploaded
const intro = document.getElementById("hero-intro");
const heroLoop = document.getElementById("hero-loop");
// same rule as the intro: 4K only where the screen has the pixels for it
const loopSrc = "assets/" + (Math.max(screen.width, screen.height) * (devicePixelRatio || 1) > 2600 ? "film_loop_4k.mp4" : "film_loop_2560.mp4");
fetch(loopSrc, { method: "HEAD" }).then((r) => {
  if (!r.ok) return;
  heroLoop.src = loopSrc;
  heroLoop.preload = "auto";
  intro.addEventListener("ended", () => {
    heroLoop.hidden = false;
    heroLoop.play().then(() => (intro.hidden = true)).catch(() => {});
  });
}).catch(() => {});

// ============================================================ LOOP
function sizeOf(canvas) {
  const b = canvas.getBoundingClientRect();
  return { w: Math.max(1, Math.round(b.width)), h: Math.max(1, Math.round(b.height)) };
}
// a phone's address bar fires resize while scrolling; reallocating the buffers for a
// size that has not changed is a spike, so only a real change does anything
function resize() {
  for (const [r, cam, cv] of [[eR, eCam, earthCanvas], [cR, cCam, cardCanvas]]) {
    const { w, h } = sizeOf(cv);
    if (cv.__w === w && cv.__h === h) continue;
    cv.__w = w; cv.__h = h;
    r.setSize(w, h, false);
    cam.aspect = w / h;
    cam.updateProjectionMatrix();
  }
  // narrow screens: pull back so the hanging card fits
  cCam.position.z = innerWidth / innerHeight < 0.8 ? 8.5 : 6.5;
}
resize();
addEventListener("resize", resize);

// visibility from an observer, not a getBoundingClientRect per frame: reading layout
// right after GSAP has written styles forces a full layout on every frame
const visible = new Map();
const io = new IntersectionObserver((es) => es.forEach((e) => visible.set(e.target, e.isIntersecting)), { rootMargin: "50px 0px" });
io.observe(earthCanvas);
io.observe(cardCanvas);
const onScreen = (el) => visible.get(el) === true;
const clock = new THREE.Clock();
let idle = 0;
function tick() {
  const dt = Math.min(clock.getDelta(), 0.05);

  if (onScreen(earthCanvas) && eU.uOpacity.value > 0.001) {
    earthGroup.rotation.y = ES.rotY + clock.elapsedTime * 0.025;
    earthGroup.scale.setScalar(ES.scale);
    eR.render(eScene, eCam);
  }

  if (onScreen(cardCanvas)) {
    idle += dt * TUBE.baseSpeed;
    tube.position.y = -TUBE.travel / 2 + CS.progress * TUBE.travel;
    rows.forEach((row) => (row.rotation.y = (idle + CS.progress * 1.2) * row.userData.speed));
    for (const m of tileMats) m.opacity = CS.tubeAlpha * TILE_OPACITY;
    cardPivot.position.y = CS.y;
    cardPivot.rotation.y = CS.rotY + mouse.x * 0.3;
    cardPivot.rotation.x = mouse.y * 0.15;
    const envRot = (idle + CS.progress * 1.2) * rows[0].userData.speed - cardPivot.rotation.y;
    for (const m of glossy) {
      m.envMapRotation.set(0, envRot, 0);
      m.envMapIntensity = 0.45 + 0.75 * CS.tubeAlpha;
    }
    cR.render(cScene, cCam);
  }
  requestAnimationFrame(tick);
}
window.__fomo = { CS, ES };
tick();
