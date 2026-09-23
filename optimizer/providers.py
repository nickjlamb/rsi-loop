"""Model providers. One real provider (the Perplexity Agent API, which fronts
Anthropic/OpenAI/Google/xAI models at provider rates with web search OFF when
no tools are requested) and a scripted mock for tests and $0 pipeline runs.

    provider = PerplexityAgentProvider(api_key=os.environ["PERPLEXITY_API_KEY"])
    c = provider.complete(messages, model="anthropic/claude-sonnet-5", max_output_tokens=6000)
    c.text, c.usage, c.cost_usd, c.raw

Closed-world invariant: the request never carries a `tools` field, and the
provider refuses to send one. Every call's usage and cost are returned so the
loop can write them into the artifact.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence

AGENT_URL = "https://api.perplexity.ai/v1/agent"
PROVIDER_VERSION = "0.1.0"


class ProviderError(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    model: str
    usage: Dict[str, object] = field(default_factory=dict)
    cost_usd: Optional[float] = None
    response_id: Optional[str] = None
    latency_s: float = 0.0
    raw: Optional[Dict[str, object]] = None


class Provider(Protocol):
    name: str

    def complete(self, messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                 temperature: Optional[float] = None, cache_key: Optional[str] = None) -> Completion: ...


def build_agent_request(messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                        temperature: Optional[float] = None, cache_key: Optional[str] = None) -> Dict[str, object]:
    """The Agent API body. System content goes in `instructions`; the rest in
    `input` as role/content items. No `tools`, ever."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    inputs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    body: Dict[str, object] = {"model": model, "input": inputs, "max_output_tokens": max_output_tokens,
                               "store": False}          # the artifacts are the record; nothing is kept server-side
    if system:
        body["instructions"] = system
    if temperature is not None:
        body["temperature"] = temperature
    if cache_key:
        body["prompt_cache_key"] = cache_key
    assert "tools" not in body
    return body


def extract_text(data: Dict[str, object]) -> str:
    """Tolerant of the Responses-style shapes: `output_text`, or `output` items
    of type message with content parts carrying `text`."""
    if isinstance(data.get("output_text"), str) and data["output_text"]:
        return data["output_text"]
    parts: List[str] = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in (None, "message"):
            content = item.get("content", [])
            if isinstance(content, str):
                parts.append(content)
            else:
                for c in content or []:
                    if isinstance(c, dict) and isinstance(c.get("text"), str):
                        parts.append(c["text"])
    if not parts and isinstance(data.get("choices"), list):        # chat-completions shape, just in case
        for ch in data["choices"]:
            msg = (ch or {}).get("message", {})
            if isinstance(msg.get("content"), str):
                parts.append(msg["content"])
    return "\n".join(parts)


def extract_cost(data: Dict[str, object]) -> Optional[float]:
    u = data.get("usage") or {}
    cost = u.get("cost") if isinstance(u, dict) else None
    if isinstance(cost, dict) and isinstance(cost.get("total_cost"), (int, float)):
        return float(cost["total_cost"])
    return None


class PerplexityAgentProvider:
    name = "perplexity-agent"

    def __init__(self, api_key: str, *, url: str = AGENT_URL, timeout_s: float = 900.0, max_retries: int = 4):
        if not api_key:
            raise ProviderError("PERPLEXITY_API_KEY is empty")
        self.api_key = api_key
        self.url = url
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    def complete(self, messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                 temperature: Optional[float] = None, cache_key: Optional[str] = None) -> Completion:
        body = build_agent_request(messages, model=model, max_output_tokens=max_output_tokens,
                                   temperature=temperature, cache_key=cache_key)
        payload = json.dumps(body).encode()
        last: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.url, data=payload, method="POST", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                "User-Agent": f"rsi-loop-2/{PROVIDER_VERSION}"})
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    data = json.loads(resp.read().decode())
                text = extract_text(data)
                if not text:
                    raise ProviderError(f"empty completion; raw keys: {sorted(data)}")
                return Completion(text=text, model=str(data.get("model", model)), usage=dict(data.get("usage") or {}),
                                  cost_usd=extract_cost(data), response_id=data.get("id"),
                                  latency_s=round(time.time() - t0, 3), raw=data)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:1000]
                last = f"HTTP {e.code}: {detail}"
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(5.0 * (2 ** attempt))
                    continue
                raise ProviderError(last) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = f"network: {e}"
                if attempt < self.max_retries:
                    time.sleep(5.0 * (2 ** attempt))
                    continue
                raise ProviderError(last) from None
        raise ProviderError(last or "unknown provider failure")


class ScriptedProvider:
    """Returns pre-written replies in order; for tests and $0 pipeline validation.
    Each entry may be a string or a callable(messages) -> string."""
    name = "scripted"

    def __init__(self, replies: Sequence[object], *, model: str = "scripted/mock"):
        self._replies = list(replies)
        self._i = 0
        self.model = model
        self.calls: List[List[Dict[str, str]]] = []

    def complete(self, messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                 temperature: Optional[float] = None, cache_key: Optional[str] = None) -> Completion:
        self.calls.append([dict(m) for m in messages])
        if self._i >= len(self._replies):
            raise ProviderError("scripted provider exhausted")
        r = self._replies[self._i]
        self._i += 1
        text = r(messages) if callable(r) else str(r)
        return Completion(text=text, model=self.model, usage={"input_tokens": sum(len(m["content"]) // 4 for m in messages),
                                                              "output_tokens": len(text) // 4}, cost_usd=0.0)
