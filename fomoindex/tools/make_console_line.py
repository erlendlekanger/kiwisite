"""Build the one line the operator pastes into the Console on fomo.family (logged in), and put it on the clipboard.

fomo.family's security policy lets its page talk only to fomo, so the list of traders (username + fomo's public user id,
the most popular ones still missing a trading wallet) is written into the line itself. The line asks fomo, through the
page's own login the way the app does, for each trader's balances, one a second, and saves fomo_balances.json in
Downloads. Then: py fomoindex/tools/match_balances.py

    py fomoindex/tools/make_console_line.py [--n 300]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

LINE = r"""(async()=>{const L=__LIST__;const H={'Content-Type':'application/json','X-Supported-Chains':'1,56,143,4663,5042,8453,1399811149','App-Language':'en'};const ff=performance.getEntriesByType('resource').map(e=>e.name).find(n=>n.includes('/fomoFetch-v2-'));let F=null;if(ff){try{F=(await import(ff)).f}catch(e){}}const direct=async p=>{const r=await fetch('https://prod-api.fomo.family'+p,{credentials:'include',headers:H});let j={};try{j=await r.json()}catch(e){}return{statusCode:r.status,...j}};const get=async p=>{if(F){try{return await F(p)}catch(e){F=null}}return direct(p)};const bad=r=>!r||r.statusCode>=400||r.success===false;const out={};let skipped=0;console.log('FOMOINDEX: reading',L.length,'traders, one a second');for(let i=0;i<L.length;i++){const[h,id]=L[i];let r;try{r=await get('/v2/users/'+id+'/balances')}catch(e){r={statusCode:0,message:String(e&&e.message||e)}}if(bad(r)){if(i===0||[401,403,430,431].includes(r.statusCode)){console.error('fomo answered',r.statusCode,r.message||r.error||'','- log in on fomo.family in this tab, reload, and paste again');if(!Object.keys(out).length)return;break}skipped++;continue}const{timing,...k}=r;out[h]={id,r:k};if((i+1)%10===0)console.log(i+1,'/',L.length);await new Promise(s=>setTimeout(s,1000))}const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out)],{type:'application/json'}));a.download='fomo_balances.json';document.body.appendChild(a);a.click();console.log('FOMOINDEX: done,',Object.keys(out).length,'traders saved to Downloads/fomo_balances.json',skipped?('('+skipped+' skipped)'):'')})()"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    ids = json.loads(urllib.request.urlopen(f"https://fomoindex.app/api/resolve-list?n={a.n}", timeout=60).read())["ids"]
    line = LINE.replace("__LIST__", json.dumps(ids, separators=(",", ":")))
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                   input=line, text=True, encoding="utf-8", check=True)
    print(f"on the clipboard: the Console line for {len(ids)} traders ({len(line) // 1000} kB)")


if __name__ == "__main__":
    main()
