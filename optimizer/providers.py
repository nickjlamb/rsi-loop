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
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence

AGENT_URL = "https://api.perplexity.ai/v1/agent"
PROVIDER_VERSION = "0.1.0"


class ProviderError(RuntimeError):
    def __init__(self, message: str, raw: Optional[Dict[str, object]] = None):
        super().__init__(message)
        self.raw = raw


def diagnostics(data: Dict[str, object]) -> Dict[str, object]:
    """What we keep when a response is odd: enough to see why without the prompts."""
    out_items = data.get("output") or []
    return {"status": data.get("status"), "incomplete_details": data.get("incomplete_details"),
            "error": data.get("error"), "output_item_types": [(i.get("type"), i.get("status")) for i in out_items if isinstance(i, dict)],
            "usage": data.get("usage"), "model": data.get("model"), "id": data.get("id")}


@dataclass
class Completion:
    text: str
    model: str
    usage: Dict[str, object] = field(default_factory=dict)
    cost_usd: Optional[float] = None
    response_id: Optional[str] = None
    latency_s: float = 0.0
    raw: Optional[Dict[str, object]] = None
    finish_reason: str = "completed"          # completed | max_output_tokens | incomplete | empty


class Provider(Protocol):
    name: str

    def complete(self, messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                 temperature: Optional[float] = None, cache_key: Optional[str] = None) -> Completion: ...


def build_agent_request(messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                        temperature: Optional[float] = None, cache_key: Optional[str] = None,
                        background: bool = False, reasoning_effort: Optional[str] = None) -> Dict[str, object]:
    """The Agent API body. System content goes in `instructions`; the rest in
    `input` as role/content items. No `tools`, ever."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    inputs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    body: Dict[str, object] = {"model": model, "input": inputs, "max_output_tokens": max_output_tokens,
                               "store": bool(background)}   # background mode needs a stored response to poll; otherwise nothing is kept server-side
    if background:
        body["background"] = True
    if system:
        body["instructions"] = system
    if temperature is not None:
        body["temperature"] = temperature
    if cache_key:
        body["prompt_cache_key"] = cache_key
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
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


def _is_phantom_completion(data: Dict[str, object]) -> bool:
    if data.get("status") != "completed" or extract_text(data):
        return False
    u = data.get("usage") or {}
    return not data.get("output") and int((u or {}).get("total_tokens") or 0) == 0


def extract_cost(data: Dict[str, object]) -> Optional[float]:
    u = data.get("usage") or {}
    cost = u.get("cost") if isinstance(u, dict) else None
    if isinstance(cost, dict) and isinstance(cost.get("total_cost"), (int, float)):
        return float(cost["total_cost"])
    return None


class PerplexityAgentProvider:
    name = "perplexity-agent"

    def __init__(self, api_key: str, *, url: str = AGENT_URL, timeout_s: float = 360.0, max_retries: int = 4,
                 background: bool = True, poll_s: float = 5.0, deadline_s: float = 1800.0,
                 reasoning_effort: Optional[str] = None):
        """background=True submits the request and polls for the result instead of holding one
        HTTP connection open for the whole generation (long-reasoning calls were dropping)."""
        if not api_key:
            raise ProviderError("PERPLEXITY_API_KEY is empty")
        self.api_key = api_key
        self.url = url
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.background = background
        self.poll_s = poll_s
        self.deadline_s = deadline_s
        self.reasoning_effort = reasoning_effort      # None = provider default; recorded in trajectory.json

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                "User-Agent": f"rsi-loop-2/{PROVIDER_VERSION}"}

    def _http(self, method: str, url: str, payload: Optional[bytes] = None, timeout: Optional[float] = None) -> Dict[str, object]:
        """One HTTP exchange with retries on transient failures. Returns the parsed JSON body."""
        last: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=payload, method=method, headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout_s) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:1000]
                last = f"HTTP {e.code}: {detail}"
                if e.code in (404, 408, 429, 499, 500, 502, 503, 504) and attempt < self.max_retries:
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

    def _poll(self, response_id: str, t0: float) -> Dict[str, object]:
        """GET the stored response until it leaves queued/in_progress. Tries the two
        retrieval paths the Agent API documents (its own and the OpenAI-compatible alias)."""
        base = self.url.rsplit("/v1/", 1)[0]
        paths = [f"{base}/v1/agent/{response_id}", f"{base}/v1/responses/{response_id}"]
        path_i = 0
        while True:
            if time.time() - t0 > self.deadline_s:
                raise ProviderError(f"background response {response_id} not finished after {self.deadline_s:.0f}s")
            time.sleep(self.poll_s)
            try:
                data = self._http("GET", paths[path_i], timeout=60.0)
            except ProviderError as e:
                if "HTTP 404" in str(e) and path_i + 1 < len(paths):
                    path_i += 1
                    continue
                raise
            status = data.get("status")
            if status not in ("queued", "in_progress", None):
                return data

    def complete(self, messages: Sequence[Dict[str, str]], *, model: str, max_output_tokens: int,
                 temperature: Optional[float] = None, cache_key: Optional[str] = None) -> Completion:
        body = build_agent_request(messages, model=model, max_output_tokens=max_output_tokens,
                                   temperature=temperature, cache_key=cache_key, background=self.background,
                                   reasoning_effort=self.reasoning_effort)
        t0 = time.time()
        last: Optional[ProviderError] = None
        for attempt in range(self.max_retries + 1):
            # A nonce per submission: the Agent API de-duplicates identical stored requests and
            # returned the same phantom response id for a resubmission (23 Sep 2026).
            body["metadata"] = {"nonce": uuid.uuid4().hex, "attempt": str(attempt)}
            payload = json.dumps(body).encode()
            data = self._http("POST", self.url, payload)
            if self.background and data.get("status") in ("queued", "in_progress") and data.get("id"):
                data = self._poll(str(data["id"]), t0)
            if _is_phantom_completion(data):
                # "completed" with no output and zero tokens: a backend failure reported as success
                # (seen 23 Sep 2026). Unbilled. Re-read once in case the output was still being
                # attached, then resubmit.
                if self.background and data.get("id"):
                    time.sleep(self.poll_s)
                    try:
                        data = self._poll(str(data["id"]), t0)
                    except ProviderError:
                        pass
                if _is_phantom_completion(data):
                    last = ProviderError(f"phantom completion (no output, zero tokens): {json.dumps(diagnostics(data))[:600]}", raw=data)
                    if attempt < self.max_retries:
                        time.sleep(5.0 * (2 ** attempt))
                        continue
                    raise last
            return self._to_completion(data, model, t0)
        raise last or ProviderError("unknown provider failure")

    def _to_completion(self, data: Dict[str, object], model: str, t0: float) -> Completion:
        text = extract_text(data)
        status = data.get("status")
        inc = data.get("incomplete_details") or {}
        reason = inc.get("reason") if isinstance(inc, dict) else None
        if data.get("error") or status in ("failed", "cancelled"):
            raise ProviderError(f"provider reported failure: {json.dumps(diagnostics(data))[:1500]}", raw=data)
        finish = "completed"
        if status == "incomplete":
            finish = "max_output_tokens" if reason == "max_output_tokens" else "incomplete"
        if not text:
            # No message text at all. If the output budget was exhausted (e.g. by reasoning),
            # that is the model's reply to correct, not an infrastructure failure.
            if finish != "completed":
                finish = finish if finish != "incomplete" else "empty"
                return Completion(text="", model=str(data.get("model", model)), usage=dict(data.get("usage") or {}),
                                  cost_usd=extract_cost(data), response_id=data.get("id"),
                                  latency_s=round(time.time() - t0, 3), raw=data, finish_reason=finish)
            raise ProviderError(f"empty completion with status {status!r}: {json.dumps(diagnostics(data))[:1500]}", raw=data)
        return Completion(text=text, model=str(data.get("model", model)), usage=dict(data.get("usage") or {}),
                          cost_usd=extract_cost(data), response_id=data.get("id"),
                          latency_s=round(time.time() - t0, 3), raw=data, finish_reason=finish)


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
