from market_skew import sentinel_run, store, valuation
from market_skew.ui import research_view, value_view
from tests.test_research_view import scored_rows
from tests.test_valuation import M


def ranged(price=50.0):
    return {"symbol": "A", "value": valuation.value(M, price, "Info Tech")}


def test_block_shows_position_range_marker_and_assumptions():
    html = value_view.block(ranged(10.0))
    assert "Price is below the bear case" in html and "<svg" in html and "fv-price" in html
    assert "What this assumes" in html and "Not a target price" in html


def test_block_gives_the_reason_when_skipped_and_escapes_it():
    html = value_view.block({"value": {"ok": False, "reason": "<b>no</b>"}})
    assert "&lt;b&gt;no&lt;/b&gt;" in html and "<svg" not in html


def test_board_cell_and_sort_key():
    assert value_view.sort_key(ranged(10.0)) == 0 and value_view.sort_key(ranged(9999.0)) == 2
    assert value_view.sort_key({"value": {"ok": False}}) == -1 and "above range" in value_view.cell(ranged(9999.0))


def test_board_and_card_render_with_values_and_how_has_the_section():
    rows = sentinel_run.with_values(scored_rows())
    assert "Price vs range" in research_view.board(rows)
    assert "Fair-value range" in research_view.card(rows[0], None) and "Fair-value range" in research_view.HOW


def test_values_are_saved_with_sentinel_rows_and_revalued(tmp_path):
    with store.connect(tmp_path / "v.db") as conn:
        store.save_sentinel(conn, "2026-11-18", scored_rows())
        date, count, ranged_count = sentinel_run.revalue(conn)
        assert date == "2026-11-18" and count == len(scored_rows()) and ranged_count >= 1
        assert all("value" in r for r in store.sentinel(conn)[1])
