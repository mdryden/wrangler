import datetime
import io
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.checklist import ChecklistConfig
from models.company import Company
from models.wave_category import WaveCategory
from services.wave.client import WaveAccount, WaveAccountsResult, WaveClient

MOCK_ADMIN = "admin"
MOCK_PASSWORD = "admin"
MOCK_SECRET_KEY = "mock-secret-key-that-is-at-least-32-characters-long!"
MOCK_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def set_mock_env(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", MOCK_ADMIN)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", MOCK_PASSWORD)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", MOCK_ALGORITHM)


@pytest.fixture
def auth_headers():
    token = create_access_token(
        data={"sub": MOCK_ADMIN},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
        expires_delta=datetime.timedelta(minutes=60),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_checklist_config_get_and_put(client, auth_headers, db_session):
    # GET /config creates singleton with defaults
    resp = client.get("/api/checklist/config", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_id"] is None
    assert data["company_name"] is None
    assert data["is_wave_connected"] is False
    assert data["wave_web_business_slug"] == "d2977f10-6793-4504-a139-f0d6872b2628"

    # Create connected company
    company = Company(
        name="Michelle Dryden LTD",
        wave_api_token="tok_123",
        wave_business_id="biz_123",
    )
    db_session.add(company)
    db_session.commit()

    # PUT /config updates settings
    put_payload = {
        "company_id": str(company.id),
        "chequing_wave_account_id": "acct_chq",
        "chequing_wave_account_name": "RBC Chequing",
        "mastercard_wave_account_id": "acct_mc",
        "mastercard_wave_account_name": "RBC Mastercard",
        "tax_expense_wave_account_id": "acct_tax_exp",
        "tax_expense_wave_account_name": "Taxes - Corporate Tax",
        "tax_payable_wave_account_id": "acct_tax_pay",
        "tax_payable_wave_account_name": "Taxes Payable",
        "wave_web_business_slug": "custom-slug-123",
        "last_chequing_tx_date": "2026-09-28",
        "last_mastercard_tx_date": "2026-09-24",
    }
    put_resp = client.put("/api/checklist/config", json=put_payload, headers=auth_headers)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["company_id"] == str(company.id)
    assert put_data["company_name"] == "Michelle Dryden LTD"
    assert put_data["is_wave_connected"] is True
    assert put_data["chequing_wave_account_id"] == "acct_chq"
    assert put_data["last_chequing_tx_date"] == "2026-09-28"
    assert put_data["last_mastercard_tx_date"] == "2026-09-24"
    assert put_data["wave_web_business_slug"] == "custom-slug-123"


def test_checklist_wave_accounts_grouped(client, auth_headers, db_session):
    company = Company(
        name="Grouped Accounts LTD",
        wave_api_token="tok_group",
        wave_business_id="biz_group",
    )
    db_session.add(company)
    db_session.commit()

    mock_result = WaveAccountsResult(
        anchor_accounts=[
            WaveAccount(id="a_bank", name="Chequing", type="ASSET", subtype="CASH_AND_BANK"),
            WaveAccount(id="a_cc", name="Credit Card", type="LIABILITY", subtype="CREDIT_CARD"),
            WaveAccount(id="a_loc", name="Line of Credit", type="LIABILITY", subtype="LOANS_AND_LINE_OF_CREDIT"),
        ],
        expense_categories=[
            WaveAccount(id="e_supplies", name="Office Supplies", type="EXPENSE", subtype=None),
            WaveAccount(id="e_uncat_exp", name="Uncategorized Expense", type="EXPENSE", subtype="UNCATEGORIZED_EXPENSE", is_uncategorized=True),
            WaveAccount(id="e_uncat_inc", name="Uncategorized Income", type="INCOME", subtype="UNCATEGORIZED_INCOME", is_uncategorized=True),
        ],
        liability_accounts=[
            WaveAccount(id="l_cc", name="Credit Card", type="LIABILITY", subtype="CREDIT_CARD"),
            WaveAccount(id="l_tax", name="Taxes Payable", type="LIABILITY", subtype="OTHER_CURRENT_LIABILITY"),
            WaveAccount(id="l_loc", name="Line of Credit", type="LIABILITY", subtype="LOANS_AND_LINE_OF_CREDIT"),
        ],
    )

    with patch.object(WaveClient, "get_business_accounts", new_callable=AsyncMock, return_value=mock_result):
        resp = client.get(f"/api/checklist/wave-accounts/{company.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["bank_and_cc_accounts"]) == 3
        bank_ids = [a["id"] for a in data["bank_and_cc_accounts"]]
        assert "a_bank" in bank_ids
        assert "a_cc" in bank_ids
        assert "a_loc" in bank_ids

        # Expense categories must only include type == EXPENSE (excluding uncategorized income)
        assert len(data["expense_accounts"]) == 2
        exp_ids = [e["id"] for e in data["expense_accounts"]]
        assert "e_supplies" in exp_ids
        assert "e_uncat_exp" in exp_ids
        assert "e_uncat_inc" not in exp_ids

        assert len(data["liability_accounts"]) == 3
        liab_ids = [liab["id"] for liab in data["liability_accounts"]]
        assert "l_tax" in liab_ids


def test_monthly_checklist_get_and_carry_forward(client, auth_headers, db_session):
    # Invalid format raises 400
    bad_resp = client.get("/api/checklist/months/invalid-month", headers=auth_headers)
    assert bad_resp.status_code == 400
    assert "Invalid year_month format" in bad_resp.json()["detail"]

    # Month 1: 2026-09 initialized with defaults
    resp1 = client.get("/api/checklist/months/2026-09", headers=auth_headers)
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["year_month"] == "2026-09"
    assert d1["prior_soft_cap"] == "17600.00"
    assert d1["monthly_loc_reduction"] == "400.00"
    assert d1["current_soft_cap"] == "17200.00"
    assert d1["tax_rate"] == "12.00"
    assert d1["tax_reserve_amount"] is None
    assert d1["maximum_safe_draw"] is None
    assert "start=2026-09-01" in d1["wave_cash_flow_url"]
    assert "end=2026-09-30" in d1["wave_cash_flow_url"]

    # Month 2: 2026-10 carries forward current_soft_cap (17200.00) from 2026-09 as prior_soft_cap
    resp2 = client.get("/api/checklist/months/2026-10", headers=auth_headers)
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["year_month"] == "2026-10"
    assert d2["prior_soft_cap"] == "17200.00"
    assert d2["monthly_loc_reduction"] == "400.00"
    assert d2["current_soft_cap"] == "16800.00"
    assert "start=2026-10-01" in d2["wave_cash_flow_url"]
    assert "end=2026-10-31" in d2["wave_cash_flow_url"]


def test_monthly_checklist_patch_and_safe_draw(client, auth_headers, db_session):
    patch_payload = {
        "completed_steps": ["import_chequing"],
        "net_operating_cash": "4200.00",
        "tax_rate": "12.00",
        "prior_soft_cap": "17600.00",
        "monthly_loc_reduction": "400.00",
        "tax_liability": "1504.00",
        "actual_loc_balance": "11200.00",
    }
    resp = client.patch("/api/checklist/months/2026-09", json=patch_payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed_steps"] == ["import_chequing"]
    assert data["net_operating_cash"] == "4200.00"
    # 4200.00 * 12% = 504.00
    assert data["tax_reserve_amount"] == "504.00"
    assert data["current_soft_cap"] == "17200.00"
    # 17200 - 1504 - 11200 = 4496.00
    assert data["maximum_safe_draw"] == "4496.00"


def test_sync_rbc_chequing_csv(client, auth_headers, db_session):
    company = Company(
        name="Chequing Test LTD",
        wave_api_token="tok_chq",
        wave_business_id="biz_chq",
    )
    db_session.add(company)
    db_session.commit()

    config = ChecklistConfig(
        id=1,
        company_id=company.id,
        chequing_wave_account_id="wave_chq_anchor",
    )
    db_session.add(config)

    cat_fee = WaveCategory(company_id=company.id, wave_account_id="cat_fee_id", name="Bank Service Charges", account_type="EXPENSE")
    cat_int = WaveCategory(company_id=company.id, wave_account_id="cat_int_id", name="Interest Expense", account_type="EXPENSE")
    cat_uncat_exp = WaveCategory(
        company_id=company.id,
        wave_account_id="cat_uncat_exp_id",
        name="Uncategorized Expense",
        account_type="EXPENSE",
        account_subtype="UNCATEGORIZED_EXPENSE",
        is_uncategorized=True,
    )
    cat_uncat_inc = WaveCategory(
        company_id=company.id,
        wave_account_id="cat_uncat_inc_id",
        name="Uncategorized Income",
        account_type="INCOME",
        account_subtype="UNCATEGORIZED_INCOME",
        is_uncategorized=True,
    )
    db_session.add_all([cat_fee, cat_int, cat_uncat_exp, cat_uncat_inc])
    db_session.commit()

    csv_content = (
        "Account Type,Account Number,Transaction Date,Cheque Number,Description 1,Description 2,CAD$,USD$\n"
        "Chequing,12345,9/15/2026,,Monthly fee,, -15.00,\n"
        "Chequing,12345,9/20/2026,,Other loan, Loan interest,-120.50,\n"
        "Chequing,12345,9/25/2026,,Mobile cheque deposit -     5318,, 2500.00,\n"
        "Chequing,12345,9/28/2026,,Some Unknown Store,,-45.00,\n"
    )

    with patch.object(WaveClient, "create_money_transaction", new_callable=AsyncMock, return_value="tx_123") as mock_create:
        resp = client.post(
            "/api/checklist/months/2026-09/sync-rbc-csv",
            data={"account_type": "chequing"},
            files={"file": ("shellco-chq.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 4
        assert data["synced_count"] == 4
        assert data["failed_count"] == 0
        assert data["auto_categorized_count"] == 2  # Monthly fee and Other loan
        assert data["uncategorized_count"] == 2  # Deposit and Store
        assert data["latest_transaction_date"] == "2026-09-28"
        assert mock_create.call_count == 4

        # Verify call details
        calls = mock_create.call_args_list
        # Call 1: Monthly fee
        assert calls[0].kwargs["anchor_direction"] == "WITHDRAWAL"
        assert calls[0].kwargs["line_balance"] == "INCREASE"
        assert calls[0].kwargs["category_account_id"] == "cat_fee_id"
        assert calls[0].kwargs["amount"] == Decimal("15.00")

        # Call 2: Other loan - Loan interest
        assert calls[1].kwargs["description"] == "Other loan - Loan interest"
        assert calls[1].kwargs["category_account_id"] == "cat_int_id"

        # Call 3: Mobile cheque deposit
        assert calls[2].kwargs["description"] == "Mobile cheque deposit - 5318"
        assert calls[2].kwargs["anchor_direction"] == "DEPOSIT"
        assert calls[2].kwargs["line_balance"] == "INCREASE"
        assert calls[2].kwargs["category_account_id"] == "cat_uncat_inc_id"
        assert calls[2].kwargs["amount"] == Decimal("2500.00")

        # Call 4: Some Unknown Store
        assert calls[3].kwargs["anchor_direction"] == "WITHDRAWAL"
        assert calls[3].kwargs["category_account_id"] == "cat_uncat_exp_id"

        # Check config updated
        db_session.refresh(config)
        assert config.last_chequing_tx_date == datetime.date(2026, 9, 28)

        # Check monthly checklist step completed
        month_resp = client.get("/api/checklist/months/2026-09", headers=auth_headers)
        assert "import_chequing" in month_resp.json()["completed_steps"]


def test_sync_rbc_mastercard_csv(client, auth_headers, db_session):
    company = Company(
        name="Mastercard Test LTD",
        wave_api_token="tok_mc",
        wave_business_id="biz_mc",
    )
    db_session.add(company)
    db_session.commit()

    config = ChecklistConfig(
        id=1,
        company_id=company.id,
        mastercard_wave_account_id="wave_mc_anchor",
    )
    db_session.add(config)

    cat_acct = WaveCategory(company_id=company.id, wave_account_id="cat_acct_id", name="Accounting Fees", account_type="EXPENSE")
    cat_int = WaveCategory(company_id=company.id, wave_account_id="cat_int_id", name="Interest Expense", account_type="EXPENSE")
    cat_uncat_exp = WaveCategory(
        company_id=company.id,
        wave_account_id="cat_uncat_exp_id",
        name="Uncategorized Expense",
        account_type="EXPENSE",
        account_subtype="UNCATEGORIZED_EXPENSE",
        is_uncategorized=True,
    )
    cat_uncat_inc = WaveCategory(
        company_id=company.id,
        wave_account_id="cat_uncat_inc_id",
        name="Uncategorized Income",
        account_type="INCOME",
        account_subtype="UNCATEGORIZED_INCOME",
        is_uncategorized=True,
    )
    db_session.add_all([cat_acct, cat_int, cat_uncat_exp, cat_uncat_inc])
    db_session.commit()

    csv_content = (
        "Account Type,Account Number,Transaction Date,Cheque Number,Description 1,Description 2,CAD$,USD$\n"
        "MasterCard,67890,9/10/2026,,Wave Pro Toronto,, 24.50,\n"
        "MasterCard,67890,9/18/2026,,Purchase interest charges,, 12.30,\n"
        "MasterCard,67890,9/22/2026,,Payment - Thank You,,-500.00,\n"
        "MasterCard,67890,9/24/2026,,Hardware Store,, 150.00,\n"
    )

    with patch.object(WaveClient, "create_money_transaction", new_callable=AsyncMock, return_value="tx_mc_123") as mock_create:
        resp = client.post(
            "/api/checklist/months/2026-09/sync-rbc-csv",
            data={"account_type": "mastercard"},
            files={"file": ("shellco-mc.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 4
        assert data["synced_count"] == 4
        assert data["auto_categorized_count"] == 2
        assert data["latest_transaction_date"] == "2026-09-24"

        calls = mock_create.call_args_list
        # Call 1: Wave Pro Toronto -> positive CAD 24.50 negated to -24.50 (WITHDRAWAL)
        assert calls[0].kwargs["anchor_direction"] == "WITHDRAWAL"
        assert calls[0].kwargs["category_account_id"] == "cat_acct_id"
        assert calls[0].kwargs["amount"] == Decimal("24.50")

        # Call 2: Purchase interest -> positive CAD 12.30 negated to -12.30 (WITHDRAWAL)
        assert calls[1].kwargs["anchor_direction"] == "WITHDRAWAL"
        assert calls[1].kwargs["category_account_id"] == "cat_int_id"

        # Call 3: Payment -> negative CAD -500.00 negated to +500.00 (DEPOSIT)
        assert calls[2].kwargs["anchor_direction"] == "DEPOSIT"
        assert calls[2].kwargs["category_account_id"] == "cat_uncat_inc_id"
        assert calls[2].kwargs["amount"] == Decimal("500.00")

        # Call 4: Hardware Store -> positive CAD 150.00 negated to -150.00 (WITHDRAWAL)
        assert calls[3].kwargs["anchor_direction"] == "WITHDRAWAL"
        assert calls[3].kwargs["category_account_id"] == "cat_uncat_exp_id"

        db_session.refresh(config)
        assert config.last_mastercard_tx_date == datetime.date(2026, 9, 24)

        month_resp = client.get("/api/checklist/months/2026-09", headers=auth_headers)
        assert "import_mastercard" in month_resp.json()["completed_steps"]


def test_sync_rbc_csv_validation_errors(client, auth_headers, db_session):
    company = Company(name="Validation LTD", wave_api_token="tok", wave_business_id="biz")
    db_session.add(company)
    db_session.commit()

    config = ChecklistConfig(id=1, company_id=company.id, chequing_wave_account_id="chq_acct")
    db_session.add(config)
    db_session.commit()

    # Mismatched account type: uploading MasterCard to chequing step
    mc_csv = "Account Type,Account Number,Transaction Date,Cheque Number,Description 1,Description 2,CAD$,USD$\nMasterCard,67890,9/10/2026,,Store,, 24.50,\n"
    resp = client.post(
        "/api/checklist/months/2026-09/sync-rbc-csv",
        data={"account_type": "chequing"},
        files={"file": ("test.csv", io.BytesIO(mc_csv.encode("utf-8")), "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "invalid Account Type 'MasterCard'" in resp.json()["detail"]

    # Invalid header
    bad_header_csv = "Col1,Col2,Col3\nVal1,Val2,Val3\n"
    bad_resp = client.post(
        "/api/checklist/months/2026-09/sync-rbc-csv",
        data={"account_type": "chequing"},
        files={"file": ("test.csv", io.BytesIO(bad_header_csv.encode("utf-8")), "text/csv")},
        headers=auth_headers,
    )
    assert bad_resp.status_code == 400
    assert "Invalid CSV header" in bad_resp.json()["detail"]


def test_sync_tax_accrual_to_wave(client, auth_headers, db_session):
    company = Company(name="Tax LTD", wave_api_token="tok_tax", wave_business_id="biz_tax")
    db_session.add(company)
    db_session.commit()

    config = ChecklistConfig(
        id=1,
        company_id=company.id,
        tax_expense_wave_account_id="acct_tax_exp_123",
        tax_payable_wave_account_id="acct_tax_pay_456",
    )
    db_session.add(config)
    db_session.commit()

    # Fails when tax reserve is <= 0
    resp_bad = client.post(
        "/api/checklist/months/2026-09/sync-tax-accrual",
        json={"net_operating_cash": "-500.00"},
        headers=auth_headers,
    )
    assert resp_bad.status_code == 400
    assert "Tax reserve amount must be greater than $0.00" in resp_bad.json()["detail"]

    with patch.object(WaveClient, "create_money_transaction", new_callable=AsyncMock, return_value="wave_accrual_tx_789") as mock_create:
        resp = client.post(
            "/api/checklist/months/2026-09/sync-tax-accrual",
            json={"net_operating_cash": "10000.00", "tax_rate": "12.00"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_reserve_amount"] == "1200.00"
        assert data["tax_accrual_wave_tx_id"] == "wave_accrual_tx_789"
        assert "calculate_net_cash_and_tax" in data["completed_steps"]

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["external_id"] == f"wrangler_tax_accrual_{company.id}_2026-09"
        assert kwargs["date"] == "2026-09-30"  # Last day of September
        assert kwargs["amount"] == Decimal("1200.00")
        assert kwargs["anchor_account_id"] == "acct_tax_pay_456"
        assert kwargs["category_account_id"] == "acct_tax_exp_123"
        assert kwargs["anchor_direction"] == "WITHDRAWAL"
        assert kwargs["line_balance"] == "INCREASE"
