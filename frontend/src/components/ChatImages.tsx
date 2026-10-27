import { useEffect, useState } from "react";
import type { ChatImage } from "../types";
import { authFetch } from "../utils/authFetch";
import { config } from "../config";

/** One kept chat image: fetched with the user's own credentials (the route
 *  serves only the owner's images), shown from a local object URL. */
function KeptImage({ sha, alt }: { sha: string; alt: string }) {
  const [url, setUrl] = useState<string>("");
  useEffect(() => {
    let current = "";
    let cancelled = false;
    authFetch(`${config.API_URL}/media/${sha}`)
      .then((response) => (response.ok ? response.blob() : null))
      .then((blob) => {
        if (blob && !cancelled) {
          current = URL.createObjectURL(blob);
          setUrl(current);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (current) URL.revokeObjectURL(current);
    };
  }, [sha]);
  if (!url) return <div className="w-24 h-24 rounded-lg bg-blue-500/40 animate-pulse" aria-label={alt} />;
  return <img src={url} alt={alt} className="max-h-48 max-w-full rounded-lg object-contain" />;
}

/** The images a user attached to a message (Basar). */
export function ChatImages({ images }: { images?: ChatImage[] }) {
  if (!images?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2 justify-end">
      {images.map((image, index) =>
        image.url ? (
          <img
            key={image.url}
            src={image.url}
            alt={`Attached image ${index + 1}`}
            className="max-h-48 max-w-full rounded-lg object-contain"
          />
        ) : image.sha ? (
          <KeptImage key={image.sha} sha={image.sha} alt={`Attached image ${index + 1}`} />
        ) : null,
      )}
    </div>
  );
}
