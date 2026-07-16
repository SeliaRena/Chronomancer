# Chronomancer

**Precise duration representation, exact unit decomposition, and highly customizable compiled formatting for Python.**

Chronomancer focuses entirely on **pure, signed durations** from weeks to microseconds.

No dates. No time zones. No ambiguous months or years.

## Why Chronomancer?

A duration's **value** and its **representation** are not the same thing:

```python
from chronomancer import ChronoDelta

hours = ChronoDelta(hours=24)
days = ChronoDelta(days=1)

hours == days
# True

hours.hours
# 24

days.days
# 1
```

Both objects represent exactly the same duration, while preserving the components used to construct them.

Normalize when you want a canonical representation. Re-express the same value in exactly the units your application needs.

## Highlights

* **Value and representation are separate** — preserve `49 hours`, normalize it to `2 days, 1 hour`, or express it using another selected set of units.
* **Exact unit decomposition** — choose any combination of weeks, days, hours, minutes, seconds, milliseconds, and microseconds.
* **Construct from any unit** — turn one integer value in any supported unit into your preferred component layout.
* **`timedelta` interoperability** — convert to and from `datetime.timedelta`, optionally selecting the resulting components.
* **Exact by default** — Chronomancer raises rather than silently discarding precision; truncation must be explicitly enabled.
* **Flexible compiled formatting** — give every component its own template, then reuse the compiled formatter.
* **Solid value semantics** — immutable, hashable, comparable, signed, and equipped with arithmetic and `divmod`.
* **Zero dependencies** — pure Python, standard-library only, with inline type annotations.

## Installation

```bash
pip install py-chronomancer
```

## Control the representation

The constructor preserves the components you provide:

```python
from chronomancer import ChronoDelta

duration = ChronoDelta(hours=49, minutes=1)

duration.strfmt("{h}h {m}m")
# '49h 1m'
```

Normalize it into the canonical largest-to-smallest decomposition:

```python
duration.normalized().strfmt("{d}d {h}h {m}m")
# '2d 1h 1m'
```

Or re-express the same duration using only selected components:

```python
duration.expressed_in(
    hours=True,
    minutes=True,
).strfmt("{h}h {m}m")
# '49h 1m'
```

`expressed_in()` is exact by default. If the enabled components cannot represent the full duration, it raises instead of silently losing the remainder.

Use `truncate=True` only when discarding smaller units is intentional.

## Construct from any unit

`from_unit()` accepts one integer value and a source `ChronoUnit`, then decomposes it directly into the components you enable:

```python
from chronomancer import ChronoDelta, ChronoUnit

duration = ChronoDelta.from_unit(
    90_061,
    ChronoUnit.SECOND,
    hours=True,
    minutes=True,
    seconds=True,
)

duration.strfmt("{h}h {m}m {s}s")
# '25h 1m 1s'
```

If no output components are selected, Chronomancer uses the full canonical decomposition.

This works with every supported unit:

```text
WEEK · DAY · HOUR · MINUTE · SECOND · MILLISECOND · MICROSECOND
```

## Convert to and from `timedelta`

Without component options, `from_timedelta()` returns a normalized `ChronoDelta`:

```python
from datetime import timedelta
from chronomancer import ChronoDelta

duration = ChronoDelta.from_timedelta(
    timedelta(days=2, seconds=3_661)
)

duration.strfmt("{d}d {h}h {m}m {s}s")
# '2d 1h 1m 1s'
```

Select components when you need a different representation:

```python
duration = ChronoDelta.from_timedelta(
    timedelta(days=2, seconds=3_661),
    hours=True,
    minutes=True,
    seconds=True,
)

duration.strfmt("{h}h {m}m {s}s")
# '49h 1m 1s'

duration.to_timedelta()
# datetime.timedelta(days=2, seconds=3661)
```

Conversion is exact within the range supported by `datetime.timedelta`.

## Formatting

Chronomancer provides two formatting layers:

* `strfmt()` for quick, one-off layouts.
* `DeltaFormatter` for reusable, component-aware formatting.

### Quick formatting with `strfmt()`

```python
duration = ChronoDelta.negative(
    hours=2,
    minutes=5,
    seconds=9,
)

duration.strfmt("{sign}{h:02d}:{m:02d}:{s:02d}")
# '-02:05:09'
```

Available fields:

```text
{sign}  {w}  {d}  {h}  {m}  {s}  {ms}  {us}
```

`strfmt()` formats the components exactly as they are currently represented.

### Reusable compiled formatting

Create a formatter once, then reuse it across many durations:

```python
from chronomancer import (
    ChronoDelta,
    DeltaFormatSpec,
    create_delta_formatter,
)

clock = create_delta_formatter(
    DeltaFormatSpec(
        hours="{value:02d}",
        minutes="{value:02d}",
        seconds="{value:02d}",
        separator=":",
        show_zero_components=True,
    )
)

clock.format(ChronoDelta(hours=1, minutes=1, seconds=1))
# '01:01:01'
```

Each component has its own independent template. Components set to `None` do not participate, and zero-valued components can be omitted automatically:

```python
compact = create_delta_formatter(
    DeltaFormatSpec(
        days="{value}{symbol}",
        hours="{value}{symbol}",
        minutes="{value}{symbol}",
        separator=" ",
    )
)

compact.format(ChronoDelta(days=2, minutes=5))
# '2d 5m'
```

Available component placeholders:

```text
{value}  {name}  {abbr}  {symbol}  {plural}
```

They support standard Python format specifications and the `!s`, `!r`, and `!a` conversions:

```python
human = create_delta_formatter(
    DeltaFormatSpec(
        hours="{value} {name}{plural}",
        minutes="{value} {name}{plural}",
        separator=", ",
    )
)

human.format(ChronoDelta(hours=2, minutes=1))
# '2 hours, 1 minute'
```

The formatter also supports:

* negative-only, always-visible, or hidden signs through `sign="-"`, `sign="+-"`, or `sign=None`;
* custom separators;
* automatic zero-component omission;
* fixed-width output with `show_zero_components=True`.

Static unit metadata is resolved when the formatter is created. Compile once, then format repeatedly.

## Value semantics

Equality, hashing, and ordering use the exact duration value:

```python
ChronoDelta(hours=24) == ChronoDelta(days=1)
# True

hash(ChronoDelta(hours=24)) == hash(ChronoDelta(days=1))
# True
```

Arithmetic also operates on the exact value and returns normalized results:

```python
ChronoDelta(hours=20) + ChronoDelta(hours=5)
# ChronoDelta representing 1 day and 1 hour
```

`ChronoDelta` supports:

```text
+  -  *  divmod()  abs()  unary -  comparisons  bool()
```

## API at a glance

* `ChronoDelta(...)` — construct a duration while preserving the supplied components.
* `ChronoDelta.negative(...)` — construct a negative duration from non-negative components.
* `ChronoDelta.zero()` — obtain the cached zero value.
* `ChronoDelta.from_total_us(...)` — construct from total microseconds with canonical decomposition.
* `ChronoDelta.from_unit(...)` — construct from one source unit and selected output components.
* `normalized()` — obtain the canonical representation.
* `expressed_in(...)` — re-express an existing duration using selected components.
* `from_timedelta(...)` / `to_timedelta()` — interoperate with the standard library.
* `strfmt(...)` / `verbose_str(...)` — quick built-in string formatting.
* `DeltaFormatSpec` + `create_delta_formatter(...)` — create reusable compiled formatters.
* `components` / `iter_components()` — inspect values together with their `ChronoUnit`.
* `total_seconds` through `total_weeks` — access floating-point totals in common units.
* `is_positive`, `is_negative`, `is_zero`, and `sign` — inspect the duration's sign.

## License

MIT License: [MIT License](LICENSE.txt)