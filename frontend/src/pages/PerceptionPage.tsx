/**
 * Perception Page — Multimodal Analysis (Basirah + Nutq)
 * Upload images and audio for vision and voice analysis through the QCA pipeline.
 */

import { useState, useCallback } from "react";
import type { PageProps, PerceptionResult } from "../types";

const QALB_STATES = [
  { value: "", label: "Auto-detect" },
  { value: "neutral", label: "Neutral" },
  { value: "positive", label: "Positive" },
  { value: "frustrated", label: "Frustrated" },
  { value: "anxious", label: "Anxious" },
  { value: "confused", label: "Confused" },
  { value: "determined", label: "Determined" },
];

const CATEGORY_COLORS: Record<string, string> = {
  text: "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-400",
  diagram:
    "bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400",
  screenshot:
    "bg-cyan-100 dark:bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
  photo:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  document:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400",
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip data URL prefix to get raw base64
      const base64 = result.split(",")[1] || result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function PerceptionPage({ api }: PageProps) {
  const [text, setText] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [qalbState, setQalbState] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PerceptionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleImageSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setImageFile(file);
        const url = URL.createObjectURL(file);
        setImagePreview(url);
      }
    },
    [],
  );

  const handleAudioSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setAudioFile(file);
      }
    },
    [],
  );

  const handleAnalyze = async () => {
    if (!text && !imageFile && !audioFile) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const body: Record<string, unknown> = { text };
      if (qalbState) body.qalb_state = qalbState;

      if (imageFile) {
        body.image_base64 = await fileToBase64(imageFile);
        body.media_type = imageFile.type || "image/png";
      }
      if (audioFile) {
        body.audio_base64 = await fileToBase64(audioFile);
      }

      const res = await api.post("/perception/analyze", body);
      setResult(res as unknown as PerceptionResult);
    } catch (e) {
      setError((e as Error).message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const clearAll = () => {
    setText("");
    setImageFile(null);
    setImagePreview(null);
    setAudioFile(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/50 dark:border-white/5 bg-white/50 dark:bg-mizan-dark-surface/30 backdrop-blur-md">
        <div>
          <h2 className="page-title">Perception</h2>
          <p className="page-description">
            Vision (Basirah) & Voice (Nutq) analysis through the QCA pipeline
          </p>
        </div>
        <button className="btn-secondary text-sm" onClick={clearAll}>
          Clear
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input Panel */}
          <div className="space-y-4">
            {/* Text input */}
            <div className="card p-4 space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Text Context
              </label>
              <textarea
                className="input w-full text-sm"
                rows={3}
                placeholder="Optional text to provide context..."
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </div>

            {/* Image upload */}
            <div className="card p-4 space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Image (Basirah)
              </label>
              <div
                className="relative border-2 border-dashed border-gray-300 dark:border-zinc-600 rounded-xl p-6 text-center hover:border-amber-400 dark:hover:border-amber-500/50 transition-colors cursor-pointer"
                onClick={() =>
                  document.getElementById("perception-image-input")?.click()
                }
              >
                {imagePreview ? (
                  <div className="space-y-2">
                    <img
                      src={imagePreview}
                      alt="Preview"
                      className="max-h-48 mx-auto rounded-lg object-contain"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {imageFile?.name}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 py-4">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="w-8 h-8 mx-auto text-gray-400"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Click to upload an image
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      PNG, JPG, WebP
                    </p>
                  </div>
                )}
                <input
                  id="perception-image-input"
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleImageSelect}
                />
              </div>
            </div>

            {/* Audio upload */}
            <div className="card p-4 space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Audio (Nutq)
              </label>
              <div
                className="relative border-2 border-dashed border-gray-300 dark:border-zinc-600 rounded-xl p-6 text-center hover:border-amber-400 dark:hover:border-amber-500/50 transition-colors cursor-pointer"
                onClick={() =>
                  document.getElementById("perception-audio-input")?.click()
                }
              >
                {audioFile ? (
                  <div className="space-y-2">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="w-8 h-8 mx-auto text-amber-500"
                    >
                      <path d="M9 18V5l12-2v13" />
                      <circle cx="6" cy="18" r="3" />
                      <circle cx="18" cy="16" r="3" />
                    </svg>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {audioFile.name}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 py-4">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="w-8 h-8 mx-auto text-gray-400"
                    >
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
                    </svg>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Click to upload audio
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      MP3, WAV, M4A
                    </p>
                  </div>
                )}
                <input
                  id="perception-audio-input"
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={handleAudioSelect}
                />
              </div>
            </div>

            {/* Qalb state + Analyze */}
            <div className="flex items-center gap-3">
              <select
                className="input text-sm flex-1"
                value={qalbState}
                onChange={(e) => setQalbState(e.target.value)}
              >
                {QALB_STATES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <button
                className="btn-gold flex items-center gap-2 px-6"
                onClick={handleAnalyze}
                disabled={loading || (!text && !imageFile && !audioFile)}
              >
                {loading ? (
                  <>
                    <svg
                      className="w-4 h-4 animate-spin"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M7.76 7.76L4.93 4.93" />
                    </svg>
                    Analyzing...
                  </>
                ) : (
                  "Analyze"
                )}
              </button>
            </div>
          </div>

          {/* Results Panel */}
          <div className="space-y-4">
            {error && (
              <div className="card p-4 border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5">
                <p className="text-sm text-red-600 dark:text-red-400">
                  {error}
                </p>
              </div>
            )}

            {result && (
              <>
                {/* Basirah result */}
                {result.perception?.basirah && (
                  <div className="card p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        Vision (Basirah)
                      </h3>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${CATEGORY_COLORS[result.perception.basirah.category] || CATEGORY_COLORS.text}`}
                      >
                        {result.perception.basirah.category}
                      </span>
                    </div>

                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      {result.perception.basirah.description}
                    </p>

                    {/* Confidence bar */}
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 dark:text-gray-400 w-20">
                        Confidence
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-gray-200 dark:bg-zinc-700 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-amber-500 transition-all"
                          style={{
                            width: `${(result.perception.basirah.confidence * 100).toFixed(0)}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs font-mono text-gray-500 dark:text-gray-400 w-10 text-right">
                        {(result.perception.basirah.confidence * 100).toFixed(0)}
                        %
                      </span>
                    </div>

                    {/* Extracted text */}
                    {result.perception.basirah.extracted_text && (
                      <div className="rounded-lg bg-gray-50 dark:bg-zinc-800/50 border border-gray-200/60 dark:border-zinc-700/50 p-3">
                        <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                          Extracted Text
                        </span>
                        <p className="text-xs text-gray-700 dark:text-gray-300 mt-1 whitespace-pre-wrap">
                          {result.perception.basirah.extracted_text}
                        </p>
                      </div>
                    )}

                    {/* Key elements */}
                    {result.perception.basirah.key_elements?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {result.perception.basirah.key_elements.map(
                          (el, i) => (
                            <span
                              key={i}
                              className="px-2 py-0.5 rounded-md text-[11px] bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-gray-400"
                            >
                              {el}
                            </span>
                          ),
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Nutq result */}
                {result.perception?.nutq && (
                  <div className="card p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        Voice (Nutq)
                      </h3>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-400">
                        {result.perception.nutq.intent}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 dark:bg-zinc-700 text-gray-600 dark:text-gray-400">
                        {result.perception.nutq.language}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      {result.perception.nutq.text}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 dark:text-gray-400 w-20">
                        Confidence
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-gray-200 dark:bg-zinc-700 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-indigo-500 transition-all"
                          style={{
                            width: `${(result.perception.nutq.confidence * 100).toFixed(0)}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs font-mono text-gray-500 dark:text-gray-400 w-10 text-right">
                        {(result.perception.nutq.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                )}

                {/* QCA Integration results */}
                <div className="card p-4 space-y-3">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Cognitive Integration
                  </h3>

                  {/* Key terms */}
                  {result.key_terms?.length > 0 && (
                    <div>
                      <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Key Terms
                      </span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {result.key_terms.map((term, i) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 rounded-md text-[11px] bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200/60 dark:border-amber-500/20"
                          >
                            {term}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Zahir / Batin */}
                  {result.zahir && (
                    <div className="rounded-lg bg-gray-50 dark:bg-zinc-800/50 p-3 space-y-2">
                      <div>
                        <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                          Zahir (Apparent)
                        </span>
                        <p className="text-xs text-gray-700 dark:text-gray-300 mt-0.5">
                          {result.zahir}
                        </p>
                      </div>
                      {result.batin && (
                        <div>
                          <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                            Batin (Hidden)
                          </span>
                          <p className="text-xs text-gray-700 dark:text-gray-300 mt-0.5">
                            {result.batin}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Roots */}
                  {result.roots_identified &&
                    Object.keys(result.roots_identified).length > 0 && (
                      <div>
                        <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                          Arabic Roots (ISM)
                        </span>
                        <div className="flex flex-wrap gap-1.5 mt-1">
                          {Object.entries(result.roots_identified).map(
                            ([root, info]) => (
                              <span
                                key={root}
                                className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                                title={JSON.stringify(info)}
                              >
                                {root}
                              </span>
                            ),
                          )}
                        </div>
                      </div>
                    )}
                </div>
              </>
            )}

            {!result && !error && !loading && (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-500">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className="w-12 h-12"
                >
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                <p className="mt-3 font-medium">No analysis yet</p>
                <p className="text-sm mt-1">
                  Upload an image or audio file, then click Analyze
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
