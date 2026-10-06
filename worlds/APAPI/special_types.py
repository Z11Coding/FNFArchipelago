from __future__ import annotations
import collections.abc
import typing

T = typing.TypeVar("T")

class Abstract:
    underlying: type | None = None
    supports: tuple[type, ...] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.underlying is None and hasattr(cls, "__orig_bases__"):
            for base in getattr(cls, "__orig_bases__", ()):
                args = typing.get_args(base)
                if args:
                    cls.underlying = args[0]
                    break
        if cls.underlying is not None and not cls.supports:
            cls.supports = (cls.underlying,)

    def __new__(cls, value=None):
        if value is None and cls.underlying is not None:
            try:
                value = cls.underlying()
            except Exception:
                value = None
        if value is not None and cls.underlying is not None and not isinstance(value, cls.underlying):
            for typ in cls.supports:
                if isinstance(value, typ):
                    try:
                        if typ is not cls.underlying:
                            value = cls.underlying(value)
                    except Exception:
                        pass
                    break
            else:
                if cls.supports and isinstance(value, cls.supports):
                    try:
                        value = cls.underlying(value)
                    except Exception:
                        pass
        obj = object.__new__(cls)
        obj._value = value
        return obj

    def __getattr__(self, name):
        return getattr(self._value, name)

    def __setattr__(self, name, value):
        if name in ("_value", "underlying", "supports"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._value, name, value)

    def __str__(self):
        return str(self._value)

    def __repr__(self):
        return f"{type(self).__name__}({self._value!r})"

    def __int__(self):
        return int(self._value)

    def __float__(self):
        return float(self._value)

    def __bool__(self):
        return bool(self._value)

    def __len__(self):
        return len(self._value)

    def __iter__(self):
        return iter(self._value)

    def __contains__(self, item):
        return item in self._value

    def __getitem__(self, key):
        return self._value[key]

    def __setitem__(self, key, value):
        self._value[key] = value

    def __eq__(self, other):
        if isinstance(other, Abstract):
            return self._value == other._value
        return self._value == other

    def __hash__(self):
        try:
            return hash(self._value)
        except Exception:
            return object.__hash__(self)

    @classmethod
    def from_value(cls, value):
        return cls(value)

    def to_value(self):
        return self._value

    def __class_getitem__(cls, underlying):
        if not isinstance(underlying, tuple):
            underlying = (underlying,)
        name = f"{cls.__name__}[{','.join(getattr(t, '__name__', str(t)) for t in underlying)}]"
        return type(name, (cls,), {"underlying": underlying[0] if len(underlying)==1 else underlying[0], "supports": underlying})

def make_abstract(name: str, underlying: type, supports: tuple[type, ...] | None = None, module: str | None = None):
    supports = supports if supports is not None else (underlying,)
    return type(name, (Abstract[underlying],), {"underlying": underlying, "supports": supports, "__module__": module or __name__})

class _RefDescriptor:
    def __sub__(self, other):
        try:
            return set(self.get() or set()) - set(other or set())
        except Exception:
            return set()

    def __rsub__(self, other):
        try:
            return set(other or set()) - set(self.get() or set())
        except Exception:
            return set()

    def __and__(self, other):
        try:
            return set(self.get() or set()) & set(other or set())
        except Exception:
            return set()

    def __rand__(self, other):
        try:
            return set(other or set()) & set(self.get() or set())
        except Exception:
            return set()

    def __or__(self, other):
        try:
            return set(self.get() or set()) | set(other or set())
        except Exception:
            return set()

    def __ror__(self, other):
        try:
            return set(other or set()) | set(self.get() or set())
        except Exception:
            return set()

    def __init__(self, getter: typing.Callable[[], T] | None = None, value: T | None = None):
        self._getter = getter
        self._value = value

    def get(self) -> T | None:
        if self._getter is not None:
            try:
                return self._getter()
            except Exception:
                return self._value
        return self._value

    def set(self, value: T | _RefDescriptor):
        if isinstance(value, _RefDescriptor):
            self._value = value._value
            self._getter = value._getter
        elif callable(value) and not isinstance(value, (set, list, dict, str, int, float, bool)):
            try:
                test = value()
                self._getter = value
                self._value = None
            except Exception:
                self._value = value
                self._getter = None
        else:
            self._value = value
            self._getter = None

    def __call__(self) -> T | None:
        return self.get()

    def __iter__(self):
        v = self.get()
        return iter(v) if v is not None else iter([])

    def __contains__(self, item):
        v = self.get()
        return item in v if v is not None else False

    def __len__(self):
        v = self.get()
        return len(v) if v is not None else 0

    def __bool__(self):
        v = self.get()
        return bool(v)

    def __str__(self):
        return str(self.get())

    def __repr__(self):
        return f"Ref({self.get()!r})"

    def __int__(self):
        v = self.get()
        return int(v) if v is not None else 0

    def __float__(self):
        v = self.get()
        return float(v) if v is not None else 0.0

    def __eq__(self, other):
        if isinstance(other, _RefDescriptor):
            return self.get() == other.get()
        return self.get() == other

    def __hash__(self):
        try:
            return hash(self.get())
        except Exception:
            return object.__hash__(self)

    def __getattr__(self, name):
        v = self.get()
        return getattr(v, name)

class Ref:
    def __class_getitem__(cls, underlying):
        if isinstance(underlying, tuple):
            underlying = underlying[0]
        class _SpecializedRef(_RefDescriptor):
            _underlying_type = underlying
            def __init__(self, value=None, getter=None):
                if value is not None and getter is None and callable(value) and not isinstance(value, (set, list, dict, str, bytes)):
                    try:
                        value()
                        super().__init__(getter=value)
                        return
                    except Exception:
                        pass
                super().__init__(getter=getter, value=value)
                if value is not None and not isinstance(value, underlying) and isinstance(value, (set, list, dict)):
                    try:
                        value = underlying(value)
                        self._value = value
                    except Exception:
                        pass
            @classmethod
            def from_value(cls, v):
                return cls(v)
        _SpecializedRef.__name__ = f"Ref[{getattr(underlying, '__name__', str(underlying))}]"
        return _SpecializedRef

DynamicValue = Ref
LiveRef = Ref
