/** Match a single-file artifact to its actual browser runtime. */
export interface CodeArtifactSetup {
  template: "react" | "react-ts" | "vanilla" | "vanilla-ts" | "static";
  file: string;
  runnable: boolean;
}

export function codeArtifactSetup(language?: string): CodeArtifactSetup {
  switch ((language ?? "").toLowerCase()) {
    case "jsx":
      return { template: "react", file: "/App.js", runnable: true };
    case "tsx":
      return { template: "react-ts", file: "/App.tsx", runnable: true };
    case "javascript":
    case "js":
      return { template: "vanilla", file: "/index.js", runnable: true };
    case "typescript":
    case "ts":
      return { template: "vanilla-ts", file: "/index.ts", runnable: true };
    case "html":
      return { template: "static", file: "/index.html", runnable: true };
    default: {
      const files: Record<string, string> = {
        python: "/main.py",
        py: "/main.py",
        css: "/styles.css",
        json: "/data.json",
        bash: "/main.sh",
        shell: "/main.sh",
      };
      return {
        template: "static",
        file: files[(language ?? "").toLowerCase()] ?? "/snippet.txt",
        runnable: false,
      };
    }
  }
}

export function codeArtifactConfig(
  language: string | undefined,
  content: string,
  view: "preview" | "code",
) {
  const setup = codeArtifactSetup(language);
  return {
    ...setup,
    files: { [setup.file]: content },
    options: {
      autorun: setup.runnable && view === "preview",
      recompileMode: "delayed" as const,
      activeFile: setup.file,
      visibleFiles: [setup.file],
    },
  };
}
