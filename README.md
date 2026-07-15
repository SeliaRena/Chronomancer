<div align="center">

# Chronomancer

### Exact duration decomposition and formatting for Python.

`49 hours`
`2 days, 1 hour`
`02h : 05m : 09s`

**Python 3.12+ · Zero dependencies · Microsecond precision**

</div>

---

Chronomancer gives you control over how a duration is represented.

```python
from chronomancer import ChronoDelta

duration = ChronoDelta(hours=49)

duration.verbose_str()
# '49 hours'

duration.normalized().verbose_str()
# '2 days, 1 hour'

duration.expressed_in(hours=True).verbose_str()
# '49 hours'
```

## Why?

Most duration libraries either normalize for you or reduce everything to a human-friendly summary.

Chronomancer keeps the duration exact while letting you choose the components.

```python
duration = ChronoDelta(days=2, hours=1)

duration.expressed_in(hours=True)
# 49 hours

duration.expressed_in(days=True, hours=True)
# 2 days, 1 hour
```

Lossy conversions are rejected unless truncation is explicit:

```python
ChronoDelta(seconds=3_599).expressed_in(minutes=True)
# ValueError

ChronoDelta(seconds=3_599).expressed_in(
    minutes=True,
    truncate=True,
)
# 59 minutes
```

## Format once. Reuse everywhere.

```python
from chronomancer import (
    ChronoDelta,
    DeltaFormatSpec,
    create_delta_formatter,
)

clock = create_delta_formatter(
    DeltaFormatSpec(
        hours="{value:02d}{symbol}",
        minutes="{value:02d}{symbol}",
        seconds="{value:02d}{symbol}",
        separator=" : ",
        show_zero_components=True,
    )
)

clock.format(
    ChronoDelta(hours=2, minutes=5, seconds=9)
)
# '02h : 05m : 09s'
```

Available placeholders:

```text
{value}   {name}   {abbr}   {symbol}   {plural}
```

Python format specs and `!s`, `!r`, `!a` conversions are supported.

## More than formatting

```python
from datetime import timedelta
from chronomancer import ChronoDelta, ChronoUnit

ChronoDelta.from_total_us(90_000_000)
ChronoDelta.from_unit(90, ChronoUnit.MINUTE)

ChronoDelta.from_timedelta(timedelta(days=2))
ChronoDelta(hours=48).to_timedelta()

ChronoDelta(hours=1) + ChronoDelta(minutes=30)
ChronoDelta.negative(hours=2)
```

Chronomancer supports:

* week → microsecond precision
* exact integer arithmetic
* negative durations
* normalization and selected-unit expression
* arithmetic, comparison, hashing, and `divmod()`
* `timedelta` interoperability
* compiled reusable formatters

## Fast by design

Chronomancer uses:

* flat immutable storage
* microseconds as the canonical unit
* cached zero values
* precomputed decomposition tables
* trusted internal constructors
* constant-folded formatter plans

Common operations complete in the low single-digit microsecond range on CPython.

## Scope

Chronomancer handles fixed durations.

It intentionally does not model months, years, calendars, dates, or time zones.

## Status

Early preview. The core API is working, but may still change before `1.0`.

For now, use the source directly from this repository.

## License

See [`LICENSE`](LICENSE.txt).