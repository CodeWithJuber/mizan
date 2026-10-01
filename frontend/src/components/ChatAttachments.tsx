import { useEffect, useState } from "react";
function Attachment({ file, onRemove }: { file: File; onRemove: () => void }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return (
    <div className="flex items-center gap-3 p-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-900 min-w-0">
      {file.type.startsWith("image/") && url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View ${file.name}`}
        >
          <img
            src={url}
            alt={file.name}
            className="h-16 w-16 object-cover rounded-lg"
          />
        </a>
      ) : (
        <span className="text-2xl" aria-hidden="true">
          ♫
        </span>
      )}
      <div className="min-w-0">
        <p className="text-xs font-medium truncate max-w-40">{file.name}</p>
        <p className="text-xs text-gray-500">
          {(file.size / 1024 ** 2).toFixed(1)} MB
        </p>
      </div>
      <button
        onClick={onRemove}
        aria-label={`Remove ${file.name}`}
        className="p-2 ml-auto rounded-lg hover:bg-gray-200 dark:hover:bg-zinc-800 text-gray-500"
      >
        ×
      </button>
    </div>
  );
}
export function ChatAttachments({
  files,
  onRemove,
}: {
  files: File[];
  onRemove: (index: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 pb-3">
      {files.map((file, index) => (
        <Attachment
          key={`${file.name}-${file.lastModified}-${index}`}
          file={file}
          onRemove={() => onRemove(index)}
        />
      ))}
    </div>
  );
}
