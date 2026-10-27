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
    "project_new": {
        "en": "MIZAN built **{name}** as a new coding project.",
        "hi-latn": "MIZAN ne **{name}** naye coding project ke taur par banaya.",
        "ur": "میزان نے **{name}** ایک نئے کوڈنگ پروجیکٹ کے طور پر بنایا۔",
        "hi": "मीज़ान ने **{name}** एक नए कोडिंग प्रोजेक्ट के रूप में बनाया।",
        "ar": "بنى ميزان **{name}** مشروعًا برمجيًا جديدًا.",
    },
    "project_current": {
        "en": "MIZAN built **{name}** in your selected project.",
        "hi-latn": "MIZAN ne **{name}** aapke selected project mein banaya.",
        "ur": "میزان نے **{name}** آپ کے منتخب پروجیکٹ میں بنایا۔",
        "hi": "मीज़ान ने **{name}** आपके चुने हुए प्रोजेक्ट में बनाया।",
        "ar": "بنى ميزان **{name}** في مشروعك المحدد.",
    },
    "project_files": {
        "en": "Files",
        "hi-latn": "Files",
        "ur": "فائلیں",
        "hi": "फ़ाइलें",
        "ar": "الملفات",
    },
    "project_checks": {
        "en": "MIZAN's checks",
        "hi-latn": "MIZAN ki jaanch",
        "ur": "میزان کی جانچ",
        "hi": "मीज़ान की जाँच",
        "ar": "فحوص ميزان",
    },
    "check_links": {
        "en": "index.html loads style.css and app.js",
        "hi-latn": "index.html style.css aur app.js load karta hai",
        "ur": "index.html فائلیں style.css اور app.js لوڈ کرتی ہے",
        "hi": "index.html, style.css और app.js लोड करता है",
        "ar": "يحمّل index.html الملفين style.css وapp.js",
    },
    "check_linked": {
        "en": "MIZAN added the missing link to style.css or app.js itself",
        "hi-latn": "style.css ya app.js ka chhoota hua link MIZAN ne khud joda",
        "ur": "style.css یا app.js کا رہ جانے والا لنک میزان نے خود جوڑا",
        "hi": "style.css या app.js का छूटा लिंक मीज़ान ने खुद जोड़ा",
        "ar": "أضاف ميزان بنفسه الرابط الناقص إلى style.css أو app.js",
    },
    "check_ids": {
        "en": "every element app.js looks up exists in index.html",
        "hi-latn": "app.js jo bhi element dhoondta hai woh index.html mein maujood hai",
        "ur": "app.js جو بھی عنصر ڈھونڈتا ہے وہ index.html میں موجود ہے",
        "hi": "app.js जो भी एलिमेंट ढूँढता है वह index.html में मौजूद है",
        "ar": "كل عنصر يبحث عنه app.js موجود في index.html",
    },
    "check_css": {
        "en": "style.css is well formed (balanced braces)",
        "hi-latn": "style.css sahi bana hai (braces barabar)",
        "ur": "style.css درست بنی ہے (بریکٹس برابر)",
        "hi": "style.css सही बना है (ब्रेसेज़ बराबर)",
        "ar": "ملف style.css سليم البنية (الأقواس متوازنة)",
    },
    "check_js": {
        "en": "app.js has valid syntax (node --check in the sandbox)",
        "hi-latn": "app.js ka syntax sahi hai (sandbox mein node --check)",
        "ur": "app.js کا syntax درست ہے (سینڈ باکس میں node --check)",
        "hi": "app.js का सिंटैक्स सही है (सैंडबॉक्स में node --check)",
        "ar": "صياغة app.js صحيحة (node --check في البيئة المعزولة)",
    },
    "check_tests": {
        "en": "the unittest tests pass in the sandbox",
        "hi-latn": "unittest tests sandbox mein pass hote hain",
        "ur": "unittest ٹیسٹ سینڈ باکس میں پاس ہوتے ہیں",
        "hi": "unittest टेस्ट सैंडबॉक्स में पास होते हैं",
        "ar": "تنجح اختبارات unittest في البيئة المعزولة",
    },
    "check_main": {
        "en": "main.py runs and exits cleanly in the sandbox",
        "hi-latn": "main.py sandbox mein chal kar theek se band hota hai",
        "ur": "main.py سینڈ باکس میں چل کر درست طور پر ختم ہوتی ہے",
        "hi": "main.py सैंडबॉक्स में चलकर ठीक से बंद होता है",
        "ar": "يعمل main.py وينتهي بسلام في البيئة المعزولة",
    },
    "check_not_run": {
        "en": "not checked: {reason}",
        "hi-latn": "jaanch nahi hui: {reason}",
        "ur": "جانچ نہیں ہوئی: {reason}",
        "hi": "जाँच नहीं हुई: {reason}",
        "ar": "لم يُفحص: {reason}",
    },
    "project_repaired": {
        "en": "Lisan corrected the problems MIZAN found ({count} round(s)); MIZAN checked again.",
        "hi-latn": "MIZAN ki pakdi galtiyan Lisan ne sudhaari ({count} baar); MIZAN ne dobara jaancha.",
        "ur": "میزان کی پکڑی غلطیاں لسان نے درست کیں ({count} بار)؛ میزان نے دوبارہ جانچا۔",
        "hi": "मीज़ान की पकड़ी गलतियाँ लिसान ने सुधारीं ({count} बार); मीज़ान ने फिर जाँचा।",
        "ar": "صحّح لسان ما وجده ميزان ({count} مرة)، ثم أعاد ميزان الفحص.",
    },
    "project_open_web": {
        "en": "Open it in the Coding workspace and use Preview.",
        "hi-latn": "Coding workspace mein kholiye aur Preview dekhiye.",
        "ur": "اسے Coding workspace میں کھولیں اور Preview دیکھیں۔",
        "hi": "इसे Coding workspace में खोलें और Preview देखें।",
        "ar": "افتحه في مساحة البرمجة واستخدم المعاينة.",
    },
    "project_open_python": {
        "en": "Open it in the Coding workspace to read and run it.",
        "hi-latn": "Padhne aur chalane ke liye Coding workspace mein kholiye.",
        "ur": "پڑھنے اور چلانے کے لیے اسے Coding workspace میں کھولیں۔",
        "hi": "पढ़ने और चलाने के लिए इसे Coding workspace में खोलें।",
        "ar": "افتحه في مساحة البرمجة لقراءته وتشغيله.",
    },
    "project_failed": {
        "en": "MIZAN could not finish the project: {reason}",
        "hi-latn": "MIZAN project poora nahi kar saka: {reason}",
        "ur": "میزان پروجیکٹ مکمل نہ کر سکا: {reason}",
        "hi": "मीज़ान प्रोजेक्ट पूरा नहीं कर सका: {reason}",
        "ar": "تعذّر على ميزان إكمال المشروع: {reason}",
    },
    "waqt_today": {
        "en": "Today is **{gregorian}** · **{hijri}** ({hijri_ar}).",
        "hi-latn": "Aaj **{gregorian}** hai · **{hijri}** ({hijri_ar}).",
        "ur": "آج **{gregorian}** ہے · **{hijri}** ({hijri_ar})۔",
        "hi": "आज **{gregorian}** है · **{hijri}** ({hijri_ar})।",
        "ar": "اليوم **{gregorian}** · **{hijri_ar}** ({hijri}).",
    },
    "waqt_time": {
        "en": "Time now: **{time}** ({zone}).",
        "hi-latn": "Abhi ka waqt: **{time}** ({zone}).",
        "ur": "ابھی کا وقت: **{time}** ({zone})۔",
        "hi": "अभी का समय: **{time}** ({zone})।",
        "ar": "الوقت الآن: **{time}** ({zone}).",
    },
    "waqt_event": {
        "en": "**{event}**, {hijri}: expected on **{gregorian}** ({relative}).",
        "hi-latn": "**{event}**, {hijri}: mutawaqqe taareekh **{gregorian}** ({relative}).",
        "ur": "**{event}**، {hijri}: متوقع تاریخ **{gregorian}** ({relative})۔",
        "hi": "**{event}**, {hijri}: अपेक्षित तारीख़ **{gregorian}** ({relative})।",
        "ar": "**{event}**، {hijri}: المتوقع **{gregorian}** ({relative}).",
    },
    "waqt_in_days": {
        "en": "in {days} days",
        "hi-latn": "{days} din baad",
        "ur": "{days} دن بعد",
        "hi": "{days} दिन बाद",
        "ar": "بعد {days} يومًا",
    },
    "waqt_days_ago": {
        "en": "{days} days ago",
        "hi-latn": "{days} din pehle",
        "ur": "{days} دن پہلے",
        "hi": "{days} दिन पहले",
        "ar": "قبل {days} يومًا",
    },
    "waqt_today_word": {"en": "today", "hi-latn": "aaj", "ur": "آج", "hi": "आज", "ar": "اليوم"},
    "waqt_hijri_note": {
        "en": "Hijri dates follow the Umm al-Qura calendar; where the month begins with the local "
        "sighting of the crescent, it can differ by a day.",
        "hi-latn": "Hijri taareekh Umm al-Qura calendar ke mutabiq hai; jahan mahina maqami chand "
        "dekhne se shuru hota hai wahan ek din ka farq ho sakta hai.",
        "ur": "ہجری تاریخ ام القریٰ کیلنڈر کے مطابق ہے؛ جہاں مہینہ مقامی رؤیتِ ہلال سے شروع ہوتا ہے وہاں ایک دن کا فرق ہو سکتا ہے۔",
        "hi": "हिजरी तारीख़ उम्म अल-क़ुरा कैलेंडर के अनुसार है; जहाँ महीना स्थानीय चाँद देखने से शुरू होता है वहाँ एक दिन का फ़र्क़ हो सकता है।",
        "ar": "التاريخ الهجري وفق تقويم أم القرى، وقد يختلف بيوم حيث يبدأ الشهر برؤية الهلال محليًا.",
    },
    "waqt_sighting": {
        "en": 'For Ramadan and the Eids, follow the sighting of the crescent: "Start fasting on '
        "seeing the crescent (of Ramadan), and give up fasting on seeing the crescent (of "
        'Shawwal)" (Sahih al-Bukhari 1909; also Sahih Muslim 1081).',
        "hi-latn": "Ramadan aur Eid ke liye chand dekhne par amal karein: «صُومُوا لِرُؤْيَتِهِ "
        "وَأَفْطِرُوا لِرُؤْيَتِهِ» (mafhoom: chand dekh kar roza rakho aur chand dekh kar roza "
        "khatam karo) — Sahih al-Bukhari 1909, Sahih Muslim 1081.",
        "ur": "رمضان اور عیدین کے لیے رؤیتِ ہلال پر عمل کریں: «صُومُوا لِرُؤْيَتِهِ وَأَفْطِرُوا لِرُؤْيَتِهِ» "
        "(مفہوم: چاند دیکھ کر روزہ رکھو اور چاند دیکھ کر روزہ ختم کرو) — صحیح بخاری 1909، صحیح مسلم 1081۔",
        "hi": "रमज़ान और ईद के लिए चाँद देखने पर अमल करें: «صُومُوا لِرُؤْيَتِهِ وَأَفْطِرُوا لِرُؤْيَتِهِ» "
        "(मफ़हूम: चाँद देखकर रोज़ा रखो और चाँद देखकर रोज़ा ख़त्म करो) — सहीह बुख़ारी 1909, सहीह मुस्लिम 1081।",
        "ar": "وفي رمضان والعيدين المعتبر رؤية الهلال: «صُومُوا لِرُؤْيَتِهِ وَأَفْطِرُوا لِرُؤْيَتِهِ» "
        "(صحيح البخاري 1909، صحيح مسلم 1081).",
    },
    "waqt_utc_note": {
        "en": "Your timezone was not shared with MIZAN, so this uses UTC.",
        "hi-latn": "Aapka timezone MIZAN ko nahi mila, is liye UTC istemal hua.",
        "ur": "آپ کا ٹائم زون میزان کو نہیں ملا، اس لیے UTC استعمال ہوا۔",
        "hi": "आपका टाइमज़ोन मीज़ान को नहीं मिला, इसलिए UTC इस्तेमाल हुआ।",
        "ar": "لم تصل منطقتك الزمنية إلى ميزان، لذا استُخدم التوقيت العالمي UTC.",
    },
    "waqt_range": {
        "en": "MIZAN's Hijri calendar covers 1343–1500 AH (1924–2077 CE).",
        "hi-latn": "MIZAN ka Hijri calendar 1343–1500 AH (1924–2077 CE) tak hai.",
        "ur": "میزان کا ہجری کیلنڈر 1343–1500 ہجری (1924–2077 عیسوی) تک ہے۔",
        "hi": "मीज़ान का हिजरी कैलेंडर 1343–1500 हिजरी (1924–2077 ई.) तक है।",
        "ar": "يغطي تقويم ميزان الهجري الأعوام 1343–1500 هـ (1924–2077 م).",
    },
    "done_by_agent": {
        "en": "Done by {name}, MIZAN's {role} agent.",
        "hi-latn": "Yeh kaam MIZAN ke {role} agent {name} ne kiya.",
        "ur": "یہ کام میزان کے {role} ایجنٹ {name} نے کیا۔",
        "hi": "यह काम मीज़ान के {role} एजेंट {name} ने किया।",
        "ar": "أنجز هذا {name}، وكيل {role} في ميزان.",
    },
    "tool_not_prepared": {
        "en": "MIZAN could not prepare a valid call to {tool}: {reason}",
        "hi-latn": "MIZAN {tool} ke liye sahi call tayyar nahi kar saka: {reason}",
        "ur": "میزان {tool} کے لیے درست کال تیار نہ کر سکا: {reason}",
        "hi": "मीज़ान {tool} के लिए सही कॉल तैयार नहीं कर सका: {reason}",
        "ar": "تعذّر على ميزان إعداد استدعاء صحيح للأداة {tool}: {reason}",
    },
    "tool_failed": {
        "en": "{tool} did not succeed: {reason}",
        "hi-latn": "{tool} kaamyab nahi hua: {reason}",
        "ur": "{tool} کامیاب نہیں ہوا: {reason}",
        "hi": "{tool} सफल नहीं हुआ: {reason}",
        "ar": "لم تنجح الأداة {tool}: {reason}",
    },
    "edit_done": {
        "en": "MIZAN changed {count} file(s) in your project.",
        "hi-latn": "MIZAN ne aapke project mein {count} file(s) badli.",
        "ur": "میزان نے آپ کے پروجیکٹ میں {count} فائل(یں) بدلیں۔",
        "hi": "मीज़ान ने आपके प्रोजेक्ट में {count} फ़ाइल(ें) बदलीं।",
        "ar": "غيّر ميزان {count} ملفًا في مشروعك.",
    },
    "edit_changes": {
        "en": "Changes",
        "hi-latn": "Tabdeeliyan",
        "ur": "تبدیلیاں",
        "hi": "बदलाव",
        "ar": "التغييرات",
    },
    "edit_nothing": {
        "en": "No change was needed, or none could be written for this request. Nothing was saved.",
        "hi-latn": "Is request ke liye koi tabdeeli nahi bani. Kuch save nahi hua.",
        "ur": "اس درخواست کے لیے کوئی تبدیلی نہیں بنی۔ کچھ محفوظ نہیں ہوا۔",
        "hi": "इस अनुरोध के लिए कोई बदलाव नहीं बना। कुछ सहेजा नहीं गया।",
        "ar": "لم يُكتب أي تغيير لهذا الطلب، ولم يُحفظ شيء.",
    },
    "edit_no_checks": {
        "en": "no automatic check applies to these files",
        "hi-latn": "in files par koi automatic jaanch laagu nahi hoti",
        "ur": "ان فائلوں پر کوئی خودکار جانچ لاگو نہیں ہوتی",
        "hi": "इन फ़ाइलों पर कोई स्वचालित जाँच लागू नहीं होती",
        "ar": "لا ينطبق فحص تلقائي على هذه الملفات",
    },
    "check_refs": {"en": "`{path}` loads only files that exist"},
    "check_css_file": {"en": "`{path}` is well formed (balanced braces)"},
    "check_json": {"en": "`{path}` is valid JSON"},
    "check_syntax": {"en": "`{path}` has valid syntax (sandbox)"},
    "part_not_done": {
        "en": "MIZAN could not do this part itself: {part}. Ask it on its own.",
        "hi-latn": "Yeh hissa MIZAN khud nahi kar saka: {part}. Ise alag se poochiye.",
        "ur": "یہ حصہ میزان خود نہیں کر سکا: {part}۔ اسے الگ سے پوچھیں۔",
        "hi": "यह हिस्सा मीज़ान ख़ुद नहीं कर सका: {part}। इसे अलग से पूछें।",
        "ar": "لم يستطع ميزان تنفيذ هذا الجزء بنفسه: {part}. اسأل عنه منفردًا.",
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
    "waqt": {
        "en": "today's Gregorian and Hijri date, and conversions between them",
        "hi-latn": "aaj ki angrezi aur Hijri taareekh, aur dono ke darmiyan tabdeeli",
        "ur": "آج کی عیسوی اور ہجری تاریخ، اور دونوں کے درمیان تبدیلی",
        "hi": "आज की अंग्रेज़ी और हिजरी तारीख़, और दोनों के बीच बदलाव",
        "ar": "تاريخ اليوم الميلادي والهجري والتحويل بينهما",
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
