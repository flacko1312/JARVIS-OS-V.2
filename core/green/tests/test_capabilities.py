"""Tests for Capabilities — Phase 5 of GREEN Foundation."""
from __future__ import annotations

import unittest

from core.green.capabilities import (
    Capability,
    CapabilityError,
    CapabilitySet,
    VALID_CAPABILITIES,
    validate_capabilities,
    validate_capability,
)


class TestValidateCapability(unittest.TestCase):
    def test_valid(self):
        c = validate_capability("filesystem.read")
        assert c == Capability.FILESYSTEM_READ

    def test_invalid_rejected(self):
        with self.assertRaises(CapabilityError):
            validate_capability("flying.cars")

    def test_all_enum_values_in_valid_set(self):
        for c in Capability:
            assert c.value in VALID_CAPABILITIES


class TestValidateCapabilities(unittest.TestCase):
    def test_valid_list(self):
        result = validate_capabilities(["filesystem.read", "filesystem.write"])
        assert len(result) == 2

    def test_rejects_on_first_invalid(self):
        with self.assertRaises(CapabilityError):
            validate_capabilities(["filesystem.read", "not.real"])


class TestCapabilitySet(unittest.TestCase):
    def test_add_and_has(self):
        cs = CapabilitySet(["filesystem.read"])
        assert cs.has("filesystem.read")
        assert not cs.has("filesystem.write")

    def test_add_invalid_rejected(self):
        with self.assertRaises(CapabilityError):
            CapabilitySet(["not.valid"])

    def test_remove(self):
        cs = CapabilitySet(["filesystem.read", "filesystem.write"])
        cs.remove("filesystem.read")
        assert not cs.has("filesystem.read")
        assert cs.has("filesystem.write")

    def test_has_all(self):
        cs = CapabilitySet(["filesystem.read", "filesystem.write", "browser.read"])
        assert cs.has_all(["filesystem.read", "browser.read"])
        assert not cs.has_all(["filesystem.read", "home.control"])

    def test_has_any(self):
        cs = CapabilitySet(["filesystem.read"])
        assert cs.has_any(["filesystem.read", "home.control"])
        assert not cs.has_any(["home.control"])

    def test_satisfies(self):
        provided = CapabilitySet(["filesystem.read", "filesystem.write", "browser.read"])
        required = CapabilitySet(["filesystem.read", "browser.read"])
        assert provided.satisfies(required)

    def test_not_satisfies(self):
        provided = CapabilitySet(["filesystem.read"])
        required = CapabilitySet(["filesystem.read", "home.control"])
        assert not provided.satisfies(required)

    def test_to_list_sorted(self):
        cs = CapabilitySet(["browser.read", "filesystem.read"])
        result = cs.to_list()
        assert result == ["browser.read", "filesystem.read"]

    def test_len(self):
        cs = CapabilitySet(["filesystem.read", "filesystem.write"])
        assert len(cs) == 2

    def test_contains(self):
        cs = CapabilitySet(["filesystem.read"])
        assert "filesystem.read" in cs
        assert "home.control" not in cs

    def test_duplicate_handling(self):
        cs = CapabilitySet(["filesystem.read", "filesystem.read"])
        assert len(cs) == 1

    def test_empty(self):
        cs = CapabilitySet()
        assert len(cs) == 0
        assert cs.to_list() == []

    def test_unknown_in_has_returns_false(self):
        cs = CapabilitySet(["filesystem.read"])
        assert not cs.has("nonexistent.thing")


if __name__ == "__main__":
    unittest.main()
