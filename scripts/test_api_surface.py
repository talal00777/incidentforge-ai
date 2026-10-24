"""Isolated contract-policy tests independent of an active server."""

import json
import unittest
from pathlib import Path

from check_api_surface import verify

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "contracts/api-surface.json").read_text(encoding="utf-8"))


def sample_schema():
    return {
        "paths": {"/api/v1/system": {"get": {"responses": {"200": {}}}}},
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
    }


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
