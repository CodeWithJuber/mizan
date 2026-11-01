"""Shared response defaults, without a global language or language detector."""

import json
import re

RESPONSE_POLICY = (
    "Honor explicit output languages in the current user request; otherwise match its "
    "natural language. Use saved language only when that is unclear. Quotes, code, history "
    "and host/tool context do not set reply language. Use a preferred greeting only when "
    "a greeting fits the request. Current requests for language, tone and format override saved/role "
    "defaults and heuristic guidance."
)

CURRENT_REQUEST_START = "[CURRENT USER REQUEST]"
CURRENT_REQUEST_END = "[END CURRENT USER REQUEST]"


def has_request_prose(task: str) -> bool:
    """Select whether the saved language default is inactive, without identifying a language.

    Any Unicode prose establishes a current language cue, including unsegmented
    scripts and short words such as 'ok' or 'continue'. For short prose the model
    can use the conversation, but we do not reissue an older language instruction.
    Code, URLs, quoted evidence, JSON and numbers alone retain the saved fallback.
    This only selects defaults; the actual task and evidence are never rewritten.
    """
    try:
        json.loads(task)
    except (ValueError, TypeError, RecursionError):
        pass
    else:
        return False
    prose = re.sub(r"(?s)```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)", " ", task)
    prose = re.sub(r"`[^`\n]*`", " ", prose)
    prose = re.sub(r"(?m)^[^\S\n]*>[^\n]*", " ", prose)
    prose = re.sub(r'"(?:\\.|[^"\\])*"|“[^”]*”|«[^»]*»|「[^」]*」|『[^』]*』', " ", prose)
    prose = re.sub(r"(?<!\w)'[^'\n]*'(?!\w)|‘[^’]*’", " ", prose)
    prose = re.sub(r"(?<![\w+.-])[a-zA-Z][a-zA-Z0-9+.-]*://\S+", " ", prose)
    prose = re.sub(r"(?i)(?<![\w.-])(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?", " ", prose)
    return any(character.isalpha() for character in prose)


def reply_defaults(task: str, preferences: list[dict]) -> list[dict]:
    """Do not offer an inactive saved language as a competing model instruction.

    Original owner-scoped records stay unchanged in storage and caller context.
    Every nonlanguage preference and its provenance remains part of the request.
    """
    if has_request_prose(task):
        return [preference for preference in preferences if preference.get("key") != "language"]
    return list(preferences)
