/**
 * The message box. Everything that is not the message lives behind "+" and
 * shows as a small removable chip only when it differs from the default:
 * deep research, the permission mode, debug compare, a model for the next
 * message, an attached project. "/" opens commands and the person's skills;
 * images can be pasted or dropped.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUp, Bug, CircleCheck, FolderCode, Globe, ImagePlus, Plus, ShieldCheck, Sparkles, Square, Telescope, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { ChatAttachments } from "../../components/ChatAttachments";
import { VoiceInput } from "../../components/VoiceInput";
import { PERMISSION_LABELS, savePermissionMode } from "../../components/PermissionModeSwitch";
import { addToast } from "../../components/Toast";
import { useApi } from "../../hooks/useApi";
import { withHeard } from "../../utils/voice.ts";
import { CHAT_INPUT_LIMIT } from "../../utils/chatRecovery.ts";
import { allowedLabel, PERMISSION_MODES, type PermissionMode } from "../../utils/agentActivity";
import { useChatActions, useChatState } from "./ChatProvider";
import { PlanApproval, useAllowedAlways } from "./ChatControls";

const COMMANDS = [
  { name: "/help", description: "Show available commands" },
  { name: "/status", description: "Show system status" },
  { name: "/new", description: "Start a new chat" },
  { name: "/reset", description: "Reset agent state" },
  { name: "/model", description: "Switch AI model (e.g. /model claude-opus-5-5)" },
  { name: "/agents", description: "List available agents" },
  { name: "/compact", description: "Summarize older messages to save context" },
  { name: "/web_search", description: "Search the web for the rest of the message" },
];

const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const AUDIO_TYPES = ["audio/mpeg", "audio/wav", "audio/webm"];
const MAX_BYTES = 10 * 1024 ** 2;
const MAX_IMAGES = 4;

interface Skill {
  name: string;
  description?: string;
  enabled?: boolean;
}

function Chip({ icon: Icon, label, onRemove, to }: {
  icon: typeof Plus;
  label: string;
  onRemove?: () => void;
  to?: string;
}) {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded-full border bg-background pl-2.5 pr-1 text-xs text-muted-foreground">
      <Icon className="size-3.5 text-brand" />
      {to ? <Link to={to} className="hover:text-foreground hover:underline">{label}</Link> : <span>{label}</span>}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${label}`}
          className="inline-flex size-5 items-center justify-center rounded-full hover:bg-muted hover:text-foreground"
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  );
}

export function Composer() {
  const state = useChatState();
  const actions = useChatActions();
  const api = useApi();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const { input, streaming, attachedFiles, recovery } = state;
  const { allowed, revoke } = useAllowedAlways();

  useEffect(() => {
    actions.registerComposer(textareaRef.current);
    return () => actions.registerComposer(null);
  }, [actions]);

  // Keep the box sized to its text (up to a limit) whoever changes it.
  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
  }, [input]);

  const { data: skills = [] } = useQuery({
    queryKey: ["agent-skills"],
    staleTime: 5 * 60_000,
    queryFn: async () => ((await api.get("/agent-skills")).skills as Skill[] | undefined) ?? [],
  });

  const slashWord = input.startsWith("/") && !input.includes(" ") && !input.includes("\n") ? input.toLowerCase() : null;
  const slashItems = useMemo(() => {
    if (slashWord === null) return [];
    const commands = COMMANDS.filter((command) => command.name.startsWith(slashWord));
    const skillItems = skills
      .filter((skill) => skill.enabled !== false && `/${skill.name}`.toLowerCase().startsWith(slashWord))
      .map((skill) => ({ name: `/${skill.name}`, description: skill.description ?? "Skill", skill: true }));
    return [...commands.map((command) => ({ ...command, skill: false })), ...skillItems].slice(0, 12);
  }, [slashWord, skills]);
  const slashOpen = slashItems.length > 0 && !slashDismissed;
  useEffect(() => {
    setSlashIndex(0);
    if (slashWord === null) setSlashDismissed(false);
  }, [slashWord]);

  const addFiles = (files: File[]) => {
    const accepted: File[] = [];
    for (const file of files) {
      const image = IMAGE_TYPES.includes(file.type);
      const audio = AUDIO_TYPES.includes(file.type);
      if ((!image && !audio) || file.size > MAX_BYTES) {
        addToast({ type: "warning", title: "Choose a PNG, JPEG, WebP, GIF or audio file under 10 MB" });
        continue;
      }
      accepted.push(file);
    }
    if (!accepted.length) return;
    actions.setAttachedFiles((previous) => {
      const audio = accepted.filter((file) => file.type.startsWith("audio/"));
      // Audio goes alone over the media connection; images go up to four at a time.
      if (audio.length) return [audio[0]];
      const images = [...previous.filter((file) => file.type.startsWith("image/")), ...accepted];
      if (images.length > MAX_IMAGES) addToast({ type: "info", title: `Up to ${MAX_IMAGES} images per message` });
      return images.slice(0, MAX_IMAGES);
    });
  };

  const pickSlash = (name: string) => {
    actions.setInput(`${name} `);
    setSlashDismissed(true);
    textareaRef.current?.focus();
  };

  const hasSendable = input.trim().length > 0 || attachedFiles.length > 0;
  const overLimit = input.length > CHAT_INPUT_LIMIT;
  const costUnconfirmed = state.agentMode === "deep_research" && !state.deepResearchConfirmed;
  const sendDisabled = !hasSendable || recovery.blocked || overLimit || costUnconfirmed;
  const sendTitle = recovery.blocked
    ? "Check the previous run before sending"
    : overLimit ? `Messages are limited to ${CHAT_INPUT_LIMIT.toLocaleString()} characters`
      : costUnconfirmed ? "Confirm the deep research cost in + before sending"
        : hasSendable ? "Send message" : "Type a message to send";

  const chips = [
    state.agentMode === "deep_research" && (
      <Chip key="deep" icon={Telescope} label={state.deepResearchConfirmed ? "Deep research" : "Deep research · confirm cost in +"}
        onRemove={() => actions.setAgentMode("single")} />
    ),
    state.permissionMode !== "auto_edits" && (
      <Chip key="mode" icon={ShieldCheck} label={PERMISSION_LABELS[state.permissionMode].title}
        onRemove={() => {
          savePermissionMode("auto_edits");
          actions.setPermissionMode("auto_edits");
        }} />
    ),
    state.debugAllowed && state.debugOn && (
      <Chip key="debug" icon={Bug} label="Debug compare" onRemove={actions.toggleDebug} />
    ),
    state.chatModelOverride && (
      <Chip key="model" icon={Sparkles} label={state.chatModelOverride} onRemove={() => actions.setChatModelOverride("")} />
    ),
    state.workspaceId && (
      <Chip key="project" icon={FolderCode} label="Project attached" to={`/code/${encodeURIComponent(state.workspaceId)}`}
        onRemove={() => actions.selectWorkspace("")} />
    ),
    ...allowed.map((item) => (
      <Chip key={`always-${item.tool}`} icon={CircleCheck} label={`Always: ${allowedLabel(item.tool)}`}
        onRemove={() => void revoke(item.tool)} />
    )),
  ].filter(Boolean);

  return (
    <div className="bg-background px-3 pb-3 pt-1 sm:px-4 sm:pb-4">
      <div className="mx-auto max-w-3xl">
        <PlanApproval />
        {chips.length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{chips}</div>}

        <div
          className={cn(
            "relative rounded-2xl border bg-card shadow-xs transition-colors focus-within:border-ring/70 focus-within:ring-3 focus-within:ring-ring/15",
            dragging && "border-ring ring-3 ring-ring/25",
          )}
          onDragOver={(event) => {
            if (event.dataTransfer.types.includes("Files")) {
              event.preventDefault();
              setDragging(true);
            }
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            addFiles(Array.from(event.dataTransfer.files));
          }}
        >
          {slashOpen && (
            <div className="absolute inset-x-0 bottom-full z-30 mb-2 overflow-hidden rounded-xl border bg-popover shadow-lg">
              <Command shouldFilter={false} value={slashItems[slashIndex]?.name} className="rounded-xl">
                <CommandList className="max-h-72">
                  <CommandEmpty>No command</CommandEmpty>
                  <CommandGroup heading="Commands and skills">
                    {slashItems.map((item) => (
                      <CommandItem key={item.name} value={item.name} onSelect={() => pickSlash(item.name)}
                        onMouseEnter={() => setSlashIndex(slashItems.indexOf(item))}>
                        {item.skill ? <Sparkles className="text-brand" /> : <span className="w-4 text-center font-mono text-brand">/</span>}
                        <span className="font-mono text-sm">{item.name}</span>
                        <span className="ml-2 truncate text-xs text-muted-foreground">{item.description}</span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </div>
          )}

          {attachedFiles.length > 0 && (
            <div className="px-3 pt-3">
              <ChatAttachments
                files={attachedFiles}
                onRemove={(index) => actions.setAttachedFiles((previous) => previous.filter((_, i) => i !== index))}
              />
            </div>
          )}

          <textarea
            ref={textareaRef}
            dir="auto"
            rows={1}
            value={input}
            placeholder="Message MIZAN…"
            aria-label="Message MIZAN"
            className="block max-h-60 min-h-[52px] w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-[15px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
            onChange={(event) => actions.setInput(event.target.value)}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith("image/"));
              if (files.length) {
                event.preventDefault();
                addFiles(files);
              }
            }}
            onKeyDown={(event) => {
              if (slashOpen) {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setSlashIndex((index) => (index + 1) % slashItems.length);
                  return;
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setSlashIndex((index) => (index - 1 + slashItems.length) % slashItems.length);
                  return;
                }
                if (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey)) {
                  event.preventDefault();
                  pickSlash(slashItems[slashIndex].name);
                  return;
                }
                if (event.key === "Escape") {
                  event.preventDefault();
                  setSlashDismissed(true);
                  return;
                }
              }
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (!sendDisabled && !streaming) void actions.sendMessage();
              }
            }}
          />

          <div className="flex items-center gap-1 px-2 pb-2">
            <Popover open={menuOpen} onOpenChange={setMenuOpen}>
              <PopoverTrigger
                render={<Button variant="ghost" size="icon" aria-label="Attach and options" className="rounded-full text-muted-foreground" />}
              >
                <Plus />
              </PopoverTrigger>
              <PopoverContent side="top" align="start" className="w-80 p-0">
                <div className="p-1">
                  <button
                    type="button"
                    className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left text-sm hover:bg-muted"
                    onClick={() => {
                      setMenuOpen(false);
                      fileRef.current?.click();
                    }}
                  >
                    <ImagePlus className="size-4 text-muted-foreground" /> Attach images or audio
                  </button>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left text-sm hover:bg-muted"
                    onClick={() => {
                      setMenuOpen(false);
                      actions.setInput((previous) => (previous.startsWith("/web_search") ? previous : `/web_search ${previous}`));
                      textareaRef.current?.focus();
                    }}
                  >
                    <Globe className="size-4 text-muted-foreground" /> Search the web
                  </button>
                </div>
                <div className="space-y-2 border-t p-3">
                  <div className="flex items-center justify-between gap-3">
                    <Label htmlFor="deep-research" className="flex items-center gap-2 font-normal">
                      <Telescope className="size-4 text-muted-foreground" /> Deep research
                    </Label>
                    <Switch
                      id="deep-research"
                      checked={state.agentMode === "deep_research"}
                      disabled={streaming}
                      onCheckedChange={(checked) => actions.setAgentMode(checked ? "deep_research" : "single")}
                    />
                  </div>
                  {state.agentMode === "deep_research" && (
                    <label className="flex cursor-pointer items-start gap-2 rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={state.deepResearchConfirmed}
                        onChange={(event) => actions.setDeepResearchConfirmed(event.target.checked)}
                        className="mt-0.5 accent-(--primary)"
                      />
                      <span>
                        Runs a multi-step pipeline (planner → workers → aggregator → verifier) that uses extra model
                        budget. I confirm this request.
                      </span>
                    </label>
                  )}
                </div>
                <div className="space-y-2 border-t p-3">
                  <p className="text-xs font-medium text-muted-foreground">What MIZAN may do without asking</p>
                  <RadioGroup
                    value={state.permissionMode}
                    onValueChange={(value) => {
                      const mode = value as PermissionMode;
                      savePermissionMode(mode);
                      actions.setPermissionMode(mode);
                    }}
                    disabled={streaming}
                    className="gap-1.5"
                  >
                    {PERMISSION_MODES.map((mode) => (
                      <label key={mode} className="flex cursor-pointer items-start gap-2 rounded-md p-1 hover:bg-muted/60">
                        <RadioGroupItem value={mode} className="mt-0.5" />
                        <span className="min-w-0">
                          <span className="block text-sm">{PERMISSION_LABELS[mode].title}</span>
                          <span className="block text-xs text-muted-foreground">{PERMISSION_LABELS[mode].hint}</span>
                        </span>
                      </label>
                    ))}
                  </RadioGroup>
                </div>
                <div className="space-y-2 border-t p-3">
                  <Label htmlFor="model-override" className="text-xs font-medium text-muted-foreground">
                    Model for the next message (optional)
                  </Label>
                  <Input
                    id="model-override"
                    placeholder="e.g. claude-opus-5-5"
                    value={state.chatModelOverride}
                    onChange={(event) => actions.setChatModelOverride(event.target.value.trim())}
                  />
                  {state.debugAllowed && (
                    <div className="flex items-center justify-between gap-3 pt-1">
                      <Label htmlFor="debug-compare" className="flex items-center gap-2 font-normal">
                        <Bug className="size-4 text-muted-foreground" /> Debug compare
                      </Label>
                      <Switch id="debug-compare" checked={state.debugOn} onCheckedChange={actions.toggleDebug} />
                    </div>
                  )}
                </div>
              </PopoverContent>
            </Popover>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept={[...IMAGE_TYPES, ...AUDIO_TYPES].join(",")}
              className="hidden"
              onChange={(event) => {
                addFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />

            <div className="flex-1" />
            {overLimit && (
              <span role="alert" className="mr-1 text-xs text-destructive">
                {input.length.toLocaleString()} / {CHAT_INPUT_LIMIT.toLocaleString()}
              </span>
            )}
            <VoiceInput
              sessionId={state.sessionId}
              disabled={streaming}
              onHeard={(words) => {
                actions.setInput((previous) => withHeard(previous, words));
                textareaRef.current?.focus();
              }}
            />
            {streaming ? (
              <Button size="icon" className="rounded-full bg-foreground text-background hover:bg-foreground/85"
                onClick={actions.stopGeneration} aria-label="Stop generating" title="Stop generating">
                <Square className="size-3.5 fill-current" />
              </Button>
            ) : (
              <Button size="icon" className="rounded-full" disabled={sendDisabled}
                onClick={() => void actions.sendMessage()} aria-label="Send message" title={sendTitle}>
                <ArrowUp />
              </Button>
            )}
          </div>
        </div>
        <p className="mt-1.5 hidden text-center text-[11px] text-muted-foreground sm:block">
          Enter to send · Shift+Enter for a new line · / for commands · MIZAN can be wrong; check what matters.
        </p>
      </div>
    </div>
  );
}
