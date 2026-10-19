/* seamless star tiles behind the page, as on fomofantasy */
(() => {
  function starTile(size, count, bright) {
    const c = document.createElement('canvas'); c.width = c.height = size;
    const g = c.getContext('2d'); if (!g) return null;
    for (let i = 0; i < count; i++) {
      const depth = Math.random(), r = depth < .8 ? .55 : depth < .96 ? .95 : 1.5, m = r + 1;
      g.globalAlpha = (.05 + depth * .26) * bright; g.fillStyle = depth > .96 ? '#cdd6ff' : '#ffffff';
      g.beginPath(); g.arc(m + Math.random() * (size - m * 2), m + Math.random() * (size - m * 2), r, 0, 6.283); g.fill();
    }
    return c.toDataURL('image/png');
  }
  const bg = document.getElementById('spacebg'); if (!bg) return;
  const a = starTile(520, 1180, .8), b = starTile(820, 900, .58); if (!a) return;
  bg.style.backgroundImage = `url(${a}),url(${b})`; bg.style.backgroundSize = '520px 520px,820px 820px';
})();
