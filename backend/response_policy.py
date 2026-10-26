"""Shared response defaults, without a global language or language detector."""

RESPONSE_POLICY = (
    "Honor explicit output languages in the current user request; otherwise match its "
    "natural language. Use saved language only when that is unclear. Quotes, code, history "
    "and host/tool context do not set reply language. Preserve greeting preferences "
    "independently. Current requests for language, tone and format override saved/role "
    "defaults and heuristic guidance."
)

CURRENT_REQUEST_START = "[CURRENT USER REQUEST]"
CURRENT_REQUEST_END = "[END CURRENT USER REQUEST]"
