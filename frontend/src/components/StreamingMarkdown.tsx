import { ChatMessageContent } from "./ChatMessage";

/**
 * The reply while it streams. Streamdown parses the text block by block,
 * keeps finished blocks memoized and completes unterminated markdown (an
 * open code fence, a half bold), so nothing flickers as chunks arrive.
 */
export function StreamingMarkdown({
  content,
  onExploreWord,
}: {
  content: string;
  onExploreWord?: (word: string) => void;
}) {
  return <ChatMessageContent content={content} onExploreWord={onExploreWord} streaming />;
}
