"""Enforce the reviewed M0 API surface against the generated OpenAPI document."""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/generated/openapi.yaml"
POLICY = ROOT / "contracts/api-surface.json"


def verify(schema: dict, policy: dict) -> list[str]:
    violations = []
    paths = schema.get("paths", {})
    unknown = set(paths) - set(policy["allowed_paths"])
    if unknown:
        violations.append(f"Unreviewed endpoint paths: {sorted(unknown)}")

    for operation in policy["required_operations"]:
        endpoint = paths.get(operation["path"], {}).get(operation["method"])
        if not endpoint:
            violations.append(f"Missing {operation['method'].upper()} {operation['path']}")
            continue
        if operation["status"] not in endpoint.get("responses", {}):
            violations.append(f"Expected HTTP {operation['status']} for {operation['path']}")

    components = schema.get("components", {}).get("schemas", {})
    system = components.get("SystemInfo", {})
    missing = set(policy["system_response_properties"]) - set(system.get("properties", {}))
    if missing:
        violations.append(f"Missing SystemInfo properties: {sorted(missing)}")
    return violations


def main() -> int:
    if not SCHEMA.is_file():
        print(f"OpenAPI schema not found: {SCHEMA}", file=sys.stderr)
        return 1
    with SCHEMA.open(encoding="utf-8") as stream:
        schema = yaml.safe_load(stream)
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    violations = verify(schema, policy)
    if violations:
        for violation in violations:
            print(violation, file=sys.stderr)
        return 1
    print("Reviewed API surface matches the generated schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
