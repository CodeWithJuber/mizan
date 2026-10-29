import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { addToast } from "../components/Toast";
import { useAuth, useIsAdmin, useMe } from "./auth";

/** Signed-out visits go to /login and come back here after. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((state) => state.token);
  const expired = useAuth((state) => state.expired);
  const location = useLocation();
  useEffect(() => {
    if (!token && expired) addToast({ type: "error", title: "Session expired — please sign in again" });
  }, [token, expired]);
  if (!token) {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}

/** Administrator pages; others are sent to their own settings. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { isLoading } = useMe();
  const admin = useIsAdmin();
  if (isLoading) return null;
  if (!admin) return <Navigate to="/settings/account" replace />;
  return <>{children}</>;
}
