from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
            )
            return self._parse_json(self._response_content(response))
        except Exception:
            return None

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
