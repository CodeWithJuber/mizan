import type { Artifact } from "../types.ts";

/** HTTP uses `version`; streamed artifacts may use `current_version`. */
export function artifactVersion(
  artifact: Artifact & { version?: number },
): number {
  return Math.max(
    artifact.current_version ?? 1,
    artifact.version ?? 1,
    ...(artifact.versions ?? []).map((version) => version.version),
  );
}

export function mergeSessionArtifacts(
  sessionId: string,
  listed: Artifact[],
  incoming: Artifact[],
): Artifact[] {
  const byId = new Map<string, Artifact>();
  for (const artifact of [...listed, ...incoming]) {
    // An old publish/stream request can finish after the active chat changes.
    if (artifact.session_id !== sessionId) continue;
    const previous = byId.get(artifact.id);
    byId.set(artifact.id, {
      ...previous,
      ...artifact,
      current_version: Math.max(
        previous ? artifactVersion(previous) : 1,
        artifactVersion(artifact),
      ),
    });
  }
  return [...byId.values()];
}

export function artifactDownloadName(
  artifact: Artifact,
  content: string,
): string {
  const filename =
    artifact.title.replace(/[^a-zA-Z0-9_.-]/g, "_") || "artifact";
  if (/\.[a-z0-9]+$/i.test(filename)) return filename;
  const extensions: Record<string, string> = {
    python: "py",
    javascript: "js",
    typescript: "ts",
    bash: "sh",
    shell: "sh",
  };
  const imageType = /^data:image\/(png|jpeg|webp);base64,/.exec(content)?.[1];
  let extension: string;
  if (artifact.kind === "image") {
    extension = imageType === "jpeg" ? "jpg" : imageType ?? "png";
  } else if (artifact.kind === "html") {
    extension = "html";
  } else if (artifact.kind === "markdown") {
    extension = "md";
  } else {
    extension = extensions[artifact.language ?? ""] ?? artifact.language ?? "txt";
  }
  return `${filename}.${extension}`;
}
