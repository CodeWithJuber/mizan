"""
Plugin System (Wasilah - وسيلة — Means/Extension)
====================================================

"O you who believe, seek means (wasilah) of approach to Him" — Quran 5:35

A simple, powerful plugin system that lets anyone extend MIZAN
without touching core code.

HOW TO USE (for non-technical folks):
    1. Create a folder in plugins/ with your plugin name
    2. Add a plugin.json describing your plugin
    3. Add a main.py with your plugin class
    4. MIZAN loads it automatically on startup

EXAMPLE PLUGIN STRUCTURE:
    plugins/
    └── my_weather_plugin/
        ├── plugin.json       ← Plugin metadata
        └── main.py           ← Plugin code

EXAMPLE plugin.json:
    {
        "name": "my_weather_plugin",
        "version": "1.0.0",
        "description": "Adds weather lookup capability",
        "author": "Your Name",
        "permissions": ["network_access"],
        "hooks": ["agent.system_prompt"],
        "events": ["task.completed"]
    }

EXAMPLE main.py:
    from core.plugins import PluginBase

    class Plugin(PluginBase):
        async def on_load(self):
            # Register a hook
            self.add_hook("agent.system_prompt", self.add_weather_hint)
            # Listen to an event
            self.on_event("task.completed", self.log_completion)
            # Add a tool for agents to use
            self.add_tool("get_weather", self.get_weather, {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"]
                }
            })

        async def on_unload(self):
            pass  # Cleanup runs automatically

        async def add_weather_hint(self, data):
            data["prompt"] += "\\nYou can check weather using the get_weather tool."
            return data

        async def log_completion(self, data):
            print(f"Task done: {data}")

        async def get_weather(self, city: str):
            return {"weather": "sunny", "city": city, "temp": 25}
"""

import importlib
import importlib.util
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

from core.events import event_bus
from core.hooks import hook_registry

logger = logging.getLogger("mizan.plugins")


@dataclass
class PluginManifest:
    """Plugin metadata loaded from plugin.json."""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    permissions: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    enabled: bool = True
    min_mizan_version: str = ""
    tags: List[str] = field(default_factory=list)
    config_schema: Dict = field(default_factory=dict)


class PluginBase:
    """
    Base class for all MIZAN plugins.

    Every plugin gets:
    - Access to the event bus (emit/listen to events)
    - Access to the hook system (modify data flowing through the system)
    - Ability to register tools for agents to use
    - A config dict loaded from the plugin's settings
    - Automatic cleanup when unloaded

    Subclasses must implement:
    - on_load(): Called when plugin is loaded
    - on_unload(): Called when plugin is unloaded
    """

    def __init__(self, manifest: PluginManifest, config: Dict = None):
        self.manifest = manifest
        self.config = config or {}
        self._registered_hooks: List[tuple] = []
        self._registered_events: List[tuple] = []
        self._registered_tools: Dict[str, Dict] = {}

    async def on_load(self):
        """Called when the plugin is loaded. Override this."""
        pass

    async def on_unload(self):
        """Called when the plugin is unloaded. Override this."""
        pass

    # ── Helper methods for plugins ──

    def add_hook(self, hook_name: str, callback: Callable, priority: int = 0):
        """Register a hook handler. Automatically cleaned up on unload."""
        hook_registry.add_hook(hook_name, callback, priority=priority, source=self.manifest.name)
        self._registered_hooks.append((hook_name, callback))

    def on_event(self, event_pattern: str, callback: Callable, priority: int = 0):
        """Listen for an event. Automatically cleaned up on unload."""
        event_bus.add_listener(event_pattern, callback, priority=priority, source=self.manifest.name)
        self._registered_events.append((event_pattern, callback))

    async def emit(self, event_name: str, data: Dict = None):
        """Emit an event from this plugin."""
        await event_bus.emit(event_name, data or {}, source=self.manifest.name)

    def add_tool(self, name: str, handler: Callable, schema: Dict):
        """Register a tool that agents can use."""
        self._registered_tools[name] = {
            "handler": handler,
            "schema": schema,
        }

    def get_tools(self) -> Dict[str, Dict]:
        """Get all tools this plugin provides."""
        return self._registered_tools

    async def _cleanup(self):
        """Internal cleanup — removes all hooks and event listeners."""
        hook_registry.remove_all_from_source(self.manifest.name)
        event_bus.remove_all_from_source(self.manifest.name)
        self._registered_hooks.clear()
        self._registered_events.clear()
        self._registered_tools.clear()


class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.

    Directory structure:
        plugins/
        ├── my_plugin/
        │   ├── plugin.json    ← Required: metadata
        │   └── main.py        ← Required: Plugin class
        └── another_plugin/
            ├── plugin.json
            └── main.py
    """

    def __init__(self, plugins_dir: str = None):
        self.plugins_dir = plugins_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "plugins"
        )
        self._loaded: Dict[str, PluginBase] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._plugin_configs: Dict[str, Dict] = {}

    async def discover(self) -> List[PluginManifest]:
        """Discover all plugins in the plugins directory."""
        manifests = []

        if not os.path.exists(self.plugins_dir):
            os.makedirs(self.plugins_dir, exist_ok=True)
            logger.info(f"[WASILAH] Created plugins directory: {self.plugins_dir}")
            return manifests

        for entry in os.listdir(self.plugins_dir):
            plugin_path = os.path.join(self.plugins_dir, entry)
            manifest_path = os.path.join(plugin_path, "plugin.json")

            if os.path.isdir(plugin_path) and os.path.exists(manifest_path):
                try:
                    with open(manifest_path) as f:
                        data = json.load(f)
                    manifest = PluginManifest(**{
                        k: v for k, v in data.items()
                        if k in PluginManifest.__dataclass_fields__
                    })
                    if not manifest.name:
                        manifest.name = entry
                    self._manifests[manifest.name] = manifest
                    manifests.append(manifest)
                    logger.info(f"[WASILAH] Discovered plugin: {manifest.name} v{manifest.version}")
                except Exception as e:
                    logger.error(f"[WASILAH] Error reading {manifest_path}: {e}")

        return manifests

    async def load(self, plugin_name: str) -> bool:
        """Load and activate a plugin."""
        if plugin_name in self._loaded:
            logger.warning(f"[WASILAH] Plugin already loaded: {plugin_name}")
            return True

        manifest = self._manifests.get(plugin_name)
        if not manifest:
            logger.error(f"[WASILAH] Plugin not found: {plugin_name}")
            return False

        if not manifest.enabled:
            logger.info(f"[WASILAH] Plugin disabled: {plugin_name}")
            return False

        plugin_dir = os.path.join(self.plugins_dir, plugin_name)
        main_path = os.path.join(plugin_dir, "main.py")

        if not os.path.exists(main_path):
            logger.error(f"[WASILAH] No main.py in plugin: {plugin_name}")
            return False

        try:
            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}", main_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find the Plugin class
            plugin_cls = getattr(module, "Plugin", None)
            if not plugin_cls or not issubclass(plugin_cls, PluginBase):
                logger.error(f"[WASILAH] No valid Plugin class in {plugin_name}/main.py")
                return False

            # Create and load
            config = self._plugin_configs.get(plugin_name, {})
            plugin = plugin_cls(manifest=manifest, config=config)
            await plugin.on_load()

            self._loaded[plugin_name] = plugin
            logger.info(f"[WASILAH] Loaded plugin: {plugin_name} v{manifest.version}")

            # Emit event
            await event_bus.emit("plugin.loaded", {
                "name": plugin_name,
                "version": manifest.version,
            })

            return True

        except Exception as e:
            logger.error(f"[WASILAH] Failed to load plugin {plugin_name}: {e}")
            await event_bus.emit("plugin.error", {
                "name": plugin_name,
                "error": str(e),
            })
            return False

    async def unload(self, plugin_name: str) -> bool:
        """Unload and deactivate a plugin."""
        plugin = self._loaded.get(plugin_name)
        if not plugin:
            return False

        try:
            await plugin.on_unload()
            await plugin._cleanup()
            del self._loaded[plugin_name]

            await event_bus.emit("plugin.unloaded", {"name": plugin_name})
            logger.info(f"[WASILAH] Unloaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"[WASILAH] Error unloading {plugin_name}: {e}")
            return False

    async def reload(self, plugin_name: str) -> bool:
        """Reload a plugin (unload + load)."""
        await self.unload(plugin_name)
        return await self.load(plugin_name)

    async def load_all(self):
        """Discover and load all enabled plugins."""
        manifests = await self.discover()
        for manifest in manifests:
            if manifest.enabled:
                await self.load(manifest.name)

    async def unload_all(self):
        """Unload all plugins."""
        for name in list(self._loaded.keys()):
            await self.unload(name)

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """Get a loaded plugin instance."""
        return self._loaded.get(name)

    def get_all_tools(self) -> Dict[str, Dict]:
        """Get all tools from all loaded plugins."""
        tools = {}
        for plugin in self._loaded.values():
            tools.update(plugin.get_tools())
        return tools

    def get_all_tool_schemas(self) -> List[Dict]:
        """Get tool schemas from all loaded plugins."""
        schemas = []
        for plugin in self._loaded.values():
            for tool_info in plugin.get_tools().values():
                schemas.append(tool_info["schema"])
        return schemas

    def list_plugins(self) -> List[Dict]:
        """List all discovered plugins with their status."""
        result = []
        for name, manifest in self._manifests.items():
            result.append({
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "author": manifest.author,
                "enabled": manifest.enabled,
                "loaded": name in self._loaded,
                "permissions": manifest.permissions,
                "tags": manifest.tags,
            })
        return result

    def set_plugin_config(self, plugin_name: str, config: Dict):
        """Set configuration for a plugin."""
        self._plugin_configs[plugin_name] = config


# ── Global Plugin Manager ──
plugin_manager = PluginManager()
