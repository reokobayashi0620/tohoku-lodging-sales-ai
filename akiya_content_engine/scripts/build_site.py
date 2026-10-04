"""Generate a static English buyer site from factual candidate data. No listing photos are copied."""
from pathlib import Path
import csv, html, re
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"data"/"akiya_content_candidates.csv"
SITE=Path("docs")
BASE="https://reokobayashi0620.github.io/tohoku-lodging-sales-ai"

def esc(v): return html.escape(str(v or ""))
def slug(v): return re.sub(r"[^a-z0-9]+","-",str(v).lower()).strip("-") or "listing"
def yen(v):
 try:return f"¥{int(float(v)):,}"
 except:return "Price: see original source"
def shell(title,desc,body,canonical):
 return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><style>body{{font-family:system-ui,sans-serif;margin:auto;max-width:960px;padding:28px;color:#17212b}}a{{color:#075985}}.card{{border:1px solid #ddd;border-radius:16px;padding:22px;margin:18px 0}}.cta{{display:inline-block;background:#111;color:white;padding:14px 20px;border-radius:10px;text-decoration:none}}small{{color:#555}}</style></head><body><header><a href="/">NexT DooR — Tohoku Akiya</a></header>{body}<footer><hr><small>NexT DooR provides local field support in Tohoku. Property availability and transaction details must be confirmed with the original source and appropriate licensed professionals.</small></footer></body></html>"""
def main():
 rows=list(csv.DictReader(INPUT.open(encoding="utf-8"))) if INPUT.exists() else []
 SITE.mkdir(exist_ok=True); (SITE/"properties").mkdir(exist_ok=True)
 links=[]
 for r in rows:
  lid=r.get("listing_id") or slug(r.get("source_url"))
  fn=f"{slug(r.get('prefecture'))}-{slug(r.get('municipality'))}-{slug(lid)}.html"
  url=f"{BASE}/properties/{fn}"
  title=f"Akiya in {r.get('municipality')}, {r.get('prefecture')}, Japan | NexT DooR"
  desc=f"Explore an akiya listing in {r.get('municipality')}, {r.get('prefecture')}, Tohoku, Japan. Local buyer support from NexT DooR."
  facts=[f"<li>Listed price: {esc(yen(r.get('asking_price_jpy')))}</li>"]
  if r.get("building_sqm"): facts.append(f"<li>Building: {esc(r['building_sqm'])} m²</li>")
  if r.get("land_sqm"): facts.append(f"<li>Land: {esc(r['land_sqm'])} m²</li>")
  body=f"<h1>{esc(title.split(' | ')[0])}</h1><div class=card><ul>{''.join(facts)}</ul><p>{esc(r.get('features'))}</p><p><a href='{esc(r.get('source_url'))}' rel='nofollow'>View original public source</a></p></div><h2>Interested in a home in Tohoku?</h2><p>Tell us your preferred area, budget and intended use. We can help coordinate local field checks and connect your purchase inquiry with the appropriate support partner.</p><p><a class=cta href='/?property={quote(lid)}#buyer-inquiry'>Send buyer inquiry</a></p><small>Listing information may change. This page summarizes public factual information and is not a brokerage listing.</small>"
  (SITE/"properties"/fn).write_text(shell(title,desc,body,url),encoding="utf-8")
  links.append((r,url,fn))
 cards="".join(f"<div class=card><h2><a href='/properties/{fn}'>{esc(r.get('municipality'))}, {esc(r.get('prefecture'))}</a></h2><p>{esc(yen(r.get('asking_price_jpy')))}</p></div>" for r,_,fn in links)
 home=f"<h1>Find an Akiya in Tohoku, Japan</h1><p>Discover public akiya information across northern Japan and get local support for your search.</p>{cards or '<p>New property summaries are being prepared.</p>'}<section id=buyer-inquiry><h2>Buyer Inquiry</h2><p>Looking for an akiya in Tohoku? Contact officeMK with your preferred prefecture, budget and intended use.</p><p><a class=cta href='mailto:office.mk.7963@gmail.com?subject=NexT%20DooR%20Akiya%20Buyer%20Inquiry'>Contact NexT DooR</a></p></section>"
 (SITE/"index.html").write_text(shell("Akiya in Tohoku Japan | NexT DooR","Find akiya and countryside homes in Tohoku, Japan, with local field support.",home,BASE+"/"),encoding="utf-8")
 urls=[BASE+"/"]+[u for _,u,_ in links]
 (SITE/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)+"</urlset>",encoding="utf-8")
 (SITE/"robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n",encoding="utf-8")
 print(f"Built {len(links)} SEO property pages")
if __name__=="__main__": main()
