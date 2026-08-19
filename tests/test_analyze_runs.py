"""Tests for the model-output run aggregation script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# scripts/ is not a package, so load the script by path.  The module has to be
# registered in sys.modules before exec_module() so its dataclasses resolve.
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "analyze_runs.py"
_spec = importlib.util.spec_from_file_location("analyze_runs", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
analyze_runs = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = analyze_runs
_spec.loader.exec_module(analyze_runs)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_record(
    entry_id: str,
    *,
    source_text: str = "Bellman equation",
    translated_text: str = "贝尔曼方程",
    model: str = "claude-sonnet-4-6",
    prompt_template: str = "default",
    entry_type: str = "terms",
    input_tokens: int = 10,
    output_tokens: int = 5,
    cost_usd: float = 0.001,
    latency_ms: float = 1000.0,
    formatting: dict | None = None,
) -> dict:
    """Build one run record, matching the shape written by ``qebench run``."""
    record = {
        "entry_id": entry_id,
        "source_text": source_text,
        "translated_text": translated_text,
        "model": model,
        "provider": "claude",
        "prompt_template": prompt_template,
        "entry_type": entry_type,
        "domain": "dynamic-programming",
        "difficulty": "intermediate",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
    }
    if formatting is not None:
        record["formatting"] = formatting
    return record


def passing_formatting(**overrides) -> dict:
    """A formatting dict where every check passes, before *overrides*."""
    scores = {
        "directive_balance": True,
        "fence_consistency": True,
        "code_block_integrity": True,
        "fullwidth_punctuation": 1.0,
        "directive_spacing": 1.0,
    }
    scores.update(overrides)
    return scores


def write_run(directory: Path, name: str, records: list[dict]) -> Path:
    """Write *records* as a JSONL run file and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def find_row(rows: list[dict], run: str) -> dict:
    """Return the single row whose ``run`` label matches."""
    matches = [row for row in rows if row["run"] == run]
    assert len(matches) == 1, f"expected one row for {run!r}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestLoading:
    def test_groups_by_model_prompt_and_type(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("term-001"), make_record("term-002")])
        write_run(tmp_path, "run-b", [make_record("sent-001", entry_type="sentences")])
        write_run(tmp_path, "run-c", [make_record("term-001", prompt_template="academic")])

        runs = analyze_runs.load_directory(tmp_path).runs

        assert [(r.model, r.prompt_template, r.entry_type, len(r.records)) for r in runs] == [
            ("claude-sonnet-4-6", "academic", "terms", 1),
            ("claude-sonnet-4-6", "default", "terms", 2),
            ("claude-sonnet-4-6", "default", "sentences", 1),
        ]

    def test_type_filter_keeps_one_entry_type(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("term-001")])
        write_run(tmp_path, "run-b", [make_record("para-001", entry_type="paragraphs")])

        runs = analyze_runs.load_directory(tmp_path, entry_type="paragraphs").runs

        assert len(runs) == 1
        assert runs[0].entry_type == "paragraphs"
        assert [r.entry_id for r in runs[0].records] == ["para-001"]

    def test_entry_type_inferred_from_id_prefix(self, tmp_path: Path) -> None:
        legacy = make_record("term-001")
        del legacy["entry_type"]
        write_run(tmp_path, "april", [legacy])

        runs = analyze_runs.load_directory(tmp_path).runs

        assert runs[0].entry_type == "terms"

    def test_repeated_combination_merges_and_flags_duplicates(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("term-001")])
        write_run(tmp_path, "run-b", [make_record("term-001"), make_record("term-002")])

        runs = analyze_runs.load_directory(tmp_path).runs

        assert len(runs) == 1
        assert len(runs[0].records) == 3
        assert runs[0].duplicate_entry_ids == 1
        assert runs[0].files == ["run-a.jsonl", "run-b.jsonl"]


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

class TestCostAggregation:
    def test_totals_and_mean_latency(self, tmp_path: Path) -> None:
        write_run(
            tmp_path,
            "run-a",
            [
                make_record("term-001", input_tokens=40, output_tokens=10, cost_usd=0.0002, latency_ms=1000.0),
                make_record("term-002", input_tokens=60, output_tokens=20, cost_usd=0.0004, latency_ms=2000.0),
                make_record("term-003", input_tokens=100, output_tokens=30, cost_usd=0.0006, latency_ms=3000.0),
            ],
        )

        rows = analyze_runs.analyse(tmp_path)["cost"]

        assert len(rows) == 1
        row = rows[0]
        assert row["entries"] == 3
        assert row["input_tokens"] == 200
        assert row["output_tokens"] == 60
        assert row["total_tokens"] == 260
        assert row["cost_usd"] == pytest.approx(0.0012)
        assert row["mean_latency_ms"] == pytest.approx(2000.0)

    def test_costs_are_not_pooled_across_runs(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("term-001", cost_usd=0.01)])
        write_run(tmp_path, "run-b", [make_record("term-001", prompt_template="academic", cost_usd=0.02)])

        rows = analyze_runs.analyse(tmp_path)["cost"]

        assert find_row(rows, "claude-sonnet-4-6 / default / terms")["cost_usd"] == pytest.approx(0.01)
        assert find_row(rows, "claude-sonnet-4-6 / academic / terms")["cost_usd"] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class TestFormattingAggregation:
    def test_pass_rates_and_means_with_mixed_results(self, tmp_path: Path) -> None:
        write_run(
            tmp_path,
            "run-a",
            [
                make_record("para-001", entry_type="paragraphs", formatting=passing_formatting()),
                make_record(
                    "para-002",
                    entry_type="paragraphs",
                    formatting=passing_formatting(fence_consistency=False, fullwidth_punctuation=0.5),
                ),
                make_record(
                    "para-003",
                    entry_type="paragraphs",
                    formatting=passing_formatting(fence_consistency=False, directive_spacing=0.0),
                ),
                make_record(
                    "para-004",
                    entry_type="paragraphs",
                    formatting=passing_formatting(directive_balance=False, fullwidth_punctuation=0.5),
                ),
            ],
        )

        row = analyze_runs.analyse(tmp_path)["formatting"][0]

        assert row["records"] == 4
        assert row["pass_rates"]["directive_balance"] == pytest.approx(75.0)
        assert row["pass_rates"]["fence_consistency"] == pytest.approx(50.0)
        assert row["pass_rates"]["code_block_integrity"] == pytest.approx(100.0)
        assert row["means"]["fullwidth_punctuation"] == pytest.approx(0.75)
        assert row["means"]["directive_spacing"] == pytest.approx(0.75)
        assert row["passed"] == {"directive_balance": 3, "fence_consistency": 2, "code_block_integrity": 4}
        assert row["retroactive"] is False

    def test_failure_detail_caps_entry_ids(self, tmp_path: Path) -> None:
        failed = passing_formatting(fence_consistency=False)
        records = [
            make_record(f"para-{i:03d}", entry_type="paragraphs", formatting=failed) for i in range(1, 8)
        ]
        write_run(tmp_path, "run-a", records)

        row = analyze_runs.analyse(tmp_path)["failures"][0]

        assert row["failures"]["fence_consistency"]["count"] == 7
        assert row["failures"]["fence_consistency"]["entry_ids"] == [
            "para-001",
            "para-002",
            "para-003",
            "para-004",
            "para-005",
        ]
        assert row["failures"]["directive_balance"]["count"] == 0
        assert row["failures"]["directive_balance"]["entry_ids"] == []
        assert row["total_failures"] == 7

    def test_max_failures_is_configurable(self, tmp_path: Path) -> None:
        failed = passing_formatting(directive_balance=False)
        records = [
            make_record(f"para-{i:03d}", entry_type="paragraphs", formatting=failed) for i in range(1, 5)
        ]
        write_run(tmp_path, "run-a", records)

        row = analyze_runs.analyse(tmp_path, max_failures=2)["failures"][0]

        assert row["failures"]["directive_balance"]["entry_ids"] == ["para-001", "para-002"]


class TestRetroactiveScoring:
    def test_missing_formatting_is_computed_on_the_fly(self, tmp_path: Path) -> None:
        # Source has one fenced block, the translation drops the closing fence:
        # directive_balance and code_block_integrity must both fail.
        broken = make_record(
            "para-001",
            entry_type="paragraphs",
            source_text="Text\n\n```python\nx = 1\n```\n",
            translated_text="文本\n\n```python\nx = 1\n",
        )
        clean = make_record(
            "para-002",
            entry_type="paragraphs",
            source_text="Text\n\n```python\nx = 1\n```\n",
            translated_text="文本。\n\n```python\nx = 1\n```\n",
        )
        write_run(tmp_path, "april", [broken, clean])

        aggregates = analyze_runs.analyse(tmp_path)
        row = aggregates["formatting"][0]

        assert row["retroactive"] is True
        assert aggregates["retroactive_runs"] == ["claude-sonnet-4-6 / default / paragraphs"]
        assert row["pass_rates"]["directive_balance"] == pytest.approx(50.0)
        assert row["pass_rates"]["code_block_integrity"] == pytest.approx(50.0)
        assert aggregates["failures"][0]["failures"]["directive_balance"]["entry_ids"] == ["para-001"]

    def test_stored_formatting_is_used_verbatim(self, tmp_path: Path) -> None:
        # A stored dict that disagrees with a fresh score proves it is not recomputed.
        write_run(
            tmp_path,
            "run-a",
            [make_record("term-001", formatting=passing_formatting(directive_balance=False))],
        )

        aggregates = analyze_runs.analyse(tmp_path)

        assert aggregates["formatting"][0]["retroactive"] is False
        assert aggregates["formatting"][0]["pass_rates"]["directive_balance"] == pytest.approx(0.0)
        assert aggregates["retroactive_runs"] == []

    def test_run_is_flagged_when_only_some_records_are_rescored(self, tmp_path: Path) -> None:
        # A file appended to after the formatting field landed mixes both shapes;
        # the run must still be flagged, otherwise the footnote understates it.
        write_run(
            tmp_path,
            "mixed",
            [
                make_record("term-001", formatting=passing_formatting()),
                make_record("term-002"),
            ],
        )

        aggregates = analyze_runs.analyse(tmp_path)

        assert aggregates["formatting"][0]["retroactive"] is True
        assert aggregates["retroactive_runs"] == ["claude-sonnet-4-6 / default / terms"]

    def test_incomplete_formatting_dict_is_rescored(self, tmp_path: Path) -> None:
        write_run(
            tmp_path,
            "run-a",
            [make_record("term-001", formatting={"directive_balance": True})],
        )

        row = analyze_runs.analyse(tmp_path)["formatting"][0]

        assert row["retroactive"] is True
        assert row["means"]["directive_spacing"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------

class TestPairwiseAgreement:
    def test_known_overlap(self, tmp_path: Path) -> None:
        write_run(
            tmp_path,
            "run-a",
            [
                make_record("term-001", translated_text="贝尔曼方程"),
                make_record("term-002", translated_text="马尔可夫链"),
                make_record("term-003", translated_text="折现因子"),
                make_record("term-004", translated_text="仅在 A 中"),
            ],
        )
        write_run(
            tmp_path,
            "run-b",
            [
                # Same first line, padded with whitespace — normalisation must match it.
                make_record("term-001", prompt_template="academic", translated_text="  贝尔曼方程  "),
                make_record("term-002", prompt_template="academic", translated_text="马尔可夫过程"),
                make_record("term-003", prompt_template="academic", translated_text="折现因子\n(注：另一种译法)"),
                make_record("term-005", prompt_template="academic", translated_text="仅在 B 中"),
            ],
        )

        rows = analyze_runs.analyse(tmp_path)["agreement"]

        assert len(rows) == 1
        row = rows[0]
        assert row["entry_type"] == "terms"
        assert row["shared"] == 3
        assert row["agree"] == 2
        assert row["rate"] == pytest.approx(2 / 3, abs=1e-4)

    def test_only_same_entry_type_is_compared(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("sent-001", entry_type="sentences")])
        write_run(tmp_path, "run-b", [make_record("sent-001", entry_type="sentences", prompt_template="academic")])
        write_run(tmp_path, "run-c", [make_record("para-001", entry_type="paragraphs")])
        write_run(tmp_path, "run-d", [make_record("para-001", entry_type="paragraphs", prompt_template="academic")])

        rows = analyze_runs.analyse(tmp_path)["agreement"]

        assert {row["entry_type"] for row in rows} == {"sentences", "paragraphs"}
        assert len(rows) == 2
        assert all(row["shared"] == 1 for row in rows)

    def test_no_shared_ids_reports_no_rate(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("term-001")])
        write_run(tmp_path, "run-b", [make_record("term-002", prompt_template="academic")])

        row = analyze_runs.analyse(tmp_path)["agreement"][0]

        assert row["shared"] == 0
        assert row["agree"] == 0
        assert row["rate"] is None

    def test_single_run_has_no_pairs(self, tmp_path: Path) -> None:
        write_run(tmp_path, "run-a", [make_record("term-001")])

        assert analyze_runs.analyse(tmp_path)["agreement"] == []


# ---------------------------------------------------------------------------
# Verbosity
# ---------------------------------------------------------------------------

class TestVerbosity:
    def test_counts_multi_line_translations(self, tmp_path: Path) -> None:
        write_run(
            tmp_path,
            "run-a",
            [
                make_record("term-001", translated_text="贝尔曼方程"),
                # Blank lines alone do not make a record verbose.
                make_record("term-002", translated_text="马尔可夫链\n\n   \n"),
                make_record("term-003", translated_text="累积分布函数\n\n注：CCDF 指互补累积分布函数。"),
                make_record("term-004", translated_text="讲座\n这个术语有歧义，\n需要更多上下文。"),
            ],
        )

        row = analyze_runs.analyse(tmp_path)["verbosity"][0]

        assert row["records"] == 4
        assert row["multiline"] == 2
        assert row["pct"] == pytest.approx(50.0)
        assert row["entry_ids"] == ["term-003", "term-004"]

    def test_example_ids_are_capped(self, tmp_path: Path) -> None:
        write_run(
            tmp_path,
            "run-a",
            [make_record(f"term-{i:03d}", translated_text="讲座\n需要更多上下文。") for i in range(1, 8)],
        )

        row = analyze_runs.analyse(tmp_path, max_failures=2)["verbosity"][0]

        assert row["multiline"] == 7
        assert row["entry_ids"] == ["term-001", "term-002"]


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------

class TestGuardRails:
    def test_malformed_lines_are_skipped_with_a_message(self, tmp_path: Path) -> None:
        path = write_run(tmp_path, "run-a", [make_record("term-001"), make_record("term-002")])
        with open(path, "a", encoding="utf-8") as f:
            f.write("{not valid json\n")
            f.write("\n")
            f.write('["a list, not an object"]\n')
            f.write('{"model": "claude-sonnet-4-6"}\n')

        aggregates = analyze_runs.analyse(tmp_path)

        assert aggregates["cost"][0]["entries"] == 2
        assert len(aggregates["skipped"]) == 3
        assert any("malformed JSON" in message for message in aggregates["skipped"])
        assert any("expected a JSON object" in message for message in aggregates["skipped"])
        assert any("no entry_id" in message for message in aggregates["skipped"])
        assert all(message.startswith("run-a.jsonl:") for message in aggregates["skipped"])

    def test_empty_run_file_produces_no_runs(self, tmp_path: Path) -> None:
        write_run(tmp_path, "empty", [])

        aggregates = analyze_runs.analyse(tmp_path)

        assert aggregates["runs"] == []
        assert aggregates["cost"] == []
        assert aggregates["skipped"] == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        aggregates = analyze_runs.analyse(tmp_path)

        assert aggregates["runs"] == []
        assert aggregates["cost"] == []
        assert aggregates["formatting"] == []
        assert aggregates["failures"] == []
        assert aggregates["agreement"] == []
        assert aggregates["verbosity"] == []
        assert aggregates["retroactive_runs"] == []
        assert "No run records found." in analyze_runs.render_markdown(aggregates)

    def test_missing_directory_is_reported_not_raised(self, tmp_path: Path) -> None:
        aggregates = analyze_runs.analyse(tmp_path / "nope")

        assert aggregates["runs"] == []
        assert any("directory not found" in message for message in aggregates["skipped"])

    def test_markdown_explains_why_no_runs_were_found(self, tmp_path: Path) -> None:
        # Without this the report is an unexplained "No run records found." even
        # when every line was dropped, or the directory does not exist at all.
        path = write_run(tmp_path, "run-a", [])
        with open(path, "a", encoding="utf-8") as f:
            f.write("{not valid json\n")

        report = analyze_runs.render_markdown(analyze_runs.analyse(tmp_path))

        assert "No run records found." in report
        assert "## Skipped Lines" in report
        assert "malformed JSON" in report

        missing = analyze_runs.render_markdown(analyze_runs.analyse(tmp_path / "nope"))
        assert "directory not found" in missing

    def test_non_utf8_file_does_not_abort_the_other_runs(self, tmp_path: Path) -> None:
        write_run(tmp_path, "good", [make_record("term-001")])
        record = json.dumps(make_record("term-002"), ensure_ascii=False)
        (tmp_path / "gbk.jsonl").write_bytes(record.encode("gbk") + b"\n")

        aggregates = analyze_runs.analyse(tmp_path)

        assert aggregates["cost"][0]["entries"] == 1
        assert any("unreadable" in message for message in aggregates["skipped"])
        assert any(message.startswith("gbk.jsonl:") for message in aggregates["skipped"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_json_dump_matches_aggregates(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        run_dir = tmp_path / "runs"
        write_run(run_dir, "run-a", [make_record("term-001"), make_record("sent-001", entry_type="sentences")])
        out_path = tmp_path / "out" / "aggregates.json"

        exit_code = analyze_runs.main(["--dir", str(run_dir), "--type", "terms", "--json", str(out_path)])

        assert exit_code == 0
        dumped = json.loads(out_path.read_text(encoding="utf-8"))
        assert dumped["entry_type_filter"] == "terms"
        assert [row["run"] for row in dumped["cost"]] == ["claude-sonnet-4-6 / default / terms"]
        assert dumped == analyze_runs.analyse(run_dir, entry_type="terms")

        captured = capsys.readouterr()
        assert "| Run | Type | Entries |" in captured.out
        assert "## Formatting" in captured.out

    def test_markdown_reports_retroactive_runs(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        legacy = make_record("term-001")
        del legacy["entry_type"]
        write_run(tmp_path, "april", [legacy])

        analyze_runs.main(["--dir", str(tmp_path)])

        assert "Scored retroactively" in capsys.readouterr().out
