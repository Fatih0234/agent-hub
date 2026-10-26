#!/usr/bin/env python3
"""Failure modes the public snapshot must not hit again."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

import generate


class ShStdoutOnlyTests(unittest.TestCase):
    """Failed CLI stderr must not become a published version string."""

    def test_nonzero_exit_with_stderr_is_missing(self) -> None:
        err = "env: 'node': No such file or directory"
        with patch("generate.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=["pi", "--version"],
                returncode=127,
                stdout="",
                stderr=err,
            )
            self.assertIsNone(generate.sh(["pi", "--version"]))

    def test_zero_exit_empty_stdout_ignores_stderr(self) -> None:
        with patch("generate.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=["pi", "--version"],
                returncode=0,
                stdout="  \n",
                stderr="a warning on stderr",
            )
            self.assertIsNone(generate.sh(["pi", "--version"]))

    def test_zero_exit_uses_stdout(self) -> None:
        with patch("generate.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=["pi", "--version"],
                returncode=0,
                stdout="1.4.0\n",
                stderr="",
            )
            self.assertEqual(generate.sh(["pi", "--version"]), "1.4.0")


class SkipWriteTests(unittest.TestCase):
    """Timer must not commit timestamp-only churn, but must refresh README."""

    def test_without_time_ignores_generated_at(self) -> None:
        a = {"generated_at": "t1", "x": 1}
        b = {"generated_at": "t2", "x": 1}
        self.assertEqual(generate.without_time(a), generate.without_time(b))

    def test_readme_body_ignores_generated_timestamp(self) -> None:
        a = "Generated: `2026-01-01T00:00:00Z` (UTC).\nhello"
        b = "Generated: `2026-01-02T00:00:00Z` (UTC).\nhello"
        self.assertEqual(generate.readme_body(a), generate.readme_body(b))

    def test_skip_when_only_timestamp_would_change(self) -> None:
        old = {"generated_at": "t1", "x": 1}
        new = {"generated_at": "t2", "x": 1}
        readme_old = "Generated: `t1` (UTC).\nbody"
        readme_new = "Generated: `t2` (UTC).\nbody"
        self.assertTrue(
            generate.should_skip_write(
                new, generate.without_time(old), readme_old, readme_new
            )
        )

    def test_write_when_render_changed_but_inventory_same(self) -> None:
        old = {"generated_at": "t1", "x": 1}
        new = {"generated_at": "t2", "x": 1}
        readme_old = "Generated: `t1` (UTC).\nold render"
        readme_new = "Generated: `t2` (UTC).\nnew render"
        self.assertFalse(
            generate.should_skip_write(
                new, generate.without_time(old), readme_old, readme_new
            )
        )

    def test_write_when_readme_missing(self) -> None:
        data = {"generated_at": "t1", "x": 1}
        self.assertFalse(
            generate.should_skip_write(
                data, generate.without_time(data), None, "Generated: `t1` (UTC).\n"
            )
        )


if __name__ == "__main__":
    unittest.main()
