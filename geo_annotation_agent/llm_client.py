from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from openai import OpenAI


class BaseLLM(ABC):
    """
    Minimal provider-agnostic LLM interface used by GEOMeta.

    All pipeline stages should call only:
         llm.chat(
            messages,
            temperature=...,
            max_tokens=...,
            response_format=...,
        )
        
    The backend implementation can be direct OpenAI, LiteLLM, OpenRouter,
    vLLM, Ollama-compatible server, or another OpenAI-compatible endpoint.
    """

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        use_top_p: bool = True,
    ) -> str:
        pass


class OpenAICompatibleLLM(BaseLLM):
    """
    Generic OpenAI-compatible chat client.

    Works with:
      - Direct OpenAI API
      - LiteLLM proxy
      - OpenRouter
      - vLLM OpenAI-compatible server
      - Ollama / LM Studio OpenAI-compatible endpoints
      - other OpenAI-compatible chat-completion APIs

    Required config fields:
      - llm_api_key
      - llm_base_url
      - llm_model
    """

    def __init__(
         self,
         api_key: str,
         model: str,
         base_url: str = "",
         max_retries: int = 3,
         retry_sleep_seconds: float = 2.0,
         sleep_between_calls: float = 0.0,
         top_p: float = 1.0,
         supports_temperature: bool = True,
         supports_top_p: bool = True,
         supports_json_schema: bool = True,
     ):
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.base_url = str(base_url or "").rstrip("/")
        if not self.base_url:
            raise ValueError(
                "LLM base URL is required. Set LLM_BASE_URL."
             )
        self.max_retries = int(max_retries)
        self.retry_sleep_seconds = float(retry_sleep_seconds)
        self.sleep_between_calls = float(sleep_between_calls)
        self.top_p = float(top_p)
         
        self.supports_temperature = bool(supports_temperature)
        self.supports_top_p = bool(supports_top_p)
        
        self.supports_json_schema = bool(
             supports_json_schema
         )

        if not self.api_key:
            raise ValueError("Missing LLM API key.")
        if not self.model:
            raise ValueError("Missing LLM model name.")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        use_top_p: bool = True,
    ):
        last_err = None

        for attempt in range(1, self.max_retries + 1):
            try:
                payload = {
                    "model": self.model,
                    "messages": messages,
                }
                
                if (
                   response_format is not None
                   and self.supports_json_schema
                ):
                   payload["response_format"] = response_format

                if (
                   temperature is not None
                    and self.supports_temperature
                ):
                    payload["temperature"] = temperature

                if use_top_p and self.supports_top_p:
                    payload["top_p"] = self.top_p

                if max_tokens is not None:
                    payload["max_tokens"] = max_tokens

                resp = self.client.chat.completions.create(**payload)

                if self.sleep_between_calls > 0:
                    time.sleep(self.sleep_between_calls)

                content = resp.choices[0].message.content
                return content if content is not None else ""

            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(self.retry_sleep_seconds)

        raise RuntimeError(
            f"OpenAICompatibleLLM.chat failed after "
            f"{self.max_retries} attempts using model={self.model}, "
            f"base_url={self.base_url}: {repr(last_err)}" 
        )

def make_llm_from_config(cfg) -> BaseLLM:
    """
    Build an LLM client from GEOMeta config.

    Current supported API type:
      - openai_compatible

    Expected cfg fields:
      - cfg.llm_api_type
      - cfg.llm_api_key
      - cfg.llm_base_url
      - cfg.llm_model
      - cfg.max_retries
      - cfg.retry_sleep_seconds
      - cfg.sleep_between_calls
      - cfg.top_p
    """

    api_type = str(getattr(cfg, "llm_api_type", "openai_compatible")).lower().strip()

    if api_type != "openai_compatible":
        raise ValueError(
            f"Unsupported LLM_API_TYPE={api_type}. "
            "Currently supported: openai_compatible."
        )

    return OpenAICompatibleLLM(
        api_key=getattr(cfg, "llm_api_key", ""),
        model=getattr(cfg, "llm_model", ""),
        base_url=getattr(cfg, "llm_base_url", ""),
        max_retries=getattr(cfg, "max_retries", 3),
        retry_sleep_seconds=getattr(cfg, "retry_sleep_seconds", 2.0),
        sleep_between_calls=getattr(cfg, "sleep_between_calls", 0.0),
        top_p=getattr(cfg, "top_p", 1.0),
        
       supports_temperature=getattr(
           cfg,
           "llm_supports_temperature",
            True,
        ),

       supports_top_p=getattr(
          cfg,
           "llm_supports_top_p",
           True,
        ),
        
        supports_json_schema=getattr(
            cfg,
            "llm_supports_json_schema",
             True,
         ),
    )