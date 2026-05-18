from __future__ import annotations

import time
from typing import List, Dict, Any

from openai import AzureOpenAI


class AzureLLM:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str,
        max_retries: int = 3,
        retry_sleep_seconds: float = 2.0,
        sleep_between_calls: float = 0.0,
        top_p: float = 1.0,
    ):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.deployment = deployment.strip()
        self.api_version = api_version.strip()
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds
        self.sleep_between_calls = sleep_between_calls
        self.top_p = top_p

        self.client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.endpoint,
            api_version=self.api_version,
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        last_err = None
        deployment_name = str(self.deployment).lower()

        for attempt in range(1, self.max_retries + 1):
            try:
                payload = {
                    "model": self.deployment,
                    "messages": messages,
                }

                if temperature is not None and not deployment_name.startswith("gpt-5"):
                    payload["temperature"] = temperature

                if not deployment_name.startswith("gpt-5"):
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
            f"AzureLLM.chat failed after {self.max_retries} attempts: {repr(last_err)}"
        )