"""Tool registry and base class.

This module defines the `Tool` abstract base class and the global `TOOL_REGISTRY`
for all data pipeline tools. Tools are automatically registered via
``__init_subclass__`` — any subclass of `Tool` with a non-empty `name` is
added to the registry on class definition.

Usage:
    # Define a tool (auto-registers on import)
    class MyTool(Tool):
        name = "my_tool"
        description = "Does something useful"

        def run(self, **kwargs):
            return {"status": "ok"}

    # Retrieve tools
    from dpa.tools import get_tools, get_tool
    all_tools = get_tools()          # list[Tool]
    single = get_tool("my_tool")     # Tool instance
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

TOOL_REGISTRY: dict[str, type["Tool"]] = {}


class Tool(ABC):
    """Abstract base class for all data pipeline tools.

    Subclasses must set ``name`` (used as the tool identifier in LLM prompts
    and the registry key) and ``description`` (shown to the LLM for tool
    selection). The ``run()`` method contains the actual tool logic.

    Attributes:
        name: Unique tool identifier, e.g. ``"parse_data"``.
        description: Human-readable description for LLM context.

    Example::

        class ParseCSV(Tool):
            name = "parse_csv"
            description = "Parse a CSV file into structured data."

            def run(self, **kwargs) -> dict:
                path = kwargs.get("path", "")
                # ... parse logic ...
                return {"status": "ok", "rows": rows}
    """

    name: str = ""
    description: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-register tool subclasses into TOOL_REGISTRY.

        This hook fires when a class inherits from Tool. If the subclass
        defines a non-empty ``name``, it is added to the global registry.
        """
        super().__init_subclass__(**kwargs)
        if cls.name:
            TOOL_REGISTRY[cls.name] = cls

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the tool with the given arguments.

        Args:
            **kwargs: Tool-specific parameters. Each tool defines its own
                parameter schema.

        Returns:
            A dict with at least a ``"status"`` key (``"ok"`` or ``"error"``).
            Error responses include a ``"message"`` key with details.
        """
        ...

    def to_schema(self) -> dict:
        """Export the tool schema for LLM prompt injection.

        Returns:
            A dict with ``name``, ``description``, and ``parameters`` keys,
            suitable for inclusion in an OpenAI-style tool schema list.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": getattr(self, "parameters", {}),
        }


def get_tools() -> list[Tool]:
    """Instantiate and return all registered tools.

    Returns:
        A list of Tool instances, one per registered tool class.
    """
    return [cls() for cls in TOOL_REGISTRY.values()]


def get_tool(name: str) -> Tool:
    """Get a single tool instance by name.

    Args:
        name: The tool name (e.g. ``"parse_data"``).

    Returns:
        An instance of the requested tool.

    Raises:
        KeyError: If no tool with the given name is registered.
    """
    return TOOL_REGISTRY[name]()
