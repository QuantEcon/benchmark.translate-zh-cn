"""Tests for the judge command internals."""

from __future__ import annotations

import json

from qebench.commands.judge import _build_matchups, _get_key_term_translations, _load_model_outputs
from qebench.models import Difficulty, Sentence, Term


def _make_term(id: str = "term-001", en: str = "inflation", zh: str = "通货膨胀") -> Term:
    return Term(id=id, en=en, zh=zh, domain="economics", difficulty=Difficulty.intermediate)


def _make_sentence(
    id: str = "sent-001",
    en: str = "Inflation rises.",
    zh: str = "通货膨胀上升。",
    key_terms: list[str] | None = None,
) -> Sentence:
    return Sentence(
        id=id, en=en, zh=zh, domain="economics",
        difficulty=Difficulty.intermediate,
        key_terms=key_terms or [],
    )


class TestLoadModelOutputs:
    def test_empty_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        assert _load_model_outputs() == {}

    def test_no_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path / "nonexistent")
        assert _load_model_outputs() == {}

    def test_loads_jsonl(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        records = [
            {"model": "claude", "entry_id": "term-001", "translated_text": "通胀"},
            {"model": "claude", "entry_id": "term-002", "translated_text": "GDP"},
        ]
        path = tmp_path / "run-1.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

        outputs = _load_model_outputs()
        assert "claude" in outputs
        assert outputs["claude"]["term-001"] == "通胀"
        assert outputs["claude"]["term-002"] == "GDP"

    def test_multiple_models(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)

        (tmp_path / "run-claude.jsonl").write_text(
            json.dumps({"model": "claude", "entry_id": "term-001", "translated_text": "通胀A"}),
            encoding="utf-8",
        )
        (tmp_path / "run-gpt.jsonl").write_text(
            json.dumps({"model": "gpt-4o", "entry_id": "term-001", "translated_text": "通胀B"}),
            encoding="utf-8",
        )

        outputs = _load_model_outputs()
        assert len(outputs) == 2
        assert "claude" in outputs
        assert "gpt-4o" in outputs

    def test_prompt_template_creates_distinct_keys(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        records = [
            {"model": "claude", "prompt_template": "default", "entry_id": "term-001", "translated_text": "通胀A"},
            {"model": "claude", "prompt_template": "academic", "entry_id": "term-001", "translated_text": "通胀B"},
        ]
        path = tmp_path / "run-1.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

        outputs = _load_model_outputs()
        assert "claude:default" in outputs
        assert "claude:academic" in outputs
        assert outputs["claude:default"]["term-001"] == "通胀A"
        assert outputs["claude:academic"]["term-001"] == "通胀B"


class TestBuildMatchups:
    def test_no_model_outputs(self) -> None:
        entries = [_make_term()]
        matchups = _build_matchups(entries, {})
        assert matchups == []

    def test_single_model_vs_reference(self) -> None:
        term = _make_term()
        outputs = {"claude": {"term-001": "通胀"}}
        matchups = _build_matchups([term], outputs)
        assert len(matchups) == 1
        m = matchups[0]
        labels = {m["label_a"], m["label_b"]}
        assert "claude" in labels
        assert "human-reference" in labels

    def test_two_models_paired(self) -> None:
        term = _make_term()
        outputs = {
            "claude": {"term-001": "通胀A"},
            "gpt-4o": {"term-001": "通胀B"},
        }
        matchups = _build_matchups([term], outputs)
        assert len(matchups) == 1
        labels = {matchups[0]["label_a"], matchups[0]["label_b"]}
        assert labels == {"claude", "gpt-4o"}

    def test_skips_entries_without_outputs(self) -> None:
        entries = [_make_term("term-001"), _make_term("term-002")]
        outputs = {"claude": {"term-001": "通胀"}}  # Only term-001 has output
        matchups = _build_matchups(entries, outputs)
        assert len(matchups) == 1
        assert matchups[0]["entry"].id == "term-001"

    def test_identical_translations_can_be_detected(self) -> None:
        """When model output matches reference, translations are identical (#9)."""
        term = _make_term(zh="通货膨胀")
        outputs = {"claude": {"term-001": "通货膨胀"}}
        matchups = _build_matchups([term], outputs)
        assert len(matchups) == 1
        m = matchups[0]
        # One side is the model, other is human-reference — both have same text
        assert m["translation_a"].strip() == m["translation_b"].strip()


class TestGetKeyTermTranslations:
    def test_term_returns_empty(self) -> None:
        term = _make_term()
        assert _get_key_term_translations(term, []) == []

    def test_sentence_with_key_terms(self) -> None:
        terms = [
            _make_term("term-001", "inflation", "通货膨胀"),
            _make_term("term-002", "GDP", "国内生产总值"),
        ]
        sent = _make_sentence(key_terms=["term-001"])
        result = _get_key_term_translations(sent, terms)
        assert result == ["通货膨胀"]

    def test_sentence_no_key_terms(self) -> None:
        sent = _make_sentence(key_terms=[])
        assert _get_key_term_translations(sent, [_make_term()]) == []
