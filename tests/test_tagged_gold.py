"""Gold answers read from a tagged PDF's structure tree (src/benchmark/tagged_gold.py)."""
from pathlib import Path

from src.benchmark import tagged_gold as t

DEMO = Path(__file__).resolve().parents[1] / "frontend/public/demo/download/document.pdf"  # passes PDF/UA-1


def test_reads_headings_and_alt_text_and_strips_the_tags(tmp_path):
    gold = t.read_gold(DEMO)
    assert gold["headings"][1] == {"level": 2, "text": "Abstract", "page": 1}
    assert len(gold["headings"]) >= 10 and gold["tables"] >= 1
    assert any("bar chart" in f["alt"].lower() for f in gold["figures"])
    assert t.worth_it(gold, True) == [] and "does not pass PDF/UA-1" in t.worth_it(gold, False)

    bare = tmp_path / "bare.pdf"
    t.strip_tags(DEMO, bare)
    assert t.read_gold(bare)["headings"] == []


def test_filler_alt_text_is_not_gold():
    assert not t.real_alt("image1.png") and not t.real_alt("Figure 3") and not t.real_alt("logo")
    assert t.real_alt("Line graph of height gain by age")


def test_scoring_ignores_spacing_and_heading_convention():
    gold = {"headings": [{"level": 1, "text": "C H A P T E R 5", "page": 1}, {"level": 1, "text": "Growth", "page": 1},
                         {"level": 2, "text": "Bones", "page": 2}, {"level": 1, "text": "Missing", "page": 3}],
            "figures": [{"alt": "Line graph of height gain by age", "page": 1}], "tables": 0, "header_cells": 0}
    s = t.score(gold, [(2, "Chapter 5"), (2, "Growth"), (3, "Bones"), (2, "Age in years")], ["Graph of height gain"])
    h = s["headings"]
    assert (h["matched"], h["gold"], h["rawrs"]) == (3, 4, 4)
    assert h["level_accuracy"] == 0.0 and h["step_agreement"] == 1.0  # one H1 per section vs per document
    assert s["alt_text"]["word_recall"] == 0.6 and s["alt_text"]["rawrs_mean_words"] == 4.0
