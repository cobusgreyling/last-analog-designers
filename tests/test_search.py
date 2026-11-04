"""The bias week is the contract. Grade paths are checked against a hand trace."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from last_analog_designers.search import grade, load_week, run_week, schematic_queue

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "week.json"
RESULT = (
    "outcome-search ships 2/2 blocks in 4 grades for USD 5000; "
    "one-seat ships 1/2 blocks in 4 grades for USD 9000; "
    "two-seat ships 2/2 blocks in 6 grades for USD 18000."
)


class SearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.week = load_week(FIXTURE)
        self.report = run_week(self.week)

    def test_grader_folds_parasitic_in(self) -> None:
        block = self.week.blocks[0]
        by_id = {candidate.id: candidate for candidate in block.candidates}
        tight = grade(by_id["m-tight"], block)
        spaced = grade(by_id["m-spaced"], block)
        self.assertEqual(tight.true_noise, 13)
        self.assertTrue(tight.noise_only)
        self.assertFalse(tight.passed)
        self.assertEqual(spaced.true_noise, 7)
        self.assertTrue(spaced.passed)

    def test_outcome_promotes_the_other_layout(self) -> None:
        outcome = self.report.policy("outcome-search")
        self.assertEqual(
            [event.candidate_id for event in outcome.grades],
            ["m-tight", "m-spaced", "b-tight", "b-spaced"],
        )
        self.assertEqual(outcome.shipped_blocks, ("ldo-bias", "bandgap"))
        self.assertEqual(outcome.bill_usd, 5000)
        ldo = self.week.blocks[0]
        initial = [candidate.id for candidate in schematic_queue(ldo)]
        self.assertEqual(initial[:2], ["m-tight", "s-tight"])

    def test_promotion_does_not_read_the_parasitic(self) -> None:
        ldo = self.week.blocks[0]
        noisy = []
        for candidate in ldo.candidates:
            if candidate.id == "m-spaced":
                noisy.append(type(candidate)(
                    candidate.id,
                    candidate.sizing,
                    candidate.layout,
                    candidate.gain,
                    candidate.power,
                    candidate.noise_schematic,
                    30,
                    candidate.feel,
                ))
            else:
                noisy.append(candidate)
        mutated = type(ldo)(ldo.id, ldo.gain_min, ldo.power_max, ldo.noise_max, tuple(noisy))
        from last_analog_designers.search import play

        events, shipped = play((mutated,), 3, schematic_queue, learn=True)
        self.assertEqual([event.candidate_id for event in events], ["m-tight", "m-spaced", "s-tight"])
        self.assertFalse(events[1].passed)
        self.assertEqual(shipped, ())

    def test_seats_follow_feel(self) -> None:
        one = self.report.policy("one-seat")
        two = self.report.policy("two-seat")
        self.assertEqual(
            [event.candidate_id for event in one.grades],
            ["s-tight", "m-tight", "l-tight", "s-spaced"],
        )
        self.assertEqual(one.shipped_blocks, ("ldo-bias",))
        self.assertEqual(one.bill_usd, 9000)
        self.assertEqual(
            [event.candidate_id for event in two.grades],
            ["s-tight", "m-tight", "l-tight", "s-spaced", "a-tight", "a-spaced"],
        )
        self.assertEqual(two.shipped_blocks, ("ldo-bias", "bandgap"))
        self.assertEqual(two.bill_usd, 18000)
        self.assertLess(self.report.policy("outcome-search").bill_usd, one.bill_usd)
        self.assertGreater(self.report.policy("outcome-search").shipped_count, one.shipped_count)

    def test_result_line(self) -> None:
        self.assertEqual(self.report.result_line, RESULT)

    def test_cli(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "last_analog_designers", str(FIXTURE)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(RESULT, proc.stdout)
        self.assertIn("m-spaced", proc.stdout)

    def test_cli_json(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "last_analog_designers", "--json", str(FIXTURE)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["result"], RESULT)
        by_name = {row["policy"]: row for row in payload["policies"]}
        self.assertEqual(by_name["outcome-search"]["path"], ["m-tight", "m-spaced", "b-tight", "b-spaced"])
        self.assertEqual(by_name["one-seat"]["shipped"], 1)
        self.assertEqual(by_name["two-seat"]["grades"], 6)

    def test_missing_file(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "last_analog_designers", "fixtures/missing.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())
