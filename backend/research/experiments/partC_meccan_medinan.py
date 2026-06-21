#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PART C — out-of-box + GROUND TRUTH. Can a surah's root-usage predict whether it
is Meccan or Medinan (an external, documented label)? And critically: does the
*vocabulary* carry the signal, or is it only surah length (Medinan surahs are longer)?
Discovery-mode discipline: falsifiable claim, permutation null, CV, length baseline,
robustness to disputed labels, prior-art noted, honest labels. Meaning kept separate."""
import os, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from scipy import stats
rng=np.random.default_rng(0)
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output")
W=pd.read_csv(os.path.join(OUT,"quran_words.csv")); R=pd.read_csv(os.path.join(OUT,"roots_summary.csv"))
lab=R.set_index("root").to_dict("index")
def tag(rt): d=lab.get(rt,{}); return f"{d.get('translit',rt)}={d.get('meaning_en','?')}"

# --- conventional Medinan surahs (a standard list; a handful are disputed) ---
MED={2,3,4,5,8,9,13,22,24,33,47,48,49,55,57,58,59,60,61,62,63,64,65,66,76,98,99,110}
DISPUTED={13,22,55,76,98,99}     # commonly contested; used for a robustness re-run
suras=sorted(W["sura"].unique())
y=np.array([1 if s in MED else 0 for s in suras])
print(f"surahs={len(suras)}  Medinan(label=1)={y.sum()}  Meccan={len(y)-y.sum()}")

# --- features: per-surah length-normalised root relative frequencies (top-K roots) ---
tot=W.groupby("sura").size().reindex(suras)            # words per surah
K=200; topR=R.sort_values("freq",ascending=False)["root"].dropna().head(K).tolist()
cnt=(W[W["root"].isin(topR)].groupby(["sura","root"]).size().unstack(fill_value=0)
       .reindex(index=suras,columns=topR,fill_value=0))
Xvocab=(cnt.values/tot.values[:,None])                 # relative freq -> length removed
Xlen=np.log(tot.values).reshape(-1,1)                  # length-only baseline
Xboth=np.hstack([Xvocab,StandardScaler().fit_transform(Xlen)])

# does length alone track the label? (the confound)
pb=stats.pointbiserialr(y, tot.values)
print(f"length↔Medinan point-biserial r={pb.statistic:.3f} (p={pb.pvalue:.1e})  "
      f"median words Meccan={np.median(tot.values[y==0]):.0f}  Medinan={np.median(tot.values[y==1]):.0f}")

def oof_auc(X,yy,seed=0,C=1.0):
    pipe=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000,C=C,class_weight="balanced"))
    skf=StratifiedKFold(5,shuffle=True,random_state=seed)
    proba=cross_val_predict(pipe,X,yy,cv=skf,method="predict_proba")[:,1]
    return roc_auc_score(yy,proba), proba

# observed AUCs (averaged over seeds)
def mean_auc(X,yy,nseed=8,**kw):
    a=[oof_auc(X,yy,seed=s,**kw)[0] for s in range(nseed)]; return float(np.mean(a)),float(np.std(a))
auc_len=mean_auc(Xlen,y); auc_voc=mean_auc(Xvocab,y); auc_both=mean_auc(Xboth,y)
print("\n=== cross-validated ROC-AUC (5-fold, 8 seeds) ===")
print(f"  length-only : {auc_len[0]:.3f} ± {auc_len[1]:.3f}")
print(f"  vocabulary  : {auc_voc[0]:.3f} ± {auc_voc[1]:.3f}   (length-normalised features)")
print(f"  vocab+length: {auc_both[0]:.3f} ± {auc_both[1]:.3f}")

# permutation null for the vocabulary model (the key claim)
obs=oof_auc(Xvocab,y,seed=0)[0]; B=500; null=np.empty(B)
for i in range(B):
    yp=rng.permutation(y); null[i]=oof_auc(Xvocab,yp,seed=0)[0]
p=(np.sum(null>=obs)+1)/(B+1)
print(f"\nPERMUTATION NULL (vocab, B={B}): obs AUC={obs:.3f}  null={null.mean():.3f}±{null.std():.3f}  "
      f"max null={null.max():.3f}  p={p:.4f}")

# unsupervised: does a 2-way split emerge that matches Meccan/Medinan? (out-of-box)
km=KMeans(2,n_init=10,random_state=0).fit(StandardScaler().fit_transform(Xvocab)).labels_
ari=adjusted_rand_score(y,km)
# also is the unsupervised split just tracking length?
ari_len=adjusted_rand_score((tot.values>np.median(tot.values)).astype(int),km)
print(f"\nUNSUPERVISED KMeans(2) on vocabulary:  ARI vs Meccan/Medinan = {ari:.3f}   "
      f"ARI vs (long/short) = {ari_len:.3f}")

# robustness: drop disputed surahs, redo vocab AUC
keep=[i for i,s in enumerate(suras) if s not in DISPUTED]
auc_voc_rob=mean_auc(Xvocab[keep],y[keep])
print(f"ROBUSTNESS (drop {len(DISPUTED)} disputed surahs): vocab AUC={auc_voc_rob[0]:.3f} ± {auc_voc_rob[1]:.3f}")

# interpretable markers: logistic on all data, top coefficients
pipe=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,class_weight="balanced")).fit(Xvocab,y)
coef=pipe.named_steps["logisticregression"].coef_[0]
ordr=np.argsort(coef)
med_markers=[tag(topR[j]) for j in ordr[::-1][:10]]
mec_markers=[tag(topR[j]) for j in ordr[:10]]
print("\nTOP MEDINAN-leaning roots:", " · ".join(med_markers))
print("TOP MECCAN-leaning roots :", " · ".join(mec_markers))

res=dict(n=len(suras),n_medinan=int(y.sum()),
   length_pointbiserial=float(pb.statistic),
   auc_length=auc_len,auc_vocab=auc_voc,auc_both=auc_both,auc_vocab_robust=auc_voc_rob,
   perm_obs=float(obs),perm_null_mean=float(null.mean()),perm_null_max=float(null.max()),perm_p=float(p),
   ari_vs_period=float(ari),ari_vs_length=float(ari_len),
   medinan_markers=med_markers,meccan_markers=mec_markers)
json.dump(res,open(os.path.join(OUT,"meccan_medinan_results.json"),"w"),indent=2,default=float)

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,2,figsize=(13,4.8))
ax[0].bar(["length\nonly","vocabulary","vocab+\nlength"],[auc_len[0],auc_voc[0],auc_both[0]],
          yerr=[auc_len[1],auc_voc[1],auc_both[1]],color=["#9aa0a6","#b08d57","#3b6ea5"],capsize=4)
ax[0].axhline(0.5,color="k",lw=.7,ls="--"); ax[0].set_ylim(0.4,1.0); ax[0].set_ylabel("CV ROC-AUC")
ax[0].set_title("Predicting Meccan/Medinan")
ax[1].hist(null,bins=30,color="#9aa0a6",alpha=.85); ax[1].axvline(obs,color="#b03a2e",lw=2,label=f"observed={obs:.2f}")
ax[1].set_title(f"Vocabulary vs label-permutation null (p={p:.3f})"); ax[1].set_xlabel("AUC"); ax[1].legend()
fig.tight_layout(); fig.savefig(os.path.join(OUT,"meccan_medinan.png"),dpi=140)
print("\nsaved -> output/meccan_medinan_results.json , output/meccan_medinan.png")
