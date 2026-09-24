#!/usr/bin/env python3
"""Acquire and validate a full-text calibration set without redistributing PDFs.

The retained ledger records only source URLs, cryptographic hashes, page/text
metrics, and title checks. PDF bytes live in a caller-selected transient cache.
The selection is fail-closed: 12 TCAD papers, 5 foundational/influential works,
and 5 adjacent-conference papers must all pass PDF and text validation.
"""
from __future__ import annotations
import argparse, csv, hashlib, html, json, os, re, subprocess, time, unicodedata
import urllib.error, urllib.parse, urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

UA="coverage-certified-trace-localization-fulltext-calibration/1.0 (artifact-audit@openai.com)"

def sha256(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def plain(s:str)->str:
 s=html.unescape(s or '')
 s=re.sub(r"\\(?:textit|textbf|emph|mathrm|mathit)\s*\{([^{}]*)\}",r"\1",s)
 s=re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?",' ',s)
 s=s.replace('{','').replace('}','').replace('$',' ')
 s=unicodedata.normalize('NFKD',s)
 s=''.join(c for c in s if not unicodedata.combining(c))
 return re.sub(r'\s+',' ',s).strip()

def norm(s:str)->str:
 return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',plain(s).lower())).strip()

def toks(s:str)->set[str]:
 stop={'a','an','the','of','for','to','and','in','on','with','by','from','using','toward','towards','via','its'}
 return {x for x in norm(s).split() if len(x)>2 and x not in stop}

def title_score(a:str,b:str)->float:
 ta,tb=toks(a),toks(b)
 if not ta or not tb:return 0.0
 contain=len(ta&tb)/len(ta)
 jac=len(ta&tb)/len(ta|tb)
 seq=SequenceMatcher(None,norm(a),norm(b)).ratio()
 return max(contain,0.65*jac+0.35*seq)

def get_json(url:str,cache:Path)->Any:
 if cache.exists():return json.loads(cache.read_text())
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=35) as r: raw=r.read()
 cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(raw)
 return json.loads(raw)

def add_url(out:list[tuple[str,str]],url:str|None,method:str)->None:
 if not url:return
 url=str(url).strip()
 if not url:return
 if url.startswith('http://'):url='https://'+url[7:]
 if 'arxiv.org/abs/' in url:url=url.replace('/abs/','/pdf/')+'.pdf'
 if url.startswith('https://doi.org/'):return
 if (url,method) not in out:out.append((url,method))

def candidate_urls(row:dict[str,str],api_cache:Path)->list[tuple[str,str]]:
 out=[]; doi=row.get('doi','').strip().lower().replace('https://doi.org/','')
 add_url(out,row.get('url',''),'bib_url')
 if doi:
  enc=urllib.parse.quote(doi,safe='')
  try:
   u=get_json(f'https://api.unpaywall.org/v2/{enc}?email=artifact-audit@openai.com',api_cache/f'unpaywall-{row["key"]}.json')
   locs=[]
   if u.get('best_oa_location'):locs.append(u['best_oa_location'])
   locs.extend(u.get('oa_locations') or [])
   for loc in locs:
    add_url(out,loc.get('url_for_pdf'),'unpaywall_pdf')
    landing=loc.get('url_for_landing_page')
    if landing and (landing.lower().endswith('.pdf') or 'arxiv.org/' in landing):add_url(out,landing,'unpaywall_landing_pdf')
  except Exception:pass
  try:
   o=get_json(f'https://api.openalex.org/works/https://doi.org/{enc}',api_cache/f'openalex-fulltext-{row["key"]}.json')
   locs=[]
   if o.get('best_oa_location'):locs.append(o['best_oa_location'])
   locs.extend(o.get('locations') or [])
   for loc in locs:
    add_url(out,loc.get('pdf_url'),'openalex_pdf')
    land=loc.get('landing_page_url')
    if land and (land.lower().endswith('.pdf') or 'arxiv.org/' in land or 'hal.' in land):add_url(out,land,'openalex_landing_pdf')
  except Exception:pass
  try:
   s=get_json('https://api.semanticscholar.org/graph/v1/paper/DOI:'+enc+'?fields=title,openAccessPdf,externalIds',api_cache/f's2-{row["key"]}.json')
   add_url(out,(s.get('openAccessPdf') or {}).get('url'),'semantic_scholar_pdf')
  except Exception:pass
  try:
   c=get_json(f'https://api.crossref.org/works/{enc}',api_cache/f'crossref-fulltext-{row["key"]}.json')
   for link in (c.get('message') or {}).get('link') or []:
    if 'pdf' in str(link.get('content-type','')).lower():add_url(out,link.get('URL'),'crossref_pdf')
  except Exception:pass
  if doi.startswith('10.48550/arxiv.'):
   add_url(out,'https://arxiv.org/pdf/'+doi.split('arxiv.',1)[1]+'.pdf','arxiv_doi')
 # Convert common repository landing links.
 extra=[]
 for url,method in out:
  if 'export.arxiv.org/abs/' in url:extra.append((url.replace('/abs/','/pdf/')+'.pdf',method+'_converted'))
  if 'arxiv.org/abs/' in url:extra.append((url.replace('/abs/','/pdf/')+'.pdf',method+'_converted'))
 out.extend(x for x in extra if x not in out)
 return out

def download_pdf(url:str,dest:Path)->tuple[str,str]:
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/pdf,text/html;q=0.8,*/*;q=0.5'})
 with urllib.request.urlopen(req,timeout=55) as r:
  raw=r.read(60*1024*1024); final=r.geturl();ctype=str(r.headers.get('content-type',''))
 if not raw.startswith(b'%PDF'):
  # Some repository landing pages expose a PDF link in HTML.
  text=raw.decode('utf-8','ignore')
  links=re.findall(r'(?:href|content)=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']',text,re.I)
  if links:
   link=urllib.parse.urljoin(final,html.unescape(links[0]))
   req=urllib.request.Request(link,headers={'User-Agent':UA,'Accept':'application/pdf'})
   with urllib.request.urlopen(req,timeout=55) as r2:
    raw=r2.read(60*1024*1024);final=r2.geturl();ctype=str(r2.headers.get('content-type',''))
 if not raw.startswith(b'%PDF'):raise ValueError('not a PDF')
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 return final,ctype

def validate_pdf(path:Path,title:str)->dict[str,Any]:
 info=subprocess.run(['pdfinfo',str(path)],text=True,capture_output=True,check=True).stdout
 m=re.search(r'^Pages:\s+(\d+)',info,re.M);pages=int(m.group(1)) if m else 0
 if pages<2:raise ValueError('too few pages')
 txt=path.with_suffix('.txt')
 subprocess.run(['pdftotext','-layout',str(path),str(txt)],text=True,capture_output=True,check=True)
 text=txt.read_text(encoding='utf-8',errors='ignore')
 txt.unlink(missing_ok=True)
 chars=len(re.sub(r'\s+','',text))
 if chars<3000:raise ValueError('insufficient extractable text')
 opening=' '.join(text[:30000].split())
 score=title_score(title,opening)
 title_tokens=toks(title);hits=len(title_tokens&toks(opening));coverage=hits/max(1,len(title_tokens))
 if score<0.50 and coverage<0.55:raise ValueError(f'title mismatch {score:.3f}/{coverage:.3f}')
 section_patterns=[r'\babstract\b',r'\bintroduction\b',r'\bconclusion',r'\breferences\b']
 sections=sum(bool(re.search(p,text,re.I)) for p in section_patterns)
 if sections<2:raise ValueError('not enough paper structure markers')
 return {'pages':pages,'text_chars':chars,'title_score':round(score,6),'title_token_coverage':round(coverage,6),'structure_markers':sections}

def classify(row:dict[str,str])->str:
 v=norm(row.get('venue',''));t=norm(row.get('title',''))
 if 'transactions on computer aided design of integrated circuits and systems' in v:return 'closest'
 adjacent_terms=('design automation conference','international conference on computer aided design','design automation and test in europe','international test conference','asian test symposium','vlsi test symposium','computer design iccd','computer aided verification','dac','iccad')
 if any(x in v for x in adjacent_terms):return 'adjacent'
 foundational_terms=('longest common subsequence','set cover','diagnosability','discrete event systems','post silicon validation','post silicon debug','computer algorithms','computers and intractability','debugging','trace')
 if any(x in t for x in foundational_terms):return 'influential'
 return 'other'

def main()->None:
 ap=argparse.ArgumentParser();ap.add_argument('--verification',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);ap.add_argument('--cache',type=Path,required=True)
 args=ap.parse_args();args.outdir.mkdir(parents=True,exist_ok=True);args.cache.mkdir(parents=True,exist_ok=True)
 vr=json.loads(args.verification.read_text());rows=vr['rows'];api=args.cache/'api';pdfs=args.cache/'pdfs';attempts=[];success=[]
 # Prioritize category candidates but explore all until quotas are met.
 order={'closest':0,'adjacent':1,'influential':2,'other':3}
 candidates=sorted(rows,key=lambda r:(order[classify(r)],int(r.get('index',0))))
 for row in candidates:
  cat=classify(row)
  # Stop expensive exploration of a category after quota, except keep a small reserve.
  quota={'closest':12,'adjacent':5,'influential':5}.get(cat,0)
  if quota and sum(x['category']==cat for x in success)>=quota+2:continue
  urls=candidate_urls(row,api)
  ok=None
  for n,(url,method) in enumerate(urls):
   rec={'key':row['key'],'title':row['title'],'category':cat,'candidate_url':url,'method':method,'status':'failed','error':''}
   try:
    dest=pdfs/f"{row['key']}-{n}.pdf"
    final,ctype=download_pdf(url,dest);metrics=validate_pdf(dest,row['title'])
    rec.update({'status':'validated','final_url':final,'content_type':ctype,'sha256':sha256(dest),'bytes':dest.stat().st_size,**metrics})
    ok=rec;attempts.append(rec);break
   except Exception as e:
    rec['error']=f'{type(e).__name__}: {e}'[:500];attempts.append(rec)
   time.sleep(0.08)
  if ok:success.append(ok)
  counts={c:sum(x['category']==c for x in success) for c in ('closest','influential','adjacent')}
  if all(counts[c]>=q for c,q in {'closest':12,'influential':5,'adjacent':5}.items()):break
 # Deterministic category selection: best title score, then pages, then key.
 selected=[]
 for cat,q in [('closest',12),('influential',5),('adjacent',5)]:
  pool=sorted((x for x in success if x['category']==cat),key=lambda x:(-x['title_score'],-x['pages'],x['key']))
  selected.extend(pool[:q])
  if len(pool)<q:
   print(json.dumps({'category':cat,'needed':q,'validated':len(pool),'validated_keys':[x['key'] for x in pool]},indent=2))
 # Write complete attempts before failing, for diagnosis.
 (args.outdir/'fulltext-attempts.json').write_text(json.dumps({'attempts':attempts},indent=2,sort_keys=True)+'\n')
 if len(selected)!=22:
  raise SystemExit(f'full-text quota not met: selected {len(selected)} of 22')
 # Ensure papers are unique even if a URL is shared.
 if len({x['sha256'] for x in selected})<20:raise SystemExit('fewer than 20 unique full-text PDFs')
 fields=['category','key','title','method','candidate_url','final_url','sha256','bytes','pages','text_chars','title_score','title_token_coverage','structure_markers']
 csvp=args.outdir/'fulltext-calibration.csv'
 with csvp.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:x.get(k,'') for k in fields} for x in selected])
 report={'schema':'fulltext-calibration-v1','records':len(selected),'unique_pdfs':len({x['sha256'] for x in selected}),
         'categories':{c:sum(x['category']==c for x in selected) for c in ('closest','influential','adjacent')},
         'pdfs_redistributed':False,'cache_outside_release':str(args.cache),'ledger_csv':csvp.name,
         'ledger_sha256':hashlib.sha256(csvp.read_bytes()).hexdigest(),'records_detail':selected}
 (args.outdir/'fulltext-calibration.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:report[k] for k in ('records','unique_pdfs','categories','pdfs_redistributed')},indent=2,sort_keys=True))

if __name__=='__main__':main()
