import re, os, glob
def normalize_code(code:str)->str:
    code=re.sub(r"//.*|/\*.*?\*/|#.*","",code,flags=re.S); code=re.sub(r"\s+"," ",code).strip(); return code
def similarity_score(a:str,b:str)->float:
    a=normalize_code(a); b=normalize_code(b)
    if not a or not b: return 0.0
    sa=set(a.split()); sb=set(b.split())
    if not sa or not sb: return 0.0
    return len(sa & sb)/len(sa | sb)
def shingles(s:str,k:int=5):
    toks=normalize_code(s).split(); return set((" ".join(toks[i:i+k]) for i in range(0,max(0,len(toks)-k+1))))
def web_like_local_search(code:str, corpus_dir:str):
    target=shingles(code,5); res=[]
    for path in glob.glob(os.path.join(corpus_dir,'*')):
        try:
            src=open(path,'r',encoding='utf-8',errors='ignore').read(); sh=shingles(src,5)
            inter=len(target & sh); base=max(1,len(target)); score=inter/base
            if score>0.05: res.append({'file':os.path.basename(path),'score':round(score,3)})
        except Exception: pass
    res.sort(key=lambda x:x['score'], reverse=True); return res[:10]
