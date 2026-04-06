"""OpenAI translation provider."""

from __future__ import annotations

import time
import warnings

from qebench.providers.base import TranslationProvider, TranslationResult

# Pricing per 1M tokens (USD) — updated as needed
_PRICING: dict[str, tuple[float, float]] = {
    # Current models
    "gpt-5.4": (2.50, 15.0),
    "gpt-5.4-mini": (0.75, 4.50),
    # Legacy models
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}


class OpenAIProvider(TranslationProvider):
    """Translation provider using OpenAI's Chat Completions API."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai package not installed. Run: uv sync --extra llm"
            ) from exc

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model or self.default_model

    @property
    def name(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return "gpt-5.4"

    def translate(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        domain: str,
        prompt_template: str,
        model: str | None = None,
    ) -> TranslationResult:
        model_id = model or self._model
        prompt = prompt_template.format(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            domain=domain,
        )

        start = time.monotonic()
        response = self._client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0,
        )
        latency_ms = (time.monotonic() - start) * 1000

        translated = (response.choices[0].message.content or "").strip()
        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        input_price, output_price = _PRICING.get(model_id, (0.0, 0.0))
        if model_id not in _PRICING:
            warnings.warn(
                f"No pricing data for model '{model_id}'; cost will be $0.00",
                stacklevel=2,
            )
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000

        return TranslationResult(
            entry_id="",
            source_text=text,
            translated_text=translated,
            model=model_id,
            provider=self.name,
            prompt_template=prompt_template,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
