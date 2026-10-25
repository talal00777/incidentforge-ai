"""Isolated contract-policy tests independent of an active server."""

import json
import unittest
from pathlib import Path

from check_api_surface import verify

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "contracts/api-surface.json").read_text(encoding="utf-8"))


def sample_schema():
    schema = {
        "paths": {},
        "components": {
            "schemas": {
                "SystemInfo": {
                    "properties": {
                        name: {"type": "string"}
                        for name in POLICY["system_response_properties"]
                    }
                }
            }
        },
    for operation in POLICY["required_operations"]:
        schema["paths"].setdefault(operation["path"], {})[operation["method"]] = {
            "responses": {operation["status"]: {}}
        }
    return schema


class APISurfaceTests(unittest.TestCase):
    def test_valid_surface(self):
        self.assertEqual(verify(sample_schema(), POLICY), [])

    def test_unreviewed_path(self):
        schema = sample_schema()
        schema["paths"]["/api/v1/secrets"] = {"get": {"responses": {"200": {}}}}
        self.assertTrue(any("Unreviewed" in s for s in verify(schema, POLICY)))

    def test_missing_response_property(self):
        schema = sample_schema()
        del schema["components"]["schemas"]["SystemInfo"]["properties"]["capabilities"]
        self.assertTrue(any("capabilities" in s for s in verify(schema, POLICY)))


if __name__ == "__main__":
    unittest.main()
