"""Which of the six books holds a quoted hadith: MIZAN's own index, read with NLI."""

import pytest

from tadbir import hadith_index, sidq

MARTYR = (
    'Narrated Al-Miqdam: The Messenger of Allah said: "There are six things with Allah for '
    "the martyr. He is forgiven with the first flow of blood, he is shown his place in "
    'Paradise, he is protected from the punishment of the grave."'
)
INTENTIONS = (
    "Narrated Umar: I heard Allah's Messenger saying, \"The reward of deeds depends upon "
    'the intentions and every person will get the reward according to what he has intended."'
)
OTHER = 'Narrated Abu Huraira: The Prophet said: "The strong man is the one who controls himself."'


@pytest.fixture
def books(monkeypatch):
    monkeypatch.setenv("MIZAN_HADITH_INDEX", "on")
    index = hadith_index.build(
        {
            "bukhari": [
                {"hadithnumber": 1, "text": INTENTIONS},
                {"hadithnumber": 6114, "text": OTHER},
            ],
            "tirmidhi": [{"hadithnumber": 1663, "text": MARTYR}],
            "abudawud": [{"hadithnumber": 2201, "text": "Actions are judged by intentions."}],
        }
    )
    monkeypatch.setattr(hadith_index, "_index", index)

    async def nli(pairs):
        # Stands in for the NLI model: a narration says the quote when it holds
        # its key words.
        def reads(premise, hypothesis):
            said = ("six" in hypothesis and "six things" in premise) or (
                "intention" in hypothesis and "intention" in premise
            )
            return {
                "entailment": 0.9 if said else 0.05,
                "neutral": 0.05 if said else 0.9,
                "contradiction": 0.05,
            }

        return [reads(premise, hypothesis) for premise, hypothesis in pairs]

    monkeypatch.setattr("tadbir.ahl_dhikr.nli", nli)
    return index


def test_quotes_given_as_a_book_are_found():
    found = hadith_index.citations(
        'He said, "The martyr has six distinctions with Allah, he is forgiven" (Sahih al-Bukhari).'
    )
    assert found and found[0].books == ("bukhari",) and "six distinctions" in found[0].quote
    assert hadith_index.citations('He said "be kind to people always please" and smiled.') == []


async def test_a_hadith_cited_to_the_wrong_book_is_reported_with_where_it_is(books):
    # The 3.3.0 benchmark: given as Bukhari and Muslim; it is Tirmidhi 1663.
    answer = (
        'The Prophet said, "The martyr has six distinctions with Allah: he is forgiven at the '
        'first drop of blood" (Sahih al-Bukhari and Sahih Muslim).'
    )
    (finding,) = await hadith_index.check(answer)
    assert finding["cited"] == ["Sahih al-Bukhari", "Sahih Muslim"]
    assert finding["found"][0]["reference"] == "Jami` at-Tirmidhi 1663"


async def test_another_translation_of_the_cited_book_is_not_a_misattribution(books):
    # Bukhari's English says "deeds depend upon intentions": the same hadith.
    answer = 'In Sahih al-Bukhari: "Actions are judged by intentions, so purify them."'
    assert await hadith_index.check(answer) == []


async def test_the_truth_gate_reports_it_under_the_answer_without_changing_it(books, monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")

    async def none(*args, **kwargs):
        return []

    monkeypatch.setattr("tadbir.muhasaba.scripture", none)
    answer = (
        'The Prophet said, "The martyr has six distinctions with Allah: he is forgiven at the '
        'first drop of blood" (Sahih al-Bukhari).'
    )
    text, report = await sidq.gate(answer, check_links=False)
    assert text == answer
    (flag,) = report["flagged"]
    assert flag["kind"] == "hadith_source" and "Tirmidhi 1663" in flag["detail"]
