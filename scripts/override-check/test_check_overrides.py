import unittest

from check_overrides import classify, semver_key, versions_in_lock


class SemverTest(unittest.TestCase):
    def test_ordering(self):
        vs = ["1.30.0", "1.9.0", "1.21.2", "2.0.0-rc.1", "2.0.0"]
        self.assertEqual(
            sorted(vs, key=semver_key),
            ["1.9.0", "1.21.2", "1.30.0", "2.0.0-rc.1", "2.0.0"],
        )

    def test_rejects_non_semver(self):
        with self.assertRaises(ValueError):
            semver_key("^1.2.3")


class LockTest(unittest.TestCase):
    LOCK = {"packages": {
        "": {"name": "root"},
        "node_modules/undici": {"version": "7.29.0"},
        "node_modules/a/node_modules/undici": {"version": "5.29.0"},
        "node_modules/@scope/undici-thing": {"version": "1.0.0"},
        "node_modules/@modelcontextprotocol/sdk": {"version": "1.30.0"},
        "node_modules/linked": {"link": True, "version": "9.9.9"},
    }}

    def test_collects_every_copy(self):
        self.assertEqual(versions_in_lock(self.LOCK, "undici"), ["5.29.0", "7.29.0"])

    def test_scoped_and_no_prefix_match(self):
        self.assertEqual(versions_in_lock(self.LOCK, "@modelcontextprotocol/sdk"), ["1.30.0"])
        self.assertEqual(versions_in_lock(self.LOCK, "thing"), [])


class ClassifyTest(unittest.TestCase):
    def test_mixed_copies_flag_downgrade(self):
        r = classify("undici", "6.28.0", ["5.29.0", "7.29.0"])
        self.assertEqual((r["raises"], r["lowers"], r["downgrade"]), (["5.29.0"], ["7.29.0"], True))

    def test_pure_upgrade_is_not_downgrade(self):
        r = classify("sharp", "0.35.3", ["0.33.5"])
        self.assertFalse(r["downgrade"])
        self.assertEqual(r["raises"], ["0.33.5"])

    def test_pin_equals_highest(self):
        self.assertFalse(classify("x", "1.26.0", ["1.21.2", "1.26.0"])["downgrade"])

    def test_absent(self):
        r = classify("x", "1.0.0", [])
        self.assertTrue(r["absent"])
        self.assertFalse(r["downgrade"])


if __name__ == "__main__":
    unittest.main()
