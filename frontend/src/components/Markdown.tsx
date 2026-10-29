/**
 * Markdown for chat answers and panels, drawn by Streamdown: GFM, KaTeX math,
 * Shiki-highlighted code with copy, unterminated markdown completed while it
 * streams, links hardened, and each block's direction read from its own
 * letters (an Arabic paragraph reads right to left).
 *
 * Highlighting (Shiki) and math (KaTeX) are downloaded the first time an
 * answer needs them; until then a code block shows unhighlighted.
 */
import { memo, useEffect, useSyncExternalStore } from "react";
import { Streamdown, type Components, type PluginConfig } from "streamdown";
import "streamdown/styles.css";

let plugins: PluginConfig = {};
const listeners = new Set<() => void>();
const loading = new Set<keyof PluginConfig>();

function load(kind: "code" | "math") {
  if (loading.has(kind)) return;
  loading.add(kind);
  const module = kind === "code"
    ? import("@streamdown/code").then((m) => ({ code: m.code }))
    : import("./markdownMath").then((m) => ({ math: m.math }));
  module
    .then((loaded) => {
      plugins = { ...plugins, ...loaded };
      listeners.forEach((listener) => listener());
    })
    .catch(() => loading.delete(kind));
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const FENCE = /```|~~~/;
const MATH = /\$|\\\(|\\\[/;

function usePlugins(content: string): PluginConfig {
  const wantsCode = FENCE.test(content);
  const wantsMath = MATH.test(content);
  useEffect(() => {
    if (wantsCode) load("code");
    if (wantsMath) load("math");
  }, [wantsCode, wantsMath]);
  return useSyncExternalStore(subscribe, () => plugins);
}

interface MarkdownProps {
  content: string;
  /** Element overrides (e.g. `p` to make Arabic words tappable). */
  components?: Partial<Components>;
  /** True while the text is still arriving. */
  streaming?: boolean;
}

export const Markdown = memo(function Markdown({ content, components, streaming = false }: MarkdownProps) {
  const plugins = usePlugins(content);
  return (
    <div className="prose">
      <Streamdown
        mode={streaming ? "streaming" : "static"}
        isAnimating={streaming}
        parseIncompleteMarkdown={streaming}
        dir="auto"
        plugins={plugins}
        shikiTheme={["github-light", "github-dark"]}
        codeBlockMaxHeight={520}
        components={components}
      >
        {content}
      </Streamdown>
    </div>
  );
});

export type { Components };
