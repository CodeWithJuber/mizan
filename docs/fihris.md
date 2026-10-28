# Fihris (فهرس): finding ayahs by their words

"Sidratul muntaha kya hai", "inna lillahi wa inna ilayhi rajiun", "light upon light", "Quran me Kausar ka zikr", "سدرة المنتهى": when a request names no surah or ayah number but asks for an ayah by its words, MIZAN searches its own index of the Quran. It then quotes what it found verbatim from the authentic source, exactly as the Quran recipe does. No model chooses, recalls or words an ayah.

Code: `backend/tadbir/fihris.py`, the `_quran_search` recipe in `backend/tadbir/engine.py`, the `quran_search` intent in Qasd.

## The index

The index is downloaded once into `$MIZAN_DATA_DIR/quran` from api.alquran.cloud, the same Tanzil-based source as the Quran recipe. It holds about 24 MB in memory, is built on the first search (about 4 seconds) and is reused after that.

Every ayah has five views:

| View | Edition | Indexed as |
|---|---|---|
| Arabic | `quran-simple-clean` | letter trigrams of each word |
| Transliteration | `en.transliteration` | letter trigrams of each word |
| English | `en.sahih` (Saheeh International) | words |
| Urdu | `ur.jalandhry` | words |
| Hindi | `hi.hindi` | words |

**Trigrams, not spelling rules.** People spell transliterations their own way, so the Arabic and transliteration views match by letter trigrams:
- "sidra tu munhtah" meets "sidratil muntaha";
- "Kausar" meets "kauthar";
- "قرآن" meets "القرآن".

No rule about articles, vowels or sounds is written anywhere. Text is only normalised: lower case without accents, and Arabic-script letters that are one letter in two code points (Urdu ی and Arabic ي, the seats of hamza) written one way.

## Weighing a query

Every word of the request is weighed twice, from data:

1. **Which view reads it.** A word goes to each view of its script in proportion to the share of that view's ayahs that use it. An English word goes to the translation. A word no view uses goes to the trigram view of its script.
2. **Whether it is the topic or the way of asking.** The word counts by P(topic | word). That is the share of ayahs that use it against the share of MIZAN's request seeds (`data/qasd`) that do, with each seed left out once. In "Quran me Kausar ka zikr":
   - "Quran", "me", "ka" and "zikr" appear across many seeds, so they are how the request is phrased;
   - "Kausar" appears in none, so it is what the request is about.

Every view then scores the ayahs by BM25. Its scores are standardised over all 6236 ayahs, so a view counts by how far its best ayahs stand out, whatever its scale. The views are summed, each weighted by the share of the query's words it reads.

## The answer

- **The best ayah** is fetched from the source, in the Uthmani script with the user's translation, and quoted verbatim. The reply names the words that found it.
- **The person's question** is then answered from the ayah's own words, as for a question about a referenced ayah. Furqan checks that answer.
- **Other ayahs** are named only when they are about as likely as chance among the matches: their softmax share of the standardised scores is at least 1/k. Weak hits are left out.
- **When no ayah shares a word with the request,** MIZAN says so and quotes nothing. It does not quote ayahs from memory.
- **When no ayah says it** (`Index.find` → `Found(matches, absent, nearest)`): a query's distinctive words are those carrying more information than its average word (P(topic | word) × the IDF of the views that read it). A distinctive Latin-script word that no view reads, and that a fitted letter model (`fihris_english`, leave-one-out, cached) reads as English, is unused by the Quran. When unused words hold most of the query's distinctive information (2 · Σ unused > Σ), MIZAN answers plainly that no ayah says this ("seven continents": no ayah names them), names those words, and gives the nearest ayah only for what it shares. A transliteration ("kausar", "munhtah") counts a repeated letter once, so it is never called unused.
- **Counts** ("Quran mein kitni ayat hain?", "how many surahs") never search: the `quran_count` recipe reads MIZAN's surah index (114 surahs, 6,236 ayahs in the Hafs count; per surah for "Baqarah mein kitni ayat").

A request that names a reference ("Surah Najm 14") goes to the reference recipe instead.

## How well it does

These were measured on the real index:

| Request | First ayah |
|---|---|
| But quran has mentioned sidra tu munhtah | 53:14 |
| Sidratul muntaha kya hai | 53:14 |
| Quran me Kausar ka zikr | 108:1 |
| Zul Qarnain ka qissa | 18:83 |
| inna lillahi wa inna ilayhi rajiun | 2:156 |
| Hasbunallahu wa nimal wakeel | 3:173 |
| jannat ul firdaus | 23:11 |
| light upon light | 24:35 |
| ayah about patience and prayer | 2:153 (2:45 next) |
| Allah does not burden a soul beyond its capacity | 23:62 (2:286 close) |
| Which surah mentions the elephant? | 105:1 |
| سدرة المنتهى | 53:14 |

**Known gaps:**
- **Roman Urdu meaning words.** "Shahad", meaning honey, finds ayahs about witnesses. The transliteration has *shahid* (witness), and no view holds Roman Urdu meanings.
- **Some Devanagari words.** "सब्र" does not find ayahs on patience, because the Hindi translation uses other words.
- **Quranic phrases Qasd does not yet know.** Some transliterated phrases are still placed as conversation, for example "Hasbunallahu wa nimal wakeel" at P = 0.38 against 0.46. The index finds 3:173 for it; Qasd has to send the request there first.
