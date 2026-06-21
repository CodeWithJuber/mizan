#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quran Word-by-Word Analyzer  —  "Sifar Se Sarhad" toolkit  (v2: + English layer)
================================================================================
Walks EVERY word of the Quran in mushaf order (word #1 بِسْمِ at 1:1:1 ...
word #77429 ٱلنَّاسِ at 114:6:3) and, per word, gives:

  position    : sura, aya, word-in-aya, GLOBAL index (1..77429)
  ARABIC      : full diacritised form, skeleton, normalised type
  ENGLISH     : transliteration + word meaning *in this context*           (word-by-word translation)
  morphology  : root (Arabic + transliteration + English meaning), lemma, POS
  meaning     : word_en (context), root_en (representative), root_en_here (root meaning HERE)
  frequency   : form / normalised / lemma / ROOT
  energy       : (A) information content  I = -log2 p  [surprisal, bits]    << empirical
                (B) abjad numeric value (eastern gematria)                   << traditional, exploratory
  context     : previous & next word (Arabic + English), collocate roots (Arabic + English)
  topology    : the word's ROOT in the verse co-occurrence network
                (degree, weighted degree, clustering, eigenvector, PageRank)

Corpus outputs: entropy/perplexity, Zipf curves, top-roots chart, root network.

DATA
----
* Morphology/roots : Quranic Arabic Corpus (QAC), Arabic-script mirror  -> data/qac_raw.txt
* Word translit + word meaning : Quran.com word-by-word English (api.quran.com v4),
                                 cached to data/wbw_en.json  (77,429 words, keyed s:a:word)
SHA-256 of the morphology file is stored in summary.json for reproducibility.

EPISTEMIC LABELS  (keep these straight)
---------------------------------------
* ESTABLISHED / empirical : frequency, information content, entropy, Zipf, all graph metrics.
* TRADITIONAL / exploratory : abjad. Convention-dependent (ة/ى/hamza differ between systems).
  Included for the Hisab-e-Mizan toolkit; NOT a validated "energy"; never a proof.
* MEANING : word_en is a word-by-word TRANSLATION (a translation aid, human dataset, cited).
  root_en is DERIVED (majority gloss of that root's occurrences) — a distributional summary,
  not a dictionary entry. root_en_here = this occurrence's gloss = the root's sense in context.
  Tafsir-grade meaning is transmission, not arithmetic. A count/gloss describes; it does not
  legislate doctrine. For real tafsir use the Quran.com tafsir tools.

Usage
-----
    python quran_word_analyzer.py demo                 # build + plots + sample dossiers (default)
    python quran_word_analyzer.py build
    python quran_word_analyzer.py report 1:2:1         # full dossier (English + Arabic)
    python quran_word_analyzer.py report --index 5
    python quran_word_analyzer.py graph-root حمد --label english
    python quran_word_analyzer.py plots --label english
    flags: --start --end | --betweenness | --label {arabic,latin,english}
"""
from __future__ import annotations
import argparse, json, math, os, re, sys, hashlib, collections
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT  = os.path.join(HERE, "output")
QAC_FILE    = os.path.join(DATA, "qac_raw.txt")
WBW_FILE    = os.path.join(DATA, "wbw_en.json")     # word-by-word translit + meaning
ARABIC_FONT = os.path.join(DATA, "arabic_font.ttf")
os.makedirs(OUT, exist_ok=True)

# --------------------------------------------------------------------------- #
#  Arabic helpers
# --------------------------------------------------------------------------- #
_DIAC = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D4\u06D6-\u06DC"
                   "\u06DF-\u06E8\u06EA-\u06ED\u0640]")
def strip_diac(s: str) -> str:
    return _DIAC.sub("", s)

_NORM_MAP = str.maketrans({
    "\u0671":"\u0627","\u0623":"\u0627","\u0625":"\u0627","\u0622":"\u0627",  # ٱأإآ->ا
    "\u0649":"\u064A","\u0624":"\u0648","\u0626":"\u064A","\u0629":"\u0647",  # ى->ي ؤ->و ئ->ي ة->ه
    "\u0621":"",
})
def normalise(s: str) -> str:
    return strip_diac(s).translate(_NORM_MAP)

_ABJAD = {"ا":1,"ب":2,"ج":3,"د":4,"ه":5,"و":6,"ز":7,"ح":8,"ط":9,"ي":10,
          "ك":20,"ل":30,"م":40,"ن":50,"س":60,"ع":70,"ف":80,"ص":90,
          "ق":100,"ر":200,"ش":300,"ت":400,"ث":500,"خ":600,"ذ":700,"ض":800,"ظ":900,"غ":1000,
          "ٱ":1,"أ":1,"إ":1,"آ":1,"ء":1,"ى":10,"ؤ":6,"ئ":10,"ة":5}
def abjad(s: str) -> int:
    return sum(_ABJAD.get(ch,0) for ch in strip_diac(s))

_BW = {"ء":"'","ا":"A","ٱ":"{","أ":"<","إ":">","آ":"|","ب":"b","ت":"t","ث":"v","ج":"j",
       "ح":"H","خ":"x","د":"d","ذ":"*","ر":"r","ز":"z","س":"s","ش":"$","ص":"S","ض":"D",
       "ط":"T","ظ":"Z","ع":"E","غ":"g","ف":"f","ق":"q","ك":"k","ل":"l","م":"m","ن":"n",
       "ه":"h","و":"w","ي":"y","ة":"p","ى":"Y","ؤ":"&","ئ":"}"}
def buckwalter(s: str) -> str:
    return "".join(_BW.get(ch,"") for ch in strip_diac(s))

# readable academic transliteration for ROOT consonants (ḥ-m-d style)
_TR = {"ء":"ʾ","ٱ":"ʾ","أ":"ʾ","إ":"ʾ","آ":"ʾ","ا":"ā","ب":"b","ت":"t","ث":"th","ج":"j",
       "ح":"ḥ","خ":"kh","د":"d","ذ":"dh","ر":"r","ز":"z","س":"s","ش":"sh","ص":"ṣ","ض":"ḍ",
       "ط":"ṭ","ظ":"ẓ","ع":"ʿ","غ":"gh","ف":"f","ق":"q","ك":"k","ل":"l","م":"m","ن":"n",
       "ه":"h","و":"w","ي":"y","ة":"h","ى":"ā","ؤ":"w","ئ":"y"}
def translit_root(root: Optional[str]) -> str:
    if not root: return ""
    return "-".join(_TR.get(ch,"") for ch in strip_diac(root) if _TR.get(ch,""))

def _shaper():
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return lambda t: get_display(arabic_reshaper.reshape(t))
    except Exception:
        return None
_SHAPE = _shaper()
def ar_shape(text: str) -> str:
    return _SHAPE(text) if _SHAPE else text

# --------------------------------------------------------------------------- #
#  Word-by-word English (transliteration + meaning), cached
# --------------------------------------------------------------------------- #
def load_wbw() -> dict:
    if os.path.exists(WBW_FILE):
        try:
            return json.load(open(WBW_FILE, encoding="utf-8"))
        except Exception:
            pass
    print("[i] data/wbw_en.json not found — English columns will be blank. "
          "Re-create it from api.quran.com v4 to enable transliteration + meaning.")
    return {}

# --------------------------------------------------------------------------- #
#  Parse QAC -> words
# --------------------------------------------------------------------------- #
@dataclass
class Word:
    gidx:int=0; sura:int=0; aya:int=0; word:int=0; loc:str=""
    form:str=""; skeleton:str=""; norm:str=""
    root:Optional[str]=None; lemma:Optional[str]=None; pos:str=""
    n_seg:int=0; n_letters:int=0; segments:list=field(default_factory=list)

def _feat(feats:str):
    root=lemma=None; flags=[]
    for f in feats.split("|"):
        if f.startswith("ROOT:"): root=f[5:]
        elif f.startswith("LEM:"): lemma=f[4:]
        else: flags.append(f)
    return root,lemma,flags

def parse_qac(path:str=QAC_FILE):
    if not os.path.exists(path):
        sys.exit(f"[!] corpus not found: {path}")
    seg=[]
    with open(path,encoding="utf-8") as fh:
        for line in fh:
            line=line.rstrip("\n")
            if not line.strip(): continue
            p=line.split("\t")
            if len(p)<4: continue
            loc=p[0].split(":")
            if len(loc)!=4: continue
            s,a,w,sg=map(int,loc)
            r,l,fl=_feat(p[3])
            seg.append((s,a,w,sg,p[1],p[2],r,l,fl))
    words=[]; cur=None; cs=[]
    def flush():
        if not cs: return
        s,a,w=cur; cs.sort(key=lambda r:r[3])
        form="".join(r[4] for r in cs)
        content=next((r for r in cs if r[6]),None) or \
                next((r for r in cs if r[5] in("N","V","PN")),cs[-1])
        pos=content[5]
        if "PN" in content[8]: pos="PN"
        elif "ADJ" in content[8] and pos=="N": pos="ADJ"
        sk=strip_diac(form)
        words.append(Word(sura=s,aya=a,word=w,loc=f"{s}:{a}:{w}",form=form,skeleton=sk,
                          norm=normalise(form),root=content[6],lemma=content[7],pos=pos,
                          n_seg=len(cs),n_letters=len(sk),
                          segments=[(r[4],r[5],r[6],r[7]) for r in cs]))
    for r in seg:
        k=(r[0],r[1],r[2])
        if k!=cur: flush(); cur,cs=k,[]
        cs.append(r)
    flush()
    for i,wd in enumerate(words,1): wd.gidx=i
    return words

def file_sha256(path:str)->str:
    h=hashlib.sha256()
    with open(path,"rb") as fh:
        for c in iter(lambda:fh.read(1<<16),b""): h.update(c)
    return h.hexdigest()

# --------------------------------------------------------------------------- #
#  Topology graph
# --------------------------------------------------------------------------- #
def build_root_graph(words):
    vr=collections.defaultdict(set)
    for w in words:
        if w.root: vr[(w.sura,w.aya)].add(w.root)
    ew=collections.Counter()
    for roots in vr.values():
        rs=sorted(roots)
        for i in range(len(rs)):
            for j in range(i+1,len(rs)): ew[(rs[i],rs[j])]+=1
    G=nx.Graph(); G.add_nodes_from({w.root for w in words if w.root})
    for (u,v),w in ew.items(): G.add_edge(u,v,weight=w)
    return G

def graph_metrics(G, betweenness=False):
    deg=dict(G.degree()); wdeg=dict(G.degree(weight="weight"))
    clus=nx.clustering(G)
    pr=nx.pagerank(G,weight="weight") if G.number_of_edges() else {n:0 for n in G}
    eig={n:0.0 for n in G}
    if G.number_of_edges():
        gc=max(nx.connected_components(G),key=len)
        try: eig.update(nx.eigenvector_centrality_numpy(G.subgraph(gc),weight="weight"))
        except Exception:
            try: eig.update(nx.eigenvector_centrality(G.subgraph(gc),max_iter=1000,weight="weight"))
            except Exception: pass
    out=dict(degree=deg,wdegree=wdeg,clustering=clus,eigcent=eig,pagerank=pr)
    if betweenness:
        out["betweenness"]=nx.betweenness_centrality(G,k=min(400,G.number_of_nodes()),seed=42,weight=None)
    return out

# --------------------------------------------------------------------------- #
#  BUILD
# --------------------------------------------------------------------------- #
def _ploc(s): return tuple(int(x) for x in s.split(":"))

def build(start=None,end=None,betweenness=False,write=True):
    words=parse_qac()
    wbw=load_wbw()
    loc_en={k:v.get("en","") for k,v in wbw.items()}
    loc_tr={k:v.get("tr","") for k,v in wbw.items()}

    N=len(words)
    ff=collections.Counter(w.form for w in words)
    fn=collections.Counter(w.norm for w in words)
    fl=collections.Counter(w.lemma for w in words if w.lemma)
    fr=collections.Counter(w.root for w in words if w.root)

    # derive ROOT meaning (English) from the word-by-word glosses (majority vote)
    root_gloss=collections.defaultdict(collections.Counter)
    for w in words:
        if w.root:
            g=loc_en.get(w.loc,"").strip()
            if g: root_gloss[w.root][g]+=1
    root_en={r:c.most_common(1)[0][0] for r,c in root_gloss.items()}
    root_top={r:"; ".join(f"{g} ({n})" for g,n in c.most_common(3)) for r,c in root_gloss.items()}

    vr=collections.defaultdict(list)
    for w in words:
        if w.root: vr[(w.sura,w.aya)].append(w.root)

    G=build_root_graph(words); M=graph_metrics(G,betweenness)
    def info(c,t): return round(-math.log2(c/t),4) if c and t else float("nan")
    def inrange(w):
        t=(w.sura,w.aya,w.word)
        if start and t<_ploc(start): return False
        if end and t>_ploc(end): return False
        return True

    rows=[]; matched=0
    for i,w in enumerate(words):
        if w.loc in loc_en: matched+=1
        if not inrange(w): continue
        pv=words[i-1] if i>0 else None
        nx_=words[i+1] if i<N-1 else None
        co=[r for r in vr[(w.sura,w.aya)] if r!=w.root]
        co_top=[r for r,_ in collections.Counter(co).most_common(6)]
        word_en=loc_en.get(w.loc,"")
        row=dict(
            gidx=w.gidx,loc=w.loc,sura=w.sura,aya=w.aya,word=w.word,
            form=w.form, translit=loc_tr.get(w.loc,""), word_en=word_en,
            skeleton=w.skeleton, norm=w.norm,
            root=w.root, root_translit=translit_root(w.root),
            root_en=root_en.get(w.root,""),                 # representative root meaning
            root_en_here=word_en,                           # root's meaning in THIS context
            lemma=w.lemma, pos=w.pos, n_seg=w.n_seg, n_letters=w.n_letters,
            freq_form=ff[w.form], freq_norm=fn[w.norm],
            freq_lemma=fl.get(w.lemma,0), freq_root=fr.get(w.root,0),
            energy_info_norm=info(fn[w.norm],N),
            energy_info_lemma=info(fl.get(w.lemma,0),N) if w.lemma else float("nan"),
            energy_info_root=info(fr.get(w.root,0),N) if w.root else float("nan"),
            abjad_form=abjad(w.form), abjad_root=abjad(w.root) if w.root else 0,
            prev_form=pv.form if pv else None, prev_en=loc_en.get(pv.loc,"") if pv else None,
            prev_root=pv.root if pv else None, prev_pos=pv.pos if pv else None,
            next_form=nx_.form if nx_ else None, next_en=loc_en.get(nx_.loc,"") if nx_ else None,
            next_root=nx_.root if nx_ else None, next_pos=nx_.pos if nx_ else None,
            crosses_verse_prev=bool(pv and (pv.sura,pv.aya)!=(w.sura,w.aya)),
            crosses_verse_next=bool(nx_ and (nx_.sura,nx_.aya)!=(w.sura,w.aya)),
            collocate_roots=" ".join(co_top),
            collocate_en=" | ".join(root_en.get(r,"") for r in co_top),
            root_degree=M["degree"].get(w.root,0) if w.root else 0,
            root_wdegree=M["wdegree"].get(w.root,0) if w.root else 0,
            root_clustering=round(M["clustering"].get(w.root,0.0),5) if w.root else 0.0,
            root_eigcent=round(M["eigcent"].get(w.root,0.0),6) if w.root else 0.0,
            root_pagerank=round(M["pagerank"].get(w.root,0.0),7) if w.root else 0.0,
        )
        if betweenness:
            row["root_betweenness"]=round(M["betweenness"].get(w.root,0.0),6) if w.root else 0.0
        rows.append(row)
    df=pd.DataFrame(rows)

    rsum=[]
    for r,c in fr.most_common():
        rsum.append(dict(root=r, translit=translit_root(r), buckwalter=buckwalter(r),
            meaning_en=root_en.get(r,""), top_glosses_en=root_top.get(r,""),
            abjad=abjad(r), freq=c, info=info(c,N), n_letters=len(strip_diac(r)),
            degree=M["degree"].get(r,0), wdegree=M["wdegree"].get(r,0),
            clustering=round(M["clustering"].get(r,0.0),5),
            eigcent=round(M["eigcent"].get(r,0.0),6), pagerank=round(M["pagerank"].get(r,0.0),7)))
    roots_df=pd.DataFrame(rsum)

    def entropy(cnt):
        t=sum(cnt.values()); return round(-sum((c/t)*math.log2(c/t) for c in cnt.values()),4)
    Hr,Hf,Hn=entropy(fr),entropy(ff),entropy(fn)
    summary=dict(
        corpus_file=os.path.basename(QAC_FILE), corpus_sha256=file_sha256(QAC_FILE),
        english_source="Quran.com word-by-word English (api.quran.com v4)",
        english_words_matched=matched,
        n_words=N, n_verses=len({(w.sura,w.aya) for w in words}), n_suras=len({w.sura for w in words}),
        n_unique_forms=len(ff), n_unique_norm=len(fn), n_unique_lemmas=len(fl), n_unique_roots=len(fr),
        entropy_root_bits=Hr, perplexity_root=round(2**Hr,1),
        entropy_form_bits=Hf, perplexity_form=round(2**Hf,1), entropy_norm_bits=Hn,
        graph_nodes=G.number_of_nodes(), graph_edges=G.number_of_edges(), graph_density=round(nx.density(G),6),
        top10_roots=[(r, root_en.get(r,""), c) for r,c in fr.most_common(10)],
        notes=dict(empirical="frequency, info-content, entropy, topology",
                   exploratory_only="abjad (convention-dependent gematria, not validated)",
                   meaning="word_en = word-by-word translation (cited); root_en = majority gloss (derived); "
                           "root_en_here = this occurrence's gloss; tafsir != arithmetic"))
    if write:
        df.to_csv(os.path.join(OUT,"quran_words.csv"),index=False,encoding="utf-8-sig")
        roots_df.to_csv(os.path.join(OUT,"roots_summary.csv"),index=False,encoding="utf-8-sig")
        json.dump(summary,open(os.path.join(OUT,"summary.json"),"w",encoding="utf-8"),
                  ensure_ascii=False,indent=2)
    return df,roots_df,summary,G,M

# --------------------------------------------------------------------------- #
#  Dossier
# --------------------------------------------------------------------------- #
def report(df, loc=None, index=None):
    row=df[df["loc"]==loc] if loc is not None else df[df["gidx"]==int(index)]
    if row.empty: print(f"[!] not found: loc={loc} index={index}"); return
    r=row.iloc[0]; bar="─"*68
    n=lambda v:"—" if (v is None or (isinstance(v,float) and v!=v)) else v
    print(bar)
    print(f"  WORD #{r.gidx}    {r['loc']}    {r.form}    [{r.translit}]")
    print(f"  meaning (here): {r.word_en}")
    print(bar)
    print(f"  root         : {r.root}  [{r.root_translit}]  =  {r.root_en}")
    print(f"  root here    : {r.root_en_here}   (its sense in THIS verse)")
    print(f"  lemma        : {r.lemma}    POS={r.pos}   segments={r.n_seg}  letters={r.n_letters}")
    print(f"  frequency    : form={r.freq_form}  norm={r.freq_norm}  lemma={r.freq_lemma}  ROOT={r.freq_root}")
    print(f"  energy(info) : root={r.energy_info_root} bits  lemma={r.energy_info_lemma}  norm={r.energy_info_norm}   [empirical]")
    print(f"  abjad        : form={r.abjad_form}  root={r.abjad_root}   [traditional — exploratory only]")
    print(f"  prev word    : {n(r.prev_form)}  =  {n(r.prev_en)}  (root {n(r.prev_root)})"
          f"{'  [prev verse]' if r.crosses_verse_prev else ''}")
    print(f"  next word    : {n(r.next_form)}  =  {n(r.next_en)}  (root {n(r.next_root)})"
          f"{'  [next verse]' if r.crosses_verse_next else ''}")
    print(f"  collocates   : {r.collocate_roots}")
    print(f"                 {r.collocate_en}")
    print(f"  topology     : degree={r.root_degree}  w.degree={r.root_wdegree}  clustering={r.root_clustering}")
    print(f"                 eigen-centrality={r.root_eigcent}  pagerank={r.root_pagerank}")
    print(bar)

# --------------------------------------------------------------------------- #
#  Plots
# --------------------------------------------------------------------------- #
def _mpl(latin):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    if (not latin) and os.path.exists(ARABIC_FONT):
        fm.fontManager.addfont(ARABIC_FONT)
        plt.rcParams["font.family"]=fm.FontProperties(fname=ARABIC_FONT).get_name()
    return plt

def _labeler(roots_df, mode):
    tr=dict(zip(roots_df["root"],roots_df["translit"]))
    en=dict(zip(roots_df["root"],roots_df["meaning_en"]))
    def lab(root, maxlen=16):
        if mode=="latin":   return tr.get(root, buckwalter(root))
        if mode=="english":
            s=en.get(root,"") or tr.get(root,""); return s[:maxlen]
        return ar_shape(root)
    return lab

def plots(df, roots_df, summary, G, M, label="arabic", top_net=60):
    plt=_mpl(label!="arabic"); lab=_labeler(roots_df,label)
    # Zipf
    fig,ax=plt.subplots(figsize=(7,5))
    rf=roots_df["freq"].values
    ax.loglog(range(1,len(rf)+1),rf,".",ms=4,label="roots")
    fc=pd.Series(df["norm"]).value_counts().values
    ax.loglog(range(1,len(fc)+1),fc,".",ms=2,alpha=.4,label="normalised forms")
    ax.set_xlabel("rank");ax.set_ylabel("frequency");ax.set_title("Zipf curve (log-log)");ax.legend()
    fig.tight_layout();fig.savefig(os.path.join(OUT,"zipf.png"),dpi=140);plt.close(fig)
    # energy hist
    fig,ax=plt.subplots(figsize=(7,4.2))
    ax.hist(df["energy_info_root"].dropna(),bins=40,color="#3b6ea5",edgecolor="white")
    ax.set_xlabel("information content  −log2 p(root)  [bits]");ax.set_ylabel("word count")
    ax.set_title("Per-word energy (root surprisal)")
    fig.tight_layout();fig.savefig(os.path.join(OUT,"energy_hist.png"),dpi=140);plt.close(fig)
    # top roots
    top=roots_df.head(30)
    fig,ax=plt.subplots(figsize=(9,7))
    ax.barh(range(len(top)),top["freq"],color="#b08d57")
    ax.set_yticks(range(len(top)));ax.set_yticklabels([lab(r,28) for r in top["root"]])
    ax.invert_yaxis();ax.set_xlabel("frequency");ax.set_title(f"Top 30 roots by frequency ({label} labels)")
    fig.tight_layout();fig.savefig(os.path.join(OUT,"top_roots.png"),dpi=140);plt.close(fig)
    # network
    wd=sorted(M["wdegree"].items(),key=lambda kv:kv[1],reverse=True)[:top_net]
    H=G.subgraph([n for n,_ in wd]).copy()
    if H.number_of_edges():
        thr=np.percentile([d["weight"] for *_e,d in H.edges(data=True)],60)
        H.remove_edges_from([(u,v) for u,v,d in list(H.edges(data=True)) if d["weight"]<thr])
    fm_=dict(zip(roots_df["root"],roots_df["freq"]))
    sizes=[120+30*math.sqrt(fm_.get(n,1)) for n in H.nodes()]
    pos=nx.spring_layout(H,seed=42,k=0.6,weight="weight")
    fig,ax=plt.subplots(figsize=(12,12))
    nx.draw_networkx_edges(H,pos,alpha=.18,width=[0.3+0.04*d["weight"] for *_e,d in H.edges(data=True)],ax=ax)
    nx.draw_networkx_nodes(H,pos,node_size=sizes,node_color="#3b6ea5",alpha=.85,ax=ax)
    for n,(x,y) in pos.items():
        ax.text(x,y,lab(n,14),fontsize=9,ha="center",va="center",color="white")
    ax.set_title(f"Root co-occurrence network ({label} labels)");ax.axis("off")
    fig.tight_layout();fig.savefig(os.path.join(OUT,"root_network.png"),dpi=150);plt.close(fig)
    print(f"[+] wrote 4 plots to {OUT}/  (label mode: {label})")

def graph_root(G,M,roots_df,root,label="arabic"):
    plt=_mpl(label!="arabic"); lab=_labeler(roots_df,label)
    if root not in G: print(f"[!] root '{root}' not in graph"); return
    H=G.subgraph({root}|set(G.neighbors(root))).copy()
    edges=sorted(((u,v,d["weight"]) for u,v,d in H.edges(data=True) if root in(u,v)),
                 key=lambda e:e[2],reverse=True)[:18]
    keep={root}|{v for u,v,_ in edges}|{u for u,v,_ in edges}
    H=H.subgraph(keep).copy()
    fm_=dict(zip(roots_df["root"],roots_df["freq"]))
    sizes=[420 if n==root else 120+25*math.sqrt(fm_.get(n,1)) for n in H.nodes()]
    cols=["#b03a2e" if n==root else "#3b6ea5" for n in H.nodes()]
    pos=nx.spring_layout(H,seed=7,k=0.9)
    fig,ax=plt.subplots(figsize=(9.5,9.5))
    nx.draw_networkx_edges(H,pos,alpha=.25,width=[0.4+0.05*d["weight"] for *_e,d in H.edges(data=True)],ax=ax)
    nx.draw_networkx_nodes(H,pos,node_size=sizes,node_color=cols,alpha=.9,ax=ax)
    for n,(x,y) in pos.items():
        ax.text(x,y,lab(n,16),fontsize=10,ha="center",va="center",color="white")
    en=dict(zip(roots_df["root"],roots_df["meaning_en"])).get(root,"")
    ax.set_title(f"Ego-network of {translit_root(root)}  ({root}) = {en}");ax.axis("off")
    fig.tight_layout()
    fn=os.path.join(OUT,f"egonet_{buckwalter(root) or 'root'}.png")
    fig.savefig(fn,dpi=150);plt.close(fig);print(f"[+] wrote {fn}")

# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main():
    ap=argparse.ArgumentParser(description="Quran word-by-word analyzer (Arabic + English)")
    ap.add_argument("cmd",nargs="?",default="demo",
                    choices=["build","report","plots","graph-root","demo"])
    ap.add_argument("target",nargs="?")
    ap.add_argument("--index",type=int)
    ap.add_argument("--start");ap.add_argument("--end")
    ap.add_argument("--betweenness",action="store_true")
    ap.add_argument("--label",choices=["arabic","latin","english"],default="arabic")
    ap.add_argument("--latin-labels",action="store_true",help="alias for --label latin")
    a=ap.parse_args()
    label="latin" if a.latin_labels else a.label

    if a.cmd=="build":
        df,rdf,s,G,M=build(a.start,a.end,a.betweenness)
        print(json.dumps(s,ensure_ascii=False,indent=2)); return
    if a.cmd=="report":
        df,*_=build(a.start,a.end,a.betweenness,write=False); report(df,loc=a.target,index=a.index); return
    if a.cmd=="plots":
        df,rdf,s,G,M=build(a.start,a.end,a.betweenness); plots(df,rdf,s,G,M,label=label); return
    if a.cmd=="graph-root":
        df,rdf,s,G,M=build(a.start,a.end,a.betweenness,write=False); graph_root(G,M,rdf,a.target,label=label); return
    # demo
    df,rdf,s,G,M=build(a.start,a.end,a.betweenness)
    print(json.dumps(s,ensure_ascii=False,indent=2))
    print("\n=== sample dossiers ===")
    report(df,loc="1:1:1"); report(df,loc="1:2:1"); report(df,index=int(df.iloc[-1]["gidx"]))
    plots(df,rdf,s,G,M,label=label); graph_root(G,M,rdf,"حمد",label=label)

if __name__=="__main__":
    main()
