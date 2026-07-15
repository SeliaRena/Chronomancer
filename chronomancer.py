from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from datetime import timedelta
from types import NotImplementedType
from functools import total_ordering, cache
from collections.abc import Iterator
from typing import Literal, Final, Any, overload
from numbers import Integral
from string import Formatter

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

# types
type TimeComponent = tuple[int, ChronoUnit]
type TimeComponents = tuple[TimeComponent, ...]
type IntMatrix = tuple[tuple[int, ...], ...]

_UNITS_ASC: Final[tuple[ChronoUnit, ...]] = tuple(
    sorted(ChronoUnit, key=lambda u: u.rank)
)
_UNITS_DESC: Final[tuple[ChronoUnit, ...]] = tuple(reversed(_UNITS_ASC))

# hot path for unit lookup by rank
_UNIT_RANKS_DESC: Final[tuple[int, ...]] = tuple(u.rank for u in _UNITS_DESC)
_US_FACTORS_BY_RANK: Final[tuple[int, ...]] = tuple(u.us_factor for u in _UNITS_ASC)

# Canonical decomposition divisor table.
#
# Each row represents an integer value expressed in one source unit.
# Columns below the source unit are unused and set to 0.
# Columns at or above the source unit contain cumulative divisors
# used to decompose the value into canonical components.
#
# Unit order:
# microsecond, millisecond, second, minute, hour, day, week
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

# for getattr()
_DELTA_COMPONENT_NAMES: Final[tuple[str, ...]] = (
    "weeks",
    "days",
    "hours",
    "minutes",
    "seconds",
    "milliseconds",
    "microseconds",
)

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
            raise ValueError("All time component values must be non-negative")
        
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
        """
        A canonical entrance for initializing a ChronoDelta.
        Returns a normalized (decomposed) instance.
        """
        
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
    def from_unit(
        cls,
        value: int,
        unit: ChronoUnit,
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
        value = _require_integer(value, "value")
        
        if not isinstance(unit, ChronoUnit):
            raise TypeError(f"unit must be a ChronoUnit, got {type(unit).__name__}")
        
        flags = (microseconds, milliseconds, seconds, minutes, hours, days, weeks)
        use_default_flags = True
        for flag in flags:
            if not isinstance(flag, bool):
                raise TypeError("All time component flags must be boolean values")
            if flag:
                use_default_flags = False
        if use_default_flags:
            flags = (True,) * 7  # default to all components if none specified
        
        truncate = _require_bool(truncate, "truncate")
        
        if value == 0:
            return cls.zero()
        
        if use_default_flags:
            if unit is ChronoUnit.MICROSECOND:
                return cls.from_total_us(value)
            
            return cls.from_total_us(value * unit.us_factor)
        
        # lsr: least significant rank of the enabled components
        lsr = 0
        for rank, flag in enumerate(flags):
            if flag:
                lsr = rank
                break
        
        src_rank = unit.rank
        total = 0
        
        if src_rank <= lsr:
            lsr = src_rank
            total = value
        else:
            total = value * _DECOMPOSITION_DIVISORS[lsr][src_rank]
        
        remaining_value = abs(total)
        args: list[int] = []
        
        for target_rank in _UNIT_RANKS_DESC:
            component_value = 0
            
            if target_rank >= lsr and flags[target_rank]:
                divisor = _DECOMPOSITION_DIVISORS[lsr][target_rank]
                
                if divisor == 1:
                    component_value = remaining_value
                    remaining_value = 0
                else:
                    component_value, remaining_value = divmod(remaining_value, divisor)
            
            args.append(component_value)
        
        if remaining_value and not truncate:
            raise ValueError("Cannot express in the given components without truncation, as there are remaining units")
        
        new_total_us = (abs(total) - remaining_value) * _US_FACTORS_BY_RANK[lsr]
        
        return cls._from_validated(
            *args,
            total_us=-new_total_us if value < 0 else new_total_us
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
        for flag in (weeks, days, hours, minutes, seconds, milliseconds, microseconds):
            if not isinstance(flag, bool):
                raise TypeError("All time component flags must be boolean values")
            if flag:
                all_false = False
        if all_false:
            raise ValueError("At least one time component must be enabled for expression")
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

    def verbose_str(self, show_zero_components: bool = False) -> str:
        show_zero_components = _require_bool(show_zero_components, "show_zero_components")
        render_parts: list[str] = []
        
        for value, unit in self.components:
            if value != 0 or show_zero_components:
                render_parts.append(
                    # 0 = time value, 1 = unit name, 2 = plural 's' if needed
                    "{0} {1}{2}".format(
                        value,
                        unit.meta.name,
                        's' if value != 1 else ''
                    )
                )
        
        joined = ", ".join(render_parts)
        joined = f"-{joined}" if self.total_us < 0 else joined
        return joined if joined else "0 microseconds"

    @property
    def components(self) -> TimeComponents:
        return (
            (self.weeks, ChronoUnit.WEEK),
            (self.days, ChronoUnit.DAY),
            (self.hours, ChronoUnit.HOUR),
            (self.minutes, ChronoUnit.MINUTE),
            (self.seconds, ChronoUnit.SECOND),
            (self.milliseconds, ChronoUnit.MILLISECOND),
            (self.microseconds, ChronoUnit.MICROSECOND),
        )

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

    def iter_components(self) -> Iterator[TimeComponent]:
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

@dataclass(frozen=True, slots=True, kw_only=True)
class DeltaFormatSpec:
    weeks:        str | None = None
    days:         str | None = None
    hours:        str | None = None
    minutes:      str | None = None
    seconds:      str | None = None
    milliseconds: str | None = None
    microseconds: str | None = None
    
    sign: Literal["-", "+-", None] = "-"
    separator: str = ""
    show_zero_components: bool = False

    def __post_init__(self) -> None:
        for component in (self.weeks, self.days, self.hours, self.minutes, self.seconds, self.milliseconds, self.microseconds):
            if component is not None and not isinstance(component, str):
                raise TypeError("All component format strings must be either None or a string")
        
        if self.sign not in ("-", "+-", None):
            raise ValueError("sign must be one of '-', '+-', or None")
        if not isinstance(self.separator, str):
            raise TypeError("separator must be a string")
        if not isinstance(self.show_zero_components, bool):
            raise TypeError("show_zero_components must be a boolean")

type DeltaFormatter = _DeltaFormatter
_SUPPORTED_PLACEHOLDERS: Final[frozenset[str]] = frozenset({
    "value",
    "name",
    "abbr",
    "symbol",
    "plural",
})

# op codes
GET_VALUE = 0
GET_PLURAL = 1

@dataclass(frozen=True, slots=True)
class _ComponentFormatPlan:
    fmt_str: str # compiled format string for the component
    component_name: str # field name of the component in ChronoDelta
    ops: tuple[int, ...] # use int for op codes to avoid string comparisons at runtime

class _DeltaFormatter:
    __slots__ = (
        "_plans",
        "_neg_sign",
        "_pos_sign",
        "_separator",
        "_show_zero_components",
        "_fixed_fmt_str",
    )

    def __init__(
        self,
        plans: tuple[_ComponentFormatPlan, ...],
        sign: Literal["-", "+-", None],
        separator: str,
        show_zero_components: bool
    ) -> None:
        self._plans = plans
        self._neg_sign = "-" if sign is not None else ""
        self._pos_sign = "+" if sign == "+-" else ""
        self._separator = separator
        self._show_zero_components = show_zero_components
        
        self._fixed_fmt_str: str | None = None
        # If all components are included in the format, we can precompute a fixed format string for performance
        if show_zero_components:
            self._fixed_fmt_str = self._separator.join(
                plan.fmt_str for plan in plans
            )

    def format(self, delta: ChronoDelta) -> str:
        if not isinstance(delta, ChronoDelta):
            raise TypeError(f"delta must be a ChronoDelta, got {type(delta).__name__}")
        
        # fixed format string == "" means no components to render, return empty string
        if self._fixed_fmt_str == "":
            return ""
        
        render_parts: list[str] = []
        render_args: list[Any] = []
        
        for plan in self._plans:
            value = getattr(delta, plan.component_name)
            
            if value == 0 and not self._show_zero_components:
                continue
            
            if self._fixed_fmt_str is None:
                render_parts.append(plan.fmt_str)
            
            for op in plan.ops:
                if op == GET_VALUE:
                    render_args.append(value)
                elif op == GET_PLURAL:
                    render_args.append("s" if value != 1 else "")
        
        sign = (
            self._neg_sign
            if delta.is_negative
            else self._pos_sign
            if delta.is_positive
            else ""
        )
        
        # if fixed_fmt_str is available, render and return it before the empty render_parts get handled as a special case
        if self._fixed_fmt_str is not None:
            return sign + self._fixed_fmt_str.format(*render_args)
        
        # handle special cases first for performance
        if not render_parts:
            if delta.is_zero and not self._show_zero_components:
                return "0 microseconds"
            return ""
        
        return sign + self._separator.join(render_parts).format(*render_args)

def _format_value(value: Any, spec: str | None, conversion: str | None) -> str:
    # Avoid redundant format() calls for common cases where no spec or conversion is provided
    if spec is None and conversion is None:
        # Avoid redundant str() calls
        if isinstance(value, str):
            return value
        
        return str(value)
    
    if conversion is not None:
        if conversion == "s":
            value = str(value)
        elif conversion == "r":
            value = repr(value)
        elif conversion == "a":
            value = ascii(value)
    
    return format(value, spec if spec is not None else "")

def _build_dynamic_field(format_spec: str | None, conversion: str | None) -> str:
    return (
        "{"
        + (f"!{conversion}" if conversion is not None else "")
        + (f":{format_spec}" if format_spec is not None else "")
        + "}"
    )

def create_delta_formatter(spec: DeltaFormatSpec) -> DeltaFormatter:
    if not isinstance(spec, DeltaFormatSpec):
        raise TypeError(f"spec must be a DeltaFormatSpec, got {type(spec).__name__}")
    
    plans: list[_ComponentFormatPlan] = []
    
    for i, raw_fmt_str in enumerate((
        spec.weeks,
        spec.days,
        spec.hours,
        spec.minutes,
        spec.seconds,
        spec.milliseconds,
        spec.microseconds
    )):
        if raw_fmt_str is None:
            continue
        
        parts: list[str] = []
        ops: list[int] = []
        unit = _UNITS_DESC[i]
        for literal, field_name, format_spec, conversion in Formatter().parse(raw_fmt_str):
            parts.append(
                literal.replace("{", "{{").replace("}", "}}")
            )
            
            if field_name is None:
                continue
            if field_name not in _SUPPORTED_PLACEHOLDERS:
                raise ValueError(f"Unsupported placeholder '{field_name}' in format string for {unit.symbol}")
            
            if format_spec and (
                "{" in format_spec or "}" in format_spec
            ):
                raise ValueError(f"Nested replacement fields are not supported")
            
            if conversion not in (None, "s", "r", "a"):
                raise ValueError(f"Unsupported conversion '!{conversion}'")
            
            match field_name:
                case "value":
                    ops.append(GET_VALUE)
                    parts.append(_build_dynamic_field(format_spec, conversion))
                case "plural":
                    ops.append(GET_PLURAL)
                    parts.append(_build_dynamic_field(format_spec, conversion))
                case "name":
                    parts.append(_format_value(unit.meta.name, format_spec, conversion))
                case "abbr":
                    parts.append(_format_value(unit.meta.abbr, format_spec, conversion))
                case "symbol":
                    parts.append(_format_value(unit.symbol, format_spec, conversion))
                case _:
                    raise ValueError(f"Unsupported placeholder '{field_name}' in format string for {unit.symbol}")
        
        # finished handling parsed format string, a format plan now can be created for this component
        plans.append(
            _ComponentFormatPlan(
                fmt_str="".join(parts),
                component_name=_DELTA_COMPONENT_NAMES[i],
                ops=tuple(ops)
            )
        )
    
    return _DeltaFormatter(
        plans=tuple(plans),
        sign=spec.sign,
        separator=spec.separator,
        show_zero_components=spec.show_zero_components
    )