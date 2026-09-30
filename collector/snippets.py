"""The page scripts, ported from the skill (scripts/chrome_snippets.js and references/04_capture.md) as they are.
They run in the page through Playwright's evaluate. Where the skill's snippet used top-level await, it is wrapped in
an async function. The skill's script-output workaround (hosts printed with spaces) is not needed here, since
Playwright returns what the page returns; hosts come back as plain hosts."""

# SEO META fields, after the page loads (keep the image counts from the homepage only). The skill scrolls to the
# bottom first so lazy images load; headless, a single jump leaves lazy sections unloaded (Bay Hyundai read 54/27/53
# that way and 52/46/51 after a stepwise pass, the fixture's numbers), so the pass scrolls in steps first. A visible H1
# is one with a box bigger than the 1 px sr-only clip; the counts still include hidden ones, as the extension does.
SEO_META = """async () => {
  // 400 px steps at 300 ms: Hanania's model carousel loaded its 16 slides only at this pace (Sep 30, 2026); a faster
  // pass read 9 images without ALT where Chrome read 28
  const h = document.body.scrollHeight; for (let y = 0; y < h; y += 400) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 300)); }
  window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 3000)); window.scrollTo(0, 0);
  const all = [...document.images], md = document.querySelector('meta[name="description"]');
  // a Google map widget adds over a hundred tile images of its own (Bay Hyundai: 118); the counts keep the page's own
  // images, and the with-map counts sit beside them
  const inMap = i => !!i.closest('.gm-style, [class*="map-dynamic"], [class*="google-map"], [class*="googlemap"], [id*="google-map"], [class*="mapbox"], [class*="leaflet"]');
  const im = all.filter(i => !inMap(i));
  const cnt = arr => ({ images: arr.length, noAlt: arr.filter(i => !(i.getAttribute('alt') || '').trim()).length, noTitle: arr.filter(i => !(i.getAttribute('title') || '').trim()).length });
  // tracking pixels (zero or one px, or an ad or analytics host) are not photos: the flag's ALT-or-TITLE choice leaves them out
  const pixelHost = /adsrvr|bat\\.bing|facebook\\.com|doubleclick|googleadservices|google-analytics|googletagmanager|adroll|pixel|beacon|track|analytics|criteo|taboola|outbrain|quantserve|scorecardresearch|linkedin\\.com\\/px|snap\\.licdn|t\\.co\\/|1x1|spacer|blank\\.gif|transparent/i;
  const isPixel = i => { const r = i.getBoundingClientRect(); const src = i.currentSrc || i.src || ''; return (i.naturalWidth <= 1 && i.naturalHeight <= 1 && i.complete) || (r.width <= 1 && r.height <= 1) || pixelHost.test(src); };
  const pixels = im.filter(isPixel); const noAltPixels = pixels.filter(i => !(i.getAttribute('alt') || '').trim()).length, noTitlePixels = pixels.filter(i => !(i.getAttribute('title') || '').trim()).length;
  // carousels clone their slides and swap lazy images as they rotate, so a read's counts depend on the carousel's state
  const inCarousel = im.filter(i => i.closest('[class*="slick"], [class*="carousel"], [class*="slider"], [class*="swiper"]'));
  const cloned = im.filter(i => i.closest('.slick-cloned, [class*="clone"]'));
  const carousel = { images: inCarousel.length, noAlt: inCarousel.filter(i => !(i.getAttribute('alt') || '').trim()).length, cloned: cloned.length, clonedNoAlt: cloned.filter(i => !(i.getAttribute('alt') || '').trim()).length };
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && cs.opacity !== '0'; };
  return { title: document.title, titleLen: document.title.length, meta: md ? md.content : '', metaLen: md ? md.content.length : 0,
    h: [1,2,3,4,5,6].map(i => document.querySelectorAll('h' + i).length), withMap: all.length !== im.length ? cnt(all) : null, mapImages: all.length - im.length, carousel,
    pixels: { images: pixels.length, noAlt: noAltPixels, noTitle: noTitlePixels, srcs: pixels.slice(0, 8).map(i => (i.currentSrc || i.src || '').slice(0, 80)) },
    h1All: [...document.querySelectorAll('h1')].map(e => (e.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 120)),
    h1Visible: [...document.querySelectorAll('h1')].filter(vis).map(e => e.innerText.trim().replace(/\\s+/g, ' ').slice(0, 120)),
    images: im.length, noAlt: im.filter(i => !(i.getAttribute('alt') || '').trim()).length,
    noTitle: im.filter(i => !(i.getAttribute('title') || '').trim()).length };
}"""

# Vehicle links on the SRP: the skill's selector (a[href*="/inventory/"]) first; when it matches nothing, the platform's
# own VDP link pattern (Dealer.com links VDPs as /new/Make/... and /used/Make/..., the fixture's note), recorded as such
SRP_LINKS = """() => {
  const count = sel => { const inv = [...document.querySelectorAll(sel)].map(a => a.getAttribute('href') || '').filter(h => !/\\/index\\.htm|\\/specials|promotions|research|searchnew|searchused/i.test(h));
    return { selector: sel, links: inv.length, unique: new Set(inv.map(h => h.split('?')[0])).size, http: inv.filter(h => h.startsWith('http://')).length, example: inv.find(h => h.startsWith('http://')) || '' }; };
  const skill = count('a[href*="/inventory/"]');
  if (skill.links) return { ...skill, skill_selector_links: skill.links };
  for (const sel of ['a[href^="/new/"], a[href*="/new/"][href$=".htm"]', 'a[href*="/vehicle/"], a[href*="/vehicles/"]', 'a[href*="/vdp/"], a[href*="/detail"]', 'a[href*="vin="], a[href*="/vin/"]', 'a[href*="/new-"]']) {
    const c = count(sel); if (c.links) return { ...c, skill_selector_links: 0 }; }
  return { ...skill, skill_selector_links: 0 };
}"""

# Links on the VDP that leave the site
VDP_OFFSITE_LINKS = """() => [...document.querySelectorAll('a[href]')]
  .filter(a => (a.offsetWidth || a.offsetHeight) && /^https?:/.test(a.href) && new URL(a.href).host !== location.host)
  .map(a => ({ text: a.innerText.trim().slice(0, 40), host: new URL(a.href).host, target: a.target, href: a.href }))"""

# Every link in the main menu: the top item it sits under, its label, host and path (references/04_capture.md: read
# every link in the main menu with a script, then open each one with a real click or navigation)
MENU_LINKS = """() => {
  // every nav-like container: DealerOn keeps the dropdown links outside the header element (Natchez Nissan, Sep 30, 2026)
  const roots = [...document.querySelectorAll('nav, [role="navigation"], header, [id*="nav"], [class*="navbar"], ul[class*="nav"], [class*="main-menu"], [class*="mainmenu"], [class*="megamenu"], [class*="mega-menu"]')]
    .filter(r => !r.closest('footer, [class*="footer"]'));
  const anchors = []; const seenEl = new Set();
  for (const r of (roots.length ? roots : [document.body])) for (const a of r.querySelectorAll('a[href]')) { if (seenEl.has(a)) continue; seenEl.add(a); anchors.push(a); }
  const out = [];
  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('tel:') || href.startsWith('mailto:') || href === '?' || href === '/?' || href.startsWith('sms:')) continue;
    let u; try { u = new URL(a.href); } catch (e) { continue; }
    if (/google\\.com\\/maps|maps\\.google|maps\\.apple|bing\\.com\\/maps|goo\\.gl\\/maps/i.test(a.href)) continue;   // the header's map link is not a menu item
    if (/facebook\\.com|instagram\\.com|twitter\\.com|x\\.com\\/|youtube\\.com|tiktok\\.com|linkedin\\.com|yelp\\.com|pinterest\\.com/i.test(a.href)) continue;   // nor are the social icons
    const top = a.closest('li'); const topItem = top && top.parentElement && top.parentElement.closest('li');
    const topLabel = topItem ? (topItem.querySelector(':scope > a, :scope > span, :scope > button') || topItem).innerText.trim().split('\\n')[0].slice(0, 60) : '';
    // the label: the visible text, else the anchor's own text content (a menu item hidden behind an overflow entry
    // has no innerText while it is hidden), else its aria-label or title
    const label = (a.innerText.trim() || (a.textContent || '').trim() || a.getAttribute('aria-label') || a.getAttribute('title') || '').replace(/\\s+/g, ' ').slice(0, 80);
    out.push({ top: topLabel, label, host: u.host, path: u.pathname + (u.search ? '?' : ''), query: u.search ? u.search.slice(0, 60) : '', href: a.href, target: a.target });
  }
  const seen = new Set();
  return out.filter(l => { const k = l.href; if (seen.has(k)) return false; seen.add(k); return true; });
}"""

# Address, hours and phone text: header, footer, hours sidebars, tel: links and schema.org JSON-LD
CONTACT_TEXT = """() => {
  const text = sel => [...document.querySelectorAll(sel)].map(e => e.innerText.trim()).filter(Boolean);
  const tel = [...document.querySelectorAll('a[href^="tel:"]')].map(a => ({ text: a.innerText.trim().slice(0, 60), number: a.getAttribute('href').replace('tel:', '') }));
  const ld = [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean);
  const heading = e => { const own = e.querySelector('h1,h2,h3,h4,h5,h6,[class*="title"],[class*="heading"]'); if (own && own.innerText.trim()) return own.innerText.trim().slice(0, 60);
    for (let p = e.previousElementSibling; p; p = p.previousElementSibling) { const t = (p.innerText || '').trim(); if (t) return t.slice(0, 60); }
    for (let p = e.parentElement, n = 0; p && n < 3; p = p.parentElement, n++) { const hd = [...p.querySelectorAll('h1,h2,h3,h4,h5,h6')].find(h => /hours/i.test(h.innerText)); if (hd) return hd.innerText.trim().slice(0, 60); } return null; };
  const hoursBlocks = [...document.querySelectorAll('*')].filter(e => /hours/i.test(e.className + ' ' + e.id) && e.innerText && e.innerText.length < 2000 && e.innerText.length > 20 && /am|pm|closed/i.test(e.innerText))
    .filter((e, i, arr) => !arr.some(o => o !== e && o.contains(e) && /hours/i.test(o.className + ' ' + o.id) && o.innerText.length < 2000))
    .slice(0, 6).map(e => ({ where: (e.id || e.className || '').toString().slice(0, 60), heading: heading(e), text: e.innerText.trim().slice(0, 1500) }));
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
    // media elements are content, not blank space: a loaded image is a photo, an iframe is a widget; an img that never
    // loaded is reported separately below as a broken image
    if (['SCRIPT', 'STYLE', 'HTML', 'BODY', 'HEAD', 'IMG', 'PICTURE', 'VIDEO', 'IFRAME', 'SVG', 'CANVAS', 'OBJECT', 'EMBED', 'TABLE', 'COLGROUP', 'COL', 'THEAD', 'TBODY', 'TR', 'TD', 'TH', 'SOURCE'].includes(e.tagName)) continue;
    const cs = getComputedStyle(e);
    if (cs.backgroundImage !== 'none' || cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0' || cs.position === 'fixed') continue;
    // a link card, or any block, whose own children carry the picture as a background image is not blank; a block wrapping
    // an iframe or a table is a widget or a schedule
    if (e.querySelector('iframe, table, object, embed')) continue;
    let pictured = false; for (const d of [...e.querySelectorAll('*')].slice(0, 40)) { const ds = getComputedStyle(d); if (ds.backgroundImage !== 'none' && ds.backgroundImage !== '' ) { pictured = true; break; } } if (pictured) continue;
    if (e.tagName === 'A' || e.closest('a')) continue;
    if (r.left + scrollX < 0 || r.left + scrollX > document.documentElement.scrollWidth) continue;
    if (e.closest('.gm-style, [class*="map"], [id*="map"]')) continue;
    out.push({ tag: e.tagName.toLowerCase(), id: e.id, cls: (e.className || '').toString().slice(0, 80), x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) });
  }
  // keep the outermost of nested candidates, and drop repeats of the same box
  const seen = new Set();
  return out.filter((a, i) => !out.some((b, j) => j !== i && b.x <= a.x && b.y <= a.y && b.x + b.w >= a.x + a.w && b.y + b.h >= a.y + a.h && (b.w * b.h > a.w * a.h)))
            .filter(a => { const k = a.x + ',' + a.y + ',' + a.w + ',' + a.h; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 12);
}"""

# Images that never loaded (a broken src or a lazy image the scroll pass did not trigger), at least 150 x 300, so a
# blank photo block that is an img element is on record too
BROKEN_IMAGES = """() => [...document.images].filter(i => { const r = i.getBoundingClientRect(); return r.width >= 300 && r.height >= 150 && i.complete && i.naturalWidth === 0; })
  .map(i => { const r = i.getBoundingClientRect(); return { src: (i.currentSrc || i.src || i.getAttribute('data-src') || '').slice(0, 160), alt: (i.getAttribute('alt') || '').slice(0, 80), x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) }; }).slice(0, 12)"""

# Home slider slides from the page source (each slide image's alt text), so none is missed while the carousel rotates
SLIDER_ALTS = """() => {
  const sliders = [...document.querySelectorAll('[class*="slider"], [class*="carousel"], [class*="hero"], [class*="slick"], [class*="swiper"]')];
  const imgs = new Map();
  for (const s of sliders) for (const i of s.querySelectorAll('img')) if (!imgs.has(i.currentSrc || i.src)) imgs.set(i.currentSrc || i.src, { alt: (i.getAttribute('alt') || '').trim(), src: i.currentSrc || i.src });
  return [...imgs.values()].slice(0, 30);
}"""

# The VDP's price stack and CTA stack. Every element whose text is a dollar figure, with its label (the dt or the short
# ancestor text around it: MSRP, Doc Fee, Bay Price), nested duplicates dropped; the stack is the cluster of labeled
# prices around the first one, the biggest by font size marked; the CTAs are the button-like links in and just under
# that block, the media toolbar (Track Price, Save, Share, Compare) left out; every button on the page is kept too.
VDP_STACK = """() => {
  const money = /-?\\$\\s?\\d[\\d,]*(\\.\\d\\d)?/;
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
  const raw = [];
  for (const e of document.querySelectorAll('span, div, dd, dt, td, th, p, strong, b, li, h1, h2, h3, h4')) {
    if (!vis(e) || e.children.length > 3) continue;
    const t = clean(e.innerText);
    if (t.length > 80 || !money.test(t)) continue;
    const r = e.getBoundingClientRect();
    let label = t.replace(money, '').replace(/[:|]/g, '').trim();
    if (!label) { // the label beside the figure: a previous sibling (a dt before its dd) of the element or of its ancestors, else the short ancestor text around it
      for (let a = e, n = 0; a && n < 4 && !label; a = a.parentElement, n++) { const prev = a.previousElementSibling; if (prev && clean(prev.innerText) && clean(prev.innerText).length < 40 && !money.test(prev.innerText)) label = clean(prev.innerText); }
      if (!label) { let p = e.parentElement; for (let n = 0; p && n < 3 && !label; p = p.parentElement, n++) { const pt = clean(p.innerText); if (pt.length < 80 && pt.includes(t)) { const rest = pt.replace(t, '').trim(); if (rest && !money.test(rest)) label = rest; } } } }
    raw.push({ text: t, label: label.slice(0, 40), value: parseFloat(t.match(money)[0].replace(/[$,\\s]/g, '')), negative: /^-/.test(t.match(money)[0]), y: Math.round(r.top + scrollY), x: Math.round(r.left), size: parseFloat(getComputedStyle(e).fontSize), weight: getComputedStyle(e).fontWeight });
  }
  raw.sort((a, b) => a.y - b.y || a.x - b.x);
  // one entry per figure: the same value within 14 px is one row (DealerOn prints "MSRP: $51,805" and its inner
  // "$51,805" span); the innermost carries the price's own font size, the outer the label
  const prices = [];
  for (const p of raw) { const g = prices.find(q => q.value === p.value && Math.abs(q.y - p.y) < 14); if (!g) { prices.push({ ...p }); continue; }
    if (p.text.length < g.text.length) { g.size = p.size; g.weight = p.weight; g.text = p.text; } if (!g.label && p.label) g.label = p.label; if (p.label && p.label.length > (g.label || '').length && !money.test(p.label)) g.label = p.label; }
  const labeled = prices.filter(p => /price|msrp|fee|discount|savings|rebate|payment|total|offer|cash|retail|invoice|sale/i.test(p.label));
  let stack = [];
  if (labeled.length) { const top = labeled[0].y; stack = prices.filter(p => p.y >= top - 40 && p.y <= top + 700); }
  else stack = prices.slice(0, 8);
  const selling = /price|selling|internet|sale|final|e-?price|retail/i, notSelling = /msrp|fee|discount|savings|rebate|payment|\\/mo|month|apr|down|cash|bonus|loyalty|grad|military/i;
  let big = null; for (const p of stack) { if (!big || p.size > big.size) { big = p; continue; }
    if (p.size === big.size) { const ps = selling.test(p.label) && !notSelling.test(p.label), bs = selling.test(big.label) && !notSelling.test(big.label); if (ps && !bs) big = p; else if (ps === bs && p.value > big.value) big = p; } }
  const tied = stack.filter(p => big && p !== big && p.size === big.size);
  for (const p of stack) { p.biggest = p === big; if (p === big && tied.length) p.size_tie_with = tied.map(t => t.label || t.text).slice(0, 3); }
  const isCta = e => /btn|button|cta/i.test(e.className) || e.tagName === 'BUTTON' || (e.getAttribute('role') === 'button');
  const buttons = [...document.querySelectorAll('a, button, [role="button"]')].filter(vis).filter(isCta).map(e => { let host = ''; try { host = e.href ? new URL(e.href).host : ''; } catch (x) {} const r = e.getBoundingClientRect();
      return { text: clean(e.innerText).slice(0, 50), host, href: (e.href || '').slice(0, 200), y: Math.round(r.top + scrollY), h: Math.round(r.height), tel: /^tel:/.test(e.getAttribute('href') || ''), target: e.target || '' }; })
    .filter(c => c.text || c.tel);
  const seenB = new Set(); const all = buttons.filter(b => { const k = b.text + '@' + b.y; if (seenB.has(k)) return false; seenB.add(k); return true; });
  let ctas = [];
  const priceLabels = new Set(stack.map(p => (p.label || '').toLowerCase()).filter(Boolean));
  if (stack.length) { const top = Math.min(...stack.map(p => p.y)), bot = Math.max(...stack.map(p => p.y)); ctas = all.filter(b => b.y >= top - 120 && b.y <= bot + 650 && !/track price|^save$|^share$|compare|window sticker|full specs|^details$|highlights|full review|load more|photos?$|^ext\\.?$|^int\\.?$/i.test(b.text) && !priceLabels.has(b.text.toLowerCase()) && !money.test(b.text)); }
  // tel links hidden on desktop but in the same template (Call Now shows only on a phone)
  const hiddenTel = [...document.querySelectorAll('a[href^="tel:"]')].filter(e => !vis(e)).map(e => ({ text: clean(e.innerText).slice(0, 40), number: (e.getAttribute('href') || '').replace('tel:', '') })).slice(0, 6);
  return { prices: stack, other_prices: prices.filter(p => !stack.includes(p)).slice(0, 12), ctas, buttons_all: all.slice(0, 60), hidden_tel: hiddenTel, host: location.host };
}"""

# The VDP in a phone-sized layout (412 x 823, a mobile Chrome user agent), the same template PageSpeed renders: where
# the price stack and the CTA stack sit (one swipe is one full screen of 823 px), what covers the page on load (a
# vendor overlay or any fixed element over a third of the screen), whether the ComplyAuto panel shows, whether a
# promotion banner takes the top of the first screen, and the header's tel link.
VDP_MOBILE = """({ priceTexts, ctaTexts, popupSelectors }) => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
  const H = innerHeight, W = innerWidth;
  const firstY = (texts, sel) => { let best = null; for (const e of document.querySelectorAll(sel)) { if (!vis(e)) continue; const t = clean(e.innerText); if (!t || t.length > 80) continue;
      if (texts.some(x => x && t === x)) { const y = Math.round(e.getBoundingClientRect().top + scrollY); if (best === null || y < best) best = y; } } return best; };
  const priceY = firstY(priceTexts, 'span, div, dd, dt, td, p, strong, b, li');
  const ctaY = firstY(ctaTexts, 'a, button, [role="button"]');
  const ctaYs = ctaTexts.map(t => firstY([t], 'a, button, [role="button"]')).filter(y => y !== null);
  const priceYs = priceTexts.map(t => firstY([t], 'span, div, dd, dt, td, p, strong, b, li')).filter(y => y !== null);
  const fixed = [...document.querySelectorAll('body *')].filter(e => { const cs = getComputedStyle(e); if (cs.position !== 'fixed' || !vis(e) || cs.opacity === '0') return false; if (/\\bcollapse\\b/.test(e.className || '') && !/\\b(show|in|open)\\b/.test(e.className || '')) return false;
      const r = e.getBoundingClientRect(); const ix = Math.max(0, Math.min(r.right, W) - Math.max(r.left, 0)), iy = Math.max(0, Math.min(r.bottom, H) - Math.max(r.top, 0)); return ix * iy > W * H / 3 && clean(e.innerText).length > 0; })
    .map(e => ({ id: e.id, cls: (e.className || '').toString().slice(0, 60), text: clean(e.innerText).slice(0, 120), h: Math.round(e.getBoundingClientRect().height) }));
  const vendor = popupSelectors.map(s => { try { const e = document.querySelector(s); return e && vis(e) ? { selector: s, text: clean(e.innerText).slice(0, 100) } : null; } catch (x) { return null; } }).filter(Boolean);
  const comply = [...document.querySelectorAll('body *')].find(e => vis(e) && /Your Privacy/i.test(e.innerText || '') && /ComplyAuto/i.test(e.innerText || '') && e.getBoundingClientRect().height > 150 && e.innerText.length < 1500);
  const topText = [...document.querySelectorAll('body *')].filter(e => vis(e) && e.children.length < 4 && e.getBoundingClientRect().top + scrollY < H / 3).map(e => clean(e.innerText)).filter(Boolean).join(' | ').slice(0, 800);
  const tel = [...document.querySelectorAll('a[href^="tel:"]')].filter(vis).map(e => ({ text: clean(e.innerText).slice(0, 40), number: (e.getAttribute('href') || '').replace('tel:', ''), y: Math.round(e.getBoundingClientRect().top + scrollY) })).slice(0, 8);
  return { priceY, ctaY, priceBottom: priceYs.length ? Math.max(...priceYs) : null, ctaBottom: ctaYs.length ? Math.max(...ctaYs) : null, fixed, vendor, complyauto: comply ? clean(comply.innerText).slice(0, 120) : null, topText, tel, docHeight: document.documentElement.scrollHeight, screen: [W, H] };
}"""

# The vehicle photo currently showing in the VDP's gallery: the visible image nearest the frame's center
VDP_PHOTO = """() => { const isBig = i => { const r = i.getBoundingClientRect(); return r.width >= 300 && r.height >= 180 && r.top + scrollY < 2200; };
  let imgs = [...document.querySelectorAll('img')].filter(i => isBig(i) && i.closest('[id*="carousel"], [class*="carousel"], [class*="gallery"], [class*="media"], [class*="slider"], [class*="photo"], [class*="swiper"], [class*="slick"]'));
  if (!imgs.length) imgs = [...document.querySelectorAll('img')].filter(i => isBig(i) && !i.closest('header, nav, footer'));
  if (!imgs.length) return null; const cx = innerWidth / 2; const area = i => i.getBoundingClientRect().width * i.getBoundingClientRect().height; const big = Math.max(...imgs.map(area));
  const top = imgs.filter(i => area(i) >= big * 0.6); top.sort((a, b) => Math.abs((a.getBoundingClientRect().left + a.getBoundingClientRect().right) / 2 - cx) - Math.abs((b.getBoundingClientRect().left + b.getBoundingClientRect().right) / 2 - cx)); imgs.splice(0, imgs.length, ...top);
  const r = imgs[0].getBoundingClientRect(); return { x: Math.max(0, r.left + scrollX), y: r.top + scrollY, w: Math.min(r.width, innerWidth - Math.max(0, r.left)), h: r.height, src: (imgs[0].currentSrc || imgs[0].src || '').slice(0, 160), alt: (imgs[0].getAttribute('alt') || '').slice(0, 80) }; }"""

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
  // a fixed element that covers a third of the viewport and is actually on screen (a collapsed off-canvas menu drawer
  // is fixed and tall but sits outside the frame: Natchez Nissan's vertical-navbar-collapse, Sep 30, 2026)
  const big = () => [...document.querySelectorAll('body *')].find(e => { const cs = getComputedStyle(e); if (cs.position !== 'fixed' || cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return false;
    if (/\\bcollapse\\b/.test(e.className || '') && !/\\b(show|in|open)\\b/.test(e.className || '')) return false;
    const r = e.getBoundingClientRect(); const ix = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)), iy = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    return ix * iy > innerWidth * innerHeight / 3 && e.innerText && e.innerText.trim().length > 0; });
  let hit = null;
  await new Promise(res => { const iv = setInterval(() => {
    // a vendor element counts once it is a pop-up, not a launcher icon: at least 150 x 150 or carrying text (Gubagoo's
    // .gg-chat-wrapper is a 64 px icon first and the 300 x 364 invite a few seconds later)
    for (const s of selectors) { try { const e = document.querySelector(s); if (!e) continue; const r = e.getBoundingClientRect(); const t = (e.innerText || '').trim();
      if ((r.width >= 150 && r.height >= 150) || (r.width > 0 && t.length > 0)) { hit = { selector: s, w: Math.round(r.width), h: Math.round(r.height), text: t.slice(0, 200) }; break; } } catch (x) {} }
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

# Registered before any page script runs: the LCP entries of the collector's own load, so the element the page paints
# largest (a hero image or a pop-up's image) is on record with its source labeled. Not PageSpeed's LCP; a second source.
LCP_OBSERVER = """(() => { try { window.__lcpEntries = []; new PerformanceObserver(list => { for (const e of list.getEntries()) { const el = e.element;
  window.__lcpEntries.push({ t: Math.round(e.startTime), size: e.size, tag: el ? el.tagName : null, id: el ? el.id : null, cls: el ? (el.className || '').toString().slice(0, 80) : null,
    src: el && (el.currentSrc || el.src) ? (el.currentSrc || el.src).slice(0, 160) : null, text: el ? (el.innerText || '').trim().slice(0, 80) : null }); } }).observe({ type: 'largest-contentful-paint', buffered: true }); } catch (e) {} })()"""
LCP_READ = """() => (window.__lcpEntries || []).slice(-1)[0] || null"""

# Which pop-up and chat vendors' scripts loaded on the page, whether or not anything rendered
VENDOR_SCRIPTS = """() => { const names = { gubagoo: 'Gubagoo', podium: 'Podium', bouncex: 'Wunderkind', wunderkind: 'Wunderkind', dealerbluesky: 'dealerbluesky', tecobi: 'Tecobi', complyauto: 'ComplyAuto', dealeron: 'DealerOn', carnow: 'CarNow', conversica: 'Conversica', 'livechat': 'LiveChat', 'drift': 'Drift', 'intercom': 'Intercom', 'activengage': 'ActivEngage', 'fullpath': 'Fullpath', 'roadster': 'Roadster', 'foureyes': 'Foureyes' };
  const urls = performance.getEntriesByType('resource').map(r => r.name.toLowerCase()).join(' ') + ' ' + [...document.scripts].map(s => (s.src || '').toLowerCase()).join(' ');
  return [...new Set(Object.keys(names).filter(k => urls.includes(k)).map(k => names[k]))]; }"""

# Specials cards: the largest group of repeated, same-shaped blocks on the page that carry an image (or a background
# image) and some text; each card's title, price text and image presence. Also how much text the page's own content
# holds outside the header and footer, so an empty page (Bay Hyundai's Accessory Specials: no heading, no offers,
# only the contact sidebar) shows as one.
SPECIALS_CARDS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width >= 200 && r.width <= 760 && r.height >= 120 && r.height <= 1000; };
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
  const money = /\\$\\s?\\d[\\d,]*(\\.\\d\\d)?(\\s?\\/\\s?mo)?|\\d+(\\.\\d+)?%\\s?(APR|off)/i;
  const groups = {};
  for (const e of document.querySelectorAll('body *')) {
    if (!vis(e) || e.closest('header, footer, nav, .page-header, [class*="footer"], [class*="map"]')) continue;
    const t = clean(e.innerText); if (t.length < 8 || t.length > 700) continue;
    const hasImg = !!e.querySelector('img, picture') || getComputedStyle(e).backgroundImage !== 'none';
    if (!hasImg) continue;
    const k = e.tagName + '.' + (e.className || '').toString().trim().split(/\\s+/).slice(0, 2).join('.') + '>' + (e.parentElement ? e.parentElement.tagName + '.' + (e.parentElement.className || '').toString().trim().split(/\\s+/)[0] : '');
    (groups[k] = groups[k] || []).push(e);
  }
  const best = Object.entries(groups).filter(([k, v]) => v.length >= 2).sort((a, b) => b[1].length - a[1].length)[0];
  const cards = best ? best[1].slice(0, 30).map(e => { const h = e.querySelector('h1,h2,h3,h4,h5,h6,strong,[class*="title"],[class*="heading"]'); const t = clean(e.innerText);
      return { title: clean(h ? h.innerText : t.split(/[.|]/)[0]).slice(0, 100), price_text: (t.match(money) || [''])[0], has_image: !!e.querySelector('img[src], img[data-src], picture'), text: t.slice(0, 200) }; }) : [];
  const main = document.querySelector('main, [role="main"], #main, .main-content') || document.body;
  let mainText = clean(main.innerText); for (const x of main.querySelectorAll('header, footer, nav, .page-header, [class*="footer"], [class*="sidebar"], [class*="map"]')) mainText = mainText.replace(clean(x.innerText), '');
  const h1 = document.querySelector('h1'); const imgs = [...document.images].filter(i => !i.closest('header, footer, nav, .page-header, [class*="footer"], [class*="map"]') && i.getBoundingClientRect().width > 80).length;
  return { cards, card_group: best ? best[0] : null, main_text_chars: mainText.length, h1: h1 ? clean(h1.innerText).slice(0, 120) : null, content_images: imgs };
}"""

# A Dealership Info sidebar (Dealer Inspire's finance and service pages carry one with the phones, hours and any
# special hours): its text, so holiday hours in it are on record even when the block never says "Special Hours"
DEALERSHIP_INFO = """() => { const e = [...document.querySelectorAll('body *')].find(x => /^(Dealership|Dealer|Store) Info/i.test((x.innerText || '').trim().slice(0, 30)) && x.innerText.length < 2500 && x.getBoundingClientRect().width > 150);
  if (!e) return null; const r = e.getBoundingClientRect(); return { text: e.innerText.trim(), x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; }"""

# Menu geometry for the hover shot: the item's anchor (by label, or by href when it has none), its top-level entry,
# and the nav's visible top-level entries that have children (an overflow entry like "More"), each with its box
MENU_GEOMETRY = """([label, href, top]) => {
  const box = e => { const r = e.getBoundingClientRect(); return { cx: r.left + r.width / 2, cy: r.top + r.height / 2, w: r.width, h: r.height, visible: r.width > 0 && r.height > 0 && r.top >= 0 && r.top < innerHeight }; };
  const anchors = [...document.querySelectorAll('nav a, header a, [class*="nav"] a, [class*="menu"] a')];
  const clean = t => (t || '').trim().replace(/\\s+/g, ' ');
  const pick = list => list.find(a => box(a).visible) || list[0] || null;
  const items = anchors.filter(a => label ? clean(a.innerText) === label : (href && a.href === href));
  const tops = anchors.filter(a => top && clean(a.innerText) === top);
  const navs = [...document.querySelectorAll('nav > ul, nav ul.nav, [class*="menu"] > ul')];
  const overflow = [];
  for (const ul of navs) for (const li of ul.children) { if (li.tagName !== 'LI') continue; const b = box(li); if (!b.visible) continue; if (/has-children|dropdown|overflow|more|parent/i.test(li.className || '') || li.querySelector('ul')) overflow.push(b); }
  return { item: items.length ? box(pick(items)) : null, top: tops.length ? box(pick(tops)) : null, overflow };
}"""

MENU_OUTLINE = """([label, href]) => { for (const a of document.querySelectorAll('a')) { a.style.outline = ''; a.style.outlineOffset = ''; }
  if (!label && !href) return; for (const a of document.querySelectorAll('nav a, header a, [class*="nav"] a, [class*="menu"] a')) { const r = a.getBoundingClientRect(); if (r.width === 0) continue;
    if ((label && a.innerText.trim() === label) || (!label && a.href === href)) { a.style.outline = '3px solid #D93025'; a.style.outlineOffset = '2px'; } } }"""

# The next priced vehicle card on the SRP after a given VDP (the swap rule when a VDP will not render)
NEXT_VEHICLE = """(skipHref) => {
  const money = /\\$\\s?\\d[\\d,]{3,}/;
  const sels = 'a[href*="/new/"], a[href*="/inventory/"], a[href*="/vehicle"], a[href*="/vdp"], a[href*="vin="], a[href*="/detail"], a[href*="/new-"]';
  const skip = (skipHref || '').split('?')[0]; let passed = false; const seen = new Set();
  for (const a of document.querySelectorAll(sels)) {
    const h = a.href.split('?')[0]; if (/specials|promotions|research|inventory\\/index|new-inventory\\/index/i.test(a.getAttribute('href') || '')) continue;
    if (h === skip) { passed = true; continue; }
    if (!passed || seen.has(h)) continue; seen.add(h);
    let c = a, hops = 0;
    while (c && c !== document.body && hops < 8) { const t = (c.innerText || ''); if (money.test(t) && t.length < 2500) return { href: a.href, text: t.trim().replace(/\\s+/g, ' ').slice(0, 220) }; c = c.parentElement; hops++; }
  }
  return null;
}"""

# Expand collapsed hours panels (Service Hours, Parts Hours, See All Department Hours: read-only toggles), then give the
# smallest block that holds every hours schedule, so the hours capture shows all three
EXPAND_HOURS = """() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let clicked = 0;
  for (const e of document.querySelectorAll('button, a, h2, h3, h4, h5, [role="button"], [role="tab"], [aria-expanded], [class*="accordion"] > *, [class*="collapse"] > *, [class*="toggle"]')) {
    const t = (e.innerText || '').trim(); if (!vis(e) || t.length > 60) continue;
    if (/^(service|parts|sales|showroom|dealership)?\\s*(department\\s*)?hours$|see all department hours|all department hours|service hours|parts hours/i.test(t)) {
      const exp = e.getAttribute('aria-expanded'); const collapsed = exp === 'false' || /collapsed/.test(e.className || '') || (e.parentElement && /collapsed/.test(e.parentElement.className || ''));
      if (exp === 'true') continue; try { e.click(); clicked++; } catch (x) {} } }
  return clicked; }"""

HOURS_UNION = """() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 40 && r.height > 20; };
  const blocks = [...document.querySelectorAll('*')].filter(e => vis(e) && /hours/i.test(e.className + ' ' + e.id) && e.innerText && e.innerText.length > 20 && e.innerText.length < 2500 && /am|pm|closed/i.test(e.innerText))
    .filter((e, i, arr) => !arr.some(o => o !== e && o.contains(e)));
  if (!blocks.length) return null;
  // the smallest common ancestor of every hours block, as long as it stays a sidebar or section (not the whole page)
  let anc = blocks[0]; while (anc && !blocks.every(b => anc.contains(b))) anc = anc.parentElement;
  const page = document.documentElement.scrollHeight; let target = anc; while (target && target !== document.body && target.getBoundingClientRect().height > Math.min(2200, page * 0.6)) target = blocks[0];
  const r = (target || blocks[0]).getBoundingClientRect();
  return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, blocks: blocks.length, schedules: blocks.map(b => (b.innerText || '').replace(/\\s+/g, ' ').slice(0, 60)) }; }"""
