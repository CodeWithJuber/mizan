/** CodeMirror 6 editor with language modes, one-dark theme and Ctrl/Cmd+S to save. */
import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";
import { languageOf } from "../../utils/workspaceTree";
import { useTheme } from "../../hooks/useTheme";

function languageExtension(path: string) {
  switch (languageOf(path)) {
    case "javascript": return [javascript()];
    case "jsx": return [javascript({ jsx: true })];
    case "typescript": return [javascript({ typescript: true })];
    case "tsx": return [javascript({ jsx: true, typescript: true })];
    case "python": return [python()];
    case "html": return [html()];
    case "css": return [css()];
    case "json": return [json()];
    case "markdown": return [markdown()];
    default: return [];
  }
}

interface Props {
  path: string;
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  readOnly?: boolean;
}

export default function CodeEditor({ path, value, onChange, onSave, readOnly = false }: Props) {
  const extensions = useMemo(() => languageExtension(path), [path]);
  const { isDark: dark } = useTheme();
  return (
    <div
      className="h-full min-h-[260px] text-sm"
      onKeyDown={(event) => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s" && onSave) {
          event.preventDefault();
          onSave();
        }
      }}
    >
      <CodeMirror
        value={value}
        height="100%"
        className="h-full"
        theme={dark ? oneDark : "light"}
        extensions={extensions}
        editable={!readOnly}
        readOnly={readOnly}
        onChange={onChange}
        aria-label={`Editor for ${path}`}
        basicSetup={{ lineNumbers: true, foldGutter: true, highlightActiveLine: true, bracketMatching: true, autocompletion: true }}
      />
    </div>
  );
}
