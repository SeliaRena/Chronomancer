# Chronomancer

**Chronomancer is a Python library focused on representing and formatting pure, signed durations ranging from weeks to microseconds.**

It does not handle calendar-aware or time-zone-aware concepts such as months, dates, daylight-saving transitions, or relative date calculations. A duration in Chronomancer is simply an exact amount of elapsed time.

If you are tired of repeatedly using `divmod` to extract time units, or writing small utility functions just to produce the duration format you need, Chronomancer is designed to handle that work for you.

It provides flexible duration formatting for outputs such as:

* `02:03:04`
* `2 weeks 3 days 03:04:05`
* `3 hour watermelons, 4seconds:::0001ms??0002microseconds`

Even unusual formats can be expressed without filling your application code with custom formatting logic.

Chronomancer also provides conversion between its `ChronoDelta` type and Python's standard `datetime.timedelta`.

## Highlights

- **Value and representation are separate** — preserve `49 hours`, normalize it to `2 days, 1 hour`, or express it using another selected set of units.
- **Exact unit decomposition** — choose any combination of weeks, days, hours, minutes, seconds, milliseconds, and microseconds.
- **Construct from any unit** — turn one integer value in any supported unit into your preferred component layout.
- **`timedelta` interoperability** — convert to and from `datetime.timedelta`, optionally selecting the resulting components.
- **Exact by default** — Chronomancer raises rather than silently discarding precision; truncation must be explicitly enabled.
- **Flexible compiled formatting** — give every component its own format, zero policy, plural form, and separator behavior.
- **Convenient built-in output** — use `strfmt()` for direct layouts or `verbose_str()` for readable, filtered unit output.
- **Solid value semantics** — immutable, hashable, comparable, signed, and equipped with arithmetic and `divmod`.
- **Zero dependencies** — pure Python, standard-library only, with inline type annotations.

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

Every supported source unit works the same way:

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

Chronomancer provides three formatting layers:

- `strfmt()` for quick, explicit layouts.
- `verbose_str()` for readable unit output with component filtering.
- `DeltaFormatter` for reusable, component-aware compiled formatting.

### Quick layouts with `strfmt()`

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

### Readable output with `verbose_str()`

By default, `verbose_str()` considers every unit and omits zero-valued components:

```python
duration = ChronoDelta(hours=2, seconds=5)

duration.verbose_str()
# '2 hours, 5 seconds'
```

Select only the units relevant to your output:

```python
duration = ChronoDelta(hours=2)

duration.verbose_str(
    hours=True,
    seconds=True,
)
# '2 hours'
```

Keep selected zero-valued units when a stable layout matters:

```python
duration.verbose_str(
    hours=True,
    seconds=True,
    show_zero_components=True,
)
# '2 hours, 0 seconds'
```

The zero-duration fallback is configurable:

```python
ChronoDelta.zero().verbose_str(zero_fallback="none")
# 'none'
```

### Reusable compiled formatting

Create a `DeltaFormatter` once, then reuse it across many durations:

```python
from chronomancer import (
    ChronoDelta,
    DeltaFormatter,
    DeltaFormatSpec,
    Part,
)

clock = DeltaFormatter(
    DeltaFormatSpec(
        hours=Part("{val:02d}", show_zero=True),
        minutes=Part("{val:02d}", show_zero=True),
        seconds=Part("{val:02d}", show_zero=True),
        common_separator=":",
    )
)

clock.format(ChronoDelta(hours=1, minutes=1, seconds=1))
# '01:01:01'
```

Each enabled component receives its own `Part`. Components set to `None` do not participate, while zero-valued parts are omitted unless `show_zero=True`:

```python
compact = DeltaFormatter(
    DeltaFormatSpec(
        days=Part("{val}d"),
        hours=Part("{val}h"),
        minutes=Part("{val}m"),
        common_separator=" ",
    )
)

compact.format(ChronoDelta(days=2, minutes=5))
# '2d 5m'
```

`Part` is the concise alias of `FormatPart`.

#### Component placeholders

A component format supports three dynamic placeholders:

```text
{val}      the component value
{(text)}   text emitted unless the value is exactly 1
{|text}    text emitted only when another component was already rendered
```

`{val}` supports standard Python format specifications and the `!s`, `!r`, and `!a` conversions.

Plural suffixes and inline separators make readable sparse output possible without global metadata fields:

```python
human = DeltaFormatter(
    DeltaFormatSpec(
        hours=Part("{val} hour{(s)}"),
        minutes=Part("{|, }{val} minute{(s)}"),
        seconds=Part("{|, }{val} second{(s)}"),
    )
)

human.format(ChronoDelta(hours=2, minutes=1))
# '2 hours, 1 minute'

human.format(ChronoDelta(minutes=2, seconds=1))
# '2 minutes, 1 second'
```

Inline separators and `common_separator` are mutually exclusive. Use:

- `common_separator` when every rendered component shares the same separator;
- `{|text}` when separator placement belongs inside each component format.

A formatter can also configure:

- `sign="-"` for negative signs only;
- `sign="+-"` for explicit positive and negative signs;
- `sign=None` to hide signs;
- `zero_fallback` when a zero duration renders no parts.

Component formats are parsed and compiled when `DeltaFormatter` is constructed. Compile once, then format repeatedly.

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

- `ChronoDelta(...)` — construct a duration while preserving the supplied components.
- `ChronoDelta.negative(...)` — construct a negative duration from non-negative components.
- `ChronoDelta.zero()` — obtain the cached zero value.
- `ChronoDelta.from_total_us(...)` — construct from total microseconds with canonical decomposition.
- `ChronoDelta.from_unit(...)` — construct from one source unit and selected output components.
- `normalized()` — obtain the canonical representation.
- `expressed_in(...)` — re-express an existing duration using selected components.
- `from_timedelta(...)` / `to_timedelta()` — interoperate with the standard library.
- `strfmt(...)` — format the current component representation directly.
- `verbose_str(...)` — produce readable output with unit filtering, zero control, and a custom fallback.
- `Part(...)` / `FormatPart(...)` — define one component's compiled format and zero policy.
- `DeltaFormatSpec(...)` — define component parts, separator behavior, sign policy, and zero fallback.
- `DeltaFormatter(...)` — compile a specification into a reusable formatter.
- `components` / `iter_components()` — inspect values together with their `ChronoUnit`.
- `total_seconds` through `total_weeks` — access floating-point totals in common units.
- `is_positive`, `is_negative`, `is_zero`, and `sign` — inspect the duration's sign.

## License

[MIT License](LICENSE.txt)