import { clock, isVoiceStatus, pickRecordingType, recordingName, speakable, withHeard } from "./voice.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

check("chrome records opus in webm", pickRecordingType(() => true) === "audio/webm;codecs=opus");
check(
  "safari falls back to mp4",
  pickRecordingType((type) => type === "audio/mp4") === "audio/mp4",
);
check("no recorder, no type", pickRecordingType(() => false) === "");
check("webm file name", recordingName("audio/webm;codecs=opus") === "voice.webm");
check("safari file name", recordingName("audio/mp4") === "voice.m4a");
check("heard words fill an empty box", withHeard("", " Asr kab hai? ") === "Asr kab hai?");
check("heard words follow typed ones", withHeard("Assalamu alaikum,", "Asr kab hai?") === "Assalamu alaikum, Asr kab hai?");
check("no double space", withHeard("Salam ", "Asr") === "Salam Asr");
check("silence changes nothing", withHeard("typed", "  ") === "typed");
check("clock", clock(0) === "0:00" && clock(65.9) === "1:05" && clock(90) === "1:30");
check(
  "status shape",
  isVoiceStatus({ available: true, seconds_left: null, max_seconds: 90, max_bytes: 1 }) &&
    !isVoiceStatus({ detail: "Not Found" }) &&
    !isVoiceStatus(null),
);

const spoken = speakable(
  "Ayat al-Kursi begins: ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ and is in Al-Baqarah 255. See https://quran.com/2/255 or run `print(1)`.",
);
check("quran is named, not read", spoken.includes("(Quran text, read it yourself)") && !/[\u064B-\u065F]/.test(spoken));
check("words around it stay", spoken.startsWith("Ayat al-Kursi begins:") && spoken.includes("Al-Baqarah 255"));
check("links and code are not read", spoken.includes("(link)") && !spoken.includes("quran.com") && !spoken.includes("print"));
check("urdu without vowel marks is read", speakable("آج عصر کا وقت چار بجے ہے") === "آج عصر کا وقت چار بجے ہے");

console.log(`voice: ${checks} checks passed`);
