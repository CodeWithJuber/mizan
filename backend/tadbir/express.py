"""MIZAN's own wording, and Furqan checks on anything Lisan writes.

Templates cover every Tadbir result in English, Hinglish, Urdu, Hindi and
Arabic, so a reply never depends on a language model. When Lisan phrases a
reply, ``furqan`` rejects text that adds numbers, citations, links or claims
of actions that MIZAN's facts do not contain; the template is used instead.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import trace

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
    "gui_checked": {
        "en": "This program opens a window ({toolkit}), and MIZAN's sandbox has no screen, so it was not run here. MIZAN checked that it compiles. Run it on your computer with `python main.py`.",
        "hi-latn": "Yeh program window kholta hai ({toolkit}), aur MIZAN ke sandbox mein screen nahi hai, isliye yahan chalaya nahi gaya. MIZAN ne check kiya ki yeh compile hota hai. Apne computer par `python main.py` se chalaiye.",
        "ur": "یہ پروگرام ونڈو کھولتا ہے ({toolkit})، اور میزان کے سینڈ باکس میں اسکرین نہیں، اس لیے یہاں نہیں چلایا گیا۔ میزان نے جانچا کہ یہ کمپائل ہوتا ہے۔ اپنے کمپیوٹر پر `python main.py` سے چلائیں۔",
        "hi": "यह प्रोग्राम विंडो खोलता है ({toolkit}), और मीज़ान के सैंडबॉक्स में स्क्रीन नहीं है, इसलिए यहाँ नहीं चलाया गया। मीज़ान ने जाँचा कि यह कंपाइल होता है। अपने कंप्यूटर पर `python main.py` से चलाइए।",
        "ar": "هذا البرنامج يفتح نافذة ({toolkit})، وصندوق ميزان المعزول بلا شاشة، فلم يُشغَّل هنا. تحقق ميزان من أنه يُترجَم دون أخطاء. شغّله على حاسوبك بالأمر `python main.py`.",
    },
    "repaired": {
        "en": "The first version failed; Lisan corrected it and MIZAN ran it again ({tries} tries).",
        "hi-latn": "Pehla version fail hua; Lisan ne sudhaara aur MIZAN ne dobara chalaya ({tries} koshish).",
        "ur": "پہلا ورژن ناکام ہوا؛ لسان نے درست کیا اور میزان نے دوبارہ چلایا ({tries} کوششیں)۔",
        "hi": "पहला संस्करण विफल हुआ; लिसान ने सुधारा और मीज़ान ने फिर चलाया ({tries} प्रयास)।",
        "ar": "فشلت النسخة الأولى؛ صحّحها لسان وأعاد ميزان تشغيلها ({tries} محاولات).",
    },
    "silsila_next": {
        "en": "The next number after {terms} is **{value}**.",
        "hi-latn": "{terms} ke baad agla number **{value}** hai.",
        "ur": "{terms} کے بعد اگلا عدد **{value}** ہے۔",
        "hi": "{terms} के बाद अगला संख्या **{value}** है।",
        "ar": "العدد التالي بعد {terms} هو **{value}**.",
    },
    "silsila_several": {
        "en": "More than one rule reproduces all {total} terms of {terms}, and they give different next numbers:",
        "hi-latn": "{terms} ke sabhi {total} terms ko ek se zyada rule sahi banate hain, aur unke agle number alag hain:",
        "ur": "{terms} کے تمام {total} اعداد کو ایک سے زیادہ قاعدے درست بناتے ہیں، اور ان کے اگلے اعداد مختلف ہیں:",
        "hi": "{terms} के सभी {total} पदों को एक से अधिक नियम सही बनाते हैं, और उनके अगले संख्या अलग हैं:",
        "ar": "أكثر من قاعدة تُعيد الحدود الـ{total} كلها في {terms}، وتعطي أعدادًا تالية مختلفة:",
    },
    "silsila_rule": {
        "en": "`{formula}` ({method}); MIZAN checked that it reproduces all {total} terms exactly.",
        "hi-latn": "`{formula}` ({method}); MIZAN ne jaancha ki yeh sabhi {total} terms bilkul sahi banata hai.",
        "ur": "`{formula}` ({method})؛ میزان نے جانچا کہ یہ تمام {total} اعداد بالکل درست بناتا ہے۔",
        "hi": "`{formula}` ({method}); मीज़ान ने जाँचा कि यह सभी {total} पद बिल्कुल सही बनाता है।",
        "ar": "`{formula}` ({method})؛ تحقّق ميزان أنها تُعيد الحدود الـ{total} كلها بدقة.",
    },
    "silsila_oeis": {
        "en": "OEIS {id}: {name}",
        "hi-latn": "OEIS {id}: {name}",
        "ur": "OEIS {id}: {name}",
        "hi": "OEIS {id}: {name}",
        "ar": "OEIS {id}: {name}",
    },
    "silsila_tested": {
        "en": "{rule} (a rule Lisan proposed; MIZAN ran it in its sandbox and it reproduces all {total} terms).",
        "hi-latn": "{rule} (Lisan ka diya rule; MIZAN ne sandbox me chala kar dekha, yeh sabhi {total} terms sahi banata hai).",
        "ur": "{rule} (لسان کا تجویز کردہ قاعدہ؛ میزان نے سینڈ باکس میں چلایا، یہ تمام {total} اعداد درست بناتا ہے)۔",
        "hi": "{rule} (लिसान का प्रस्तावित नियम; मीज़ान ने सैंडबॉक्स में चलाया, यह सभी {total} पद सही बनाता है)।",
        "ar": "{rule} (قاعدة اقترحها لسان؛ شغّلها ميزان في بيئته المعزولة فأعادت الحدود الـ{total} كلها).",
    },
    "silsila_none": {
        "en": "MIZAN found no rule that reproduces all {total} terms of {terms}. It tried polynomials in n, polynomials in the n-th prime and linear recurrences up to order 3, and the OEIS has no sequence with these terms{lisan}. So it gives no next number rather than a guess. If you know where the sequence comes from, tell MIZAN and it will check that rule on every term.",
        "hi-latn": "MIZAN ko {terms} ke sabhi {total} terms ko sahi banane wala koi rule nahi mila. Usne n ke polynomial, n-th prime ke polynomial aur order 3 tak ki linear recurrences aazmayin, aur OEIS me in terms wali koi sequence nahi hai{lisan}. Isliye andaza lagane ke bajaye koi agla number nahi diya. Agar aapko sequence ka source maloom hai to bataiye, MIZAN us rule ko har term par jaanchega.",
        "ur": "میزان کو {terms} کے تمام {total} اعداد درست بنانے والا کوئی قاعدہ نہیں ملا۔ اس نے n کے کثیر رقمی، n-ویں مفرد عدد کے کثیر رقمی اور تین درجے تک کی خطی تکرار آزمائی، اور OEIS میں ان اعداد والی کوئی ترتیب نہیں{lisan}۔ اس لیے اندازے کی بجائے کوئی اگلا عدد نہیں دیا۔ اگر آپ کو ترتیب کا ماخذ معلوم ہو تو بتائیں، میزان وہ قاعدہ ہر عدد پر جانچے گا۔",
        "hi": "मीज़ान को {terms} के सभी {total} पदों को सही बनाने वाला कोई नियम नहीं मिला। उसने n के बहुपद, n-वें अभाज्य के बहुपद और 3 तक की रैखिक पुनरावृत्तियाँ आज़माईं, और OEIS में इन पदों वाली कोई अनुक्रम नहीं है{lisan}। इसलिए अनुमान के बजाय कोई अगली संख्या नहीं दी। यदि आपको अनुक्रम का स्रोत पता हो तो बताइए, मीज़ान वह नियम हर पद पर जाँचेगा।",
        "ar": "لم يجد ميزان قاعدةً تُعيد الحدود الـ{total} كلها في {terms}. جرّب كثيرات حدود في n وفي العدد الأولي رقم n والتكرارات الخطية حتى الرتبة 3، ولا يحوي OEIS متتالية بهذه الحدود{lisan}. لذلك لا يعطي عددًا تاليًا بدل التخمين. إن عرفت مصدر المتتالية فأخبر ميزان ليتحقّق من قاعدتها على كل حد.",
    },
    "silsila_tried_lisan": {
        "en": "; Lisan proposed {tries} rule(s) and none reproduced every term in MIZAN's sandbox",
        "hi-latn": "; Lisan ne {tries} rule diye, koi bhi MIZAN ke sandbox me har term sahi nahi bana saka",
        "ur": "؛ لسان نے {tries} قاعدے دیے، کوئی بھی میزان کے سینڈ باکس میں ہر عدد درست نہ بنا سکا",
        "hi": "; लिसान ने {tries} नियम दिए, कोई भी मीज़ान के सैंडबॉक्स में हर पद सही नहीं बना सका",
        "ar": "؛ واقترح لسان {tries} قاعدة لم تُعِد أيٌّ منها كل الحدود في بيئة ميزان",
    },
    "qiyas_proven": {
        "en": "MIZAN found a rule that reproduces all {total} examples exactly in its sandbox, and applied it to the test input.",
        "hi-latn": "MIZAN ko ek rule mila jo sandbox me sabhi {total} misaalein bilkul sahi banata hai; wahi rule test input par lagaya.",
        "ur": "میزان کو ایک قاعدہ ملا جو سینڈ باکس میں تمام {total} مثالیں بالکل درست بناتا ہے، اور وہی ٹیسٹ پر لگایا۔",
        "hi": "मीज़ान को एक नियम मिला जो सैंडबॉक्स में सभी {total} उदाहरण बिल्कुल सही बनाता है, और वही टेस्ट पर लगाया।",
        "ar": "وجد ميزان قاعدةً تُعيد إنتاج الأمثلة الـ{total} كلها بدقة في بيئته المعزولة، وطبّقها على مُدخل الاختبار.",
    },
    "qiyas_unproven": {
        "en": "Not verified: MIZAN's best rule reproduces {fitted} of {total} examples, so this answer is a guess.",
        "hi-latn": "Tasdeeq nahi hui: MIZAN ka behtareen rule {total} me se {fitted} misaalein sahi banata hai, isliye yeh jawab andaza hai.",
        "ur": "تصدیق نہیں ہوئی: میزان کا بہترین قاعدہ {total} میں سے {fitted} مثالیں درست بناتا ہے، اس لیے یہ جواب اندازہ ہے۔",
        "hi": "पुष्टि नहीं हुई: मीज़ान का सबसे अच्छा नियम {total} में से {fitted} उदाहरण सही बनाता है, इसलिए यह उत्तर अनुमान है।",
        "ar": "لم يُتحقَّق: أفضل قاعدة لدى ميزان تُعيد {fitted} من {total} أمثلة، فهذا الجواب تخمين.",
    },
    "qiyas_no_rule": {
        "en": "MIZAN could not find a rule that runs on these {total} examples, so it gives no answer.",
        "hi-latn": "MIZAN in {total} misaalon par chalne wala koi rule nahi dhoondh saka, isliye jawab nahi diya.",
        "ur": "میزان ان {total} مثالوں پر چلنے والا کوئی قاعدہ نہیں ڈھونڈ سکا، اس لیے جواب نہیں دیا۔",
        "hi": "मीज़ान इन {total} उदाहरणों पर चलने वाला कोई नियम नहीं ढूंढ सका, इसलिए उत्तर नहीं दिया।",
        "ar": "لم يجد ميزان قاعدةً تعمل على هذه الأمثلة الـ{total}، فلم يُعطِ جوابًا.",
    },
    "qiyas_answer": {
        "en": "Test output {n}",
        "hi-latn": "Test output {n}",
        "ur": "ٹیسٹ نتیجہ {n}",
        "hi": "टेस्ट आउटपुट {n}",
        "ar": "ناتج الاختبار {n}",
    },
    "muhasaba_head": {
        "en": "Correction (Muhasaba): MIZAN re-checked an earlier answer in this chat and found a mistake.",
        "hi-latn": "Islah (Muhasaba): MIZAN ne is chat ka ek pichla jawab dobara jaancha aur ghalati payi.",
        "ur": "اصلاح (محاسبہ): میزان نے اس چیٹ کا ایک پچھلا جواب دوبارہ جانچا اور غلطی پائی۔",
        "hi": "सुधार (मुहासबा): मीज़ान ने इस चैट का एक पिछला उत्तर दोबारा जाँचा और ग़लती पाई।",
        "ar": "تصحيح (محاسبة): أعاد ميزان فحص جواب سابق في هذه المحادثة فوجد خطأً.",
    },
    "muhasaba_arithmetic": {
        "en": "`{expression}` is **{correct}**, not {claimed} (calculated exactly by MIZAN).",
        "hi-latn": "`{expression}` ka jawab **{correct}** hai, {claimed} nahi (MIZAN ka exact hisab).",
        "ur": "`{expression}` کا جواب **{correct}** ہے، {claimed} نہیں (میزان کا درست حساب)۔",
        "hi": "`{expression}` का उत्तर **{correct}** है, {claimed} नहीं (मीज़ान का सटीक हिसाब)।",
        "ar": "`{expression}` يساوي **{correct}** لا {claimed} (حسبه ميزان بدقة).",
    },
    "muhasaba_quote": {
        "en": "The text quoted for {reference} does not match the source. The source text is:",
        "hi-latn": "{reference} ke liye diya gaya matan asal source se nahi milta. Asal matan yeh hai:",
        "ur": "{reference} کے لیے دیا گیا متن اصل ماخذ سے نہیں ملتا۔ اصل متن یہ ہے:",
        "hi": "{reference} के लिए दिया गया पाठ मूल स्रोत से मेल नहीं खाता। मूल पाठ यह है:",
        "ar": "النص المنقول لـ{reference} لا يطابق المصدر. نص المصدر هو:",
    },
    "muhasaba_tail": {
        "en": "MIZAN reviews the answers it did not verify; set the chat preference muhasaba to off to stop these corrections.",
        "hi-latn": "MIZAN un jawabon ko jaanchta hai jinki tasdeeq nahi hui thi; ye islah band karne ke liye chat preference muhasaba ko off karein.",
        "ur": "میزان اُن جوابات کو جانچتا ہے جن کی تصدیق نہیں ہوئی تھی؛ یہ اصلاحات بند کرنے کے لیے چیٹ ترجیح muhasaba کو off کریں۔",
        "hi": "मीज़ान उन उत्तरों को जाँचता है जिनकी पुष्टि नहीं हुई थी; ये सुधार बंद करने के लिए चैट वरीयता muhasaba को off करें।",
        "ar": "يراجع ميزان الأجوبة التي لم يتحقّق منها؛ لإيقاف هذه التصحيحات اضبط تفضيل المحادثة muhasaba على off.",
    },
    "amanah_ignored": {
        "en": "Amanah: {count} instruction(s) aimed at the AI were found in what MIZAN read and were ignored; they did not change this answer or any action.",
        "hi-latn": "Amanah: jo MIZAN ne padha usme AI ke liye {count} hidayat chhupi thi; MIZAN ne unhe nazar-andaz kiya, is jawab ya kisi action par unka asar nahi hua.",
        "ur": "امانت: میزان نے جو پڑھا اس میں AI کے لیے {count} ہدایت تھی؛ میزان نے اسے نظرانداز کیا، اس جواب یا کسی عمل پر اس کا اثر نہیں ہوا۔",
        "hi": "अमानत: मीज़ान ने जो पढ़ा उसमें AI के लिए {count} निर्देश थे; मीज़ान ने उन्हें अनदेखा किया, इस जवाब या किसी काम पर उनका असर नहीं हुआ।",
        "ar": "أمانة: وُجد فيما قرأه ميزان {count} من التعليمات الموجّهة إلى الذكاء الاصطناعي، فتجاهلها؛ ولم تؤثر في هذا الجواب ولا في أي إجراء.",
    },
    "hifz_reused": {
        "en": "MIZAN re-ran a program it verified before, with no language-model call; the output matches what was verified (run {runs}).",
        "hi-latn": "MIZAN ne pehle tasdeeq kiya hua program dobara chalaya, bina language model ke; output wahi hai jo tasdeeq hua tha (run {runs}).",
        "ur": "میزان نے پہلے سے تصدیق شدہ پروگرام دوبارہ چلایا، لینگویج ماڈل کے بغیر؛ نتیجہ وہی ہے جس کی تصدیق ہوئی تھی (رن {runs})۔",
        "hi": "मीज़ान ने पहले से सत्यापित प्रोग्राम फिर चलाया, भाषा मॉडल के बिना; आउटपुट वही है जो सत्यापित हुआ था (रन {runs})।",
        "ar": "أعاد ميزان تشغيل برنامج تحقّق منه سابقًا، دون استدعاء النموذج اللغوي؛ والناتج مطابق لما تُحقِّق منه (التشغيل {runs}).",
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
    "watch_created": {
        "en": 'Saved: **{title}**, {when}. Next: {next}. Notices arrive in your Muraqabah chat; MIZAN holds them during salah and learns from your "useful" and "not now". Manage it on the Watchers page.',
        "hi-latn": 'Save ho gaya: **{title}**, {when}. Agli baar: {next}. Paigham aapki Muraqabah chat me aayenge; namaz ke waqt MIZAN unhe rok kar rakhta hai aur aapke "useful" aur "not now" se seekhta hai. Watchers page par badal sakte hain.',
        "ur": 'محفوظ ہو گیا: **{title}**، {when}۔ اگلی بار: {next}۔ پیغامات آپ کی مراقبہ چیٹ میں آئیں گے؛ نماز کے وقت میزان انہیں روکے رکھتا ہے اور آپ کے "useful" اور "not now" سے سیکھتا ہے۔',
        "hi": 'सहेज लिया: **{title}**, {when}। अगली बार: {next}। संदेश आपकी मुराक़बा चैट में आएँगे; नमाज़ के समय मीज़ान उन्हें रोके रखता है और आपके "useful" और "not now" से सीखता है।',
        "ar": 'حُفظ: **{title}**، {when}. المرة القادمة: {next}. تصل التنبيهات إلى محادثة المراقبة؛ ويؤخرها ميزان وقت الصلاة ويتعلّم من "مفيد" و"ليس الآن".',
    },
    "watch_need_place": {
        "en": 'To time this around the prayer, MIZAN needs your city. Write it in the request (for example "... after Fajr in Karachi") or set it on the Watchers page.',
        "hi-latn": 'Namaz ke hisaab se waqt rakhne ke liye MIZAN ko aapka shehar chahiye. Paigham me likhiye (jaise "... Fajr ke baad, Karachi") ya Watchers page par set kijiye.',
        "ur": "نماز کے حساب سے وقت رکھنے کے لیے میزان کو آپ کا شہر چاہیے۔ پیغام میں لکھیے یا Watchers صفحے پر درج کیجیے۔",
        "hi": "नमाज़ के हिसाब से समय रखने के लिए मीज़ान को आपका शहर चाहिए। संदेश में लिखिए या Watchers पेज पर सेट कीजिए।",
        "ar": "ليضبط ميزان الوقت حسب الصلاة يحتاج إلى مدينتك. اكتبها في الطلب أو حدّدها في صفحة المراقبة.",
    },
    "watch_failed": {
        "en": "MIZAN could not save the watcher: {reason}",
        "hi-latn": "MIZAN watcher save nahi kar saka: {reason}",
        "ur": "میزان واچر محفوظ نہیں کر سکا: {reason}",
        "hi": "मीज़ान वॉचर सहेज नहीं सका: {reason}",
        "ar": "تعذّر على ميزان حفظ المراقِب: {reason}",
    },
    "salah_header": {
        "en": "**Prayer times for {place}**, {date} ({hijri})",
        "hi-latn": "**{place} ke namaz ke auqaat**, {date} ({hijri})",
        "ur": "**{place} کے اوقاتِ نماز**، {date} ({hijri})",
        "hi": "**{place} के नमाज़ के औक़ात**, {date} ({hijri})",
        "ar": "**مواقيت الصلاة في {place}**، {date} ({hijri})",
    },
    "salah_method": {
        "en": "Computed by MIZAN with the {method} method, Asr by the {asr} school. Your masjid's iqamah and its own timetable come first.",
        "hi-latn": "MIZAN ne {method} tareeqe se hisaab kiya, Asr {asr} mazhab ke mutabiq. Aapki masjid ki iqamat aur uska timetable muqaddam hai.",
        "ur": "میزان نے {method} طریقے سے حساب کیا، عصر {asr} مذہب کے مطابق۔ آپ کی مسجد کی اقامت اور اس کا نظام الاوقات مقدم ہے۔",
        "hi": "मीज़ान ने {method} तरीक़े से हिसाब किया, अस्र {asr} मज़हब के मुताबिक़। आपकी मस्जिद की इक़ामत और उसका टाइमटेबल पहले है।",
        "ar": "حسبها ميزان بطريقة {method}، والعصر على مذهب {asr}. وتقويم مسجدك وإقامته مقدَّمان.",
    },
    "salah_need_place": {
        "en": 'Which city? For example "Fajr time in Karachi", or set your city on the Watchers page.',
        "hi-latn": 'Kaunsa shehar? Jaise "Fajr ka time Karachi", ya Watchers page par apna shehar set kijiye.',
        "ur": 'کون سا شہر؟ مثلاً "کراچی میں فجر کا وقت"، یا Watchers صفحے پر اپنا شہر درج کیجیے۔',
        "hi": 'कौन-सा शहर? जैसे "कराची में फ़ज्र का समय", या Watchers पेज पर अपना शहर सेट कीजिए।',
        "ar": 'أي مدينة؟ مثلاً "وقت الفجر في كراتشي"، أو حدّد مدينتك في صفحة المراقبة.',
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
    "sidq_corrected": {
        "en": "Truth Gate (Sidq): MIZAN corrected or removed {count} claim(s) it could prove wrong or unsupported.",
        "hi-latn": "Truth Gate (Sidq): MIZAN ne {count} aisi baat(ein) theek ki ya hata di jo galat ya be-saboot sabit hui.",
        "ur": "Truth Gate (صدق): میزان نے {count} ایسی بات درست کی یا ہٹا دی جو غلط یا بے ثبوت ثابت ہوئی۔",
        "hi": "Truth Gate (सिद्क़): मीज़ान ने {count} ऐसी बात ठीक की या हटा दी जो ग़लत या बेसबूत साबित हुई।",
        "ar": "بوابة الصدق: صحّح ميزان أو حذف {count} ادعاءً ثبت خطؤه أو لا سند له.",
    },
    "sidq_flagged": {
        "en": "Truth Gate (Sidq): {count} claim(s) above could not be backed by MIZAN; see the marks.",
        "hi-latn": "Truth Gate (Sidq): upar ki {count} baat(ein) MIZAN saboot se pakki nahi kar saka.",
        "ur": "Truth Gate (صدق): اوپر کی {count} بات میزان ثبوت سے پکی نہیں کر سکا۔",
        "hi": "Truth Gate (सिद्क़): ऊपर की {count} बात मीज़ान सबूत से पक्की नहीं कर सका।",
        "ar": "بوابة الصدق: لم يستطع ميزان إسناد {count} من الادعاءات أعلاه.",
    },
    "sidq_quote": {
        "en": "MIZAN replaced the quoted text with its source ({reference}).",
        "hi-latn": "MIZAN ne quote ki hui ibarat ko asal source se badla ({reference}).",
        "ur": "میزان نے نقل شدہ عبارت کو اصل ماخذ سے بدل دیا ({reference})۔",
        "hi": "मीज़ान ने उद्धृत पाठ को मूल स्रोत से बदल दिया ({reference})।",
        "ar": "استبدل ميزان النص المقتبس بنص المصدر ({reference}).",
    },
    "quran_answer": {
        "en": "Answer from the ayah's own words (its translation, above), not tafsir",
        "hi-latn": "Jawab ayat ke apne alfaaz (upar diye tarjume) se, tafsir nahi",
        "ur": "جواب آیت کے اپنے الفاظ (اوپر دیے گئے ترجمے) سے، تفسیر نہیں",
        "hi": "जवाब आयत के अपने शब्दों (ऊपर दिए अनुवाद) से, तफ़सीर नहीं",
        "ar": "الجواب من ألفاظ الآية نفسها (ترجمتها أعلاه)، وليس تفسيرًا",
    },
    "hf_repos": {
        "en": "{kind} of **{owner}** on Hugging Face ({count}):",
        "hi-latn": "Hugging Face par **{owner}** ke {kind} ({count}):",
        "ur": "ہگنگ فیس پر **{owner}** کے {kind} ({count}):",
        "hi": "Hugging Face पर **{owner}** के {kind} ({count}):",
        "ar": "{kind} لدى **{owner}** على Hugging Face ({count}):",
    },
    "hf_files": {
        "en": "**{repo}** has {count} file(s), {size} in all:",
        "hi-latn": "**{repo}** mein {count} file(s) hain, kul {size}:",
        "ur": "**{repo}** میں {count} فائلیں ہیں، کل {size}:",
        "hi": "**{repo}** में {count} फ़ाइलें हैं, कुल {size}:",
        "ar": "في **{repo}** {count} ملفًا، المجموع {size}:",
    },
    "hf_preview": {
        "en": "First rows ({split}):",
        "hi-latn": "Pehli rows ({split}):",
        "ur": "پہلی قطاریں ({split}):",
        "hi": "पहली पंक्तियाँ ({split}):",
        "ar": "أول الصفوف ({split}):",
    },
    "hf_imported": {
        "en": "MIZAN imported `{source_path}` from {repo} into your project as `{path}` ({size}{rows}). Code can now use it offline.",
        "hi-latn": "MIZAN ne {repo} se `{source_path}` aapke project mein `{path}` ke naam se rakh di ({size}{rows}). Ab code isse bina internet ke use kar sakta hai.",
        "ur": "میزان نے {repo} سے `{source_path}` آپ کے پروجیکٹ میں `{path}` کے نام سے رکھ دی ({size}{rows})۔ اب کوڈ اسے بغیر انٹرنیٹ کے استعمال کر سکتا ہے۔",
        "hi": "मीज़ान ने {repo} से `{source_path}` आपके प्रोजेक्ट में `{path}` नाम से रख दी ({size}{rows})। अब कोड इसे बिना इंटरनेट के इस्तेमाल कर सकता है।",
        "ar": "استورد ميزان `{source_path}` من {repo} إلى مشروعك باسم `{path}` ({size}{rows})، ويستطيع الكود استخدامه دون اتصال.",
    },
    "hf_sampled": {
        "en": "The file on the Hub is {total}; it is larger than a project file may be, so MIZAN kept its first whole rows.",
        "hi-latn": "Hub par file {total} ki hai; project ki had se badi hai, isliye MIZAN ne uski pehli poori rows rakhi hain.",
        "ur": "ہب پر فائل {total} کی ہے؛ پروجیکٹ کی حد سے بڑی ہے، اس لیے میزان نے اس کی پہلی مکمل قطاریں رکھی ہیں۔",
        "hi": "Hub पर फ़ाइल {total} की है; प्रोजेक्ट की सीमा से बड़ी है, इसलिए मीज़ान ने उसकी पहली पूरी पंक्तियाँ रखीं।",
        "ar": "حجم الملف على المنصة {total}، وهو أكبر من حد ملف المشروع، فاحتفظ ميزان بأول صفوفه الكاملة.",
    },
    "hf_failed": {
        "en": "MIZAN could not read that from Hugging Face: {reason}",
        "hi-latn": "MIZAN Hugging Face se yeh nahi padh saka: {reason}",
        "ur": "میزان ہگنگ فیس سے یہ نہیں پڑھ سکا: {reason}",
        "hi": "मीज़ान Hugging Face से यह नहीं पढ़ सका: {reason}",
        "ar": "تعذّر على ميزان قراءة ذلك من Hugging Face: {reason}",
    },
    "hf_next": {
        "en": 'To bring a file into your project, name it: "…{repo} se `<file>` project me lao".',
        "hi-latn": 'Koi file project mein laani ho to uska naam likhiye: "{repo} se `<file>` project me lao".',
        "ur": 'کوئی فائل پروجیکٹ میں لانی ہو تو اس کا نام لکھیے: "{repo} se `<file>` project me lao"۔',
        "hi": 'कोई फ़ाइल प्रोजेक्ट में लानी हो तो उसका नाम लिखिए: "{repo} se `<file>` project me lao"।',
        "ar": 'لإحضار ملف إلى مشروعك اذكر اسمه: "{repo} se `<file>` project me lao".',
    },
    "page_fallback": {
        "en": "{failed} could not be read ({reason}), so MIZAN read {url}, the other address you gave.",
        "hi-latn": "{failed} nahi padha ja saka ({reason}), isliye MIZAN ne aapka diya hua doosra address {url} padha.",
        "ur": "{failed} نہیں پڑھا جا سکا ({reason})، اس لیے میزان نے آپ کا دیا ہوا دوسرا پتا {url} پڑھا۔",
        "hi": "{failed} नहीं पढ़ा जा सका ({reason}), इसलिए मीज़ान ने आपका दिया दूसरा पता {url} पढ़ा।",
        "ar": "تعذّرت قراءة {failed} ({reason})، فقرأ ميزان العنوان الآخر الذي أعطيته: {url}.",
    },
    "page_computed": {
        "en": "MIZAN worked this out from the page with a program it ran in its sandbox.",
        "hi-latn": "MIZAN ne yeh page se ek program chala kar nikala (apne sandbox mein).",
        "ur": "میزان نے یہ صفحے سے ایک پروگرام اپنے سینڈ باکس میں چلا کر نکالا۔",
        "hi": "मीज़ान ने यह पेज से एक प्रोग्राम अपने सैंडबॉक्स में चलाकर निकाला।",
        "ar": "استخرج ميزان هذا من الصفحة ببرنامج شغّله في بيئته المعزولة.",
    },
    "ran_file": {
        "en": "MIZAN ran `{path}` in your project's sandbox.",
        "hi-latn": "MIZAN ne `{path}` aapke project ke sandbox mein chalaya.",
        "ur": "میزان نے `{path}` آپ کے پروجیکٹ کے سینڈ باکس میں چلایا۔",
        "hi": "मीज़ान ने `{path}` आपके प्रोजेक्ट के सैंडबॉक्स में चलाया।",
        "ar": "شغّل ميزان `{path}` في بيئة مشروعك المعزولة.",
    },
    "run_file_missing": {
        "en": "There is no `{path}` in this project.",
        "hi-latn": "Is project mein `{path}` nahi hai.",
        "ur": "اس پروجیکٹ میں `{path}` نہیں ہے۔",
        "hi": "इस प्रोजेक्ट में `{path}` नहीं है।",
        "ar": "لا يوجد `{path}` في هذا المشروع.",
    },
    "task_missing": {
        "en": "MIZAN could not find {files} in this project.",
        "hi-latn": "MIZAN ko is project mein {files} nahi mile.",
        "ur": "میزان کو اس پروجیکٹ میں {files} نہیں ملے۔",
        "hi": "मीज़ान को इस प्रोजेक्ट में {files} नहीं मिले।",
        "ar": "لم يجد ميزان {files} في هذا المشروع.",
    },
    "task_failed": {
        "en": "MIZAN could not finish this on your project's files: {reason}",
        "hi-latn": "MIZAN yeh aapke project ki files par poora nahi kar saka: {reason}",
        "ur": "میزان یہ آپ کے پروجیکٹ کی فائلوں پر مکمل نہیں کر سکا: {reason}",
        "hi": "मीज़ान यह आपके प्रोजेक्ट की फ़ाइलों पर पूरा नहीं कर सका: {reason}",
        "ar": "لم يستطع ميزان إتمام هذا على ملفات مشروعك: {reason}",
    },
    "task_done": {
        "en": "MIZAN did this with a program it ran on your project's files and checked.",
        "hi-latn": "MIZAN ne yeh aapke project ki files par ek program chala kar kiya aur check kiya.",
        "ur": "میزان نے یہ آپ کے پروجیکٹ کی فائلوں پر ایک پروگرام چلا کر کیا اور جانچا۔",
        "hi": "मीज़ान ने यह आपके प्रोजेक्ट की फ़ाइलों पर एक प्रोग्राम चलाकर किया और जाँचा।",
        "ar": "أنجز ميزان هذا ببرنامج شغّله على ملفات مشروعك وتحقّق منه.",
    },
    "task_files": {
        "en": "Files written",
        "hi-latn": "Likhi gayi files",
        "ur": "لکھی گئی فائلیں",
        "hi": "लिखी गई फ़ाइलें",
        "ar": "الملفات المكتوبة",
    },
    "task_restored": {
        "en": "MIZAN put back {files}: the request did not ask to change them.",
        "hi-latn": "MIZAN ne {files} wapas pehle jaisi kar di: request mein inhe badalne ko nahi kaha gaya tha.",
        "ur": "میزان نے {files} پہلے جیسی کر دیں: درخواست میں انہیں بدلنے کو نہیں کہا گیا تھا۔",
        "hi": "मीज़ान ने {files} पहले जैसी कर दीं: अनुरोध में इन्हें बदलने को नहीं कहा गया था।",
        "ar": "أعاد ميزان {files} كما كانت: لم يطلب الطلب تغييرها.",
    },
    "amanah_held_files": {
        "en": "MIZAN did not write {files}: your request did not name them, and a file it read tried to instruct the AI.",
        "hi-latn": "MIZAN ne {files} nahi likhi: aapki request mein inka naam nahi tha, aur padhi gayi ek file AI ko hukm dene ki koshish kar rahi thi.",
        "ur": "میزان نے {files} نہیں لکھیں: آپ کی درخواست میں ان کا نام نہیں تھا، اور پڑھی گئی ایک فائل AI کو حکم دینے کی کوشش کر رہی تھی۔",
        "hi": "मीज़ान ने {files} नहीं लिखीं: आपके अनुरोध में इनका नाम नहीं था, और पढ़ी गई एक फ़ाइल AI को आदेश देने की कोशिश कर रही थी।",
        "ar": "لم يكتب ميزان {files}: لم يذكرها طلبك، وحاول ملف قرأه أن يوجّه الذكاء الاصطناعي.",
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
    "remembered": {
        "en": "I'll remember that. It is saved in your notes as you said it; you can see or forget it in your Daftar.",
        "hi-latn": "Main yeh yaad rakhunga. Aapke alfaaz jaise the waise notes mein save hain; Daftar mein dekh ya bhula sakte hain.",
        "ur": "میں یہ یاد رکھوں گا۔ آپ کے الفاظ جیسے تھے ویسے نوٹس میں محفوظ ہیں؛ دفتر میں دیکھ یا بھلا سکتے ہیں۔",
        "hi": "मैं यह याद रखूँगा। आपके शब्द जैसे थे वैसे नोट्स में सहेजे गए हैं; दफ़्तर में देख या भुला सकते हैं।",
        "ar": "سأتذكر ذلك. حُفظ في ملاحظاتك كما قلته؛ يمكنك رؤيته أو نسيانه في دفترك.",
    },
    "capabilities": {
        "en": "MIZAN works through its own tools, and they are real:",
        "hi-latn": "MIZAN apne asli tools se kaam karta hai:",
        "ur": "میزان اپنے حقیقی ٹولز سے کام کرتا ہے:",
        "hi": "मीज़ान अपने असली टूल्स से काम करता है:",
        "ar": "يعمل ميزان بأدواته الحقيقية:",
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


_CAUTION_KEY = re.compile(r"warn|error|stderr|caution|deprecat|alert", re.IGNORECASE)
_CAUTION_LINE = re.compile(
    r"\b(?:warning|deprecated|deprecation|caution|insecure|unsafe|expired|truncated|"
    r"partial(?:ly)?|skipped|rate[ -]?limit(?:ed)?|quota)\b",
    re.IGNORECASE,
)
_ACKNOWLEDGED = re.compile(
    r"warn|error|caution|careful|deprecat|fail|insecure|unsafe|expire|truncat|partial|skipp|"
    r"limit|quota|chetavani|dhyan|ehtiyat|khabardar|ghalti|galti|"
    r"\u062a\u062d\u0630\u064a\u0631|\u062a\u0646\u0628\u064a\u0647|\u062e\u0637\u0623|"
    r"\u0627\u062d\u062a\u06cc\u0627\u0637|\u062e\u0628\u0631\u062f\u0627\u0631|"
    r"\u063a\u0644\u0637\u06cc|\u091a\u0947\u0924\u093e\u0935\u0928\u0940|"
    r"\u0924\u094d\u0930\u0941\u091f\u093f|\u0938\u093e\u0935\u0927\u093e\u0928",
    re.IGNORECASE,
)


def cautions(result: Any, limit: int = 4) -> list[str]:
    """Warnings and errors a tool's result carries, which any wording of it must keep."""
    found: list[str] = []

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 6 or len(found) >= limit:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if _CAUTION_KEY.search(str(key)) and item not in (None, "", [], {}, False, 0):
                    found.append(f"{key}: {item}"[:200])
                else:
                    walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value[:50]:
                walk(item, depth + 1)
        elif isinstance(value, str):
            stripped = value.strip()
            if stripped[:1] in "{[":
                try:
                    walk(json.loads(stripped), depth + 1)
                    return
                except ValueError:
                    pass
            found.extend(
                line.strip()[:200] for line in value.splitlines() if _CAUTION_LINE.search(line)
            )

    walk(result)
    return list(dict.fromkeys(found))[:limit]


def acknowledges(text: str, caution: str) -> bool:
    """The wording mentions the caution: its kind, or its own distinctive words."""
    if _ACKNOWLEDGED.search(text):
        return True
    words = {word.lower() for word in re.findall(r"[^\W\d_]{5,}", caution)}
    return bool(words) and sum(word in text.lower() for word in words) * 3 >= len(words)


def furqan(
    text: str, facts_text: str, *, max_citation: int = 0, warnings: list[str] | None = None
) -> list[str]:
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
    # Safety omission: a warning or error in the tool's result may not be dropped.
    for caution in warnings or []:
        if not acknowledges(text, caution):
            problems.append(f"the wording leaves out a warning: {caution[:80]}")
            break
    trace.event("verify", "furqan", accepted=not problems, problems=problems)
    return problems
