"""Utility script to fetch and dump Wave's complete GraphQL schema via introspection.

Usage:
    uv run python .agents/skills/wave-api/scripts/fetch_schema.py <WAVE_BEARER_TOKEN> [output_file]

Default output_file:
    .agents/skills/wave-api/references/wave_schema.json
"""

import json
import sys
from pathlib import Path
import httpx

WAVE_GRAPHQL_URL = "https://gql.waveapps.com/graphql/public"

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        type { ...TypeRef }
        isDeprecated
        deprecationReason
      }
      inputFields {
        name
        description
        type { ...TypeRef }
        defaultValue
      }
      interfaces { ...TypeRef }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
      }
      possibleTypes { ...TypeRef }
    }
    directives {
      name
      description
      locations
      args {
        name
        description
        type { ...TypeRef }
        defaultValue
      }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
          }
        }
      }
    }
  }
}
"""


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python fetch_schema.py <WAVE_BEARER_TOKEN> [output_file]")
        sys.exit(1)

    token = sys.argv[1].strip()
    output_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(__file__).resolve().parent.parent / "references" / "wave_schema.json"
    )

    print(f"Fetching Wave GraphQL schema from {WAVE_GRAPHQL_URL}...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": INTROSPECTION_QUERY}

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(WAVE_GRAPHQL_URL, json=payload, headers=headers)

    if resp.status_code != 200:
        print(f"Error: Wave returned HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    if "errors" in data and data["errors"]:
        print(f"GraphQL Errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data.get("data", {}), f, indent=2)

    print(f"Successfully saved Wave GraphQL schema introspection to: {output_path}")


if __name__ == "__main__":
    main()
