#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART E — lemma-level embeddings. At root level, نور(light) and نار(fire) share the
consonantal root ن-و-ر and got merged. Lemmas are distinct words, so they should
separate. Same pipeline (PPMI -> SVD) on LEMMA co-occurrence. We check: does light now
sit with light-words and fire with hell/burning? And we retry the polarity axis with
clean lemma seeds. Honest caveats: lemma vocab is larger and sparser (noisier), and
antonyms still tend to be close distributionally."""
import os, re, json, collections, numpy as np, pandas as pd
from sklearn.decomposition import TruncatedSVD, PCA
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output")
W=pd.read_csv(os.path.join(OUT,"quran_words.csv")).dropna(subset=["lemma"])

# lemma -> majority English gloss + freq (translation aid; meaning kept separate)
W["word_en"]=W["word_en"].astype(str)
gloss=(W.groupby("lemma")["word_en"].agg(lambda s:s.value_counts().idxmax()))
freq=W.groupby("lemma").size()
def tag(l): return f"{l}={gloss.get(l,'?')}"

verses=W.groupby(["sura","aya"])["lemma"].apply(lambda s:sorted(set(s)))
lem=sorted({l for v in verses for l in v}); idx={l:i for i,l in enumerate(lem)}; n=len(lem)
print(f"lemmas={n}  verses={len(verses)}")
C=np.zeros((n,n))
for v in verses:
    ii=[idx[l] for l in v]
    for a in range(len(ii)):
        for b in range(a,len(ii)):
            C[ii[a],ii[b]]+=1
            if a!=b: C[ii[b],ii[a]]+=1
tot=C.sum();rs=C.sum(1,keepdims=True);cs=C.sum(0,keepdims=True)
with np.errstate(divide="ignore",invalid="ignore"):
    PMI=np.log((C/tot)/((rs/tot)*(cs/tot))); PMI[~np.isfinite(PMI)]=0
E=normalize(TruncatedSVD(100,random_state=0).fit_transform(np.maximum(PMI,0)))

def neigh(l,m=8):
    if l not in idx: return []
    s=E@E[idx[l]];o=np.argsort(-s)
    return [(lem[j],float(s[j])) for j in o if j!=idx[l]][:m]
def find_lemma(pat,exclude=None,minf=5):
    p=re.compile(pat,re.I); x=re.compile(exclude,re.I) if exclude else None
    cand=[(l,freq[l]) for l in lem if freq[l]>=minf and p.search(str(gloss[l]))
          and not (x and x.search(str(gloss[l])))]
    cand.sort(key=lambda t:-t[1]); return cand[0][0] if cand else None

want={"believe":(r"\bbeliev",None),"disbelieve":(r"disbeliev|\breject",None),
      "guide":(r"\bguid",None),"astray":(r"astray|\bstray|\berror\b",None),
      "light":(r"\blight\b",r"lighten|lightn|lightning"),"fire":(r"\bfire\b",None),
      "darkness":(r"darkness|\bdark",None),"prayer":(r"\bprayer",None),"mercy":(r"mercy|merciful",None)}
seeds={k:find_lemma(p,x) for k,(p,x) in want.items()}
print("\nresolved seeds (lemma = majority gloss):")
for k,l in seeds.items():
    if l: print(f"  {k:11}-> {tag(l)}  (freq={int(freq[l])})")

print("\n=== KEY TEST: does light separate from fire at lemma level? ===")
for k in ["light","fire","darkness"]:
    if seeds[k]:
        print(f"  [{k:9}] {tag(seeds[k])}")
        print("     → "+" | ".join(f"{tag(l)} ({s:.2f})" for l,s in neigh(seeds[k],6)))

print("\n=== other neighbours ===")
for k in ["believe","disbelieve","guide","astray","prayer","mercy"]:
    if seeds[k]:
        print(f"  [{k:11}] {tag(seeds[k])}")
        print("     → "+" | ".join(f"{tag(l)} ({s:.2f})" for l,s in neigh(seeds[k],6)))

def vec(k): return E[idx[seeds[k]]] if seeds.get(k) else None
print("\n=== polarity axis retry (clean lemma seeds) ===")
pairs=[("believe","disbelieve"),("guide","astray"),("light","darkness")]
cos_out={}
for a,b in pairs:
    va,vb=vec(a),vec(b)
    if va is not None and vb is not None:
        cos_out[f"{a}~{b}"]=float(va@vb)
        print(f"  cos({a},{b})={va@vb:+.3f}")
pos=[vec(x) for x in ["believe","guide","light"] if vec(x) is not None]
neg=[vec(x) for x in ["disbelieve","astray","darkness"] if vec(x) is not None]
ax_out={}
if pos and neg:
    axis=normalize((np.mean(pos,0)-np.mean(neg,0)).reshape(1,-1))[0]
    pr=E@axis;o=np.argsort(-pr)
    pe=[tag(lem[j]) for j in o[:10]]; ne=[tag(lem[j]) for j in o[::-1][:10]]
    ax_out={"positive_end":pe,"negative_end":ne}
    print("  + end (faith/guidance/light): "+" · ".join(pe))
    print("  − end (disbelief/astray/dark): "+" · ".join(ne))

json.dump({"seeds":{k:(seeds[k],str(gloss.get(seeds[k],""))) for k in seeds if seeds[k]},
           "light_neighbours":neigh(seeds["light"],8) if seeds["light"] else [],
           "fire_neighbours":neigh(seeds["fire"],8) if seeds["fire"] else [],
           "axis_cosines":cos_out,"axis_ends":ax_out},
          open(os.path.join(OUT,"lemma_embeddings.json"),"w"),indent=2,default=float)

# 2D map of frequent lemmas
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
show=[l for l in lem if freq[l]>=40]; si=[idx[l] for l in show]
XY=PCA(2,random_state=0).fit_transform(E[si]); cl=KMeans(10,n_init=10,random_state=0).fit_predict(E[si])
fig,ax=plt.subplots(figsize=(15,11)); ax.scatter(XY[:,0],XY[:,1],c=cl,cmap="tab10",s=30)
for (x,y),l in zip(XY,show): ax.annotate(str(gloss[l])[:14],(x,y),fontsize=6,alpha=.8)
ax.set_title("Quran LEMMA semantic map (PCA of distributional embeddings; label=English gloss)")
fig.tight_layout(); fig.savefig(os.path.join(OUT,"lemma_embeddings_map.png"),dpi=140)
print("\nsaved -> output/lemma_embeddings.json , output/lemma_embeddings_map.png")
