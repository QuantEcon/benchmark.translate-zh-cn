"""Anthropic Claude translation provider."""

from __future__ import annotations

import time

from qebench.providers.base import TranslationProvider, TranslationResult

# Pricing per 1M tokens (USD) — updated as needed
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-3-20250122": (0.80, 4.0),
}


class ClaudeProvider(TranslationProvider):
    """Translation provider using Anthropic's Claude API."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package not installed. Run: uv sync --extra llm"
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or self.default_model

    @property
    def name(self) -> str:
        return "claude"

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-20250514"

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
        message = self._client.messages.create(
            model=model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000

        translated = message.content[0].text.strip()
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        input_price, output_price = _PRICING.get(model_id, (0.0, 0.0))
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
