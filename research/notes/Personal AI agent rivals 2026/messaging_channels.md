# Messaging channels for a self-hosted personal agent (MIZAN), as of 27 October 2026

Scope: how MIZAN, a self-hosted Python/FastAPI personal agent that already has a Telegram bot (Bot API long polling, one-time link codes, inline Allow/Deny buttons) and Web Push, can reach its owner on more channels. WhatsApp is the priority. Registry versions below were read live from PyPI, npm, the Go module proxy and Homebrew on 27 Oct 2026. Items dated before 2026 are marked historical.

## 1. WhatsApp: what exactly do Meta's AI-provider terms ban?

### Takeaway
Section 4.7 of the "Meta Terms for WhatsApp Business Platform" (last modified 23 Sep 2026) bars "AI Providers" from the WhatsApp Business Platform wherever AI is the primary function of what is offered. Meta decides who counts as an AI Provider "in its sole discretion". Two things are excluded: AI that is "incidental or ancillary", and a business that hires an AI vendor as its Solution Provider. Meta also allows such assistants in countries listed on a separate page. In practice these are the markets where regulators forced access.

### Cited Findings
- Historical: Meta announced the change in October 2025. It applied to new Business API accounts from 15 Oct 2025 and to existing AI providers from 15 Jan 2026. OpenAI, Perplexity and Microsoft said their WhatsApp chatbots would stop. — [TechCrunch, 18 Oct 2025](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform/); [TLT LLP timeline, 10 Feb 2026](https://www.tlt.com/insights-and-events/insight/ai-chatbots-and-competition-law-a-look-into-the-meta-whatsapp-antitrust-investigations); [AGCM press release, 24 Dec 2025](https://en.agcm.it/en/media/press-releases/2025/12/A576)
- The current terms are titled "Meta Terms for WhatsApp Business Platform", "Last Modified: September 23, 2026". The old whatsapp.com/legal/business-solution-terms URL now 301-redirects there. — [Meta Terms for WhatsApp Business Platform](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform)
- Section 4.7 says:
  - "AI Providers" are providers and developers of "artificial intelligence or machine learning technologies", including LLMs, generative AI platforms and similar technologies "as determined by Meta in its sole discretion".
  - AI Providers are "strictly prohibited from accessing or using the WhatsApp Business Platform" when such technologies are "the primary (rather than incidental or ancillary) functionality" being offered.
  - Exception: "you may retain an AI Provider as your Solution Provider". Platform data then may not be used to train or improve AI models.
  - Such technologies "may be made available to businesses in certain countries as set forth" on a linked page.
  - Source: [Meta Terms for WhatsApp Business Platform, s.4.7 (23 Sep 2026)](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform)
- Meta's AI Providers pricing page restates the rule: since the 15 Jan 2026 terms update, AI Providers may offer general-purpose assistants only where Meta is legally required to permit it. — [Meta developer docs: AI Providers pricing policy](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers.md)
- The separate WhatsApp Business Messaging Policy (last updated 23 Sep 2026) does not mention AI providers. It does say:
  - automation is allowed in the 24-hour window, but the business "must also have available prompt, clear, and direct escalation paths" (human agent transfer, phone, email, web support and so on);
  - a business may contact people only if they "have given you their mobile phone number or username";
  - the business must keep a profile "with customer support contact information".
  - Source: [WhatsApp Business Messaging Policy](https://whatsappbusiness.com/policy/)
- Secondary reading: one vendor guide describes the effect as a line between open-ended assistants (banned) and business automation for a company's own customers, such as answering questions, booking or order tracking (allowed). — [Alibaba Cloud ChatApp guide](https://www.alibabacloud.com/help/en/chatapp/use-cases/whatsapp-ai-policy-2026-guide); [Galantis blog](https://whatsapp.galantis.com/blog/whatsapp-ai-chatbot-ban-2026)

### Inferences
- The test is functional ("primary" vs "incidental or ancillary") and Meta has sole discretion over it. MIZAN would be a general-purpose assistant offered over WhatsApp, which is the central case the clause targets. Outside the carve-out markets, a WhatsApp Business API number that fronts MIZAN for open-ended chat is at high risk of falling under s.4.7.
- A narrow MIZAN WhatsApp surface fits the "ancillary" reading better than open chat. Examples: prayer-time or watcher notices, approvals of held actions, delivery of results the owner requested elsewhere. The terms do not define "ancillary", so this remains a judgement call.

### Gaps
- The linked country page in s.4.7 was not retrieved. The country list below comes from the AI Providers pricing page, not from the terms.
- I found no Meta text that addresses a single-user, self-hosted assistant.

## 2. WhatsApp: antitrust actions and their status (Oct 2026)

### Takeaway
Regulators have forced Meta to readmit general-purpose AI assistants in three places:
- **EEA (European Commission):** interim measures of 9 Jun 2026 require free access on the pre-15-Oct-2025 terms. Meta appealed to the General Court in August 2026, and the appeal is pending.
- **Brazil (CADE):** a preventive measure was upheld on 4 Mar 2026. Meta charges US$0.0625 per non-template AI message there, and CADE treats that fee as non-compliance.
- **Türkiye (Competition Board):** interim measure announced 5 Jun 2026. Meta lists Türkiye as allowed, with no charge, from 15 Oct 2026.

Italy's separate case was folded into the Commission's case and closed on 19 May 2026. Everywhere else, the ban stands.

### Cited Findings
- **Italy (AGCM, case A576):**
  - Opened 22 Jul 2025 over Meta AI's integration into WhatsApp (Art. 102 TFEU). Widened on 25 Nov 2025 to cover the new terms.
  - On 22 Dec 2025 (announced 24 Dec 2025) AGCM ordered Meta to "immediately suspend the WhatsApp Business Solution Terms" insofar as they exclude rival chatbots, under art. 14-bis of Law 287/1990.
  - Meta called the measure "fundamentally flawed" and said it would appeal.
  - Sources: [AGCM press release, 24 Dec 2025](https://en.agcm.it/en/media/press-releases/2025/12/A576); [Tomkiel law firm note](https://tomkielaw.com/en/european-commission-orders-interim-measures-against-metas-exclusion-of-rival-ai-chatbots/); [Wolters Kluwer competition blog](https://legalblogs.wolterskluwer.com/competition-blog/the-italian-competition-authority-imposes-interim-measures-in-its-abuse-of-dominance-case-against-meta-ai/)
- **European Commission, case AT.41034 "Exclusion of AI competitors from WhatsApp":**
  - Proceedings opened 4 Dec 2025. The Tomkiel note also prints the number as AT.40134 in its introduction, an internal inconsistency.
  - Statement of Objections issued 9 Feb 2026: the policy "appears at first sight to be in breach of EU competition rules".
  - In March 2026 Meta readmitted rivals for a fee. The Commission amended its objections, holding the fee "equivalent in effect to the original ban".
  - On 15 Apr 2026 the investigation was extended to Italy. AGCM then closed its own case on 19 May 2026 (resolution No. 31971) under Art. 11(6) Reg. 1/2003.
  - Interim measures were adopted 9 Jun 2026, EEA-wide. Meta must "re-instate access for third-party general-purpose AI assistants" to the WhatsApp Business API on pre-15-Oct-2025 terms, "notably, free of charge", until the final decision.
  - The AI chatbot Poke returned to WhatsApp on about 11 Jun 2026.
  - Sources: [TLT, 10 Feb 2026](https://www.tlt.com/insights-and-events/insight/ai-chatbots-and-competition-law-a-look-into-the-meta-whatsapp-antitrust-investigations); [Tomkiel note](https://tomkielaw.com/en/european-commission-orders-interim-measures-against-metas-exclusion-of-rival-ai-chatbots/); [Houthoff, 18 Jun 2026](https://www.houthoff.com/insights/news/a-rare-show-offorce-commission-deploys-interim-measures-against-meta-to-safeguard-ai-competition/); Commission press release [IP/26/1276](https://ec.europa.eu/commission/presscorner/detail/en/ip_26_1276), cited by Houthoff (my fetch returned 403)
- **Interim-measure details from secondary sources only, not checked against the Commission text:**
  - five working days to comply;
  - the measure lasts until the final decision or June 2029, whichever is first;
  - fines of up to 10% of turnover, or periodic penalties of up to 5% of average daily turnover;
  - Meta called it "regulatory overreach";
  - before the decision, Meta had offered EEA AI chatbots free access for 12 months, and a month of free access as part of talks with the Commission.
  - Sources: [Decrypt](https://decrypt.co/370580/eu-orders-meta-open-whatsapp-rival-ai-chatbots); [Neowin](https://www.neowin.net/news/eu-says-meta-must-restore-rival-chatbots-access-to-whatsapp/); [Reuters via Yahoo Finance](https://finance.yahoo.com/news/meta-allow-ai-rivals-whatsapp-122729247.html); [EU Perspectives, June 2026](https://euperspectives.eu/2026/06/commission-gives-meta-five-days-to-open-whatsapp-ai-to-competition/) (fetch returned 503; claim seen in search snippet)
- **Appeal:** Meta appealed the interim measures decision to the General Court in August 2026, advised by Slaughter and May. The page does not give a case number or say whether suspension was sought. — [Slaughter and May, 25 Aug 2026](https://www.slaughterandmay.com/recent-work/meta-on-its-appeal-against-the-european-commission-s-whatsapp-interim-measures-decision/)
- **Brazil (CADE):**
  - Inquiry opened in January 2026 after complaints by Luzia and Zapia in September 2025. Temporary injunction issued 12 Jan 2026.
  - Meta's appeal to suspend it was reported as successful on 23 Jan 2026. The CADE tribunal then unanimously upheld the preventive measure on 4 Mar 2026.
  - Meta began charging $0.0625 per non-template message to Brazilian users from 11 Mar 2026. Meta said: "we are introducing pricing for the companies that choose to use our platform to provide those services."
  - CADE kept a daily fine of R$250,000 because it treats the pricing as non-compliance. This last point comes from Portuguese-language secondary reports.
  - Sources: [TLT](https://www.tlt.com/insights-and-events/insight/ai-chatbots-and-competition-law-a-look-into-the-meta-whatsapp-antitrust-investigations); [TechCrunch, 6 Mar 2026](https://techcrunch.com/2026/03/06/after-europe-whatsapp-will-let-rival-ai-companies-offer-chatbots-in-brazil/); [CNN Brasil](https://www.cnnbrasil.com.br/economia/negocios/cade-mantem-medida-preventiva-que-obriga-meta-a-permitir-chatbots-de-ia-no-whatsapp/); [Observador, 30 Mar 2026](https://observador.pt/2026/03/30/brasil-mantem-multa-diaria-de-40-mil-euros-ao-whatsapp-e-meta/)
- **Türkiye (Rekabet Kurulu):**
  - Decision 26-18/536-193 at the 14 May 2026 meeting, announced 5 Jun 2026.
  - The Board opened an investigation under Art. 6 of Law 4054. It ordered Meta to create conditions under which third-party general-purpose generative AI chatbots can offer their primary service via WhatsApp, within one month of notification.
  - Sources: [Alomaliye, 5 Jun 2026](https://www.alomaliye.com/2026/06/05/rekabet-kurulundan-meta-karari-sorusturma-acildi-gecici-tedbir-uygulanacak/); [NTV](https://www.ntv.com.tr/ntvpara/rekabet-kurumundan-metaya-tedbir-ve-sorusturma-1727345)
- **COMESA:** a complaint was filed with the COMESA Competition and Consumer Commission on 5 Jan 2026. No decision had been reported as of 10 Feb 2026. — [TLT](https://www.tlt.com/insights-and-events/insight/ai-chatbots-and-competition-law-a-look-into-the-meta-whatsapp-antitrust-investigations)
- **How Meta implemented it, per its AI Providers pricing page:**
  - Italy (+39): charged from 16 Feb to 12 May 2026; not charged from 13 May 2026. A secondary report gave about $0.0691 per AI response in Italy.
  - Brazil (+55): charged from 11 Mar 2026, with no end date.
  - 29 EU/EEA markets (AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IS, IE, LV, LI, LT, LU, MT, NL, NO, PL, PT, RO, SK, SI, ES, SE): charged from 11 Mar to 12 May 2026; not charged from 13 May 2026.
  - Türkiye (+90): added "not charged" from 15 Oct 2026.
  - The service-message charges that begin 1 Oct 2026 "do not apply to AI Providers".
  - Sources: [Meta AI Providers pricing policy](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers.md); [Meta pricing page](https://developers.facebook.com/docs/whatsapp/pricing); [TechBuzz (Italy rate)](https://www.techbuzz.ai/articles/meta-charges-ai-chatbot-devs-0-07-msg-on-whatsapp-in-italy)

### Inferences
- In the EEA, Italy and Türkiye, a general-purpose AI assistant may now use the Business Platform without an AI-specific per-message charge. In Brazil it may do so for $0.0625 per non-template message. This is Meta's legally compelled position: the EEA measure is interim, and Meta's appeal is pending.
- Because the access in each country is court- or regulator-dependent, MIZAN should treat WhatsApp Cloud API as a region-gated channel that can be withdrawn. Gate it on the owner's country code and keep Telegram or Web Push as the fallback.

### Gaps
- I could not confirm whether Meta formally complied with the 9 Jun 2026 order beyond the charge removal recorded on its pricing page.
- Also unconfirmed: the General Court case number, any interim-relief ruling, and whether the CADE daily fine is still accruing in October 2026.
- Whether ChatGPT returned to WhatsApp in the EEA is reported only by a low-quality blog, so I omitted it.

## 3. WhatsApp: can an owner-only personal assistant use the Cloud API legally?

### Takeaway
It is legally unclear and depends on the owner's country.

- **EEA, Italy and Türkiye numbers:** the compelled access makes owner-only use defensible. The assistant would still be a "business" messaging its own opted-in "customer".
- **Brazil:** the same applies, but AI messages are paid.
- **Everywhere else:** an assistant whose WhatsApp purpose is general AI chat probably falls under s.4.7.

Beyond that, the Business Messaging Policy assumes a real business. It expects a support-contact profile and human escalation paths for automation. A one-person "business" fits these awkwardly. I found nothing in Meta's documents that explicitly allows or forbids it.

### Cited Findings
- The platform is described as letting "businesses … send or receive messages or calls" and "interact with consumer users on the WhatsApp network". The terms contain no "personal use" clause and no clause limiting messaging to a business's own customers. — [Meta Terms for WhatsApp Business Platform, s.1.1](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform)
- AI Providers are prohibited where AI is the primary function, as determined "in its sole discretion". A business may retain an AI Provider as its Solution Provider. — [same, s.4.7](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform)
- Requirements on any business sender:
  - opt-in (the user gave you their number or username);
  - a business profile with customer-support contact information;
  - "prompt, clear, and direct escalation paths" when automating;
  - Meta "may limit or remove your access", up to banning "you and your organization from all future use of WhatsApp products and services".
  - Source: [WhatsApp Business Messaging Policy, 23 Sep 2026](https://whatsappbusiness.com/policy/)
- New business portfolios start with a messaging limit of 250 unique users per moving 24 hours. Business verification raises it to 2,000. The limit counts only messages sent outside a customer-service window. — [Meta: messaging limits](https://developers.facebook.com/docs/whatsapp/messaging-limits)

### Inferences
- **Practical reading:** one owner messaging their own MIZAN number creates one opted-in user, so scale limits do not matter. The live risks are classification under s.4.7 and Meta's discretionary enforcement, not volume.
- **Lowest-risk design outside the carve-out markets:** use WhatsApp only for ancillary functions. Examples are templated utility notifications (a watcher fired, an action is held, a reply is ready) with deep links back to the MIZAN web app or Telegram, rather than open-ended AI chat. This still relies on "ancillary" being read in MIZAN's favour.
- MIZAN must not train on WhatsApp data. Its Ruh learner (`backend/learner/`) should exclude WhatsApp-origin messages, to respect the s.4.7 no-training condition when an AI Provider is retained.

### Gaps
- There is no ruling or Meta guidance on whether a self-hosted, single-user agent counts as an "AI Provider" or as a "business".
- This is not legal advice. The owner should read s.4.7 and the linked country page before enabling the channel.

## 4. WhatsApp Cloud API: pricing and 24-hour window (Oct 2026)

### Takeaway
Since 1 Jul 2025, Meta bills per delivered message, by category and recipient country. Two changes took effect on 1 Oct 2026:
- Service messages (free-form replies inside the 24-hour customer service window) are charged again beyond 1,000 free per number per month.
- Utility templates sent inside the window are charged again.

Outside the window, only paid templates can be sent. For a single owner, replies are effectively free. Proactive notices after 24 hours of owner silence cost a utility-template fee each.

### Cited Findings
- **Per-message model:** "Meta charges on a per-message basis" (since 1 Jul 2025). Undelivered messages and user-to-business messages are free. The categories are:
  - Marketing, Utility and Authentication (templates);
  - Service (non-template replies in an open window, "including by people or third-party AI");
  - Meta Business Agent (token-billed).
  - Source: [Meta: Pricing on the WhatsApp Business Platform](https://developers.facebook.com/docs/whatsapp/pricing)
- **Customer service window:** a 24-hour timer starts when the user messages or calls and resets on each new user message. "Businesses can only send non-template messages to users when this window is open". Outside it, only template messages may be sent. — [Meta pricing page](https://developers.facebook.com/docs/whatsapp/pricing)
- **From 1 Oct 2026:**
  - "Each business phone number has one free tier of 1,000 delivered service messages per month". Beyond that, service messages are charged at the market's utility/authentication rate, with no volume tiers.
  - Utility messages sent inside the window, free since 1 Jul 2025, are charged again.
  - Without a payment method by 30 Sep 2026, service messages stop after the free tier.
  - Sources: [Meta pricing page](https://developers.facebook.com/docs/whatsapp/pricing); [Meta: upcoming pricing updates for non-template messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages)
- **Example rate:** Brazil utility/authentication was about 0.68 US cents per message as of 1 Jul 2026. Other markets are in rate-card files that I did not retrieve. — [Meta non-template pricing page](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages)
- **Free entry point:** after a click-to-WhatsApp ad, "The FEP window may remain open for up to 7 days", and messages in it are free. — [Meta pricing page](https://developers.facebook.com/docs/whatsapp/pricing)
- **Meta Business Agent (Meta's own AI, launched 1 Jul 2026, billed from 1 Aug 2026):** "$2.00 USD per 1 million (M) tokens". A typical message uses about 20–25k tokens, roughly 4–5 cents. — [Meta non-template pricing page](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages)
- **2026 rate changes:**
  - 1 Jan: Egypt and France marketing down, India up.
  - 1 Apr: Pakistan utility/authentication up, Saudi Arabia marketing up.
  - 1 Jul: nine markets changed.
  - 1 Oct: nine markets moved out of the "Rest of" regions.
  - Source: [Meta pricing page](https://developers.facebook.com/docs/whatsapp/pricing)

### Inferences
- **Owner-only cost model:** owner→MIZAN and MIZAN→owner replies within 24 hours fall under the 1,000/month free tier. AI-provider charges apply only in Brazil at $0.0625. Watcher or prayer-time notices sent when the owner has been silent for more than 24 hours need an approved utility template and are billed per message at the owner's country rate.
- MIZAN's Muraqabah budget should prefer Telegram or Web Push for routine notices. Iqtisad should account for WhatsApp template costs as a paid action.

### Gaps
- Rate-card CSV/PDF values for key MIZAN markets (Saudi Arabia, Pakistan, India, Indonesia, Egypt, UK, US) were not retrieved.

## 5. WhatsApp unofficial routes: Baileys, whatsapp-web.js, whatsmeow, and documented bans

### Takeaway
All three libraries emulate a WhatsApp Web or linked-device client. That conflicts with WhatsApp's consumer Terms, which prohibit auto-messaging, reverse engineering and automated access. They are well maintained in October 2026, but the ban risk is real and documented, including multi-day restrictions after reconnect storms. They avoid Meta's AI-provider rule only by not using the Business Platform at all.

### Cited Findings
- **WhatsApp consumer Terms (version shown: effective 4 Jan 2021).** Prohibited:
  - "bulk messaging, auto-messaging, auto-dialing, and the like";
  - to "reverse engineer, alter, modify, create derivative works from, decompile, or extract code from our Services";
  - accessing the services "through automated or other means";
  - creating accounts "through unauthorized or automated means".
  - Source: [WhatsApp Terms of Service](https://www.whatsapp.com/legal/terms-of-service)
- **Baileys** (npm `baileys` / `@whiskeysockets/baileys`):
  - MIT licence. Latest is 7.0.0-rc14, published 29 Jul 2026; 7.0.0 introduced "multiple breaking changes".
  - README: "not affiliated, associated, authorized, endorsed by, or in any way officially connected with WhatsApp". The maintainers "do not in any way condone" ToS violations and "discourage any stalkerware, bulk or automated messaging usage".
  - Sources: [npm registry: baileys](https://registry.npmjs.org/baileys); [Baileys README](https://github.com/WhiskeySockets/Baileys)
- **whatsapp-web.js:** Apache-2.0, latest 1.34.7 (24 Apr 2026). It drives WhatsApp Web through a headless browser (Puppeteer). — [npm registry: whatsapp-web.js](https://registry.npmjs.org/whatsapp-web.js)
- **whatsmeow** (Go, `go.mau.fi/whatsmeow`):
  - MPL-2.0. "a Go library for the WhatsApp web multidevice API".
  - Supports text and media, groups, receipts, app state and retry receipts. Broadcast lists and calls are not implemented.
  - It has no tagged releases. The latest pseudo-version is from a commit on 27 Oct 2026.
  - Python wrapper: `neonize` 0.5.2 (21 Sep 2026); licence not stated in PyPI metadata.
  - Sources: [whatsmeow README](https://github.com/tulir/whatsmeow); [Go proxy @latest](https://proxy.golang.org/go.mau.fi/whatsmeow/@latest); [PyPI neonize](https://pypi.org/pypi/neonize/json)
- **Documented ban (OpenClaw issue #16270, 14 Feb 2026):** two competing systemd services caused "3,500+ Baileys connection cycles in ~3 hours". The account was restricted and could not re-link for 72+ hours; the reporter says restrictions "persist 48-72+ hours". A circuit-breaker request was auto-closed "not planned" on 18 Mar 2026. — [openclaw/openclaw#16270](https://github.com/openclaw/openclaw/issues/16270)
- **OpenClaw issue #23093 (22 Feb 2026):** reports that Baileys "causes frequent session logouts, 401 errors, and account bans". It links reports of stuck logins, "can't link new devices", and a bot that mass-messaged contacts. The request for official Cloud API support was auto-closed "not planned" on 20 Mar 2026, with no maintainer reply. — [openclaw/openclaw#23093](https://github.com/openclaw/openclaw/issues/23093)
- **Anecdotal ban timelines** (same-day, within 48 hours, "within days") come from commercial blogs. They advise a dedicated number, low outbound volume and no identical messages to many recipients. — [OpenClaw.Direct](https://openclaw.direct/blog/whatsapp-ban-openclaw-telegram-setup); [OpenClawDC](https://openclawdc.com/blog/openclaw-whatsapp-bot/); [Blink](https://blink.new/blog/openclaw-whatsapp-setup-status-2026); [VoidMob](https://voidmob.com/learn/openclaw-whatsapp-number)

### Inferences
- **If MIZAN offers an unofficial WhatsApp route at all:**
  - make it opt-in and clearly labelled "unofficial – your number can be restricted";
  - use a dedicated number and self-chat or owner-only mode;
  - never send outbound to non-owners;
  - add exponential backoff and a reconnect circuit breaker (the #16270 failure mode);
  - run it as a separate process: Baileys is Node and whatsapp-web.js needs a browser.
- The lowest-maintenance unofficial path is the mautrix-whatsapp bridge (whatsmeow), which a dedicated project keeps current (see section 8), not embedding Baileys.

### Gaps
- The body of WhatsApp's Help Center page "About unofficial apps" did not render, so its exact ban wording is unquoted.
- Meta publishes no detection criteria.
- I found no ban data specific to whatsmeow or whatsapp-web.js.

## 6. How OpenClaw and Hermes Agent connect to WhatsApp, and what happened to their users

### Takeaway
- **OpenClaw:** reaches WhatsApp only through Baileys as a linked WhatsApp Web device. Its docs carry no ban or ToS warning, and the project closed requests for Cloud API support. Users have reported 401 logouts and 48–72-hour or longer restrictions.
- **Hermes Agent (Nous Research):** ships both a Baileys bridge, with an explicit warning about restriction risk, and a separate "WhatsApp Cloud API" platform. Both gateways deny unknown senders by default and use expiring pairing codes.

### Cited Findings
- **OpenClaw WhatsApp channel:**
  - "production-ready via WhatsApp Web (Baileys)". Login is QR-only (`openclaw channels login --channel whatsapp`), and there is "no separate Twilio WhatsApp channel".
  - `dmPolicy` is `pairing` (default), `allowlist`, `open` (requires `"*"`) or `disabled`. Pairing requests expire after 1 hour, with at most 3 pending.
  - Group rules: `groupPolicy` and `groupAllowFrom`, with `requireMention` on by default. "Replying to an allowlisted user does not grant sender authorization."
  - `mediaMaxMb` defaults to 50; voice is transcoded with ffmpeg.
  - "A separate WhatsApp number is recommended"; personal-number and self-chat setups are supported.
  - No ban or ToS warning appears.
  - Source: [OpenClaw docs: WhatsApp](https://docs.openclaw.ai/channels/whatsapp)
- OpenClaw is MIT, npm `openclaw` 2026.10.8, published 27 Oct 2026. — [npm registry: openclaw](https://registry.npmjs.org/openclaw)
- **User outcomes:** see section 5 (#16270 restriction for 72+ hours; #23093 logouts and bans). Both were closed by a stale bot, not fixed. — [#16270](https://github.com/openclaw/openclaw/issues/16270); [#23093](https://github.com/openclaw/openclaw/issues/23093)
- **Hermes Agent WhatsApp:**
  - "built-in bridge based on Baileys", "not through the official WhatsApp Business API". It needs Node.js 18+ and pairs via `hermes whatsapp` and a QR code.
  - Warnings, quoted: "WhatsApp does **not** officially support third-party bots outside the Business API" and "Using a third-party bridge carries a small risk of account restrictions".
  - Advice: use a dedicated number (Google Voice, prepaid SIM or VoIP), avoid bulk messages, and do not message people who have not written first.
  - Modes are `WHATSAPP_MODE=bot` or `self-chat`. Access is controlled by `WHATSAPP_ALLOWED_USERS`; if nothing is set, all messages are denied.
  - The Cloud API is offered as a separate guide. It requires a Meta Business account and a public webhook URL.
  - Source: [Hermes docs: WhatsApp](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/whatsapp)
- **Hermes gateway overall:**
  - Platforms: Telegram, Discord, Slack, Google Chat, Mattermost, Matrix, Teams, LINE, ntfy, IRC, SimpleX, WhatsApp, WhatsApp Cloud API, Signal, SMS, Email, BlueBubbles and Photon (iMessage), plus several Chinese platforms.
  - "By default, the gateway denies all users who are not in an allowlist or paired via DM."
  - Pairing codes are one-time, expire after 1 hour, are rate-limited and cryptographically random: `hermes pairing approve <platform> <code>`.
  - It has separate admin and user command scopes for DMs and groups, and `/approve` and `/deny` for dangerous commands.
  - Source: [Hermes docs: Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)

### Inferences
- Neither project solves the policy problem. OpenClaw ignores it. Hermes documents both routes, leaving the ToS choice to the user.
- MIZAN can stand apart by defaulting to the official Cloud API where Meta must allow AI assistants, and labelling everything else as unofficial.

### Gaps
- Hermes ban reports were not searched separately.
- Hermes's Cloud API guide (`/whatsapp-cloud`) was not read.

## 7. Signal: signal-cli, libsignal licence, and how bots work

### Takeaway
Signal has no official bot API. Bots are ordinary accounts driven by the unofficial signal-cli. signal-cli is GPL-3.0, 0.14.9, requires Java 25, and must be updated roughly every three months. libsignal is AGPLv3, and Signal says "Use outside of Signal is unsupported". Signal's Terms prohibit auto-messaging and unauthorized access. A one-to-one owner bot carries low but nonzero ToS risk, and there is no Signal equivalent of Meta's AI rule.

### Cited Findings
- **signal-cli:**
  - Describes itself as "an unofficial command-line, JSON-RPC, and D-Bus interface"; "Licensed under the GPLv3".
  - It can `link` as a secondary device to an existing account or register its own number. Registering "will unregister any existing client associated with the same number".
  - "needs to be kept up-to-date to keep up with Signal-Server changes". Releases older than three months "may not work correctly".
  - Requires JRE 25. It is "primarily intended to be used on servers to notify admins".
  - Source: [signal-cli README](https://github.com/AsamK/signal-cli)
- signal-cli 0.14.9 (Homebrew stable, GPL-3.0-or-later). The GitHub release of 7 Oct added the SSE endpoint Last-Event-ID replay and support for linking phone-numberless accounts. — [Homebrew formula JSON](https://formulae.brew.sh/api/formula/signal-cli.json); [signal-cli releases](https://github.com/AsamK/signal-cli/releases)
- **libsignal:** "Licensed under the GNU AGPLv3", "Copyright 2020-2026 Signal Messenger, LLC", "Use outside of Signal is unsupported", "All APIs and implementations are subject to change without notice". — [libsignal README](https://github.com/signalapp/libsignal)
- **Signal Terms** prohibit:
  - "bulk messaging, auto-messaging, and auto-dialing";
  - creating accounts "through unauthorized or automated means";
  - using the services "in unauthorized manners".
  - Source: [Signal Terms & Privacy Policy](https://signal.org/legal/)
- **Python options:** `signalbot` 2.2.1 (MIT, 25 Oct 2026), which builds on signal-cli-rest-api. `semaphore-bot` (AGPLv3+) was last released in December 2023 and is stale. — [PyPI signalbot](https://pypi.org/pypi/signalbot/json); [PyPI semaphore-bot](https://pypi.org/pypi/semaphore-bot/json)
- Forum reports: there is no official bot API, Signal rate-limits automation, and each bot needs its own number. These are anecdotal. — [r/signal thread (mirror)](https://reddit.birdcat.cafe/r/signal/comments/1jpz0d9/signal_developer_api)

### Inferences
- **Best pattern:** run signal-cli in `daemon --http` or JSON-RPC mode in a sidecar container, linked to a dedicated number. MIZAN talks to it over localhost JSON-RPC or SSE, which avoids linking GPL/AGPL code into Apache-2.0 MIZAN. Enforce an owner-only allowlist by Signal ACI/UUID, and auto-update the container monthly.
- Alternatively, use mautrix-signal through Matrix (section 8), which also wraps libsignal.

### Gaps
- No official Signal statement on bots or on signal-cli was found.

## 8. Matrix: matrix-nio, mautrix, and bridges as a self-hosted path

### Takeaway
Matrix is the most maintainable "many networks, keys on your server" path. MIZAN would speak one protocol (Matrix, through the mautrix-python or matrix-nio client). The mautrix bridges for WhatsApp, Signal, Telegram, Meta and Google Messages, all AGPL-3.0 and released monthly, would absorb the protocol churn. End-to-bridge encryption keeps content off the homeserver's disk. The bridge still holds the WhatsApp or Signal session, so WhatsApp's unofficial-client ban risk remains.

### Cited Findings
- **Python clients:** `matrix-nio` 0.26.0 (ISC licence, 23 Jul 2026) and `mautrix` (python) 0.21.1 (MPL-2.0, 5 Jul 2026). Higher-level wrappers: `simplematrixbotlib` 2.13.1 (MIT, 29 Mar 2026) and `nio-bot` 1.2.1 (LGPLv3, May 2025). — [PyPI matrix-nio](https://pypi.org/pypi/matrix-nio/json); [PyPI mautrix](https://pypi.org/pypi/mautrix/json); [PyPI simplematrixbotlib](https://pypi.org/pypi/simplematrixbotlib/json); [PyPI nio-bot](https://pypi.org/pypi/nio-bot/json)
- **Bridges and Go library:**
  - mautrix-go v0.32.0 (16 Oct 2026).
  - mautrix-whatsapp, -signal, -telegram, -meta and -gmessages are all v0.2610.0 (16 Oct 2026), all Go. The Telegram bridge is now under the Go module path `go.mau.fi/mautrix-telegram`.
  - Sources: Go proxy [mautrix-go](https://proxy.golang.org/maunium.net/go/mautrix/@latest), [whatsapp](https://proxy.golang.org/go.mau.fi/mautrix-whatsapp/@latest), [signal](https://proxy.golang.org/go.mau.fi/mautrix-signal/@latest), [telegram](https://proxy.golang.org/go.mau.fi/mautrix-telegram/@latest), [meta](https://proxy.golang.org/go.mau.fi/mautrix-meta/@latest), [gmessages](https://proxy.golang.org/go.mau.fi/mautrix-gmessages/@latest)
- **mautrix-whatsapp:** AGPL-3.0 with a LICENSE.exceptions file; "A Matrix-WhatsApp puppeting bridge based on whatsmeow". The docs are "mostly targeted towards people who are hosting the bridge themselves". Public instances include beeper.com and tchncs.de. Logs contain phone numbers. — [mautrix/whatsapp](https://github.com/mautrix/whatsapp); [docs.mau.fi WhatsApp](https://docs.mau.fi/bridges/go/whatsapp/index.html)
- **End-to-bridge encryption:**
  - "The bridge can optionally encrypt messages between Matrix users and the bridge to hide messages from the homeserver". Without it, unencrypted-room events are stored in plaintext in the homeserver DB.
  - Settings: `encryption.allow`, `default`, `require`, `self_sign`, `msc4190` (needed for OAuth/MAS next-gen auth) and `delete_keys`.
  - The bridge itself decrypts in order to talk to the remote network.
  - Source: [mautrix docs: End-to-bridge encryption](https://docs.mau.fi/bridges/general/end-to-bridge-encryption.html)
- Hermes also supports Matrix (`MATRIX_ALLOWED_USERS`). — [Hermes Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)

### Inferences
- **Architecture:** a self-hosted homeserver (Synapse, Conduit or Tuwunel), mautrix bridges as separate containers, and MIZAN as a Matrix bot user via mautrix-python, MPL-2.0 and asyncio, which matches MIZAN's stack.
  - The owner pairs WhatsApp or Signal into the bridge from their own account.
  - MIZAN sees each bridged chat as a Matrix room.
  - One adapter then serves WhatsApp, Signal, Telegram-as-user, Messenger/Instagram and Google Messages (SMS/RCS).
- **Licensing:** the bridges are AGPL. Running them unmodified as separate network services does not, in the usual reading, impose AGPL on Apache-2.0 MIZAN. This is not legal advice.
- **Cost:** heavy operations (homeserver, Postgres, several bridges). It suits power users. MIZAN should offer it as an advanced option and keep direct official APIs as the default.

### Gaps
- No public ban statistics specific to mautrix-whatsapp were found.

## 9. Discord, Slack (Socket Mode), email (IMAP IDLE/SMTP, JMAP), SMS/RCS

### Takeaway
- **Discord and Slack:** both allow bots, and an owner-only bot is clearly permitted. Slack's 2025 limits on data access spare internal, customer-built apps. Discord bots receive DM content without the privileged intent.
- **Email:** the most universal channel. Use IMAP IDLE and SMTP via asyncio libraries, or JMAP where the provider supports it. It is the highest-risk channel for prompt injection.
- **SMS in the US:** requires A2P 10DLC registration, with small fees.
- **RCS:** carrier-vetted brand onboarding. It is not suitable for a personal agent except through the Google Messages bridge.

### Cited Findings
- **Slack:**
  - The API terms update of 29 May 2025 set `conversations.history` and `conversations.replies` to 1 request/minute and a 15-object limit, for new commercially distributed non-Marketplace apps.
  - "Internal customer-built applications are not impacted by these changes"; internal custom apps get 50+ requests/minute and a 1,000-object limit.
  - The stated reason is to "prevent bulk data exfiltration by unvetted applications".
  - Python libraries: `slack-bolt` 1.30.0 (MIT, 15 Jul 2026) and `slack-sdk` 3.45.0 (MIT, 1 Oct 2026). Socket Mode avoids needing a public webhook.
  - Sources: [Slack changelog, 29 May 2025](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps); [PyPI slack-bolt](https://pypi.org/pypi/slack-bolt/json); [PyPI slack-sdk](https://pypi.org/pypi/slack-sdk/json)
- **Discord:**
  - `MESSAGE_CONTENT` is a privileged intent. Without it, apps "will receive empty values" in content fields, except in messages the app sends, in DMs with the app, and in messages that mention it.
  - Approval is needed for verified apps (100+ servers); a review applies above 10,000 users.
  - The gateway limit is 120 events per 60 seconds per connection.
  - Library: `discord.py` 2.7.1 (MIT, 3 Mar 2026).
  - Sources: [Discord docs: Gateway, Message Content intent](https://docs.discord.com/developers/events/gateway#message-content-intent); [PyPI discord.py](https://pypi.org/pypi/discord.py/json)
- **Email standards:** IMAP IDLE ([RFC 2177, June 1997](https://www.rfc-editor.org/rfc/rfc2177)), JMAP core ([RFC 8620, July 2019](https://www.rfc-editor.org/rfc/rfc8620)) and JMAP Mail ([RFC 8621, August 2019](https://www.rfc-editor.org/rfc/rfc8621)).
- **Email libraries:**
  - `aioimaplib` 2.0.3 (GPL-3.0-only, 13 Oct 2026);
  - `IMAPClient` 4.1.0 (18 Sep 2026; licence not shown in metadata);
  - `aiosmtplib` 5.1.3 (MIT, 8 Sep 2026);
  - `jmapc` 0.4.0 (GPL-3.0-only, 11 Oct 2026).
  - Sources: [PyPI aioimaplib](https://pypi.org/pypi/aioimaplib/json); [PyPI IMAPClient](https://pypi.org/pypi/IMAPClient/json); [PyPI aiosmtplib](https://pypi.org/pypi/aiosmtplib/json); [PyPI jmapc](https://pypi.org/pypi/jmapc/json)
- Hermes ignores unknown email senders unless email pairing is enabled. — [Hermes Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
- **US SMS (Twilio A2P 10DLC), sole proprietor:**
  - $4.50 one-time brand fee, $15 one-time campaign vetting and $2 per month per campaign.
  - Limited to 1 campaign, 1 number and 1 message segment per second; for people without an EIN.
  - A standard brand costs $46 one-time. Older Twilio pages give $4 and $44, so check the Console.
  - The `twilio` Python SDK is 9.12.0 (MIT, 12 Oct 2026).
  - Sources: [Twilio support: Starter/Low-Volume/Standard comparison](https://support.twilio.com/hc/en-us/articles/4407882914971-Comparison-between-Starter-Low-Volume-Standard-and-Standard-registration-for-A2P-10DLC); [PyPI twilio](https://pypi.org/pypi/twilio/json)
- **US RCS via Twilio:**
  - Brand vetting by Aegis Mobile, which charges an annual fee. Carriers such as T-Mobile charge a one-time onboarding fee per sender and "may approve or reject any use case".
  - It requires an EIN or FTIN, logo and legal address.
  - Twilio expects carrier standards to be developed in 2026.
  - Source: [Twilio US RCS guidelines (undated)](https://www.twilio.com/en-us/guidelines/us/rcs)

### Inferences
- Slack and Discord are low-risk "workspace" channels. MIZAN should install as an internal Slack app, so the rate limits do not bite, and as a DM-only Discord bot, so the privileged intent is not needed.
- GPL email libraries (aioimaplib, jmapc) would be imported into Apache-2.0 MIZAN. Prefer `IMAPClient`, in a thread, after checking its licence, or the stdlib `imaplib` wrapped in asyncio, plus `aiosmtplib` (MIT). Alternatively, run the GPL tool as a separate process.
- **Email sender authentication:** check DMARC, SPF and DKIM results and accept only the owner's address. Treat every mail body as untrusted data, which MIZAN's Amanah already does.
- **SMS/RCS:** a personal agent should use the owner's own phone via mautrix-gmessages (section 8) instead of A2P registration, unless it is in the US and willing to register as a sole proprietor.

### Gaps
- Discord's developer policy on AI bots and Slack's API Terms text on LLM data use were not retrieved; the changelog does not mention LLMs.
- Non-US SMS rules were not covered.

## 10. iMessage: BlueBubbles and Apple Messages for Business

### Takeaway
There is no official iMessage bot API for individuals. BlueBubbles needs an always-on Mac signed into the owner's Apple ID. For edit, typing indicators and similar features, its Private API requires turning off System Integrity Protection. Apple Messages for Business is only for registered businesses through an approved Messaging Service Provider and requires live agents, so it does not fit a personal agent.

### Cited Findings
- BlueBubbles Private API features require disabling SIP, which the docs compare to jailbreaking. The helper supports macOS 10.13+ on Intel and Apple Silicon. On Apple Silicon, disabling SIP also disables running iOS apps on the Mac. Basic messaging works without the helper. — [BlueBubbles docs: Private API installation](https://docs.bluebubbles.app/private-api/installation); [BlueBubbles FAQ](https://bluebubbles.app/faq/)
- OpenClaw's BlueBubbles channel uses the BlueBubbles REST API (`/api/v1/ping`, `/message/text`). It is tested on macOS Sequoia 15; on Tahoe 26, edit is broken. — [OpenClaw BlueBubbles doc (npm mirror)](https://cdn.jsdelivr.net/npm/openclaw1@2026.2.1/docs/channels/bluebubbles.md)
- Hermes supports "BlueBubbles and Photon (iMessage)". — [Hermes Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
- Apple Messages for Business:
  - requires an Apple-approved MSP and registration through Apple Business Register;
  - Apple's policies require a live agent during business hours, and "bot-only solutions are not allowed";
  - Apple charges nothing, but MSPs do.
  - These points come from secondary vendor summaries; Apple's own messaging documentation is version 2.9.4.
  - Sources: [Bird explainer](https://bird.com/explained/apple-messages/what-does-apple-messages-for-business-cost-and-who-is-eligible); [Kanal 2026 guide](https://getkanal.com/blog/apple-messages-for-business); [Apple Business Register messaging documentation](https://register.apple.com/resources/messages/messaging-documentation)

### Inferences
- iMessage is feasible only for owners with a spare Mac. MIZAN should talk to BlueBubbles' REST API over a private network (Tailscale or WireGuard) with its server password, never exposed publicly. It should not ask users to disable SIP by default.

### Gaps
- I did not confirm whether Apple's ToS address automation of personal iMessage accounts.
- BlueBubbles' current release and licence were not retrieved.

## 11. Telegram Bot API 2025–2026 features a personal agent should use

### Takeaway
Telegram moved fast toward AI agents in 2026. The most useful additions for MIZAN, which already uses Telegram:
- streaming drafts, available to all bots since Bot API 9.5;
- rich messages with streaming (10.1) and stop-generation updates (10.3);
- topics in private chats (9.3/9.4), for one thread per MIZAN chat or task;
- ephemeral messages in groups (10.2), for private approvals;
- Business/"Chat Automation", which lets a user's bot answer on their behalf without Premium since 10.0;
- checklists (9.1/9.2), for plans and todos;
- guest-mode AI bots (10.0);
- Mini Apps origin lock-down (10.2).

The latest version is Bot API 10.3 (24 Aug 2026).

### Cited Findings
- **Bot API changelog:**
  - 8.2 (1 Jan 2025): verification on behalf of organisations.
  - 9.0 (11 Apr 2025): extensive business-account management and Mini App DeviceStorage and SecureStorage.
  - 9.1 (3 Jul 2025): checklists sent and edited for business accounts.
  - 9.2 (15 Aug 2025): checklist task replies, direct messages in channels, suggested posts.
  - 9.3 (31 Dec 2025): `sendMessageDraft` for streaming partial messages; topics in private chats.
  - 9.4 (9 Feb 2026): bots create topics in private chats; colored buttons.
  - 9.5 (1 Mar 2026): `sendMessageDraft` available to all bots; date-time entities.
  - 9.6 (3 Apr 2026): managed bots (bots creating bots); poll upgrades.
  - 10.0 (8 May 2026): guest mode (`answerGuestQuery`); business bots manage user accounts without Premium; bot-to-bot messaging.
  - 10.1 (11 Jun 2026): `sendRichMessage` and `sendRichMessageDraft`.
  - 10.2 (14 Jul 2026): ephemeral messages visible to one user; Communities; Mini App methods blocked from foreign origins from 20 Jul 2026.
  - 10.3 (24 Aug 2026): draft `can_stop` and `keep_on_stop`; an update when the user stops generation; disabled inline buttons.
  - Source: [Telegram Bot API changelog](https://core.telegram.org/bots/api-changelog)
- **Telegram blog, 7 May 2026:**
  - "Guest AI Bots": mention a bot in any chat; it sees only the tagged message and replies to it.
  - "Bot-to-Bot Chats".
  - "Chat Automation": "Any user can connect a bot to their profile so it responds to messages on their behalf", choosing which chats it can access (Settings > Chat Automation).
  - Streaming text.
  - Source: [Telegram blog: Guest AI Bots, Bot-to-Bot Chats, Chat Automation…](https://telegram.org/blog/ai-bot-revolution-11-new-features)
- **Telegram's own AI:**
  - AI Summaries (3 Jan 2026) run open-source models on Cocoon, a decentralized network on TON.
  - An AI Editor followed (31 Mar 2026), then custom AI styles (7 May 2026) and "AI Guardians for Groups" (11 Jun 2026).
  - Sources: [Telegram blog index](https://telegram.org/blog); [Telegram blog, 3 Jan 2026](https://telegram.org/blog/new-design-ai-summaries); [CyberInsider on Cocoon summaries](https://cyberinsider.com/?p=298310)
- Historical: an xAI–Telegram Grok deal was announced in May 2025 ($300M plus a revenue share), but its status is unclear. Musk said it was not signed; Durov said only formalities remained. — [Digital Trends ES](https://es.digitaltrends.com/?p=1070964); [Habr](https://habr.com/ru/amp/publications/913774)
- **Python libraries:** `python-telegram-bot` 22.8 (LGPL-3.0-only, 12 Jun 2026) and `aiogram` 3.31.0 (MIT, 26 Aug 2026). In TypeScript, `grammy` 1.46.0 (MIT). — [PyPI python-telegram-bot](https://pypi.org/pypi/python-telegram-bot/json); [PyPI aiogram](https://pypi.org/pypi/aiogram/json); [npm grammy](https://registry.npmjs.org/grammy)

### Inferences
- **Concrete upgrades to MIZAN's Bab Telegram adapter (raw httpx, so no library lag):**
  - Stream Lisan output with `sendMessageDraft` or `sendRichMessageDraft`, and honour the stop-generation update as a cancel.
  - Map each MIZAN chat to a private-chat topic.
  - Render Tadbir plans as checklists.
  - Send Allow/Deny held-action prompts as ephemeral messages when the bot is in a group.
  - Offer "Chat Automation" (business connection) only with an explicit per-chat scope and approval for any outgoing reply in the owner's name.
- Raw httpx means MIZAN must track the changelog itself. Pinning `aiogram`, which tracks Bot API releases, is an option.

### Gaps
- I did not verify the exact business-connection rights model for 10.0 "without Premium", or whether Chat Automation bots see whole chats or only scoped ones.
- Changelog text after the first 100k characters was not read; it is older material.

## 12. Security patterns for channel-connected agents, with incidents

### Takeaway
The documented attacks fall into four groups:
- incoming-message injection that drives exfiltration through the same messaging tool (Invariant, WhatsApp MCP, April 2025, historical);
- content-borne injection that makes an agent add an attacker-controlled chat channel and allowlist entry (Zenity on OpenClaw, Feb 2026);
- one-click token theft leading to full gateway control (OpenClaw CVE-2026-25253, Jan 2026);
- shared-space injection in group channels (Slack AI, Aug 2024, historical).

The common defence is architectural:
- deny-by-default identity on immutable IDs;
- out-of-band pairing;
- channel and allowlist changes that the model can never make;
- all inbound text, including forwards and replies, fenced as data;
- held approval for any model-directed outbound send.

### Cited Findings
- **Invariant Labs, 7 Apr 2025 (updated 9 Apr; historical):**
  - A "sleeper" MCP tool rug-pull exfiltrated a user's entire WhatsApp history.
  - In Experiment 2, no malicious server was needed: the attacker "merely has to send the target a prompt injection as a message", which surfaces via `list_chats`. It leaked contacts by `send_message` to an attacker number.
  - The confirmation dialog showed "Hi" while hiding the payload off-screen.
  - "Code isolation or sandboxing of the MCP server is not a relevant mitigation".
  - Source: [Invariant Labs: WhatsApp MCP exploited](https://invariantlabs.ai/blog/whatsapp-mcp-exploited)
- **Zenity Labs, 4 Feb 2026, "OpenClaw or OpenDoor?":**
  - An injected document made OpenClaw create "a new chat integration", a Telegram bot with the attacker's allowlist entry and bot token. That gave the attacker a command channel.
  - It then exfiltrated and deleted files, rewrote SOUL.md through a scheduled task every two minutes, and ran a Sliver C2 beacon.
  - Quotes: "No software vulnerability is required. All attacks abuse OpenClaw's intended capabilities" and "untrusted content can induce a persistent configuration change".
  - Source: [Zenity Labs](https://labs.zenity.io/post/openclaw-or-opendoor-indirect-prompt-injection-makes-openclaw-vulnerable-to-backdoors-and-much-more)
- **CVE-2026-25253 (CVSS 8.8):**
  - OpenClaw's Control UI trusted a `gatewayUrl` query parameter and sent the stored gateway token to it on page load.
  - Cross-site WebSocket hijacking then let attackers change sandbox and tool policy. This worked even with a loopback-only gateway.
  - Fixed in 2026.1.29 (30 Jan 2026).
  - Source: [The Hacker News, Feb 2026](https://thehackernews.com/2026/02/openclaw-bug-enables-one-click-remote.html)
- **Slack AI (PromptArmor, reported 14 Aug 2024; historical):**
  - An attacker's message in a public channel caused Slack AI to leak data, including an API key, from a private channel the attacker could not read.
  - Slack initially called this "intended" and later patched it.
  - Sources: [PromptArmor](https://promptarmor.substack.com/p/data-exfiltration-from-slack-ai-via); [The Register, 21 Aug 2024](https://www.theregister.com/2024/08/21/slack_ai_prompt_injection/)
- **Manus (Oct 2026):** researchers bypassed prompt-injection protections with hidden, obfuscated email prompts, reaching code execution. It was reportedly patched. Details are from a secondary report only. — [TechRadar, Oct 2026](https://www.techradar.com/pro/security/this-popular-ai-agent-could-be-hacked-by-a-single-email-with-potentially-disastrous-consequences)
- **Unit 42 (March 2026):** indirect prompt injection on the web "is being actively weaponized". — [Unit 42](https://unit42.paloaltonetworks.com/ai-agent-prompt-injection/)
- **Pairing and allowlist practice in rival gateways:**
  - OpenClaw: pairing codes expire after 1 hour, at most 3 pending, E.164 allowlists. Groups require a mention, and "Replying to an allowlisted user does not grant sender authorization". — [OpenClaw WhatsApp docs](https://docs.openclaw.ai/channels/whatsapp)
  - Hermes: deny by default; one-time pairing codes that expire after 1 hour, are rate-limited and cryptographically random; separate admin and user command scopes; `/approve` and `/deny`. — [Hermes Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
- **Attachment handling in OpenClaw:** a 50 MB default cap (`mediaMaxMb`); outbound media accepted from HTTP(S), `file://` or local paths; ffmpeg transcoding. — [OpenClaw WhatsApp docs](https://docs.openclaw.ai/channels/whatsapp)
- **Telegram Mini Apps:** methods called from origins other than the app's domain are blocked automatically from 20 Jul 2026. — [Bot API changelog 10.2](https://core.telegram.org/bots/api-changelog)
- **End-to-end encryption trade-offs:**
  - Matrix end-to-bridge encryption hides content from the homeserver, but the bridge decrypts in order to speak the remote protocol. — [mautrix E2BE docs](https://docs.mau.fi/bridges/general/end-to-bridge-encryption.html)
  - Signal and WhatsApp via linked-device bridges keep keys on the owner's server. The Cloud API places a Meta-hosted endpoint in the path; see Gaps.

### Inferences
Recommended pattern for MIZAN's Bab:
1. **Identity:** bind each channel to immutable platform IDs (Telegram user_id, WhatsApp wa_id or E.164, Signal ACI, Matrix MXID, Slack user ID, Discord snowflake), never display names.
   - Keep MIZAN's existing one-time 128-bit, 10-minute, single-use codes.
   - Require that the code is shown in the logged-in web UI and typed into the channel, not the reverse.
2. **Channel config is a sealed resource:** adding a channel, adding an allowlist entry, or changing a bot token or webhook URL must be impossible from any agent tool. Only an authenticated web-UI action can do it, recorded as a Sakk receipt. This directly closes the Zenity attack.
3. **Inbound text is data:**
   - Fence all inbound channel text in `<<untrusted>>` blocks, as Amanah does, including forwards, quoted replies, captions, filenames and transcripts.
   - Never let a forwarded message, or a message whose sender is not the bound owner ID, become an instruction.
   - Treat the owner's own messages as instructions, but taint the run when they contain forwarded or quoted content.
4. **Outbound sends:** any model-directed message to anyone other than the owner, or one containing data from tools, is held for Allow/Deny. The approval prompt should show the full payload (the Invariant "Hi" dialog trick).
5. **Groups:** default off. If enabled, require a mention, use a per-group sender allowlist, run a reduced tool set with no file or memory access, and never put other members' messages into the owner's memory (Daftar) without consent. Slack AI showed how shared spaces leak.
6. **Attachments:**
   - Enforce size and type caps and verify MIME by magic bytes.
   - Transcode and parse (ffmpeg, PDF) in the existing sandbox container with no network.
   - Strip EXIF and location from outbound media.
   - Never accept `file://` or local paths as outbound media sources chosen by the model.
7. **Web UI:** validate any URL parameters that select a backend endpoint and use CSRF-safe WebSocket origins (CVE-2026-25253 class).
8. **Reliability as a ban defence:** exponential backoff, a reconnect circuit breaker and a single-instance lock per channel session (OpenClaw #16270).

### Gaps
- No primary-source documented case was found of a production personal agent hijacked by an inbound WhatsApp or Telegram message from a stranger. Invariant's Experiment 2 is a research PoC.
- The encryption properties of the WhatsApp Cloud API (where decryption happens, Meta as processor) and the non-E2EE status of Telegram bot chats were not verified from primary docs in this session.

## 13. Unified open-source channel layers and the least-maintenance design

### Takeaway
There are four kinds of unified layer:
1. Agent gateways: OpenClaw (TypeScript, MIT) and Hermes (Python), each with 20 or more channels.
2. SDKs: Vercel Chat SDK (TypeScript, MIT, adapters for Slack, Teams, Google Chat, Discord, Telegram, GitHub, Linear and WhatsApp).
3. Notification fan-out: Apprise (Python, BSD-2-Clause, outbound only).
4. Protocol bridging: the mautrix bridges via Matrix (Go, AGPL).

Matterbridge appears unmaintained (last module release January 2023). For a Python, self-hosted, owner-only agent, the least maintenance comes from a small internal adapter interface:
- direct official APIs for Telegram, Slack, Discord, email and the WhatsApp Cloud API, where it is allowed;
- Matrix plus mautrix bridges as the single adapter for unofficial networks (WhatsApp-as-user, Signal, Google Messages, Meta);
- Apprise only for one-way alerts.

### Cited Findings
- OpenClaw: npm `openclaw` 2026.10.8 (MIT, 27 Oct 2026); its gateway owns channel sessions such as the WhatsApp linked device. — [npm openclaw](https://registry.npmjs.org/openclaw); [OpenClaw WhatsApp docs](https://docs.openclaw.ai/channels/whatsapp)
- Hermes Agent: "a single background process that runs all configured platforms", with the platform list in section 6 and commands `hermes gateway setup/start/status`. — [Hermes Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/); [DigitalOcean marketplace](https://docs.digitalocean.com/products/marketplace/catalog/hermes-agent/)
- Vercel Chat SDK: npm `chat` and `@chat-adapter/{slack,telegram,whatsapp,…}` 4.43.0 (MIT, 19 Oct 2026); repository github.com/vercel/chat. Platforms: Slack, Teams, Google Chat, Discord, Telegram, GitHub, Linear and WhatsApp. — [npm chat](https://registry.npmjs.org/chat); [npm @chat-adapter/whatsapp](https://registry.npmjs.org/@chat-adapter/whatsapp); [Vercel guide](https://vercel.com/kb/guide/the-complete-guide-to-chat-sdk)
- Apprise 2.1.0 (BSD-2-Clause, 24 Oct 2026). — [PyPI apprise](https://pypi.org/pypi/apprise/json)
- Matterbridge: latest Go module version v1.26.0, dated 29 Jan 2023. — [Go proxy matterbridge](https://proxy.golang.org/github.com/42wim/matterbridge/@latest)
- mautrix bridges: monthly versioned releases, all at v0.2610.0 on 16 Oct 2026. — [Go proxy mautrix-whatsapp](https://proxy.golang.org/go.mau.fi/mautrix-whatsapp/@latest)
- WhatsApp Cloud API Python wrapper: `pywa` 4.5.0 (MIT, 24 Sep 2026). `heyoo` is stale (0.1.2, March 2024). — [PyPI pywa](https://pypi.org/pypi/pywa/json); [PyPI heyoo](https://pypi.org/pypi/heyoo/json)
- Signal REST sidecar: `signalbot` 2.2.1 (MIT, 25 Oct 2026). — [PyPI signalbot](https://pypi.org/pypi/signalbot/json)

### Inferences
- **Do not adopt OpenClaw's or Hermes's gateway wholesale.**
  - OpenClaw's is TypeScript and Baileys-based, with a security track record (CVE-2026-25253, Zenity).
  - Hermes's is Python but tied to its own agent loop.
  - Copy their good ideas instead: per-channel `dmPolicy`, pairing expiry and limits, mention-gated groups, and admin and user command scopes.
- **Proposed MIZAN design ("Bab adapters"):**
  - one async `ChannelAdapter` protocol (`receive() -> InboundMessage`, `send()`, `send_approval()`, `stream_draft()`, `capabilities`);
  - one identity table keyed by (channel, immutable_id) and bound to a MIZAN user through the existing link codes;
  - every inbound message routed through `_bab_turn` under deferred approvals.
- **Adapters, in order of value and risk:**
  1. Telegram (existing; add drafts, topics and checklists).
  2. Email (IMAP IDLE plus SMTP, DMARC-checked owner only).
  3. WhatsApp Cloud API via httpx or pywa. Enable only when the owner's number is in a Meta-required market (EEA, Italy, Türkiye; Brazil paid) or in "ancillary notifications" mode elsewhere. Template-aware for outside the 24-hour window, with costs fed to Iqtisad.
  4. Matrix (mautrix-python) as the gateway to bridged WhatsApp-as-user, Signal and SMS/RCS via Google Messages, for advanced self-hosters.
  5. Slack (Socket Mode, internal app) and Discord (DM-only).
  6. Signal direct via a signal-cli JSON-RPC sidecar, for users without Matrix.
  7. iMessage via BlueBubbles REST over a private network.
  8. Apprise for outbound-only alerts to anything else.
- **Licence hygiene:** keep GPL and AGPL components (signal-cli, libsignal, mautrix bridges, aioimaplib, jmapc) out of process, behind JSON-RPC, HTTP or Matrix, so Apache-2.0 MIZAN stays clean.

### Gaps
- I did not evaluate Beeper's self-hosted bridge manager (bbctl) or the Matrix "megabridge" bridgev2 operational docs.
- The Vercel Chat SDK is TypeScript-only, so its fit for a Python backend would need a Node sidecar. Its maintenance record was not assessed beyond the release date.
