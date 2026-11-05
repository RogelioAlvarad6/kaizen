"""Claude agent loop: a manual tool-use loop so every step can be logged to the run timeline."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from . import db
from .config import DEFAULT_EFFORT, DEFAULT_MODEL, MODELS

# Server-side refusal fallback is supported on these models (Claude API, "default" routing mode).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env / backend/.env
    return _client


def estimate_cost(model: str, usage: Any) -> float:
    price_in, price_out = MODELS.get(model, MODELS[DEFAULT_MODEL])["price"]
    inp = (getattr(usage, "input_tokens", 0) or 0)
    inp += (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25
    inp += (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.10
    out = getattr(usage, "output_tokens", 0) or 0
    return (inp * price_in + out * price_out) / 1_000_000


@dataclass
class AgentResult:
    text: str
    cost: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    stop_reason: str = ""


class AgentError(RuntimeError):
    pass


def run_agent(
    *,
    system: str,
    messages: list[dict],
    tool_defs: list[dict] | None = None,
    tool_handler: Callable[[str, dict], str] | None = None,
    model: str | None = None,
    effort: str | None = None,
    max_turns: int = 15,
    max_tokens: int = 16000,
    source: str = "agent",
    on_event: Callable[[str], None] | None = None,
) -> AgentResult:
    """Run Claude until it stops calling tools. `messages` is mutated in place (append-only),
    so callers can persist full content blocks (thinking blocks must be replayed unchanged)."""
    model = model or DEFAULT_MODEL
    effort = effort or DEFAULT_EFFORT
    log = on_event or (lambda _msg: None)

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "output_config": {"effort": effort},
    }
    if tool_defs:
        kwargs["tools"] = tool_defs
    if model in FALLBACK_MODELS:
        kwargs["betas"] = [FALLBACK_BETA]
        kwargs["fallbacks"] = "default"

    result = AgentResult(text="", messages=messages)
    for _turn in range(max_turns):
        try:
            resp = client().beta.messages.create(messages=messages, **kwargs)
        except anthropic.AuthenticationError as e:
            raise AgentError("Anthropic API key missing or invalid. Set ANTHROPIC_API_KEY in backend/.env") from e
        except anthropic.RateLimitError as e:
            raise AgentError("Rate limited by the Anthropic API. Try again in a minute.") from e
        except anthropic.BadRequestError as e:
            raise AgentError(f"Bad request: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise AgentError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AgentError("Could not reach the Anthropic API. Check your internet connection.") from e
        except TypeError as e:
            if "authentication" in str(e).lower():
                raise AgentError("No Anthropic API key found. Add ANTHROPIC_API_KEY=... to backend/.env and restart the app.") from e
            raise

        cost = estimate_cost(resp.model or model, resp.usage)
        result.cost += cost
        db.record_spend(source, resp.model or model, cost)

        # Append the full content (thinking/fallback blocks included) - never rewrite history.
        messages.append({"role": "assistant", "content": [b.to_dict() for b in resp.content]})
        result.stop_reason = resp.stop_reason or ""

        texts = [b.text for b in resp.content if b.type == "text"]
        if texts:
            result.text = "\n".join(texts).strip()

        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            why = getattr(details, "explanation", None) or "the request was declined"
            raise AgentError(f"Claude declined this request: {why}")

        if resp.stop_reason == "pause_turn":
            continue

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not tool_uses:
            if resp.stop_reason == "max_tokens":
                result.text += "\n\n[output truncated: hit max_tokens]"
            return result

        tool_results = []
        for tu in tool_uses:
            args = tu.input if isinstance(tu.input, dict) else {}
            log(f"tool → {tu.name}({_short(args)})")
            try:
                if tool_handler is None:
                    raise ValueError(f"No tools available, but Claude called {tu.name}")
                out = tool_handler(tu.name, args)
                is_error = False
            except Exception as e:  # tool errors go back to Claude, not up the stack
                out, is_error = f"Error: {e}", True
            result.tool_calls.append({"name": tu.name, "input": args, "error": is_error})
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out, "is_error": is_error})
        # All results for one assistant turn go back in a single user message.
        messages.append({"role": "user", "content": tool_results})

    result.text += "\n\n[stopped: reached max agent turns]"
    return result


def ask(prompt: str, *, system: str = "You are a concise, helpful assistant.", model: str | None = None,
        effort: str | None = None, source: str = "ask") -> AgentResult:
    return run_agent(system=system, messages=[{"role": "user", "content": prompt}],
                     model=model, effort=effort, source=source)


def _short(args: dict) -> str:
    s = json.dumps(args, ensure_ascii=False)
    return s if len(s) <= 120 else s[:117] + "..."
