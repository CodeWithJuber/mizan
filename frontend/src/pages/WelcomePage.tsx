/**
 * Welcome / Setup Wizard for MIZAN
 * Shows on first visit. Guides users through initial setup.
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../types";

interface WelcomePageProps {
  api: ApiClient;
  wsStatus: string;
  onComplete: () => void;
}

type Step = "welcome" | "provider" | "ready";

interface ProviderOption {
  id: string;
  name: string;
  description: string;
  configured: boolean;
  link: string;
  badge?: string;
}

export default function WelcomePage({ api, wsStatus, onComplete }: WelcomePageProps) {
  const [step, setStep] = useState<Step>("welcome");
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [testing, setTesting] = useState<string | null>(null);
  const [healthResult, setHealthResult] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    try {
      const res = await api.get("/providers") as { providers?: Array<{ name: string; configured: boolean; display: string }> };
      const list = res.providers || [];
      setProviders([
        {
          id: "anthropic",
          name: "Anthropic Claude",
          description: "Best for reasoning and coding. Claude Opus, Sonnet, Haiku.",
          configured: list.find((p) => p.name === "anthropic")?.configured || false,
          link: "https://console.anthropic.com/",
          badge: "Recommended",
        },
        {
          id: "openrouter",
          name: "OpenRouter",
          description: "Access 300+ models: Gemini, Llama, Mistral, and more.",
          configured: list.find((p) => p.name === "openrouter")?.configured || false,
          link: "https://openrouter.ai/",
          badge: "300+ models",
        },
        {
          id: "openai",
          name: "OpenAI",
          description: "GPT-4o, o3 and other OpenAI models.",
          configured: list.find((p) => p.name === "openai")?.configured || false,
          link: "https://platform.openai.com/",
        },
        {
          id: "ollama",
          name: "Ollama (Local)",
          description: "Run AI models on your own machine. Free, fully private.",
          configured: list.find((p) => p.name === "ollama")?.configured || false,
          link: "https://ollama.ai/",
          badge: "Free",
        },
      ]);
    } catch {
      // Use defaults
      setProviders([
        { id: "anthropic", name: "Anthropic Claude", description: "Best for reasoning and coding.", configured: false, link: "https://console.anthropic.com/", badge: "Recommended" },
        { id: "openrouter", name: "OpenRouter", description: "Access 300+ models.", configured: false, link: "https://openrouter.ai/", badge: "300+ models" },
        { id: "openai", name: "OpenAI", description: "GPT-4o and other models.", configured: false, link: "https://platform.openai.com/" },
        { id: "ollama", name: "Ollama (Local)", description: "Free, private, runs locally.", configured: false, link: "https://ollama.ai/", badge: "Free" },
      ]);
    }
  };

  const testProvider = async (name: string) => {
    setTesting(name);
    try {
      const res = await api.get(`/providers/${name}/health`) as { healthy?: boolean };
      setHealthResult((prev) => ({ ...prev, [name]: !!res.healthy }));
    } catch {
      setHealthResult((prev) => ({ ...prev, [name]: false }));
    }
    setTesting(null);
  };

  const finishSetup = () => {
    localStorage.setItem("mizan_setup_complete", "true");
    onComplete();
  };

  const anyConfigured = providers.some((p) => p.configured || healthResult[p.id]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-zinc-950 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full">

        {/* Step 1: Welcome */}
        {step === "welcome" && (
          <div className="text-center space-y-8">
            {/* Logo */}
            <div className="space-y-3">
              <div className="text-5xl font-arabic text-mizan-gold">&#1605;&#1610;&#1586;&#1575;&#1606;</div>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Welcome to MIZAN</h1>
              <p className="text-lg text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                Your personal AI assistant that can chat, browse the web, run code, and much more.
              </p>
            </div>

            {/* Connection status */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 shadow-sm">
              <div className={`w-2.5 h-2.5 rounded-full ${
                wsStatus === "connected" ? "bg-emerald-500" :
                wsStatus === "connecting" ? "bg-amber-500 animate-pulse" :
                "bg-red-500"
              }`} />
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {wsStatus === "connected" ? "Backend connected" :
                 wsStatus === "connecting" ? "Connecting to backend..." :
                 "Backend not running"}
              </span>
            </div>

            {wsStatus !== "connected" && (
              <div className="bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 rounded-lg p-4 text-sm text-amber-800 dark:text-amber-300 max-w-md mx-auto">
                <p className="font-medium mb-1">Start the backend first:</p>
                <code className="bg-amber-100 dark:bg-amber-500/10 px-2 py-1 rounded text-xs">mizan serve</code>
                {" "}or{" "}
                <code className="bg-amber-100 dark:bg-amber-500/10 px-2 py-1 rounded text-xs">make dev</code>
              </div>
            )}

            <div className="flex justify-center gap-3 pt-4">
              <button
                onClick={() => setStep("provider")}
                className="px-8 py-3 bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md"
              >
                Get Started
              </button>
              <button
                onClick={finishSetup}
                className="px-6 py-3 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-sm transition"
              >
                Skip setup
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Provider Setup */}
        {step === "provider" && (
          <div className="space-y-6">
            <div className="text-center space-y-2">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Choose Your AI Provider</h2>
              <p className="text-gray-600 dark:text-gray-400">
                You need at least one AI provider. Set the API key in your <code className="bg-gray-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded text-xs">.env</code> file.
              </p>
            </div>

            <div className="grid gap-3">
              {providers.map((p) => (
                <div key={p.id} className={`bg-white dark:bg-zinc-900 border rounded-xl p-4 transition ${
                  p.configured || healthResult[p.id]
                    ? "border-emerald-300 dark:border-emerald-500/30 ring-1 ring-emerald-200 dark:ring-emerald-500/20"
                    : "border-gray-200 dark:border-zinc-800"
                }`}>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100">{p.name}</h3>
                        {p.badge && (
                          <span className="text-xs bg-mizan-gold/10 text-mizan-gold px-2 py-0.5 rounded-full font-medium">
                            {p.badge}
                          </span>
                        )}
                        {(p.configured || healthResult[p.id]) && (
                          <span className="text-xs bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 rounded-full">
                            Ready
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{p.description}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <a
                        href={p.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        Get key
                      </a>
                      <button
                        onClick={() => testProvider(p.id)}
                        disabled={testing !== null}
                        className="text-xs px-3 py-1.5 bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 text-gray-700 dark:text-gray-300 rounded-lg transition disabled:opacity-50"
                      >
                        {testing === p.id ? "Testing..." : "Test"}
                      </button>
                    </div>
                  </div>
                  {healthResult[p.id] === false && (
                    <p className="text-xs text-red-500 mt-2">
                      Not configured. Add the API key to your .env file and restart the backend.
                    </p>
                  )}
                </div>
              ))}
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setStep("welcome")}
                className="px-4 py-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-sm transition"
              >
                Back
              </button>
              <button
                onClick={() => setStep("ready")}
                className="px-8 py-3 bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md"
              >
                {anyConfigured ? "Continue" : "Skip for now"}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Ready */}
        {step === "ready" && (
          <div className="text-center space-y-8">
            <div className="space-y-3">
              <div className="text-5xl">&#10024;</div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">You're All Set!</h2>
              <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                Start chatting with your AI, explore the agents, or build plugins to extend it.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-lg mx-auto">
              {[
                { label: "Start Chatting", desc: "Talk to your AI", icon: "\uD83D\uDCAC" },
                { label: "Meet Your Agents", desc: "See your AI team", icon: "\uD83E\uDD16" },
                { label: "Read the Docs", desc: "Learn to extend", icon: "\uD83D\uDCD6" },
              ].map((item) => (
                <div key={item.label} className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl p-4 text-center">
                  <div className="text-2xl mb-2">{item.icon}</div>
                  <div className="font-medium text-sm text-gray-900 dark:text-gray-100">{item.label}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{item.desc}</div>
                </div>
              ))}
            </div>

            <button
              onClick={finishSetup}
              className="px-8 py-3 bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md"
            >
              Enter MIZAN
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
