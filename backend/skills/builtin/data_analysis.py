"""
Data Analysis Skill
====================

Analyze CSV/JSON data with basic statistics.
"""

import csv
import io
import json

from ..base import SkillBase, SkillManifest


class DataAnalysisSkill(SkillBase):
    """Basic data analysis skill"""

    manifest = SkillManifest(
        name="data_analysis",
        version="1.0.0",
        description="Analyze data from CSV/JSON with basic statistics",
        permissions=["file:read:/tmp/mizan/*"],
        tags=["data", "analysis", "statistics"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._tools = {
            "analyze_csv": self.analyze_csv,
            "analyze_json": self.analyze_json,
        }

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "analyze_csv")
        if action == "analyze_csv":
            return await self.analyze_csv(params.get("data", ""))
        elif action == "analyze_json":
            return await self.analyze_json(params.get("data", ""))
        return {"error": f"Unknown action: {action}"}

    async def analyze_csv(self, data: str) -> dict:
        """Analyze CSV data"""
        try:
            reader = csv.DictReader(io.StringIO(data))
            rows = list(reader)

            if not rows:
                return {"error": "No data found"}

            columns = list(rows[0].keys())
            num_rows = len(rows)

            # Basic stats for numeric columns
            stats = {}
            for col in columns:
                values = []
                for row in rows:
                    try:
                        values.append(float(row[col]))
                    except (ValueError, TypeError):
                        continue

                if values:
                    stats[col] = {
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "mean": sum(values) / len(values),
                    }

            return {
                "rows": num_rows,
                "columns": columns,
                "numeric_stats": stats,
                "sample": rows[:3],
            }
        except Exception as e:
            return {"error": str(e)}

    async def analyze_json(self, data: str) -> dict:
        """Analyze JSON data"""
        try:
            parsed = json.loads(data)

            if isinstance(parsed, list):
                return {
                    "type": "array",
                    "length": len(parsed),
                    "sample": parsed[:3],
                    "item_type": type(parsed[0]).__name__ if parsed else "unknown",
                }
            elif isinstance(parsed, dict):
                return {
                    "type": "object",
                    "keys": list(parsed.keys()),
                    "num_keys": len(parsed),
                }
            else:
                return {"type": type(parsed).__name__, "value": str(parsed)[:500]}
        except Exception as e:
            return {"error": str(e)}

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "analyze_csv",
                "description": "Analyze CSV data and return basic statistics (row count, columns, numeric stats)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string", "description": "CSV data as a string"},
                    },
                    "required": ["data"],
                },
            },
            {
                "name": "analyze_json",
                "description": "Analyze JSON data structure and return type info and samples",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string", "description": "JSON data as a string"},
                    },
                    "required": ["data"],
                },
            },
        ]
