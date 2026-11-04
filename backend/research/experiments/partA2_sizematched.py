#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART A2 — size-matched null. The hadith corpus is ~18x larger, and Zipf/Heaps
exponents drift with corpus size. So: draw many random 77,429-token samples from
the hadith pool and build the null distribution of α, β, ρ AT THE QURAN'S SIZE.
Then ask where the Quran's values fall. This is the honest 'is it unusual?' test."""
import json, re, os, urllib.request
import numpy as np, pandas as pd
from scipy import stats
from sklearn.metrics import r2_score
rng=np.random.default_rng(7)
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output"); DATA=os.path.join(HERE,"data")
CACHE=os.path.join(DATA,"hadith_tokens.txt")

_DIAC=re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D4\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")
_MAP=str.maketrans({"\u0671":"\u0627","\u0623":"\u0627","\u0625":"\u0627","\u0622":"\u0627",
    "\u0649":"\u064A","\u0624":"\u0648","\u0626":"\u064A","\u0629":"\u0647","\u0621":""})
ARABIC=re.compile(r"[^\u0621-\u064A]")
def norm_tok(t): return ARABIC.sub("",_DIAC.sub("",t).translate(_MAP))

if os.path.exists(CACHE):
    h=open(CACHE,encoding="utf-8").read().split("\n"); h=[x for x in h if x]
else:
    h=[]
    for ed in ["ara-bukhari","ara-muslim","ara-abudawud"]:
        u=f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{ed}.min.json"
        d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"r/1"}),timeout=90))
        for x in d["hadiths"]:
            for w in re.split(r"\s+",x.get("text","")):
                t=norm_tok(w)
                if t: h.append(t)
    open(CACHE,"w",encoding="utf-8").write("\n".join(h))
h=np.array(h,dtype=object); print("hadith pool tokens:",len(h))

def alpha(tokens):
    f=pd.Series(tokens).value_counts().values.astype(float)
    r=np.arange(1,len(f)+1); a,_=np.polyfit(np.log10(r),np.log10(f),1); return -a
def beta(tokens):
    seen=set();N=[];V=[]
    for i,t in enumerate(tokens,1):
        seen.add(t)
        if i%200==0:N.append(i);V.append(len(seen))
    N=np.array(N,float);V=np.array(V,float);m=N>=200
    b,_=np.polyfit(np.log10(N[m]),np.log10(V[m]),1); return b
def rho(tokens):
    s=pd.Series(tokens).value_counts(); df=pd.DataFrame({"f":s.values}); df["L"]=[len(x) for x in s.index]
    return stats.spearmanr(df["L"],np.log10(df["f"])).statistic

QA,QB,QR=0.935,0.744,-0.200; n=77429; B=200
A=np.empty(B);Bt=np.empty(B);Rr=np.empty(B)
for i in range(B):
    idx=rng.choice(len(h),n,replace=False); samp=h[idx]
    A[i]=alpha(samp); Bt[i]=beta(samp); Rr[i]=rho(samp)
def z(v,arr): return (v-arr.mean())/arr.std()
def pct(v,arr): return float((np.sum(arr<=v)+0.5)/len(arr))
print(f"\nHADITH null at Quran size (n={n}, B={B} random samples):")
print(f"  Zipf α : null {A.mean():.3f}±{A.std():.3f}   Quran {QA:.3f}   z={z(QA,A):+.2f}  pct={pct(QA,A):.3f}")
print(f"  Heaps β: null {Bt.mean():.3f}±{Bt.std():.3f}   Quran {QB:.3f}   z={z(QB,Bt):+.2f}  pct={pct(QB,Bt):.3f}")
print(f"  brevity ρ: null {Rr.mean():.3f}±{Rr.std():.3f}  Quran {QR:.3f}  z={z(QR,Rr):+.2f}  pct={pct(QR,Rr):.3f}")
res=dict(n=n,B=B,
   alpha=dict(null_mean=float(A.mean()),null_sd=float(A.std()),quran=QA,z=float(z(QA,A)),pct=pct(QA,A)),
   beta=dict(null_mean=float(Bt.mean()),null_sd=float(Bt.std()),quran=QB,z=float(z(QB,Bt)),pct=pct(QB,Bt)),
   rho=dict(null_mean=float(Rr.mean()),null_sd=float(Rr.std()),quran=QR,z=float(z(QR,Rr)),pct=pct(QR,Rr)))
json.dump(res,open(os.path.join(OUT,"baseline_sizematched.json"),"w"),indent=2,default=float)

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,3,figsize=(15,4.4))
for axi,(arr,qv,nm) in zip(ax,[(A,QA,"Zipf α"),(Bt,QB,"Heaps β"),(Rr,QR,"brevity ρ")]):
    axi.hist(arr,bins=30,color="#3b6ea5",alpha=.8)
    axi.axvline(qv,color="#b03a2e",lw=2,label=f"Quran={qv:.3f}")
    axi.set_title(f"{nm}: hadith null vs Quran");axi.legend()
fig.suptitle("Size-matched null (hadith @ 77,429 tokens) vs Quran",fontsize=13)
fig.tight_layout(rect=[0,0,1,0.92]);fig.savefig(os.path.join(OUT,"baseline_sizematched.png"),dpi=140)
print("saved -> output/baseline_sizematched.{json,png}")
