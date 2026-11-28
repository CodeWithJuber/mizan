import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { judge, pollOAuth, readConnectorPhase, readOAuthStatus, type OAuthSample, type PollEnd } from "./oauth";

describe("reading how a sign-in goes", () => {
  it("reads /oauth/status", () => {
    expect(readOAuthStatus({ state: "pending" })).toEqual({ state: "pending" });
    expect(readOAuthStatus({ state: "connected" })).toEqual({ state: "connected" });
    expect(readOAuthStatus({ state: "error", error: "access_denied" })).toEqual({ state: "error", error: "access_denied" });
    expect(readOAuthStatus({})).toEqual({ state: "pending" });
  });

  it("reads an older server's connector status, where auth_required means still signing in", () => {
    expect(readConnectorPhase("auth_required", null, true)).toEqual({ state: "pending" });
    expect(readConnectorPhase("auth_required", "expired", false)).toEqual({ state: "auth_required", error: "expired" });
    expect(readConnectorPhase("connecting", null, true)).toEqual({ state: "pending" });
    expect(readConnectorPhase("error", "boom", true)).toEqual({ state: "error", error: "boom" });
    expect(readConnectorPhase("connected", null, true)).toEqual({ state: "connected" });
  });

  it("ends on connected, error or auth_required, and after the last attempt", () => {
    expect(judge({ state: "connected" }, 1, 10)).toEqual({ outcome: "connected" });
    expect(judge({ state: "error", error: "x" }, 1, 10)).toEqual({ outcome: "error", error: "x" });
    expect(judge({ state: "auth_required" }, 1, 10)).toEqual({ outcome: "auth_required" });
    expect(judge({ state: "pending" }, 9, 10)).toBeNull();
    expect(judge({ state: "pending" }, 10, 10)).toEqual({ outcome: "timeout" });
  });
});

describe("pollOAuth", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  /** A check that answers the given samples in turn (the last one repeats). */
  function scripted(samples: (OAuthSample | Error)[]) {
    let call = 0;
    return vi.fn(async () => {
      const next = samples[Math.min(call++, samples.length - 1)];
      if (next instanceof Error) throw next;
      return next;
    });
  }

  it("asks every 2 s while pending and stops on connected", async () => {
    const check = scripted([{ state: "pending" }, { state: "pending" }, { state: "connected" }]);
    const ends: PollEnd[] = [];
    pollOAuth({ check, onEnd: (end) => ends.push(end) });
    expect(check).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2000);
    expect(check).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(4000);
    expect(check).toHaveBeenCalledTimes(3);
    expect(ends).toEqual([{ outcome: "connected" }]);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(check).toHaveBeenCalledTimes(3);
  });

  it("stops on error and on auth_required, saying why", async () => {
    for (const [sample, end] of [
      [{ state: "error", error: "denied" }, { outcome: "error", error: "denied" }],
      [{ state: "auth_required" }, { outcome: "auth_required" }],
    ] as [OAuthSample, PollEnd][]) {
      const check = scripted([{ state: "pending" }, sample]);
      const onEnd = vi.fn();
      pollOAuth({ check, onEnd });
      await vi.advanceTimersByTimeAsync(10_000);
      expect(onEnd).toHaveBeenCalledTimes(1);
      expect(onEnd).toHaveBeenCalledWith(end);
      expect(check).toHaveBeenCalledTimes(2);
    }
  });

  it("gives up after the last attempt", async () => {
    const check = scripted([{ state: "pending" }]);
    const onEnd = vi.fn();
    pollOAuth({ check, onEnd, maxAttempts: 3 });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(check).toHaveBeenCalledTimes(3);
    expect(onEnd).toHaveBeenCalledWith({ outcome: "timeout" });
  });

  it("rides out a failed check but stops after three in a row", async () => {
    const recovering = scripted([new Error("offline"), { state: "connected" }]);
    const first = vi.fn();
    pollOAuth({ check: recovering, onEnd: first });
    await vi.advanceTimersByTimeAsync(4000);
    expect(first).toHaveBeenCalledWith({ outcome: "connected" });

    const failing = scripted([new Error("offline")]);
    const second = vi.fn();
    pollOAuth({ check: failing, onEnd: second });
    await vi.advanceTimersByTimeAsync(20_000);
    expect(failing).toHaveBeenCalledTimes(3);
    expect(second).toHaveBeenCalledWith({ outcome: "error", error: "offline" });
  });

  it("stop() ends the asking without reporting an end", async () => {
    const check = scripted([{ state: "pending" }]);
    const onEnd = vi.fn();
    const stop = pollOAuth({ check, onEnd });
    await vi.advanceTimersByTimeAsync(2000);
    stop();
    await vi.advanceTimersByTimeAsync(20_000);
    expect(check).toHaveBeenCalledTimes(1);
    expect(onEnd).not.toHaveBeenCalled();
  });
});
