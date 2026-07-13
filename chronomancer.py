from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from datetime import timedelta
from types import NotImplementedType
from functools import total_ordering, cache
from collections.abc import Iterator, Callable
from typing import Literal, Final, overload
from numbers import Integral

def _integer_like(value: object) -> bool:
    if type(value) is int:
        return True
    
    return isinstance(value, Integral) and not isinstance(value, bool)

def _require_integer(value: object, name: str) -> int:
    # fast path for int type, since it's the most common case
    if type(value) is int:
        return value
    
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    return int(value)

def _require_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean, got {type(value).__name__}")
    return value

def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    return value

# Module-level time conversion support constants
_MS_PER_MS  : Final[int] = 1
_MS_PER_SEC : Final[int] = 1_000 * _MS_PER_MS
_MS_PER_MIN : Final[int] = 60    * _MS_PER_SEC
_MS_PER_HOUR: Final[int] = 60    * _MS_PER_MIN
_MS_PER_DAY : Final[int] = 24    * _MS_PER_HOUR
_MS_PER_WEEK: Final[int] = 7     * _MS_PER_DAY

# timedelta supports
_US_PER_SEC : Final[int] = 1_000_000
_SEC_PER_DAY: Final[int] = 86_400

def _truncate_us_to_ms(us: int) -> int:
    magnitude_ms = abs(us) // 1_000
    return -magnitude_ms if us < 0 else magnitude_ms

@dataclass(frozen=True, slots=True)
class _ScaleMeta:
    name: str
    abbr: str
    mini: str
    ms_factor: int
    rank: int

class ChronoScale(Enum):
    MILLISECOND = _ScaleMeta("millisecond" ,"msec" ,"ms" ,_MS_PER_MS   ,0)
    SECOND      = _ScaleMeta("second"      ,"sec"  ,"s"  ,_MS_PER_SEC  ,1)
    MINUTE      = _ScaleMeta("minute"      ,"min"  ,"m"  ,_MS_PER_MIN  ,2)
    HOUR        = _ScaleMeta("hour"        ,"hr"   ,"h"  ,_MS_PER_HOUR ,3)
    DAY         = _ScaleMeta("day"         ,"day"  ,"d"  ,_MS_PER_DAY  ,4)
    WEEK        = _ScaleMeta("week"        ,"wk"   ,"w"  ,_MS_PER_WEEK ,5)
    
    @property
    def fullname(self) -> str:
        return self.value.name

    @property
    def abbr(self) -> str:
        return self.value.abbr

    @property
    def mini(self) -> str:
        return self.value.mini

    @property
    def ms_factor(self) -> int:
        return self.value.ms_factor

    @property
    def rank(self) -> int:
        return self.value.rank

_RANK_TO_SCALE = tuple(sorted((scale for scale in ChronoScale), key=lambda s: s.rank))

def _resolve_rank(rank_or_scale: int | ChronoScale) -> int:
    if isinstance(rank_or_scale, ChronoScale):
        return rank_or_scale.rank
    
    rank = rank_or_scale
    if not _integer_like(rank):
        raise TypeError(f"Rank must be an integer or ChronoScale, got {type(rank).__name__}")
    if not (0 <= rank < len(_RANK_TO_SCALE)):
        raise ValueError(f"Rank must be between 0 and {len(_RANK_TO_SCALE) - 1}, got {rank}")
    
    return rank

def promote(rank_or_scale: int | ChronoScale) -> ChronoScale | None:
    rank = _resolve_rank(rank_or_scale)
    return _RANK_TO_SCALE[rank + 1] if rank < len(_RANK_TO_SCALE) - 1 else None

def downgrade(rank_or_scale: int | ChronoScale) -> ChronoScale | None:
    rank = _resolve_rank(rank_or_scale)
    return _RANK_TO_SCALE[rank - 1] if rank > 0 else None

def _require_scale(value: object, name: str) -> ChronoScale:
    if not isinstance(value, ChronoScale):
        raise TypeError(f"{name} must be a ChronoScale, got {type(value).__name__}")
    
    return value

@dataclass(frozen=True, slots=True)
class ChronoSpan:
    value: int
    scale: ChronoScale

    def __post_init__(self) -> None:
        value = _require_integer(self.value, "ChronoSpan.value")
        
        if value < 0:
            raise ValueError("ChronoSpan.value must be non-negative")
        
        scale = _require_scale(self.scale, "ChronoSpan.scale")
        
        if type(self.value) is not int:
            object.__setattr__(self, 'value', value)

    @classmethod
    def _from_validated(
        cls,
        value: int,
        scale: ChronoScale
    ) -> ChronoSpan:
        self = object.__new__(cls)
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'scale', scale)
        return self

    @property
    def ms_factor(self) -> int:
        return self.scale.ms_factor
    
    @property
    def in_ms(self) -> int:
        return self.value * self.ms_factor

    def strfmt(self, fmt: str = "{value} {name}{plural}") -> str:
        """
        Follows the same pattern as `str.format`. Use the `{value}` placeholder to access the value of the ChronoSpan.\n
        For example, `span.strfmt("duration={value:0>4d} seconds")` will return a string like "duration=0005 seconds" 
        if `span.value` is 5.
        """
        
        return fmt.format(
            value=self.value,
            name=self.scale.fullname,
            abbr=self.scale.abbr,
            mini=self.scale.mini,
            plural='s' if self.value != 1 else ''
        )

    def verbose_str(self) -> str:
        return f"{self.value} {self.scale.fullname}{'s' if self.value != 1 else ''}"

    def __str__(self) -> str:
        return f"{self.value}{self.scale.mini}"

    def as_scale(self, target: ChronoScale) -> tuple[ChronoSpan, ChronoSpan]:
        target = _require_scale(target, "target")
        value, remaining_ms = divmod(self.in_ms, target.ms_factor)
        return ChronoSpan(value, target), ChronoSpan(remaining_ms, ChronoScale.MILLISECOND)

    def value_in(self, target: ChronoScale) -> float:
        target = _require_scale(target, "target")
        return self.in_ms / target.ms_factor

# Avoid re-creating zero spans for each scale every time a ChronoDelta is created. This is a performance optimization.
_ZERO_SPANS: Final[dict[ChronoScale, ChronoSpan]] = {
    scale: ChronoSpan._from_validated(0, scale) for scale in ChronoScale
}

def _span_from_validated(value: int, scale: ChronoScale) -> ChronoSpan:
    if value == 0:
        return _ZERO_SPANS[scale]
    
    return ChronoSpan._from_validated(value, scale)

@total_ordering
@dataclass(frozen=True, slots=True, init=False)
class ChronoDelta:
    weeks       : ChronoSpan
    days        : ChronoSpan
    hours       : ChronoSpan
    minutes     : ChronoSpan
    seconds     : ChronoSpan
    milliseconds: ChronoSpan
    total_ms    : int = 0

    def __init__(
        self,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        milliseconds: int = 0,
        *,
        neg: bool = False
    ) -> None:
        neg = _require_bool(neg, "neg")
        weeks = _require_integer(weeks, "weeks")
        days = _require_integer(days, "days")
        hours = _require_integer(hours, "hours")
        minutes = _require_integer(minutes, "minutes")
        seconds = _require_integer(seconds, "seconds")
        milliseconds = _require_integer(milliseconds, "milliseconds")
        
        if (weeks < 0 or days < 0 or hours < 0 or minutes < 0 or seconds < 0 or milliseconds < 0):
            raise ValueError("All time components must be non-negative")
        
        total_ms = (
            weeks * _MS_PER_WEEK +
            days * _MS_PER_DAY +
            hours * _MS_PER_HOUR +
            minutes * _MS_PER_MIN +
            seconds * _MS_PER_SEC +
            milliseconds
        )
        
        if neg:
            total_ms = -total_ms
        
        # Use trusted constructors to bypass validation since we already validated the inputs
        object.__setattr__(self, 'weeks', _span_from_validated(weeks, ChronoScale.WEEK))
        object.__setattr__(self, 'days', _span_from_validated(days, ChronoScale.DAY))
        object.__setattr__(self, 'hours', _span_from_validated(hours, ChronoScale.HOUR))
        object.__setattr__(self, 'minutes', _span_from_validated(minutes, ChronoScale.MINUTE))
        object.__setattr__(self, 'seconds', _span_from_validated(seconds, ChronoScale.SECOND))
        object.__setattr__(self, 'milliseconds', _span_from_validated(milliseconds, ChronoScale.MILLISECOND))
        object.__setattr__(self, 'total_ms', total_ms)

    @classmethod
    def from_total_ms(cls, total_ms: int) -> ChronoDelta:
        total_ms = _require_integer(total_ms, "total_ms")
        
        if total_ms == 0:
            return cls.zero()
        
        remaining_ms = abs(total_ms)
        
        weeks  , remaining_ms = divmod(remaining_ms, _MS_PER_WEEK)
        days   , remaining_ms = divmod(remaining_ms, _MS_PER_DAY)
        hours  , remaining_ms = divmod(remaining_ms, _MS_PER_HOUR)
        minutes, remaining_ms = divmod(remaining_ms, _MS_PER_MIN)
        seconds, remaining_ms = divmod(remaining_ms, _MS_PER_SEC)
        milliseconds = remaining_ms
        
        return cls._from_validated(
            weeks=_span_from_validated(weeks, ChronoScale.WEEK),
            days=_span_from_validated(days, ChronoScale.DAY),
            hours=_span_from_validated(hours, ChronoScale.HOUR),
            minutes=_span_from_validated(minutes, ChronoScale.MINUTE),
            seconds=_span_from_validated(seconds, ChronoScale.SECOND),
            milliseconds=_span_from_validated(milliseconds, ChronoScale.MILLISECOND),
            total_ms=total_ms
        )

    @classmethod
    def _from_validated(
        cls,
        weeks: ChronoSpan,
        days: ChronoSpan,
        hours: ChronoSpan,
        minutes: ChronoSpan,
        seconds: ChronoSpan,
        milliseconds: ChronoSpan,
        total_ms: int
    ) -> ChronoDelta:
        self = object.__new__(cls)
        
        object.__setattr__(self, 'weeks', weeks)
        object.__setattr__(self, 'days', days)
        object.__setattr__(self, 'hours', hours)
        object.__setattr__(self, 'minutes', minutes)
        object.__setattr__(self, 'seconds', seconds)
        object.__setattr__(self, 'milliseconds', milliseconds)
        object.__setattr__(self, 'total_ms', total_ms)
        
        return self

    @classmethod
    @cache
    def zero(cls) -> ChronoDelta:
        return cls._from_validated(
            weeks=_ZERO_SPANS[ChronoScale.WEEK],
            days=_ZERO_SPANS[ChronoScale.DAY],
            hours=_ZERO_SPANS[ChronoScale.HOUR],
            minutes=_ZERO_SPANS[ChronoScale.MINUTE],
            seconds=_ZERO_SPANS[ChronoScale.SECOND],
            milliseconds=_ZERO_SPANS[ChronoScale.MILLISECOND],
            total_ms=0
        )

    @classmethod
    def negative(
        cls,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        milliseconds: int = 0
    ) -> ChronoDelta:
        return cls(
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            milliseconds=milliseconds,
            neg=True
        )

    @classmethod
    def from_timedelta(
        cls, 
        td: timedelta,
        *,
        convert: Callable[[int], int] = _truncate_us_to_ms
    ) -> ChronoDelta:
        if not isinstance(td, timedelta):
            raise TypeError(f"td must be a timedelta, got {type(td).__name__}")
        if not callable(convert):
            raise TypeError(f"convert must be a callable, got {type(convert).__name__}")
        
        total_us = (td.days * _SEC_PER_DAY + td.seconds) * _US_PER_SEC + td.microseconds
        return cls.from_total_ms(convert(total_us))

    def to_timedelta(self) -> timedelta:
        return timedelta(milliseconds=self.total_ms)

    def normalized(self) -> ChronoDelta:
        return self.from_total_ms(self.total_ms)

    def expressed_in(
        self,
        *,
        weeks: bool = False,
        days: bool = False,
        hours: bool = False,
        minutes: bool = False,
        seconds: bool = False,
        milliseconds: bool = False,
        truncate: bool = False
    ) -> ChronoDelta:
        all_false = True
        for part in (weeks, days, hours, minutes, seconds, milliseconds):
            if not isinstance(part, bool):
                raise TypeError("All time component flags must be boolean values")
            if part:
                all_false = False
        if all_false:
            raise ValueError("At least one time component must be set to True")
        if not isinstance(truncate, bool):
            raise TypeError("truncate must be a boolean value")
        
        remaining_ms = abs(self.total_ms)
        
        _weeks  , remaining_ms = divmod(remaining_ms, _MS_PER_WEEK) if weeks else (0, remaining_ms)
        _days   , remaining_ms = divmod(remaining_ms, _MS_PER_DAY) if days else (0, remaining_ms)
        _hours  , remaining_ms = divmod(remaining_ms, _MS_PER_HOUR) if hours else (0, remaining_ms)
        _minutes, remaining_ms = divmod(remaining_ms, _MS_PER_MIN) if minutes else (0, remaining_ms)
        _seconds, remaining_ms = divmod(remaining_ms, _MS_PER_SEC) if seconds else (0, remaining_ms)
        _milliseconds = remaining_ms if milliseconds else 0
        
        if not milliseconds and not truncate and remaining_ms > 0:
            raise ValueError("Cannot express in the given components without truncation, as there are remaining milliseconds")
        
        _new_total_ms = (
            _weeks * _MS_PER_WEEK +
            _days * _MS_PER_DAY +
            _hours * _MS_PER_HOUR +
            _minutes * _MS_PER_MIN +
            _seconds * _MS_PER_SEC +
            _milliseconds
        )
        
        if self.is_negative:
            _new_total_ms = -_new_total_ms
        
        return self._from_validated(
            weeks=_span_from_validated(_weeks, ChronoScale.WEEK),
            days=_span_from_validated(_days, ChronoScale.DAY),
            hours=_span_from_validated(_hours, ChronoScale.HOUR),
            minutes=_span_from_validated(_minutes, ChronoScale.MINUTE),
            seconds=_span_from_validated(_seconds, ChronoScale.SECOND),
            milliseconds=_span_from_validated(_milliseconds, ChronoScale.MILLISECOND),
            total_ms=_new_total_ms
        )

    def strfmt(self, fmt: str = "{sign}{w}:{d}:{h:02d}:{m:02d}:{s:02d}.{ms:03d}") -> str:
        return fmt.format(
            sign='-' if self.total_ms < 0 else '',
            w=self.week_count,
            d=self.day_count,
            h=self.hour_count,
            m=self.minute_count,
            s=self.second_count,
            ms=self.millisecond_count
        )

    def verbose_str(self, show_zero_parts: bool = False) -> str:
        show_zero_parts = _require_bool(show_zero_parts, "show_zero_parts")
        parts_shown: list[str] = []
        
        for part in self.iter_parts():
            if part.value != 0 or show_zero_parts:
                parts_shown.append(part.verbose_str())
        
        joined = ", ".join(parts_shown)
        joined = f"-{joined}" if self.total_ms < 0 else joined
        return joined if joined else "0 milliseconds"

    @property
    def week_count(self) -> int:
        return self.weeks.value

    @property
    def day_count(self) -> int:
        return self.days.value

    @property
    def hour_count(self) -> int:
        return self.hours.value

    @property
    def minute_count(self) -> int:
        return self.minutes.value

    @property
    def second_count(self) -> int:
        return self.seconds.value

    @property
    def millisecond_count(self) -> int:
        return self.milliseconds.value

    @property
    def total_seconds(self) -> float:
        return self.total_ms / _MS_PER_SEC

    @property
    def total_minutes(self) -> float:
        return self.total_ms / _MS_PER_MIN

    @property
    def total_hours(self) -> float:
        return self.total_ms / _MS_PER_HOUR

    @property
    def total_days(self) -> float:
        return self.total_ms / _MS_PER_DAY

    @property
    def total_weeks(self) -> float:
        return self.total_ms / _MS_PER_WEEK

    @property
    def is_positive(self) -> bool:
        return self.total_ms > 0

    @property
    def is_negative(self) -> bool:
        return self.total_ms < 0

    @property
    def is_zero(self) -> bool:
        return self.total_ms == 0

    @property
    def sign(self) -> Literal[-1, 0, 1]:
        return 1 if self.is_positive else -1 if self.is_negative else 0

    def iter_parts(self) -> Iterator[ChronoSpan]:
        yield self.weeks
        yield self.days
        yield self.hours
        yield self.minutes
        yield self.seconds
        yield self.milliseconds

    def __str__(self) -> str:
        return f"{'-' if self.total_ms < 0 else ''}{' '.join([
            str(self.weeks),
            str(self.days),
            str(self.hours),
            str(self.minutes),
            str(self.seconds),
            str(self.milliseconds)
        ])}"

    def __hash__(self) -> int:
        return hash(self.total_ms)

    def __add__(self, other: object) -> ChronoDelta | NotImplementedType:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return ChronoDelta.from_total_ms(self.total_ms + other.total_ms)

    def __sub__(self, other: object) -> ChronoDelta | NotImplementedType:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return ChronoDelta.from_total_ms(self.total_ms - other.total_ms)

    def __mul__(self, factor: object) -> ChronoDelta | NotImplementedType:
        if not isinstance(factor, int) or isinstance(factor, bool):
            return NotImplemented
        
        return ChronoDelta.from_total_ms(self.total_ms * factor)

    def __rmul__(self, factor: object) -> ChronoDelta | NotImplementedType:
        return self.__mul__(factor)

    @overload
    def __divmod__(self, divisor: ChronoDelta) -> tuple[int, ChronoDelta]: ...

    @overload
    def __divmod__(self, divisor: int) -> tuple[ChronoDelta, ChronoDelta]: ...

    def __divmod__(self, divisor: object) -> tuple[int | ChronoDelta, ChronoDelta] | NotImplementedType:
        if isinstance(divisor, ChronoDelta):
            if divisor.total_ms == 0:
                raise ZeroDivisionError("Cannot divide by a ChronoDelta with total_ms of 0")
            
            quotient, remainder_ms = divmod(self.total_ms, divisor.total_ms)
            return quotient, ChronoDelta.from_total_ms(remainder_ms)
        elif isinstance(divisor, int) and not isinstance(divisor, bool):
            if divisor == 0:
                raise ZeroDivisionError("Cannot divide by zero")
            
            quotient_ms, remainder_ms = divmod(self.total_ms, divisor)
            return ChronoDelta.from_total_ms(quotient_ms), ChronoDelta.from_total_ms(remainder_ms)
        else:
            return NotImplemented

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return self.total_ms == other.total_ms

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return self.total_ms < other.total_ms

    def __bool__(self) -> bool:
        return self.total_ms != 0

    def __abs__(self) -> ChronoDelta:
        if not self.is_negative:
            return self
        
        return self._from_validated(
            self.weeks,
            self.days,
            self.hours,
            self.minutes,
            self.seconds,
            self.milliseconds,
            total_ms=-self.total_ms
        )

    def __neg__(self) -> ChronoDelta:
        if self.is_zero:
            return self
        
        return self._from_validated(
            self.weeks,
            self.days,
            self.hours,
            self.minutes,
            self.seconds,
            self.milliseconds,
            total_ms=-self.total_ms
        )

class ChronoDeltaFormatter:
    def __init__(self, show_zero_parts: bool = False) -> None:
        self._scale_formats: dict[ChronoScale, str | None] = {
            ChronoScale.WEEK: None,
            ChronoScale.DAY: None,
            ChronoScale.HOUR: None,
            ChronoScale.MINUTE: None,
            ChronoScale.SECOND: None,
            ChronoScale.MILLISECOND: None
        }
        
        self._prefix: str = "{sign}"
        self._separator: str = ""
        self._zero_fallback: str = "0 milliseconds"
        self._show_zero_parts = _require_bool(show_zero_parts, "show_zero_parts")

    def prefix(self, prefix: str) -> ChronoDeltaFormatter:
        prefix = _require_str(prefix, "prefix")
        self._prefix = prefix
        return self

    def separator(self, sep: str) -> ChronoDeltaFormatter:
        sep = _require_str(sep, "separator")
        self._separator = sep
        return self

    def zero_fallback(self, fallback: str) -> ChronoDeltaFormatter:
        fallback = _require_str(fallback, "zero_fallback")
        self._zero_fallback = fallback
        return self

    def week_fmt(self, fmt: str | None) -> ChronoDeltaFormatter:
        fmt = _require_str(fmt, "week_fmt") if fmt is not None else None
        self._scale_formats[ChronoScale.WEEK] = fmt
        return self

    def day_fmt(self, fmt: str | None) -> ChronoDeltaFormatter:
        fmt = _require_str(fmt, "day_fmt") if fmt is not None else None
        self._scale_formats[ChronoScale.DAY] = fmt
        return self

    def hr_fmt(self, fmt: str | None) -> ChronoDeltaFormatter:
        fmt = _require_str(fmt, "hr_fmt") if fmt is not None else None
        self._scale_formats[ChronoScale.HOUR] = fmt
        return self

    def min_fmt(self, fmt: str | None) -> ChronoDeltaFormatter:
        fmt = _require_str(fmt, "min_fmt") if fmt is not None else None
        self._scale_formats[ChronoScale.MINUTE] = fmt
        return self

    def sec_fmt(self, fmt: str | None) -> ChronoDeltaFormatter:
        fmt = _require_str(fmt, "sec_fmt") if fmt is not None else None
        self._scale_formats[ChronoScale.SECOND] = fmt
        return self

    def ms_fmt(self, fmt: str | None) -> ChronoDeltaFormatter:
        fmt = _require_str(fmt, "ms_fmt") if fmt is not None else None
        self._scale_formats[ChronoScale.MILLISECOND] = fmt
        return self

    def format(self, delta: ChronoDelta) -> str:
        result_parts: list[str] = []
        
        for span in delta.iter_parts():
            fmt = self._scale_formats[span.scale]
            if fmt is not None:
                if span.value != 0 or self._show_zero_parts:
                    result_parts.append(span.strfmt(fmt))
        
        joined = self._separator.join(result_parts)
        prefix = self._prefix.format(
            posign='-' if delta.total_ms < 0 else '+',
            sign='-' if delta.total_ms < 0 else '',
        )
        
        # if anything is formatted, return it with the prefix.
        if result_parts:
            return f"{prefix}{joined}"
        
        # if delta == 0 and we don't want to show zero parts, there's nothing to show.
        # But since we already knew that delta == 0, we can return the zero fallback string
        # without causing any issue of "formatted value != delta value"
        if delta.is_zero and not self._show_zero_parts:
            return self._zero_fallback
        
        # do not handle when "nothing to show" is caused by the lack of format strings for the scales.
        return ""