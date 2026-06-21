#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART A — 'Is it special?' Compare Quran vs a matched Classical-Arabic baseline
(hadith: Bukhari+Muslim+AbuDawud) on the SAME unit (normalized surface word forms),
for Zipf, Heaps, and the brevity law. Approximate bootstrap CIs; honest overlap read."""
import json, re, os, math, urllib.request
import numpy as np, pandas as pd
from scipy import stats
from sklearn.metrics import r2_score
rng=np.random.default_rng(42)
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output")

# --- normalization identical to the Quran pipeline ---
_DIAC=re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D4\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")
_MAP=str.maketrans({"\u0671":"\u0627","\u0623":"\u0627","\u0625":"\u0627","\u0622":"\u0627",
    "\u0649":"\u064A","\u0624":"\u0648","\u0626":"\u064A","\u0629":"\u0647","\u0621":""})
ARABIC=re.compile(r"[^\u0621-\u064A]")
def norm_tok(t):
    t=_DIAC.sub("",t).translate(_MAP); t=ARABIC.sub("",t); return t

def zipf_alpha(freqs):
    f=np.sort(np.asarray(freqs,float))[::-1]; r=np.arange(1,len(f)+1)
    a,b=np.polyfit(np.log10(r),np.log10(f),1)
    return -a, r2_score(np.log10(f),a*np.log10(r)+b), f
def heaps_beta(tokens, step=200):
    seen=set(); N=[];V=[]
    for i,t in enumerate(tokens,1):
        seen.add(t)
        if i%step==0: N.append(i);V.append(len(seen))
    N.append(len(tokens));V.append(len(seen))
    N=np.array(N,float);V=np.array(V,float); m=N>=step
    b,c=np.polyfit(np.log10(N[m]),np.log10(V[m]),1)
    return b, r2_score(np.log10(V[m]),b*np.log10(N[m])+c), (N,V,10**c)
def brevity_rho(types):
    L=types["length"].values; F=np.log10(types["freq"].values)
    return stats.spearmanr(L,F).statistic, L, F
def ci(vals,fn,nb=1500):
    out=[]
    for _ in range(nb):
        idx=rng.integers(0,len(vals),len(vals))
        try: out.append(fn(np.asarray(vals)[idx]))
        except Exception: pass
    return float(np.nanpercentile(out,2.5)),float(np.nanpercentile(out,97.5))

# ---------- QURAN (surface forms) ----------
W=pd.read_csv(os.path.join(OUT,"quran_words.csv"))
q_tokens=W["norm"].astype(str).tolist()
qt=W.groupby("norm").agg(freq=("norm","size"),length=("n_letters","first")).reset_index()
qa,qaR2,qf=zipf_alpha(qt["freq"].values)
qb,qbR2,_=heaps_beta(q_tokens)
qr,qL,qF=brevity_rho(qt)
print(f"QURAN  (forms={len(qt)}, tokens={len(q_tokens)})")
print(f"  Zipf α={qa:.3f} (R²={qaR2:.3f}) | Heaps β={qb:.3f} (R²={qbR2:.3f}) | brevity ρ={qr:.3f}")

# ---------- HADITH baseline ----------
print("fetching hadith baseline (Bukhari+Muslim+AbuDawud)…")
h_tokens=[]
for ed in ["ara-bukhari","ara-muslim","ara-abudawud"]:
    u=f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{ed}.min.json"
    d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"r/1"}),timeout=90))
    for h in d["hadiths"]:
        for w in re.split(r"\s+", h.get("text","")):
            t=norm_tok(w)
            if t: h_tokens.append(t)
    print(f"  {ed}: cumulative tokens {len(h_tokens)}")
hc=pd.Series(h_tokens).value_counts()
ht=pd.DataFrame({"form":hc.index,"freq":hc.values}); ht["length"]=ht["form"].str.len()
ha,haR2,hf=zipf_alpha(ht["freq"].values)
hb,hbR2,_=heaps_beta(h_tokens)
hr,_,_=brevity_rho(ht)
print(f"HADITH (forms={len(ht)}, tokens={len(h_tokens)})")
print(f"  Zipf α={ha:.3f} (R²={haR2:.3f}) | Heaps β={hb:.3f} (R²={hbR2:.3f}) | brevity ρ={hr:.3f}")

# ---------- approximate bootstrap CIs ----------
qa_ci=ci(np.c_[np.log10(np.arange(1,len(qf)+1)),np.log10(qf)],
         lambda M:-np.polyfit(M[:,0],M[:,1],1)[0])
ha_ci=ci(np.c_[np.log10(np.arange(1,len(hf)+1)),np.log10(hf)],
         lambda M:-np.polyfit(M[:,0],M[:,1],1)[0])
qr_ci=ci(qt[["length","freq"]].values,lambda M:stats.spearmanr(M[:,0],np.log10(M[:,1])).statistic)
hr_ci=ci(ht[["length","freq"]].values,lambda M:stats.spearmanr(M[:,0],np.log10(M[:,1])).statistic)

print("\n=== COMPARISON (approx 95% CIs) ===")
print(f"  Zipf α   Quran {qa:.3f} [{qa_ci[0]:.3f},{qa_ci[1]:.3f}]   Hadith {ha:.3f} [{ha_ci[0]:.3f},{ha_ci[1]:.3f}]")
print(f"  Heaps β  Quran {qb:.3f}                 Hadith {hb:.3f}")
print(f"  brevity ρ Quran {qr:.3f} [{qr_ci[0]:.3f},{qr_ci[1]:.3f}]  Hadith {hr:.3f} [{hr_ci[0]:.3f},{hr_ci[1]:.3f}]")
def overlap(a,b): return not (a[1]<b[0] or b[1]<a[0])
print(f"  α CIs overlap?  {overlap(qa_ci,ha_ci)}    ρ CIs overlap?  {overlap(qr_ci,hr_ci)}")

res=dict(quran=dict(forms=len(qt),tokens=len(q_tokens),alpha=qa,alpha_ci=qa_ci,beta=qb,rho=qr),
         hadith=dict(forms=len(ht),tokens=len(h_tokens),alpha=ha,alpha_ci=ha_ci,beta=hb,rho=hr),
         alpha_overlap=overlap(qa_ci,ha_ci),rho_overlap=overlap(qr_ci,hr_ci))
json.dump(res,open(os.path.join(OUT,"baseline_results.json"),"w"),indent=2,default=float)

# ---------- figure ----------
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
ax[0].loglog(np.arange(1,len(qf)+1),qf,".",ms=2,label=f"Quran α={qa:.2f}")
ax[0].loglog(np.arange(1,len(hf)+1),hf,".",ms=2,alpha=.5,label=f"Hadith α={ha:.2f}")
ax[0].set_title("Zipf (surface forms)");ax[0].set_xlabel("rank");ax[0].set_ylabel("freq");ax[0].legend()
qN,qV,_=heaps_beta(q_tokens)[2]; hN,hV,_=heaps_beta(h_tokens)[2]
ax[1].loglog(qN,qV,"-",label=f"Quran β={qb:.2f}");ax[1].loglog(hN,hV,"-",alpha=.6,label=f"Hadith β={hb:.2f}")
ax[1].set_title("Heaps (vocab growth)");ax[1].set_xlabel("tokens");ax[1].set_ylabel("distinct forms");ax[1].legend()
ax[2].bar(["Quran","Hadith"],[qr,hr],color=["#b08d57","#3b6ea5"])
ax[2].set_title("Brevity ρ(length, log freq)");ax[2].axhline(0,color="k",lw=.6)
fig.suptitle("Quran vs Classical-Arabic baseline (hadith) — same laws, same unit",fontsize=13)
fig.tight_layout(rect=[0,0,1,0.93]);fig.savefig(os.path.join(OUT,"baseline_compare.png"),dpi=140)
print("saved -> output/baseline_results.json , output/baseline_compare.png")
