"""Read-only Google Search Console indexing audit. Requires GSC_SERVICE_ACCOUNT_JSON secret."""
import datetime,json,os,pathlib,re,urllib.request,urllib.parse,xml.etree.ElementTree as ET
from google.oauth2 import service_account
from google.auth.transport.requests import Request
BASE="https://reokobayashi0620.github.io/tohoku-lodging-sales-ai/"
PREFS={"aomori":"青森","iwate":"岩手","miyagi":"宮城","akita":"秋田","yamagata":"山形","fukushima":"福島"}
KAZUNO=BASE+"properties/akita-kazuno-081f5ded6e67bd7e.html"
STATE=pathlib.Path("seo-monitor/gsc-state.json")
REPORT=pathlib.Path("seo-monitor/gsc-report.md")
def api(url,token,payload=None):
    body=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(url,data=body,headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=10) as res:return json.load(res)
def main():
    raw=os.getenv("GSC_SERVICE_ACCOUNT_JSON","")
    if not raw:
        print("GSC_SERVICE_ACCOUNT_JSON is not configured; skipping Google index checks.")
        return
    creds=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    creds.refresh(Request())
    token=creds.token
    sites=api("https://www.googleapis.com/webmasters/v3/sites",token).get("siteEntry",[])
    if not any(s.get("siteUrl")==BASE and s.get("permissionLevel")!="siteUnverifiedUser" for s in sites):
        raise RuntimeError("Service account has no access to the exact Search Console URL-prefix property: "+BASE)
    with urllib.request.urlopen(BASE+"sitemap.xml",timeout=30) as res:
        root=ET.fromstring(res.read())
    urls=[e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text and e.text.strip().startswith(BASE)]
    all_targets=sorted(set([BASE,KAZUNO]+[u for u in urls if "/properties/" in u]))
    # Keep each run bounded; prioritize Kazuno and a sample from every prefecture.
    priority=[BASE,KAZUNO]
    for code in PREFS:
        match=next((u for u in all_targets if re.search(r"/properties/"+code+r"-",u)),None)
        if match:priority.append(match)
    targets=list(dict.fromkeys(priority+[u for u in all_targets if u not in priority]))[:60]
    print(f"Inspecting {len(targets)} of {len(all_targets)} URLs",flush=True)
    if len(targets)>1900:raise RuntimeError("More than 1900 URLs; refusing to exceed daily quota")
    data={}
    for i,url in enumerate(targets,1):
        print(f"Inspecting {i}/{len(targets)}: {url}",flush=True)
        try:
            r=api("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",token,{"inspectionUrl":url,"siteUrl":BASE,"languageCode":"ja-JP"})
            ix=r.get("inspectionResult",{}).get("indexStatusResult",{})
            data[url]={k:ix.get(k) for k in ("verdict","coverageState","indexingState","robotsTxtState","pageFetchState","lastCrawlTime","googleCanonical")}
        except Exception as e:
            data[url]={"error":str(e)}
    prev=json.loads(STATE.read_text()) if STATE.exists() else {}
    changes=[{"url":u,"before":prev.get(u),"after":v} for u,v in data.items() if prev.get(u)!=v]
    # Ignore last crawl timestamp changes when comparing; keep meaningful status changes.
    meaningful=[c for c in changes if not c["before"] or {k:v for k,v in c["before"].items() if k!="lastCrawlTime"}!={k:v for k,v in c["after"].items() if k!="lastCrawlTime"}]
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    lines=["# Google Search Console インデックス監視",f"実行日時（UTC）: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",""]
    for code,name in PREFS.items():
        entries=[v for u,v in data.items() if re.search(r"/properties/"+code+r"-",u)]
        indexed=sum(v.get("verdict")=="PASS" for v in entries)
        lines.append(f"- {name}: 登録判定PASS {indexed}/{len(entries)} 件、APIエラー {sum('error' in v for v in entries)} 件")
    lines.append("\n鹿角市: "+json.dumps(data.get(KAZUNO),ensure_ascii=False))
    lines.append(f"\n前回からの状態変化: {len(meaningful)} 件")
    for c in meaningful:lines.append("- "+c["url"]+" : "+str(c["before"])+" → "+str(c["after"]))
    lines.append("\n※ URL Inspection APIのGoogle保存済み情報であり、ライブ検査ではありません。")
    REPORT.write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
if __name__=="__main__":main()
