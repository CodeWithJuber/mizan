import { Skeleton } from "@/components/ui/skeleton";

/** Shown while a page's code loads. */
export function PageFallback() {
  return (
    <div className="space-y-3 p-6" aria-busy="true" aria-live="polite">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
