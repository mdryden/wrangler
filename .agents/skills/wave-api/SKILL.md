---
name: wave-api
description: >-
  Reference guide and conventions for Wave Financial's public GraphQL API (gql.waveapps.com).
  Use when integrating, querying, or troubleshooting Wave accounting features such as testing
  bearer tokens, listing businesses, fetching the chart of accounts, recording money transactions,
  and handling Wave GraphQL errors.
---

# Wave Financial Public GraphQL API Guide

Wave provides a public GraphQL API for querying business accounting data and recording transactions.

- **GraphQL Endpoint**: `https://gql.waveapps.com/graphql/public`
- **Authentication**: HTTP Header `Authorization: Bearer <FULL_ACCESS_TOKEN>`
- **Content-Type**: `application/json`

---

## 1. Critical Schema Conventions & Pitfalls

### Top-Level Root Queries vs. `User` Type
> [!CAUTION]
> **Do not query `businesses` on `User`**.
> In Wave's GraphQL schema, `businesses` is a query on the root `Query` type. Attempting to query `user { businesses { ... } }` will fail schema validation with:
> `Cannot query field "businesses" on type "User"`.

- **User Query (`user`)**: Only exposes user account metadata (e.g., `id`, `defaultEmail`), **not** business relationships.
- **Businesses Query (`businesses`)**: Root-level paginated query returning all businesses accessible by the token.
- **Single Business Query (`business(id: ID!)`)**: Root-level query for querying chart of accounts, customers, or vendor data for a specific business.

---

## 2. Standard Queries

### Fetching Accessible Businesses
```graphql
query GetBusinesses {
  businesses(page: 1, pageSize: 50) {
    pageInfo {
      currentPage
      totalPages
      totalCount
    }
    edges {
      node {
        id
        name
        isPersonal
      }
    }
  }
}
```

### Fetching Business Chart of Accounts
```graphql
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
```

#### Wrangler Account Filtering Rules
When importing Wave accounts into Wrangler:
- **Anchor Accounts (Equity/Bank clearing)**:
  - Types: `ASSET`, `LIABILITY`, `EQUITY`
  - Subtypes: `CASH_AND_BANK`, `CREDIT_CARD`, `MONEY_MARKET`, `OWNERS_EQUITY`
- **Expense Categories**:
  - Filter by `type.value == "EXPENSE"` (excluding archived accounts).
  - Identify fallback uncategorized account by checking if subtype/name represents uncategorized expense.

---

## 3. Transaction Mutations

### Creating a Money Transaction
```graphql
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
```

#### Input Payload Construction:
- **`externalId`**: Unique idempotency key (e.g. `wrangler_<allocation_id>`).
- **`businessId`**: Target business ID.
- **`date`**: ISO date format (`YYYY-MM-DD`).
- **`description`**: Transaction description (kept clean without memo annotations).
- **`notes`**: Optional memo / annotation string (e.g. `"Receipt: filename.pdf"`).
- **`anchor`**:
  - For standard positive expenses:
    - `direction: "WITHDRAWAL"`
    - `amount`: Positive decimal
    - `accountId`: Company anchor equity/bank account ID
  - For negative expenses (refunds):
    - `direction: "DEPOSIT"`
    - `amount`: Absolute value of refund
    - `accountId`: Company anchor equity/bank account ID
- **`lineItems`**:
  - For standard positive expenses:
    - `balance: "INCREASE"`
    - `amount`: Positive decimal
    - `accountId`: Expense category account ID
  - For refunds:
    - `balance: "DECREASE"`
    - `amount`: Absolute value of refund
    - `accountId`: Expense category account ID

---

## 4. Error Handling Guidelines

1. **HTTP Status Codes**:
   - `401 Unauthorized`: Token is missing, invalid, or expired.
   - `400 Bad Request`: GraphQL syntax errors or schema validation failures (e.g. invalid field name or nested type).
2. **GraphQL Error Objects**:
   - `data.errors`: Upstream GraphQL errors. Inspect `extensions.code` for `UNAUTHENTICATED` or authorization issues.
   - `didSucceed == false`: Inspect `inputErrors` inside mutation responses for validation errors (e.g. inactive accounts, unbalanced legs).
3. **Debugging Rule**:
   - Upstream API contract issues cannot be found in internal git logs. Always verify against official Wave API documentation or targeted web search when investigating schema discrepancies.

---

## 5. Local Schema References & Fetch Tooling

- **Core GraphQL SDL Reference**: [references/wave_schema_snippets.graphql](references/wave_schema_snippets.graphql) contains the exact definitions for `Query`, `Mutation`, `Business`, `Account`, `MoneyTransactionCreateInput`, etc.
- **Fetch Full Live Introspection Schema**: To dump the entire live Wave GraphQL schema, run:
  ```bash
  uv run python .agents/skills/wave-api/scripts/fetch_schema.py <WAVE_TOKEN>
  ```
  This dumps Wave's full introspection schema JSON to `.agents/skills/wave-api/references/wave_schema.json`.

---

## 6. Official References & Documentation

When researching new fields, arguments, or changes to the Wave API schema, agents should consult:

- **[Wave Developer Documentation](https://developer.waveapps.com/hc/en-us/categories/360001114072)**: Guides for authentication (OAuth 2.0 & tokens), webhooks, and core accounting concepts.
- **[Wave API Reference & Schema](https://developer.waveapps.com/hc/en-us/articles/360019968212-API-Reference)**: Complete GraphQL schema reference covering all root queries, mutations, objects, arguments, and input types.
- When searching via `search_web`, target `domain: "developer.waveapps.com"` for official query and mutation definitions.
