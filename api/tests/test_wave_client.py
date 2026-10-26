from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.wave.client import (
    WaveAccount,
    WaveAccountsResult,
    WaveApiError,
    WaveAuthError,
    WaveBusiness,
    WaveClient,
)


@pytest.mark.anyio
async def test_get_user_businesses_success():
    mock_payload = {
        "data": {
            "businesses": {
                "edges": [
                    {
                        "node": {
                            "id": "biz_1",
                            "name": "Company One",
                            "isPersonal": False,
                        }
                    },
                    {
                        "node": {
                            "id": "biz_2",
                            "name": "Personal Books",
                            "isPersonal": True,
                        }
                    },
                ]
            }
        }
    }

    mock_resp = httpx.Response(status_code=200, json=mock_payload, request=httpx.Request("POST", "http://test"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        businesses = await WaveClient.get_user_businesses("token-abc")
        assert len(businesses) == 2
        assert businesses[0] == WaveBusiness(id="biz_1", name="Company One", is_personal=False)
        assert businesses[1] == WaveBusiness(id="biz_2", name="Personal Books", is_personal=True)


@pytest.mark.anyio
async def test_get_user_businesses_missing_data():
    mock_payload = {"data": {}}
    mock_resp = httpx.Response(status_code=200, json=mock_payload, request=httpx.Request("POST", "http://test"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(WaveApiError, match="Wave API did not return businesses information"):
            await WaveClient.get_user_businesses("token-abc")


@pytest.mark.anyio
async def test_get_user_businesses_auth_error_http_401():
    mock_resp = httpx.Response(status_code=401, text="Unauthorized", request=httpx.Request("POST", "http://test"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(WaveAuthError, match="Invalid or expired Wave access token"):
            await WaveClient.get_user_businesses("bad-token")


@pytest.mark.anyio
async def test_get_user_businesses_auth_error_graphql_error():
    mock_payload = {
        "errors": [
            {
                "message": "Authentication failed",
                "extensions": {"code": "UNAUTHENTICATED"},
            }
        ]
    }
    mock_resp = httpx.Response(status_code=200, json=mock_payload, request=httpx.Request("POST", "http://test"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(WaveAuthError, match="Authentication failed"):
            await WaveClient.get_user_businesses("bad-token")


@pytest.mark.anyio
async def test_get_user_businesses_network_error():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection timed out")):
        with pytest.raises(WaveApiError, match="Network error connecting to Wave API"):
            await WaveClient.get_user_businesses("token-abc")


@pytest.mark.anyio
async def test_get_business_accounts_filtering():
    mock_payload = {
        "data": {
            "business": {
                "id": "biz_1",
                "name": "Company One",
                "accounts": {
                    "edges": [
                        # Archived account -> should be excluded
                        {
                            "node": {
                                "id": "acct_archived",
                                "name": "Old Bank",
                                "type": {"value": "ASSET"},
                                "subtype": {"value": "CASH_AND_BANK"},
                                "isArchived": True,
                            }
                        },
                        # Valid Anchor: Bank (Asset)
                        {
                            "node": {
                                "id": "acct_bank",
                                "name": "Checking Account",
                                "type": {"value": "ASSET"},
                                "subtype": {"value": "CASH_AND_BANK"},
                                "isArchived": False,
                            }
                        },
                        # Valid Anchor: Credit Card (Liability)
                        {
                            "node": {
                                "id": "acct_cc",
                                "name": "Visa 1234",
                                "type": {"value": "LIABILITY"},
                                "subtype": {"value": "CREDIT_CARD"},
                                "isArchived": False,
                            }
                        },
                        # Valid Anchor: Due to You and Other Business Owners (Liability)
                        {
                            "node": {
                                "id": "acct_due_to_owner",
                                "name": "Due to You and Other Business Owners",
                                "type": {"value": "LIABILITY"},
                                "subtype": {"value": "DUE_TO_YOU_AND_OTHER_OWNERS"},
                                "isArchived": False,
                            }
                        },
                        # Excluded from anchors: Owner's Equity (Equity)
                        {
                            "node": {
                                "id": "acct_equity",
                                "name": "Owner Equity",
                                "type": {"value": "EQUITY"},
                                "subtype": {"value": "OWNERS_EQUITY"},
                                "isArchived": False,
                            }
                        },
                        # Non-anchor asset (Accounts Receivable) -> excluded from anchors
                        {
                            "node": {
                                "id": "acct_ar",
                                "name": "Accounts Receivable",
                                "type": {"value": "ASSET"},
                                "subtype": {"value": "ACCOUNTS_RECEIVABLE"},
                                "isArchived": False,
                            }
                        },
                        # Expense category: standard
                        {
                            "node": {
                                "id": "acct_exp_supplies",
                                "name": "Office Supplies",
                                "type": {"value": "EXPENSE"},
                                "subtype": None,
                                "isArchived": False,
                            }
                        },
                        # Expense category: uncategorized expense
                        {
                            "node": {
                                "id": "acct_uncategorized",
                                "name": "Uncategorized Expense",
                                "type": {"value": "EXPENSE"},
                                "subtype": {"value": "UNCATEGORIZED_EXPENSE"},
                                "isArchived": False,
                            }
                        },
                        # Revenue category: uncategorized income
                        {
                            "node": {
                                "id": "acct_uncat_income",
                                "name": "Uncategorized Income",
                                "type": {"value": "INCOME"},
                                "subtype": {"value": "UNCATEGORIZED_INCOME"},
                                "isArchived": False,
                            }
                        },
                        # Liability: Taxes Payable
                        {
                            "node": {
                                "id": "acct_tax_payable",
                                "name": "Taxes Payable",
                                "type": {"value": "LIABILITY"},
                                "subtype": {"value": "OTHER_CURRENT_LIABILITY"},
                                "isArchived": False,
                            }
                        },
                        # Liability Anchor: Business Line of Credit
                        {
                            "node": {
                                "id": "acct_loc",
                                "name": "Operating Line of Credit",
                                "type": {"value": "LIABILITY"},
                                "subtype": {"value": "LOANS_AND_LINE_OF_CREDIT"},
                                "isArchived": False,
                            }
                        },
                    ]
                },
            }
        }
    }

    mock_resp = httpx.Response(status_code=200, json=mock_payload, request=httpx.Request("POST", "http://test"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res: WaveAccountsResult = await WaveClient.get_business_accounts("token-abc", "biz_1")

        # Anchors should have checking, credit card, due to owner, and line of credit, but NOT owner equity
        anchor_ids = [a.id for a in res.anchor_accounts]
        assert "acct_bank" in anchor_ids
        assert "acct_cc" in anchor_ids
        assert "acct_due_to_owner" in anchor_ids
        assert "acct_loc" in anchor_ids
        assert "acct_equity" not in anchor_ids
        assert anchor_ids == ["acct_bank", "acct_cc", "acct_due_to_owner", "acct_loc"]
        assert all(isinstance(a, WaveAccount) for a in res.anchor_accounts)

        # Liability accounts should include all non-archived liabilities
        liability_ids = [acct.id for acct in res.liability_accounts]
        assert "acct_cc" in liability_ids
        assert "acct_due_to_owner" in liability_ids
        assert "acct_tax_payable" in liability_ids
        assert "acct_loc" in liability_ids
        assert len(res.liability_accounts) == 4

        # Expense categories should have supplies, uncategorized expense, AND uncategorized income
        exp_ids = [c.id for c in res.expense_categories]
        assert exp_ids == ["acct_exp_supplies", "acct_uncategorized", "acct_uncat_income"]

        supplies = next(c for c in res.expense_categories if c.id == "acct_exp_supplies")
        assert supplies.is_uncategorized is False

        uncat_exp = next(c for c in res.expense_categories if c.id == "acct_uncategorized")
        assert uncat_exp.is_uncategorized is True

        uncat_inc = next(c for c in res.expense_categories if c.id == "acct_uncat_income")
        assert uncat_inc.is_uncategorized is True
        assert uncat_inc.type == "INCOME"


@pytest.mark.anyio
async def test_create_money_transaction_positive_expense():
    captured_payload = None

    async def mock_post(*args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        data = {
            "data": {
                "moneyTransactionCreate": {
                    "didSucceed": True,
                    "inputErrors": [],
                    "transaction": {"id": "wave_tx_999"},
                }
            }
        }
        return httpx.Response(status_code=200, json=data, request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        tx_id = await WaveClient.create_money_transaction(
            token="token-abc",
            business_id="biz_1",
            external_id="wrangler_uuid_123",
            date="2026-10-20",
            description="Office Chairs",
            amount=Decimal("250.75"),
            anchor_account_id="acct_anchor_1",
            category_account_id="acct_cat_1",
            notes="Receipt: chair.png",
        )

        assert tx_id == "wave_tx_999"
        assert captured_payload is not None
        inp = captured_payload["variables"]["input"]
        assert inp["externalId"] == "wrangler_uuid_123"
        assert inp["businessId"] == "biz_1"
        assert inp["date"] == "2026-10-20"
        assert inp["description"] == "Office Chairs"
        assert inp["notes"] == "Receipt: chair.png"
        # Anchor check: WITHDRAWAL
        assert inp["anchor"]["accountId"] == "acct_anchor_1"
        assert inp["anchor"]["amount"] == 250.75
        assert inp["anchor"]["direction"] == "WITHDRAWAL"
        # LineItems check: INCREASE
        assert len(inp["lineItems"]) == 1
        assert inp["lineItems"][0]["accountId"] == "acct_cat_1"
        assert inp["lineItems"][0]["amount"] == 250.75
        assert inp["lineItems"][0]["balance"] == "INCREASE"


@pytest.mark.anyio
async def test_create_money_transaction_negative_refund():
    captured_payload = None

    async def mock_post(*args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        data = {
            "data": {
                "moneyTransactionCreate": {
                    "didSucceed": True,
                    "inputErrors": [],
                    "transaction": {"id": "wave_refund_888"},
                }
            }
        }
        return httpx.Response(status_code=200, json=data, request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        tx_id = await WaveClient.create_money_transaction(
            token="token-abc",
            business_id="biz_1",
            external_id="wrangler_uuid_refund",
            date="2026-10-20",
            description="Item Return",
            amount=Decimal("-45.50"),
            anchor_account_id="acct_anchor_1",
            category_account_id="acct_cat_1",
        )

        assert tx_id == "wave_refund_888"
        inp = captured_payload["variables"]["input"]
        assert "notes" not in inp
        # Anchor check: DEPOSIT with absolute amount
        assert inp["anchor"]["accountId"] == "acct_anchor_1"
        assert inp["anchor"]["amount"] == 45.50
        assert inp["anchor"]["direction"] == "DEPOSIT"
        # LineItems check: DECREASE with absolute amount
        assert len(inp["lineItems"]) == 1
        assert inp["lineItems"][0]["accountId"] == "acct_cat_1"
        assert inp["lineItems"][0]["amount"] == 45.50
        assert inp["lineItems"][0]["balance"] == "DECREASE"


@pytest.mark.anyio
async def test_create_money_transaction_input_errors():
    mock_payload = {
        "data": {
            "moneyTransactionCreate": {
                "didSucceed": False,
                "inputErrors": [
                    {
                        "path": ["input", "anchor", "accountId"],
                        "message": "Account not found or inactive",
                        "code": "INVALID",
                    }
                ],
                "transaction": None,
            }
        }
    }

    mock_resp = httpx.Response(status_code=200, json=mock_payload, request=httpx.Request("POST", "http://test"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(WaveApiError, match="Account not found or inactive"):
            await WaveClient.create_money_transaction(
                token="token-abc",
                business_id="biz_1",
                external_id="wrangler_uuid_123",
                date="2026-10-20",
                description="Failed Tx",
                amount=Decimal("100.00"),
                anchor_account_id="acct_bad",
                category_account_id="acct_cat_1",
            )


@pytest.mark.anyio
async def test_create_money_transaction_with_direction_overrides():
    captured_payload = None

    async def mock_post(*args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        data = {
            "data": {
                "moneyTransactionCreate": {
                    "didSucceed": True,
                    "inputErrors": [],
                    "transaction": {"id": "wave_tx_custom_dir"},
                }
            }
        }
        return httpx.Response(status_code=200, json=data, request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        tx_id = await WaveClient.create_money_transaction(
            token="token-abc",
            business_id="biz_1",
            external_id="wrangler_tax_accrual_1",
            date="2026-10-31",
            description="Tax Accrual",
            amount=Decimal("1200.00"),
            anchor_account_id="acct_tax_payable",
            category_account_id="acct_tax_expense",
            anchor_direction="DEPOSIT",
            line_balance="DECREASE",
        )

        assert tx_id == "wave_tx_custom_dir"
        assert captured_payload is not None
        inp = captured_payload["variables"]["input"]
        assert inp["anchor"]["direction"] == "DEPOSIT"
        assert inp["lineItems"][0]["balance"] == "DECREASE"
