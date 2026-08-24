"""Export the FastAPI app's OpenAPI schema as deterministic JSON.

Importing `src.main` has no side effects — external clients (Mongo, Google APIs, the LLM
provider) are only constructed inside FastAPI's lifespan, which this script never triggers.

Usage:
    uv run python scripts/export_openapi.py <output-path>
"""

import json
import sys

from src.main import app


def main(output_path: str) -> None:
    schema = app.openapi()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
