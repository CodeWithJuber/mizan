"""In-chat command handlers for MIZAN"""

COMMANDS = {}


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
        count = len(await memory.recall("", limit=100))
        status["memories"] = count
    lines = ["**System Status:**", ""]
    for k, v in status.items():
        lines.append(f"  **{k}:** {v}")
    return "\n".join(lines)


@command("/new", "Start a new chat session")
async def cmd_new(session_id=None, sessions=None, **kwargs):
    if session_id and sessions and session_id in sessions:
        sessions[session_id] = {"history": []}
    return "Session cleared. Starting fresh conversation."


@command("/reset", "Reset agent state")
async def cmd_reset(agent=None, **kwargs):
    if agent:
        agent.state = "resting"
        agent.consecutive_errors = 0
    return "Agent state reset to resting."


@command("/model", "Switch AI model (usage: /model claude-sonnet-4-6)")
async def cmd_model(args="", agent=None, **kwargs):
    model_name = args.strip()
    if not model_name:
        current = agent.ai_model if agent else "unknown"
        return f"Current model: `{current}`\n\nUsage: `/model <model-name>`\nExamples: `/model claude-sonnet-4-6`, `/model gpt-4o`"
    if agent:
        agent.ai_model = model_name
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
async def cmd_compact(session_id=None, sessions=None, **kwargs):
    if not session_id or not sessions or session_id not in sessions:
        return "No active session to compact."
    history = sessions[session_id].get("history", [])
    if len(history) < 6:
        return "Session too short to compact (need at least 6 messages)."
    # Keep last 4 messages, summarize the rest
    older = history[:-4]
    summary = (
        f"[Previous conversation: {len(older)} messages about: "
        + ", ".join(set(m.get("content", "")[:30] + "..." for m in older[:5] if m.get("content")))
        + "]"
    )
    sessions[session_id]["history"] = [{"role": "system", "content": summary}] + history[-4:]
    return f"Compacted {len(older)} older messages into summary. Context preserved."


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
