"""Abstract base class for LLM translation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# A stable prefix shorter than this is not worth a cache breakpoint.  The real
# minimum is model-side — 1,024 tokens on Sonnet 4.6, 4,096 on Haiku 4.5 — and
# a provider silently declines to cache below it, so this only keeps pointless
# breakpoints out of the short `default` and `academic` templates.  The
# glossary block that `action-new` carries is around 5,000 tokens, well clear
# of both minimums.
MIN_CACHEABLE_PREFIX_CHARS = 2000


@dataclass
class TranslationResult:
    """Result from a single LLM translation call.

    ``input_tokens`` counts only the prompt tokens billed at the full input
    rate.  Tokens served from — or written to — a prompt cache are reported
    separately, so the whole prompt is always
    ``input_tokens + cache_creation_tokens + cache_read_tokens``.  Providers
    normalise to that convention even when their API reports it differently.
    """

    entry_id: str
    source_text: str
    translated_text: str
    model: str
    provider: str
    prompt_template: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def prompt_tokens(self) -> int:
        """Every prompt token, cached or not — comparable across runs."""
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


def split_prompt(
    prompt_template: str,
    *,
    text: str,
    source_lang: str,
    target_lang: str,
    domain: str,
) -> tuple[str, str]:
    """Render *prompt_template* as a per-run prefix and a per-entry suffix.

    Every shipped template ends with the ``{text}`` placeholder, and everything
    before it is identical for every entry in a run — the rules, and for
    ``action-new`` the whole injected glossary.  Splitting there lets a
    provider mark the prefix as cacheable and re-send only the entry itself.

    ``prefix + suffix`` is exactly the string the un-split
    ``prompt_template.format(...)`` call would have produced, so a provider
    that cannot cache can concatenate the two and send the original prompt.

    Args:
        prompt_template: Template string, glossary already substituted.
        text: The source text for this entry.
        source_lang: Source language code (e.g. 'en').
        target_lang: Target language code (e.g. 'zh-cn').
        domain: Domain hint (e.g. 'economics').

    Returns:
        ``(prefix, suffix)``.  *prefix* is empty when the template opens with
        ``{text}`` or omits it, leaving nothing worth caching.
    """
    fmt = {
        "text": text,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "domain": domain,
    }
    head, separator, tail = prompt_template.partition("{text}")
    if not separator:
        # load_template() rejects templates without {text}, but translate() is
        # also reachable with a raw string.  Nothing splits — cache nothing.
        return "", prompt_template.format(**fmt)

    # `head` cannot contain {text}, so formatting it alone is safe.  The source
    # text is concatenated rather than formatted in, exactly as ``.format()``
    # would substitute it: a paragraph containing ``{math}`` must not be
    # re-processed as a format field.
    return head.format(**fmt), text + tail.format(**fmt)


def is_cacheable(prefix: str) -> bool:
    """True when *prefix* is long enough to be worth a cache breakpoint."""
    return len(prefix) >= MIN_CACHEABLE_PREFIX_CHARS


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
        """Default model identifier, e.g. 'claude-sonnet-4-6'."""

    @property
    def model(self) -> str:
        """Active model identifier (may differ from default if overridden)."""
        return getattr(self, "_model", self.default_model)

    @property
    def caches_prompts(self) -> bool:
        """True when a repeated prompt prefix is cheaper on the second call.

        Providers whose caching is automatic report True as well — the saving
        is the same, and :meth:`translate_batch` warms the cache either way.
        """
        return False

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
        cache_prefix: bool = True,
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
            cache_prefix: Whether this prompt's shared prefix is worth caching.
                :meth:`translate_batch` passes False when no other entry in the
                batch renders the same prefix, so nothing would ever read the
                entry back. Providers that do not cache prompts ignore it.

        Returns:
            TranslationResult with the translation and usage metadata.
        """

    def _cache_groups(
        self,
        texts: list[dict],
        *,
        source_lang: str,
        target_lang: str,
        prompt_template: str,
    ) -> tuple[set[int], list[int]]:
        """Work out which entries share a cacheable prefix.

        Returns ``(shared, warm_up)``: the indices whose prefix at least one
        other entry also renders, and one index per such prefix to translate
        before the rest.  A prefix rendered by a single entry is left out of
        both — caching it would pay the write premium for an entry nothing
        reads back.
        """
        if not self.caches_prompts:
            return set(), []

        groups: dict[str, list[int]] = {}
        for idx, entry in enumerate(texts):
            prefix, _ = split_prompt(
                prompt_template,
                text=entry["text"],
                source_lang=source_lang,
                target_lang=target_lang,
                domain=entry.get("domain", "general"),
            )
            if is_cacheable(prefix):
                groups.setdefault(prefix, []).append(idx)

        repeated = [indices for indices in groups.values() if len(indices) > 1]
        shared = {idx for indices in repeated for idx in indices}
        warm_up = [indices[0] for indices in repeated]
        return shared, warm_up

    def translate_batch(
        self,
        texts: list[dict],
        *,
        source_lang: str,
        target_lang: str,
        prompt_template: str,
        max_workers: int = 10,
        on_complete: Callable[[TranslationResult], None] | None = None,
    ) -> list[TranslationResult]:
        """Translate multiple entries concurrently.

        Default implementation calls translate() via a thread pool.
        Providers can override for batch API support.

        When the provider caches prompts, one entry per distinct prefix is
        translated before the rest fan out.  A cache entry only becomes
        readable once the response that wrote it has begun, so firing the whole
        pool at once would make every request pay the write premium instead of
        one.  Prefixes are grouped rather than assumed identical because
        ``action-new`` interpolates ``{domain}`` ahead of its glossary, giving
        one prefix per domain rather than one per run.

        Args:
            texts: List of dicts with keys: id, text, domain.
            source_lang: Source language code.
            target_lang: Target language code.
            prompt_template: The prompt template string.
            max_workers: Maximum concurrent API calls (default 10).
            on_complete: Optional callback invoked after each translation completes.

        Returns:
            List of TranslationResult objects in the same order as texts.
        """
        results: list[TranslationResult | None] = [None] * len(texts)
        shared, warm_up = self._cache_groups(
            texts, source_lang=source_lang, target_lang=target_lang, prompt_template=prompt_template
        )

        def _translate_one(idx: int) -> TranslationResult:
            entry = texts[idx]
            result = self.translate(
                entry["text"],
                source_lang=source_lang,
                target_lang=target_lang,
                domain=entry.get("domain", "general"),
                prompt_template=prompt_template,
                model=None,
                cache_prefix=idx in shared,
            )
            result.entry_id = entry["id"]
            result.source_text = entry["text"]
            return result

        def _run(indices: list[int]) -> None:
            if not indices:
                return
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_idx = {pool.submit(_translate_one, idx): idx for idx in indices}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    result = future.result()
                    results[idx] = result
                    if on_complete:
                        on_complete(result)

        _run(warm_up)
        _run([idx for idx in range(len(texts)) if idx not in set(warm_up)])

        assert all(r is not None for r in results), "Some translations failed"
        return [r for r in results if r is not None]
