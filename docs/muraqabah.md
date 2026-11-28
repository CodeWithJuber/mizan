# Muraqabah: watchers that judge when to interrupt

Personal agents that act on a schedule tend to interrupt too much, at the wrong moment, and never learn. Muraqabah (`backend/automation/muraqabah.py`) gives each user watchers that work for them, with two judgements about when a notice reaches them:
- never during salah
- only as often as the user finds it useful

## Watchers

A watcher pairs a trigger with a task.

| Trigger | Example | Fires |
|---|---|---|
| `daily` | `{"kind": "daily", "time": "20:30"}` | Every day at that local time |
| `prayer` | `{"kind": "prayer", "prayer": "fajr", "offset": 20}` | 20 minutes after Fajr; a negative offset is before |
| `hijri` | `{"kind": "hijri", "days": [13, 14, 15], "time": "20:00"}` | On those days of each Hijri month (Umm al-Qura calendar); `months` narrows it |
| `page` | `{"kind": "page", "url": "https://…", "hours": 6}` | When the page's text changes (read through the web tool and [Amanah](amanah.md)) |

| Task | What runs |
|---|---|
| `ayah_of_the_day` | MIZAN's own: the next ayah of the Quran in order (one a day, the whole Quran over 6,236 days), verbatim from its Quran source, with the Hijri and Gregorian date. No model call. |
| `remind:<text>` | The reminder text. No model call. |
| anything else | A request run through the user's own agent (the watcher's `agent_id` when it names one, else their default agent: [personal agents](personal-agents.md#the-default-agent)) and its gates, so Quran, hadith, dates and calculations come from MIZAN's recipes. No one is watching the run, so an action that needs a person is held for the owner, and the notice says what waits ([agentic coding](agentic-coding.md#runs-no-one-is-watching)). |

Notices go to the user's own **Muraqabah** chat, and also to their devices (Web Push), linked Telegram and linked WhatsApp ([Bab](bab.md)).

A watcher's task can never create another watcher, so a watcher cannot multiply. A user has at most 30 watchers.

## Creating watchers from the chat

Fahm recognises standing requests without a model:

| Message | Watcher |
|---|---|
| "Har subah Fajr ke baad ek ayat aur Hijri date bhejo" | 20 min after Fajr · ayah of the day |
| "Isha ke 10 minute baad mujhe witr padhne ka yaad dilana" | 10 min after Isha · reminder "witr padhne" |
| "15 minutes before Maghrib remind me to break my fast with dates" | 15 min before Maghrib · reminder |
| "every day at 8:30 pm remind me to read Surah Al-Mulk" | 20:30 daily · reminder |
| "har shaam 7 baje mujhe Hijri date bhejo" | 19:00 daily · "Hijri date" (MIZAN's calendar recipe) |

With no number of minutes, "after" a prayer means 20 minutes after and "before" means 30 minutes before. Other wording is mapped by Lisan to a `watch` step. MIZAN validates the trigger and refuses a task that is itself a schedule.

If the message names a city that MIZAN knows ("… Karachi"), that city becomes the user's place.

**Prayer times:** asking "Fajr ka time kya hai?", "Karachi me iftar kab hai" or "prayer times in London" returns today's times, computed by MIZAN for the user's place or the named city:
- Sehri is answered with Fajr and iftar with Maghrib.
- The method and Asr school are stated.
- The user's masjid's own timetable and iqamah come first.

## Quiet around salah

Prayer times are computed on the server with [adhanpy](https://github.com/alphahm/adhanpy), a port of the Adhan astronomical library (MIT licence, no network calls). Each user's place sets:
- the coordinates and time zone
- the calculation method (Karachi, Umm al-Qura, Muslim World League, Egyptian, Dubai, Moonsighting Committee, North America, Kuwait, Qatar, Singapore or UOIF)
- the Asr school (Hanafi or Shafi'i)

Countries get a sensible default; Pakistan, India, Bangladesh, Afghanistan and Turkey default to Hanafi Asr.

Nothing is delivered from **5 minutes before each adhan until 20 minutes after**. On **Friday** the window runs from **30 minutes before Dhuhr until 60 minutes after**, for Jumu'ah. A notice due in a window waits until it ends. The user can turn quiet windows off.

## Attention

Each kind of watcher keeps a Beta posterior per user of how often its notices were useful. It starts at Beta(2, 1), mostly trusting, and learns from the **Useful** and **Not now** buttons on each notice.

When a notice is ready:

1. **During salah** → held until the window ends.
2. **Marked "always"** → delivered.
3. **Today's attention budget used up** (default 6 a day) → into the digest.
4. **Otherwise** → a Thompson draw from the posterior:
   - **≥ 0.5** → delivered.
   - **Below 0.5** → into the digest.

The **digest** arrives once a day at the user's chosen time (default 21:00), outside salah, with everything that waited.

## Places

MIZAN knows 33 cities offline (37 names, counting spellings such as Makkah/Mecca): Makkah, Madinah, Karachi, Lahore, Delhi, Dhaka, Jakarta, Istanbul, Cairo, London, New York and more. Other cities are found with Open-Meteo's free geocoder, or the user enters coordinates.

## API and settings

All routes act on the signed-in user's own watchers.

| Route | Purpose |
|---|---|
| `GET /api/muraqabah` | Watchers, place, today's times and quiet windows, attention, budget |
| `PUT /api/muraqabah/place` | `city`, or `lat`/`lon`/`tz`; `method`, `hanafi`, `budget`, `digest`, `quiet` |
| `POST /api/muraqabah/watchers` | `title`, `trigger`, `task`, `priority` (`judge` or `always`) |
| `PATCH` / `DELETE /api/muraqabah/watchers/{id}` | Change, pause or remove |
| `POST /api/muraqabah/watchers/{id}/run` | Run now; the notice is judged like any other |
| `GET /api/muraqabah/notices` | Recent notices and their status |
| `POST /api/muraqabah/notices/{id}/feedback` | `{"useful": true\|false}` |

- **Admin switch:** `MIZAN_MURAQABAH=on|off` in System settings.
- **Storage:** `$MIZAN_DATA_DIR/muraqabah.db`. All times are stored as UTC.
- **Interface:** the **Watchers** page.
