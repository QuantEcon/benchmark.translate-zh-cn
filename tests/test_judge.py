"""Tests for the judge command internals."""

from __future__ import annotations

import json

import pytest

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


class TestBomHandling:
    """Raised on #33: only export.py had moved to utf-8-sig."""

    def test_bom_does_not_cost_the_file_its_first_record(self, tmp_path, monkeypatch) -> None:
        """A Windows BOM leaves \\ufeff on line 1, so record 1 parsed as malformed."""
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        records = [
            {"model": "claude", "entry_id": "term-001", "translated_text": "通胀"},
            {"model": "claude", "entry_id": "term-002", "translated_text": "GDP"},
        ]
        (tmp_path / "run-1.jsonl").write_text(
            "﻿" + "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
            encoding="utf-8",
        )
        outputs = _load_model_outputs()
        assert outputs == {"claude": {"term-001": "通胀", "term-002": "GDP"}}


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

    def test_skips_malformed_line_and_keeps_rest_of_file(self, tmp_path, monkeypatch, capsys) -> None:
        """One bad line must not discard the good records around it."""
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        path = tmp_path / "run-1.jsonl"
        path.write_text(
            '{"model": "claude", "entry_id": "term-001", "translated_text": "通胀"}\n'
            "{not json at all\n"
            "\n"
            '{"model": "claude", "prompt_template": "academic", '
            '"entry_id": "term-002", "translated_text": "GDP"}\n',
            encoding="utf-8",
        )

        outputs = _load_model_outputs()
        assert outputs == {
            "claude": {"term-001": "通胀"},
            "claude:academic": {"term-002": "GDP"},
        }
        out = capsys.readouterr().out
        assert "warning" in out
        assert "run-1.jsonl" in out
        assert "line 2" in out

    def test_skips_unusable_records(self, tmp_path, monkeypatch) -> None:
        """A bare list, string or null parses fine but has no .get — it must be skipped.

        The non-empty ``entry_id``/``translated_text`` rule still applies to
        the records that are objects.
        """
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        path = tmp_path / "run-1.jsonl"
        path.write_text(
            "[1, 2, 3]\n"
            '"just a string"\n'
            "null\n"
            '{"model": "claude", "entry_id": "", "translated_text": "通胀"}\n'
            '{"model": "claude", "entry_id": "term-002", "translated_text": ""}\n'
            '{"model": "claude", "entry_id": "term-003", "translated_text": "通胀"}\n',
            encoding="utf-8",
        )

        assert _load_model_outputs() == {"claude": {"term-003": "通胀"}}

    def test_skips_non_string_values(self, tmp_path, monkeypatch, capsys) -> None:
        """A non-string entry_id/translated_text must not reach the returned dict.

        The declared return type is ``dict[str, dict[str, str]]`` and
        ``_build_matchups`` calls ``.strip()`` on the translation, so letting a
        number through only moves the crash further from the corrupt file.
        """
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        (tmp_path / "run-1.jsonl").write_text(
            '{"model": "claude", "entry_id": "term-001", "translated_text": 123}\n'
            '{"model": "claude", "entry_id": ["term-002"], "translated_text": "通胀"}\n'
            '{"model": "claude", "entry_id": "term-003", "translated_text": {"zh": "通胀"}}\n'
            '{"model": "claude", "entry_id": "term-004", "translated_text": "通胀"}\n',
            encoding="utf-8",
        )

        outputs = _load_model_outputs()
        assert outputs == {"claude": {"term-004": "通胀"}}
        assert all(
            isinstance(k, str) and isinstance(v, str)
            for by_id in outputs.values()
            for k, v in by_id.items()
        )
        assert capsys.readouterr().out.count("warning") == 3

    def test_warns_about_non_object_records(self, tmp_path, monkeypatch, capsys) -> None:
        """A valid-JSON-but-wrong-shape line is corruption; drop it loudly, not silently."""
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        (tmp_path / "run-1.jsonl").write_text("[1, 2, 3]\n", encoding="utf-8")

        assert _load_model_outputs() == {}
        out = capsys.readouterr().out
        assert "warning" in out
        assert "run-1.jsonl" in out
        assert "line 1" in out

    def test_undecodable_file_does_not_lose_other_models(self, tmp_path, monkeypatch, capsys) -> None:
        """A contributor's GBK-saved file must not cost every other model its outputs.

        UnicodeDecodeError comes from the file iterator, not from json.loads,
        so guarding only the parse leaves it uncaught — and it is a ValueError,
        so ``except (json.JSONDecodeError, OSError)`` would not catch it either.
        """
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        (tmp_path / "run-claude.jsonl").write_text(
            json.dumps({"model": "claude", "entry_id": "term-001", "translated_text": "通胀"}),
            encoding="utf-8",
        )
        gbk = tmp_path / "run-gpt.jsonl"
        gbk.write_bytes(
            json.dumps(
                {"model": "gpt-4o", "entry_id": "term-001", "translated_text": "通货膨胀率上涨"},
                ensure_ascii=False,
            ).encode("gbk")
            + b"\n"
        )
        # Precondition: those bytes really are undecodable as UTF-8.
        with pytest.raises(UnicodeDecodeError):
            gbk.read_text(encoding="utf-8")

        assert _load_model_outputs() == {"claude": {"term-001": "通胀"}}
        out = capsys.readouterr().out
        assert "warning" in out
        assert "run-gpt.jsonl" in out

    def test_unreadable_file_does_not_lose_other_models(self, tmp_path, monkeypatch, capsys) -> None:
        """A file that cannot be opened at all is skipped, not fatal."""
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        (tmp_path / "run-claude.jsonl").write_text(
            json.dumps({"model": "claude", "entry_id": "term-001", "translated_text": "通胀A"}),
            encoding="utf-8",
        )
        (tmp_path / "run-gpt.jsonl").write_text(
            json.dumps({"model": "gpt-4o", "entry_id": "term-001", "translated_text": "通胀B"}),
            encoding="utf-8",
        )

        real_open = open

        def fail_on_gpt(path, *args, **kwargs):
            if str(path).endswith("run-gpt.jsonl"):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail_on_gpt)
        assert _load_model_outputs() == {"claude": {"term-001": "通胀A"}}
        out = capsys.readouterr().out
        assert "warning" in out
        assert "run-gpt.jsonl" in out

    def test_only_bad_files_returns_empty_dict(self, tmp_path, monkeypatch) -> None:
        """A directory of nothing but broken files yields {} rather than raising."""
        monkeypatch.setattr("qebench.commands.judge.MODEL_OUTPUTS_DIR", tmp_path)
        (tmp_path / "run-broken.jsonl").write_text("{not json at all\n[1, 2, 3]\n", encoding="utf-8")
        (tmp_path / "run-gbk.jsonl").write_bytes(
            json.dumps(
                {"model": "gpt-4o", "entry_id": "t", "translated_text": "通货膨胀率上涨"},
                ensure_ascii=False,
            ).encode("gbk")
        )

        assert _load_model_outputs() == {}


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
