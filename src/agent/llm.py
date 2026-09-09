"""DeepSeek API client used by keyword generation, note organization, and Q&A."""

from typing import Optional

from openai import OpenAI

from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class DeepSeekClient:
    """Wrapper around DeepSeek's OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        resolved_api_key = DEEPSEEK_API_KEY if api_key is None else api_key
        resolved_base_url = DEEPSEEK_BASE_URL if base_url is None else base_url

        if not resolved_api_key or not resolved_api_key.strip():
            raise ValueError("DEEPSEEK_API_KEY is not configured")

        self.client = OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
        )
        self.model_name = model_name or DEEPSEEK_MODEL

    def generate(self, prompt: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content or ""
