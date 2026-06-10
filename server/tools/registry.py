from typing import Protocol


class Tool(Protocol):
    name: str

    def run(self, **kwargs):
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def execute(self, name: str, **kwargs):
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name].run(**kwargs)

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name]
