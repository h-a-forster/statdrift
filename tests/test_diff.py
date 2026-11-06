"""The differ on synthetic result files with planted changes."""

from __future__ import annotations

import pytest
from conftest import make_row

from statdrift import diff


def compare(results, rows_a, rows_b):
    _, a = diff.load(results("a.jsonl", rows_a))
    _, b = diff.load(results("b.jsonl", rows_b))
    tally, changes = diff.compare(a, b)
    return tally.get("grid", {}), changes


def test_planted_changes_are_counted_exactly(results):
    base = [
        make_row(input_="same", value=0.2),
        make_row(input_="noise", value=0.2),
        make_row(input_="moved", value=0.2),
        make_row(input_="crossed", value=0.051),
        make_row(input_="crossed-both", value=0.5),
        make_row(input_="to-nan", value=0.2),
        make_row(input_="to-raise", value=0.2),
        make_row(input_="stat", field="statistic", value=3.0),
    ]
    new = [dict(r) for r in base]
    new[1]["value"] = 0.2 * (1 + 1e-12)
    new[2]["value"] = 0.21
    new[3]["value"] = 0.049
    new[4]["value"] = 0.001
    new[5]["value"] = "nan"
    new[6] |= {"value": None, "dtype": None, "exception": "ValueError"}
    new[7]["value"] = 3.0000001
    tally, changes = compare(results, base, new)
    assert tally["cells"] == 8
    assert tally[diff.NUMERIC] == 4
    assert tally[diff.STATUS] == 2
    assert tally["p_cells"] == 7
    assert tally["flip0.05"] == 2
    assert tally["flip0.01"] == 1
    assert tally["p_flipped"] == 2
    assert tally["p_lost"] == 2
    assert {c.input for c in changes} == {
        "moved",
        "crossed",
        "crossed-both",
        "to-nan",
        "to-raise",
        "stat",
    }
    stat = next(c for c in changes if c.input == "stat")
    assert not stat.material  # 3e-8 relative: above 1e-9, below the material line


def test_rounding_around_zero_is_not_a_change_but_a_small_p_is(results):
    rows_a = [
        make_row(input_="t", field="statistic", value=1e-16),
        make_row(input_="p", value=1e-20),
    ]
    rows_b = [
        make_row(input_="t", field="statistic", value=3e-16),
        make_row(input_="p", value=2e-20),
    ]
    tally, changes = compare(results, rows_a, rows_b)
    assert [c.input for c in changes] == ["p"]
    assert tally[diff.NUMERIC] == 1


def test_a_raising_call_covers_every_field_of_the_other_side(results):
    failed = make_row(field="*", value=None, dtype=None, exception="ValueError")
    fine = [make_row(field="pvalue"), make_row(field="statistic", value=2.0)]
    tally, changes = compare(results, [failed], fine)
    assert tally["cells"] == 2
    assert tally[diff.STATUS] == 2
    assert {c.kind for c in changes} == {"p", "x"}


def test_p_lost_is_a_number_going_away_and_p_gained_is_the_reverse(results):
    failed = make_row(value=None, dtype=None, exception="ValueError")
    number, nan = make_row(), make_row(value="nan")
    for before, after, lost, gained in [
        (number, nan, 1, 0),
        (number, failed, 1, 0),
        (failed, number, 0, 1),
        (nan, number, 0, 1),
        (failed, nan, 0, 0),
    ]:
        tally, _ = compare(results, [before], [after])
        assert (tally.get("p_lost", 0), tally.get("p_gained", 0)) == (lost, gained)


def test_same_exception_is_same_and_a_new_type_is_status(results):
    one = make_row(field="*", value=None, dtype=None, exception="ValueError")
    tally, _ = compare(results, [one], [dict(one)])
    assert tally[diff.SAME] == 1
    other = dict(one, exception="LinAlgError")
    tally, _ = compare(results, [one], [other])
    assert tally[diff.STATUS] == 1


def test_added_keyword_is_not_drift_but_a_removed_one_is(results):
    rejected = make_row(field="*", value=None, dtype=None, exception=diff.KEYWORD)
    works = make_row(field="pvalue")
    tally, _ = compare(results, [rejected], [works])
    assert tally == {diff.API_ADDED: 1}
    tally, _ = compare(results, [works], [rejected])
    assert tally[diff.STATUS] == 1
    tally, _ = compare(results, [rejected], [dict(rejected)])
    assert tally == {diff.NOT_APPLICABLE: 1}


def test_new_result_fields_are_counted_apart_from_cells(results):
    tally, _ = compare(results, [make_row()], [make_row(), make_row(field="df", value=3.0)])
    assert tally["cells"] == 1
    assert tally["field_added"] == 1


def test_a_scalar_that_becomes_an_array_is_a_status_change(results):
    scalar = make_row(field="statistic", value="nan")
    matrix = [
        make_row(field="statistic[0,0]", value=1.0),
        make_row(field="statistic[0,1]", value=0.5),
    ]
    tally, changes = compare(results, [scalar], matrix)
    assert tally["cells"] == 2
    assert tally[diff.STATUS] == 2
    assert all(c.material for c in changes)


def test_dtype_and_warning_changes_are_not_numeric_changes(results):
    tally, changes = compare(results, [make_row(dtype="int64")], [make_row(dtype="float64")])
    assert tally[diff.DTYPE] == 1
    assert diff.function_units(changes) == {}
    tally, _ = compare(results, [make_row()], [make_row(warnings=["RuntimeWarning"])])
    assert tally[diff.WARNING] == 1


def test_unfinished_file_is_refused(tmp_path):
    path = tmp_path / "partial.jsonl"
    path.write_text('{"meta": {}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="end marker"):
        diff.load(path)


def test_different_batteries_are_refused(results):
    with pytest.raises(ValueError, match="same battery"):
        compare(results, [make_row(input_="a")], [make_row(input_="b")])


def test_unstable_cells_are_dropped(results):
    _, a = diff.load(results("a.jsonl", [make_row(value=0.2)]))
    _, b = diff.load(results("b.jsonl", [make_row(value=0.9)]))
    tally, changes = diff.compare(a, b, {("scipy.stats.f", "default", "in")})
    assert not changes
    assert tally["grid"] == {"unstable": 1}


def test_clopper_pearson_matches_scipy():
    stats = pytest.importorskip("scipy.stats")
    for k, n in [(0, 10), (1, 10), (7, 20), (20, 20), (33, 90)]:
        low, high = diff.clopper_pearson(k, n)
        exact = stats.binomtest(k, n).proportion_ci(0.95, method="exact")
        assert low == pytest.approx(exact.low, abs=1e-9)
        assert high == pytest.approx(exact.high, abs=1e-9)
