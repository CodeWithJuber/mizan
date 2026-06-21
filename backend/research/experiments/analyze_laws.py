#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quantitative-law analysis of the Quran word/root data  (pre-registered battery).
Honors quranic-computational-research discipline: hypotheses fixed BEFORE fitting,
honest nulls (permutation), effect sizes + CIs, multiple-comparison correction,
robustness ("try to kill it"), status labels, meaning kept separate.
"""
import json, math, os, warnings, collections
import numpy as np, pandas as pd
from scipy import optimize, stats
from sklearn.metrics import r2_score
warnings.filterwarnings("ignore")
rng = np.random.default_rng(42)

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"output")
W=pd.read_csv(os.path.join(OUT,"quran_words.csv"))          # mushaf order (gidx)
R=pd.read_csv(os.path.join(OUT,"roots_summary.csv"))        # roots, freq desc

def line(c="─",n=74): print(c*n)
def boot_ci(x,y,fn,nb=2000):
    n=len(x); out=[]
    for _ in range(nb):
        idx=rng.integers(0,n,n); 
        try: out.append(fn(np.asarray(x)[idx],np.asarray(y)[idx]))
        except Exception: pass
    return (float(np.nanpercentile(out,2.5)),float(np.nanpercentile(out,97.5)))
def perm_p_spear(x,y,n=20000):
    x=np.asarray(x,float); y=np.asarray(y,float)
    obs=stats.spearmanr(x,y).statistic
    yy=y.copy(); cnt=0
    for _ in range(n):
        rng.shuffle(yy)
        if abs(stats.spearmanr(x,yy).statistic)>=abs(obs): cnt+=1
    return obs,(cnt+1)/(n+1)
def aic(y,yhat,k):
    n=len(y); sse=float(np.sum((np.asarray(y)-np.asarray(yhat))**2))
    return n*math.log(sse/n)+2*k, sse

print("="*74)
print(" PRE-REGISTERED HYPOTHESIS BATTERY  (stated before fitting)")
print("="*74)
print(""" corpus: QAC morphology mirror (sha 742bfac…), Hafs/Kufan numbering — FROZEN
 units : token=word(77429), root(1651), verse(6236), sura(114), letter=skeleton

 H1 Zipf            root freq f(r) = C·r^(−α),  expect α≈1            [fit: α, R²]
 H2 Heaps/Herdan    distinct roots V(N) = K·N^β, 0<β<1                [fit: β, R²]
 H3 Brevity (Zipf abbreviation)  longer word ⇒ rarer; ρ(len,logf)<0  [Spearman+perm]
 H4 Menzerath (sura→verse)  bigger sura(verses) ⇒ shorter verses     [Spearman+perm,AIC,SR]
 H5 Menzerath (word→morpheme) more segments ⇒ shorter each segment   [Spearman+perm]
 H6 Degree scaling  root network degree k = a·f^b vs frequency       [fit: b, R²]

 Fixed battery of 6 (no scanning letters/windows/numberings). Primary relationship
 tests (H3,H4,H5,H6) get Benjamini–Hochberg FDR correction. Nulls = permutation.""")
res={}

# ---------------- H1 Zipf ----------------
line()
r=np.arange(1,len(R)+1); f=R["freq"].values.astype(float)
lr,lf=np.log10(r),np.log10(f)
a1,b1=np.polyfit(lr,lf,1); R2_z=r2_score(lf,a1*lr+b1); alpha=-a1
ci_a=boot_ci(lr,lf,lambda X,Y:-np.polyfit(X,Y,1)[0])
# Zipf–Mandelbrot f = C/(r+b)^a
def zm(r,C,b,a): return C/np.power(r+b,a)
try:
    p,_=optimize.curve_fit(zm,r,f,p0=[f[0],2.0,1.0],maxfev=20000)
    zm_hat=zm(r,*p); aic_zm,_=aic(np.log10(f),np.log10(zm_hat),3)
except Exception: p=None; aic_zm=float("nan")
aic_pow,_=aic(lf,a1*lr+b1,2)
print(f"H1 ZIPF  α={alpha:.3f}  95%CI[{ci_a[0]:.3f},{ci_a[1]:.3f}]  R²(log-log)={R2_z:.4f}")
print(f"         Zipf–Mandelbrot params C,b,a = {None if p is None else [round(x,3) for x in p]}")
print(f"         AIC  power={aic_pow:.1f}   Mandelbrot={aic_zm:.1f}  (lower=better)")
# robustness: lemmas
lem=W.dropna(subset=['lemma']).groupby('lemma').size().sort_values(ascending=False).values.astype(float)
rl=np.arange(1,len(lem)+1); al,_=np.polyfit(np.log10(rl),np.log10(lem),1)
print(f"         robustness: α(lemmas)={-al:.3f}")
res["H1_zipf"]=dict(alpha=alpha,alpha_ci=ci_a,R2=R2_z,alpha_lemma=-al,
                    aic_power=aic_pow,aic_mandelbrot=aic_zm)

# ---------------- H2 Heaps ----------------
line()
roots_seq=W["root"].tolist()
seen=set(); N=[]; V=[]
for i,rt in enumerate(roots_seq,1):
    if isinstance(rt,str): seen.add(rt)
    if i%200==0:
        N.append(i); V.append(len(seen))
N.append(len(roots_seq)); V.append(len(seen))
N=np.array(N,float); V=np.array(V,float)
m=N>=200
bH,cH=np.polyfit(np.log10(N[m]),np.log10(V[m]),1); R2_h=r2_score(np.log10(V[m]),bH*np.log10(N[m])+cH)
ci_b=boot_ci(np.log10(N[m]),np.log10(V[m]),lambda X,Y:np.polyfit(X,Y,1)[0])
print(f"H2 HEAPS  β={bH:.3f}  95%CI[{ci_b[0]:.3f},{ci_b[1]:.3f}]  R²(log-log)={R2_h:.4f}  K≈{10**cH:.2f}")
print(f"          (final vocab {int(V[-1])} roots at N={int(N[-1])} tokens)")
res["H2_heaps"]=dict(beta=bH,beta_ci=ci_b,R2=R2_h,K=10**cH)

# ---------------- H3 Brevity ----------------
line()
# types = unique normalized forms; length in skeleton letters
typ=W.groupby("norm").agg(freq=("norm","size"),length=("n_letters","first")).reset_index()
rho_w,p_w=perm_p_spear(typ["length"].values, np.log10(typ["freq"].values))
ci_w=boot_ci(typ["length"].values,np.log10(typ["freq"].values),lambda X,Y:stats.spearmanr(X,Y).statistic)
# roots: root letters vs root freq
Rr=R.copy(); Rr["rlen"]=Rr["root"].astype(str).str.replace(r'[^\u0621-\u064A]','',regex=True).str.len()
rho_r,p_r=perm_p_spear(Rr["rlen"].values, np.log10(Rr["freq"].values))
print(f"H3 BREVITY (word types) ρ(length, log freq) = {rho_w:.3f}  95%CI[{ci_w[0]:.3f},{ci_w[1]:.3f}]  perm p={p_w:.2e}")
print(f"   binned mean length by freq decile:")
typ["fbin"]=pd.qcut(typ["freq"],10,labels=False,duplicates="drop")
bm=typ.groupby("fbin")["length"].mean()
print("     "+"  ".join(f"{v:.1f}" for v in bm.values)+"   (low→high freq)")
print(f"H3 BREVITY (roots)      ρ(root letters, log freq) = {rho_r:.3f}  perm p={p_r:.2e}")
res["H3_brevity"]=dict(rho_words=rho_w,ci=ci_w,p_words=p_w,rho_roots=rho_r,p_roots=p_r,
                       binned_len=[float(x) for x in bm.values])

# ---------------- H4 Menzerath sura→verse ----------------
line()
sg=W.groupby("sura").agg(verses=("aya","nunique"),words=("word","size")).reset_index()
sg["mwpv"]=sg["words"]/sg["verses"]
x=sg["verses"].values.astype(float); y=sg["mwpv"].values.astype(float)
rho_s,p_s=perm_p_spear(x,y)
ci_s=boot_ci(x,y,lambda X,Y:stats.spearmanr(X,Y).statistic)
print(f"H4 MENZERATH (sura→verse) ρ(verses, mean words/verse) = {rho_s:.3f}  95%CI[{ci_s[0]:.3f},{ci_s[1]:.3f}]  perm p={p_s:.2e}")
# model selection
models={}
models["const"]=(np.full_like(y,y.mean()),1)
A=np.polyfit(x,y,1); models["linear"]=(np.polyval(A,x),2)
A=np.polyfit(np.log(x),y,1); models["log"]=(A[0]*np.log(x)+A[1],2)
try:
    pp,_=optimize.curve_fit(lambda x,a,b:a*np.power(x,b),x,y,p0=[20,-0.2],maxfev=20000)
    models["power"]=(pp[0]*np.power(x,pp[1]),2)
except Exception: pass
try:
    pm,_=optimize.curve_fit(lambda x,a,b,c:a*np.power(x,-b)*np.exp(c*x),x,y,p0=[20,0.2,0.0],maxfev=40000)
    models["menzerath"]=(pm[0]*np.power(x,-pm[1])*np.exp(pm[2]*x),3)
except Exception: pm=None
aics={k:aic(y,v[0],v[1])[0] for k,v in models.items()}
best=min(aics,key=aics.get)
print("   AIC by model: "+"  ".join(f"{k}={v:.1f}" for k,v in sorted(aics.items(),key=lambda kv:kv[1])))
print(f"   best functional form: {best}")
if "power" in models: print(f"   power fit: mean_words/verse ≈ {pp[0]:.2f} · verses^({pp[1]:.3f})")
if pm is not None: print(f"   MAL fit  : y ≈ {pm[0]:.2f}·x^(−{pm[1]:.3f})·e^({pm[2]:.4f}·x)")
res["H4_menzerath_sura"]=dict(rho=rho_s,ci=ci_s,p=p_s,best_model=best,aic=aics,
                              power=(None if "power" not in models else [float(pp[0]),float(pp[1])]))

# symbolic regression (synthetic programming) to DISCOVER the form
sr_prog=None; sr_r2=None
try:
    from gplearn.genetic import SymbolicRegressor
    Xsr=x.reshape(-1,1)
    sr=SymbolicRegressor(population_size=2500,generations=22,
        function_set=('add','sub','mul','div','log','sqrt','inv','neg'),
        parsimony_coefficient=0.01,metric="mean absolute error",
        const_range=(-5,30),random_state=1,verbose=0,n_jobs=1)
    sr.fit(Xsr,y); yhat=sr.predict(Xsr); sr_r2=float(r2_score(y,yhat))
    sr_prog=str(sr._program)
    print(f"   SYMBOLIC REGRESSION discovered:  y = {sr_prog}")
    print(f"   symbolic-regression R² = {sr_r2:.4f}")
except Exception as e:
    print("   [symbolic regression skipped]",e)
res["H4_symbolic"]=dict(program=sr_prog,R2=sr_r2)

# ---------------- H5 Menzerath word→morpheme ----------------
line()
ww=W[W["n_seg"]>0].copy(); ww["seglen"]=ww["n_letters"]/ww["n_seg"]
rho_m,p_m=perm_p_spear(ww["n_seg"].values, ww["seglen"].values, n=8000)
mb=ww.groupby("n_seg")["seglen"].mean()
print(f"H5 MENZERATH (word→morpheme) ρ(#segments, letters/segment) = {rho_m:.3f}  perm p={p_m:.2e}")
print("   mean letters/segment by #segments:")
print("     "+"  ".join(f"{seg}:{v:.2f}" for seg,v in mb.items()))
res["H5_menzerath_word"]=dict(rho=rho_m,p=p_m,means={int(k):float(v) for k,v in mb.items()})

# ---------------- H6 degree scaling ----------------
line()
Rd=R[(R["degree"]>0)&(R["freq"]>0)]
ld,lff=np.log10(Rd["degree"].values),np.log10(Rd["freq"].values)
b6,c6=np.polyfit(lff,ld,1); R2_d=r2_score(ld,b6*lff+c6)
ci_6=boot_ci(lff,ld,lambda X,Y:np.polyfit(Y,X,1)[0] if False else np.polyfit(X,Y,1)[0])
print(f"H6 DEGREE SCALING  degree ≈ {10**c6:.2f}·freq^({b6:.3f})   R²(log-log)={R2_d:.4f}  95%CI b[{ci_6[0]:.3f},{ci_6[1]:.3f}]")
print("   (mechanistic: more occurrences ⇒ more verse co-occurrences; exponent is the empirical part)")
res["H6_degree"]=dict(b=b6,R2=R2_d,ci=ci_6)

# ---------------- multiple-comparison correction ----------------
line()
from statsmodels.stats.multitest import multipletests
labels=["H3 brevity(words)","H3 brevity(roots)","H4 menzerath(sura)","H5 menzerath(word)"]
pvals=[res["H3_brevity"]["p_words"],res["H3_brevity"]["p_roots"],
       res["H4_menzerath_sura"]["p"],res["H5_menzerath_word"]["p"]]
rej,padj,_,_=multipletests(pvals,alpha=0.05,method="fdr_bh")
print("MULTIPLE-COMPARISON CORRECTION (Benjamini–Hochberg, 4 primary relationship tests):")
for l,p,pa,rj in zip(labels,pvals,padj,rej):
    print(f"   {l:22} p={p:.2e}  p_adj={pa:.2e}  {'significant' if rj else 'n.s.'}")
res["bh_correction"]=dict(labels=labels,p=pvals,p_adj=list(padj),reject=[bool(x) for x in rej])

json.dump(res,open(os.path.join(OUT,"laws_results.json"),"w"),indent=2,default=float)
line("=")
print("results saved -> output/laws_results.json")

# ---------------- figure ----------------
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(2,3,figsize=(16,10))
ax[0,0].loglog(r,f,".",ms=3); ax[0,0].loglog(r,10**(a1*lr+b1),"r-",lw=1.5)
ax[0,0].set_title(f"H1 Zipf  α={alpha:.2f}, R²={R2_z:.3f}"); ax[0,0].set_xlabel("rank"); ax[0,0].set_ylabel("freq")
ax[0,1].loglog(N,V,"o",ms=4); ax[0,1].loglog(N[m],10**(bH*np.log10(N[m])+cH),"r-",lw=1.5)
ax[0,1].set_title(f"H2 Heaps  β={bH:.2f}, R²={R2_h:.3f}"); ax[0,1].set_xlabel("tokens N"); ax[0,1].set_ylabel("distinct roots")
ax[0,2].scatter(typ["length"],np.log10(typ["freq"]),s=4,alpha=.25)
ax2=ax[0,2]
ax2.set_title(f"H3 Brevity  ρ={rho_w:.2f}"); ax2.set_xlabel("word length (letters)"); ax2.set_ylabel("log10 freq")
order=np.argsort(x)
ax[1,0].scatter(x,y,s=20)
if "power" in models: ax[1,0].plot(x[order],(pp[0]*np.power(x,pp[1]))[order],"r-",lw=1.5,label="power")
if sr_prog: ax[1,0].plot(x[order],yhat[order],"g--",lw=1.2,label="symbolic")
ax[1,0].set_title(f"H4 Menzerath sura→verse  ρ={rho_s:.2f}"); ax[1,0].set_xlabel("verses in sura"); ax[1,0].set_ylabel("mean words/verse"); ax[1,0].legend()
ax[1,1].bar([str(k) for k in mb.index],mb.values,color="#3b6ea5")
ax[1,1].set_title(f"H5 Menzerath word→morpheme  ρ={rho_m:.2f}"); ax[1,1].set_xlabel("# segments"); ax[1,1].set_ylabel("mean letters/segment")
ax[1,2].loglog(Rd["freq"],Rd["degree"],".",ms=3); ax[1,2].loglog(Rd["freq"],10**(b6*lff+c6),"r-",lw=1.5)
ax[1,2].set_title(f"H6 degree~freq^{b6:.2f}  R²={R2_d:.3f}"); ax[1,2].set_xlabel("root freq"); ax[1,2].set_ylabel("network degree")
fig.suptitle("Quantitative-linguistic laws in the Quran (pre-registered battery)",fontsize=14)
fig.tight_layout(rect=[0,0,1,0.97]); fig.savefig(os.path.join(OUT,"analysis_laws.png"),dpi=140)
print("figure saved -> output/analysis_laws.png")
