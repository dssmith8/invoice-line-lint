"""Pure logic for parsing and checking invoice line items.

Nothing in this module touches the filesystem or stdout. The CLI module
is the only place that does I/O; everything here takes plain values in
and returns plain values out, which is what makes it easy to test.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")

# Different billing systems export the same data under different headers.
# Each tuple is checked in order, so the canonical name always wins if a
# file happens to have both (e.g. "line_total" and a stray "amount" column).
FIELD_ALIASES = {
    "line_id": ("line_id", "id", "item_id", "line_item_id"),
    "description": ("description", "desc", "item", "item_description"),
    "quantity": ("quantity", "qty"),
    "unit_price": ("unit_price", "price", "rate", "unit_cost"),
    "tax_rate": ("tax_rate", "tax", "tax_pct", "tax_percent"),
    "line_total": ("line_total", "amount", "total", "line_amount"),
}


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


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def normalize_row(row: dict) -> dict:
    """Map a raw CSV row onto the canonical field names in FIELD_ALIASES.

    Header matching is case-insensitive and ignores spaces/hyphens vs
    underscores. Fields with no recognized header are simply absent from
    the result, which parse_row treats the same as a missing column.
    """
    by_normalized_key = {_normalize_key(key): key for key in row if key is not None}
    canonical = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in by_normalized_key:
                canonical[field] = row[by_normalized_key[alias]]
                break
    return canonical


def parse_row(row: dict) -> LineItem:
    """Turn one CSV row (str -> str) into a LineItem.

    Column names are matched against FIELD_ALIASES first, so exports that
    use e.g. "amount" instead of "line_total" work without configuration.
    Raises ParseError if a required field is missing or not numeric.
    Does not validate the arithmetic between fields; that is check_items's job.
    """
    row = normalize_row(row)

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
