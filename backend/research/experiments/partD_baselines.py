#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART D — multiple baselines. Earlier the Quran looked high-β (faster vocab growth)
and weak-ρ (weaker brevity) vs hadith. Was that genre-specific? Here we add two more
Classical-Arabic registers: classical poetry (arbml/ashaar, فصيح) and exegetical prose
(Tabari). For each register we build a size-matched null (n=77,429) of Zipf α / Heaps β
/ brevity ρ and see where the Quran falls. Honest read: is the Quran consistent across
registers, or does it just sit somewhere in the normal Arabic spread?"""
import os, json, numpy as np, pandas as pd
from scipy import stats
rng=np.random.default_rng(11)
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output"); DATA=os.path.join(HERE,"data")

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
    s=pd.Series(tokens).value_counts(); L=[len(x) for x in s.index]
    return stats.spearmanr(L,np.log10(s.values)).statistic

# ---- Quran reference (surface forms) ----
W=pd.read_csv(os.path.join(OUT,"quran_words.csv")); q=W["norm"].astype(str).tolist()
QA,QB,QR=alpha(q),beta(q),rho(q); n=len(q)
print(f"QURAN (forms, n={n}): Zipf α={QA:.3f}  Heaps β={QB:.3f}  brevity ρ={QR:.3f}\n")

pools={"hadith":"hadith_tokens.txt","poetry":"poetry_tokens.txt","tabari":"tabari_tokens.txt"}
# None of the pools is shipped (backend/research/datasets/LICENSES.md). partA2_sizematched.py
# builds the hadith pool from fawazahmed0/hadith-api; the poetry and Tabari samples have no
# documented source, so a run without them skips those registers.
missing=[name for name,fn in pools.items() if not os.path.exists(os.path.join(DATA,fn))]
for name in missing:
    print(f"[i] {name}: {os.path.join(DATA,pools.pop(name))} not found, skipped")
B=200; res={"quran":dict(alpha=QA,beta=QB,rho=QR,n=n),"baselines":{}}
NULLS={}
for name,fn in pools.items():
    h=np.array([x for x in open(os.path.join(DATA,fn),encoding="utf-8").read().split("\n") if x],dtype=object)
    A=np.empty(B);Bt=np.empty(B);Rr=np.empty(B)
    for i in range(B):
        idx=rng.choice(len(h),n,replace=False); s=h[idx]
        A[i]=alpha(s);Bt[i]=beta(s);Rr[i]=rho(s)
    NULLS[name]=(A,Bt,Rr)
    def zp(v,arr): return (v-arr.mean())/arr.std(),float((np.sum(arr<=v)+0.5)/len(arr))
    za,pa=zp(QA,A);zb,pb=zp(QB,Bt);zr,pr=zp(QR,Rr)
    res["baselines"][name]=dict(pool=len(h),
        alpha=dict(null_mean=float(A.mean()),null_sd=float(A.std()),z=float(za),pct=pa),
        beta =dict(null_mean=float(Bt.mean()),null_sd=float(Bt.std()),z=float(zb),pct=pb),
        rho  =dict(null_mean=float(Rr.mean()),null_sd=float(Rr.std()),z=float(zr),pct=pr))
    print(f"[{name:7}] pool={len(h):>8}")
    print(f"   Zipf α : null {A.mean():.3f}±{A.std():.3f}  z={za:+6.2f}  pct={pa:.3f}")
    print(f"   Heaps β: null {Bt.mean():.3f}±{Bt.std():.3f}  z={zb:+6.2f}  pct={pb:.3f}")
    print(f"   brevity ρ: null {Rr.mean():.3f}±{Rr.std():.3f}  z={zr:+6.2f}  pct={pr:.3f}")

json.dump(res,open(os.path.join(OUT,"baselines_multi.json"),"w"),indent=2,default=float)

# verdict helper
print("\n=== VERDICT (is Quran consistently extreme across registers?) ===")
for stat,qv,key in [("Zipf α",QA,"alpha"),("Heaps β",QB,"beta"),("brevity ρ",QR,"rho")]:
    line=f"  {stat:9} Quran={qv:+.3f} | "+" | ".join(
        f"{nm}: null {res['baselines'][nm][key]['null_mean']:+.3f} (z={res['baselines'][nm][key]['z']:+.1f})"
        for nm in pools)
    print(line)

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
col={"hadith":"#3b6ea5","poetry":"#2e8b57","tabari":"#9b59b6"}
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
for axi,(j,nm) in zip(ax,enumerate(["Zipf α","Heaps β","brevity ρ"])):
    qv=[QA,QB,QR][j]
    for reg in pools:
        axi.hist(NULLS[reg][j],bins=22,alpha=.5,color=col[reg],label=reg)
    axi.axvline(qv,color="#b03a2e",lw=2.4,label=f"Quran={qv:.3f}")
    axi.set_title(f"{nm}: register nulls vs Quran"); axi.legend(fontsize=8)
fig.suptitle("Quran vs three Classical-Arabic registers (size-matched nulls, n=77,429)",fontsize=13)
fig.tight_layout(rect=[0,0,1,0.93]); fig.savefig(os.path.join(OUT,"baselines_multi.png"),dpi=140)
print("\nsaved -> output/baselines_multi.json , output/baselines_multi.png")
