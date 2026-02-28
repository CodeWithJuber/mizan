import { memo, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 px-2 py-0.5 text-xs rounded bg-gray-200 dark:bg-zinc-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-zinc-600 transition-colors cursor-pointer focus-ring"
      aria-label="Copy code"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

interface MarkdownProps {
  content: string;
}

export const Markdown = memo(function Markdown({ content }: MarkdownProps) {
  return (
    <div className="prose">
      <ReactMarkdown
        components={{
          code({ children, className }) {
            const isBlock = className?.startsWith("language-");
            const lang = className?.replace("language-", "") || "";
            const text = String(children).replace(/\n$/, "");

            if (isBlock) {
              return (
                <div className="code-block-wrapper">
                  {lang && <span className="code-lang">{lang}</span>}
                  <CopyButton text={text} />
                  <pre>
                    <code>{text}</code>
                  </pre>
                </div>
              );
            }

            return <code>{children}</code>;
          },
          pre({ children }) {
            return <>{children}</>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
