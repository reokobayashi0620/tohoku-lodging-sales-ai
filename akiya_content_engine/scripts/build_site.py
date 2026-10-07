"""Generate an English SEO buyer site from factual public-source candidate data."""
from pathlib import Path
from collections import defaultdict
import csv, html, json, re
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"data"/"akiya_content_candidates.csv"
HEALTH=ROOT/"output"/"source_health.json"
SITE=Path("docs")
BASE="https://reokobayashi0620.github.io/tohoku-lodging-sales-ai"
FORM_ACTION="https://formsubmit.co/d45da5a4f774175159fdc40ef5f882c8"
PREFS=("Aomori","Iwate","Miyagi","Akita","Yamagata","Fukushima")

def esc(v): return html.escape(str(v or ""))
def slug(v): return re.sub(r"[^a-z0-9]+","-",str(v).lower()).strip("-") or "listing"
def yen(v):
    try:return f"¥{int(float(v)):,}"
    except:return "Price: see original source"
def price_num(v):
    try:return int(float(v))
    except:return None

def shell(title,desc,body,canonical,jsonld=None):
    structured=""
    if jsonld:
        structured='<script type="application/ld+json">'+json.dumps(jsonld,ensure_ascii=False).replace("</","<\\/")+"</script>"
    nav=" · ".join(f'<a href="{BASE}/prefectures/{slug(p)}.html">{p}</a>' for p in PREFS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}">
{structured}<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:auto;max-width:1040px;padding:28px;color:#17212b;line-height:1.55}}a{{color:#075985}}header{{margin-bottom:28px}}nav{{margin-top:10px;font-size:.95rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}.card{{border:1px solid #ddd;border-radius:16px;padding:20px;margin:16px 0}}.cta,button{{display:inline-block;background:#111;color:white;padding:14px 20px;border:0;border-radius:10px;text-decoration:none;font-weight:700;cursor:pointer}}small,.muted{{color:#555}}label{{display:block;font-weight:650;margin-top:14px}}input,select,textarea{{width:100%;box-sizing:border-box;padding:12px;margin-top:6px;border:1px solid #bbb;border-radius:8px;font:inherit}}textarea{{min-height:110px}}.health-ok{{color:#166534}}.health-failed{{color:#b42318}}.notice{{padding:14px;border:1px solid #9ac7a8;border-radius:10px;background:#f3fff6}}footer{{margin-top:36px}}@media(max-width:600px){{body{{padding:18px}}}}
</style></head><body><header><a href="{BASE}/"><strong>NexT DooR — Tohoku Akiya</strong></a><nav>{nav}</nav></header>{body}<footer><hr><small>NexT DooR provides local field support in Tohoku. Property availability and transaction details must be confirmed with the original source and appropriate licensed professionals. NexT DooR / officeMK does not present these summaries as brokerage listings.</small></footer></body></html>"""

def health_html():
    if not HEALTH.exists(): return ""
    try:data=json.loads(HEALTH.read_text(encoding="utf-8"))
    except Exception:return ""
    cards=[]
    for key in ("iwate","aomori","miyagi","akita","yamagata","fukushima"):
        item=data.get(key,{})
        status=item.get("status","not_checked")
        cls="health-ok" if status=="ok" else "health-failed"
        detail="Current public feed available." if status=="ok" else "Source currently unavailable to automation; no stale data is shown."
        cards.append(f"<div class=card><strong>{esc(item.get('label',key.title()))}</strong><p class='{cls}'>{esc(status.upper())} · {esc(item.get('listings',0))} listings</p><small>{detail}</small></div>")
    return "<section><h2>Source status</h2><p class=muted>Automated source checks are shown transparently. A blocked source does not stop the other prefectures.</p><div class=grid>"+"".join(cards)+"</div></section>"

def inquiry_form():
    return f"""<section id="buyer-inquiry"><h2>Buyer Inquiry</h2>
<div id="sent" class="notice" hidden>Thank you. Your inquiry was submitted.</div>
<p>Tell officeMK what you are looking for in Tohoku. We can coordinate local field checks and connect purchase inquiries with an appropriate purchase-support partner.</p>
<form action="{FORM_ACTION}" method="POST">
<input type="hidden" name="_subject" value="NexT DooR Akiya Buyer Inquiry"><input type="hidden" name="_next" value="{BASE}/?inquiry=sent#buyer-inquiry"><input type="hidden" id="property" name="property_id" value="">
<label>Your name<input name="name" autocomplete="name" required></label><label>Email<input type="email" name="email" autocomplete="email" required></label><label>Country / region<input name="country" autocomplete="country-name" required></label>
<label>Preferred prefecture / area<input name="preferred_area" placeholder="e.g. Akita / Kazuno"></label><label>Budget (JPY)<input name="budget_jpy" inputmode="numeric" placeholder="e.g. 5,000,000"></label>
<label>Purchase method<select name="purchase_method"><option value="">Select</option><option>Cash</option><option>Financing</option><option>Not decided</option></select></label>
<label>Intended use<select name="intended_use"><option value="">Select</option><option>Second home</option><option>Primary residence</option><option>Investment</option><option>Renovation project</option><option>Other</option></select></label>
<label>Message<textarea name="message" placeholder="Tell us what matters to you: location, condition, renovation, access, timing, etc."></textarea></label>
<label style="font-weight:400"><input type="checkbox" name="partner_sharing_consent" value="yes" required style="width:auto"> I agree that my inquiry details may be shared with a purchase-support partner when needed to respond to my request.</label><p><button type="submit">Send buyer inquiry</button></p></form></section>
<script>const q=new URLSearchParams(location.search);const p=q.get("property");if(p)document.getElementById("property").value=p;if(q.get("inquiry")==="sent")document.getElementById("sent").hidden=false;</script>"""

def main():
    rows=list(csv.DictReader(INPUT.open(encoding="utf-8"))) if INPUT.exists() else []
    SITE.mkdir(exist_ok=True); (SITE/"properties").mkdir(exist_ok=True); (SITE/"prefectures").mkdir(exist_ok=True)
    links=[]; by_pref=defaultdict(list)
    for r in rows:
        lid=r.get("listing_id") or slug(r.get("source_url")); pref=r.get("prefecture",""); muni=r.get("municipality","")
        fn=f"{slug(pref)}-{slug(muni)}-{slug(lid)}.html"; url=f"{BASE}/properties/{fn}"
        price=yen(r.get("asking_price_jpy"))
        title=f"Akiya for Sale in {muni}, {pref}, Japan — {price} | NexT DooR"
        desc=f"Explore an akiya in {muni}, {pref}, Japan listed at {price}. Public-source property summary with local field support in Tohoku from NexT DooR / officeMK."
        facts=[f"<li>Listed price: {esc(yen(r.get('asking_price_jpy')))}</li>"]
        if r.get("building_sqm"):facts.append(f"<li>Building: {esc(r['building_sqm'])} m²</li>")
        if r.get("land_sqm"):facts.append(f"<li>Land: {esc(r['land_sqm'])} m²</li>")
        body=f"""<p><a href="{BASE}/prefectures/{slug(pref)}.html">{esc(pref)} akiya</a> › {esc(muni)}</p><h1>Akiya for Sale in {esc(muni)}, {esc(pref)}, Japan</h1><p>Looking for a cheap house or vacant home in northern Japan? This public-source property summary covers an akiya in {esc(muni)}, {esc(pref)} Prefecture, in the Tohoku region. NexT DooR / officeMK can help overseas buyers coordinate local field checks before they move forward with the appropriate property professionals.</p><div class=card><ul>{''.join(facts)}</ul><p>{esc(r.get('features'))}</p><p><a href="{esc(r.get('source_url'))}" rel="nofollow">View original public source</a></p></div><h2>Local support for overseas buyers</h2><p>Buying an akiya from overseas can require local confirmation of the building condition, surroundings and current property status. NexT DooR / officeMK provides on-the-ground support in Tohoku and can coordinate field checks and connect purchase inquiries with appropriate purchase-support partners.</p><h2>Interested in this property or {esc(pref)}?</h2><p>Send a buyer inquiry with your country, budget, intended use and preferred area. We can use this property as a starting point or help narrow your search in Tohoku.</p><p><a class=cta href="{BASE}/?property={quote(lid)}#buyer-inquiry">Send buyer inquiry</a></p><small>Listing information may change. This page summarizes public factual information and is not a brokerage listing.</small>"""
        schema={"@context":"https://schema.org","@type":"WebPage","name":title,"url":url,"description":desc,"isPartOf":{"@type":"WebSite","name":"NexT DooR — Tohoku Akiya","url":BASE+"/"}}
        (SITE/"properties"/fn).write_text(shell(title,desc,body,url,schema),encoding="utf-8")
        item=(r,url,fn);links.append(item);by_pref[pref].append(item)

    pref_urls=[]
    for pref in PREFS:
        items=by_pref.get(pref,[]); url=f"{BASE}/prefectures/{slug(pref)}.html"; pref_urls.append(url)
        munis=sorted({r.get("municipality","") for r,_,_ in items if r.get("municipality")})
        prices=[price_num(r.get("asking_price_jpy")) for r,_,_ in items]; prices=[p for p in prices if p is not None]
        price_text=f" Current listed-price range in this feed: {yen(min(prices))} to {yen(max(prices))}." if prices else ""
        cards="".join(f"<div class=card><h2><a href='{BASE}/properties/{fn}'>{esc(r.get('municipality'))}</a></h2><p>{esc(yen(r.get('asking_price_jpy')))}</p></div>" for r,_,fn in items)
        intro=f"Looking for an akiya for sale, cheap house or vacant home in {esc(pref)}, Japan? Explore {len(items)} public-source akiya summaries currently available in this Tohoku prefecture. Areas in the current feed include {esc(', '.join(munis) or 'municipal sources in the prefecture')}.{esc(price_text)}"
        body=f"<p><a href='{BASE}/'>Tohoku Akiya</a> › {esc(pref)}</p><h1>Akiya in {esc(pref)}, Japan</h1><p>{intro}</p><p>NexT DooR / officeMK can support on-site checks, photo/video reporting, repair-condition checks and local coordination in Tohoku.</p><div class=grid>{cards or '<p>No current summaries are available from the automated feed.</p>'}</div><p><a class=cta href='{BASE}/?property={quote(pref)}#buyer-inquiry'>Ask about {esc(pref)}</a></p>"
        desc=f"Find akiya for sale, cheap houses and vacant homes in {pref}, Tohoku, Japan. Browse {len(items)} public-source property summaries and request local field support for overseas buyers."
        schema={"@context":"https://schema.org","@type":"CollectionPage","name":f"Akiya in {pref}, Japan","url":url,"description":desc,"numberOfItems":len(items)}
        (SITE/"prefectures"/f"{slug(pref)}.html").write_text(shell(f"Akiya for Sale in {pref}, Japan | Cheap Houses in Tohoku | NexT DooR",desc,body,url,schema),encoding="utf-8")

    pref_cards="".join(f"<div class=card><h2><a href='{BASE}/prefectures/{slug(p)}.html'>{p}</a></h2><p>{len(by_pref.get(p,[]))} current summaries</p></div>" for p in PREFS)
    latest="".join(f"<div class=card><h3><a href='{BASE}/properties/{fn}'>{esc(r.get('municipality'))}, {esc(r.get('prefecture'))}</a></h3><p>{esc(yen(r.get('asking_price_jpy')))}</p></div>" for r,_,fn in links[:30])
    home=f"<h1>Akiya for Sale in Tohoku, Japan</h1><p>Find cheap houses and vacant homes in northern Japan. Explore public-source akiya information across Aomori, Iwate, Miyagi, Akita, Yamagata and Fukushima, then request local field support from NexT DooR / officeMK as an overseas buyer.</p><section><h2>Browse by prefecture</h2><div class=grid>{pref_cards}</div></section>{health_html()}<section><h2>Property summaries</h2><div class=grid>{latest or '<p>New property summaries are being prepared.</p>'}</div><p class=muted>Browse a prefecture above to see its full current feed.</p></section>{inquiry_form()}"
    home_schema={"@context":"https://schema.org","@type":"WebSite","name":"NexT DooR — Tohoku Akiya","url":BASE+"/","description":"Find akiya for sale, cheap houses and vacant homes across Tohoku, Japan, with local field support for overseas buyers."}
    (SITE/"index.html").write_text(shell("Akiya for Sale in Tohoku, Japan | Cheap Houses & Vacant Homes | NexT DooR","Find akiya for sale, cheap houses and vacant homes across Tohoku, Japan. Public-source property summaries with local field support for overseas buyers.",home,BASE+"/",home_schema),encoding="utf-8")
    urls=[BASE+"/"]+pref_urls+[u for _,u,_ in links]
    (SITE/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)+"</urlset>",encoding="utf-8")
    (SITE/"robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n",encoding="utf-8")
    print(f"Built {len(links)} SEO property pages and {len(PREFS)} prefecture landing pages")

if __name__=="__main__":main()
