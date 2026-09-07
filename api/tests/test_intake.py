from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.intake import BaseIntakeParser, ManualIntakeParser, ParsedTransaction


class DummyCustomParser(BaseIntakeParser):
    @property
    def source_name(self) -> str:
        return "amazon"

    def parse(self, raw_data: list[dict]) -> list[ParsedTransaction]:
        results = []
        for row in raw_data:
            results.append(
                ParsedTransaction(
                    source=self.source_name,
                    external_id=row["order_id"],
                    date=row["order_date"],
                    description=row["item_name"],
                    total_amount=Decimal(str(row["amount"])),
                    currency_code=row.get("currency", "USD"),
                    receipt_file_path=row.get("invoice_pdf"),
                )
            )
        return results


def test_base_intake_parser_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseIntakeParser()  # type: ignore[abstract]


def test_manual_intake_parser_single_dict():
    parser = ManualIntakeParser()
    assert parser.source_name == "manual"

    data = {
        "date": date(2026, 9, 6),
        "description": "Office supplies",
        "total_amount": Decimal("42.50"),
    }
    results = parser.parse(data)
    assert len(results) == 1
    item = results[0]
    assert item.source == "manual"
    assert item.external_id is None
    assert item.date == date(2026, 9, 6)
    assert item.description == "Office supplies"
    assert item.total_amount == Decimal("42.50")
    assert item.currency_code == "USD"
    assert item.receipt_file_path is None


def test_manual_intake_parser_list_of_dicts():
    parser = ManualIntakeParser()
    data = [
        {
            "date": date(2026, 9, 1),
            "description": "Item 1",
            "total_amount": Decimal("10.00"),
            "external_id": "MAN-001",
        },
        {
            "date": date(2026, 9, 2),
            "description": "Item 2",
            "total_amount": Decimal("20.00"),
            "currency_code": "CAD",
            "receipt_file_path": "receipts/item2.pdf",
        },
    ]
    results = parser.parse(data)
    assert len(results) == 2
    assert results[0].external_id == "MAN-001"
    assert results[0].currency_code == "USD"
    assert results[1].external_id is None
    assert results[1].currency_code == "CAD"
    assert results[1].receipt_file_path == "receipts/item2.pdf"


def test_manual_intake_parser_parsed_transaction_instance():
    parser = ManualIntakeParser()
    parsed = ParsedTransaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Pre-parsed item",
        total_amount=Decimal("15.00"),
    )
    results = parser.parse(parsed)
    assert len(results) == 1
    assert results[0] is parsed


def test_manual_intake_parser_validation_error():
    parser = ManualIntakeParser()
    with pytest.raises(ValidationError):
        # Missing required description and total_amount
        parser.parse({"date": date(2026, 9, 6)})


def test_custom_intake_parser():
    parser = DummyCustomParser()
    assert parser.source_name == "amazon"

    raw_items = [
        {
            "order_id": "111-222-333",
            "order_date": date(2026, 8, 15),
            "item_name": "USB-C Cable",
            "amount": "14.99",
            "currency": "USD",
            "invoice_pdf": "receipts/amazon_111.pdf",
        }
    ]
    parsed = parser.parse(raw_items)
    assert len(parsed) == 1
    item = parsed[0]
    assert item.source == "amazon"
    assert item.external_id == "111-222-333"
    assert item.date == date(2026, 8, 15)
    assert item.description == "USB-C Cable"
    assert item.total_amount == Decimal("14.99")
    assert item.currency_code == "USD"
    assert item.receipt_file_path == "receipts/amazon_111.pdf"
