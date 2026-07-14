from __future__ import annotations

import json
from typing import Dict, List, Optional

from src.core import load_config


class TradingAgentsLLM:
    """
    OpenAI-compatible LLM client used by analyst agents.

    It supports both plain chat text and Structured Outputs JSON calls.
    Configuration is loaded from .env / user config through infra.config.
    Compatible env names:
    - LLM_MODEL_ID or NEWS_AGENT_MODEL
    - LLM_API_KEY or OPENAI_API_KEY
    - LLM_BASE_URL or OPENAI_BASE_URL
    - LLM_TIMEOUT
    """

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

        kwargs = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self.client = OpenAI(**kwargs)

    def think(self, messages: List[Dict[str, str]], temperature: float = 0, stream: bool = False) -> Optional[str]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=stream,
            )
            if not stream:
                return self._response_content(response)

            collected = []
            for chunk in response:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected.append(content)
            print()
            return "".join(collected)
        except Exception:
            return None

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
            content = self._response_content(response)
            data = self._parse_json(content)
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

    def _response_content(self, response) -> Optional[str]:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        if message is None:
            return None
        return getattr(message, "content", None) or None

    def _parse_json(self, content: Optional[str]) -> Optional[dict]:
        if not content:
            return None
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None


def call_structured_llm(
    *,
    system_prompt: str,
    user_payload: dict,
    schema: dict,
    model: Optional[str] = None,
    temperature: float = 0,
    max_tokens: int = 900,
) -> Optional[dict]:
    try:
        client = TradingAgentsLLM(model=model)
        return client.structured(
            system_prompt=system_prompt,
            user_payload=user_payload,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception:
        return None
