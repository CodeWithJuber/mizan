"""Connectors: Model Context Protocol (MCP) servers each user adds to MIZAN.

A user connects remote MCP servers (Streamable HTTP, with OAuth or headers)
or local stdio servers. Their tools join the agent's own tool flow as
``mcp__<server>__<tool>`` and pass through the same Fitrah, Izn (permission
and approvals), Wali and Yaqin checks as built-in tools.
"""
