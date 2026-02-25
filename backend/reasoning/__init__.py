"""
MIZAN Reasoning Engine (Aql - عَقْل — Intellect)
===================================================

"Will you not use reason (Aql)?" — Quran 2:44

Advanced reasoning with Claude tool_use API,
ReAct loop, and Tafakkur self-correction.
"""

from .aql_engine import AqlEngine, ReasoningStep
from .planner import TafakkurPlanner, SubTask
from .context_manager import ContextManager
