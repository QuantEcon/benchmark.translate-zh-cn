"""Tests for the glossary sync-back candidate script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from qebench.models import Term

# scripts/ is not on the import path, so load the script by file location.
# It must be registered in sys.modules before exec_module for @dataclass to resolve.
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "glossary_syncback.py"
_spec = importlib.util.spec_from_file_location("glossary_syncback", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
gs = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gs
_spec.loader.exec_module(gs)


# --- helpers -----------------------------------------------------------------


def make_term(
    term_id: str,
    en: str,
    zh: str,
    *,
    domain: str = "economics",
    alternatives: list[str] | None = None,
) -> Term:
    """Build a benchmark Term for use as a fixture."""
    return Term(
        id=term_id,
        en=en,
        zh=zh,
        domain=domain,
        difficulty="intermediate",
        alternatives=alternatives or [],
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    """Write records as JSONL, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def attempt(entry_id: str, username: str, text: str, confidence: int | None = 4) -> Any:
    """Build a HumanAttempt record."""
    return gs.HumanAttempt(entry_id=entry_id, username=username, attempt=text, reference="", confidence=confidence)


def output(entry_id: str, text: str, *, model: str = "claude-sonnet-4-6", prompt: str = "default") -> Any:
    """Build a ModelOutput record."""
    return gs.ModelOutput(
        entry_id=entry_id,
        translated_text=text,
        model=model,
        prompt_template=prompt,
        entry_type="terms",
    )


GLOSSARY = [
    {"en": "Bellman equation", "zh-cn": "贝尔曼方程", "context": "dynamic programming"},
    {"en": "Arrow securities", "zh-cn": "阿罗证券", "context": "finance"},
]


# --- normalisation -----------------------------------------------------------


class TestNormaliseZh:
    def test_strips_whitespace(self) -> None:
        assert gs.normalise_zh("  价值 函数\n") == "价值函数"

    def test_strips_ascii_punctuation(self) -> None:
        assert gs.normalise_zh("价值函数.") == "价值函数"
        assert gs.normalise_zh('"价值函数"') == "价值函数"

    def test_strips_fullwidth_punctuation(self) -> None:
        assert gs.normalise_zh("价值函数。") == "价值函数"
        assert gs.normalise_zh("（价值函数）、") == "价值函数"
        assert gs.normalise_zh("“价值函数”") == "价值函数"

    def test_variants_compare_equal(self) -> None:
        assert gs.normalise_zh(" 贝尔曼方程。") == gs.normalise_zh("贝尔曼方程")

    def test_keeps_distinct_translations_distinct(self) -> None:
        assert gs.normalise_zh("阿罗证券") != gs.normalise_zh("箭头证券")

    def test_empty_string(self) -> None:
        assert gs.normalise_zh("") == ""

    def test_punctuation_only(self) -> None:
        assert gs.normalise_zh("。，！") == ""


class TestNormaliseEn:
    def test_case_insensitive(self) -> None:
        assert gs.normalise_en("Bellman Equation") == gs.normalise_en("bellman equation")

    def test_whitespace_normalised(self) -> None:
        assert gs.normalise_en("  Bellman   equation \n") == "bellman equation"


class TestFirstLine:
    def test_single_line(self) -> None:
        assert gs.first_line("贝尔曼方程") == "贝尔曼方程"

    def test_skips_leading_blank_lines(self) -> None:
        assert gs.first_line("\n\n  贝尔曼方程\n注释：...") == "贝尔曼方程"

    def test_empty(self) -> None:
        assert gs.first_line("\n \n") == ""


# --- loaders -----------------------------------------------------------------


class TestLoadHumanAttempts:
    def test_username_from_file_stem(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        write_jsonl(
            tmp_path / "alice.jsonl",
            [{"entry_id": "term-001", "attempt": "贝尔曼方程", "reference": "贝尔曼方程", "confidence": 5}],
        )
        monkeypatch.setattr(gs, "TRANSLATIONS_DIR", tmp_path)
        attempts = gs.load_human_attempts()
        assert len(attempts) == 1
        assert attempts[0].username == "alice"
        assert attempts[0].confidence == 5

    def test_skips_malformed_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "bob.jsonl"
        path.write_text(
            '{"entry_id": "term-001", "attempt": "贝尔曼方程"}\nnot json\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(gs, "TRANSLATIONS_DIR", tmp_path)
        assert len(gs.load_human_attempts()) == 1

    def test_missing_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gs, "TRANSLATIONS_DIR", tmp_path / "nope")
        assert gs.load_human_attempts() == []


class TestLoadModelOutputs:
    def test_reads_run_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        write_jsonl(
            tmp_path / "claude-run.jsonl",
            [
                {
                    "entry_id": "term-002",
                    "translated_text": "箭头证券",
                    "model": "claude-haiku-4-5",
                    "prompt_template": "default",
                    "entry_type": "terms",
                }
            ],
        )
        monkeypatch.setattr(gs, "MODEL_OUTPUTS_DIR", tmp_path)
        outputs = gs.load_model_outputs()
        assert len(outputs) == 1
        assert outputs[0].run_label == "claude-haiku-4-5/default"

    def test_missing_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gs, "MODEL_OUTPUTS_DIR", tmp_path / "nope")
        assert gs.load_model_outputs() == []


# --- glossary index ----------------------------------------------------------


class TestBuildGlossaryIndex:
    def test_keys_are_normalised(self) -> None:
        index = gs.build_glossary_index([{"en": "  Bellman   Equation ", "zh-cn": "贝尔曼方程"}])
        assert "bellman equation" in index

    def test_skips_entries_without_translation(self) -> None:
        assert gs.build_glossary_index([{"en": "Orphan"}]) == {}

    def test_first_duplicate_wins(self) -> None:
        index = gs.build_glossary_index([
            {"en": "GDP", "zh-cn": "国内生产总值"},
            {"en": "gdp", "zh-cn": "GDP"},
        ])
        assert gs.glossary_zh(index["gdp"]) == "国内生产总值"


# --- corrections -------------------------------------------------------------


class TestFindCorrections:
    index = gs.build_glossary_index(GLOSSARY)
    terms = [make_term("term-001", "Bellman equation", "贝尔曼方程", domain="dynamic-programming")]

    def test_two_annotators_produce_a_correction(self) -> None:
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式", confidence=5),
            attempt("term-001", "bob", "贝尔曼等式。", confidence=4),
        ]
        found = gs.find_corrections(self.terms, self.index, attempts)
        assert len(found) == 1
        assert found[0]["en"] == "Bellman equation"
        assert found[0]["glossary_zh"] == "贝尔曼方程"
        assert found[0]["proposed_zh"] == "贝尔曼等式"
        assert found[0]["annotators"] == ["alice", "bob"]
        assert found[0]["confidences"] == {"alice": 5, "bob": 4}

    def test_one_annotator_produces_nothing(self) -> None:
        attempts = [attempt("term-001", "alice", "贝尔曼等式")]
        assert gs.find_corrections(self.terms, self.index, attempts) == []

    def test_repeat_attempts_by_one_annotator_produce_nothing(self) -> None:
        """Distinct usernames are counted, not attempts."""
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式"),
            attempt("term-001", "alice", "贝尔曼等式"),
            attempt("term-001", "alice", "贝尔曼等式"),
        ]
        assert gs.find_corrections(self.terms, self.index, attempts) == []

    def test_proposed_zh_is_the_most_frequent_raw_spelling(self) -> None:
        """Not merely the first-seen spelling of the winning normalised group."""
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式。"),
            attempt("term-001", "bob", "贝尔曼等式"),
            attempt("term-001", "carol", "贝尔曼等式"),
        ]
        found = gs.find_corrections(self.terms, self.index, attempts)
        assert found[0]["proposed_zh"] == "贝尔曼等式"
        assert found[0]["annotators"] == ["alice", "bob", "carol"]

    def test_min_annotators_option_is_honoured(self) -> None:
        attempts = [attempt("term-001", "alice", "贝尔曼等式")]
        found = gs.find_corrections(self.terms, self.index, attempts, min_annotators=1)
        assert len(found) == 1

    def test_agreement_with_glossary_is_not_a_correction(self) -> None:
        attempts = [
            attempt("term-001", "alice", "贝尔曼方程"),
            attempt("term-001", "bob", " 贝尔曼方程。"),
        ]
        assert gs.find_corrections(self.terms, self.index, attempts) == []

    def test_disagreeing_annotators_need_the_same_translation(self) -> None:
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式"),
            attempt("term-001", "bob", "贝尔曼方程式"),
        ]
        assert gs.find_corrections(self.terms, self.index, attempts) == []

    def test_terms_outside_the_glossary_are_skipped(self) -> None:
        terms = [make_term("term-009", "Lake model", "湖泊模型")]
        attempts = [
            attempt("term-009", "alice", "劳动力池模型"),
            attempt("term-009", "bob", "劳动力池模型"),
        ]
        assert gs.find_corrections(terms, self.index, attempts) == []

    def test_english_matching_is_case_insensitive(self) -> None:
        """A differently-cased/spaced headword still resolves to the glossary entry."""
        terms = [make_term("term-001", "BELLMAN  Equation", "贝尔曼方程")]
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式"),
            attempt("term-001", "bob", "贝尔曼等式"),
        ]
        found = gs.find_corrections(terms, self.index, attempts)
        assert len(found) == 1
        assert found[0]["glossary_zh"] == "贝尔曼方程"


# --- additions ---------------------------------------------------------------


class TestFindAdditions:
    index = gs.build_glossary_index(GLOSSARY)

    def test_verified_missing_term_is_proposed(self) -> None:
        terms = [
            make_term("term-009", "Lake model", "劳动力池模型", domain="macroeconomics", alternatives=["湖泊模型"])
        ]
        attempts = [attempt("term-009", "alice", "劳动力池模型。", confidence=5)]
        found = gs.find_additions(terms, self.index, attempts)
        assert len(found) == 1
        assert found[0]["en"] == "Lake model"
        assert found[0]["proposed_zh"] == "劳动力池模型"
        assert found[0]["domain"] == "macroeconomics"
        assert found[0]["alternatives"] == ["湖泊模型"]
        assert found[0]["evidence"]["annotators"] == ["alice"]
        assert found[0]["evidence"]["matching_attempts"] == 1

    def test_unverified_missing_term_is_skipped(self) -> None:
        terms = [make_term("term-009", "Lake model", "劳动力池模型")]
        assert gs.find_additions(terms, self.index, []) == []

    def test_disagreeing_attempt_is_not_verification(self) -> None:
        terms = [make_term("term-009", "Lake model", "劳动力池模型")]
        attempts = [attempt("term-009", "alice", "湖泊模型")]
        assert gs.find_additions(terms, self.index, attempts) == []

    def test_term_already_in_glossary_is_skipped(self) -> None:
        terms = [make_term("term-001", "bellman  EQUATION", "贝尔曼方程")]
        attempts = [attempt("term-001", "alice", "贝尔曼方程")]
        assert gs.find_additions(terms, self.index, attempts) == []

    def test_total_attempts_counts_all_evidence(self) -> None:
        terms = [make_term("term-009", "Lake model", "劳动力池模型")]
        attempts = [
            attempt("term-009", "alice", "劳动力池模型"),
            attempt("term-009", "bob", "湖泊模型"),
        ]
        found = gs.find_additions(terms, self.index, attempts)
        assert found[0]["evidence"]["matching_attempts"] == 1
        assert found[0]["evidence"]["total_attempts"] == 2


# --- needs context -----------------------------------------------------------


class TestFindNeedsContext:
    index = gs.build_glossary_index(GLOSSARY)
    terms = [make_term("term-002", "Arrow securities", "阿罗证券", domain="finance")]

    def test_low_compliance_is_flagged(self) -> None:
        outputs = [
            output("term-002", "箭头证券", model="haiku", prompt="default"),
            output("term-002", "箭头证券", model="haiku", prompt="academic"),
            output("term-002", "箭状证券", model="sonnet", prompt="default"),
            output("term-002", "阿罗证券", model="sonnet", prompt="academic"),
        ]
        found = gs.find_needs_context(self.terms, self.index, outputs)
        assert len(found) == 1
        assert found[0]["glossary_zh"] == "阿罗证券"
        assert found[0]["compliant_runs"] == 1
        assert found[0]["total_runs"] == 4
        assert found[0]["compliance"] == 0.25
        assert found[0]["models_produced"][0] == {
            "zh": "箭头证券",
            "runs": 2,
            "sources": ["haiku/academic", "haiku/default"],
        }

    def test_compliant_term_is_not_flagged(self) -> None:
        outputs = [
            output("term-002", "阿罗证券"),
            output("term-002", "阿罗证券。"),
            output("term-002", "阿罗式证券"),
        ]
        assert gs.find_needs_context(self.terms, self.index, outputs) == []

    def test_containment_counts_anywhere_in_a_multiline_output(self) -> None:
        outputs = [
            output("term-002", "翻译如下：\n阿罗证券\n\n注：金融术语。"),
            output("term-002", "箭头证券"),
        ]
        assert gs.find_needs_context(self.terms, self.index, outputs) == []

    def test_first_line_is_reported_for_noncompliant_output(self) -> None:
        outputs = [output("term-002", "箭头证券\n（说明：直译自 Arrow）")]
        found = gs.find_needs_context(self.terms, self.index, outputs)
        assert found[0]["models_produced"][0]["zh"] == "箭头证券"

    def test_alternatives_are_grouped_by_normalised_form(self) -> None:
        """Punctuation/spacing variants of one wrong translation are ONE row, not several."""
        outputs = [
            output("term-002", "箭头证券", model="haiku", prompt="default"),
            output("term-002", "箭头证券。", model="haiku", prompt="academic"),
            output("term-002", "# 箭头证券", model="sonnet", prompt="default"),
        ]
        found = gs.find_needs_context(self.terms, self.index, outputs)
        assert len(found[0]["models_produced"]) == 1
        assert found[0]["models_produced"][0]["runs"] == 3
        assert found[0]["models_produced"][0]["sources"] == [
            "haiku/academic",
            "haiku/default",
            "sonnet/default",
        ]

    def test_most_frequent_raw_spelling_is_reported(self) -> None:
        outputs = [
            output("term-002", "箭头证券。"),
            output("term-002", "箭头证券"),
            output("term-002", "箭头证券"),
        ]
        found = gs.find_needs_context(self.terms, self.index, outputs)
        assert found[0]["models_produced"][0]["zh"] == "箭头证券"

    def test_alternatives_ranked_by_total_runs(self) -> None:
        outputs = [
            output("term-002", "箭状证券"),
            output("term-002", "箭头证券"),
            output("term-002", "箭头证券。"),
        ]
        found = gs.find_needs_context(self.terms, self.index, outputs)
        assert [(m["zh"], m["runs"]) for m in found[0]["models_produced"]] == [
            ("箭头证券", 2),
            ("箭状证券", 1),
        ]

    def test_terms_without_model_runs_are_skipped(self) -> None:
        assert gs.find_needs_context(self.terms, self.index, []) == []

    def test_terms_outside_the_glossary_are_skipped(self) -> None:
        terms = [make_term("term-009", "Lake model", "劳动力池模型")]
        outputs = [output("term-009", "湖泊模型")]
        assert gs.find_needs_context(terms, self.index, outputs) == []

    def test_ranked_worst_first(self) -> None:
        terms = [
            make_term("term-001", "Bellman equation", "贝尔曼方程"),
            make_term("term-002", "Arrow securities", "阿罗证券"),
        ]
        outputs = [
            # Bellman: 1/2 compliant is above threshold, so drop to 1/4.
            output("term-001", "贝尔曼方程"),
            output("term-001", "贝尔曼等式"),
            output("term-001", "贝尔曼等式"),
            output("term-001", "贝尔曼等式"),
            # Arrow: 0/2 compliant — worse.
            output("term-002", "箭头证券"),
            output("term-002", "箭头证券"),
        ]
        found = gs.find_needs_context(terms, self.index, outputs)
        assert [c["en"] for c in found] == ["Arrow securities", "Bellman equation"]
        assert found[0]["compliance"] == 0.0
        assert found[1]["compliance"] == 0.25


# --- report ------------------------------------------------------------------


class TestBuildReport:
    def test_all_three_categories(self) -> None:
        terms = [
            make_term("term-001", "Bellman equation", "贝尔曼方程", domain="dynamic-programming"),
            make_term("term-002", "Arrow securities", "阿罗证券", domain="finance"),
            make_term("term-009", "Lake model", "劳动力池模型", domain="macroeconomics"),
        ]
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式"),
            attempt("term-001", "bob", "贝尔曼等式"),
            attempt("term-009", "alice", "劳动力池模型"),
        ]
        outputs = [output("term-002", "箭头证券"), output("term-002", "箭状证券")]

        report = gs.build_report(GLOSSARY, terms, attempts, outputs)
        assert report["counts"]["corrections"] == 1
        assert report["counts"]["additions"] == 1
        assert report["counts"]["needs_context"] == 1
        assert report["min_annotators"] == 2
        assert report["counts"]["glossary_terms"] == 2

    def test_markdown_renders_empty_report(self) -> None:
        report = gs.build_report(GLOSSARY, [], [], [])
        markdown = gs.render_markdown(report)
        assert "# Glossary sync-back candidates" in markdown
        assert markdown.count("_No candidates._") == 3


class TestWriteReports:
    def test_writes_json_markdown_and_gitkeep(self, tmp_path: Path) -> None:
        report = gs.build_report(GLOSSARY, [], [], [])
        json_path, md_path = gs.write_reports(report, tmp_path / "syncback")
        assert json_path.exists()
        assert md_path.exists()
        assert (tmp_path / "syncback" / ".gitkeep").exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["counts"]["corrections"] == 0

    def test_json_keeps_chinese_unescaped(self, tmp_path: Path) -> None:
        """ensure_ascii=False — the report must be readable CJK, not \\uXXXX escapes."""
        terms = [make_term("term-001", "Bellman equation", "贝尔曼方程")]
        attempts = [
            attempt("term-001", "alice", "贝尔曼等式"),
            attempt("term-001", "bob", "贝尔曼等式"),
        ]
        report = gs.build_report(GLOSSARY, terms, attempts, [])
        json_path, md_path = gs.write_reports(report, tmp_path / "syncback")
        raw = json_path.read_text(encoding="utf-8")
        assert "贝尔曼等式" in raw
        assert "\\u8d1d" not in raw
        assert "贝尔曼等式" in md_path.read_text(encoding="utf-8")


class TestMain:
    def test_end_to_end_with_synthetic_fixtures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        translations = tmp_path / "translations"
        model_outputs = tmp_path / "model-outputs"
        write_jsonl(
            translations / "alice.jsonl",
            [
                {"entry_id": "term-001", "attempt": "贝尔曼等式", "reference": "贝尔曼方程", "confidence": 5},
                {"entry_id": "term-009", "attempt": "劳动力池模型", "reference": "劳动力池模型", "confidence": 4},
            ],
        )
        write_jsonl(
            translations / "bob.jsonl",
            [{"entry_id": "term-001", "attempt": "贝尔曼等式。", "reference": "贝尔曼方程", "confidence": 4}],
        )
        write_jsonl(
            model_outputs / "run.jsonl",
            [
                {
                    "entry_id": "term-002",
                    "translated_text": "箭头证券",
                    "model": "haiku",
                    "prompt_template": "default",
                    "entry_type": "terms",
                }
            ],
        )

        terms = [
            make_term("term-001", "Bellman equation", "贝尔曼方程"),
            make_term("term-002", "Arrow securities", "阿罗证券"),
            make_term("term-009", "Lake model", "劳动力池模型"),
        ]
        monkeypatch.setattr(gs, "TRANSLATIONS_DIR", translations)
        monkeypatch.setattr(gs, "MODEL_OUTPUTS_DIR", model_outputs)
        monkeypatch.setattr(gs, "load_glossary", lambda: GLOSSARY)
        monkeypatch.setattr(gs, "load_terms", lambda: terms)

        out_dir = tmp_path / "out"
        monkeypatch.setattr("sys.argv", ["glossary_syncback.py", "--output-dir", str(out_dir)])
        gs.main()

        report = json.loads((out_dir / "glossary-syncback.json").read_text(encoding="utf-8"))
        assert report["counts"] == {
            "glossary_terms": 2,
            "benchmark_terms": 3,
            "human_attempts": 3,
            "model_outputs": 1,
            "corrections": 1,
            "additions": 1,
            "needs_context": 1,
        }
        markdown = (out_dir / "glossary-syncback.md").read_text(encoding="utf-8")
        assert "贝尔曼等式" in markdown
        assert "Lake model" in markdown
        assert "箭头证券" in markdown

    def test_min_annotators_flag_changes_the_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        translations = tmp_path / "translations"
        write_jsonl(
            translations / "alice.jsonl",
            [{"entry_id": "term-001", "attempt": "贝尔曼等式", "reference": "贝尔曼方程", "confidence": 5}],
        )
        monkeypatch.setattr(gs, "TRANSLATIONS_DIR", translations)
        monkeypatch.setattr(gs, "MODEL_OUTPUTS_DIR", tmp_path / "missing")
        monkeypatch.setattr(gs, "load_glossary", lambda: GLOSSARY)
        monkeypatch.setattr(gs, "load_terms", lambda: [make_term("term-001", "Bellman equation", "贝尔曼方程")])

        out_dir = tmp_path / "out"
        monkeypatch.setattr(
            "sys.argv",
            ["glossary_syncback.py", "--output-dir", str(out_dir), "--min-annotators", "1"],
        )
        gs.main()

        report = json.loads((out_dir / "glossary-syncback.json").read_text(encoding="utf-8"))
        assert report["min_annotators"] == 1
        assert report["counts"]["corrections"] == 1

    def test_rejects_zero_min_annotators(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["glossary_syncback.py", "--output-dir", str(tmp_path / "out"), "--min-annotators", "0"],
        )
        with pytest.raises(SystemExit):
            gs.main()
