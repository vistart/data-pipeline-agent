"""Token budget control for the pipeline agent.

Manages a per-turn token budget to prevent runaway LLM costs. The budget
is divided into phases based on remaining capacity:

    - **normal** (>50%): Full execution, up to 2000 output tokens
    - **warning** (20-50%): Reduced output limit (1000 tokens)
    - **critical** (0-20%): Minimal output (500 tokens), history truncated
    - **exhausted** (0%): No further LLM calls allowed

The budget is reset at the start of each user turn.

Usage::

    from dpa.token_budget import TokenBudget

    budget = TokenBudget(total_budget=10000)

    if budget.can_afford(2000):
        # Proceed with LLM call
        budget.consume(estimated_tokens)

    # Truncate history if running low
    messages = budget.truncate_history(messages, keep_recent=3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenBudget:
    """Token budget manager with phase-based degradation.

    Tracks token consumption and provides budget-aware decision making
    for the agent loop. Supports history truncation, output limit
    adjustment, and budget exhaustion detection.

    Attributes:
        total_budget: Maximum tokens allowed per turn.
        used: Tokens consumed so far.
        plan_ratio: Budget allocation for plan handler.
        tool_ratio: Budget allocation per tool call.
        verify_ratio: Budget allocation for verify handler.
        history_ratio: Budget allocation for conversation history.
        safety_ratio: Reserved safety margin.
        remaining_ratio: Unallocated budget.
    """

    total_budget: int = 10000
    used: int = 0
    plan_ratio: float = 0.15
    tool_ratio: float = 0.05
    verify_ratio: float = 0.10
    history_ratio: float = 0.30
    safety_ratio: float = 0.20
    remaining_ratio: float = 0.20

    @property
    def remaining(self) -> int:
        """Return the number of tokens remaining in the budget."""
        return max(0, self.total_budget - self.used)

    @property
    def remaining_pct(self) -> float:
        """Return the remaining budget as a percentage (0.0 to 1.0)."""
        return self.remaining / self.total_budget if self.total_budget > 0 else 0

    @property
    def phase(self) -> str:
        """Return the current budget phase.

        Phases:
            - ``"normal"``: >50% remaining
            - ``"warning"``: 20-50% remaining
            - ``"critical"``: 0-20% remaining
            - ``"exhausted"``: 0% remaining
        """
        if self.remaining_pct > 0.5:
            return "normal"
        elif self.remaining_pct > 0.2:
            return "warning"
        elif self.remaining_pct > 0.0:
            return "critical"
        else:
            return "exhausted"

    def can_afford(self, estimated_tokens: int) -> bool:
        """Check if the budget can accommodate the estimated token cost.

        Args:
            estimated_tokens: Estimated tokens for the next operation.

        Returns:
            True if remaining budget >= estimated_tokens.
        """
        return self.remaining >= estimated_tokens

    def consume(self, tokens: int) -> None:
        """Consume tokens from the budget.

        Args:
            tokens: Number of tokens to deduct.
        """
        self.used += tokens

    def get_max_output_tokens(self) -> int:
        """Return the maximum allowed output tokens for the current phase.

        Returns:
            Phase-based output limit:
                - exhausted: 0
                - critical: min(500, remaining)
                - warning: min(1000, remaining)
                - normal: min(2000, remaining)
        """
        if self.phase == "exhausted":
            return 0
        elif self.phase == "critical":
            return min(500, self.remaining)
        elif self.phase == "warning":
            return min(1000, self.remaining)
        else:
            return min(2000, self.remaining)

    def truncate_history(self, messages: list[dict], keep_recent: int = 3) -> list[dict]:
        """Truncate conversation history to fit within budget.

        Preserves the system prompt and the most recent N non-system
        messages, discarding older messages.

        Args:
            messages: Full message list (including system prompt).
            keep_recent: Number of recent non-system messages to keep.

        Returns:
            Truncated message list with system prompt preserved.
        """
        if len(messages) <= keep_recent:
            return messages

        # Preserve system prompt + recent N messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= keep_recent:
            return messages

        truncated = non_system[-keep_recent:]
        return system_msgs + truncated

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string.

        Uses a simple heuristic: Chinese characters count as 1 token,
        other characters count as 1 token per 4 characters.

        Args:
            text: Input text to estimate.

        Returns:
            Estimated token count.
        """
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return chinese_chars + other_chars // 4

    def snapshot(self) -> dict[str, Any]:
        """Export the current budget state as a dict.

        Returns:
            Dict with keys: ``total_budget``, ``used``, ``remaining``,
            ``remaining_pct``, ``phase``, ``max_output_tokens``.
        """
        return {
            "total_budget": self.total_budget,
            "used": self.used,
            "remaining": self.remaining,
            "remaining_pct": f"{self.remaining_pct:.1%}",
            "phase": self.phase,
            "max_output_tokens": self.get_max_output_tokens(),
        }
