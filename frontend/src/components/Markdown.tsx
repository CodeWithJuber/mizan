/**
 * Markdown for chat answers and panels, drawn by Streamdown: GFM, KaTeX math,
 * Shiki-highlighted code with copy, unterminated markdown completed while it
 * streams, links hardened, and each block's direction read from its own
 * letters (an Arabic paragraph reads right to left).
 */
import { memo } from "react";
import { Streamdown, type Components } from "streamdown";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import "katex/dist/katex.min.css";
import "streamdown/styles.css";

const plugins = { code, math };

interface MarkdownProps {
  content: string;
  /** Element overrides (e.g. `p` to make Arabic words tappable). */
  components?: Partial<Components>;
  /** True while the text is still arriving. */
  streaming?: boolean;
}

export const Markdown = memo(function Markdown({ content, components, streaming = false }: MarkdownProps) {
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
