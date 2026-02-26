"""
Middleware Pipeline (Silsilah - سلسلة — Chain)
=================================================

"And hold firmly to the rope (chain) of Allah" — Quran 3:103

Middleware lets you intercept and process requests/responses
at the API level. Think of it as a chain of guards that each
request must pass through.

HOW TO USE:
    from core.middleware import middleware_pipeline

    # Add a middleware
    @middleware_pipeline.use("api")
    async def log_requests(request, next_handler):
        print(f"Request to {request['path']}")
        response = await next_handler(request)
        print(f"Response: {response['status']}")
        return response
"""

import logging
from typing import Any, Callable, Dict, List
from dataclasses import dataclass

logger = logging.getLogger("mizan.middleware")


@dataclass
class MiddlewareEntry:
    """A middleware handler in the pipeline."""
    callback: Callable
    name: str = ""
    pipeline: str = "api"
    priority: int = 0
    source: str = ""


class MiddlewarePipeline:
    """
    Middleware pipeline manager.

    Supports multiple named pipelines:
    - "api": HTTP request/response processing
    - "ws": WebSocket message processing
    - "agent": Agent task processing
    - "chat": Chat message processing
    """

    def __init__(self):
        self._pipelines: Dict[str, List[MiddlewareEntry]] = {}

    def use(self, pipeline: str = "api", name: str = "", priority: int = 0, source: str = ""):
        """Decorator to add middleware to a pipeline."""
        def decorator(func):
            entry = MiddlewareEntry(
                callback=func,
                name=name or func.__name__,
                pipeline=pipeline,
                priority=priority,
                source=source,
            )
            if pipeline not in self._pipelines:
                self._pipelines[pipeline] = []
            self._pipelines[pipeline].append(entry)
            self._pipelines[pipeline].sort(key=lambda e: e.priority, reverse=True)
            return func
        return decorator

    def add(self, pipeline: str, callback: Callable, name: str = "",
            priority: int = 0, source: str = ""):
        """Programmatic way to add middleware."""
        entry = MiddlewareEntry(
            callback=callback,
            name=name or callback.__name__,
            pipeline=pipeline,
            priority=priority,
            source=source,
        )
        if pipeline not in self._pipelines:
            self._pipelines[pipeline] = []
        self._pipelines[pipeline].append(entry)
        self._pipelines[pipeline].sort(key=lambda e: e.priority, reverse=True)

    def remove_from_source(self, source: str):
        """Remove all middleware from a specific source."""
        for pipeline in self._pipelines:
            self._pipelines[pipeline] = [
                e for e in self._pipelines[pipeline] if e.source != source
            ]

    async def execute(self, pipeline: str, data: Any, final_handler: Callable = None) -> Any:
        """
        Execute a middleware pipeline.

        Each middleware receives (data, next_handler) where next_handler
        calls the next middleware in the chain.
        """
        entries = self._pipelines.get(pipeline, [])

        async def create_chain(index: int):
            if index >= len(entries):
                # End of chain — call final handler or return data
                if final_handler:
                    return await final_handler(data)
                return data

            entry = entries[index]

            async def next_handler(modified_data=None):
                return await create_chain(index + 1)

            try:
                return await entry.callback(data, next_handler)
            except Exception as e:
                logger.error(f"[SILSILAH] Middleware error '{entry.name}': {e}")
                return await create_chain(index + 1)

        return await create_chain(0)

    def list_middleware(self) -> Dict[str, List[Dict]]:
        """List all registered middleware by pipeline."""
        result = {}
        for pipeline, entries in self._pipelines.items():
            result[pipeline] = [
                {"name": e.name, "priority": e.priority, "source": e.source}
                for e in entries
            ]
        return result


# ── Global Middleware Pipeline ──
middleware_pipeline = MiddlewarePipeline()
