from enum import Enum
from typing import Optional, Any, List, TypeVar, Type, Callable, cast


T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)


def from_none(x: Any) -> Any:
    assert x is None
    return x


def from_union(fs, x):
    for f in fs:
        try:
            return f(x)
        except:
            pass
    assert False


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def to_enum(c: Type[EnumT], x: Any) -> EnumT:
    assert isinstance(x, c)
    return x.value


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


class Name(Enum):
    ADVANCED = "ADVANCED"
    HELPSTRING = "HELPSTRING"
    STRINGS = "STRINGS"


class Property:
    name: Optional[Name]
    value: Optional[str]

    def __init__(self, name: Optional[Name], value: Optional[str]) -> None:
        self.name = name
        self.value = value

    @staticmethod
    def from_dict(obj: Any) -> 'Property':
        assert isinstance(obj, dict)
        name = from_union([Name, from_none], obj.get("name"))
        value = from_union([from_str, from_none], obj.get("value"))
        return Property(name, value)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.name is not None:
            result["name"] = from_union([lambda x: to_enum(Name, x), from_none], self.name)
        if self.value is not None:
            result["value"] = from_union([from_str, from_none], self.value)
        return result


class TypeEnum(Enum):
    BOOL = "BOOL"
    FILEPATH = "FILEPATH"
    INTERNAL = "INTERNAL"
    PATH = "PATH"
    STATIC = "STATIC"
    STRING = "STRING"
    UNINITIALIZED = "UNINITIALIZED"


class Entry:
    name: Optional[str]
    properties: Optional[List[Property]]
    type: Optional[TypeEnum]
    value: Optional[str]

    def __init__(self, name: Optional[str], properties: Optional[List[Property]], type: Optional[TypeEnum], value: Optional[str]) -> None:
        self.name = name
        self.properties = properties
        self.type = type
        self.value = value

    @staticmethod
    def from_dict(obj: Any) -> 'Entry':
        assert isinstance(obj, dict)
        name = from_union([from_str, from_none], obj.get("name"))
        properties = from_union([lambda x: from_list(Property.from_dict, x), from_none], obj.get("properties"))
        type = from_union([TypeEnum, from_none], obj.get("type"))
        value = from_union([from_str, from_none], obj.get("value"))
        return Entry(name, properties, type, value)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        if self.properties is not None:
            result["properties"] = from_union([lambda x: from_list(lambda x: to_class(Property, x), x), from_none], self.properties)
        if self.type is not None:
            result["type"] = from_union([lambda x: to_enum(TypeEnum, x), from_none], self.type)
        if self.value is not None:
            result["value"] = from_union([from_str, from_none], self.value)
        return result


class Version:
    major: Optional[int]
    minor: Optional[int]

    def __init__(self, major: Optional[int], minor: Optional[int]) -> None:
        self.major = major
        self.minor = minor

    @staticmethod
    def from_dict(obj: Any) -> 'Version':
        assert isinstance(obj, dict)
        major = from_union([from_int, from_none], obj.get("major"))
        minor = from_union([from_int, from_none], obj.get("minor"))
        return Version(major, minor)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.major is not None:
            result["major"] = from_union([from_int, from_none], self.major)
        if self.minor is not None:
            result["minor"] = from_union([from_int, from_none], self.minor)
        return result


class Cache:
    entries: Optional[List[Entry]]
    kind: Optional[str]
    version: Optional[Version]

    def __init__(self, entries: Optional[List[Entry]], kind: Optional[str], version: Optional[Version]) -> None:
        self.entries = entries
        self.kind = kind
        self.version = version

    @staticmethod
    def from_dict(obj: Any) -> 'Cache':
        assert isinstance(obj, dict)
        entries = from_union([lambda x: from_list(Entry.from_dict, x), from_none], obj.get("entries"))
        kind = from_union([from_str, from_none], obj.get("kind"))
        version = from_union([Version.from_dict, from_none], obj.get("version"))
        return Cache(entries, kind, version)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.entries is not None:
            result["entries"] = from_union([lambda x: from_list(lambda x: to_class(Entry, x), x), from_none], self.entries)
        if self.kind is not None:
            result["kind"] = from_union([from_str, from_none], self.kind)
        if self.version is not None:
            result["version"] = from_union([lambda x: to_class(Version, x), from_none], self.version)
        return result


def cache_from_dict(s: Any) -> Cache:
    return Cache.from_dict(s)


def cache_to_dict(x: Cache) -> Any:
    return to_class(Cache, x)
