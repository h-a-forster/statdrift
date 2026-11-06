"""Name matching and section tiers in release notes."""

from __future__ import annotations

from statdrift import notes

NOTES = """==========================
SciPy 9.9.0 Release Notes
==========================

************
New features
************

``scipy.stats`` improvements
============================
- `scipy.stats.ttest_ind_from_stats` got faster.
- `scipy.stats.mstats.kruskal` handles masks.

******************************
Backwards incompatible changes
******************************
- `scipy.stats.rankdata` now returns floats.

*******
Authors
*******
* Ann Anderson
* anderson (GitHub handle)

************************
Issues closed for 9.9.0
************************
* `#1 <url>`__: BUG: stats.wilcoxon: wrong p
"""


def tiers(fn):
    found = notes.tiers_naming(fn, [NOTES])
    return {tier for tier, lines in found.items() if lines}


def test_word_boundaries_and_tiers():
    assert tiers("scipy.stats.rankdata") == {notes.ANY, notes.NARRATIVE, notes.COMPATIBILITY}
    assert tiers("scipy.stats.wilcoxon") == {notes.ANY}
    assert tiers("scipy.stats.ttest_ind") == set()  # ttest_ind_from_stats is another function


def test_author_list_is_not_a_mention():
    assert tiers("scipy.stats.anderson") == set()


def test_mstats_mentions_do_not_count_for_the_main_function_or_back():
    assert tiers("scipy.stats.mstats.kruskal") == {notes.ANY, notes.NARRATIVE}
    assert tiers("scipy.stats.kruskal") == set()
    assert tiers("scipy.stats.mstats.rankdata") == set()


def test_methods_use_the_distribution_name():
    assert notes.short_name("scipy.stats.multinomial.pmf") == "multinomial"
    assert notes.short_name("statsmodels.api.OLS") == "OLS"


def test_a_step_reads_every_patch_of_its_minor():
    assert notes.scipy_versions(["1.14.1", "1.15.3"])["1.15.3"] == [
        "1.15.0",
        "1.15.1",
        "1.15.2",
        "1.15.3",
    ]
