"""In-chat command handlers for MIZAN"""

COMMANDS: dict = {}


def command(name, description):
    """Decorator to register a command"""

    def decorator(func):
        COMMANDS[name] = {"handler": func, "description": description}
        return func

    return decorator


@command("/help", "Show available commands")
async def cmd_help(**kwargs):
    lines = ["**Available Commands:**", ""]
    for name, info in sorted(COMMANDS.items()):
        lines.append(f"  `{name}` — {info['description']}")
    return "\n".join(lines)


@command("/status", "Show system status")
async def cmd_status(agent=None, session_id=None, memory=None, **kwargs):
    status = {
        "agent": agent.name if agent else "none",
        "model": agent.ai_model if agent else "none",
        "state": agent.state if agent else "unknown",
        "nafs_level": agent.nafs_level if agent else 0,
        "session": session_id or "none",
    }
    if memory:
        from security.auth import current_user_id

        status.update(await memory.conversation_counts(current_user_id() or ""))
        status["conversation_recall"] = "recent and relevant owned user statements"
    status["response_provider"] = getattr(
        getattr(agent, "ai_client", None), "provider_name", "unavailable"
    )
    from mizan_owned.learning_service import configured_root, learning_service

    status["owned_learning_configured"] = configured_root() is not None
    status["automatic_weight_training"] = (
        "watching for approved original-data bundles"
        if learning_service.automation_active
        else "disabled"
    )
    status["owned_learning_worker_busy"] = learning_service.busy
    status["chat_capture"] = "unreviewed candidates; does not update model weights"
    status["architecture_metrics"] = "software heuristics, not AGI or verified correctness"
    lines = ["**System Status:**", ""]
    for k, v in status.items():
        lines.append(f"  **{k}:** {v}")
    return "\n".join(lines)


@command("/new", "Start a new chat session")
async def cmd_new(session_id=None, sessions=None, **kwargs):
    if session_id and sessions and session_id in sessions:
        sessions.setdefault(session_id, {})["history"] = []
    return "Session cleared. Starting fresh conversation."


@command("/reset", "Reset agent state")
async def cmd_reset(agent=None, **kwargs):
    if agent:
        agent.state = "resting"
        agent.consecutive_errors = 0
    return "Agent state reset to resting."


@command("/model", "Switch AI model (usage: /model claude-opus-5-5)")
async def cmd_model(args="", agent=None, **kwargs):
    model_name = args.strip()
    if not model_name:
        current = agent.ai_model if agent else "unknown"
        return f"Current model: `{current}`\n\nUsage: `/model <model-name>`\nExamples: `/model claude-opus-5-5`, `/model claude-sonnet-5-5`, `/model gpt-6.1-sol`"
    if agent:
        from mizan_owned.provider import owned_only
        from providers import create_provider, normalize_model_for_provider

        if owned_only() or getattr(agent.ai_client, "provider_name", "") == "mizan-owned":
            return "Owned mode is active. OpenRouter support must be requested separately."
        provider = create_provider(model=model_name)
        if provider is None:
            return "Requested provider is unavailable. Configure it in AI Providers first."
        model_name = normalize_model_for_provider(model_name, provider.provider_name)
        agent.ai_model, agent.ai_client = model_name, provider
        return f"Switched to model: `{model_name}`"
    return "No agent available to switch model."


@command("/agents", "List available agents")
async def cmd_agents(active_agents=None, **kwargs):
    if not active_agents:
        return "No agents available."
    lines = ["**Available Agents:**", ""]
    for _aid, agent in active_agents.items():
        lines.append(f"  **{agent.name}** ({agent.role}) — {agent.state}")
    return "\n".join(lines)


@command("/compact", "Summarize older messages to save context")
async def cmd_compact(session_id=None, memory=None, agent=None, **kwargs):
    """Fold the whole session into its persisted running summary."""
    if not session_id or memory is None or not hasattr(memory, "get_session_summary"):
        return "No active session to compact."
    from providers import effective_limits
    from reasoning.context_engine import ContextEngine, agent_summarizer, estimate_tokens

    window, _ = effective_limits(
        getattr(agent, "ai_client", None), getattr(agent, "ai_model", "") or ""
    )
    summary = await ContextEngine(memory).compact_now(
        session_id, agent_summarizer(agent) if agent is not None else None, window
    )
    if not summary:
        return "Nothing to compact yet."
    return (
        f"Compacted this conversation into a running summary (~{estimate_tokens(summary)} "
        "tokens). Earlier turns stay saved and are now sent as that summary."
    )


@command("/web_search", "Search the web (usage: /web_search your query)")
async def cmd_web_search(args="", **kwargs):
    """Search the web using DuckDuckGo via the web_browse skill."""
    query = args.strip()
    if not query:
        return "Usage: /web_search your search query"
    try:
        from skills.builtin.web_browse import WebBrowseSkill

        skill = WebBrowseSkill()
        result = await skill.search(query)
        if "error" in result:
            return f"Search failed: {result['error']}"
        results = [r for r in result.get("results", []) if isinstance(r, dict)][:10]
        if not results:
            return f"No results found for '{query}'."
        lines = [f"**Web search results for '{query}':**", ""]
        for i, item in enumerate(results, 1):
            title = str(item.get("title") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip()
            line = f"{i}. [{title}]({url})" if url else f"{i}. {title}"
            snippet = str(item.get("snippet") or "").strip()
            lines.append(f"{line}\n   {snippet[:240]}" if snippet else line)
        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


async def handle_command(content: str, **context) -> dict:
    """Parse and execute a chat command. Returns {is_command, response}"""
    if not content.startswith("/"):
        return {"is_command": False}

    parts = content.split(maxsplit=1)
    cmd_name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd_name not in COMMANDS:
        return {
            "is_command": True,
            "response": f"Unknown command: `{cmd_name}`. Type `/help` for available commands.",
        }

    handler = COMMANDS[cmd_name]["handler"]
    result = await handler(args=args, **context)
    return {"is_command": True, "response": result}
