"""
Hello World Plugin — Your First MIZAN Plugin!
================================================

This is a simple example showing how to build a MIZAN plugin.
Copy this folder to create your own plugin!

What this plugin does:
1. Adds a friendly greeting to the agent's system prompt
2. Logs when tasks are completed
3. Provides a "greet" tool that agents can use
"""

from core.plugins import PluginBase


class Plugin(PluginBase):
    """
    Every plugin must have a class called 'Plugin' that extends PluginBase.

    You get these helper methods:
    - self.add_hook(name, callback)     → Modify data flowing through the system
    - self.on_event(name, callback)     → React to things that happen
    - self.add_tool(name, handler, schema) → Give agents new abilities
    - self.emit(name, data)             → Tell other parts something happened
    - self.config                       → Your plugin's configuration
    - self.manifest                     → Your plugin.json data
    """

    async def on_load(self):
        """Called when your plugin is loaded. Set up everything here."""

        # 1. Add a hook that modifies the system prompt
        self.add_hook("agent.system_prompt", self.customize_prompt)

        # 2. Listen for task completion events
        self.on_event("task.completed", self.on_task_done)

        # 3. Register a tool that agents can use
        self.add_tool("greet", self.greet_tool, {
            "name": "greet",
            "description": "Send a friendly greeting to someone",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the person to greet",
                    }
                },
                "required": ["name"],
            },
        })

        print(f"[Hello World Plugin] Loaded! v{self.manifest.version}")

    async def on_unload(self):
        """Called when your plugin is unloaded. Clean up here."""
        print("[Hello World Plugin] Goodbye!")

    async def customize_prompt(self, data):
        """
        This hook modifies the system prompt before it's sent to the LLM.

        'data' is a dict with a 'prompt' key. Modify it and return it.
        """
        data["prompt"] += "\nYou are extra friendly and helpful today!"
        return data

    async def on_task_done(self, data):
        """
        This event handler is called whenever a task completes.

        'data' contains info about the completed task.
        """
        agent = data.get("agent_name", "Unknown")
        print(f"[Hello World Plugin] Task completed by {agent}!")

    async def greet_tool(self, name: str) -> dict:
        """
        This tool can be called by any agent.

        When an agent decides to use the "greet" tool, this function runs.
        """
        greeting = f"Hello, {name}! Welcome to MIZAN! 🌟"
        return {"greeting": greeting, "plugin": "hello_world"}
