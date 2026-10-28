import { Component, type ErrorInfo, type ReactNode } from "react";
import { useRouteError } from "react-router-dom";
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { reloadIfStale } from "../utils/staleBuild";

function Failure({ error, onRetry }: { error?: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? `${error.name}: ${error.message.slice(0, 200)}` : "";
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="w-full max-w-md space-y-5 text-center">
        <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-destructive/10">
          <TriangleAlert className="size-7 text-destructive" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">Something went wrong</h2>
          <p className="mt-1 text-sm text-muted-foreground">Try again, or reload the page.</p>
          {message && <p className="mt-2 break-words font-mono text-xs text-muted-foreground">{message}</p>}
        </div>
        <div className="flex justify-center gap-2">
          {onRetry && <Button onClick={onRetry}>Try again</Button>}
          <Button variant="outline" onClick={() => window.location.reload()}>Reload</Button>
        </div>
      </div>
    </div>
  );
}

/** Catches a failing page so the rest of the app keeps working. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("A page failed:", error, info);
    // A tab opened before a deploy asks for code files the new build no longer
    // has; when the server now serves another build, load it.
    void reloadIfStale();
  }

  componentDidUpdate(previous: { resetKey?: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (this.state.error) return <Failure error={this.state.error} onRetry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}

/** The router's error page (a route's code failed to load, for example after a deploy). */
export function RouteError() {
  const error = useRouteError();
  void reloadIfStale();
  return (
    <div className="flex min-h-dvh">
      <Failure error={error} />
    </div>
  );
}
