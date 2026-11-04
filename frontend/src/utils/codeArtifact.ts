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

const IMPORTED = /\bimport\s+(?:[^'";]*?\s+from\s+)?["']([^"']+)["']|\brequire\(\s*["']([^"']+)["']\s*\)/g;

/** The npm packages one file imports; React itself comes with the template. */
export function npmPackages(source: string): Record<string, string> {
  const packages: Record<string, string> = {};
  for (const match of source.matchAll(IMPORTED)) {
    const specifier = match[1] ?? match[2] ?? "";
    if (!specifier || /^[./]/.test(specifier) || specifier.includes(":")) continue;
    const parts = specifier.split("/");
    const name = specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
    if (name !== "react" && name !== "react-dom") packages[name] = "latest";
  }
  return packages;
}

export function codeArtifactConfig(
  language: string | undefined,
  content: string,
  view: "preview" | "code",
) {
  const setup = codeArtifactSetup(language);
  const dependencies = setup.runnable && setup.template !== "static" ? npmPackages(content) : {};
  return {
    ...setup,
    customSetup: Object.keys(dependencies).length ? { dependencies } : undefined,
    files: { [setup.file]: content },
    options: {
      autorun: setup.runnable && view === "preview",
      recompileMode: "delayed" as const,
      activeFile: setup.file,
      visibleFiles: [setup.file],
    },
  };
}
