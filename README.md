![last-analog-designers](assets/header.png)

# last-analog-designers

A senior analog designer can afford a few real grades a week. The drawing is part of the circuit, so a wire that looks fine on the schematic can fail once its parasitic is in the grade.

This program runs one week, two blocks, against that grader. It is offline and deterministic. It is not SPICE. Gain, power, schematic noise, and the layout parasitic are the fixture. The true noise is their sum, computed when the candidate is graded.

**one-seat** walks a feel order: compact drawings first. Four grades ship the first block and never start the second. The bill is the seat, USD 9000, whether or not the second block exists.

**two-seat** is the same feel order with eight grades. It ships both blocks and uses six of those grades. The bill is two seats, USD 18000.

**outcome-search** does not read the parasitic while it proposes. It orders legal tight layouts by schematic noise. If a grade fails on noise alone, the other layout of that same sizing is graded next. Four grades ship both blocks. The bill is USD 2500 for each block that passes, USD 5000 here, and nothing for a miss.

## Run

From the repo root. Python 3.11 or newer. No install and no API key.

```bash
python3 -m last_analog_designers fixtures/week.json
python3 -m last_analog_designers --verbose fixtures/week.json
python3 -m last_analog_designers --json fixtures/week.json
python3 -m unittest discover -s tests -v
```

## Result

```
program bias-week  blocks 2  one-seat grades 4  outcome grades 4

policy            shipped  grades  bill_usd  path
----------------  -------  ------  --------  ----------------------------
outcome-search          2       4      5000  ldo-bias:m-spaced, bandgap:b-spaced
one-seat                1       4      9000  ldo-bias:s-spaced
two-seat                2       6     18000  ldo-bias:s-spaced, bandgap:a-spaced

outcome-search ships 2/2 blocks in 4 grades for USD 5000; one-seat ships 1/2 blocks in 4 grades for USD 9000; two-seat ships 2/2 blocks in 6 grades for USD 18000.
```

On ldo-bias the search grades `m-tight` (true noise 13, over a limit of 12) and immediately grades `m-spaced` (true noise 7), which passes. The seat spends its third grade on `l-tight`, a sizing the schematic already misses, and only passes on the fourth grade. The week is then over, so bandgap is not started. Two seats reach bandgap and pass it on grade 6.

| Policy | What it pays for | Shipped | Grades | Bill |
|---|---|---|---|---|
| outcome-search | a block that passes | 2/2 | 4 | USD 5000 |
| one-seat | the seat | 1/2 | 4 | USD 9000 |
| two-seat | two seats | 2/2 | 6 | USD 18000 |

## Fixture shape

Layouts of one sizing must share gain, power, and schematic noise. Only `parasitic` changes with the drawing. `feel` is the seat's order. The search never sorts on it.

```json
{"id": "m-spaced", "sizing": "M", "layout": "spaced", "gain": 44, "power": 70, "noise_schematic": 4, "parasitic": 3, "feel": 5}
```

A candidate passes when gain and power meet the spec and `noise_schematic + parasitic` is within `noise_max`.

## License

MIT
