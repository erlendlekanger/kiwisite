/* Stars with depth and a slow drift; parallax with the pointer. Shared by every page. */
(() => {
  const c = document.getElementById('space'); if (!c) return;
  const ctx = c.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let stars = [], W = 0, H = 0;
  const ptr = { x: 0.5, y: 0.5 };
  addEventListener('pointermove', (e) => { ptr.x = e.clientX / innerWidth; ptr.y = e.clientY / innerHeight; }, { passive: true });
  function size() {
    const dpr = Math.min(2, devicePixelRatio || 1);
    W = innerWidth; H = innerHeight; c.width = W * dpr; c.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round((W * H) / 6500);
    stars = Array.from({ length: n }, () => {
      const z = Math.random();
      return { x: Math.random() * W, y: Math.random() * H, z, r: z > 0.92 ? 1.6 : z > 0.6 ? 1 : 0.65, a: 0.25 + Math.random() * 0.65, w: Math.random() * 6.28, v: 0.4 + Math.random() * 0.9, col: Math.random() < 0.12 ? '#b9c2ff' : Math.random() < 0.06 ? '#ffe9c4' : '#e8ebff' };
    });
  }
  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    const px = (ptr.x - 0.5) * 22, py = (ptr.y - 0.5) * 22;
    for (const s of stars) {
      const tw = reduced ? 1 : 0.7 + 0.3 * Math.sin(t * s.v + s.w);
      const dx = reduced ? 0 : (t * 1.2 * s.z) % W;
      let x = s.x - dx - px * s.z, y = s.y - py * s.z;
      if (x < 0) x += W;
      ctx.globalAlpha = s.a * tw; ctx.fillStyle = s.col;
      ctx.beginPath(); ctx.arc(x, y, s.r, 0, 6.283); ctx.fill();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame((n) => draw(n / 1000));
  }
  size(); addEventListener('resize', size); requestAnimationFrame((n) => draw(n / 1000));
})();
