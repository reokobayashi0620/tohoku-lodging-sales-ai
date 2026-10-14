import json, urllib.request, urllib.error, xml.etree.ElementTree as ET, pathlib, datetime, re
BASE="https://reokobayashi0620.github.io/tohoku-lodging-sales-ai/"
SITEMAP=BASE+"sitemap.xml"
STATE=pathlib.Path("seo-monitor/state.json")
REPORT=pathlib.Path("seo-monitor/report.md")
PREFS={"aomori":"青森","iwate":"岩手","miyagi":"宮城","akita":"秋田","yamagata":"山形","fukushima":"福島"}
KAZUNO=BASE+"properties/akita-kazuno-081f5ded6e67bd7e.html"
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NexTDooR-SEO-Monitor/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=20) as res:
            return res.status,res.read() if url==SITEMAP else b""
    except urllib.error.HTTPError as e: return e.code,b""
    except Exception as e: return "ERROR:"+str(e),b""
def main():
    status,body=fetch(SITEMAP)
    urls=[]
    if status==200:
        try:
            root=ET.fromstring(body)
            urls=[x.text.strip() for x in root.iter() if x.tag.endswith("loc") and x.text]
        except Exception as e: status="XML_ERROR:"+str(e)
    targets=sorted(set([u for u in urls if u.startswith(BASE) and "/properties/" in u]+[KAZUNO]))
    results={u:fetch(u)[0] for u in targets}
    bypref={v:{"total":0,"ok":0,"errors":[]} for v in PREFS.values()}
    for u,s in results.items():
        match=re.search(r"/properties/([a-z]+)-",u)
        if match and match.group(1) in PREFS:
            p=bypref[PREFS[match.group(1)]]
            p["total"]+=1
            if s==200:p["ok"]+=1
            else:p["errors"].append({"url":u,"status":s})
    current={"sitemap_status":status,"url_count":len(urls),"properties":results,"prefectures":bypref,"kazuno_status":results.get(KAZUNO)}
    previous=json.loads(STATE.read_text()) if STATE.exists() else None
    changes=[]
    if previous:
        if previous.get("sitemap_status")!=status:changes.append("サイトマップ取得状況の変化")
        for u,s in results.items():
            if previous.get("properties",{}).get(u)!=s:changes.append(f"{u}: {previous.get('properties',{}).get(u,'新規')} → {s}")
        for u in previous.get("properties",{}):
            if u not in results:changes.append(f"監視対象から消失: {u}")
    else:changes.append("初回基準値を記録")
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(current,ensure_ascii=False,indent=2)+"\n")
    lines=["# NexT DooR 公開ページ監視",f"実行日: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",f"サイトマップHTTP: {status}",f"サイトマップURL数: {len(urls)}",f"鹿角市HTTP: {results.get(KAZUNO)}","","## 県別"]
    for name,p in bypref.items():lines.append(f"- {name}: HTTP 200 = {p['ok']}/{p['total']}件、異常 {len(p['errors'])}件")
    lines+=["","## 前回との差分"]+["- "+x for x in changes]
    lines+=["","※ HTTP検査であり、Googleのインデックス登録・登録除外・クロール統計を示すものではありません。"]
    REPORT.write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
if __name__=="__main__":main()
