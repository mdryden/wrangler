import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from models.allocation import Allocation, SyncStatus
from models.transaction import Transaction
from services.export import generate_wave_csv


def test_generate_wave_csv_empty():
    csv_str = generate_wave_csv([])
    assert csv_str == "Date,Description,Amount\r\n"


def test_generate_wave_csv_basic():
    cid = uuid.uuid4()
    t1 = Transaction(
        id=uuid.uuid4(),
        source="manual",
        date=date(2026, 9, 1),
        description="Office Supplies",
        total_amount=Decimal("12.50"),
    )
    a1 = Allocation(
        id=uuid.uuid4(),
        transaction_id=t1.id,
        transaction=t1,
        company_id=cid,
        amount=Decimal("12.50"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )

    t2 = Transaction(
        id=uuid.uuid4(),
        source="manual",
        date=date(2026, 9, 2),
        description="Refund for returned item",
        total_amount=Decimal("-50.00"),
    )
    a2 = Allocation(
        id=uuid.uuid4(),
        transaction_id=t2.id,
        transaction=t2,
        company_id=cid,
        amount=Decimal("-50.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )

    csv_str = generate_wave_csv([a1, a2], company_id=cid)

    reader = list(csv.reader(io.StringIO(csv_str)))
    assert len(reader) == 3
    assert reader[0] == ["Date", "Description", "Amount"]
    assert reader[1] == ["2026-09-01", "Office Supplies", "12.50"]
    assert reader[2] == ["2026-09-02", "Refund for returned item", "-50.00"]


def test_generate_wave_csv_excludes_personal_and_other_companies():
    cid1 = uuid.uuid4()
    cid2 = uuid.uuid4()

    t1 = Transaction(id=uuid.uuid4(), source="manual", date=date(2026, 9, 1), description="Business 1", total_amount=Decimal("10.00"))
    a1 = Allocation(transaction_id=t1.id, transaction=t1, company_id=cid1, amount=Decimal("10.00"), is_personal=False)

    t2 = Transaction(id=uuid.uuid4(), source="manual", date=date(2026, 9, 2), description="Personal Lunch", total_amount=Decimal("20.00"))
    a2 = Allocation(transaction_id=t2.id, transaction=t2, company_id=cid1, amount=Decimal("20.00"), is_personal=True)

    t3 = Transaction(id=uuid.uuid4(), source="manual", date=date(2026, 9, 3), description="Company 2 item", total_amount=Decimal("30.00"))
    a3 = Allocation(transaction_id=t3.id, transaction=t3, company_id=cid2, amount=Decimal("30.00"), is_personal=False)

    csv_str = generate_wave_csv([a1, a2, a3], company_id=cid1)

    reader = list(csv.reader(io.StringIO(csv_str)))
    assert len(reader) == 2
    assert reader[1] == ["2026-09-01", "Business 1", "10.00"]


def test_generate_wave_csv_rfc4180_escaping():
    cid = uuid.uuid4()
    t = Transaction(
        id=uuid.uuid4(),
        source="manual",
        date=date(2026, 9, 5),
        description='Acme, Inc. "Special" Items & Hardware\nSecond Line',
        total_amount=Decimal("99.90"),
    )
    a = Allocation(
        id=uuid.uuid4(),
        transaction_id=t.id,
        transaction=t,
        company_id=cid,
        amount=Decimal("99.90"),
        is_personal=False,
    )

    csv_str = generate_wave_csv([a])

    # Check raw string contains proper RFC 4180 quoting
    assert '"Acme, Inc. ""Special"" Items & Hardware\nSecond Line"' in csv_str
    assert "99.90" in csv_str

    # Parse with standard csv reader
    reader = list(csv.reader(io.StringIO(csv_str)))
    assert len(reader) == 2
    assert reader[1][0] == "2026-09-05"
    assert reader[1][1] == 'Acme, Inc. "Special" Items & Hardware\nSecond Line'
    assert reader[1][2] == "99.90"
