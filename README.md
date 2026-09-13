# invoice-line-lint

A command line tool that checks a CSV export of invoice line items for two
common problems:

- the recorded `line_total` doesn't actually match `quantity * unit_price *
  (1 + tax_rate)` (rounding bugs, a stale export, someone hand-edited a cell)
- the same `line_id` shows up more than once, which usually means a join
  went wrong upstream

I keep running into invoice exports from different billing systems where the
totals are just slightly off, and eyeballing a spreadsheet for it doesn't
scale. This tool reads the CSV, recomputes what each line should add up to,
and tells you exactly which rows disagree.

## Input format

A CSV file with a header row and these columns:

```
line_id,description,quantity,unit_price,tax_rate,line_total
```

`tax_rate` is a fraction, so `0.0825` for 8.25%, not `8.25`.

A few common alternate headers are recognized too, since different billing
systems name these columns differently. Matching is case-insensitive and
treats spaces/hyphens the same as underscores:

- `line_id`: `id`, `item_id`, `line_item_id`
- `description`: `desc`, `item`, `item_description`
- `quantity`: `qty`
- `unit_price`: `price`, `rate`, `unit_cost`
- `tax_rate`: `tax`, `tax_pct`, `tax_percent`
- `line_total`: `amount`, `total`, `line_amount`

If a file happens to have both the canonical column and an alias (e.g. both
`line_total` and `amount`), the canonical one wins.

Example (`invoices.csv`):

```
line_id,description,quantity,unit_price,tax_rate,line_total
INV-001-1,Widget,10,4.50,0.08,48.60
INV-001-2,Bracket,3,12.00,0.08,38.88
INV-001-2,Bracket,3,12.00,0.08,38.88
```

## Usage

```
python -m invoice_line_lint.cli invoices.csv
```

Output:

```
checked 3 line item(s)
  subtotal: 117.00
  tax:      9.36
  total:    126.36

1 issue(s) found:
  - [INV-001-2] duplicate line_id 'INV-001-2'
```

Exit code is `0` when the file is clean, `1` when issues or unreadable rows
were found, `2` when the file itself couldn't be opened.

Pass `--tolerance` to change how much rounding drift is allowed (default
`0.01`):

```
python -m invoice_line_lint.cli invoices.csv --tolerance 0.05
```

## Design

All of the actual checking logic lives in `invoice_line_lint/core.py` as
plain functions: give them a `LineItem` or a list of them, get back a value,
no file handles or globals involved. `invoice_line_lint/cli.py` is the thin
layer that reads the file, calls into `core`, and prints the result. That
split is intentional - it's what lets the logic be tested without touching
disk.

## Requirements

Python 3.9 or newer. No third-party dependencies.

## Tests

```
python -m unittest
```
