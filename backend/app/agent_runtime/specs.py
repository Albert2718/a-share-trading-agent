from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable, Generic, TypeVar

from pydantic import BaseModel, ValidationError


class ToolEffect(StrEnum):
    READ = "read"
    CONFIRM_WRITE = "confirm_write"
    BACKGROUND = "background"


ArgumentsT = TypeVar("ArgumentsT", bound=BaseModel)
ContextT = TypeVar("ContextT")


@dataclass(frozen=True)
class ToolExecution:
    name: str
    result: dict
    pending_action: dict | None = None


@dataclass(frozen=True)
class ToolSpec(Generic[ContextT, ArgumentsT]):
    name: str
    description: str
    input_model: type[ArgumentsT]
    effect: ToolEffect
    handler: Callable[[ContextT, ArgumentsT], Awaitable[dict]]

    def llm_schema(self) -> dict:
        parameters = self.input_model.model_json_schema()
        parameters.pop("title", None)
        parameters["additionalProperties"] = False
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


class AsyncToolRegistry(Generic[ContextT]):
    def __init__(self, definitions: list[ToolSpec]):
        self._definitions = {item.name: item for item in definitions}

    def schemas(self) -> list[dict]:
        return [item.llm_schema() for item in self._definitions.values()]

    async def execute(self, context: ContextT, name: str, arguments: dict) -> ToolExecution:
        definition = self._definitions.get(name)
        if definition is None:
            return ToolExecution(name=name, result={"ok": False, "error": "unknown tool"})
        try:
            validated = definition.input_model.model_validate(arguments or {})
        except ValidationError as exc:
            return ToolExecution(
                name=name,
                result={"ok": False, "error": "invalid arguments", "details": exc.errors(include_url=False)},
            )
        if definition.effect == ToolEffect.CONFIRM_WRITE:
            return ToolExecution(
                name=name,
                result={"ok": True, "status": "pending_confirmation"},
                pending_action={
                    "tool_name": name,
                    "arguments": validated.model_dump(mode="json"),
                },
            )
        try:
            result = await definition.handler(context, validated)
        except Exception:
            return ToolExecution(name=name, result={"ok": False, "error": "tool execution failed"})
        return ToolExecution(name=name, result=result)


class BoundToolExecutor(Generic[ContextT]):
    """Bind authenticated request context to the web tool registry for LangGraph."""

    def __init__(self, registry: AsyncToolRegistry[ContextT], context: ContextT):
        self.registry = registry
        self.context = context

    def schemas(self) -> list[dict]:
        return self.registry.schemas()

    async def execute(self, name: str, arguments: dict) -> ToolExecution:
        return await self.registry.execute(self.context, name, arguments)
