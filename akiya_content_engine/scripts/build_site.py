"""Generate a static English buyer site from factual candidate data. No listing photos are copied."""
from pathlib import Path
import csv, html, json, re
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"data"/"akiya_content_candidates.csv"
HEALTH=ROOT/"output"/"source_health.json"
SITE=Path("docs")
BASE="https://reokobayashi0620.github.io/tohoku-lodging-sales-ai"
FORM_ACTION="https://formsubmit.co/d45da5a4f774175159fdc40ef5f882c8"

def esc(v): return html.escape(str(v or ""))
def slug(v): return re.sub(r"[^a-z0-9]+","-",str(v).lower()).strip("-") or "listing"
def yen(v):
    try:return f"¥{int(float(v)):,}"
    except:return "Price: see original source"

def shell(title,desc,body,canonical):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:auto;max-width:1040px;padding:28px;color:#17212b;line-height:1.55}}a{{color:#075985}}header{{margin-bottom:28px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}.card{{border:1px solid #ddd;border-radius:16px;padding:20px;margin:16px 0}}.cta,button{{display:inline-block;background:#111;color:white;padding:14px 20px;border:0;border-radius:10px;text-decoration:none;font-weight:700;cursor:pointer}}small,.muted{{color:#555}}label{{display:block;font-weight:650;margin-top:14px}}input,select,textarea{{width:100%;box-sizing:border-box;padding:12px;margin-top:6px;border:1px solid #bbb;border-radius:8px;font:inherit}}textarea{{min-height:110px}}.health-ok{{color:#166534}}.health-failed{{color:#b42318}}footer{{margin-top:36px}}@media(max-width:600px){{body{{padding:18px}}}}
</style></head><body><header><a href="{esc(BASE)}/">NexT DooR — Tohoku Akiya</a></header>{body}<footer><hr><small>NexT DooR provides local field support in Tohoku. Property availability and transaction details must be confirmed with the original source and appropriate licensed professionals. NexT DooR / officeMK does not present these summaries as brokerage listings.</small></footer></body></html>"""

def health_html():
    if not HEALTH.exists():
        return ""
    try:
        data=json.loads(HEALTH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    cards=[]
    for key in ("iwate","aomori","miyagi","akita","yamagata","fukushima"):
        item=data.get(key,{})
        status=item.get("status","not_checked")
        cls="health-ok" if status=="ok" else "health-failed"
        label=esc(item.get("label",key.title()))
        count=esc(item.get("listings",0))
        detail="Current public feed available." if status=="ok" else "Source currently unavailable to automation; no stale data is shown."
        cards.append(f"<div class=card><strong>{label}</strong><p class='{cls}'>{esc(status.upper())} · {count} listings</p><small>{detail}</small></div>")
    return "<section><h2>Source status</h2><p class=muted>Automated source checks are shown transparently. A blocked source does not stop the other prefectures.</p><div class=grid>"+"".join(cards)+"</div></section>"

def inquiry_form():
    return f"""<section id="buyer-inquiry"><h2>Buyer Inquiry</h2>
<p>Tell officeMK what you are looking for in Tohoku. We can coordinate local field checks and connect purchase inquiries with an appropriate purchase-support partner.</p>
<form action="{FORM_ACTION}" method="POST">
<input type="hidden" name="_subject" value="NexT DooR Akiya Buyer Inquiry">
<input type="hidden" name="_next" value="{BASE}/?inquiry=sent#buyer-inquiry">
<input type="hidden" id="property" name="property_id" value="">
<label>Your name<input name="name" autocomplete="name" required></label>
<label>Email<input type="email" name="email" autocomplete="email" required></label>
<label>Country / region<input name="country" autocomplete="country-name" required></label>
<label>Preferred prefecture / area<input name="preferred_area" placeholder="e.g. Akita / Kazuno"></label>
<label>Budget (JPY)<input name="budget_jpy" inputmode="numeric" placeholder="e.g. 5,000,000"></label>
<label>Purchase method<select name="purchase_method"><option value="">Select</option><option>Cash</option><option>Financing</option><option>Not decided</option></select></label>
<label>Intended use<select name="intended_use"><option value="">Select</option><option>Second home</option><option>Primary residence</option><option>Investment</option><option>Renovation project</option><option>Other</option></select></label>
<label>Message<textarea name="message" placeholder="Tell us what matters to you: location, condition, renovation, access, timing, etc."></textarea></label>
<label style="font-weight:400"><input type="checkbox" name="partner_sharing_consent" value="yes" required style="width:auto"> I agree that my inquiry details may be shared with a purchase-support partner when needed to respond to my request.</label>
<p><button type="submit">Send buyer inquiry</button></p>
<small>Form submission is handled by FormSubmit. The first submission may require a one-time email activation by officeMK before delivery is enabled.</small>
</form></section>
<script>
const p=new URLSearchParams(location.search).get("property");
if(p) document.getElementById("property").value=p;
</script>"""

def main():
    rows=list(csv.DictReader(INPUT.open(encoding="utf-8"))) if INPUT.exists() else []
    SITE.mkdir(exist_ok=True); (SITE/"properties").mkdir(exist_ok=True)
    links=[]
    for r in rows:
        lid=r.get("listing_id") or slug(r.get("source_url"))
        fn=f"{slug(r.get('prefecture'))}-{slug(r.get('municipality'))}-{slug(lid)}.html"
        url=f"{BASE}/properties/{fn}"
        title=f"Akiya in {r.get('municipality')}, {r.get('prefecture')}, Japan | NexT DooR"
        desc=f"Explore public akiya information in {r.get('municipality')}, {r.get('prefecture')}, Tohoku, Japan, with local field support from NexT DooR."
        facts=[f"<li>Listed price: {esc(yen(r.get('asking_price_jpy')))}</li>"]
        if r.get("building_sqm"): facts.append(f"<li>Building: {esc(r['building_sqm'])} m²</li>")
        if r.get("land_sqm"): facts.append(f"<li>Land: {esc(r['land_sqm'])} m²</li>")
        body=f"""<h1>{esc(title.split(' | ')[0])}</h1><div class=card><ul>{''.join(facts)}</ul><p>{esc(r.get('features'))}</p><p><a href="{esc(r.get('source_url'))}" rel="nofollow">View original public source</a></p></div>
<h2>Interested in this area?</h2><p>Use the buyer inquiry form and include your preferred area, budget and intended use.</p><p><a class=cta href="{esc(BASE)}/?property={quote(lid)}#buyer-inquiry">Send buyer inquiry</a></p><small>Listing information may change. This page summarizes public factual information and is not a brokerage listing.</small>"""
        (SITE/"properties"/fn).write_text(shell(title,desc,body,url),encoding="utf-8")
        links.append((r,url,fn))
    cards="".join(f"<div class=card><h2><a href='{esc(BASE)}/properties/{fn}'>{esc(r.get('municipality'))}, {esc(r.get('prefecture'))}</a></h2><p>{esc(yen(r.get('asking_price_jpy')))}</p></div>" for r,_,fn in links)
    home=f"<h1>Find an Akiya in Tohoku, Japan</h1><p>Explore public vacant-home information across northern Japan and request local field support from officeMK.</p>{health_html()}<section><h2>Property summaries</h2>{cards or '<p>New property summaries are being prepared.</p>'}</section>{inquiry_form()}"
    (SITE/"index.html").write_text(shell("Akiya in Tohoku Japan | NexT DooR","Find akiya and countryside homes in Tohoku, Japan, with local field support.",home,BASE+"/"),encoding="utf-8")
    urls=[BASE+"/"]+[u for _,u,_ in links]
    (SITE/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)+"</urlset>",encoding="utf-8")
    (SITE/"robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n",encoding="utf-8")
    print(f"Built {len(links)} SEO property pages")

if __name__=="__main__":
    main()
