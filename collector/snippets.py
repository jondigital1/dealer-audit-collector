"""The page scripts, ported from the skill (scripts/chrome_snippets.js and references/04_capture.md) as they are.
They run in the page through Playwright's evaluate. Where the skill's snippet used top-level await, it is wrapped in
an async function. The skill's script-output workaround (hosts printed with spaces) is not needed here, since
Playwright returns what the page returns; hosts come back as plain hosts."""

# SEO META fields, after the page loads (keep the image counts from the homepage only)
SEO_META = """async () => {
  window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 2500));
  const im = [...document.images], md = document.querySelector('meta[name="description"]');
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  return { title: document.title, titleLen: document.title.length, meta: md ? md.content : '', metaLen: md ? md.content.length : 0,
    h: [1,2,3,4,5,6].map(i => document.querySelectorAll('h' + i).length),
    h1Visible: [...document.querySelectorAll('h1')].filter(vis).map(e => e.innerText.trim().slice(0, 120)),
    images: im.length, noAlt: im.filter(i => !(i.getAttribute('alt') || '').trim()).length,
    noTitle: im.filter(i => !(i.getAttribute('title') || '').trim()).length };
}"""

# Vehicle links on the SRP
SRP_LINKS = """() => {
  const inv = [...document.querySelectorAll('a[href*="/inventory/"]')].map(a => a.getAttribute('href'));
  return { links: inv.length, http: inv.filter(h => h.startsWith('http://')).length, example: inv.find(h => h.startsWith('http://')) || '' };
}"""

# Links on the VDP that leave the site
VDP_OFFSITE_LINKS = """() => [...document.querySelectorAll('a[href]')]
  .filter(a => (a.offsetWidth || a.offsetHeight) && /^https?:/.test(a.href) && new URL(a.href).host !== location.host)
  .map(a => ({ text: a.innerText.trim().slice(0, 40), host: new URL(a.href).host, target: a.target, href: a.href }))"""

# Every link in the main menu: the top item it sits under, its label, host and path (references/04_capture.md: read
# every link in the main menu with a script, then open each one with a real click or navigation)
MENU_LINKS = """() => {
  const nav = document.querySelector('nav, [role="navigation"], header') || document.body;
  const out = [];
  for (const a of nav.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('tel:') || href.startsWith('mailto:')) continue;
    let u; try { u = new URL(a.href); } catch (e) { continue; }
    const top = a.closest('li'); const topItem = top && top.parentElement && top.parentElement.closest('li');
    const topLabel = topItem ? (topItem.querySelector(':scope > a, :scope > span, :scope > button') || topItem).innerText.trim().split('\\n')[0].slice(0, 60) : '';
    out.push({ top: topLabel, label: a.innerText.trim().replace(/\\s+/g, ' ').slice(0, 80), host: u.host, path: u.pathname + (u.search ? '?' : ''), href: a.href, target: a.target });
  }
  const seen = new Set();
  return out.filter(l => { const k = l.href; if (seen.has(k)) return false; seen.add(k); return true; });
}"""

# Address, hours and phone text: header, footer, hours sidebars, tel: links and schema.org JSON-LD
CONTACT_TEXT = """() => {
  const text = sel => [...document.querySelectorAll(sel)].map(e => e.innerText.trim()).filter(Boolean);
  const tel = [...document.querySelectorAll('a[href^="tel:"]')].map(a => ({ text: a.innerText.trim().slice(0, 60), number: a.getAttribute('href').replace('tel:', '') }));
  const ld = [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean);
  const hoursBlocks = [...document.querySelectorAll('*')].filter(e => /hours/i.test(e.className + ' ' + e.id) && e.innerText && e.innerText.length < 2000 && e.innerText.length > 20)
    .slice(0, 6).map(e => ({ where: (e.id || e.className || '').toString().slice(0, 60), text: e.innerText.trim().slice(0, 1500) }));
  const special = [...document.querySelectorAll('*')].filter(e => /special hours/i.test(e.innerText || '') && e.innerText.length < 1500).slice(-1).map(e => e.innerText.trim());
  return { header: text('header').slice(0, 2).map(t => t.slice(0, 1500)), footer: text('footer').slice(0, 2).map(t => t.slice(0, 2000)), tel, ld, hoursBlocks, specialHours: special[0] || null };
}"""

# Blank-block candidates (references/04_capture.md, Empty spaces and special hours): elements at least 150 px tall
# and 300 px wide with no text and no img, picture, video or iframe inside, whose computed background-image is none
EMPTY_BLOCKS = """() => {
  const out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (r.height < 150 || r.width < 300) continue;
    if ((e.innerText || '').trim()) continue;
    if (e.querySelector('img, picture, video, iframe, svg, canvas')) continue;
    const cs = getComputedStyle(e);
    if (cs.backgroundImage !== 'none' || cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (['SCRIPT', 'STYLE', 'HTML', 'BODY', 'HEAD'].includes(e.tagName)) continue;
    out.push({ tag: e.tagName.toLowerCase(), id: e.id, cls: (e.className || '').toString().slice(0, 80), x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) });
  }
  // keep the outermost of nested candidates
  return out.filter((a, i) => !out.some((b, j) => j !== i && b.x <= a.x && b.y <= a.y && b.x + b.w >= a.x + a.w && b.y + b.h >= a.y + a.h && (b.w * b.h > a.w * a.h))).slice(0, 20);
}"""

# Home slider slides from the page source (each slide image's alt text), so none is missed while the carousel rotates
SLIDER_ALTS = """() => {
  const sliders = [...document.querySelectorAll('[class*="slider"], [class*="carousel"], [class*="hero"], [class*="slick"], [class*="swiper"]')];
  const imgs = new Map();
  for (const s of sliders) for (const i of s.querySelectorAll('img')) if (!imgs.has(i.currentSrc || i.src)) imgs.set(i.currentSrc || i.src, { alt: (i.getAttribute('alt') || '').trim(), src: i.currentSrc || i.src });
  return [...imgs.values()].slice(0, 30);
}"""

# The VDP's price stack and CTA stack, as the mobile template shows them: every element whose text looks like a price
# or a label beside one, in document order, and every visible button-like link
VDP_STACK = """() => {
  const money = /\\$\\s?\\d[\\d,]*(\\.\\d\\d)?/;
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const prices = [];
  for (const e of document.querySelectorAll('span, div, dd, dt, td, th, p, strong, b, li')) {
    if (!vis(e) || e.children.length > 3) continue;
    const t = (e.innerText || '').trim().replace(/\\s+/g, ' ');
    if (t.length > 80 || !money.test(t)) continue;
    const r = e.getBoundingClientRect();
    prices.push({ text: t, value: parseFloat(t.match(money)[0].replace(/[$,\\s]/g, '')), y: Math.round(r.top + scrollY), size: parseFloat(getComputedStyle(e).fontSize) });
  }
  const seen = new Set();
  const stack = prices.filter(p => { const k = p.text + '@' + p.y; if (seen.has(k)) return false; seen.add(k); return true; }).sort((a, b) => a.y - b.y).slice(0, 25);
  const ctas = [...document.querySelectorAll('a, button')].filter(vis).filter(e => /btn|button|cta/i.test(e.className) || e.tagName === 'BUTTON')
    .map(e => { let host = ''; try { host = e.href ? new URL(e.href).host : ''; } catch (x) {} const r = e.getBoundingClientRect();
      return { text: (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 50), host, href: e.href || '', y: Math.round(r.top + scrollY), tel: /^tel:/.test(e.getAttribute('href') || '') }; })
    .filter(c => c.text).slice(0, 40);
  return { prices: stack, ctas, host: location.host };
}"""

# Clear cookies and storage so a cookie-capped pop-up opens again on reload (references/04_capture.md)
CLEAR_STORAGE = """() => {
  for (const c of document.cookie.split(';')) { const n = c.split('=')[0].trim(); if (!n) continue;
    for (const d of [location.hostname, '.' + location.hostname, location.hostname.replace(/^www\\./, '.')]) document.cookie = n + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=' + d; }
  try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
  return true;
}"""

# Poll for a pop-up: any of the vendor selectors, or a fixed element that appears after load covering a third of the
# viewport. Returns seconds from navigation start and the load event's time.
POPUP_POLL = """async ({ selectors, maxMs }) => {
  const start = performance.now();
  const big = () => [...document.querySelectorAll('body *')].find(e => { const cs = getComputedStyle(e); if (cs.position !== 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect(); return r.width * r.height > innerWidth * innerHeight / 3 && e.innerText && e.innerText.trim().length > 0; });
  let hit = null;
  await new Promise(res => { const iv = setInterval(() => {
    for (const s of selectors) { try { const e = document.querySelector(s); if (e && (e.offsetWidth || e.offsetHeight)) { hit = { selector: s }; break; } } catch (x) {} }
    if (!hit) { const b = big(); if (b) hit = { selector: 'fixed:' + (b.id || b.className || b.tagName).toString().slice(0, 60) }; }
    if (hit) { clearInterval(iv); res(); } }, 100); setTimeout(() => { clearInterval(iv); res(); }, maxMs); });
  const nav = performance.getEntriesByType('navigation')[0];
  const gb = performance.getEntriesByType('resource').find(r => r.name.includes('cdn.gubagoo.io/gb1/'));
  return { hit, popupSec: hit ? +((performance.now()) / 1000).toFixed(1) : null, loadSec: nav ? +(nav.loadEventEnd / 1000).toFixed(1) : null,
    gubagooSec: gb ? +(gb.startTime / 1000).toFixed(1) : null,
    bouncex: (window.bouncex && window.bouncex.campaigns) ? Object.values(window.bouncex.campaigns).map(c => ({ id: c.id, name: c.name, delay: c.activation_delay, activations: c.activations })) : null };
}"""

# Read the LHR from the PageSpeed report page, if the page exposes it (the VM build confirms the accessor)
PSI_PAGE_LHR = """() => {
  const cand = [window.__LIGHTHOUSE_JSON__, window.__lhr, window.lhr];
  for (const c of cand) if (c && c.audits) return { found: true, lhr: c };
  return { found: false };
}"""

# The treemap tab: count the googletagmanager.com scripts (the skill's snippet)
TREEMAP_GTM = """() => {
  const nodes = (window.__treemapOptions && __treemapOptions.lhr.audits['script-treemap-data'].details.nodes) || [];
  return { count: nodes.filter(n => /googletagmanager\\.com/.test(n.name)).length, names: nodes.filter(n => /googletagmanager\\.com/.test(n.name)).map(n => n.name), total: nodes.length };
}"""

HIDE = """(sels) => { for (const s of sels) for (const e of document.querySelectorAll(s)) e.style.display = 'none'; return true; }"""
ZOOM = """(z) => { document.documentElement.style.zoom = String(z); return true; }"""
SCROLL_PASS = """async () => { const h = document.body.scrollHeight; for (let y = 0; y < h; y += 800) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 600)); return h; }"""
