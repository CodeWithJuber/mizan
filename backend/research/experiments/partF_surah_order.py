#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART F — does surah ORDER carry a vocabulary gradient? Mantel test: correlate the
114x114 surah vocabulary-distance matrix with the position-distance matrix, for (a) the
canonical mushaf order and (b) the Egyptian-standard chronological (nuzul) order.
Permutation null on surah<->position assignment. Plus: project surahs on PC1 of
vocabulary and correlate with mushaf position / chronological position / length, to
expose the length confound. Out-of-box question: which arrangement better explains the
vocabulary gradient. Honest labels; meaning kept separate."""
import os, json, numpy as np, pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_distances
rng=np.random.default_rng(3)
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output")
W=pd.read_csv(os.path.join(OUT,"quran_words.csv")); R=pd.read_csv(os.path.join(OUT,"roots_summary.csv"))
suras=sorted(W["sura"].unique())

# features: per-surah top-K root relative frequencies (length-normalised)
tot=W.groupby("sura").size().reindex(suras); K=200
topR=R.sort_values("freq",ascending=False)["root"].dropna().head(K).tolist()
cnt=(W[W["root"].isin(topR)].groupby(["sura","root"]).size().unstack(fill_value=0)
       .reindex(index=suras,columns=topR,fill_value=0))
X=cnt.values/tot.values[:,None]
Dv=cosine_distances(X)                               # vocabulary distance 114x114

# Egyptian-standard chronological (nuzul) order — convention; variants exist
CHRON=[96,68,73,74,1,111,81,87,92,89,93,94,103,100,108,102,107,109,105,113,114,112,53,
80,97,91,85,95,106,101,75,104,77,50,90,86,54,38,7,72,36,25,35,19,20,56,26,27,28,17,10,
11,12,15,6,37,31,34,39,40,41,42,43,44,45,46,51,88,18,16,71,14,21,23,32,52,67,69,70,78,
79,82,84,30,29,83,2,8,3,33,60,4,99,57,47,13,55,76,65,98,59,24,22,63,58,49,66,64,61,62,48,5,9,110]
assert sorted(CHRON)==list(range(1,115)), "chronological list is not a valid permutation!"

def posdist(order):
    rankmap={s:i for i,s in enumerate(order)}
    r=np.array([rankmap[s] for s in suras],float)
    return np.abs(r[:,None]-r[None,:])
def mantel(Dx,Dy,B=2000):
    iu=np.triu_indices_from(Dx,1); x=Dx[iu]; y=Dy[iu]
    obs=stats.pearsonr(x,y).statistic
    idx=np.arange(Dx.shape[0]); null=np.empty(B)
    for b in range(B):
        p=rng.permutation(idx); yp=Dy[np.ix_(p,p)][iu]
        null[b]=stats.pearsonr(x,yp).statistic
    pval=(np.sum(null>=obs)+1)/(B+1)             # one-sided positive
    return obs,pval,null

res={}
print("=== MANTEL: vocabulary-distance vs position-distance ===")
for nm,order in [("mushaf",suras),("chronological",CHRON)]:
    Dp=posdist(order); r,p,null=mantel(Dv,Dp)
    res[nm]=dict(mantel_r=float(r),p=float(p),null_mean=float(null.mean()),null_sd=float(null.std()))
    print(f"  {nm:13}: Mantel r={r:+.3f}  p={p:.4f}  (null {null.mean():+.3f}±{null.std():.3f})")

# PC1 vs position / length (length confound)
pc1=PCA(2,random_state=0).fit_transform(X)[:,0]
length=tot.values.astype(float)
mpos=np.array([suras.index(s) for s in suras],float)          # = 0..113 (mushaf)
cpos=np.array([CHRON.index(s) for s in suras],float)          # chronological rank
def sp(a,b): r=stats.spearmanr(a,b); return float(r.statistic),float(r.pvalue)
res["pc1"]=dict(vs_mushaf_pos=sp(pc1,mpos),vs_chron_pos=sp(pc1,cpos),vs_length=sp(pc1,length),
                length_vs_mushaf=sp(length,mpos),length_vs_chron=sp(length,cpos))
print("\n=== PC1 of vocabulary — Spearman ρ (statistic, p) ===")
print(f"  PC1 vs mushaf position  : {res['pc1']['vs_mushaf_pos']}")
print(f"  PC1 vs chrono position  : {res['pc1']['vs_chron_pos']}")
print(f"  PC1 vs surah length     : {res['pc1']['vs_length']}")
print(f"  length vs mushaf position: {res['pc1']['length_vs_mushaf']}")
print(f"  length vs chrono position: {res['pc1']['length_vs_chron']}")

json.dump(res,open(os.path.join(OUT,"surah_order.json"),"w"),indent=2,default=float)

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,2,figsize=(14,5.2))
for nm,order,c in [("mushaf",suras,"#b08d57"),("chronological",CHRON,"#3b6ea5")]:
    Dp=posdist(order); iu=np.triu_indices_from(Dv,1)
    ax[0].scatter(Dp[iu],Dv[iu],s=2,alpha=.15,color=c,label=f"{nm} (r={res[nm]['mantel_r']:+.2f})")
ax[0].set_xlabel("position distance |i−j|"); ax[0].set_ylabel("vocabulary distance (1−cos)")
ax[0].set_title("Surah vocab distance vs order distance"); ax[0].legend()
ax[1].scatter(cpos,pc1,s=22,color="#3b6ea5",label="by chrono position")
ax[1].scatter(mpos,pc1,s=22,color="#b08d57",alpha=.6,label="by mushaf position")
ax[1].set_xlabel("surah position (rank)"); ax[1].set_ylabel("vocabulary PC1")
ax[1].set_title("Vocabulary PC1 along the two orderings"); ax[1].legend()
fig.tight_layout(); fig.savefig(os.path.join(OUT,"surah_order.png"),dpi=140)
print("\nsaved -> output/surah_order.json , output/surah_order.png")
