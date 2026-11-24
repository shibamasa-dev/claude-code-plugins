"""Judge for decision-capture: does an assistant reply ask the user, in prose, to make a decision?

asks_decision(text, backend) looks at the last TAIL_CHARS of the reply and returns a Verdict.

Backends:
  regex    : local patterns, sends nothing anywhere (the default, and the fallback of the others)
  openai   : OpenAI Decisions API, a 4-way `choice` question; the score is the probability of `decide`
  typesafe : TypeSafe (Jev) API, a yes/no `noul` question; the score is the probability of yes
  google   : Gemini Decisions API, the same 4-way `choice` question as openai
A model backend sends only that tail, and only when a loose pre-filter (maybe_asks) matches, so most Stops never call
out. A missing key, a timeout, an HTTP error or a response of another shape falls back to regex, and the Verdict says
so (fell_back, error). The scores are not comparable across vendors, so each has its own threshold (THRESHOLDS); how
each was measured is in the plugin README.
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

BACKENDS = ("regex", "openai", "typesafe", "google")
TAIL_CHARS = 1500  # the question sits at the end of a reply; this also limits what a model backend is sent
TIMEOUT = 2.0      # runs on every judged Stop

# Default threshold per vendor. A reply is judged to ask when the score is at least this
THRESHOLDS = {"openai": 0.9, "typesafe": 0.97, "google": 0.8}

OPENAI_URL = "https://api.openai.com/v1/decisions"
OPENAI_MODEL = "gpt-6-luna"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-latest"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
GOOGLE_MODEL = "gemini-decision-1"


@dataclass
class Verdict:
    asks: bool
    score: Optional[float]
    backend: str                 # the backend that answered
    fell_back: bool = False      # a model backend failed and regex answered
    error: Optional[str] = None


class JudgeError(Exception):
    pass


def tail(text):
    return (text or "")[-TAIL_CHARS:]


def looks_like_machine_output(text):
    """The whole reply is one JSON value or one code fence (judged on the whole text: a cut tail no longer parses)."""
    s = (text or "").strip()
    if s.startswith("```") and s.endswith("```") and s.count("```") == 2:
        return True
    if s[:1] in "{[":
        try:
            return isinstance(json.loads(s), (dict, list))
        except ValueError:
            return False
    return False


# ------------------------------------------------------------------ regex
# Strict forms only: a sentence that explicitly asks the user to choose, approve or decide. Looked for in the last
# STRICT_TAIL_LINES non-empty lines, so a question quoted earlier in a report does not count.
_STRICT_PATTERNS = [
    # Japanese: "may I ...?", "shall I ...?", "which one ...?", "please decide / approve", "waiting for your answer"
    r"(てよい|でよい|ていい|でいい|て良い|で良い|てもいい|てもよい|てかまわない)(ですか|でしょうか|か)?\s*[？?]",
    r"(しますか|しましょうか|進めますか|やりますか|続けますか|にしますか)\s*[？?]",
    r"(どちら|どっち|どれ)(に|で|から)?(する|しますか|進めますか|にする)?\s*[？?]",
    r"(判断|承認|ご判断|ご承認)(を|が)?(して|お願い|ください|ほしい|欲しい|お待ちしています|いただけますか)",
    r"決めて(ください|ほしい|欲しい)",
    r"(返事|ご返事|お返事|回答)をお待ちしています",
    r"(GO|OK)\s*を?ください",
    # English
    r"\b(shall I|should I|may I|can I go ahead|do you want me to|would you like me to)\b",
    r"\bwhich (one|option|approach)\b[^.\n]{0,60}\?",
    r"\b(ok|okay) to (proceed|merge|delete|go ahead|continue)\b[^.\n]{0,40}\?",
    r"\bplease (decide|choose|pick|approve|confirm which)\b",
    r"\bA or B\?",
]
_STRICT_RE = re.compile("|".join(_STRICT_PATTERNS), re.I)
STRICT_TAIL_LINES = 6

# Loose pre-filter for the model backends: a reply that does not match is never sent out. Wider than the strict
# patterns on purpose, since a reply it drops is a miss.
_MAYBE_RE = re.compile(
    r"[？?]|か。|か$|ください|ほしい|欲しい|お待ち|待ち|判断|決め|承認|よければ|良ければ|言って|一言|指示|いかが"
    r"|\b(should|shall|would you|which|waiting|let me know|go-ahead|approve|decide)\b", re.I | re.M)


def maybe_asks(text):
    t = tail(text)
    return bool(t.strip()) and not looks_like_machine_output(text) and bool(_MAYBE_RE.search(t))


def regex_asks(text):
    t = tail(text)
    if not t.strip() or looks_like_machine_output(text):
        return Verdict(False, 0.0, "regex")
    lines = [ln for ln in t.splitlines() if ln.strip()]
    hit = bool(_STRICT_RE.search("\n".join(lines[-STRICT_TAIL_LINES:])))
    return Verdict(hit, 1.0 if hit else 0.0, "regex")


# ------------------------------------------------------------- questions
ASK_INSTRUCTIONS = (
    "The state is the final message an AI coding assistant wrote to its user before stopping. Does this message ask "
    "the user to make a decision (choose between options, approve or reject a proposed action, or set a direction) "
    "such that the assistant's next step depends on the answer?"
)
ASK_CRITERIA = {
    "true": "It ends by asking the user to choose, approve, or decide (e.g. 'shall I proceed?', 'A or B?', "
            "'please decide', 'may I delete these?'), including re-listing decisions still awaiting the answer.",
    "false": "A completion or progress report, an explanation, a request for facts or for the user to perform a "
             "manual task, an offer with no question ('tell me if you need X'), a mere statement that merging is "
             "the user's call, or machine output such as JSON.",
}
# Asked as a 4-way choice rather than yes/no: a single yes/no question gave scores stuck at 0 or 1, which no threshold
# could tune. The question asks what the reply needs from the user to continue, and `decide` covers a table of open
# decisions with recommendations and a request placed mid-message before status notes.
CHOICE_INSTRUCTIONS = (
    "The input is the final message an AI coding assistant wrote to its user before it stopped and waited. "
    "What does this message ask the user to do before the assistant can continue?"
)
CHOICES = {
    "decide": "Make a decision the assistant is waiting on: choose between options, approve or reject a proposed "
              "action, or set a direction (e.g. 'shall I proceed?', 'A or B?', 'may I delete these?'), including a "
              "list or table of open decisions with recommendations that the user is asked to answer (e.g. 'tell me "
              "if all as recommended is fine', 'once you answer I will pass it on'). The request may sit in the "
              "middle of the message, followed by status notes.",
    "inform": "Provide facts or information the assistant lacks (e.g. 'what is the client name?', 'please answer "
              "these hearing items').",
    "act": "Perform a manual task (e.g. run a command, check a phone, click a button).",
    "nothing": "Nothing: a completion or progress report, an explanation, or an offer without a question.",
}


# ------------------------------------------------------------- backends
def _post(url, headers, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise JudgeError(f"HTTP {e.code}") from None
    except Exception as e:  # timeout, DNS, broken JSON
        raise JudgeError(type(e).__name__) from None


def openai_score(text, key, timeout):
    """OpenAI Decisions: questions is a list; the answer's probabilities is a list of {value, probability}."""
    q = {"type": "choice", "name": "kind", "instructions": CHOICE_INSTRUCTIONS,
         "choices": [{"value": v, "description": d} for v, d in CHOICES.items()]}
    res = _post(OPENAI_URL, {"Authorization": f"Bearer {key}"},
                {"model": OPENAI_MODEL, "input": tail(text), "questions": [q]}, timeout)
    try:
        a = res["answers"][0]
        if a.get("type") != "choice":
            raise JudgeError(f"answer type {a.get('type')}")
        return float(next(x["probability"] for x in a["probabilities"] if x["value"] == "decide"))
    except (KeyError, TypeError, ValueError, IndexError, StopIteration):
        raise JudgeError("unexpected response") from None


def typesafe_score(text, key, timeout):
    """TypeSafe (Jev): questions is a map; answers[<key>].noul is the probability of yes."""
    body = {"model": TYPESAFE_MODEL, "state": {"assistant_message": tail(text)},
            "questions": {"asks": {"type": "noul", "instructions": ASK_INSTRUCTIONS, "criteria": ASK_CRITERIA}}}
    res = _post(TYPESAFE_URL, {"Authorization": f"Bearer {key}"}, body, timeout)
    try:
        return float(res["answers"]["asks"]["noul"])
    except (KeyError, TypeError, ValueError):
        raise JudgeError("unexpected response") from None


def google_score(text, key, timeout):
    """Gemini Decisions: questions is a map; a choice question's criteria maps option ids to descriptions, and
    answers[<key>].probabilities maps option ids to probabilities."""
    body = {"model": GOOGLE_MODEL, "input": tail(text),
            "questions": {"kind": {"type": "choice", "instructions": CHOICE_INSTRUCTIONS, "criteria": CHOICES}}}
    res = _post(GOOGLE_URL, {"x-goog-api-key": key}, body, timeout)
    try:
        a = res["answers"]["kind"]
        if a.get("type") != "choice":
            raise JudgeError(f"answer type {a.get('type')}")
        return float(a["probabilities"]["decide"])
    except (KeyError, TypeError, ValueError):
        raise JudgeError("unexpected response") from None


SCORERS = {"openai": openai_score, "typesafe": typesafe_score, "google": google_score}


def asks_decision(text, backend="regex", key="", threshold=None, timeout=TIMEOUT):
    """Verdict for text. backend: one of BACKENDS (anything else is regex). key: the vendor's API key.
    threshold: overrides the vendor's default in THRESHOLDS."""
    if backend not in SCORERS:
        return regex_asks(text)
    if not maybe_asks(text):
        return Verdict(False, 0.0, backend)
    try:
        if not key:
            raise JudgeError("no API key")
        score = SCORERS[backend](text, key, timeout)
    except JudgeError as e:
        v = regex_asks(text)
        v.fell_back, v.error = True, f"{backend}: {e}"
        return v
    return Verdict(score >= (THRESHOLDS[backend] if threshold is None else threshold), score, backend)
