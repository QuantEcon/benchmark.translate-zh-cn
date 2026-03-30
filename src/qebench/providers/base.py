"""Abstract base class for LLM translation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslationResult:
    """Result from a single LLM translation call."""

    entry_id: str
    source_text: str
    translated_text: str
    model: str
    provider: str
    prompt_template: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class TranslationProvider(ABC):
    """Abstract interface for LLM translation providers.

    Each provider wraps a specific API (Anthropic, OpenAI, etc.) and
    translates a single text from source to target language.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider name, e.g. 'claude' or 'openai'."""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model identifier, e.g. 'claude-sonnet-4-20250514'."""

    @property
    def model(self) -> str:
        """Active model identifier (may differ from default if overridden)."""
        return getattr(self, "_model", self.default_model)

    @abstractmethod
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
        """Translate a single text.

        Args:
            text: Source text to translate.
            source_lang: Source language code (e.g. 'en').
            target_lang: Target language code (e.g. 'zh-cn').
            domain: Domain hint (e.g. 'economics').
            prompt_template: The prompt template string with {text}, {source_lang},
                {target_lang}, {domain} placeholders.
            model: Override the default model. None uses self.default_model.

        Returns:
            TranslationResult with the translation and usage metadata.
        """

    def translate_batch(
        self,
        texts: list[dict],
        *,
        source_lang: str,
        target_lang: str,
        prompt_template: str,
    ) -> list[TranslationResult]:
        """Translate multiple entries sequentially.

        Default implementation calls translate() in a loop.
        Providers can override for batch API support.

        Args:
            texts: List of dicts with keys: id, text, domain.
            source_lang: Source language code.
            target_lang: Target language code.
            prompt_template: The prompt template string.

        Returns:
            List of TranslationResult objects.
        """
        results = []
        for entry in texts:
            result = self.translate(
                entry["text"],
                source_lang=source_lang,
                target_lang=target_lang,
                domain=entry.get("domain", "general"),
                prompt_template=prompt_template,
                model=None,
            )
            result.entry_id = entry["id"]
            result.source_text = entry["text"]
            results.append(result)
        return results
