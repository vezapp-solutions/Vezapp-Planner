"""Excel files the scheduler hands back: the upload template and the error report."""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .importer import COLUMNS, RowResult

HEADER_FILL = PatternFill("solid", fgColor="0B6F67")
HEADER_FONT = Font(bold=True, color="FFFFFF")
RED = PatternFill("solid", fgColor="F8E4E1")
AMBER = PatternFill("solid", fgColor="F6EAD0")


def put(sheet, row: int, column: int, value):
    """Write a cell as plain text so a value starting with = + - @ can never run as a formula."""
    cell = sheet.cell(row=row, column=column)
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"
    return cell


def _widths(sheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def template_workbook() -> bytes:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Schedule"
    for column, (_, header) in enumerate(COLUMNS, start=1):
        cell = put(sheet, 1, column, header)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    sheet.freeze_panes = "A2"
    _widths(sheet, [16, 12, 16, 12, 16, 30, 10, 12, 12, 14, 18, 36])
    for row in range(2, 502):
        sheet.cell(row=row, column=3).number_format = "dd-mm-yyyy"
        sheet.cell(row=row, column=11).number_format = "dd-mm-yyyy"

    help_sheet = wb.create_sheet("How to fill")
    lines = [
        "Fill one row per dispatch requirement on the Schedule sheet. Keep the header row as it is.",
        "",
        "Part Number (required): must exist in the Part Master. A part that is not there is listed after",
        "  the preview so you can create it or fix the row; the other rows still load.",
        "Order Qty (required): a whole number of pieces, 1 or more.",
        "Dispatch Date (required): the date the order must leave. Use DD-MM-YYYY (for example 15-05-2027).",
        "Month: optional, for example May. It is checked against the dispatch date, and the date wins.",
        "Customer Code or Customer Name: optional. Blank means the part's default customer.",
        "Status: Open or Closed. Only Open orders are planned; Closed orders stay on the list as history.",
        "WIP Stock: castings already made and still in process. Leave blank to keep what is recorded.",
        "FG Stock: finished goods ready to dispatch. Leave blank to keep what is recorded.",
        "Dispatched Qty: pieces already sent to the customer (cumulative). Leave blank to keep what is recorded.",
        "Last Dispatch Date: optional, the date of the last dispatch. It cannot be in the future.",
        "Remarks: optional, up to 500 characters.",
        "",
        "Balance to produce = Order Qty - (WIP + FG + Dispatched). Only the balance is planned.",
        "To update stock later, upload the same file again with 'Insert new and update matching rows'.",
        "",
        "Example rows (do not copy the part numbers; use your own):",
        "Part Number | Order Qty | Dispatch Date | Month | Customer Code | Status | WIP Stock | FG Stock | Dispatched Qty",
        "GG-1001 | 600 | 15-05-2027 | May | CUST-01 | Open | 0 | 0 | 0",
        "SG-2002 | 250 | 28-05-2027 | May | (blank: the part's default customer) | Open | 40 | 60 | 0",
        "GG-1001 | 400 | 10-06-2027 | June | CUST-01 | Closed | 0 | 0 | 400",
        "",
        "Dates may be typed as DD-MM-YYYY or DD/MM/YYYY, or be real Excel dates.",
        "Both .xlsx and .csv files are accepted, up to 5,000 rows and 5 MB.",
        "You always see a preview first. Nothing is saved until you confirm.",
    ]
    for index, text in enumerate(lines, start=1):
        put(help_sheet, index, 1, text)
    help_sheet.column_dimensions["A"].width = 110
    help_sheet["A1"].font = Font(bold=True)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def error_report(results: list[RowResult]) -> bytes:
    """Every row that has an error or a warning, with what is wrong and the values as uploaded."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Problems"
    headers = ["Row", "Result", "Problem", *[h for _, h in COLUMNS]]
    for column, header in enumerate(headers, start=1):
        cell = put(sheet, 1, column, header)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    sheet.freeze_panes = "A2"

    out_row = 2
    for result in results:
        if result.status == "ok":
            continue
        fill = RED if result.status == "error" else AMBER
        values = [
            result.row_number,
            "Error" if result.status == "error" else "Warning",
            "\n".join(f"{m.field.replace('_', ' ')}: {m.text}" for m in result.messages),
            *[result.raw.get(key, "") for key, _ in COLUMNS],
        ]
        for column, value in enumerate(values, start=1):
            cell = put(sheet, out_row, column, value)
            cell.fill = fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        out_row += 1
    _widths(sheet, [8, 10, 60, 16, 12, 16, 12, 16, 30, 10, 12, 12, 14, 18, 36])
    if out_row == 2:
        put(sheet, 2, 1, "No problems found.")

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def report_from_stored(rows: list[dict]) -> bytes:
    """Rebuild the error report of a committed upload from the rows kept on its history record."""
    from .importer import Message

    results = [
        RowResult(
            row_number=r["row"],
            status=r["status"],
            action=r["action"],
            messages=[
                Message(m["level"], m["field"], m["text"], m.get("code", "")) for m in r["messages"]
            ],
            raw=r["raw"],
        )
        for r in rows
    ]
    return error_report(results)
