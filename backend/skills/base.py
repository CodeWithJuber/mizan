"""
Skill Base Class
=================

Every skill must implement this interface.
Skills declare their permissions upfront (like Android manifest).
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class SkillManifest:
    """Skill metadata and permission declaration"""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    permissions: List[str] = field(default_factory=list)
    # Permission format: "category:action:scope"
    # Examples:
    # - "file:read:/tmp/mizan/*"
    # - "network:https://*.api.com"
    # - "shell:git"
    # - "memory:read:*"
    tags: List[str] = field(default_factory=list)
    enabled: bool = True


class SkillBase(ABC):
    """
    Base class for all MIZAN skills.
    Subclasses must implement execute() and define a manifest.
    """

    manifest: SkillManifest = SkillManifest()

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._tools: Dict[str, Callable] = {}

    @abstractmethod
    async def execute(self, params: Dict, context: Dict = None) -> Dict:
        """Execute the skill with given parameters"""
        pass

    def get_tools(self) -> Dict[str, Callable]:
        """Return tools this skill provides to agents"""
        return self._tools

    def get_tool_schemas(self) -> List[Dict]:
        """Return Claude tool_use schemas for this skill's tools"""
        return []

    def validate_params(self, params: Dict) -> bool:
        """Validate parameters before execution"""
        return True
