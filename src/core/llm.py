from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .config import load_config


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    content: str = ""
    tool_calls: List[LLMToolCall] = field(default_factory=list)


class LLMClient:
    """OpenAI-compatible client used by chat and research agents."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        config = load_config()
        self.model = model or config.news_agent_model
        self.api_key = api_key or config.openai_api_key
        self.base_url = base_url or config.openai_base_url
        self.timeout = timeout or config.llm_timeout
        if not self.model or not self.api_key:
            raise ValueError("LLM model and API key must be configured.")

        from openai import OpenAI  # type: ignore

        kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self.client = OpenAI(**kwargs)

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0,
    ) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            **self._provider_request_options(),
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            return LLMResponse()
        message = getattr(choices[0], "message", None)
        if message is None:
            return LLMResponse()
        calls = []
        for call in getattr(message, "tool_calls", None) or []:
            function = getattr(call, "function", None)
            raw_arguments = getattr(function, "arguments", "{}") if function is not None else "{}"
            try:
                arguments = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                LLMToolCall(
                    id=getattr(call, "id", "") or getattr(function, "name", "tool"),
                    name=getattr(function, "name", ""),
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return LLMResponse(content=getattr(message, "content", None) or "", tool_calls=calls)

    def chat_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        temperature: float = 0,
    ) -> LLMResponse:
        """Stream assistant text while still aggregating OpenAI tool-call deltas."""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            stream=True,
            **self._provider_request_options(),
        )
        content_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None) or ""
            if content:
                content_parts.append(content)
                on_token(content)
            for call in getattr(delta, "tool_calls", None) or []:
                index = int(getattr(call, "index", 0) or 0)
                item = calls.setdefault(
                    index, {"id": "", "name": "", "arguments": ""}
                )
                item["id"] += getattr(call, "id", None) or ""
                function = getattr(call, "function", None)
                if function is not None:
                    item["name"] += getattr(function, "name", None) or ""
                    item["arguments"] += getattr(function, "arguments", None) or ""
        tool_calls = []
        for item in calls.values():
            try:
                arguments = json.loads(item["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                LLMToolCall(
                    id=item["id"] or item["name"] or "tool",
                    name=item["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return LLMResponse(content="".join(content_parts), tool_calls=tool_calls)

    def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.2) -> str:
        """Run a tool-free conversational turn for the web Agent."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            **self._provider_request_options(),
        )
        return self._response_content(response) or ""

    def structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        schema: dict,
        temperature: float = 0,
        max_tokens: int = 900,
    ) -> Optional[dict]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_schema", "json_schema": schema},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                **self._provider_request_options(),
            )
            data = self._parse_json(self._response_content(response))
            if data is not None:
                return data
        except Exception:
            pass
        return self._structured_fallback(
            system_prompt=system_prompt,
            user_payload=user_payload,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _structured_fallback(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        schema: dict,
        temperature: float,
        max_tokens: int,
    ) -> Optional[dict]:
        try:
            schema_text = json.dumps(schema.get("schema", schema), ensure_ascii=False)
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{system_prompt}\n\n"
                            "Return exactly one valid JSON object. Do not use markdown fences. "
                            f"The JSON object must match this schema: {schema_text}"
                        ),
                    },
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                **self._provider_request_options(),
            )
            return self._parse_json(self._response_content(response))
        except Exception:
            return None

    def _provider_request_options(self) -> dict[str, Any]:
        if self._is_deepseek_v4():
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {}

    def _is_deepseek_v4(self) -> bool:
        model = (self.model or "").lower()
        base_url = (self.base_url or "").lower()
        return "deepseek" in model and ("v4" in model or "deepseek" in base_url)

    @staticmethod
    def _response_content(response) -> Optional[str]:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        return getattr(message, "content", None) or None if message is not None else None

    @staticmethod
    def _parse_json(content: Optional[str]) -> Optional[dict]:
        if not content:
            return None
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None


def get_llm_client() -> LLMClient:
    return LLMClient()
