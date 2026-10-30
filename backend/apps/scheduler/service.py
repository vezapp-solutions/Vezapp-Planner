"""Database side of an upload: build lookups, preview a file, commit it all-or-nothing."""

from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.masters.models import Customer, Part, PartCustomer

from .importer import (
    CustomerInfo,
    ExistingLine,
    FileProblem,
    Lookups,
    PartInfo,
    RawRow,
    RowResult,
    month_end,
    parse_date,
    read_table,
    summarize,
    validate_rows,
)
from .models import LineStatus, ScheduleLine, UploadBatch


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def build_lookups(company, rows: list[RawRow]) -> Lookups:
    lookups = Lookups()
    for c in Customer.objects.for_company(company):
        info = _info_customer(c)
        lookups.customers_by_code[_key(c.code)] = info
        lookups.customers_by_name.setdefault(_key(c.name), info)
    for p in Part.objects.for_company(company):
        lookups.parts_by_number[_key(p.part_number)] = _info_part(p)
    lookups.links = set(
        PartCustomer.objects.for_company(company).values_list("part_id", "customer_id")
    )

    dates = []
    for row in rows:
        try:
            dates.append(parse_date(row.values.get("internal_date")))
        except (ValueError, TypeError):
            continue
    if dates:
        qs = ScheduleLine.objects.for_company(company).filter(
            internal_dispatch_date__range=(min(dates), max(dates))
        )
        for line in qs.exclude(status=LineStatus.CANCELLED):
            lookups.existing.setdefault(
                (line.customer_id, line.part_id, line.internal_dispatch_date), []
            ).append(
                ExistingLine(
                    line.id,
                    line.dispatch_qty,
                    line.actual_dispatch_date,
                    line.actual_dispatched_qty,
                    line.remarks,
                    line.status,
                )
            )
    return lookups


def _info_customer(c):
    return CustomerInfo(c.id, c.code, c.name, c.is_active)


def _info_part(p):
    return PartInfo(p.id, p.part_number, p.name, p.is_active)


def analyse(company, filename: str, content: bytes, mode: str) -> list[RowResult]:
    if mode not in ("insert", "upsert"):
        raise ValidationError({"mode": "Mode must be insert or upsert."})
    try:
        rows = read_table(filename, content)
    except FileProblem as exc:
        raise ValidationError({"file": str(exc)}) from exc
    lookups = build_lookups(company, rows)
    return validate_rows(rows, lookups, timezone.localdate(), mode)


def preview(company, filename: str, content: bytes, mode: str) -> dict:
    results = analyse(company, filename, content, mode)
    return {
        "file_name": filename,
        "mode": mode,
        "summary": summarize(results),
        "rows": [r.as_dict() for r in results],
    }


@transaction.atomic
def commit(company, user, filename: str, content: bytes, mode: str, skip_errors: bool):
    results = analyse(company, filename, content, mode)
    summary = summarize(results)
    if summary["error"] and not skip_errors:
        raise ValidationError(
            {
                "file": f"{summary['error']} row(s) have errors. Fix them, or choose to skip "
                "the rows with errors. Nothing was saved."
            }
        )
    if summary["insert"] + summary["update"] == 0:
        raise ValidationError({"file": "There is nothing to save from this file."})

    batch = UploadBatch.objects.create(
        company=company,
        user=user,
        username=user.username,
        file_name=filename[:255],
        mode=mode,
        skipped_errors=bool(summary["error"]),
        rows_total=summary["total"],
        rows_inserted=summary["insert"],
        rows_updated=summary["update"],
        rows_unchanged=summary["unchanged"],
        rows_skipped=summary["skip"],
        rows_error=summary["error"],
        rows_warning=summary["warning"],
        report=[r.as_dict() for r in results if r.status != "ok"][:1000],
    )
    for result in results:
        data = result.data
        if result.action == "insert":
            line = ScheduleLine(company=company, upload_batch=batch, **data)
            line.status = (
                LineStatus.DISPATCHED if data["actual_dispatch_date"] else LineStatus.PLANNED
            )
            line.save()
        elif result.action == "update":
            line = ScheduleLine.objects.for_company(company).get(pk=result.existing_id)
            line.dispatch_qty = data["dispatch_qty"]
            # A blank optional cell keeps what is already recorded; it never wipes it.
            if data["actual_dispatch_date"]:
                line.actual_dispatch_date = data["actual_dispatch_date"]
                line.status = LineStatus.DISPATCHED
            if data["actual_dispatched_qty"] is not None:
                line.actual_dispatched_qty = data["actual_dispatched_qty"]
            if data["remarks"]:
                line.remarks = data["remarks"]
            line.upload_batch = batch
            line.save()
    if any(
        r.action in ("insert", "update") and r.data.get("actual_dispatch_date") for r in results
    ):
        from apps.insights.service import refresh_quietly  # dispatch performance has new data

        refresh_quietly(company, trigger="actuals")
    return batch


def copy_month(company, from_month: date, to_month: date) -> dict:
    """Copy one month's lines into another, keeping the day of month (clamped to month end)."""
    source = (
        ScheduleLine.objects.for_company(company)
        .filter(
            internal_dispatch_date__year=from_month.year,
            internal_dispatch_date__month=from_month.month,
        )
        .exclude(status=LineStatus.CANCELLED)
    )
    last_day = month_end(to_month).day
    existing = set(
        ScheduleLine.objects.for_company(company)
        .filter(
            internal_dispatch_date__year=to_month.year,
            internal_dispatch_date__month=to_month.month,
        )
        .values_list("customer_id", "part_id", "internal_dispatch_date", "dispatch_qty")
    )
    created = skipped = 0
    with transaction.atomic():
        for line in source.order_by("internal_dispatch_date", "id"):
            day = min(line.internal_dispatch_date.day, last_day)
            target = to_month.replace(day=day)
            key = (line.customer_id, line.part_id, target, line.dispatch_qty)
            if key in existing:
                skipped += 1
                continue
            ScheduleLine.objects.create(
                company=company,
                customer_id=line.customer_id,
                part_id=line.part_id,
                dispatch_qty=line.dispatch_qty,
                internal_dispatch_date=target,
                remarks=line.remarks,
            )
            existing.add(key)
            created += 1
    return {"created": created, "skipped": skipped}
