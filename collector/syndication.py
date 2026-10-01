"""Phase 4, step 3: the syndication check for research copy (references/02_steps.md, step 12: "To confirm the copy
is syndicated, search one distinctive sentence from it in quotes and see whether other dealers' sites carry it word
for word"). On each store's model research page (one model per store), one distinctive sentence of 12 to 20 words
from the body copy is searched in quotes, headless, on Bing web search, with DuckDuckGo's html endpoint as the
fallback; every other dealer domain carrying it word for word is recorded, the manufacturer's own site left out of
the count. results.json gets research_content: the sentence, the engine, the time, the domains, the page's capture."""
import re
import urllib.parse

from . import captures, config
from .store import domain_of, now_et

OEM = ('nissanusa.com', 'hyundaiusa.com', 'kia.com', 'toyota.com', 'honda.com', 'ford.com', 'chevrolet.com', 'gmc.com', 'buick.com', 'cadillac.com',
       'chrysler.com', 'dodge.com', 'jeep.com', 'ramtrucks.com', 'mazdausa.com', 'subaru.com', 'vw.com', 'lexus.com', 'acura.com', 'infinitiusa.com',
       'mitsubishicars.com', 'lincoln.com', 'volvocars.com', 'bmwusa.com', 'mbusa.com', 'audiusa.com', 'genesis.com', 'porsche.com', 'landroverusa.com', 'jaguarusa.com')
NOT_DEALERS = ('wikipedia.org', 'youtube.com', 'facebook.com', 'edmunds.com', 'kbb.com', 'cars.com', 'autotrader.com', 'caranddriver.com', 'motortrend.com', 'reddit.com', 'bing.com', 'duckduckgo.com', 'microsoft.com', 'msn.com')

# A distinctive sentence from the page's own copy: a paragraph in the content (not the header, nav or footer), split
# into sentences, the first of 12 to 20 words that names no dealer, town or price and has no link-only words
PICK_SENTENCE = """([avoid, lo, hi]) => { const bad = new RegExp(avoid.filter(Boolean).map(s => s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')).join('|') || 'zzzzzz', 'i');
  const paras = [...document.querySelectorAll('main p, article p, [class*="content"] p, [class*="research"] p, [class*="body"] p, section p, p')].filter(p => !p.closest('header, nav, footer, [class*="header"], [class*="footer"], [class*="nav"], [class*="disclaimer"], [class*="sidebar"]') && p.getBoundingClientRect().width > 200);
  const out = [];
  for (const p of paras) { const t = (p.innerText || '').replace(/\\s+/g, ' ').trim(); if (t.length < 80) continue;
    for (const s of t.split(/(?<=[.!?])\\s+/)) { const w = s.trim().replace(/[\\u201c\\u201d"]/g, ''); const n = w.split(/\\s+/).length; if (n < lo || n > hi) continue; if (bad.test(w) || /\\$|\\d{4}|%|click|call us|visit us|contact/i.test(w)) continue; out.push(w); if (out.length >= 3) return out; } }
  return out; }"""

# Bing wraps every result link in bing.com/ck/a?u=a1<base64url of the target>; the snippet sits in .b_caption. When the
# quoted sentence has no match Bing says "No results found for" and shows results for a common word instead, so a
# result counts only when its snippet carries a run of the sentence.
BING_RESULTS = """() => ({ notice: ((document.body.innerText || '').match(/No results found for[^\\n]{0,120}|Including results for[^\\n]{0,120}|Showing results for[^\\n]{0,120}/) || [''])[0],
  rows: [...document.querySelectorAll('li.b_algo')].map(li => { const cite = li.querySelector('cite'); const a = li.querySelector('h2 a'); const cap = li.querySelector('.b_caption p, .b_caption, p');
    return { href: a ? a.href : '', cite: cite ? cite.innerText.trim() : '', title: a ? a.innerText.trim().slice(0, 80) : '', snippet: cap ? cap.innerText.trim().slice(0, 400) : '' }; }) })"""
DDG_RESULTS = """() => ({ notice: ((document.body.innerText || '').match(/No results\\.?[^\\n]{0,80}/) || [''])[0],
  rows: [...document.querySelectorAll('.result')].map(r => { const a = r.querySelector('a.result__a, a.result__url'); let h = a ? a.href : ''; try { const u = new URL(h); const m = u.searchParams.get('uddg'); if (m) h = decodeURIComponent(m); } catch (e) {}
    const sn = r.querySelector('.result__snippet'); return { href: h.slice(0, 200), title: a ? a.innerText.trim().slice(0, 80) : '', snippet: sn ? sn.innerText.trim().slice(0, 400) : '' }; }) })"""


def bing_target(href):
    """The target of a bing.com/ck/a redirect link (its u parameter: 'a1' plus base64url of the URL)."""
    import base64
    try:
        u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get('u', [''])[0]
        if u.startswith('a1'):
            return base64.urlsafe_b64decode(u[2:] + '=' * (-len(u[2:]) % 4)).decode('utf-8', 'ignore')
    except Exception:
        pass
    return href


def carries(snippet, sentence):
    """Does a snippet carry the sentence word for word: the whole sentence, or a run of six of its words."""
    norm = lambda t: re.sub(r'[^a-z0-9 ]+', ' ', (t or '').lower())
    sn, se = re.sub(r'\s+', ' ', norm(snippet)), re.sub(r'\s+', ' ', norm(sentence)).strip()
    if not sn or not se:
        return False
    if se in sn:
        return True
    w = se.split(' ')
    return any(' '.join(w[i:i + 6]) in sn for i in range(0, max(1, len(w) - 5)))


def host_of(text):
    t = (text or '').strip()
    m = re.match(r'(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})', t, re.I)
    return m.group(1).lower().replace('www.', '') if m else None


def search(page, sentence):
    """The quoted sentence on Bing, then DuckDuckGo's html endpoint when Bing gives nothing readable."""
    q = urllib.parse.quote('"' + sentence + '"')
    tried = []
    last_answer = None
    for engine, url, js in (('bing', f'https://www.bing.com/search?q={q}', BING_RESULTS), ('duckduckgo', f'https://html.duckduckgo.com/html/?q={q}', DDG_RESULTS)):
        try:
            resp = captures.goto(page, url, wait='domcontentloaded')
            page.wait_for_timeout(2500)
            body = page.evaluate('() => (document.body.innerText || "").slice(0, 1500)')
            if re.search(r'captcha|unusual traffic|verify you are|are you a robot', body, re.I):
                tried.append({'engine': engine, 'result': 'challenge page'})
                continue
            res = page.evaluate(js)
            rows, notice = res.get('rows') or [], (res.get('notice') or '').strip()
            hits = []
            for row in rows:
                target = bing_target(row['href']) if engine == 'bing' else row.get('href')
                h = host_of(target) or host_of(row.get('cite'))
                if h:
                    hits.append({'host': h, 'title': row.get('title'), 'carries_sentence': carries(row.get('snippet'), sentence) or carries(row.get('title'), sentence)})
            exact = [h for h in hits if h['carries_sentence']]
            tried.append({'engine': engine, 'status': resp.status if resp else None, 'results': len(rows), 'carrying_the_sentence': len(exact), 'notice': notice[:120] or None})
            answered = bool(rows) or bool(notice)
            if answered and (exact or not re.search(r'no results found', notice, re.I)):
                return engine, exact, tried
            if answered and not exact:
                last_answer = engine   # a clear "no results" is an answer: nothing carries the sentence
        except Exception as e:
            tried.append({'engine': engine, 'result': f'{type(e).__name__}: {str(e)[:100]}'})
    return last_answer, [], tried


def check(store, page):
    """One research page per store: the sentence, the search, the other dealer domains."""
    r = store.results
    research = [c for c in r.get('cx') or [] if c.get('page') == 'research' and c.get('url')]
    if not research:
        store.check('research_content', 'skipped', 'no research page was opened for this store')
        return
    entry = research[0]
    # words that mark the dealer's own localized copy, not syndicated copy: the store, its city and state, the request's towns
    req = store.req or {}
    avoid = [r.get('store') or '', r.get('city') or '', (r.get('store') or '').split(' ')[0], req.get('state') or ''] + list(req.get('towns') or [])
    try:
        captures.goto(page, entry['url'])
        page.wait_for_timeout(1000)
        sentences = page.evaluate(PICK_SENTENCE, [avoid, 12, 20])
        picked_range = '12 to 20 words'
        if not sentences:   # a short research page: a wider range, then one that allows the brand's name
            sentences = page.evaluate(PICK_SENTENCE, [avoid, 9, 28])
            picked_range = '9 to 28 words'
        if not sentences:
            sentences = page.evaluate(PICK_SENTENCE, [[r.get('store') or '', r.get('city') or ''] + list(req.get('towns') or []), 9, 28])
            picked_range = '9 to 28 words, the brand allowed'
        if not sentences:
            store.check('research_content', 'failed', f'no sentence of 9 to 28 words without the dealer\'s name in the body copy of {entry["url"]}')
            return
        sentence = sentences[0]
        engine, hits, tried = search(page, sentence)
        own = domain_of(r['pages']['home'])
        others = []
        seen = set()
        for h in hits:
            host = h['host']
            if host == own or host.endswith('.' + own) or host in seen:
                continue
            if any(host == o or host.endswith('.' + o) for o in OEM) or any(host == o or host.endswith('.' + o) for o in NOT_DEALERS):
                continue
            seen.add(host)
            others.append(host)
        oem_hits = sorted({h['host'] for h in hits if any(h['host'] == o or h['host'].endswith('.' + o) for o in OEM)})
        r['research_content'] = {'page': entry['url'], 'label': entry.get('label'), 'sentence': sentence, 'sentence_range': picked_range, 'other_sentences': sentences[1:], 'engine': engine, 'searched_at': now_et(),
                                 'results_carrying_it': len(hits), 'other_dealer_domains': others, 'manufacturer_site_carries_it': oem_hits, 'own_domain_in_results': any(h['host'] == own for h in hits),
                                 'engines_tried': tried, 'capture': entry.get('capture'),
                                 'note': 'the count leaves out the store itself, the manufacturer\'s own site and review or video sites; Claude confirms a domain is a dealer before it goes on a slide'}
        store.check('research_content', 'ok' if engine else 'failed', None if engine else f'neither search engine returned results headless: {tried}')
    except Exception as e:
        store.check('research_content', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
