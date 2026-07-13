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

# New standards, us as a canonical unit
_US_PER_US  : Final[int] = 1
_US_PER_MS  : Final[int] = 1_000
_US_PER_SEC : Final[int] = 1_000_000
_US_PER_MIN : Final[int] = 60 * _US_PER_SEC
_US_PER_HOUR: Final[int] = 60 * _US_PER_MIN
_US_PER_DAY : Final[int] = 24 * _US_PER_HOUR
_US_PER_WEEK: Final[int] = 7 * _US_PER_DAY

@dataclass(frozen=True, slots=True)
class _UnitMeta:
    name     : str
    abbr     : str
    symbol   : str
    us_factor: int
    rank     : int

class ChronoUnit(Enum):
    MICROSECOND = _UnitMeta("microsecond" ,"μsec" ,"μs" ,_US_PER_US   ,0)
    MILLISECOND = _UnitMeta("millisecond" ,"msec" ,"ms" ,_US_PER_MS   ,1)
    SECOND      = _UnitMeta("second"      ,"sec"  ,"s"  ,_US_PER_SEC  ,2)
    MINUTE      = _UnitMeta("minute"      ,"min"  ,"m"  ,_US_PER_MIN  ,3)
    HOUR        = _UnitMeta("hour"        ,"hr"   ,"h"  ,_US_PER_HOUR ,4)
    DAY         = _UnitMeta("day"         ,"day"  ,"d"  ,_US_PER_DAY  ,5)
    WEEK        = _UnitMeta("week"        ,"wk"   ,"w"  ,_US_PER_WEEK ,6)

    @property
    def meta(self) -> _UnitMeta:
        return self.value

    @property
    def fullname(self) -> str:
        return self.value.name

    @property
    def abbr(self) -> str:
        return self.value.abbr

    @property
    def symbol(self) -> str:
        return self.value.symbol

    @property
    def us_factor(self) -> int:
        return self.value.us_factor

    @property
    def rank(self) -> int:
        return self.value.rank

_UNITS_ASC: Final[tuple[ChronoUnit, ...]] = tuple(
    sorted(ChronoUnit, key=lambda u: u.rank)
)
_UNITS_DESC: Final[tuple[ChronoUnit, ...]] = tuple(reversed(_UNITS_ASC))

# Canonical decomposition divisor table.
#
# Each row represents an integer value expressed in one source unit.
# Columns below the source unit are unused and set to 0.
# Columns at or above the source unit contain cumulative divisors
# used to decompose the value into canonical components.
#
# Unit order:
# microsecond, millisecond, second, minute, hour, day, week
type IntMatrix = tuple[tuple[int, ...], ...]
_DECOMPOSITION_DIVISORS: Final[IntMatrix] = tuple(
    tuple(
        0
        if target.rank < source.rank
        else target.us_factor // source.us_factor
        for target in _UNITS_ASC
    )
    for source in _UNITS_ASC
)

# timedelta supports
_SEC_PER_DAY: Final[int] = 86_400

@total_ordering
@dataclass(frozen=True, slots=True, init=False)
class ChronoDelta:
    weeks       : int = 0
    days        : int = 0
    hours       : int = 0
    minutes     : int = 0
    seconds     : int = 0
    milliseconds: int = 0
    microseconds: int = 0
    total_us    : int = 0

    def __init__(
        self,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        milliseconds: int = 0,
        microseconds: int = 0,
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
        microseconds = _require_integer(microseconds, "microseconds")
        
        if (weeks < 0 or days < 0 or hours < 0 or minutes < 0 or seconds < 0 or milliseconds < 0 or microseconds < 0):
            raise ValueError("All time components must be non-negative")
        
        total_us = (
            weeks * _US_PER_WEEK +
            days * _US_PER_DAY +
            hours * _US_PER_HOUR +
            minutes * _US_PER_MIN +
            seconds * _US_PER_SEC +
            milliseconds * _US_PER_MS +
            microseconds
        )
        
        if neg:
            total_us = -total_us
        
        # Use trusted constructors to bypass validation since we already validated the inputs
        object.__setattr__(self, 'weeks', weeks)
        object.__setattr__(self, 'days', days)
        object.__setattr__(self, 'hours', hours)
        object.__setattr__(self, 'minutes', minutes)
        object.__setattr__(self, 'seconds', seconds)
        object.__setattr__(self, 'milliseconds', milliseconds)
        object.__setattr__(self, 'microseconds', microseconds)
        object.__setattr__(self, 'total_us', total_us)

    @classmethod
    def from_total_us(cls, total_us: int) -> ChronoDelta:
        total_us = _require_integer(total_us, "total_us")
        
        if total_us == 0:
            return cls.zero()
        
        remaining_us = abs(total_us)
        
        weeks,         remaining_us = divmod(remaining_us, _US_PER_WEEK)
        days,          remaining_us = divmod(remaining_us, _US_PER_DAY)
        hours,         remaining_us = divmod(remaining_us, _US_PER_HOUR)
        minutes,       remaining_us = divmod(remaining_us, _US_PER_MIN)
        seconds,       remaining_us = divmod(remaining_us, _US_PER_SEC)
        milliseconds,  remaining_us = divmod(remaining_us, _US_PER_MS)
        microseconds = remaining_us
        
        return cls._from_validated(
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            milliseconds=milliseconds,
            microseconds=microseconds,
            total_us=total_us
        )

    @classmethod
    def _from_validated(
        cls,
        weeks: int,
        days: int,
        hours: int,
        minutes: int,
        seconds: int,
        milliseconds: int,
        microseconds: int,
        total_us: int
    ) -> ChronoDelta:
        self = object.__new__(cls)
        
        object.__setattr__(self, 'weeks', weeks)
        object.__setattr__(self, 'days', days)
        object.__setattr__(self, 'hours', hours)
        object.__setattr__(self, 'minutes', minutes)
        object.__setattr__(self, 'seconds', seconds)
        object.__setattr__(self, 'milliseconds', milliseconds)
        object.__setattr__(self, 'microseconds', microseconds)
        object.__setattr__(self, 'total_us', total_us)
        
        return self

    @classmethod
    @cache
    def zero(cls) -> ChronoDelta:
        return cls._from_validated(0, 0, 0, 0, 0, 0, 0, 0)

    @classmethod
    def negative(
        cls,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        milliseconds: int = 0,
        microseconds: int = 0
    ) -> ChronoDelta:
        return cls(
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            milliseconds=milliseconds,
            microseconds=microseconds,
            neg=True
        )

    @classmethod
    def from_timedelta(cls, td: timedelta) -> ChronoDelta:
        if not isinstance(td, timedelta):
            raise TypeError(f"td must be a timedelta, got {type(td).__name__}")
        
        total_us = (td.days * _SEC_PER_DAY + td.seconds) * _US_PER_SEC + td.microseconds
        return cls.from_total_us(total_us)

    def to_timedelta(self) -> timedelta:
        return timedelta(microseconds=self.total_us)

    def normalized(self) -> ChronoDelta:
        return self.from_total_us(self.total_us)

    def expressed_in(
        self,
        *,
        weeks: bool = False,
        days: bool = False,
        hours: bool = False,
        minutes: bool = False,
        seconds: bool = False,
        milliseconds: bool = False,
        microseconds: bool = False,
        truncate: bool = False
    ) -> ChronoDelta:
        all_false = True
        for part in (weeks, days, hours, minutes, seconds, milliseconds, microseconds):
            if not isinstance(part, bool):
                raise TypeError("All time component flags must be boolean values")
            if part:
                all_false = False
        if all_false:
            raise ValueError("At least one time component must be set to True")
        if not isinstance(truncate, bool):
            raise TypeError("truncate must be a boolean value")
        
        remaining_us = abs(self.total_us)
        
        _weeks,         remaining_us = divmod(remaining_us, _US_PER_WEEK) if weeks else (0, remaining_us)
        _days,          remaining_us = divmod(remaining_us, _US_PER_DAY) if days else (0, remaining_us)
        _hours,         remaining_us = divmod(remaining_us, _US_PER_HOUR) if hours else (0, remaining_us)
        _minutes,       remaining_us = divmod(remaining_us, _US_PER_MIN) if minutes else (0, remaining_us)
        _seconds,       remaining_us = divmod(remaining_us, _US_PER_SEC) if seconds else (0, remaining_us)
        _milliseconds,  remaining_us = divmod(remaining_us, _US_PER_MS) if milliseconds else (0, remaining_us)
        _microseconds = remaining_us if microseconds else 0
        
        if not microseconds and not truncate and remaining_us > 0:
            raise ValueError("Cannot express in the given components without truncation, as there are remaining microseconds")
        
        _new_total_us = (
            _weeks * _US_PER_WEEK +
            _days * _US_PER_DAY +
            _hours * _US_PER_HOUR +
            _minutes * _US_PER_MIN +
            _seconds * _US_PER_SEC +
            _milliseconds * _US_PER_MS +
            _microseconds
        )
        
        if self.is_negative:
            _new_total_us = -_new_total_us
        
        return self._from_validated(
            weeks=_weeks,
            days=_days,
            hours=_hours,
            minutes=_minutes,
            seconds=_seconds,
            milliseconds=_milliseconds,
            microseconds=_microseconds,
            total_us=_new_total_us
        )

    def strfmt(self, fmt: str = "{sign}{w}:{d}:{h:02d}:{m:02d}:{s:02d}.{ms:03d}.{us:03d}") -> str:
        return fmt.format(
            sign='-' if self.total_us < 0 else '',
            w=self.weeks,
            d=self.days,
            h=self.hours,
            m=self.minutes,
            s=self.seconds,
            ms=self.milliseconds,
            us=self.microseconds
        )

    def verbose_str(self, show_zero_parts: bool = False) -> str:
        show_zero_parts = _require_bool(show_zero_parts, "show_zero_parts")
        parts_shown: list[str] = []
        
        for part, unit in self.iter_parts():
            if part != 0 or show_zero_parts:
                parts_shown.append(
                    # 0 = time value, 1 = unit name, 2 = plural 's' if needed
                    "{0} {1}{2}".format(
                        part,
                        unit.meta.name,
                        's' if part != 1 else ''
                    )
                )
        
        joined = ", ".join(parts_shown)
        joined = f"-{joined}" if self.total_us < 0 else joined
        return joined if joined else "0 microseconds"

    @property
    def total_seconds(self) -> float:
        return self.total_us / _US_PER_SEC

    @property
    def total_minutes(self) -> float:
        return self.total_us / _US_PER_MIN

    @property
    def total_hours(self) -> float:
        return self.total_us / _US_PER_HOUR

    @property
    def total_days(self) -> float:
        return self.total_us / _US_PER_DAY

    @property
    def total_weeks(self) -> float:
        return self.total_us / _US_PER_WEEK

    @property
    def is_positive(self) -> bool:
        return self.total_us > 0

    @property
    def is_negative(self) -> bool:
        return self.total_us < 0

    @property
    def is_zero(self) -> bool:
        return self.total_us == 0

    @property
    def sign(self) -> Literal[-1, 0, 1]:
        return 1 if self.is_positive else -1 if self.is_negative else 0

    def iter_parts(self) -> Iterator[tuple[int, ChronoUnit]]:
        yield self.weeks, ChronoUnit.WEEK
        yield self.days, ChronoUnit.DAY
        yield self.hours, ChronoUnit.HOUR
        yield self.minutes, ChronoUnit.MINUTE
        yield self.seconds, ChronoUnit.SECOND
        yield self.milliseconds, ChronoUnit.MILLISECOND
        yield self.microseconds, ChronoUnit.MICROSECOND

    def __str__(self) -> str:
        return f"{'-' if self.total_us < 0 else ''}{' '.join([
            f"{self.weeks}w",
            f"{self.days}d",
            f"{self.hours}h",
            f"{self.minutes}m",
            f"{self.seconds}s",
            f"{self.milliseconds}ms",
            f"{self.microseconds}us",
        ])}"

    def __hash__(self) -> int:
        return hash(self.total_us)

    def __add__(self, other: object) -> ChronoDelta | NotImplementedType:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return ChronoDelta.from_total_us(self.total_us + other.total_us)

    def __sub__(self, other: object) -> ChronoDelta | NotImplementedType:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return ChronoDelta.from_total_us(self.total_us - other.total_us)

    def __mul__(self, factor: object) -> ChronoDelta | NotImplementedType:
        if not isinstance(factor, int) or isinstance(factor, bool):
            return NotImplemented
        
        return ChronoDelta.from_total_us(self.total_us * factor)

    def __rmul__(self, factor: object) -> ChronoDelta | NotImplementedType:
        return self.__mul__(factor)

    @overload
    def __divmod__(self, divisor: ChronoDelta) -> tuple[int, ChronoDelta]: ...

    @overload
    def __divmod__(self, divisor: int) -> tuple[ChronoDelta, ChronoDelta]: ...

    def __divmod__(self, divisor: object) -> tuple[int | ChronoDelta, ChronoDelta] | NotImplementedType:
        if isinstance(divisor, ChronoDelta):
            if divisor.total_us == 0:
                raise ZeroDivisionError("Cannot divide by a ChronoDelta with total_us of 0")
            
            quotient, remainder_us = divmod(self.total_us, divisor.total_us)
            return quotient, ChronoDelta.from_total_us(remainder_us)
        elif isinstance(divisor, int) and not isinstance(divisor, bool):
            if divisor == 0:
                raise ZeroDivisionError("Cannot divide by zero")
            
            quotient_us, remainder_us = divmod(self.total_us, divisor)
            return ChronoDelta.from_total_us(quotient_us), ChronoDelta.from_total_us(remainder_us)
        else:
            return NotImplemented

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return self.total_us == other.total_us

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ChronoDelta):
            return NotImplemented
        
        return self.total_us < other.total_us

    def __bool__(self) -> bool:
        return self.total_us != 0

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
            self.microseconds,
            total_us=-self.total_us
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
            self.microseconds,
            total_us=-self.total_us
        )