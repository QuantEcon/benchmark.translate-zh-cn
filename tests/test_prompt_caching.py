"""Tests for prompt splitting and provider-side prompt caching."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from qebench.providers.base import (
    MIN_CACHEABLE_PREFIX_CHARS,
    TranslationProvider,
    TranslationResult,
    is_cacheable,
    split_prompt,
)
from qebench.providers.claude import ClaudeProvider
from qebench.providers.prompts import list_templates, load_template

FMT = {"source_lang": "en", "target_lang": "zh-cn", "domain": "economics"}


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass
class StubUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class StubBlock:
    text: str


@dataclass
class StubMessage:
    content: list
    usage: StubUsage


class StubMessages:
    """Records every request and replays a canned usage object."""

    def __init__(self, usage: StubUsage | None = None, reply: str = "译文") -> None:
        self.calls: list[dict] = []
        self._usage = usage or StubUsage(input_tokens=10, output_tokens=5)
        self._reply = reply

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return StubMessage(content=[StubBlock(self._reply)], usage=self._usage)

    @property
    def content_blocks(self) -> list[dict]:
        return self.calls[-1]["messages"][0]["content"]


def make_claude(usage: StubUsage | None = None, *, cache: bool = True, model: str | None = None):
    """Build a provider around a stub client, without the anthropic SDK.

    ``__init__`` is bypassed because it imports ``anthropic``, which CI does
    not install — it runs ``uv sync --extra dev``, and the SDKs live in the
    ``llm`` extra. Nothing under test touches the SDK; the only thing that
    would is the client the stub replaces.
    """
    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._model = model or provider.default_model
    provider._cache = cache
    stub = StubMessages(usage)
    provider._client = type("StubClient", (), {"messages": stub})()
    return provider, stub


# ---------------------------------------------------------------------------
# split_prompt
# ---------------------------------------------------------------------------

class TestSplitPrompt:
    def test_prefix_and_suffix_rejoin_to_the_unsplit_prompt(self) -> None:
        template = "Rules for {domain}, {source_lang}→{target_lang}.\n\nText:\n{text}"
        prefix, suffix = split_prompt(template, text="inflation", **FMT)

        assert prefix + suffix == template.format(text="inflation", **FMT)

    @pytest.mark.parametrize("name", sorted(list_templates()))
    def test_every_shipped_template_rejoins(self, name: str) -> None:
        template = load_template(name).replace("{glossary}", "  Inflation → 通货膨胀")
        prefix, suffix = split_prompt(template, text="inflation", **FMT)

        assert prefix + suffix == template.format(text="inflation", **FMT)

    def test_prefix_carries_the_shared_rules_and_suffix_the_entry(self) -> None:
        template = "Domain: {domain}\n\nText:\n{text}"
        prefix, suffix = split_prompt(template, text="inflation", **FMT)

        assert prefix == "Domain: economics\n\nText:\n"
        assert suffix == "inflation"

    def test_braces_in_the_source_text_are_not_re_formatted(self) -> None:
        """A paragraph holding ```{math}``` must survive verbatim."""
        text = "```{math}\nx_{t+1} = f(x_t)\n```"
        prefix, suffix = split_prompt("Domain: {domain}\n\n{text}", text=text, **FMT)

        assert suffix == text
        assert "{math}" in prefix + suffix

    def test_escaped_braces_in_the_prefix_render_literally(self) -> None:
        template = "Never mix ```{{math}}``` fences.\n\n{text}"
        prefix, suffix = split_prompt(template, text="inflation", **FMT)

        assert "```{math}```" in prefix
        assert prefix + suffix == template.format(text="inflation", **FMT)

    def test_repeated_text_placeholder_is_substituted_in_both_places(self) -> None:
        template = "First: {text}\nAgain: {text}"
        prefix, suffix = split_prompt(template, text="inflation", **FMT)

        assert prefix == "First: "
        assert suffix == "inflation\nAgain: inflation"

    def test_template_without_the_placeholder_has_no_cacheable_prefix(self) -> None:
        prefix, suffix = split_prompt("Translate for {domain}.", text="inflation", **FMT)

        assert prefix == ""
        assert suffix == "Translate for economics."

    def test_template_opening_with_the_placeholder_has_no_prefix(self) -> None:
        prefix, suffix = split_prompt("{text} — translate.", text="inflation", **FMT)

        assert prefix == ""
        assert suffix == "inflation — translate."


class TestIsCacheable:
    def test_short_prefix_is_not_worth_a_breakpoint(self) -> None:
        assert not is_cacheable("x" * (MIN_CACHEABLE_PREFIX_CHARS - 1))

    def test_prefix_at_the_threshold_is(self) -> None:
        assert is_cacheable("x" * MIN_CACHEABLE_PREFIX_CHARS)

    def test_the_action_new_glossary_block_clears_the_threshold(self) -> None:
        """The prompt this whole feature exists for has to qualify."""
        glossary = "\n".join(f"  Term {i} → 术语{i}" for i in range(357))
        template = load_template("action-new").replace("{glossary}", glossary)
        prefix, _ = split_prompt(template, text="inflation", **FMT)

        assert is_cacheable(prefix)

    def test_the_short_templates_do_not(self) -> None:
        for name in ("default", "academic"):
            prefix, _ = split_prompt(load_template(name), text="inflation", **FMT)
            assert not is_cacheable(prefix), name


# ---------------------------------------------------------------------------
# Claude request shape
# ---------------------------------------------------------------------------

class TestClaudeContentBlocks:
    def _translate(self, provider, template: str) -> None:
        provider.translate("inflation", prompt_template=template, **FMT)

    def test_long_prefix_is_split_and_marked(self) -> None:
        provider, stub = make_claude()
        template = "R" * MIN_CACHEABLE_PREFIX_CHARS + "\n{text}"
        self._translate(provider, template)

        blocks = stub.content_blocks
        assert len(blocks) == 2
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in blocks[1]
        assert blocks[1]["text"] == "inflation"

    def test_the_split_preserves_the_prompt_text(self) -> None:
        provider, stub = make_claude()
        template = "R" * MIN_CACHEABLE_PREFIX_CHARS + "\n{text}"
        self._translate(provider, template)

        joined = "".join(block["text"] for block in stub.content_blocks)
        assert joined == template.format(text="inflation", **FMT)

    def test_short_prefix_stays_one_unmarked_block(self) -> None:
        provider, stub = make_claude()
        self._translate(provider, "Domain: {domain}\n{text}")

        blocks = stub.content_blocks
        assert len(blocks) == 1
        assert "cache_control" not in blocks[0]

    def test_no_cache_sends_the_original_single_block(self) -> None:
        """--no-cache has to stay a fair comparison with a pre-caching run."""
        template = "R" * MIN_CACHEABLE_PREFIX_CHARS + "\n{text}"
        provider, stub = make_claude(cache=False)
        self._translate(provider, template)

        blocks = stub.content_blocks
        assert len(blocks) == 1
        assert blocks[0]["text"] == template.format(text="inflation", **FMT)

    def test_caches_prompts_follows_the_flag(self) -> None:
        assert make_claude(cache=True)[0].caches_prompts
        assert not make_claude(cache=False)[0].caches_prompts


class TestClaudeUsageAndCost:
    def test_cache_tokens_are_reported_separately(self) -> None:
        usage = StubUsage(
            input_tokens=12,
            output_tokens=8,
            cache_creation_input_tokens=5000,
            cache_read_input_tokens=0,
        )
        provider, _ = make_claude(usage, model="claude-sonnet-4-6")
        result = provider.translate("inflation", prompt_template="{text}", **FMT)

        assert result.input_tokens == 12
        assert result.cache_creation_tokens == 5000
        assert result.cache_read_tokens == 0
        assert result.prompt_tokens == 5012

    def test_a_write_is_billed_at_1_25x_the_input_rate(self) -> None:
        usage = StubUsage(input_tokens=0, output_tokens=0, cache_creation_input_tokens=1_000_000)
        provider, _ = make_claude(usage, model="claude-sonnet-4-6")
        result = provider.translate("inflation", prompt_template="{text}", **FMT)

        assert result.cost_usd == pytest.approx(3.0 * 1.25)

    def test_a_read_is_billed_at_0_1x_the_input_rate(self) -> None:
        usage = StubUsage(input_tokens=0, output_tokens=0, cache_read_input_tokens=1_000_000)
        provider, _ = make_claude(usage, model="claude-sonnet-4-6")
        result = provider.translate("inflation", prompt_template="{text}", **FMT)

        assert result.cost_usd == pytest.approx(3.0 * 0.1)

    def test_uncached_cost_is_unchanged(self) -> None:
        usage = StubUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        provider, _ = make_claude(usage, model="claude-sonnet-4-6")
        result = provider.translate("inflation", prompt_template="{text}", **FMT)

        assert result.cost_usd == pytest.approx(18.0)

    def test_usage_without_cache_fields_reads_as_zero(self) -> None:
        """An older SDK response object has neither attribute."""

        @dataclass
        class BareUsage:
            input_tokens: int = 7
            output_tokens: int = 3

        provider, _ = make_claude(model="claude-sonnet-4-6")
        provider._client.messages._usage = BareUsage()
        result = provider.translate("inflation", prompt_template="{text}", **FMT)

        assert result.cache_creation_tokens == 0
        assert result.cache_read_tokens == 0


# ---------------------------------------------------------------------------
# Batch warm-up
# ---------------------------------------------------------------------------

class RecordingProvider(TranslationProvider):
    """Records the order translations start in and the hint each one got."""

    def __init__(self, *, caches: bool) -> None:
        self._caches = caches
        self._lock = threading.Lock()
        self.started: list[str] = []
        self.hints: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return "recording"

    @property
    def default_model(self) -> str:
        return "recording-v1"

    @property
    def caches_prompts(self) -> bool:
        return self._caches

    def translate(
        self, text, *, source_lang, target_lang, domain, prompt_template, model=None, cache_prefix=True
    ):
        with self._lock:
            self.started.append(text)
            self.hints[text] = cache_prefix
        return TranslationResult(
            entry_id="",
            source_text=text,
            translated_text=f"[{text}]",
            model=self.default_model,
            provider=self.name,
            prompt_template=prompt_template,
        )


def _entries(n: int, *, domain: str = "economics", offset: int = 0) -> list[dict]:
    return [
        {"id": f"term-{i:03d}", "text": f"term {i}", "domain": domain}
        for i in range(offset, offset + n)
    ]


class TestBatchPrefixGrouping:
    """`action-new` renders one prefix per domain, so grouping is per domain."""

    CACHEABLE = "R" * MIN_CACHEABLE_PREFIX_CHARS + "\nDomain: {domain}\n{text}"
    SHORT = "Domain: {domain}\n{text}"

    def _batch(self, provider, template, entries, on_complete=None):
        return provider.translate_batch(
            entries,
            source_lang="en",
            target_lang="zh-cn",
            prompt_template=template,
            max_workers=4,
            on_complete=on_complete,
        )

    def test_one_entry_per_domain_runs_before_the_rest(self) -> None:
        entries = _entries(4, domain="economics") + _entries(4, domain="finance", offset=4)
        provider = RecordingProvider(caches=True)

        self._batch(provider, self.CACHEABLE, entries)

        # Wave two is not submitted until wave one's pool has drained, so the
        # first two starts are exactly one per domain.
        assert set(provider.started[:2]) == {"term 0", "term 4"}
        assert len(provider.started) == 8

    def test_a_single_domain_warms_exactly_one_call(self) -> None:
        provider = RecordingProvider(caches=True)

        self._batch(provider, self.CACHEABLE, _entries(8))

        assert provider.started[0] == "term 0"
        assert set(provider.started[1:]) == {f"term {i}" for i in range(1, 8)}

    def test_every_entry_of_a_repeated_prefix_is_marked_cacheable(self) -> None:
        provider = RecordingProvider(caches=True)

        self._batch(provider, self.CACHEABLE, _entries(8))

        assert all(provider.hints.values())

    def test_a_domain_with_one_entry_is_not_cached(self) -> None:
        """Marking it would buy a write premium nothing ever reads back."""
        entries = _entries(4, domain="economics") + _entries(1, domain="game-theory", offset=9)
        provider = RecordingProvider(caches=True)

        self._batch(provider, self.CACHEABLE, entries)

        assert provider.hints["term 9"] is False
        assert provider.hints["term 0"] is True
        assert "term 9" not in provider.started[:1]

    def test_nothing_is_cached_when_the_provider_does_not(self) -> None:
        provider = RecordingProvider(caches=False)

        self._batch(provider, self.CACHEABLE, _entries(8))

        assert not any(provider.hints.values())

    def test_nothing_is_cached_when_the_prefix_is_too_short(self) -> None:
        provider = RecordingProvider(caches=True)

        self._batch(provider, self.SHORT, _entries(8))

        assert not any(provider.hints.values())

    def test_order_and_ids_survive_the_reordering(self) -> None:
        entries = _entries(4, domain="economics") + _entries(4, domain="finance", offset=4)
        provider = RecordingProvider(caches=True)

        results = self._batch(provider, self.CACHEABLE, entries)

        assert [r.entry_id for r in results] == [e["id"] for e in entries]
        assert [r.source_text for r in results] == [e["text"] for e in entries]

    def test_on_complete_fires_once_per_entry_across_both_waves(self) -> None:
        provider = RecordingProvider(caches=True)
        seen: list[str] = []

        self._batch(provider, self.CACHEABLE, _entries(8), on_complete=lambda r: seen.append(r.entry_id))

        assert sorted(seen) == [f"term-{i:03d}" for i in range(8)]

    def test_a_single_entry_batch_still_works(self) -> None:
        provider = RecordingProvider(caches=True)

        results = self._batch(provider, self.CACHEABLE, _entries(1))

        assert len(results) == 1
        assert results[0].entry_id == "term-000"
        assert provider.hints["term 0"] is False

    def test_an_empty_batch_is_a_no_op(self) -> None:
        provider = RecordingProvider(caches=True)

        assert self._batch(provider, self.CACHEABLE, []) == []


class TestClaudeHonoursTheHint:
    def test_cache_prefix_false_sends_one_block(self) -> None:
        provider, stub = make_claude()
        template = "R" * MIN_CACHEABLE_PREFIX_CHARS + "\n{text}"

        provider.translate("inflation", prompt_template=template, cache_prefix=False, **FMT)

        assert len(stub.content_blocks) == 1

    def test_cache_prefix_true_sends_a_marked_block(self) -> None:
        provider, stub = make_claude()
        template = "R" * MIN_CACHEABLE_PREFIX_CHARS + "\n{text}"

        provider.translate("inflation", prompt_template=template, cache_prefix=True, **FMT)

        assert stub.content_blocks[0]["cache_control"] == {"type": "ephemeral"}


class TestPromptTokens:
    def test_sums_billed_and_cached_prompt_tokens(self) -> None:
        result = TranslationResult(
            entry_id="term-001",
            source_text="inflation",
            translated_text="通货膨胀",
            model="claude-sonnet-4-6",
            provider="claude",
            prompt_template="action-new",
            input_tokens=13,
            output_tokens=6,
            cache_creation_tokens=100,
            cache_read_tokens=5000,
        )

        assert result.prompt_tokens == 5113

    def test_defaults_to_zero_cache_tokens(self) -> None:
        result = TranslationResult(
            entry_id="term-001",
            source_text="inflation",
            translated_text="通货膨胀",
            model="claude-sonnet-4-6",
            provider="claude",
            prompt_template="default",
            input_tokens=13,
        )

        assert result.cache_creation_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.prompt_tokens == 13
