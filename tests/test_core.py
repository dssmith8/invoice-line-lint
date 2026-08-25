import unittest
from decimal import Decimal

from invoice_line_lint.core import (
    Issue,
    LineItem,
    ParseError,
    check_items,
    expected_subtotal,
    expected_total,
    parse_row,
    summarize,
)


def make_row(**overrides):
    row = {
        "line_id": "INV-1",
        "description": "Widget",
        "quantity": "10",
        "unit_price": "4.50",
        "tax_rate": "0.08",
        "line_total": "48.60",
    }
    row.update(overrides)
    return row


def make_item(**overrides):
    fields = {
        "line_id": "INV-1",
        "description": "Widget",
        "quantity": Decimal("10"),
        "unit_price": Decimal("4.50"),
        "tax_rate": Decimal("0.08"),
        "line_total": Decimal("48.60"),
    }
    fields.update(overrides)
    return LineItem(**fields)


class ParseRowTests(unittest.TestCase):
    def test_parses_a_well_formed_row(self):
        item = parse_row(make_row())
        self.assertEqual(item.line_id, "INV-1")
        self.assertEqual(item.description, "Widget")
        self.assertEqual(item.quantity, Decimal("10"))
        self.assertEqual(item.unit_price, Decimal("4.50"))
        self.assertEqual(item.tax_rate, Decimal("0.08"))
        self.assertEqual(item.line_total, Decimal("48.60"))

    def test_strips_whitespace_from_line_id(self):
        item = parse_row(make_row(line_id="  INV-1  "))
        self.assertEqual(item.line_id, "INV-1")

    def test_missing_description_defaults_to_empty_string(self):
        row = make_row()
        del row["description"]
        item = parse_row(row)
        self.assertEqual(item.description, "")

    def test_missing_line_id_raises(self):
        row = make_row()
        del row["line_id"]
        with self.assertRaises(ParseError):
            parse_row(row)

    def test_empty_line_id_raises(self):
        with self.assertRaises(ParseError):
            parse_row(make_row(line_id="   "))

    def test_missing_numeric_field_raises(self):
        row = make_row()
        del row["unit_price"]
        with self.assertRaises(ParseError):
            parse_row(row)

    def test_non_numeric_field_raises(self):
        with self.assertRaises(ParseError):
            parse_row(make_row(quantity="ten"))


class ExpectedValueTests(unittest.TestCase):
    def test_expected_subtotal_rounds_to_two_places(self):
        item = make_item(quantity=Decimal("3"), unit_price=Decimal("12.005"))
        self.assertEqual(expected_subtotal(item), Decimal("36.02"))

    def test_expected_total_applies_tax_after_subtotal(self):
        item = make_item(
            quantity=Decimal("10"),
            unit_price=Decimal("4.50"),
            tax_rate=Decimal("0.08"),
        )
        self.assertEqual(expected_total(item), Decimal("48.60"))

    def test_expected_total_with_zero_tax(self):
        item = make_item(
            quantity=Decimal("2"),
            unit_price=Decimal("10.00"),
            tax_rate=Decimal("0"),
        )
        self.assertEqual(expected_total(item), Decimal("20.00"))


class CheckItemsTests(unittest.TestCase):
    def test_no_issues_for_correct_items(self):
        items = [make_item()]
        self.assertEqual(check_items(items), [])

    def test_flags_mismatched_line_total(self):
        item = make_item(line_total=Decimal("50.00"))
        issues = check_items([item])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line_id, "INV-1")
        self.assertIn("does not match expected", issues[0].message)

    def test_flags_duplicate_line_id(self):
        items = [make_item(), make_item()]
        issues = check_items(items)
        self.assertEqual(len(issues), 1)
        self.assertIn("duplicate line_id", issues[0].message)

    def test_within_tolerance_is_not_flagged(self):
        item = make_item(line_total=Decimal("48.61"))
        self.assertEqual(check_items([item]), [])

    def test_custom_tolerance_is_respected(self):
        item = make_item(line_total=Decimal("48.65"))
        self.assertEqual(check_items([item], tolerance=Decimal("0.10")), [])
        self.assertEqual(len(check_items([item], tolerance=Decimal("0.01"))), 1)

    def test_duplicate_and_mismatch_both_reported(self):
        bad = make_item(line_total=Decimal("50.00"))
        items = [bad, bad]
        issues = check_items(items)
        # one duplicate issue, plus a mismatch issue for each occurrence
        self.assertEqual(len(issues), 3)


class SummarizeTests(unittest.TestCase):
    def test_summary_totals_match_items(self):
        items = [
            make_item(line_id="A", quantity=Decimal("10"), unit_price=Decimal("4.50"),
                      tax_rate=Decimal("0.08"), line_total=Decimal("48.60")),
            make_item(line_id="B", quantity=Decimal("3"), unit_price=Decimal("12.00"),
                      tax_rate=Decimal("0.08"), line_total=Decimal("38.88")),
        ]
        summary = summarize(items, issues=[])
        self.assertEqual(summary.item_count, 2)
        self.assertEqual(summary.subtotal, Decimal("81.00"))
        self.assertEqual(summary.total, Decimal("87.48"))
        self.assertEqual(summary.tax, Decimal("6.48"))
        self.assertEqual(summary.issue_count, 0)

    def test_summary_with_no_items(self):
        summary = summarize([], issues=[])
        self.assertEqual(summary.item_count, 0)
        self.assertEqual(summary.subtotal, Decimal("0.00"))
        self.assertEqual(summary.total, Decimal("0.00"))
        self.assertEqual(summary.tax, Decimal("0.00"))

    def test_summary_reports_issue_count(self):
        issues = [Issue("A", "duplicate line_id 'A'")]
        summary = summarize([make_item()], issues=issues)
        self.assertEqual(summary.issue_count, 1)


if __name__ == "__main__":
    unittest.main()
