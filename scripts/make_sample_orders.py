"""Write docs/samples/monthly-orders-sample.xlsx: a monthly order file for the demo foundry.

Run from the repo root with the backend virtualenv:
    backend\\.venv\\Scripts\\python.exe scripts\\make_sample_orders.py

The rows use the demo foundry's parts and customers (run the seed first). They cover May and June 2027, two
grades (GG25 and SG500), Open and Closed orders, stock filled in on some, one order fully covered by stock, a
part with no route (SPR-900: cannot plan), and a part that is not in the Part Master (NEW-777: unmatched).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from apps.scheduler.importer import COLUMNS
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

KEYS = [k for k, _ in COLUMNS]
ROWS = [
    # part, qty, date, month, customer, status, wip, fg, dispatched, last dispatch, remarks
    ("PMP-201", 600, "15-05-2027", "May", "C-101", "Open", 100, 50, 0, "", "Pump casing, GG25"),
    ("PMP-202", 400, "20-05-2027", "May", "C-101", "Open", 0, 0, 0, "", "Pump cover, GG25"),
    ("VLV-310", 300, "25-05-2027", "May", "C-102", "Open", 80, 120, 100, "", "Covered by stock: balance 0"),
    ("VLV-311", 800, "28-05-2027", "May", "C-102", "Open", 200, 0, 0, "", "Valve bonnet, SG500"),
    ("AUT-420", 500, "05-06-2027", "June", "C-103", "Open", 0, 0, 0, "", "Brake drum, GG25"),
    ("ENG-505", 120, "12-06-2027", "June", "C-104", "Open", 0, 20, 0, "", "Gearbox housing, GG25"),
    ("PMP-201", 700, "18-06-2027", "June", "C-101", "Closed", 0, 0, 700, "", "Shipped: closed, kept as history"),
    ("SPR-900", 60, "22-06-2027", "June", "C-101", "Open", 0, 0, 0, "", "Part has no route: cannot plan"),
    ("NEW-777", 200, "25-06-2027", "June", "", "Open", 0, 0, 0, "", "Not in the Part Master: create it, then re-check"),
]
# the same order as the template columns
ORDER = ["part_number", "dispatch_qty", "internal_date", "month", "customer_code", "status", "wip_qty", "fg_qty", "actual_qty", "actual_date", "remarks"]


def main() -> None:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Orders"
    for column, (_, header) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0B6F67")
    for r, row in enumerate(ROWS, start=2):
        values = dict(zip(ORDER, row, strict=True))
        for column, key in enumerate(KEYS, start=1):
            value = values.get(key, "")
            sheet.cell(row=r, column=column, value=value if value != "" else None)
    sheet.freeze_panes = "A2"
    for index, width in enumerate([12, 10, 14, 8, 14, 22, 9, 9, 9, 13, 14, 14][: len(KEYS)], start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    out = ROOT / "docs" / "samples" / "monthly-orders-sample.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"wrote {out.relative_to(ROOT)} with {len(ROWS)} rows")


if __name__ == "__main__":
    main()
