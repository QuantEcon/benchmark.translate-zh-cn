"""Anthropic Claude translation provider."""

from __future__ import annotations

import time
import warnings

from qebench.providers.base import (
    TranslationProvider,
    TranslationResult,
    is_cacheable,
    split_prompt,
)

# Pricing per 1M tokens (USD) — updated as needed
_PRICING: dict[str, tuple[float, float]] = {
    # Current models
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    # Legacy models
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
}

# Prompt-cache pricing, as multiples of the model's base input rate.  Writing
# an entry on the default five-minute TTL costs 1.25x; every later read costs
# 0.1x.  Two requests therefore already beat sending the prefix twice.
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.1


class ClaudeProvider(TranslationProvider):
    """Translation provider using Anthropic's Claude API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        cache: bool = True,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package not installed. Run: uv sync --extra llm"
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or self.default_model
        self._cache = cache

    @property
    def name(self) -> str:
        return "claude"

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-6"

    @property
    def caches_prompts(self) -> bool:
        return self._cache

    def _content_blocks(self, prefix: str, suffix: str, *, cache_prefix: bool) -> list[dict]:
        """Build the user content, with a cache breakpoint when one pays off.

        Without caching the prompt goes out as a single block, byte-identical
        to what a pre-caching run sent, so ``--no-cache`` stays a fair
        comparison.  With caching the same text is split in two at the
        ``{text}`` boundary and only the prefix carries the breakpoint —
        marking the whole prompt would write a new entry per entry_id and
        never read one back.
        """
        if not prefix or not self._cache or not cache_prefix or not is_cacheable(prefix):
            return [{"type": "text", "text": prefix + suffix}]
        return [
            {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": suffix},
        ]

    def translate(
        self,
        text: str,
        *,
        source_lang: str,
        target_lang: str,
        domain: str,
        prompt_template: str,
        model: str | None = None,
        cache_prefix: bool = True,
    ) -> TranslationResult:
        model_id = model or self._model
        prefix, suffix = split_prompt(
            prompt_template,
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            domain=domain,
        )

        start = time.monotonic()
        message = self._client.messages.create(
            model=model_id,
            max_tokens=2048,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": self._content_blocks(prefix, suffix, cache_prefix=cache_prefix),
                }
            ],
        )
        latency_ms = (time.monotonic() - start) * 1000

        translated = message.content[0].text.strip()
        usage = message.usage
        # Anthropic already reports input_tokens as the uncached remainder, so
        # the three counts sum to the whole prompt without adjustment.
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_creation_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

        input_price, output_price = _PRICING.get(model_id, (0.0, 0.0))
        if model_id not in _PRICING:
            warnings.warn(
                f"No pricing data for model '{model_id}'; cost will be $0.00",
                stacklevel=2,
            )
        cost = (
            input_tokens * input_price
            + cache_creation_tokens * input_price * _CACHE_WRITE_MULTIPLIER
            + cache_read_tokens * input_price * _CACHE_READ_MULTIPLIER
            + output_tokens * output_price
        ) / 1_000_000

        return TranslationResult(
            entry_id="",
            source_text=text,
            translated_text=translated,
            model=model_id,
            provider=self.name,
            prompt_template=prompt_template,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
