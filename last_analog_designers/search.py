"""Play a week of analog design against a grader that folds layout parasitics in.

The seat walks a feel order and stops when the grade budget is gone. The
outcome search starts from the schematic only. If a drawing fails on noise
alone, the other layout of that sizing is graded next. That promotion uses
the sizing id, not the parasitic number. The parasitic is added inside grade().

One seat buys grades_per_seat real answers. Two seats buy twice that, in the
same feel order. The outcome bill is outcome_usd times blocks that pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    id: str
    sizing: str
    layout: str
    gain: int
    power: int
    noise_schematic: int
    parasitic: int
    feel: int


@dataclass(frozen=True)
class Block:
    id: str
    gain_min: int
    power_max: int
    noise_max: int
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class Week:
    program: str
    grades_per_seat: int
    outcome_grades: int
    seat_usd: int
    outcome_usd: int
    blocks: tuple[Block, ...]
    source: str


@dataclass(frozen=True)
class Grade:
    passed: bool
    true_noise: int
    noise_only: bool


@dataclass(frozen=True)
class GradeEvent:
    block_id: str
    candidate_id: str
    true_noise: int
    passed: bool


@dataclass(frozen=True)
class PolicyResult:
    name: str
    grades: tuple[GradeEvent, ...]
    shipped_blocks: tuple[str, ...]
    bill_usd: int

    @property
    def grade_count(self) -> int:
        return len(self.grades)

    @property
    def shipped_count(self) -> int:
        return len(self.shipped_blocks)


@dataclass(frozen=True)
class Report:
    week: Week
    policies: tuple[PolicyResult, ...]

    def policy(self, name: str) -> PolicyResult:
        for item in self.policies:
            if item.name == name:
                return item
        raise KeyError(name)

    @property
    def result_line(self) -> str:
        return format_result_line(self)


def load_week(path: Path) -> Week:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc.msg})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected an object")
    where = str(path)
    blocks = tuple(_load_block(item, f"{where} blocks") for item in _need_list(raw, "blocks", where))
    if not blocks:
        raise ValueError(f"{where}: blocks must not be empty")
    _unique([block.id for block in blocks], f"{where}: duplicate block id")
    return Week(
        program=_need_str(raw, "program", where),
        grades_per_seat=_bounded_int(raw, "grades_per_seat", where, 1, 1000),
        outcome_grades=_bounded_int(raw, "outcome_grades", where, 1, 10000),
        seat_usd=_bounded_int(raw, "seat_usd", where, 0, 10_000_000),
        outcome_usd=_bounded_int(raw, "outcome_usd", where, 0, 10_000_000),
        blocks=blocks,
        source=where,
    )


def grade(candidate: Candidate, block: Block) -> Grade:
    true_noise = candidate.noise_schematic + candidate.parasitic
    gain_ok = candidate.gain >= block.gain_min
    power_ok = candidate.power <= block.power_max
    noise_ok = true_noise <= block.noise_max
    return Grade(
        passed=gain_ok and power_ok and noise_ok,
        true_noise=true_noise,
        noise_only=gain_ok and power_ok and not noise_ok,
    )


def feel_queue(block: Block) -> list[Candidate]:
    return sorted(block.candidates, key=lambda candidate: (candidate.feel, candidate.id))


def schematic_queue(block: Block) -> list[Candidate]:
    """Order proposals from the schematic. Parasitics are not read."""
    legal_tight: list[Candidate] = []
    legal_other: list[Candidate] = []
    illegal: list[Candidate] = []
    for candidate in block.candidates:
        legal = candidate.gain >= block.gain_min and candidate.power <= block.power_max
        if not legal:
            illegal.append(candidate)
        elif candidate.layout == "tight":
            legal_tight.append(candidate)
        else:
            legal_other.append(candidate)
    schematic_key = lambda candidate: (candidate.noise_schematic, candidate.id)
    legal_tight.sort(key=schematic_key)
    legal_other.sort(key=schematic_key)
    illegal.sort(key=lambda candidate: candidate.id)
    return legal_tight + legal_other + illegal


def play(blocks: tuple[Block, ...], budget: int, queue_of, learn: bool) -> tuple[tuple[GradeEvent, ...], tuple[str, ...]]:
    remaining = budget
    events: list[GradeEvent] = []
    shipped: list[str] = []
    for block in blocks:
        if remaining <= 0:
            break
        queue = queue_of(block)
        while queue and remaining > 0:
            candidate = queue.pop(0)
            result = grade(candidate, block)
            remaining -= 1
            events.append(GradeEvent(block.id, candidate.id, result.true_noise, result.passed))
            if result.passed:
                shipped.append(block.id)
                break
            if learn and result.noise_only:
                siblings = [item for item in queue if item.sizing == candidate.sizing]
                if siblings:
                    rest = [item for item in queue if item.sizing != candidate.sizing]
                    queue = siblings + rest
    return tuple(events), tuple(shipped)


def run_week(week: Week) -> Report:
    one_grades, one_shipped = play(week.blocks, week.grades_per_seat, feel_queue, learn=False)
    two_grades, two_shipped = play(week.blocks, week.grades_per_seat * 2, feel_queue, learn=False)
    out_grades, out_shipped = play(week.blocks, week.outcome_grades, schematic_queue, learn=True)
    policies = (
        PolicyResult("outcome-search", out_grades, out_shipped, week.outcome_usd * len(out_shipped)),
        PolicyResult("one-seat", one_grades, one_shipped, week.seat_usd),
        PolicyResult("two-seat", two_grades, two_shipped, week.seat_usd * 2),
    )
    return Report(week, policies)


def format_result_line(report: Report) -> str:
    total = len(report.week.blocks)
    parts = [
        (
            f"{policy.name} ships {policy.shipped_count}/{total} blocks "
            f"in {policy.grade_count} grades for USD {policy.bill_usd}"
        )
        for policy in report.policies
    ]
    return "; ".join(parts) + "."


def format_table(report: Report) -> str:
    week = report.week
    lines = [
        (
            f"program {week.program}  blocks {len(week.blocks)}  "
            f"one-seat grades {week.grades_per_seat}  "
            f"outcome grades {week.outcome_grades}"
        ),
        "",
        f"{'policy':<16}  {'shipped':>7}  {'grades':>6}  {'bill_usd':>8}  path",
        f"{'-' * 16}  {'-' * 7}  {'-' * 6}  {'-' * 8}  {'-' * 28}",
    ]
    for policy in report.policies:
        path = _path(policy)
        lines.append(
            f"{policy.name:<16}  {policy.shipped_count:>7}  {policy.grade_count:>6}  "
            f"{policy.bill_usd:>8}  {path}"
        )
    lines.append("")
    lines.append(report.result_line)
    return "\n".join(lines)


def format_details(report: Report) -> str:
    lines = ["grades  true_noise includes the layout parasitic"]
    for policy in report.policies:
        for event in policy.grades:
            flag = "pass" if event.passed else "fail"
            lines.append(
                f"  {policy.name:<16}  {event.block_id:<10}  {event.candidate_id:<10}  "
                f"noise {event.true_noise:>3}  {flag}"
            )
    return "\n".join(lines)


def to_json(report: Report) -> str:
    payload = {
        "program": report.week.program,
        "policies": [
            {
                "policy": policy.name,
                "shipped": policy.shipped_count,
                "grades": policy.grade_count,
                "bill_usd": policy.bill_usd,
                "shipped_blocks": list(policy.shipped_blocks),
                "path": [event.candidate_id for event in policy.grades],
            }
            for policy in report.policies
        ],
        "result": report.result_line,
    }
    return json.dumps(payload, indent=2) + "\n"


def _path(policy: PolicyResult) -> str:
    if not policy.shipped_blocks:
        return "-"
    shipped = set(policy.shipped_blocks)
    winners = [event.candidate_id for event in policy.grades if event.passed and event.block_id in shipped]
    return ", ".join(f"{block}:{winner}" for block, winner in zip(policy.shipped_blocks, winners))


def _load_block(raw: object, where: str) -> Block:
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object")
    block_id = _need_str(raw, "id", where)
    candidates = tuple(
        _load_candidate(item, f"{where} {block_id}") for item in _need_list(raw, "candidates", where)
    )
    if len(candidates) < 2:
        raise ValueError(f"{where} {block_id}: need at least two candidates")
    _unique([candidate.id for candidate in candidates], f"{where} {block_id}: duplicate candidate id")
    feels = [candidate.feel for candidate in candidates]
    if len(feels) != len(set(feels)):
        raise ValueError(f"{where} {block_id}: feel ranks must be unique")
    _check_sizings(candidates, f"{where} {block_id}")
    return Block(
        id=block_id,
        gain_min=_bounded_int(raw, "gain_min", f"{where} {block_id}", 0, 10_000),
        power_max=_bounded_int(raw, "power_max", f"{where} {block_id}", 1, 10_000),
        noise_max=_bounded_int(raw, "noise_max", f"{where} {block_id}", 0, 10_000),
        candidates=candidates,
    )


def _check_sizings(candidates: tuple[Candidate, ...], where: str) -> None:
    grouped: dict[str, Candidate] = {}
    for candidate in candidates:
        prior = grouped.get(candidate.sizing)
        if prior is None:
            grouped[candidate.sizing] = candidate
            continue
        same = (
            prior.gain == candidate.gain
            and prior.power == candidate.power
            and prior.noise_schematic == candidate.noise_schematic
        )
        if not same:
            raise ValueError(f"{where}: sizing {candidate.sizing} changes the schematic across layouts")


def _load_candidate(raw: object, where: str) -> Candidate:
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object")
    candidate_id = _need_str(raw, "id", where)
    spot = f"{where} {candidate_id}"
    return Candidate(
        id=candidate_id,
        sizing=_need_str(raw, "sizing", spot),
        layout=_need_str(raw, "layout", spot),
        gain=_bounded_int(raw, "gain", spot, 0, 10_000),
        power=_bounded_int(raw, "power", spot, 0, 10_000),
        noise_schematic=_bounded_int(raw, "noise_schematic", spot, 0, 10_000),
        parasitic=_bounded_int(raw, "parasitic", spot, 0, 10_000),
        feel=_bounded_int(raw, "feel", spot, 1, 10_000),
    )


def _need_list(raw: dict, key: str, where: str) -> list:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{where}: {key} must be a list")
    return value


def _need_str(raw: dict, key: str, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {key} must be a non-empty string")
    return value


def _bounded_int(raw: dict, key: str, where: str, low: int, high: int) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{where}: {key} must be an integer")
    if value < low or value > high:
        raise ValueError(f"{where}: {key} must be from {low} to {high}")
    return value


def _unique(values: list[str], message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)
