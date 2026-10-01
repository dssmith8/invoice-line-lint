"""Command line entry point. This is the only module that does I/O."""

import argparse
import csv
import json
import sys
from decimal import Decimal

from invoice_line_lint.core import (
    ParseError,
    check_items,
    fixed_rows,
    parse_row,
    summarize,
    summarize_by_invoice,
)


def read_rows(path: str):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_rows(path: str, fieldnames, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_report(summary, issues, parse_errors, invoices=()) -> dict:
    # Decimal values go out as strings, not float(), so a total like
    # 48.60 round-trips exactly instead of becoming 48.6 or 48.599999999999994.
    return {
        "ok": not issues and not parse_errors,
        "summary": {
            "item_count": summary.item_count,
            "subtotal": str(summary.subtotal),
            "tax": str(summary.tax),
            "total": str(summary.total),
            "issue_count": summary.issue_count,
        },
        "invoices": [
            {
                "invoice_id": invoice.invoice_id,
                "item_count": invoice.item_count,
                "subtotal": str(invoice.subtotal),
                "tax": str(invoice.tax),
                "total": str(invoice.total),
            }
            for invoice in invoices
        ],
        "issues": [
            {"line_id": issue.line_id, "message": issue.message} for issue in issues
        ],
        "parse_errors": list(parse_errors),
    }


def format_report(summary, issues, parse_errors, invoices=()) -> str:
    lines = []
    lines.append(f"checked {summary.item_count} line item(s)")
    lines.append(f"  subtotal: {summary.subtotal}")
    lines.append(f"  tax:      {summary.tax}")
    lines.append(f"  total:    {summary.total}")

    if invoices:
        lines.append(f"\nper invoice ({len(invoices)}):")
        for invoice in invoices:
            name = invoice.invoice_id or "(no invoice id)"
            lines.append(
                f"  {name}: {invoice.item_count} item(s), subtotal {invoice.subtotal}, "
                f"tax {invoice.tax}, total {invoice.total}"
            )

    if parse_errors:
        lines.append(f"\n{len(parse_errors)} row(s) could not be read:")
        for message in parse_errors:
            lines.append(f"  - {message}")

    if issues:
        lines.append(f"\n{len(issues)} issue(s) found:")
        for issue in issues:
            lines.append(f"  - [{issue.line_id}] {issue.message}")
    elif not parse_errors:
        lines.append("\nno issues found")

    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="invoice-line-lint",
        description="Audit an invoice line item CSV export for arithmetic and duplicate-id errors.",
    )
    parser.add_argument("csv_path", help="path to a CSV file with line_id, description, "
                         "quantity, unit_price, tax_rate, line_total columns")
    parser.add_argument(
        "--tolerance",
        default="0.01",
        help="allowed absolute difference between recorded and expected line_total (default: 0.01)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as JSON on stdout instead of plain text",
    )
    parser.add_argument(
        "--fix",
        metavar="OUTPUT_CSV",
        help="write a copy of the CSV to OUTPUT_CSV with line_total corrected on rows that "
        "failed the arithmetic check (duplicate line_id rows are left as-is)",
    )
    args = parser.parse_args(argv)

    try:
        fieldnames, rows = read_rows(args.csv_path)
    except OSError as exc:
        print(f"could not read {args.csv_path}: {exc}", file=sys.stderr)
        return 2

    tolerance = Decimal(args.tolerance)

    items = []
    parse_errors = []
    for row in rows:
        try:
            items.append(parse_row(row))
        except ParseError as exc:
            parse_errors.append(str(exc))

    issues = check_items(items, tolerance=tolerance)
    summary = summarize(items, issues)

    # A file with no invoice column is one anonymous invoice; a per-invoice
    # breakdown of it would just repeat the overall totals.
    invoices = []
    if any(item.invoice_id for item in items):
        invoices = summarize_by_invoice(items)

    if args.json:
        print(json.dumps(build_report(summary, issues, parse_errors, invoices), indent=2))
    else:
        print(format_report(summary, issues, parse_errors, invoices))

    if args.fix:
        try:
            write_rows(args.fix, fieldnames, fixed_rows(rows, tolerance=tolerance))
        except OSError as exc:
            print(f"could not write {args.fix}: {exc}", file=sys.stderr)
            return 2
        print(f"\nwrote corrected line_total values to {args.fix}")

    return 1 if issues or parse_errors else 0


if __name__ == "__main__":
    sys.exit(main())
