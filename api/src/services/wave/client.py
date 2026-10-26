from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

WAVE_GRAPHQL_URL = "https://gql.waveapps.com/graphql/public"


@dataclass
class WaveBusiness:
    id: str
    name: str
    is_personal: bool


@dataclass
class WaveAccount:
    id: str
    name: str
    type: str
    subtype: str | None = None
    is_uncategorized: bool = False


@dataclass
class WaveAccountsResult:
    anchor_accounts: list[WaveAccount]
    expense_categories: list[WaveAccount]


class WaveAuthError(Exception):
    """Raised when authentication against Wave fails (invalid or expired token)."""

    pass


class WaveApiError(Exception):
    """Raised when upstream Wave API returns errors or fails."""

    pass


GET_BUSINESSES_QUERY = """
query GetBusinesses {
  businesses(page: 1, pageSize: 50) {
    edges {
      node {
        id
        name
        isPersonal
      }
    }
  }
}
"""

GET_USER_BUSINESSES_QUERY = GET_BUSINESSES_QUERY

GET_BUSINESS_ACCOUNTS_QUERY = """
query GetBusinessAccounts($businessId: ID!) {
  business(id: $businessId) {
    id
    name
    accounts(page: 1, pageSize: 500) {
      edges {
        node {
          id
          name
          type {
            value
            name
          }
          subtype {
            value
            name
          }
          isArchived
        }
      }
    }
  }
}
"""

CREATE_MONEY_TRANSACTION_MUTATION = """
mutation CreateMoneyTransaction($input: MoneyTransactionCreateInput!) {
  moneyTransactionCreate(input: $input) {
    didSucceed
    inputErrors {
      path
      message
      code
    }
    transaction {
      id
    }
  }
}
"""


class WaveClient:
    """GraphQL client targeting Wave's public API."""

    @classmethod
    async def _execute_graphql(
        cls,
        token: str,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(WAVE_GRAPHQL_URL, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise WaveApiError(f"Network error connecting to Wave API: {exc}") from exc

        if resp.status_code == 401:
            raise WaveAuthError("Invalid or expired Wave access token")
        if resp.status_code >= 400:
            raise WaveApiError(f"Wave API returned HTTP {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
        except Exception as exc:
            raise WaveApiError(f"Invalid JSON response from Wave API: {resp.text}") from exc

        if "errors" in data and data["errors"]:
            for err in data["errors"]:
                msg = err.get("message", "")
                code = err.get("extensions", {}).get("code", "")
                if "UNAUTHENTICATED" in code or "unauthorized" in msg.lower() or "authentication" in msg.lower():
                    raise WaveAuthError(msg)
            error_msgs = "; ".join(err.get("message", str(err)) for err in data["errors"])
            raise WaveApiError(f"Wave GraphQL error: {error_msgs}")

        return data.get("data", {})

    @classmethod
    async def get_user_businesses(cls, token: str) -> list[WaveBusiness]:
        """Fetch all businesses accessible by the Wave bearer token."""
        data = await cls._execute_graphql(token, GET_BUSINESSES_QUERY)
        businesses_container = data.get("businesses")
        if businesses_container is None:
            raise WaveApiError("Wave API did not return businesses information")

        businesses_data = businesses_container.get("edges", [])
        businesses: list[WaveBusiness] = []
        for edge in businesses_data:
            node = edge.get("node", {})
            businesses.append(
                WaveBusiness(
                    id=node.get("id"),
                    name=node.get("name"),
                    is_personal=bool(node.get("isPersonal", False)),
                )
            )
        return businesses

    @classmethod
    async def get_business_accounts(cls, token: str, business_id: str) -> WaveAccountsResult:
        """Fetch business Chart of Accounts, filtering for eligible anchor accounts and active expense categories."""
        data = await cls._execute_graphql(token, GET_BUSINESS_ACCOUNTS_QUERY, {"businessId": business_id})
        biz_data = data.get("business")
        if not biz_data:
            raise WaveApiError(f"Business '{business_id}' not found in Wave")

        accounts_edges = biz_data.get("accounts", {}).get("edges", [])
        anchor_accounts: list[WaveAccount] = []
        expense_categories: list[WaveAccount] = []

        valid_anchor_subtypes = {
            "DUE_TO_YOU_AND_OTHER_OWNERS",
            "CASH_AND_BANK",
            "CREDIT_CARD",
            "MONEY_MARKET",
        }
        valid_anchor_types = {"ASSET", "LIABILITY"}

        for edge in accounts_edges:
            node = edge.get("node", {})
            if node.get("isArchived", False):
                continue

            type_obj = node.get("type", {})
            type_val = type_obj.get("value") if isinstance(type_obj, dict) else None

            subtype_obj = node.get("subtype")
            subtype_val = subtype_obj.get("value") if isinstance(subtype_obj, dict) else None

            if type_val in valid_anchor_types and subtype_val in valid_anchor_subtypes:
                anchor_accounts.append(
                    WaveAccount(
                        id=node.get("id"),
                        name=node.get("name"),
                        type=type_val,
                        subtype=subtype_val,
                        is_uncategorized=False,
                    )
                )

            if type_val == "EXPENSE":
                is_uncat = subtype_val == "UNCATEGORIZED_EXPENSE"
                expense_categories.append(
                    WaveAccount(
                        id=node.get("id"),
                        name=node.get("name"),
                        type=type_val,
                        subtype=subtype_val,
                        is_uncategorized=is_uncat,
                    )
                )

        return WaveAccountsResult(anchor_accounts=anchor_accounts, expense_categories=expense_categories)

    @classmethod
    async def create_money_transaction(
        cls,
        token: str,
        business_id: str,
        external_id: str,
        date: str,
        description: str,
        amount: Decimal,
        anchor_account_id: str,
        category_account_id: str,
        notes: str | None = None,
    ) -> str:
        """Execute Wave moneyTransactionCreate mutation with double-entry balance mappings."""
        float_amt = float(abs(amount))
        if amount > Decimal("0"):
            anchor_direction = "WITHDRAWAL"
            line_balance = "INCREASE"
        else:
            anchor_direction = "DEPOSIT"
            line_balance = "DECREASE"

        input_payload: dict[str, Any] = {
            "businessId": business_id,
            "externalId": external_id,
            "date": date,
            "description": description,
            "anchor": {
                "accountId": anchor_account_id,
                "amount": float_amt,
                "direction": anchor_direction,
            },
            "lineItems": [
                {
                    "accountId": category_account_id,
                    "amount": float_amt,
                    "balance": line_balance,
                }
            ],
        }
        if notes:
            input_payload["notes"] = notes

        data = await cls._execute_graphql(token, CREATE_MONEY_TRANSACTION_MUTATION, {"input": input_payload})
        result = data.get("moneyTransactionCreate", {})
        did_succeed = result.get("didSucceed", False)
        input_errors = result.get("inputErrors", [])

        if not did_succeed or input_errors:
            err_msg = "; ".join(f"{e.get('path', '')}: {e.get('message', '')}" for e in input_errors) or "Unknown error creating money transaction"
            raise WaveApiError(err_msg)

        tx = result.get("transaction")
        if not tx or not tx.get("id"):
            raise WaveApiError("Wave moneyTransactionCreate did not return a transaction ID")

        return str(tx["id"])
