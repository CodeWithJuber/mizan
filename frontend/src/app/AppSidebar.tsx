/**
 * The sidebar: a new chat, the six places, the person's chats (searchable,
 * grouped by date) and their account. On a phone it is a drawer.
 */
import { useDeferredValue, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Bot, Code2, Ellipsis, Library, LoaderCircle, LogOut, MessageSquare, Monitor, Moon, PencilLine,
  Settings, SquarePen, Sun, Trash2, Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader,
  SidebarInput, SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem, SidebarMenuSkeleton,
  SidebarRail, SidebarTrigger, useSidebar,
} from "@/components/ui/sidebar";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import { confirmDialog } from "../components/ui/confirm";
import { useTheme, type ThemeMode } from "../hooks/useTheme";
import { signOut, useMe } from "./auth";
import { useSocketStatus } from "../realtime/socket";
import { useChatActions } from "../features/chat/ChatProvider";
import { useChatSummary } from "../features/chat/liveStore";
import { chatTitle, groupChats, useChatSessions, type ChatSessionRow } from "../features/chat/sessions";
import { RenameDialog } from "../features/chat/RenameDialog";

const PLACES = [
  { to: "/chat", label: "Chat", icon: MessageSquare, match: "/chat" },
  { to: "/code", label: "Code", icon: Code2, match: "/code" },
  { to: "/agents", label: "Agents", icon: Bot, match: "/agents" },
  { to: "/library/memory", label: "Library", icon: Library, match: "/library" },
  { to: "/automations/watchers", label: "Automations", icon: Workflow, match: "/automations" },
  { to: "/settings/account", label: "Settings", icon: Settings, match: "/settings" },
];

function ChatItem({ row, active, running }: { row: ChatSessionRow; active: boolean; running: boolean }) {
  const actions = useChatActions();
  const navigate = useNavigate();
  const { setOpenMobile } = useSidebar();
  const [renaming, setRenaming] = useState(false);
  const title = chatTitle(row);
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        isActive={active}
        render={<NavLink to={`/chat/${encodeURIComponent(row.session_id)}`} onClick={() => setOpenMobile(false)} />}
        title={title}
      >
        <span className="truncate">{title}</span>
        {running && <LoaderCircle className="ml-auto size-3.5 shrink-0 animate-spin text-brand" aria-label="Answering" />}
      </SidebarMenuButton>
      <DropdownMenu>
        <DropdownMenuTrigger render={<SidebarMenuAction showOnHover aria-label={`Options for ${title}`} />}>
          <Ellipsis />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start" className="w-40">
          <DropdownMenuItem onClick={() => setRenaming(true)}>
            <PencilLine /> Rename
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onClick={async () => {
              if ((await actions.deleteSession(row.session_id)) && active) navigate("/chat");
            }}
          >
            <Trash2 /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <RenameDialog sessionId={row.session_id} current={title} open={renaming} onOpenChange={setRenaming} />
    </SidebarMenuItem>
  );
}

function ChatHistory() {
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search);
  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useChatSessions(query);
  const current = useChatSummary((state) => state.sessionId);
  const streaming = useChatSummary((state) => state.streaming);
  const { pathname } = useLocation();
  const onChat = pathname.startsWith("/chat");
  const rows = data?.pages.flatMap((page) => page.sessions) ?? [];
  const groups = groupChats(rows);
  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>Chats</SidebarGroupLabel>
      <SidebarGroupContent className="space-y-2">
        <SidebarInput
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search chats"
          aria-label="Search chats"
        />
        {isLoading ? (
          <SidebarMenu>
            {Array.from({ length: 5 }).map((_, index) => (
              <SidebarMenuItem key={index}><SidebarMenuSkeleton /></SidebarMenuItem>
            ))}
          </SidebarMenu>
        ) : rows.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">{query ? "No chat matches." : "No chats yet."}</p>
        ) : (
          groups.map((group) => (
            <div key={group.label}>
              <p className="px-2 pb-1 pt-2 text-[11px] font-medium text-muted-foreground">{group.label}</p>
              <SidebarMenu>
                {group.rows.map((row) => (
                  <ChatItem
                    key={row.session_id}
                    row={row}
                    active={onChat && row.session_id === current}
                    running={streaming && row.session_id === current}
                  />
                ))}
              </SidebarMenu>
            </div>
          ))
        )}
        {hasNextPage && (
          <Button variant="ghost" size="sm" className="w-full text-muted-foreground" onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage ? "Loading…" : "Show more"}
          </Button>
        )}
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

function AccountMenu() {
  const { data: me } = useMe();
  const { theme, setTheme } = useTheme();
  const status = useSocketStatus((state) => state.status);
  const navigate = useNavigate();
  const admin = me?.roles?.includes("admin");
  const { data: version } = useQuery({
    queryKey: ["health-version"],
    enabled: Boolean(admin),
    staleTime: 10 * 60_000,
    queryFn: async () => {
      const response = await authFetch(`${config.API_URL}/health`);
      const data = await response.json();
      return typeof data.version === "string" ? data.version : null;
    },
  });
  const live = status === "connected";
  const name = me?.username ?? "…";
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger render={<SidebarMenuButton size="lg" aria-label="Account and theme" />}>
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-medium text-brand">
              {name[0]?.toUpperCase()}
            </span>
            <span className="min-w-0 flex-1 text-left leading-tight">
              <span className="block truncate text-sm font-medium">{name}</span>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={`size-1.5 rounded-full ${live ? "bg-success" : status === "auth_required" ? "bg-destructive" : "bg-warning"}`} />
                {live ? "Connected" : status === "auth_required" ? "Signed out" : "Reconnecting…"}
              </span>
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-60">
            <DropdownMenuGroup>
              <DropdownMenuLabel>
                {name}
                {admin && <span className="ml-1.5 text-xs font-normal text-muted-foreground">administrator</span>}
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Theme</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as ThemeMode)}>
                <DropdownMenuRadioItem value="light"><Sun /> Light</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="dark"><Moon /> Dark</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="system"><Monitor /> Same as device</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/settings/account")}><Settings /> Settings</DropdownMenuItem>
            <DropdownMenuItem
              onClick={async () => {
                if (!(await confirmDialog({ title: "Sign out of MIZAN?", confirmLabel: "Sign out" }))) return;
                await authFetch(`${config.API_URL}/auth/logout`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: "{}",
                }).catch(() => undefined);
                signOut();
              }}
            >
              <LogOut /> Sign out
            </DropdownMenuItem>
            {version && (
              <p className="px-2 pb-1 pt-2 text-[11px] text-muted-foreground">MIZAN v{version}</p>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

export function AppSidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const actions = useChatActions();
  const current = useChatSummary((state) => state.sessionId);
  const hasMessages = useChatSummary((state) => state.hasMessages);
  const { setOpenMobile } = useSidebar();
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-1 pt-1">
          <NavLink to="/chat" className="flex min-w-0 items-center gap-2 group-data-[collapsible=icon]:hidden" aria-label="MIZAN home">
            <span className="font-arabic text-2xl leading-none text-brand" aria-hidden="true">ميزان</span>
            <span className="text-sm font-semibold tracking-wide">MIZAN</span>
          </NavLink>
          <SidebarTrigger className="ml-auto" />
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="New chat"
              className="border bg-background shadow-xs hover:bg-muted"
              onClick={() => {
                actions.startNewSession();
                navigate("/chat");
                setOpenMobile(false);
              }}
            >
              <SquarePen />
              <span>New chat</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {PLACES.map((place) => {
              const to = place.to === "/chat" && hasMessages ? `/chat/${encodeURIComponent(current)}` : place.to;
              return (
                <SidebarMenuItem key={place.to}>
                  <SidebarMenuButton
                    tooltip={place.label}
                    isActive={pathname.startsWith(place.match)}
                    render={<NavLink to={to} onClick={() => setOpenMobile(false)} />}
                  >
                    <place.icon />
                    <span>{place.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
        <ChatHistory />
      </SidebarContent>
      <SidebarFooter>
        <AccountMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
