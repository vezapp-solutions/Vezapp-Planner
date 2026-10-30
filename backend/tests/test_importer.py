"""Schedule file parsing and validation, without a database."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from apps.scheduler.importer import (
    CustomerInfo,
    ExistingLine,
    FileProblem,
    Lookups,
    PartInfo,
    RawRow,
    parse_date,
    parse_qty,
    read_table,
    summarize,
    validate_rows,
)

TODAY = date(2026, 11, 10)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("05-11-2026", date(2026, 11, 5)),
        ("5/11/2026", date(2026, 11, 5)),
        ("05/11/2026", date(2026, 11, 5)),
        (" 05-11-2026 ", date(2026, 11, 5)),
        ("2026-11-05", date(2026, 11, 5)),
        (datetime(2026, 11, 5, 14, 30), date(2026, 11, 5)),
        (date(2026, 11, 5), date(2026, 11, 5)),
        (46331, date(2026, 11, 5)),  # Excel serial number
        (46331.0, date(2026, 11, 5)),
        ("46331", date(2026, 11, 5)),
    ],
)
def test_dates_in_every_accepted_form(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize(
    "value",
    ["31-02-2026", "13/25/2026", "tomorrow", "", "05-11-26", 5, 99999999, True, "01-01-1899", None],
)
def test_bad_dates_are_rejected(value):
    with pytest.raises(ValueError):
        parse_date(value)


@pytest.mark.parametrize(
    "value, expected",
    [(600, 600), (600.0, 600), ("600", 600), ("1,200", 1200), ("1 200", 1200), (Decimal("5"), 5)],
)
def test_quantities(value, expected):
    assert parse_qty(value) == expected


@pytest.mark.parametrize("value", [0, -5, 12.5, "abc", "", "12.5", 10**9, True, float("nan")])
def test_bad_quantities(value):
    with pytest.raises(ValueError):
        parse_qty(value)


def lookups():
    c1 = CustomerInfo(1, "C1", "Aarav Pumps")
    c2 = CustomerInfo(2, "C2", "Bharat Valves", active=False)
    p1, p2 = PartInfo(10, "P-1", "Casing"), PartInfo(11, "P-2", "Cover", active=False)
    return Lookups(
        customers_by_code={"c1": c1, "c2": c2},
        customers_by_name={"aarav pumps": c1, "bharat valves": c2},
        parts_by_number={"p-1": p1, "p-2": p2},
        links={(10, 1)},
        existing={
            (1, 10, date(2026, 11, 20)): [ExistingLine(99, 100, None, None, "old", "planned")]
        },
    )


def row(number=2, **values):
    base = {
        "customer_code": "C1",
        "part_number": "P-1",
        "dispatch_qty": 100,
        "internal_date": "20-11-2026",
    }
    return RawRow(number, {**base, **values})


def check(r, mode="insert"):
    return validate_rows([r], lookups(), TODAY, mode)[0]


def test_a_clean_row_is_ok_and_normalised():
    result = check(row(internal_date="21-11-2026"))
    assert (result.status, result.action) == ("ok", "insert")
    assert result.data == {
        "customer_id": 1, "part_id": 10, "dispatch_qty": 100,
        "internal_dispatch_date": date(2026, 11, 21), "actual_dispatch_date": None,
        "actual_dispatched_qty": None, "remarks": "",
    }  # fmt: skip


def test_customer_is_found_by_code_then_by_exact_name():
    assert (
        check(row(customer_code="c1", internal_date="21-11-2026")).status == "ok"
    )  # code is case-insensitive
    by_name = check(
        row(customer_code="", customer_name="  aarav   PUMPS ", internal_date="21-11-2026")
    )
    assert by_name.status == "ok" and by_name.data["customer_id"] == 1
    unknown = check(row(customer_code="ZZ", customer_name=""))
    assert unknown.status == "error" and "ZZ" in unknown.messages[0].text


def test_unknown_code_with_a_matching_name_warns():
    result = check(row(customer_code="ZZ", customer_name="Aarav Pumps", internal_date="21-11-2026"))
    assert result.status == "warning" and result.data["customer_id"] == 1


def test_name_that_differs_from_the_code_warns():
    result = check(row(customer_name="Someone Else", internal_date="21-11-2026"))
    assert result.status == "warning" and "differs" in result.messages[0].text


def test_unlinked_and_inactive_are_warnings_not_blocks():
    unlinked = check(row(customer_code="C2", internal_date="21-11-2026"))
    assert unlinked.status == "warning"
    assert any("not linked" in m.text for m in unlinked.messages)
    assert any("inactive" in m.text for m in unlinked.messages)
    assert check(row(part_number="P-2", internal_date="21-11-2026")).data is not None


def test_actual_date_rules():
    assert check(row(actual_date="10-11-2026", internal_date="21-11-2026")).status == "ok"
    future = check(row(actual_date="11-11-2026", internal_date="21-11-2026"))
    assert future.status == "error" and "future" in future.messages[0].text
    orphan = check(row(actual_qty=40, internal_date="21-11-2026"))
    assert orphan.status == "error" and orphan.messages[0].field == "actual_qty"


def test_several_problems_are_all_reported_on_one_row():
    result = check(row(part_number="NOPE", dispatch_qty=0, internal_date="bad"))
    assert result.status == "error" and {m.field for m in result.messages} == {
        "part_number", "dispatch_qty", "internal_date",
    }  # fmt: skip


def test_insert_mode_skips_a_line_already_in_the_schedule():
    result = check(row(), mode="insert")
    assert (result.status, result.action, result.existing_id) == ("warning", "skip", 99)


def test_upsert_mode_updates_or_reports_unchanged():
    assert check(row(dispatch_qty=250), mode="upsert").action == "update"
    assert check(row(dispatch_qty=100), mode="upsert").action == "unchanged"
    # blank optional cells never count as a change
    assert check(row(dispatch_qty=100, remarks=""), mode="upsert").action == "unchanged"
    assert check(row(dispatch_qty=100, remarks="rush"), mode="upsert").action == "update"


def test_duplicates_inside_the_file_warn_in_insert_mode_and_block_in_upsert_mode():
    rows = [row(2, internal_date="21-11-2026"), row(3, internal_date="21-11-2026")]
    insert = validate_rows(rows, lookups(), TODAY, "insert")
    assert [r.status for r in insert] == ["ok", "warning"] and "row 2" in insert[1].messages[0].text
    upsert = validate_rows(rows, lookups(), TODAY, "upsert")
    assert [r.status for r in upsert] == ["ok", "error"]


def test_summary_counts():
    rows = [row(2, internal_date="21-11-2026"), row(3, part_number="X"), row(4)]
    summary = summarize(validate_rows(rows, lookups(), TODAY, "insert"))
    assert summary == {
        "total": 3,
        "ok": 1,
        "warning": 1,
        "error": 1,
        "insert": 1,
        "update": 0,
        "skip": 1,
        "unchanged": 0,
    }


# --- reading files -------------------------------------------------------------------------------
def test_csv_with_semicolons_and_synonym_headers():
    text = "Customer Code;Part No;Qty;Dispatch Date\nC1;P-1;5;01-11-2026\n"
    rows = read_table("x.csv", text.encode("utf-8-sig"))
    assert rows[0].number == 2
    assert rows[0].values == {
        "customer_code": "C1", "part_number": "P-1", "dispatch_qty": "5", "internal_date": "01-11-2026",
    }  # fmt: skip


def test_a_file_with_no_customer_column_is_refused():
    with pytest.raises(FileProblem, match="Customer Code or Customer Name"):
        read_table("x.csv", b"Part Number,Dispatch Qty,Internal Dispatch Date\nP,1,01-11-2026\n")


@pytest.mark.parametrize(
    "name, content, text",
    [
        ("a.txt", b"x", "xlsx or .csv"),
        ("a.xlsx", b"not a zip", "valid .xlsx"),
        ("a.csv", b"", "empty"),
        (
            "a.csv",
            b"Customer Code,Part Number,Dispatch Qty,Internal Dispatch Date\n",
            "no data rows",
        ),
        ("a.csv", b"Part Number,Dispatch Qty\nP,1\n", "Missing column"),
        pytest.param("a.csv", b"x" * (5 * 1024 * 1024 + 1), "5 MB", id="too-big"),
    ],
)
def test_unusable_files(name, content, text):
    with pytest.raises(FileProblem, match=text):
        read_table(name, content)


def test_blank_rows_are_ignored_and_row_numbers_match_excel():
    text = "Customer Code,Part Number,Dispatch Qty,Internal Dispatch Date\nC1,P-1,5,01-11-2026\n,,,\nC1,P-1,6,02-11-2026\n"
    assert [r.number for r in read_table("x.csv", text.encode())] == [2, 4]
