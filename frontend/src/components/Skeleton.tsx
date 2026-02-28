interface SkeletonLineProps {
  className?: string;
}

export function SkeletonLine({ className = "h-4 w-full" }: SkeletonLineProps) {
  return <div className={`skeleton ${className}`} />;
}

interface SkeletonCardProps {
  count?: number;
}

export function SkeletonCard({ count = 1 }: SkeletonCardProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card space-y-3 animate-fade-in">
          <div className="flex items-center gap-3">
            <div className="skeleton w-10 h-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <div className="skeleton h-4 w-1/3" />
              <div className="skeleton h-3 w-1/5" />
            </div>
          </div>
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-4/5" />
          <div className="flex gap-2">
            <div className="skeleton h-8 w-20 rounded-lg" />
            <div className="skeleton h-8 w-20 rounded-lg" />
            <div className="skeleton h-8 w-20 rounded-lg" />
          </div>
        </div>
      ))}
    </>
  );
}

export function SkeletonAvatar({ size = "w-8 h-8" }: { size?: string }) {
  return <div className={`skeleton rounded-full ${size}`} />;
}
