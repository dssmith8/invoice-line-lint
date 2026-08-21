"""Pure logic for parsing and checking invoice line items.

Nothing in this module touches the filesystem or stdout. The CLI module
is the only place that does I/O; everything here takes plain values in
and returns plain values out, which is what makes it easy to test.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")


class ParseError(Exception):
    """A row from the source CSV could not be turned into a LineItem."""


@dataclass(frozen=True)
class LineItem:
    line_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class Issue:
    line_id: str
    message: str


@dataclass(frozen=True)
class Summary:
    item_count: int
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    issue_count: int


def _to_decimal(raw: str, field: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        raise ParseError(f"field {field!r} is not a number: {raw!r}")


def parse_row(row: dict) -> LineItem:
    """Turn one CSV row (str -> str) into a LineItem.

    Raises ParseError if a required field is missing or not numeric.
    Does not validate the arithmetic between fields; that is check_items's job.
    """
    try:
        line_id = row["line_id"].strip()
    except (KeyError, AttributeError):
        raise ParseError("row is missing 'line_id'")
    if not line_id:
        raise ParseError("row has an empty 'line_id'")

    description = row.get("description", "").strip()

    try:
        quantity = _to_decimal(row["quantity"], "quantity")
        unit_price = _to_decimal(row["unit_price"], "unit_price")
        tax_rate = _to_decimal(row["tax_rate"], "tax_rate")
        line_total = _to_decimal(row["line_total"], "line_total")
    except KeyError as exc:
        raise ParseError(f"line {line_id!r} is missing field {exc.args[0]!r}")

    return LineItem(
        line_id=line_id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        tax_rate=tax_rate,
        line_total=line_total,
    )


def expected_subtotal(item: LineItem) -> Decimal:
    return (item.quantity * item.unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def expected_total(item: LineItem) -> Decimal:
    subtotal = item.quantity * item.unit_price
    taxed = subtotal * (Decimal("1") + item.tax_rate)
    return taxed.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def check_items(items: list, tolerance: Decimal = TWO_PLACES) -> list:
    """Return a list of Issues found across all items.

    Checks each item's recorded line_total against quantity * unit_price *
    (1 + tax_rate), and flags any line_id that appears more than once.
    """
    issues = []
    seen_ids = set()

    for item in items:
        if item.line_id in seen_ids:
            issues.append(Issue(item.line_id, f"duplicate line_id {item.line_id!r}"))
        seen_ids.add(item.line_id)

        want = expected_total(item)
        diff = (item.line_total - want).copy_abs()
        if diff > tolerance:
            issues.append(
                Issue(
                    item.line_id,
                    f"line_total {item.line_total} does not match expected {want} "
                    f"(quantity {item.quantity} x unit_price {item.unit_price} "
                    f"x tax_rate {item.tax_rate})",
                )
            )

    return issues


def summarize(items: list, issues: list) -> Summary:
    subtotal = sum((expected_subtotal(item) for item in items), Decimal("0"))
    total = sum((item.line_total for item in items), Decimal("0"))
    tax = (total - subtotal).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return Summary(
        item_count=len(items),
        subtotal=subtotal.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
        tax=tax,
        total=total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
        issue_count=len(issues),
    )
