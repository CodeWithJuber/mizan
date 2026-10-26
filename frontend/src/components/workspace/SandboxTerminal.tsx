/** Interactive shell in the project's sandbox session (xterm.js over a WebSocket). */
import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { config } from "../../config";

interface Props {
  workspaceId: string;
  onClosed: () => void;
}

export default function SandboxTerminal({ workspaceId, onClosed }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const closedRef = useRef(onClosed);
  closedRef.current = onClosed;
  const [state, setState] = useState<"connecting" | "open" | "closed">("connecting");

  useEffect(() => {
    if (!host.current) return;
    const dark = document.documentElement.classList.contains("dark");
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 12,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      theme: dark ? { background: "#09090b" } : { background: "#18181b", foreground: "#f4f4f5" },
      scrollback: 3000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host.current);
    fit.fit();
    const token = localStorage.getItem("mizan_token") ?? "";
    // The token travels as a subprotocol so it never appears in URLs or access logs.
    const socket = new WebSocket(
      `${config.WS_URL}/workspaces/${encodeURIComponent(workspaceId)}/terminal?cols=${term.cols}&rows=${term.rows}`,
      ["mizan.terminal", `bearer.${token}`],
    );
    socket.binaryType = "arraybuffer";
    const encoder = new TextEncoder();
    socket.onopen = () => {
      setState("open");
      term.focus();
    };
    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) term.write(new Uint8Array(event.data));
      else term.write(String(event.data));
    };
    socket.onclose = (event) => {
      setState("closed");
      term.write(`\r\n\x1b[90m[terminal closed${event.reason ? `: ${event.reason}` : ""}]\x1b[0m\r\n`);
      closedRef.current();
    };
    const input = term.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(encoder.encode(data));
    });
    const resize = term.onResize(({ cols, rows }) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "resize", cols, rows }));
    });
    const observer = new ResizeObserver(() => {
      try { fit.fit(); } catch { /* hidden panel */ }
    });
    observer.observe(host.current);
    return () => {
      observer.disconnect();
      input.dispose();
      resize.dispose();
      socket.onclose = null;
      socket.close();
      term.dispose();
    };
  }, [workspaceId]);

  return (
    <div className="space-y-1">
      <p className="text-2xs text-gray-500" role="status">
        {state === "connecting" ? "Connecting to the sandbox…" : state === "open" ? "Connected · files sync when you press Sync" : "Disconnected"}
      </p>
      <div ref={host} className="h-64 rounded-lg overflow-hidden bg-zinc-900 p-1" aria-label="Sandbox terminal" />
    </div>
  );
}
