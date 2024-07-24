from typing import Optional, Any, List, TypeVar, Type, cast, Callable


T = TypeVar("T")


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
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


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


class Generator:
    multi_config: Optional[bool]
    name: Optional[str]

    def __init__(self, multi_config: Optional[bool], name: Optional[str]) -> None:
        self.multi_config = multi_config
        self.name = name

    @staticmethod
    def from_dict(obj: Any) -> 'Generator':
        assert isinstance(obj, dict)
        multi_config = from_union([from_bool, from_none], obj.get("multiConfig"))
        name = from_union([from_str, from_none], obj.get("name"))
        return Generator(multi_config, name)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.multi_config is not None:
            result["multiConfig"] = from_union([from_bool, from_none], self.multi_config)
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        return result


class Paths:
    cmake: Optional[str]
    cpack: Optional[str]
    ctest: Optional[str]
    root: Optional[str]

    def __init__(self, cmake: Optional[str], cpack: Optional[str], ctest: Optional[str], root: Optional[str]) -> None:
        self.cmake = cmake
        self.cpack = cpack
        self.ctest = ctest
        self.root = root

    @staticmethod
    def from_dict(obj: Any) -> 'Paths':
        assert isinstance(obj, dict)
        cmake = from_union([from_str, from_none], obj.get("cmake"))
        cpack = from_union([from_str, from_none], obj.get("cpack"))
        ctest = from_union([from_str, from_none], obj.get("ctest"))
        root = from_union([from_str, from_none], obj.get("root"))
        return Paths(cmake, cpack, ctest, root)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.cmake is not None:
            result["cmake"] = from_union([from_str, from_none], self.cmake)
        if self.cpack is not None:
            result["cpack"] = from_union([from_str, from_none], self.cpack)
        if self.ctest is not None:
            result["ctest"] = from_union([from_str, from_none], self.ctest)
        if self.root is not None:
            result["root"] = from_union([from_str, from_none], self.root)
        return result


class CmakeVersion:
    is_dirty: Optional[bool]
    major: Optional[int]
    minor: Optional[int]
    patch: Optional[int]
    string: Optional[str]
    suffix: Optional[str]

    def __init__(self, is_dirty: Optional[bool], major: Optional[int], minor: Optional[int], patch: Optional[int], string: Optional[str], suffix: Optional[str]) -> None:
        self.is_dirty = is_dirty
        self.major = major
        self.minor = minor
        self.patch = patch
        self.string = string
        self.suffix = suffix

    @staticmethod
    def from_dict(obj: Any) -> 'CmakeVersion':
        assert isinstance(obj, dict)
        is_dirty = from_union([from_bool, from_none], obj.get("isDirty"))
        major = from_union([from_int, from_none], obj.get("major"))
        minor = from_union([from_int, from_none], obj.get("minor"))
        patch = from_union([from_int, from_none], obj.get("patch"))
        string = from_union([from_str, from_none], obj.get("string"))
        suffix = from_union([from_str, from_none], obj.get("suffix"))
        return CmakeVersion(is_dirty, major, minor, patch, string, suffix)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.is_dirty is not None:
            result["isDirty"] = from_union([from_bool, from_none], self.is_dirty)
        if self.major is not None:
            result["major"] = from_union([from_int, from_none], self.major)
        if self.minor is not None:
            result["minor"] = from_union([from_int, from_none], self.minor)
        if self.patch is not None:
            result["patch"] = from_union([from_int, from_none], self.patch)
        if self.string is not None:
            result["string"] = from_union([from_str, from_none], self.string)
        if self.suffix is not None:
            result["suffix"] = from_union([from_str, from_none], self.suffix)
        return result


class Cmake:
    generator: Optional[Generator]
    paths: Optional[Paths]
    version: Optional[CmakeVersion]

    def __init__(self, generator: Optional[Generator], paths: Optional[Paths], version: Optional[CmakeVersion]) -> None:
        self.generator = generator
        self.paths = paths
        self.version = version

    @staticmethod
    def from_dict(obj: Any) -> 'Cmake':
        assert isinstance(obj, dict)
        generator = from_union([Generator.from_dict, from_none], obj.get("generator"))
        paths = from_union([Paths.from_dict, from_none], obj.get("paths"))
        version = from_union([CmakeVersion.from_dict, from_none], obj.get("version"))
        return Cmake(generator, paths, version)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.generator is not None:
            result["generator"] = from_union([lambda x: to_class(Generator, x), from_none], self.generator)
        if self.paths is not None:
            result["paths"] = from_union([lambda x: to_class(Paths, x), from_none], self.paths)
        if self.version is not None:
            result["version"] = from_union([lambda x: to_class(CmakeVersion, x), from_none], self.version)
        return result


class ObjectVersion:
    major: Optional[int]
    minor: Optional[int]

    def __init__(self, major: Optional[int], minor: Optional[int]) -> None:
        self.major = major
        self.minor = minor

    @staticmethod
    def from_dict(obj: Any) -> 'ObjectVersion':
        assert isinstance(obj, dict)
        major = from_union([from_int, from_none], obj.get("major"))
        minor = from_union([from_int, from_none], obj.get("minor"))
        return ObjectVersion(major, minor)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.major is not None:
            result["major"] = from_union([from_int, from_none], self.major)
        if self.minor is not None:
            result["minor"] = from_union([from_int, from_none], self.minor)
        return result


class Object:
    json_file: Optional[str]
    kind: Optional[str]
    version: Optional[ObjectVersion]

    def __init__(self, json_file: Optional[str], kind: Optional[str], version: Optional[ObjectVersion]) -> None:
        self.json_file = json_file
        self.kind = kind
        self.version = version

    @staticmethod
    def from_dict(obj: Any) -> 'Object':
        assert isinstance(obj, dict)
        json_file = from_union([from_str, from_none], obj.get("jsonFile"))
        kind = from_union([from_str, from_none], obj.get("kind"))
        version = from_union([ObjectVersion.from_dict, from_none], obj.get("version"))
        return Object(json_file, kind, version)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.json_file is not None:
            result["jsonFile"] = from_union([from_str, from_none], self.json_file)
        if self.kind is not None:
            result["kind"] = from_union([from_str, from_none], self.kind)
        if self.version is not None:
            result["version"] = from_union([lambda x: to_class(ObjectVersion, x), from_none], self.version)
        return result


class Reply:
    cache_v2: Optional[Object]
    cmake_files_v1: Optional[Object]
    codemodel_v2: Optional[Object]

    def __init__(self, cache_v2: Optional[Object], cmake_files_v1: Optional[Object], codemodel_v2: Optional[Object]) -> None:
        self.cache_v2 = cache_v2
        self.cmake_files_v1 = cmake_files_v1
        self.codemodel_v2 = codemodel_v2

    @staticmethod
    def from_dict(obj: Any) -> 'Reply':
        assert isinstance(obj, dict)
        cache_v2 = from_union([Object.from_dict, from_none], obj.get("cache-v2"))
        cmake_files_v1 = from_union([Object.from_dict, from_none], obj.get("cmakeFiles-v1"))
        codemodel_v2 = from_union([Object.from_dict, from_none], obj.get("codemodel-v2"))
        return Reply(cache_v2, cmake_files_v1, codemodel_v2)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.cache_v2 is not None:
            result["cache-v2"] = from_union([lambda x: to_class(Object, x), from_none], self.cache_v2)
        if self.cmake_files_v1 is not None:
            result["cmakeFiles-v1"] = from_union([lambda x: to_class(Object, x), from_none], self.cmake_files_v1)
        if self.codemodel_v2 is not None:
            result["codemodel-v2"] = from_union([lambda x: to_class(Object, x), from_none], self.codemodel_v2)
        return result


class Index:
    cmake: Optional[Cmake]
    objects: Optional[List[Object]]
    reply: Optional[Reply]

    def __init__(self, cmake: Optional[Cmake], objects: Optional[List[Object]], reply: Optional[Reply]) -> None:
        self.cmake = cmake
        self.objects = objects
        self.reply = reply

    @staticmethod
    def from_dict(obj: Any) -> 'Index':
        assert isinstance(obj, dict)
        cmake = from_union([Cmake.from_dict, from_none], obj.get("cmake"))
        objects = from_union([lambda x: from_list(Object.from_dict, x), from_none], obj.get("objects"))
        reply = from_union([Reply.from_dict, from_none], obj.get("reply"))
        return Index(cmake, objects, reply)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.cmake is not None:
            result["cmake"] = from_union([lambda x: to_class(Cmake, x), from_none], self.cmake)
        if self.objects is not None:
            result["objects"] = from_union([lambda x: from_list(lambda x: to_class(Object, x), x), from_none], self.objects)
        if self.reply is not None:
            result["reply"] = from_union([lambda x: to_class(Reply, x), from_none], self.reply)
        return result


def index_from_dict(s: Any) -> Index:
    return Index.from_dict(s)


def index_to_dict(x: Index) -> Any:
    return to_class(Index, x)
