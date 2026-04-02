"""Tests for the provider base classes and prompt loading."""

from __future__ import annotations

from qebench.providers.base import TranslationProvider, TranslationResult


class DummyProvider(TranslationProvider):
    """Concrete test provider that returns the source text as-is."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def default_model(self) -> str:
        return "dummy-v1"

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
        return TranslationResult(
            entry_id="",
            source_text=text,
            translated_text=f"[translated] {text}",
            model=model or self.default_model,
            provider=self.name,
            prompt_template=prompt_template,
            input_tokens=10,
            output_tokens=5,
        )


class TestTranslationResult:
    def test_defaults(self) -> None:
        r = TranslationResult(
            entry_id="term-001",
            source_text="hello",
            translated_text="你好",
            model="test",
            provider="test",
            prompt_template="default",
        )
        assert r.cost_usd == 0.0
        assert r.latency_ms == 0.0
        assert r.metadata == {}

    def test_fields(self) -> None:
        r = TranslationResult(
            entry_id="term-001",
            source_text="inflation",
            translated_text="通货膨胀",
            model="claude-sonnet-4-20250514",
            provider="claude",
            prompt_template="default",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.0006,
            latency_ms=450.5,
        )
        assert r.entry_id == "term-001"
        assert r.input_tokens == 100
        assert r.cost_usd == 0.0006


class TestProviderInterface:
    def test_name_and_model(self) -> None:
        p = DummyProvider()
        assert p.name == "dummy"
        assert p.default_model == "dummy-v1"

    def test_translate(self) -> None:
        p = DummyProvider()
        result = p.translate(
            "inflation",
            source_lang="en",
            target_lang="zh-cn",
            domain="economics",
            prompt_template="Translate {text}",
        )
        assert result.translated_text == "[translated] inflation"
        assert result.provider == "dummy"

    def test_translate_batch(self) -> None:
        p = DummyProvider()
        texts = [
            {"id": "term-001", "text": "inflation", "domain": "economics"},
            {"id": "term-002", "text": "GDP", "domain": "economics"},
        ]
        results = p.translate_batch(
            texts,
            source_lang="en",
            target_lang="zh-cn",
            prompt_template="Translate {text} ({domain})",
        )
        assert len(results) == 2
        assert results[0].entry_id == "term-001"
        assert results[1].entry_id == "term-002"
        assert "[translated]" in results[0].translated_text
