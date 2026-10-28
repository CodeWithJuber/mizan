/** Sign in (or create an account). Where a signed-out visit lands. */
import { useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "../components/PasswordInput";
import { ApiError, useApi } from "../hooks/useApi";
import { signIn, useAuth } from "../app/auth";

function friendly(error: unknown, registering: boolean): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Wrong username or password.";
    if (error.status === 409) return "That username is taken.";
    if (error.status === 429) return "Too many attempts. Wait a minute and try again.";
    if (error.message) return error.message;
  }
  const message = error instanceof Error ? error.message : "";
  if (/failed to fetch|networkerror|load failed/i.test(message)) return "Can't reach the server.";
  return registering ? "The account could not be created." : "Sign in failed.";
}

export default function LoginPage() {
  const api = useApi();
  const token = useAuth((state) => state.token);
  const expired = useAuth((state) => state.expired);
  const [params] = useSearchParams();
  const next = params.get("next");
  const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (token) return <Navigate to={target} replace />;

  const submit = async () => {
    if (registering && password !== confirm) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const data = (await api.post(registering ? "/auth/register" : "/auth/login", { username, password })) as {
        token?: string;
        error?: string;
      };
      if (data.token) signIn(data.token);
      else setError(data.error || "Sign in failed.");
    } catch (failure) {
      setError(friendly(failure, registering));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="font-arabic text-5xl leading-none text-brand" aria-hidden="true">ميزان</div>
          <h1 className="mt-3 text-xl font-semibold tracking-tight">
            {registering ? "Create your MIZAN account" : "Sign in to MIZAN"}
          </h1>
          {expired && !registering && (
            <p className="mt-2 text-sm text-muted-foreground">Your session ended. Sign in again to continue.</p>
          )}
        </div>
        <form
          className="space-y-4 rounded-xl border bg-card p-5 shadow-xs"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <PasswordInput
              id="password"
              ariaLabel="Password"
              value={password}
              onChange={setPassword}
              autoComplete={registering ? "new-password" : "current-password"}
            />
          </div>
          {registering && (
            <div className="space-y-1.5">
              <Label htmlFor="confirm">Confirm password</Label>
              <PasswordInput id="confirm" ariaLabel="Confirm password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">{error}</p>
          )}
          <Button type="submit" className="h-10 w-full" disabled={busy || !username || !password}>
            {busy && <LoaderCircle className="animate-spin" />}
            {registering ? "Create account" : "Sign in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          {registering ? "Already have an account?" : "New here?"}{" "}
          <button
            type="button"
            className="font-medium text-brand underline-offset-4 hover:underline"
            onClick={() => {
              setRegistering((value) => !value);
              setError(null);
            }}
          >
            {registering ? "Sign in" : "Create an account"}
          </button>
        </p>
      </div>
    </main>
  );
}
