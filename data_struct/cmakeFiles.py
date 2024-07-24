from typing import Optional, Any, List, TypeVar, Callable, Type, cast


T = TypeVar("T")


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


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


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


class Input:
    path: Optional[str]
    is_c_make: Optional[bool]
    is_external: Optional[bool]
    is_generated: Optional[bool]

    def __init__(self, path: Optional[str], is_c_make: Optional[bool], is_external: Optional[bool], is_generated: Optional[bool]) -> None:
        self.path = path
        self.is_c_make = is_c_make
        self.is_external = is_external
        self.is_generated = is_generated

    @staticmethod
    def from_dict(obj: Any) -> 'Input':
        assert isinstance(obj, dict)
        path = from_union([from_str, from_none], obj.get("path"))
        is_c_make = from_union([from_bool, from_none], obj.get("isCMake"))
        is_external = from_union([from_bool, from_none], obj.get("isExternal"))
        is_generated = from_union([from_bool, from_none], obj.get("isGenerated"))
        return Input(path, is_c_make, is_external, is_generated)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.path is not None:
            result["path"] = from_union([from_str, from_none], self.path)
        if self.is_c_make is not None:
            result["isCMake"] = from_union([from_bool, from_none], self.is_c_make)
        if self.is_external is not None:
            result["isExternal"] = from_union([from_bool, from_none], self.is_external)
        if self.is_generated is not None:
            result["isGenerated"] = from_union([from_bool, from_none], self.is_generated)
        return result


class Paths:
    build: Optional[str]
    source: Optional[str]

    def __init__(self, build: Optional[str], source: Optional[str]) -> None:
        self.build = build
        self.source = source

    @staticmethod
    def from_dict(obj: Any) -> 'Paths':
        assert isinstance(obj, dict)
        build = from_union([from_str, from_none], obj.get("build"))
        source = from_union([from_str, from_none], obj.get("source"))
        return Paths(build, source)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.build is not None:
            result["build"] = from_union([from_str, from_none], self.build)
        if self.source is not None:
            result["source"] = from_union([from_str, from_none], self.source)
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


class CMakeFiles:
    inputs: Optional[List[Input]]
    kind: Optional[str]
    paths: Optional[Paths]
    version: Optional[Version]

    def __init__(self, inputs: Optional[List[Input]], kind: Optional[str], paths: Optional[Paths], version: Optional[Version]) -> None:
        self.inputs = inputs
        self.kind = kind
        self.paths = paths
        self.version = version

    @staticmethod
    def from_dict(obj: Any) -> 'CMakeFiles':
        assert isinstance(obj, dict)
        inputs = from_union([lambda x: from_list(Input.from_dict, x), from_none], obj.get("inputs"))
        kind = from_union([from_str, from_none], obj.get("kind"))
        paths = from_union([Paths.from_dict, from_none], obj.get("paths"))
        version = from_union([Version.from_dict, from_none], obj.get("version"))
        return CMakeFiles(inputs, kind, paths, version)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.inputs is not None:
            result["inputs"] = from_union([lambda x: from_list(lambda x: to_class(Input, x), x), from_none], self.inputs)
        if self.kind is not None:
            result["kind"] = from_union([from_str, from_none], self.kind)
        if self.paths is not None:
            result["paths"] = from_union([lambda x: to_class(Paths, x), from_none], self.paths)
        if self.version is not None:
            result["version"] = from_union([lambda x: to_class(Version, x), from_none], self.version)
        return result


def c_make_files_from_dict(s: Any) -> CMakeFiles:
    return CMakeFiles.from_dict(s)


def c_make_files_to_dict(x: CMakeFiles) -> Any:
    return to_class(CMakeFiles, x)
