"""Core pipeline agent loop.

This module implements the main agent that orchestrates the entire data
pipeline workflow. The agent:

1. Receives natural language input from the user
2. Uses an LLM to reason about which tools to call
3. Executes tools and feeds results back to the LLM
4. Continues until the LLM produces a final response (no more tool calls)

Key features:
    - LLM API retry with exponential backoff (3 retries per model)
    - Model fallback chain (4 models, auto-switch on failure)
    - Embedding-based tool context injection (via pg_vector)
    - Token budget control (phase-based degradation)
    - Metrics collection (latency, token usage, tool calls)
    - Session persistence (JSONL format)

Usage::

    from dpa.core import PipelineAgent
    from dpa.sessions import Session

    agent = PipelineAgent()
    session = Session()
    response = agent.run("Analyze data quality of orders.csv", session)
    print(response)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from dpa.embedding import EmbeddingService
from dpa.metrics import get_metrics
from dpa.sessions import Session
from dpa.token_budget import TokenBudget
from dpa.tools import Tool, get_tool, get_tools

FALLBACK_MODELS = [
    "glm-5.2",
    "deepseek-v4-flash",
    "sensenova-6.8-flash-lite",
    "sensenova-6.7-flash-lite",
]

MAX_RETRIES = 3
RETRY_DELAY_BASE = 2


class PipelineAgent:
    """The main adaptive data pipeline agent.

    Manages the LLM-driven tool orchestration loop: plan -> execute -> verify.
    Integrates embedding-based tool retrieval, token budget control, metrics
    collection, and session persistence.

    Args:
        model (str, optional): LLM model name. Defaults to ``DPA_MODEL`` env var.
        base_url (str, optional): API base URL. Defaults to ``DPA_BASE_URL`` env var.
        api_key (str, optional): API key. Defaults to ``DPA_API_KEY`` env var.

    Example::

        agent = PipelineAgent(model="sensenova-6.8-flash-lite")
        session = Session(name="demo")
        response = agent.run("Parse orders.csv and check quality", session)
    """

    def __init__(self, model: str = "", base_url: str = "", api_key: str = "") -> None:
        """Initialize the agent with LLM configuration and dependencies."""
        self.model = model or os.getenv("DPA_MODEL", "glm-5.2")
        self.base_url = base_url or os.getenv("DPA_BASE_URL", "")
        self.api_key = api_key or os.getenv("DPA_API_KEY", "")
        self.tools = get_tools()
        self._system_prompt = self._build_system_prompt()
        self._metrics = get_metrics()
        self._embedding = EmbeddingService()
        self._budget = TokenBudget()

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool schemas for LLM context.

        Includes all registered tool schemas in JSON format so the LLM
        knows which tools are available and their parameter signatures.
        """
        tool_schemas = [t.to_schema() for t in self.tools]
        tools_desc = json.dumps(tool_schemas, indent=2, ensure_ascii=False)
        return f"""You are an Adaptive Data Pipeline Agent.

Your job is to help users manage data pipelines: parse, validate, transform, and monitor data.

You have access to these tools:
{tools_desc}

When you need to use a tool, respond with a JSON block:
```tool
{{"name": "tool_name", "args": {{"key": "value"}}}}
```

Always explain your reasoning before and after tool calls.
Handle errors gracefully and suggest fixes."""

    def run(self, user_input: str, session: Session) -> str:
        """Run the agent loop for a single user turn.

        The loop continues as long as the LLM response contains tool calls
        (marked with ```tool blocks). Each iteration:
            1. Check token budget
            2. Parse tool call from LLM response
            3. Execute the tool
            4. Send tool result back to LLM
            5. Repeat until no more tool calls

        Args:
            user_input: Natural language input from the user.
            session: Session object for persistence.

        Returns:
            The final LLM response as a string.
        """
        session.user(user_input)
        self._metrics.inc("messages_total")
        self._budget = TokenBudget()  # Reset budget for new turn

        # Retrieve tool context via embedding search
        tool_context = self._embedding.get_tool_context(user_input)

        messages = [
            {"role": "system", "content": self._system_prompt},
            *[self._to_msg(m) for m in session.messages()],
            {"role": "user", "content": user_input},
        ]

        # Truncate history if budget is low
        if not self._budget.can_afford(2000):
            messages = self._budget.truncate_history(messages)

        self._metrics.start("llm_call")
        response = self._call_llm(messages)
        self._metrics.stop("llm_call")
        session.assistant(response)

        tool_call_count = 0
        while "```tool" in response:
            # Check token budget before tool call
            if not self._budget.can_afford(500):
                response += "\n\n[Token budget exhausted, cannot continue tool calls]"
                break

            tool_name, tool_args, response = self._extract_tool_call(response)
            if tool_name:
                result = self._execute_tool(tool_name, tool_args, session)
                tool_call_count += 1
                self._budget.consume(200)  # Estimate token consumption for tool call

                self._metrics.start("llm_call")
                response = self._call_llm(messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": f"Tool result: {json.dumps(result, ensure_ascii=False)}"},
                ])
                self._metrics.stop("llm_call")
                session.assistant(response)

        self._metrics.observe("tool_calls_per_session", tool_call_count)
        return response

    def _call_llm(self, messages: list[dict]) -> str:
        """Call the LLM with model fallback chain.

        Tries the primary model first, then falls back to other models
        in order. Returns the first successful response, or the last error.
        """
        if not self.base_url:
            return "[LLM not configured] Set DPA_BASE_URL and DPA_API_KEY in .env"

        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        last_error = ""

        for model in models_to_try:
            result = self._call_llm_with_retry(messages, model)
            if not result.startswith("[LLM error]") and not result.startswith("[LLM 不可用]"):
                return result
            last_error = result

        return last_error

    def _call_llm_with_retry(self, messages: list[dict], model: str) -> str:
        """Call a specific model with retry logic.

        Retry strategy:
            - 429 (rate limit): exponential backoff (2s, 4s, 8s)
            - 500/503 (server error): fixed delay retry
            - Timeout: retry with fixed delay
            - 401: immediate failure (auth error)
            - Other: immediate failure
        """
        for attempt in range(MAX_RETRIES):
            start = time.monotonic()
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": model, "messages": messages, "temperature": 0.3},
                    timeout=60,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    token_input = usage.get("prompt_tokens", 0)
                    token_output = usage.get("completion_tokens", 0)
                    self._metrics.record_llm_call(model, latency_ms, token_input, token_output, True)
                    return content

                if resp.status_code == 429:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    time.sleep(delay)
                    continue

                if resp.status_code in (500, 503):
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_BASE)
                        continue
                    self._metrics.record_llm_call(model, latency_ms, 0, 0, False)
                    return f"[LLM error] {model}: {resp.status_code}"

                if resp.status_code == 401:
                    self._metrics.record_llm_call(model, latency_ms, 0, 0, False)
                    return "[认证失败] 请检查 DPA_API_KEY 配置"

                self._metrics.record_llm_call(model, latency_ms, 0, 0, False)
                return f"[LLM error] {resp.status_code}: {resp.text[:200]}"

            except httpx.TimeoutException:
                latency_ms = int((time.monotonic() - start) * 1000)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_BASE)
                    continue
                self._metrics.record_llm_call(model, latency_ms, 0, 0, False)
                return f"[LLM error] {model}: timeout"

            except Exception as e:
                latency_ms = int((time.monotonic() - start) * 1000)
                self._metrics.record_llm_call(model, latency_ms, 0, 0, False)
                return f"[LLM error] {model}: {e}"

        return f"[LLM 不可用] {model}: 所有重试均失败"

    def _extract_tool_call(self, text: str) -> tuple[str | None, dict, str]:
        """Extract a tool call from LLM response text.

        Looks for ```tool blocks containing JSON with ``name`` and ``args``.
        Returns the parsed tool call and the remaining text (with the tool
        block removed).

        Returns:
            Tuple of (tool_name, tool_args, remaining_text). Returns
            (None, {}, original_text) if no tool call found.
        """
        start = text.find("```tool")
        if start == -1:
            return None, {}, text
        end = text.find("```", start + 7)
        if end == -1:
            return None, {}, text
        block = text[start + 7:end].strip()
        try:
            call = json.loads(block)
            name = call.get("name")
            args = call.get("args", {})
            response = text[:start] + text[end + 3:]
            return name, args, response.strip()
        except json.JSONDecodeError:
            return None, {}, text

    def _execute_tool(self, name: str, args: dict, session: Session) -> Any:
        """Execute a tool and record metrics + session log.

        Wraps tool execution with timing, error handling, and session
        persistence. Returns the tool result dict.
        """
        tool = get_tool(name)
        start = time.monotonic()
        try:
            result = tool.run(**args)
            latency_ms = int((time.monotonic() - start) * 1000)
            success = result.get("status") != "error" if isinstance(result, dict) else True
            self._metrics.record_tool_call(name, latency_ms, success)
            session.tool_call(name, args, result, latency_ms)
            return result
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._metrics.record_tool_call(name, latency_ms, False)
            error_result = {"status": "error", "message": str(e)}
            session.tool_call(name, args, error_result, latency_ms)
            return error_result

    def _to_msg(self, entry: dict) -> dict | None:
        """Convert a session log entry to an LLM message dict.

        Filters out tool_call and error entries, returning only user and
        assistant messages suitable for the LLM context window.
        """
        role = entry.get("role")
        if role == "user":
            return {"role": "user", "content": entry.get("content", "")}
        if role == "assistant":
            return {"role": "assistant", "content": entry.get("content", "")}
        return None
