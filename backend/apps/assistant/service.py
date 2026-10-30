"""Ask, explain and summarise: Claude when a key is set, basic mode otherwise, with the number guard.

A chat is remembered on the server, so "why?" and "and for C-102?" are understood and nobody can
forge what the assistant said earlier. An answer with a number that is not in the data gets one
chance to put itself right before it is replaced by the data-based answer.
"""

import logging
import re
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import basic, claude, guard
from .models import AssistantLog
from .suggestions import follow_ups
from .tools import Toolbox

log = logging.getLogger(__name__)

DISCLAIMER = (
    "AI text is advisory. Check the numbers on the Plan and Insights screens before acting on them."
)
GUARD_NOTE = "I left out my first answer because it had a number I could not back with your data. Here is what the data says."
FAILED_NOTE = "The AI service could not be reached, so this is the basic-mode answer."
HISTORY_TURNS = 6  # earlier questions of the same chat the assistant can see
CORRECTIONS = 1  # extra tries when an answer has a number that is not in the data


def get_client():
    return claude.get_client()


def status() -> dict[str, Any]:
    ai = bool(settings.ANTHROPIC_API_KEY)
    return {
        "mode": "ai" if ai else "basic",
        "notice": None if ai else basic.BASIC_NOTICE,
        "disclaimer": DISCLAIMER,
        "max_question_chars": settings.ASSISTANT_MAX_QUESTION_CHARS,
        "starters": follow_ups([]),
    }


def _check_daily_limit(user) -> None:
    since = timezone.now() - timedelta(hours=24)
    used = AssistantLog.objects.filter(user=user, created_at__gte=since).count()
    if used >= settings.ASSISTANT_DAILY_LIMIT:
        raise ValidationError(
            {"detail": "You have reached the limit of questions for 24 hours. Try again later."}
        )


def _clean(question: str) -> str:
    question = " ".join((question or "").split())
    if not question:
        raise ValidationError({"question": "Type a question."})
    if len(question) > settings.ASSISTANT_MAX_QUESTION_CHARS:
        raise ValidationError(
            {"question": f"Keep it under {settings.ASSISTANT_MAX_QUESTION_CHARS} characters."}
        )
    return question


def _conversation_id(value: Any) -> str:
    """The chat this belongs to: the id the caller sent if it is well formed, else a new one."""
    value = str(value or "")
    return value if re.fullmatch(r"[0-9a-f]{32}", value) else uuid.uuid4().hex


def _history(user, company, conversation: str) -> tuple[list[dict[str, Any]], str]:
    """The earlier turns of this chat, as messages for the model and as text for the number check."""
    rows = list(
        AssistantLog.objects.filter(user=user, company=company, conversation=conversation, kind="ask")
        .order_by("-id")[:HISTORY_TURNS]
    )[::-1]  # fmt: skip
    messages: list[dict[str, Any]] = []
    for row in rows:
        messages.append({"role": "user", "content": row.prompt})
        messages.append({"role": "assistant", "content": row.answer[:2000]})
    return messages, "\n".join(f"{r.prompt}\n{r.answer}" for r in rows)


def _respond(
    user,
    company,
    kind: str,
    prompt: str,
    ai_question: str,
    fallback,
    client=None,
    conversation: str = "",
) -> dict[str, Any]:
    """Run the model (when there is one), guard its numbers, and fall back to the templated answer."""
    _check_daily_limit(user)
    box = Toolbox(company)
    client = client if client is not None else get_client()
    conversation = conversation or uuid.uuid4().hex
    earlier, earlier_text = _history(user, company, conversation) if kind == "ask" else ([], "")
    notes: list[str] = []
    text: str | None = None
    mode, flagged, tokens = "basic", False, [0, 0]
    if client is not None:
        try:
            messages = [*earlier, {"role": "user", "content": ai_question}]
            context = f"{ai_question}\n{earlier_text}"
            reply, tin, tout = claude.run(client, box, messages)
            tokens = [tin, tout]
            invented = guard.unverified(reply, box.results, context)
            for _ in range(CORRECTIONS if invented else 0):
                log.info("Assistant answer corrected: numbers not in tool results: %s", invented)
                messages.append({"role": "user", "content": claude.correction_for(invented)})
                reply, tin, tout = claude.run(client, box, messages)
                tokens = [tokens[0] + tin, tokens[1] + tout]
                invented = guard.unverified(reply, box.results, context)
            if invented:
                flagged = True
                notes.append(GUARD_NOTE)
                log.warning("Assistant answer blocked: numbers not in tool results: %s", invented)
            else:
                text, mode = reply, "ai"
        except Exception:
            log.exception("The AI call failed")
            notes.append(FAILED_NOTE)
    result: dict[str, Any] = {}
    if text is None:
        result = fallback(box)
        text = result["answer"] if isinstance(result, dict) else result
        if client is None:
            notes.append(basic.BASIC_NOTICE)
    AssistantLog.objects.create(
        company=company, user=user, username=user.username, kind=kind, mode=mode, prompt=prompt[:600],
        tool_calls=box.calls, answer=text, flagged=flagged, input_tokens=tokens[0],
        output_tokens=tokens[1], conversation=conversation if kind == "ask" else "",
    )  # fmt: skip
    names = [c["name"] for c in box.calls]
    return {
        "answer": text, "mode": mode, "notes": notes, "disclaimer": DISCLAIMER, "tools": names,
        "intent": result.get("intent") if isinstance(result, dict) else None,
        "conversation": conversation, "follow_ups": follow_ups(names, prompt),
    }  # fmt: skip


def ask(user, company, question: str, client=None, conversation: str = "") -> dict[str, Any]:
    question = _clean(question)
    return _respond(
        user,
        company,
        "ask",
        question,
        question,
        lambda box: basic.answer(box, question),
        client,
        _conversation_id(conversation),
    )


def explain(user, company, key: str, client=None) -> dict[str, Any]:
    """The "Explain this" button on an insight card."""
    from apps.insights.service import latest_run

    run = latest_run(company)
    card = run.cards.filter(key=key).first() if run else None
    if card is None:
        raise ValidationError(
            {"insight": "This insight is no longer current. Refresh the insights."}
        )

    def templated(box: Toolbox) -> dict[str, Any]:
        box.call("get_insight", {"key": key})
        why = " ".join(card.why)
        return {
            "answer": f"{card.message}\nHow I worked it out: {why}\nA good next step: {card.action}".strip(),
            "intent": "explain",
        }

    prompt = f"Explain this insight in plain words for a planner: {card.title}. Start by calling get_insight with key {key!r}."
    return _respond(user, company, "explain", f"Explain {key}", prompt, templated, client)


def monthly_summary(user, company, client=None) -> dict[str, Any]:
    prompt = (
        "Summarise this month for the plant manager in at most 8 lines. Open with one sentence that "
        "says whether the month is on course or behind and why. Then list what needs attention first "
        "(the three worst lines and what holds each up, or the data problem if one is not scheduled), "
        "then the dispatch record, then the month forecast. Use the tools for every figure."
    )
    return _respond(
        user,
        company,
        "summary",
        "Summarise this month",
        prompt,
        lambda box: {"answer": basic.summary(box), "intent": "summary"},
        client,
    )
