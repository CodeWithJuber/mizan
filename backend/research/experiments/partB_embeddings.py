#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART B — distributional embeddings from the Quran's OWN verse co-occurrence.
Root-root co-occurrence -> PPMI -> truncated SVD -> 100-dim vectors. No pretrained
model (pure distributional hypothesis, fully reproducible). Then: nearest neighbours,
KMeans semantic fields, a 2D map, and a falsifiable 'meaning axis' check.
Honest caveat baked in: distributional vectors capture RELATEDNESS (antonyms can be
close because they share contexts); we test that, we don't hide it."""
import os, re, json, collections
import numpy as np, pandas as pd
from sklearn.decomposition import TruncatedSVD, PCA
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output")
W=pd.read_csv(os.path.join(OUT,"quran_words.csv"))
R=pd.read_csv(os.path.join(OUT,"roots_summary.csv"))

lab=R.set_index("root").to_dict("index")          # root -> {translit,meaning_en,freq,...}
def tag(rt):
    d=lab.get(rt,{}); tr=str(d.get("translit",rt)); en=str(d.get("meaning_en","?"))
    return f"{tr}={en}"

# ---- root–root co-occurrence over verses (unique roots per verse) ----
verses=W.dropna(subset=["root"]).groupby(["sura","aya"])["root"].apply(lambda s:sorted(set(s)))
roots=sorted({r for v in verses for r in v})
idx={r:i for i,r in enumerate(roots)}; n=len(roots)
C=np.zeros((n,n),dtype=np.float64)
for v in verses:
    ii=[idx[r] for r in v]
    for a in range(len(ii)):
        for b in range(a,len(ii)):
            C[ii[a],ii[b]]+=1; 
            if a!=b: C[ii[b],ii[a]]+=1
print(f"roots={n}  verses={len(verses)}  cooc nnz={(C>0).sum()}")

# ---- PPMI ----
tot=C.sum(); rs=C.sum(1,keepdims=True); cs=C.sum(0,keepdims=True)
with np.errstate(divide="ignore",invalid="ignore"):
    P=C/tot; PMI=np.log((P)/((rs/tot)*(cs/tot))); PMI[~np.isfinite(PMI)]=0.0
PPMI=np.maximum(PMI,0.0)
# ---- SVD embeddings ----
k=100; svd=TruncatedSVD(n_components=k,random_state=0); U=svd.fit_transform(PPMI)
E=normalize(U)                                    # L2 -> cosine = dot
print(f"embedding dims={k}  explained var={svd.explained_variance_ratio_.sum():.3f}")

def neigh(rt,m=8):
    if rt not in idx: return []
    s=E@E[idx[rt]]; order=np.argsort(-s)
    return [(roots[j],float(s[j])) for j in order if j!=idx[rt]][:m]

def find_root(*keywords):
    """locate the highest-freq root whose meaning_en matches any keyword regex"""
    pat=re.compile("|".join(keywords),re.I)
    cand=R[R["meaning_en"].astype(str).str.contains(pat,na=False)]
    cand=cand[cand["root"].isin(idx)].sort_values("freq",ascending=False)
    return cand.iloc[0]["root"] if len(cand) else None

want={"Allah":"ʾ-l-h","believe":"ʾ-m-n","disbelieve":"k-f-r","know":"ʿ-l-m",
      "Lord":"r-b-b","say":"q-w-l","guide":"h-d-y","astray":"ḍ-l-l",
      "light":"n-w-r","dark":"ẓ-l-m","prayer":"ṣ-l-w","day":"y-w-m"}
tr2root={str(v.get("translit","")):k for k,v in lab.items()}
seeds={name:tr2root[t] for name,t in want.items() if t in tr2root and tr2root[t] in idx}

print("\n=== NEAREST NEIGHBOURS (distributional, from Quranic co-occurrence) ===")
nn_out={}
for name,rt in seeds.items():
    ns=neigh(rt,7); nn_out[name]={"root":rt,"neighbours":ns}
    print(f"  [{name:10}] {tag(rt)}")
    print("       → "+" | ".join(f"{tag(r)} ({s:.2f})" for r,s in ns))

# ---- KMeans semantic fields (on frequent roots to keep labels meaningful) ----
freqmap=R.set_index("root")["freq"].to_dict()
topR=[r for r in roots if freqmap.get(r,0)>=20]
ti=[idx[r] for r in topR]; Et=E[ti]
K=12; km=KMeans(n_clusters=K,n_init=10,random_state=0).fit(Et)
clusters=collections.defaultdict(list)
for r,c in zip(topR,km.labels_): clusters[c].append(r)
print(f"\n=== {K} SEMANTIC FIELDS (KMeans on {len(topR)} frequent roots) ===")
field_out={}
for c in range(K):
    mem=sorted(clusters[c],key=lambda r:-freqmap.get(r,0))[:6]
    field_out[c]=[tag(r) for r in mem]
    print(f"  field {c:2}: "+" · ".join(tag(r) for r in mem))

# ---- falsifiable meaning-axis check ----
print("\n=== MEANING-AXIS CHECK (falsifiable) ===")
def vec(name): return E[idx[seeds[name]]] if name in seeds else None
pairs=[("believe","disbelieve"),("guide","astray"),("light","dark")]
print("  cosine of opposite-concept pairs (distributional similarity, NOT opposition):")
cos_out={}
for a,b in pairs:
    va,vb=vec(a),vec(b)
    if va is not None and vb is not None:
        c=float(va@vb); cos_out[f"{a}~{b}"]=c
        print(f"    {a:11} ~ {b:11}: cos={c:+.3f}   ({tag(seeds[a])}  vs  {tag(seeds[b])})")
# polarity axis = belief/guidance/light  minus  disbelief/astray/dark
pos=[vec(x) for x in ["believe","guide","light"] if vec(x) is not None]
neg=[vec(x) for x in ["disbelieve","astray","dark"] if vec(x) is not None]
axis_top={}
if pos and neg:
    axis=normalize((np.mean(pos,0)-np.mean(neg,0)).reshape(1,-1))[0]
    proj=E@axis
    order=np.argsort(-proj)
    posend=[tag(roots[j]) for j in order[:8]]
    negend=[tag(roots[j]) for j in order[::-1][:8]]
    axis_top={"positive_end":posend,"negative_end":negend}
    print("  projecting all roots on (faith/guidance/light − disbelief/astray/dark) axis:")
    print("    + end: "+" · ".join(posend))
    print("    − end: "+" · ".join(negend))

json.dump({"nn":nn_out,"fields":field_out,"axis_cosines":cos_out,"axis_ends":axis_top,
           "explained_var":float(svd.explained_variance_ratio_.sum())},
          open(os.path.join(OUT,"embeddings_results.json"),"w"),indent=2,default=float)

# ---- 2D map of top roots ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
showR=[r for r in roots if freqmap.get(r,0)>=60]
si=[idx[r] for r in showR]; XY=PCA(2,random_state=0).fit_transform(E[si])
lab2=km.predict(E[si])
fig,ax=plt.subplots(figsize=(15,11))
sc=ax.scatter(XY[:,0],XY[:,1],c=lab2,cmap="tab20",s=40)
for (x,y),r in zip(XY,showR):
    d=lab.get(r,{}); ax.annotate(str(d.get("translit",r)),(x,y),fontsize=7,alpha=.8)
ax.set_title("Quran root semantic map — PCA of distributional embeddings (label=translit, colour=KMeans field)")
fig.tight_layout(); fig.savefig(os.path.join(OUT,"embeddings_map.png"),dpi=140)
print("\nsaved -> output/embeddings_results.json , output/embeddings_map.png")
