"""Parser tests against real detail pages + synthetic edge cases."""

from __future__ import annotations

from uzex_backfill.parser import (
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_PARSE_EMPTY,
    hash_fields,
    parse_detail,
    status_sentinel_hash,
)


def _table(rows_html: str) -> str:
    return (
        "<html><body><table class='table table-bordered custom-table-dark'>"
        f"<tbody>{rows_html}</tbody></table><footer>x</footer></body></html>"
    )


# -- real pages ------------------------------------------------------------
def test_ok_page_parses_many_fields(fixture_html):
    result = parse_detail(fixture_html("offer_ok.html"))
    assert result.status == STATUS_OK
    # A real offer has ~19 rows; acceptance requires >= 10.
    assert result.field_count >= 10
    # culture=ru labels are Russian.
    assert any("Наименование" in label for label in result.labels)


def test_ok_page_captures_links_as_href_objects(fixture_html):
    result = parse_detail(fixture_html("offer_ok.html"))
    link_values = [v for v in result.fields.values() if isinstance(v, dict) and "href" in v]
    assert link_values, "expected at least one href-aware value (soliq.uz taxpayer link)"
    assert any("soliq.uz" in v["href"] for v in link_values)


def test_not_found_page(fixture_html):
    result = parse_detail(fixture_html("offer_not_found.html"))
    assert result.status == STATUS_NOT_FOUND
    assert result.field_count == 0


# -- synthetic edge cases --------------------------------------------------
def test_malformed_page_is_parse_empty():
    # No details table and not a full site render -> malformed.
    result = parse_detail("<html><body>oops truncated")
    assert result.status == STATUS_PARSE_EMPTY


def test_table_without_pairs_is_parse_empty():
    # A details table whose rows have <2 cells yields no pairs.
    result = parse_detail(_table("<tr><td>only-one-cell</td></tr>"))
    assert result.status == STATUS_PARSE_EMPTY


def test_duplicate_labels_are_preserved():
    html = _table(
        "<tr><td>Примечание</td><td>первое</td></tr>"
        "<tr><td>Примечание</td><td>второе</td></tr>"
    )
    result = parse_detail(html)
    assert result.status == STATUS_OK
    assert result.fields["Примечание"] == "первое"
    assert result.fields["Примечание (2)"] == "второе"


def test_multi_link_cell_keeps_all_hrefs():
    html = _table(
        "<tr><td>Ссылки</td><td>"
        "<a href='https://a.example'>a</a> <a href='https://b.example'>b</a>"
        "</td></tr>"
    )
    result = parse_detail(html)
    value = result.fields["Ссылки"]
    assert value["href"] == "https://a.example"
    assert value["hrefs"] == ["https://a.example", "https://b.example"]


def test_single_link_cell_shape():
    html = _table("<tr><td>Плательщик</td><td><a href='https://x.example'>X</a></td></tr>")
    value = parse_detail(html).fields["Плательщик"]
    assert value == {"text": "X", "href": "https://x.example"}
    assert "hrefs" not in value


# -- hashing ---------------------------------------------------------------
def test_hash_is_order_independent():
    a = {"one": "1", "two": "2"}
    b = {"two": "2", "one": "1"}
    assert hash_fields(a) == hash_fields(b)


def test_hash_changes_with_content():
    assert hash_fields({"x": "1"}) != hash_fields({"x": "2"})


def test_status_sentinels_are_distinct():
    hashes = {
        status_sentinel_hash("not_found"),
        status_sentinel_hash("parse_empty"),
        status_sentinel_hash("fetch_failed"),
    }
    assert len(hashes) == 3
