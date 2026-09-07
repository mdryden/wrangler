import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from models.company import Company
from models.wave_category import WaveCategory


class WaveError(Exception):
    """Base exception for Wave integration errors."""


class WaveAuthError(WaveError):
    """Raised when authentication or OAuth operations fail."""


class WaveNotConnectedError(WaveError):
    """Raised when an operation requires Wave credentials but the company is not connected."""


class WaveConfigurationError(WaveError):
    """Raised when required Wave configuration on a company or environment is missing."""


class WaveGraphQLError(WaveError):
    """Raised when Wave GraphQL API returns errors."""

    def __init__(self, errors: list[dict[str, Any]] | str):
        super().__init__(str(errors))
        self.errors = errors


def generate_oauth_state(company_id: uuid.UUID, expires_in_minutes: int = 15) -> str:
    """Generate a signed JWT for the OAuth state parameter containing the company ID."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(company_id),
        "company_id": str(company_id),
        "type": "wave_oauth",
        "iat": now,
        "exp": now + timedelta(minutes=expires_in_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_oauth_state(state: str) -> uuid.UUID:
    """Validate and unpack the signed OAuth state JWT, returning the target company_id."""
    try:
        payload = jwt.decode(state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise WaveAuthError(f"Invalid or expired OAuth state parameter: {exc}") from exc

    if payload.get("type") != "wave_oauth":
        raise WaveAuthError("Invalid OAuth state token type")

    company_id_str = payload.get("company_id") or payload.get("sub")
    if not company_id_str:
        raise WaveAuthError("OAuth state parameter missing company ID")

    try:
        return uuid.UUID(company_id_str)
    except ValueError as exc:
        raise WaveAuthError(f"Invalid company UUID in OAuth state: {exc}") from exc


def build_oauth_authorize_url(company_id: uuid.UUID) -> str:
    """Build the full Wave OAuth authorization URL requesting required scopes."""
    state = generate_oauth_state(company_id)
    params = {
        "client_id": settings.WAVE_CLIENT_ID,
        "response_type": "code",
        "scope": "business:read account:read transaction:write",
        "state": state,
        "redirect_uri": settings.WAVE_REDIRECT_URI,
    }
    return f"{settings.WAVE_AUTHORIZE_URL.rstrip('/')}/?{urlencode(params)}"


def exchange_oauth_code(code: str, http_client: httpx.Client | None = None) -> dict[str, Any]:
    """Exchange an authorization code for Wave access and refresh tokens."""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.WAVE_CLIENT_ID,
        "client_secret": settings.WAVE_CLIENT_SECRET,
        "redirect_uri": settings.WAVE_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    client = http_client if http_client is not None else httpx.Client(timeout=30.0)
    try:
        response = client.post(settings.WAVE_TOKEN_URL, data=payload, headers=headers)
    except httpx.RequestError as exc:
        raise WaveAuthError(f"Network error communicating with Wave token endpoint: {exc}") from exc
    finally:
        if http_client is None:
            client.close()

    if response.status_code != 200:
        raise WaveAuthError(f"Wave token exchange failed ({response.status_code}): {response.text}")

    try:
        data = response.json()
    except Exception as exc:
        raise WaveAuthError(f"Invalid JSON response from Wave token endpoint: {exc}") from exc

    if "access_token" not in data:
        raise WaveAuthError(f"Wave token endpoint response missing access_token: {data}")

    return data


CHART_OF_ACCOUNTS_QUERY = """
query GetChartOfAccounts($businessId: ID!, $page: Int!, $pageSize: Int!) {
  business(id: $businessId) {
    id
    accounts(page: $page, pageSize: $pageSize, types: [EXPENSE, ASSET, INCOME]) {
      pageInfo {
        currentPage
        totalPages
        totalCount
      }
      edges {
        node {
          id
          name
          type {
            name
            value
          }
          subtype {
            name
            value
          }
          isArchived
        }
      }
    }
  }
}
"""


class WaveClient:
    """HTTP client utility for Wave GraphQL and OAuth endpoints."""

    def __init__(
        self,
        company: Company,
        db: Session | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.company = company
        self.db = db
        self._http_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=30.0)

    def is_token_expired(self, buffer_seconds: int = 60) -> bool:
        """Check whether the company's access token is expired or close to expiring."""
        expires_at = self.company.wave_token_expires_at
        if expires_at is None:
            return True

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        return expires_at <= datetime.now(UTC) + timedelta(seconds=buffer_seconds)

    def refresh_token(self) -> dict[str, Any]:
        """Refresh access token using wave_refresh_token and persist updates to database."""
        refresh_token = self.company.wave_refresh_token
        if not refresh_token:
            raise WaveAuthError("Company has no wave_refresh_token configured")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.WAVE_CLIENT_ID,
            "client_secret": settings.WAVE_CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        client = self._get_client()
        should_close = self._http_client is None
        try:
            response = client.post(settings.WAVE_TOKEN_URL, data=payload, headers=headers)
        except httpx.RequestError as exc:
            raise WaveAuthError(f"Network error refreshing Wave token: {exc}") from exc
        finally:
            if should_close:
                client.close()

        if response.status_code != 200:
            raise WaveAuthError(f"Wave token refresh failed ({response.status_code}): {response.text}")

        try:
            data = response.json()
        except Exception as exc:
            raise WaveAuthError(f"Invalid JSON returned by Wave token refresh: {exc}") from exc

        access_token = data.get("access_token")
        if not access_token:
            raise WaveAuthError(f"Refresh response missing access_token: {data}")

        self.company.wave_access_token = access_token
        if data.get("refresh_token"):
            self.company.wave_refresh_token = data["refresh_token"]

        expires_in = data.get("expires_in")
        if expires_in is not None:
            self.company.wave_token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

        if self.db is not None:
            self.db.add(self.company)
            self.db.commit()
            self.db.refresh(self.company)

        return data

    def ensure_valid_token(self) -> str:
        """Verify token expiration and refresh automatically if needed, returning a valid access token."""
        if not self.company.wave_access_token:
            raise WaveNotConnectedError(f"Company '{self.company.name}' is not connected to Wave")

        if self.is_token_expired():
            self.refresh_token()

        return self.company.wave_access_token  # type: ignore[return-value]

    def query_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query against the Wave GraphQL API using a valid token."""
        access_token = self.ensure_valid_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "query": query,
            "variables": variables or {},
        }

        client = self._get_client()
        should_close = self._http_client is None
        try:
            response = client.post(settings.WAVE_GRAPHQL_URL, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise WaveError(f"Network error during Wave GraphQL query: {exc}") from exc
        finally:
            if should_close:
                client.close()

        if response.status_code == 401:
            raise WaveAuthError("Wave GraphQL returned 401 Unauthorized")

        if response.status_code != 200:
            raise WaveError(f"Wave GraphQL query failed with HTTP {response.status_code}: {response.text}")

        try:
            result = response.json()
        except Exception as exc:
            raise WaveError(f"Invalid JSON returned by Wave GraphQL API: {exc}") from exc

        if "errors" in result and result["errors"]:
            raise WaveGraphQLError(result["errors"])

        return result.get("data", {})

    def get_chart_of_accounts(
        self,
        business_id: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, str]]:
        """Fetch active Expense, Asset, and Income accounts from Wave Chart of Accounts."""
        target_business_id = business_id or self.company.wave_business_id
        if not target_business_id:
            raise WaveConfigurationError(f"Company '{self.company.name}' does not have a Wave business ID configured")

        page = 1
        accounts: list[dict[str, str]] = []
        seen_ids: set[str] = set()

        while True:
            variables = {
                "businessId": target_business_id,
                "page": page,
                "pageSize": page_size,
            }
            data = self.query_graphql(CHART_OF_ACCOUNTS_QUERY, variables)
            business_data = data.get("business")
            if not business_data:
                raise WaveError(f"Wave business '{target_business_id}' not found or inaccessible")

            accounts_data = business_data.get("accounts") or {}
            edges = accounts_data.get("edges") or []

            for edge in edges:
                node = edge.get("node") or {}
                node_id = node.get("id")
                node_name = node.get("name")
                if not node_id or not node_name:
                    continue

                if str(node_id) in seen_ids:
                    continue

                if node.get("isArchived") is True:
                    continue

                type_info = node.get("type")
                if type_info:
                    if isinstance(type_info, dict):
                        type_val = str(type_info.get("value") or type_info.get("name") or "").upper()
                    else:
                        type_val = str(type_info).upper()
                    if type_val and type_val not in {"EXPENSE", "ASSET", "INCOME"}:
                        continue

                accounts.append(
                    {
                        "wave_account_id": str(node_id),
                        "name": str(node_name),
                    }
                )
                seen_ids.add(str(node_id))

            page_info = accounts_data.get("pageInfo") or {}
            total_pages = page_info.get("totalPages")
            if total_pages is not None:
                if page >= total_pages:
                    break
            else:
                if not edges or len(edges) < page_size:
                    break

            page += 1

        return accounts


def sync_company_categories(
    company: Company,
    db: Session,
    client: WaveClient | None = None,
) -> list[WaveCategory]:
    """Fetch accounts from Wave and upsert into WaveCategory table for the company."""
    if not company.wave_access_token:
        raise WaveNotConnectedError(f"Company '{company.name}' is not connected to Wave")

    if not company.wave_business_id:
        raise WaveConfigurationError(f"Company '{company.name}' has no Wave business ID configured")

    wave_client = client if client is not None else WaveClient(company, db=db)
    raw_accounts = wave_client.get_chart_of_accounts()

    existing_categories_stmt = select(WaveCategory).where(WaveCategory.company_id == company.id)
    existing_map = {cat.wave_account_id: cat for cat in db.scalars(existing_categories_stmt).all()}

    for item in raw_accounts:
        wave_acc_id = item["wave_account_id"]
        cat_name = item["name"]

        if wave_acc_id in existing_map:
            cat = existing_map[wave_acc_id]
            if cat.name != cat_name:
                cat.name = cat_name
                db.add(cat)
        else:
            new_cat = WaveCategory(
                company_id=company.id,
                wave_account_id=wave_acc_id,
                name=cat_name,
            )
            db.add(new_cat)
            existing_map[wave_acc_id] = new_cat

    db.commit()

    stmt = select(WaveCategory).where(WaveCategory.company_id == company.id).order_by(WaveCategory.name)
    return list(db.scalars(stmt).all())
