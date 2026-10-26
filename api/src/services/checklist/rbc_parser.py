from __future__ import annotations

import csv
import datetime
import io
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.wave_category import WaveCategory


@dataclass
class NormalizedRbcRow:
    date: datetime.date
    raw_account_type: str
    description: str
    signed_amount: Decimal
    row_index: int


EXPECTED_HEADER = [
    "account type",
    "account number",
    "transaction date",
    "cheque number",
    "description 1",
    "description 2",
    "cad$",
    "usd$",
]


def _parse_date(date_str: str) -> datetime.date:
    clean_date = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.datetime.strptime(clean_date, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid Transaction Date format: '{date_str}', expected M/D/YYYY or YYYY-MM-DD")


def parse_rbc_csv(content: bytes | str, expected_account_type: str) -> list[NormalizedRbcRow]:
    if isinstance(content, bytes):
        # Handle UTF-8 with BOM or plain UTF-8
        text = content.decode("utf-8-sig")
    else:
        text = content

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    # Filter out empty lines
    non_empty_rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not non_empty_rows:
        raise ValueError("CSV file is empty")

    header_row = [cell.strip().lower() for cell in non_empty_rows[0]]
    if len(header_row) != len(EXPECTED_HEADER) or header_row != EXPECTED_HEADER:
        raise ValueError(f"Invalid CSV header. Expected exactly 8 columns: {', '.join(EXPECTED_HEADER)}, but got {', '.join(header_row)}")

    expected_acc_lower = expected_account_type.strip().lower()
    normalized_rows: list[NormalizedRbcRow] = []

    for idx, raw_row in enumerate(non_empty_rows[1:], start=1):
        if len(raw_row) < 7:
            continue

        raw_acc_type = raw_row[0].strip()
        if raw_acc_type.lower() != expected_acc_lower:
            raise ValueError(f"File contains invalid Account Type '{raw_acc_type}', expected '{expected_account_type}'")

        date_val = _parse_date(raw_row[2])

        desc1 = re.sub(r"\s+", " ", raw_row[4]).strip()
        desc2 = re.sub(r"\s+", " ", raw_row[5]).strip()

        if desc2:
            desc1_base = desc1.rstrip(" -").strip() if desc1.endswith("-") else desc1
            description = f"{desc1_base} - {desc2}"
        else:
            description = desc1

        cad_str = raw_row[6].replace("$", "").replace(",", "").strip()
        if not cad_str:
            raise ValueError(f"Row {idx}: missing CAD$ amount")
        raw_cad = Decimal(cad_str)

        if expected_acc_lower == "chequing":
            signed_amount = raw_cad
        elif expected_acc_lower == "mastercard":
            signed_amount = -raw_cad
        else:
            signed_amount = raw_cad

        normalized_rows.append(
            NormalizedRbcRow(
                date=date_val,
                raw_account_type=raw_acc_type,
                description=description,
                signed_amount=signed_amount,
                row_index=idx,
            )
        )

    normalized_rows.sort(key=lambda r: (r.date, r.row_index))
    return normalized_rows


def resolve_category_for_row(row: NormalizedRbcRow, wave_categories: list[WaveCategory]) -> tuple[str, bool]:
    desc_clean = row.description.strip().lower()
    target_category_name: str | None = None

    if desc_clean == "activity fee":
        target_category_name = "Bank Service Charges"
    elif desc_clean == "monthly fee":
        target_category_name = "Bank Service Charges"
    elif desc_clean == "other loan - loan interest":
        target_category_name = "Interest Expense"
    elif desc_clean.startswith("purchase interest"):
        target_category_name = "Interest Expense"
    elif desc_clean == "wave pro toronto":
        target_category_name = "Accounting Fees"

    if target_category_name:
        for cat in wave_categories:
            if cat.name.strip().lower() == target_category_name.lower():
                return cat.wave_account_id, True

    uncat_exp_id: str | None = None
    uncat_inc_id: str | None = None

    for cat in wave_categories:
        if cat.is_uncategorized:
            if cat.account_subtype == "UNCATEGORIZED_INCOME" or cat.account_type in ("REVENUE", "INCOME"):
                uncat_inc_id = cat.wave_account_id
            elif cat.account_subtype == "UNCATEGORIZED_EXPENSE" or cat.account_type == "EXPENSE":
                uncat_exp_id = cat.wave_account_id

    if row.signed_amount < Decimal("0"):
        if uncat_exp_id:
            return uncat_exp_id, False
        fallback = wave_categories[0].wave_account_id if wave_categories else ""
        return fallback, False
    else:
        chosen_id = uncat_inc_id or uncat_exp_id
        if chosen_id:
            return chosen_id, False
        fallback = wave_categories[0].wave_account_id if wave_categories else ""
        return fallback, False
