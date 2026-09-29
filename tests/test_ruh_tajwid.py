"""Tests for the Tajwīd backend (Ḥafṣ ʿan ʿĀṣim, text-based rules engine).

Engine tests use classical textbook examples per rule; API tests cover
the /v1/tajwid router (analyze + rules catalog, schema, qirāʾah gating).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.ruh_tajwid import analyze_text, get_rule_catalog, router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def rule_ids(text):
    return {a["rule_id"] for a in analyze_text(text)["annotations"]}


# ---------- nūn sākinah / tanwīn ----------


class TestNunSakinah:
    def test_iqlab(self):
        assert "nun_iqlab" in rule_ids("مِنْ بَعْدِ")

    def test_izhar_halq(self):
        assert "nun_izhar" in rule_ids("مَنْ آمَنَ")

    def test_izhar_tanwin(self):
        assert "nun_izhar" in rule_ids("عَذَابٌ أَلِيمٌ")

    def test_idgham_ghunnah_kamil(self):
        assert "nun_idgham_ghunnah" in rule_ids("حَبْلٌ مِنْ مَسَدٍ")

    def test_idgham_ghunnah_naqis(self):
        # ي keeps ghunnah (nāqiṣ)
        assert "nun_idgham_ghunnah" in rule_ids("فَمَنْ يَعْمَلْ")

    def test_idgham_no_ghunnah(self):
        assert "nun_idgham_no_ghunnah" in rule_ids("يَكُنْ لَهُ")

    def test_ikhfa(self):
        assert "nun_ikhfa" in rule_ids("مِنْ شَرِّ")

    def test_ikhfa_tanwin_across_iwad(self):
        # tanwīn sits on م, ʿiwaḍ alif must not block the lookahead
        assert "nun_ikhfa" in rule_ids("كِرَامًا كَاتِبِينَ")

    def test_izhar_mutlaq(self):
        # the four words: idghām blocked inside one word
        assert "nun_izhar_mutlaq" in rule_ids("الدُّنْيَا")
        assert "nun_idgham_ghunnah" not in rule_ids("الدُّنْيَا")


# ---------- mīm sākinah / ghunnah ----------


class TestMimGhunnah:
    def test_mim_ikhfa(self):
        assert "mim_ikhfa" in rule_ids("لَهُمْ بِهِ")

    def test_mim_idgham(self):
        assert "mim_idgham" in rule_ids("لَكُمْ مَا")

    def test_mim_izhar(self):
        assert "mim_izhar" in rule_ids("أَنْعَمْتَ")

    def test_ghunnah_mushaddad(self):
        assert "ghunnah_mushaddad" in rule_ids("إِنَّ")
        assert "ghunnah_mushaddad" in rule_ids("ثُمَّ")


# ---------- madd ----------


class TestMadd:
    def test_muttasil(self):
        assert "madd_muttasil" in rule_ids("جَاءَ")

    def test_munfasil(self):
        assert "madd_munfasil" in rule_ids("إِنَّا أَعْطَيْنَاكَ")

    def test_badal(self):
        assert "madd_badal" in rule_ids("آمَنُوا")

    def test_lazim_kalimi_muthaqqal(self):
        assert "madd_lazim_kalimi" in rule_ids("الضَّالِّينَ")

    def test_lazim_kalimi_mukhaffaf_beats_badal(self):
        # آلْآنَ: lāzim (6), not badal
        assert "madd_lazim_kalimi" in rule_ids("آلْآنَ")

    def test_arid(self):
        assert "madd_arid" in rule_ids("نَسْتَعِينُ")

    def test_lin(self):
        assert "madd_lin" in rule_ids("خَيْرٌ")

    def test_silah_sughra(self):
        assert "madd_silah_sughra" in rule_ids("يَكُنْ لَهُ")

    def test_silah_blocked_before_sakin(self):
        # فِيهِ: sākin before hāʾ → no ṣilah (25:69 needs verse context)
        assert "madd_silah_sughra" not in rule_ids("فِيهِ")

    def test_silah_blocked_yardah(self):
        assert "madd_silah_sughra" not in rule_ids("يَرْضَهُ")

    def test_iwad(self):
        assert "madd_iwad" in rule_ids("رِزْقًا")
        assert "madd_tabi" not in rule_ids("رِزْقًا")

    def test_no_madd_on_hamzat_wasl(self):
        # وَاللَّهُ: the alif of ال after prefix is hamzat waṣl, not madd
        assert "madd_tabi" not in rule_ids("وَاللَّهُ")
        assert "madd_tabi" not in rule_ids("بِسْمِ اللَّهِ")


# ---------- qalqalah / rāʾ / lām ----------


class TestQalqalahRaLam:
    def test_qalqalah_sughra_midword(self):
        assert "qalqalah_sughra" in rule_ids("قَدْ أَفْلَحَ")

    def test_qalqalah_kubra_phrase_end(self):
        assert "qalqalah_kubra" in rule_ids("الْفَلَقِ")
        assert "qalqalah_kubra" not in rule_ids("قَدْ أَفْلَحَ")

    def test_ra_tafkhim_fatha(self):
        assert "ra_tafkhim" in rule_ids("صِرَاطَ")

    def test_ra_tarqeeq_kasra(self):
        assert "ra_tarqeeq" in rule_ids("الْقِطْرِ")

    def test_ra_jawaz_firq(self):
        assert "ra_jawaz" in rule_ids("فِرْقٍ")

    def test_ra_jawaz_misr_waqf_noted(self):
        ids = rule_ids("مِصْرَ")
        assert "ra_tafkhim" in ids  # waṣl value; jawāz noted in detail

    def test_lam_jalalah_tafkhim(self):
        assert "lam_jalalah_tafkhim" in rule_ids("وَاللَّهُ")

    def test_lam_jalalah_tarqeeq(self):
        assert "lam_jalalah_tarqeeq" in rule_ids("بِسْمِ اللَّهِ")

    def test_lam_shamsi(self):
        assert "lam_shamsi" in rule_ids("الشَّمْسُ")

    def test_lam_qamari(self):
        assert "lam_qamari" in rule_ids("الْقَمَرُ")

    def test_hamzat_wasl(self):
        assert "hamzat_wasl" in rule_ids("الْقَمَرُ")


# ---------- sakt / muqaṭṭaʿāt / istiʿlāʾ ----------


class TestSaktMuqattaat:
    def test_sakt_blocks_idgham(self):
        ids = rule_ids("مَنْ رَاقٍ")
        assert "sakt" in ids
        assert "nun_idgham_no_ghunnah" not in ids

    def test_sakt_iwaj_pair(self):
        ids = rule_ids("عِوَجًا قَيِّمًا")
        assert "sakt" in ids
        assert "nun_ikhfa" not in ids  # sakt blocks the ikhfāʾ

    def test_muqattaat_lazim(self):
        ids = rule_ids("الم")
        assert "madd_lazim_harfi" in ids

    def test_muqattaat_tabi(self):
        # هـ in كهيعص → ṭabīʿī ḥarfī
        assert "madd_tabi" in rule_ids("كهيعص")

    def test_tafkheem_istila(self):
        assert "tafkheem_istila" in rule_ids("صِرَاطَ")


# ---------- engine honesty ----------


class TestEngineHonesty:
    def test_no_diacritics_partial(self):
        r = analyze_text("الم")
        assert r["status"] == "partial"
        assert r["diacritic_coverage"] == 0
        assert r["note"]  # honest about what ran

    def test_no_diacritics_letter_rules_only(self):
        # no vowel-guessing: only letter-shape rules
        r = analyze_text("الشمس")
        assert r["status"] == "partial"
        assert "lam_shamsi" in {a["rule_id"] for a in r["annotations"]}

    def test_diacritics_ok(self):
        r = analyze_text("مِنْ بَعْدِ")
        assert r["status"] == "ok"
        assert r["diacritic_coverage"] > 0

    def test_spans_align_with_text(self):
        text = "مِنْ بَعْدِ"
        for a in analyze_text(text)["annotations"]:
            assert text[a["start"] : a["end"]] == a["span"]

    def test_qiraat_notes_flagged_not_computed(self):
        # munfaṣil carries a Warsh note; engine stays Ḥafṣ
        anns = analyze_text("إِنَّا أَعْطَيْنَاكَ")["annotations"]
        mun = [a for a in anns if a["rule_id"] == "madd_munfasil"]
        assert mun and mun[0]["qiraat_note"]

    def test_catalog_has_sources(self):
        catalog = get_rule_catalog()
        assert len(catalog) >= 30
        for r in catalog:
            assert r["rule_id"] and r["name_ar"] and r["name_en"] and r["sources"]


# ---------- API ----------


class TestTajwidApi:
    def test_analyze_ok(self, client):
        resp = client.post("/v1/tajwid/analyze", json={"text": "مِنْ بَعْدِ"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["qiraat"] == "hafs"
        ids = {a["rule_id"] for a in data["annotations"]}
        assert "nun_iqlab" in ids
        # schema shape
        a0 = data["annotations"][0]
        for key in (
            "rule_id",
            "rule_name_ar",
            "rule_name_en",
            "category",
            "span",
            "start",
            "end",
            "detail",
        ):
            assert key in a0
        assert data["scope"]  # honest scope note in every response

    def test_analyze_partial_no_diacritics(self, client):
        resp = client.post("/v1/tajwid/analyze", json={"text": "الم"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "partial"

    def test_analyze_rejects_other_qiraat(self, client):
        resp = client.post("/v1/tajwid/analyze", json={"text": "مِنْ بَعْدِ", "qiraat": "warsh"})
        assert resp.status_code == 422

    def test_analyze_rejects_empty(self, client):
        resp = client.post("/v1/tajwid/analyze", json={"text": ""})
        assert resp.status_code == 422

    def test_rules_catalog(self, client):
        resp = client.get("/v1/tajwid/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 30
        assert data["qiraat"] == "hafs"
        r0 = data["rules"][0]
        for key in (
            "rule_id",
            "name_ar",
            "name_en",
            "category",
            "description",
            "default_length",
            "sources",
        ):
            assert key in r0
