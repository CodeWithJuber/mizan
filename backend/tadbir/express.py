"""MIZAN's own wording, and Furqan checks on anything Lisan writes.

Templates cover every Tadbir result in English, Hinglish, Urdu, Hindi and
Arabic, so a reply never depends on a language model. When Lisan phrases a
reply, ``furqan`` rejects text that adds numbers, citations, links or claims
of actions that MIZAN's facts do not contain; the template is used instead.
"""

from __future__ import annotations

import re

PHRASES: dict[str, dict[str, str]] = {
    "computed": {
        "en": "Calculated exactly by MIZAN.",
        "hi-latn": "MIZAN ne exact hisab kiya.",
        "ur": "میزان نے درست حساب کیا۔",
        "hi": "मीज़ान ने सटीक हिसाब किया।",
        "ar": "حسبه ميزان بدقة.",
    },
    "ran_ok": {
        "en": "Ran in MIZAN's isolated sandbox (exit code 0, {ms} ms).",
        "hi-latn": "MIZAN ke isolated sandbox mein chalaya gaya (exit code 0, {ms} ms).",
        "ur": "میزان کے الگ سینڈ باکس میں چلایا گیا (exit code 0، {ms} ms)۔",
        "hi": "मीज़ान के अलग सैंडबॉक्स में चलाया गया (exit code 0, {ms} ms)।",
        "ar": "نُفِّذ في بيئة ميزان المعزولة (رمز الخروج 0، {ms} ms).",
    },
    "ran_failed": {
        "en": "The program failed in the sandbox (exit code {code}).",
        "hi-latn": "Program sandbox mein fail hua (exit code {code}).",
        "ur": "پروگرام سینڈ باکس میں ناکام ہوا (exit code {code})۔",
        "hi": "प्रोग्राम सैंडबॉक्स में विफल हुआ (exit code {code})।",
        "ar": "فشل البرنامج في البيئة المعزولة (رمز الخروج {code}).",
    },
    "not_run": {
        "en": "The code could not be run: {reason}",
        "hi-latn": "Code chalaya nahi ja saka: {reason}",
        "ur": "کوڈ نہیں چلایا جا سکا: {reason}",
        "hi": "कोड नहीं चलाया जा सका: {reason}",
        "ar": "تعذّر تشغيل الشيفرة: {reason}",
    },
    "repaired": {
        "en": "The first version failed; Lisan corrected it and MIZAN ran it again ({tries} tries).",
        "hi-latn": "Pehla version fail hua; Lisan ne sudhaara aur MIZAN ne dobara chalaya ({tries} koshish).",
        "ur": "پہلا ورژن ناکام ہوا؛ لسان نے درست کیا اور میزان نے دوبارہ چلایا ({tries} کوششیں)۔",
        "hi": "पहला संस्करण विफल हुआ; लिसान ने सुधारा और मीज़ान ने फिर चलाया ({tries} प्रयास)।",
        "ar": "فشلت النسخة الأولى؛ صحّحها لسان وأعاد ميزان تشغيلها ({tries} محاولات).",
    },
    "cross_checked": {
        "en": "Verified: the sandbox output matches MIZAN's own exact calculation.",
        "hi-latn": "Tasdeeq: sandbox ka output MIZAN ke apne exact hisab se milta hai.",
        "ur": "تصدیق: سینڈ باکس کا نتیجہ میزان کے اپنے درست حساب سے ملتا ہے۔",
        "hi": "पुष्टि: सैंडबॉक्स का परिणाम मीज़ान के अपने सटीक हिसाब से मेल खाता है।",
        "ar": "تحقّق: ناتج البيئة المعزولة يطابق حساب ميزان الدقيق.",
    },
    "code": {"en": "Code", "hi-latn": "Code", "ur": "کوڈ", "hi": "कोड", "ar": "الشيفرة"},
    "output": {"en": "Output", "hi-latn": "Output", "ur": "نتیجہ", "hi": "परिणाम", "ar": "الناتج"},
    "quran_source": {
        "en": "Arabic text: {source}. Translation: {translation}.",
        "hi-latn": "Arabi matan: {source}. Tarjuma: {translation}.",
        "ur": "عربی متن: {source}۔ ترجمہ: {translation}۔",
        "hi": "अरबी पाठ: {source}। अनुवाद: {translation}।",
        "ar": "النص العربي: {source}.",
    },
    "quran_no_tafsir": {
        "en": "MIZAN quotes the text and an established translation only; for explanation (tafsir) "
        "refer to a recognised tafsir such as Ibn Kathir.",
        "hi-latn": "MIZAN sirf matan aur mustanad tarjuma pesh karta hai; tafseer ke liye Ibn Kathir "
        "jaisi mustanad tafseer dekhein.",
        "ur": "میزان صرف متن اور مستند ترجمہ پیش کرتا ہے؛ تفسیر کے لیے ابن کثیر جیسی مستند تفسیر دیکھیں۔",
        "hi": "मीज़ान केवल पाठ और प्रामाणिक अनुवाद देता है; तफ़सीर के लिए इब्न कसीर जैसी प्रामाणिक तफ़सीर देखें।",
        "ar": "يورد ميزان النص فقط؛ وللتفسير يُرجع إلى تفسير معتمد كتفسير ابن كثير.",
    },
    "quran_unavailable": {
        "en": "MIZAN could not fetch the Quran text ({reason}). It does not write ayahs from memory.",
        "hi-latn": "MIZAN Quran ka matan nahi la saka ({reason}). Woh ayaat yaaddasht se nahi likhta.",
        "ur": "میزان قرآن کا متن حاصل نہ کر سکا ({reason})۔ وہ آیات یادداشت سے نہیں لکھتا۔",
        "hi": "मीज़ान क़ुरआन का पाठ नहीं ला सका ({reason})। वह आयतें याद से नहीं लिखता।",
        "ar": "تعذّر على ميزان جلب نص القرآن ({reason}). لا يكتب الآيات من الذاكرة.",
    },
    "quran_partial": {
        "en": 'Showing ayahs {first}–{last} of {requested}. Ask for the next part, e.g. "{label} {next_first}-{next_last}".',
        "hi-latn": 'Ayaat {first}–{last} dikhayi gayi ({requested} mein se). Agla hissa maangiye, jaise "{label} {next_first}-{next_last}".',
        "ur": 'آیات {first}–{last} دکھائی گئیں ({requested} میں سے)۔ اگلا حصہ مانگیں، جیسے "{label} {next_first}-{next_last}"۔',
        "hi": 'आयतें {first}–{last} दिखाई गईं ({requested} में से)। अगला भाग माँगें, जैसे "{label} {next_first}-{next_last}"।',
        "ar": 'عُرضت الآيات {first}–{last} من {requested}. اطلب الجزء التالي مثل "{label} {next_first}-{next_last}".',
    },
    "hadith_source": {
        "en": "Arabic text and translation: {source}.",
        "hi-latn": "Arabi matan aur tarjuma: {source}.",
        "ur": "عربی متن اور ترجمہ: {source}۔",
        "hi": "अरबी पाठ और अनुवाद: {source}।",
        "ar": "النص العربي: {source}.",
    },
    "hadith_sahih": {
        "en": "{collection}: the scholars of hadith accept its connected (musnad) narrations as authentic (sahih).",
        "hi-latn": "{collection}: is ki muttasil (musnad) riwayaat ko muhaddiseen ne sahih qubool kiya hai.",
        "ur": "{collection}: اس کی متصل (مسند) روایات کو محدثین نے صحیح تسلیم کیا ہے۔",
        "hi": "{collection}: इसकी मुत्तसिल (मुसनद) रिवायतों को मुहद्दिसीन ने सहीह माना है।",
        "ar": "{collection}: تلقّى أهل الحديث أحاديثه المسندة المتصلة بالقبول وصحّحوها.",
    },
    "hadith_grades": {
        "en": "Grades in this source:",
        "hi-latn": "Is source mein darje (grades):",
        "ur": "اس ماخذ میں درجات:",
        "hi": "इस स्रोत में दर्जे:",
        "ar": "الأحكام في هذا المصدر:",
    },
    "hadith_weak": {
        "en": "At least one scholar graded this narration weak or lower. Do not attribute it to the Prophet ﷺ without checking its grading.",
        "hi-latn": "Kam se kam ek aalim ne is riwayat ko zaeef ya us se kamzor kaha hai. Tehqeeq ke baghair ise Nabi ﷺ ki taraf mansoob na karein.",
        "ur": "کم از کم ایک عالم نے اس روایت کو ضعیف یا اس سے کم درجے کا قرار دیا ہے۔ تحقیق کے بغیر اسے نبی ﷺ کی طرف منسوب نہ کریں۔",
        "hi": "कम से कम एक आलिम ने इस रिवायत को ज़ईफ़ या उससे कमज़ोर कहा है। जाँच के बिना इसे नबी ﷺ से न जोड़ें।",
        "ar": "ضعّف هذه الرواية عالمٌ واحد على الأقل أو حكم عليها بأشدّ من ذلك؛ فلا تُنسب إلى النبي ﷺ قبل التحقق من درجتها.",
    },
    "hadith_ungraded": {
        "en": "This source gives no grade for this narration. Check its grading before relying on it.",
        "hi-latn": "Is source mein is riwayat ka darja nahi diya gaya. Bharosa karne se pehle is ka darja check karein.",
        "ur": "اس ماخذ میں اس روایت کا درجہ نہیں دیا گیا۔ اس پر اعتماد سے پہلے اس کا درجہ معلوم کریں۔",
        "hi": "इस स्रोत में इस रिवायत का दर्जा नहीं दिया गया। भरोसा करने से पहले इसका दर्जा जाँचें।",
        "ar": "لا يذكر هذا المصدر حكمًا لهذه الرواية؛ فتحقّق من درجتها قبل الاعتماد عليها.",
    },
    "hadith_narrations": {
        "en": 'Number {number} has {count} narrations ({first}–{last}). This is {shown}; ask for another, e.g. "{example}".',
        "hi-latn": 'Number {number} ki {count} riwayaat hain ({first}–{last}). Yeh {shown} hai; doosri maangiye, jaise "{example}".',
        "ur": 'نمبر {number} کی {count} روایات ہیں ({first}–{last})۔ یہ {shown} ہے؛ دوسری مانگیں، جیسے "{example}"۔',
        "hi": 'नंबर {number} की {count} रिवायतें हैं ({first}–{last})। यह {shown} है; दूसरी माँगें, जैसे "{example}"।',
        "ar": 'للرقم {number} عدد {count} من الروايات ({first}–{last}). هذه {shown}؛ اطلب غيرها مثل "{example}".',
    },
    "hadith_clipped": {
        "en": "The text is long and was shortened here; read it in full in the source.",
        "hi-latn": "Matan lamba hai, yahan chhota kiya gaya; poora source mein padhein.",
        "ur": "متن طویل ہے، یہاں مختصر کیا گیا؛ مکمل متن ماخذ میں پڑھیں۔",
        "hi": "पाठ लंबा है, यहाँ छोटा किया गया; पूरा स्रोत में पढ़ें।",
        "ar": "النص طويل فاختُصر هنا؛ اقرأه كاملًا في المصدر.",
    },
    "hadith_unavailable": {
        "en": "MIZAN could not fetch the hadith ({reason}). It does not write hadith from memory.",
        "hi-latn": "MIZAN hadith nahi la saka ({reason}). Woh hadith yaaddasht se nahi likhta.",
        "ur": "میزان حدیث حاصل نہ کر سکا ({reason})۔ وہ حدیث یادداشت سے نہیں لکھتا۔",
        "hi": "मीज़ान हदीस नहीं ला सका ({reason})। वह हदीस याद से नहीं लिखता।",
        "ar": "تعذّر على ميزان جلب الحديث ({reason}). لا يكتب الأحاديث من الذاكرة.",
    },
    "hadith_no_sharh": {
        "en": "MIZAN quotes the text and the scholars' grades only; for explanation (sharh) refer to "
        "a recognised commentary such as {commentary}.",
        "hi-latn": "MIZAN sirf matan aur ulama ke darje pesh karta hai; sharah ke liye {commentary} "
        "jaisi mustanad sharah dekhein.",
        "ur": "میزان صرف متن اور علماء کے درجات پیش کرتا ہے؛ شرح کے لیے {commentary} جیسی مستند شرح دیکھیں۔",
        "hi": "मीज़ान केवल पाठ और उलमा के दर्जे देता है; शरह के लिए {commentary} जैसी प्रामाणिक शरह देखें।",
        "ar": "يورد ميزان النص وأحكام العلماء فقط؛ وللشرح يُرجع إلى شرح معتمد مثل {commentary}.",
    },
    "hadith_no_sharh_any": {
        "en": "MIZAN quotes the text and the scholars' grades only; for explanation (sharh) refer to "
        "a recognised commentary or a scholar.",
        "hi-latn": "MIZAN sirf matan aur ulama ke darje pesh karta hai; sharah ke liye mustanad sharah "
        "ya kisi aalim se rujoo karein.",
        "ur": "میزان صرف متن اور علماء کے درجات پیش کرتا ہے؛ شرح کے لیے مستند شرح یا کسی عالم سے رجوع کریں۔",
        "hi": "मीज़ान केवल पाठ और उलमा के दर्जे देता है; शरह के लिए प्रामाणिक शरह या किसी आलिम से रुजू करें।",
        "ar": "يورد ميزान النص وأحكام العلماء فقط؛ وللشرح يُرجع إلى شرح معتمد أو إلى أهل العلم.",
    },
    "sources": {"en": "Sources", "hi-latn": "Sources", "ur": "ماخذ", "hi": "स्रोत", "ar": "المصادر"},
    "no_results": {
        "en": "The web search returned no results for this.",
        "hi-latn": "Is ke liye web search mein koi nateeja nahi mila.",
        "ur": "اس کے لیے ویب سرچ میں کوئی نتیجہ نہیں ملا۔",
        "hi": "इसके लिए वेब खोज में कोई परिणाम नहीं मिला।",
        "ar": "لم يُرجع البحث نتائج لهذا.",
    },
    "found": {
        "en": "MIZAN found these results:",
        "hi-latn": "MIZAN ko yeh nataij mile:",
        "ur": "میزان کو یہ نتائج ملے:",
        "hi": "मीज़ान को ये परिणाम मिले:",
        "ar": "وجد ميزان هذه النتائج:",
    },
    "page_failed": {
        "en": "MIZAN could not read that page: {reason}",
        "hi-latn": "MIZAN woh page nahi padh saka: {reason}",
        "ur": "میزان وہ صفحہ نہیں پڑھ سکا: {reason}",
        "hi": "मीज़ान वह पेज नहीं पढ़ सका: {reason}",
        "ar": "تعذّر على ميزان قراءة الصفحة: {reason}",
    },
    "page_excerpt": {
        "en": "Beginning of the page:",
        "hi-latn": "Page ki shuruaat:",
        "ur": "صفحے کا آغاز:",
        "hi": "पेज की शुरुआत:",
        "ar": "بداية الصفحة:",
    },
    "memories": {
        "en": "From your saved memory:",
        "hi-latn": "Aapki saved memory se:",
        "ur": "آپ کی محفوظ یادداشت سے:",
        "hi": "आपकी सहेजी याददाश्त से:",
        "ar": "من ذاكرتك المحفوظة:",
    },
    "capabilities": {
        "en": "Yes. MIZAN works through its own tools, and they are real:",
        "hi-latn": "Haan. MIZAN apne asli tools se kaam karta hai:",
        "ur": "جی ہاں۔ میزان اپنے حقیقی ٹولز سے کام کرتا ہے:",
        "hi": "हाँ। मीज़ान अपने असली टूल्स से काम करता है:",
        "ar": "نعم. يعمل ميزان بأدواته الحقيقية:",
    },
    "capabilities_tail": {
        "en": "Ask in any language; MIZAN plans and checks the work, and the language model only helps with wording and writing code.",
        "hi-latn": "Kisi bhi zubaan mein poochiye; kaam ki planning aur jaanch MIZAN karta hai, language model sirf alfaaz aur code likhne mein madad karta hai.",
        "ur": "کسی بھی زبان میں پوچھیں؛ کام کی منصوبہ بندی اور جانچ میزان کرتا ہے، زبان کا ماڈل صرف الفاظ اور کوڈ لکھنے میں مدد کرتا ہے۔",
        "hi": "किसी भी भाषा में पूछिए; काम की योजना और जाँच मीज़ान करता है, भाषा मॉडल केवल शब्दों और कोड लिखने में मदद करता है।",
        "ar": "اسأل بأي لغة؛ يخطّط ميزان للعمل ويتحقق منه، ويساعد النموذج اللغوي في الصياغة وكتابة الشيفرة فقط.",
    },
}

CAPABILITY_LINES = {
    "code": {
        "en": "run Python, JavaScript and shell code in an isolated sandbox",
        "hi-latn": "isolated sandbox mein Python, JavaScript aur shell code chalana",
        "ur": "الگ سینڈ باکس میں Python، JavaScript اور shell کوڈ چلانا",
        "hi": "अलग सैंडबॉक्स में Python, JavaScript और shell कोड चलाना",
        "ar": "تشغيل شيفرات Python وJavaScript وshell في بيئة معزولة",
    },
    "calc": {
        "en": "exact calculation (big numbers, fractions)",
        "hi-latn": "exact hisab (bade numbers, fractions)",
        "ur": "درست حساب (بڑے اعداد، کسور)",
        "hi": "सटीक हिसाब (बड़ी संख्याएँ, भिन्न)",
        "ar": "حساب دقيق (أعداد كبيرة وكسور)",
    },
    "quran": {
        "en": "quote Quran ayahs exactly from an authentic source, with translation",
        "hi-latn": "Quran ki ayaat mustanad source se hoo-ba-hoo, tarjume ke saath",
        "ur": "قرآن کی آیات مستند ماخذ سے بعینہٖ، ترجمے کے ساتھ",
        "hi": "क़ुरआन की आयतें प्रामाणिक स्रोत से ज्यों की त्यों, अनुवाद सहित",
        "ar": "إيراد آيات القرآن بنصها من مصدر موثوق",
    },
    "hadith": {
        "en": "quote hadith from Bukhari, Muslim, the Sunan, the Muwatta and the Forty collections, "
        "in Arabic with translation and the scholars' grades",
        "hi-latn": "Bukhari, Muslim, Sunan, Muwatta aur Arbaeen se ahadith, Arabi matan, tarjume aur "
        "ulama ke darjon ke saath",
        "ur": "بخاری، مسلم، سنن، موطا اور اربعین سے احادیث، عربی متن، ترجمے اور علماء کے درجات کے ساتھ",
        "hi": "बुख़ारी, मुस्लिम, सुनन, मुवत्ता और अरबईन से हदीसें, अरबी पाठ, अनुवाद और उलमा के दर्जों के साथ",
        "ar": "إيراد الأحاديث من البخاري ومسلم والسنن والموطأ والأربعينات بنصها العربي مع أحكام العلماء",
    },
    "web": {
        "en": "search the web and read pages, with sources",
        "hi-latn": "web search aur pages padhna, sources ke saath",
        "ur": "ویب سرچ اور صفحات پڑھنا، ماخذ کے ساتھ",
        "hi": "वेब खोज और पेज पढ़ना, स्रोतों सहित",
        "ar": "البحث في الويب وقراءة الصفحات مع المصادر",
    },
    "files": {
        "en": "create, edit and search project files",
        "hi-latn": "project files banana, badalna aur dhundhna",
        "ur": "پروجیکٹ فائلیں بنانا، بدلنا اور تلاش کرنا",
        "hi": "प्रोजेक्ट फ़ाइलें बनाना, बदलना और खोजना",
        "ar": "إنشاء ملفات المشروع وتحريرها والبحث فيها",
    },
    "memory": {
        "en": "remember and recall what you share",
        "hi-latn": "aapki batayi baatein yaad rakhna",
        "ur": "آپ کی بتائی باتیں یاد رکھنا",
        "hi": "आपकी बताई बातें याद रखना",
        "ar": "تذكّر ما تشاركه",
    },
    "connectors": {
        "en": "use your connected apps (MCP connectors) and Agent Skills",
        "hi-latn": "aapke connected apps (MCP connectors) aur Agent Skills",
        "ur": "آپ کی منسلک ایپس (MCP) اور Agent Skills",
        "hi": "आपके जुड़े ऐप्स (MCP) और Agent Skills",
        "ar": "تطبيقاتك المتصلة (MCP) ومهارات الوكيل",
    },
}


def phrase(key: str, language: str, **values: object) -> str:
    table = PHRASES[key]
    return table.get(language, table["en"]).format(**values)


def fence(text: str, language: str = "") -> str:
    ticks = "````" if "```" in text else "```"
    return f"{ticks}{language}\n{text.rstrip()}\n{ticks}"


# ── Furqan: is Lisan's wording supported by MIZAN's facts? ────────────────

_NUMBER = re.compile(r"\d[\d,]{2,}(?:\.\d+)?")
_CITATION = re.compile(r"\[(\d{1,2})\]")
_URL = re.compile(r"https?://\S+")
_ACTION_CLAIM = re.compile(
    r"\bi\s+(?:ran|executed|searched|checked|verified|tested)\b|\bmaine\s+(?:chalaya|check|search)",
    re.IGNORECASE,
)


def furqan(text: str, facts_text: str, *, max_citation: int = 0) -> list[str]:
    """Reasons the text is unsupported (empty when it may be delivered)."""
    problems = []
    support = facts_text.replace(",", "")
    for number in _NUMBER.findall(text):
        if number.replace(",", "") not in support:
            problems.append(f"number {number} is not in MIZAN's facts")
    for citation in _CITATION.findall(text):
        if not 1 <= int(citation) <= max_citation:
            problems.append(f"citation [{citation}] has no source")
    for url in _URL.findall(text):
        if url.rstrip(").,") not in facts_text:
            problems.append("a link that MIZAN did not find")
    if _ACTION_CLAIM.search(text):
        problems.append("Lisan claimed an action")
    if not text.strip():
        problems.append("empty text")
    return problems
