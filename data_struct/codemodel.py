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


def to_enum(c: Type[EnumT], x: Any) -> EnumT:
    assert isinstance(x, c)
    return x.value


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


class String(Enum):
    THE_28122 = "2.8.12.2"


class MinimumCMakeVersion:
    string: Optional[String]

    def __init__(self, string: Optional[String]) -> None:
        self.string = string

    @staticmethod
    def from_dict(obj: Any) -> 'MinimumCMakeVersion':
        assert isinstance(obj, dict)
        string = from_union([from_str, from_none], obj.get("string"))
        return MinimumCMakeVersion(string)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.string is not None:
            result["string"] = from_union([lambda x: to_enum(String, x), from_none], self.string)
        return result


class Directory:
    build: Optional[str]
    child_indexes: Optional[List[int]]
    has_install_rule: Optional[bool]
    json_file: Optional[str]
    minimum_c_make_version: Optional[MinimumCMakeVersion]
    project_index: Optional[int]
    source: Optional[str]
    target_indexes: Optional[List[int]]
    parent_index: Optional[int]

    def __init__(self, build: Optional[str], child_indexes: Optional[List[int]], has_install_rule: Optional[bool], json_file: Optional[str], minimum_c_make_version: Optional[MinimumCMakeVersion], project_index: Optional[int], source: Optional[str], target_indexes: Optional[List[int]], parent_index: Optional[int]) -> None:
        self.build = build
        self.child_indexes = child_indexes
        self.has_install_rule = has_install_rule
        self.json_file = json_file
        self.minimum_c_make_version = minimum_c_make_version
        self.project_index = project_index
        self.source = source
        self.target_indexes = target_indexes
        self.parent_index = parent_index

    @staticmethod
    def from_dict(obj: Any) -> 'Directory':
        assert isinstance(obj, dict)
        build = from_union([from_str, from_none], obj.get("build"))
        child_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("childIndexes"))
        has_install_rule = from_union([from_bool, from_none], obj.get("hasInstallRule"))
        json_file = from_union([from_str, from_none], obj.get("jsonFile"))
        minimum_c_make_version = from_union([MinimumCMakeVersion.from_dict, from_none], obj.get("minimumCMakeVersion"))
        project_index = from_union([from_int, from_none], obj.get("projectIndex"))
        source = from_union([from_str, from_none], obj.get("source"))
        target_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("targetIndexes"))
        parent_index = from_union([from_int, from_none], obj.get("parentIndex"))
        return Directory(build, child_indexes, has_install_rule, json_file, minimum_c_make_version, project_index, source, target_indexes, parent_index)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.build is not None:
            result["build"] = from_union([from_str, from_none], self.build)
        if self.child_indexes is not None:
            result["childIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.child_indexes)
        if self.has_install_rule is not None:
            result["hasInstallRule"] = from_union([from_bool, from_none], self.has_install_rule)
        if self.json_file is not None:
            result["jsonFile"] = from_union([from_str, from_none], self.json_file)
        if self.minimum_c_make_version is not None:
            result["minimumCMakeVersion"] = from_union([lambda x: to_class(MinimumCMakeVersion, x), from_none], self.minimum_c_make_version)
        if self.project_index is not None:
            result["projectIndex"] = from_union([from_int, from_none], self.project_index)
        if self.source is not None:
            result["source"] = from_union([from_str, from_none], self.source)
        if self.target_indexes is not None:
            result["targetIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.target_indexes)
        if self.parent_index is not None:
            result["parentIndex"] = from_union([from_int, from_none], self.parent_index)
        return result


class Project:
    child_indexes: Optional[List[int]]
    directory_indexes: Optional[List[int]]
    name: Optional[str]
    target_indexes: Optional[List[int]]
    parent_index: Optional[int]

    def __init__(self, child_indexes: Optional[List[int]], directory_indexes: Optional[List[int]], name: Optional[str], target_indexes: Optional[List[int]], parent_index: Optional[int]) -> None:
        self.child_indexes = child_indexes
        self.directory_indexes = directory_indexes
        self.name = name
        self.target_indexes = target_indexes
        self.parent_index = parent_index

    @staticmethod
    def from_dict(obj: Any) -> 'Project':
        assert isinstance(obj, dict)
        child_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("childIndexes"))
        directory_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("directoryIndexes"))
        name = from_union([from_str, from_none], obj.get("name"))
        target_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("targetIndexes"))
        parent_index = from_union([from_int, from_none], obj.get("parentIndex"))
        return Project(child_indexes, directory_indexes, name, target_indexes, parent_index)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.child_indexes is not None:
            result["childIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.child_indexes)
        if self.directory_indexes is not None:
            result["directoryIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.directory_indexes)
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        if self.target_indexes is not None:
            result["targetIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.target_indexes)
        if self.parent_index is not None:
            result["parentIndex"] = from_union([from_int, from_none], self.parent_index)
        return result


class Target:
    directory_index: Optional[int]
    id: Optional[str]
    json_file: Optional[str]
    name: Optional[str]
    project_index: Optional[int]

    def __init__(self, directory_index: Optional[int], id: Optional[str], json_file: Optional[str], name: Optional[str], project_index: Optional[int]) -> None:
        self.directory_index = directory_index
        self.id = id
        self.json_file = json_file
        self.name = name
        self.project_index = project_index

    @staticmethod
    def from_dict(obj: Any) -> 'Target':
        assert isinstance(obj, dict)
        directory_index = from_union([from_int, from_none], obj.get("directoryIndex"))
        id = from_union([from_str, from_none], obj.get("id"))
        json_file = from_union([from_str, from_none], obj.get("jsonFile"))
        name = from_union([from_str, from_none], obj.get("name"))
        project_index = from_union([from_int, from_none], obj.get("projectIndex"))
        return Target(directory_index, id, json_file, name, project_index)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.directory_index is not None:
            result["directoryIndex"] = from_union([from_int, from_none], self.directory_index)
        if self.id is not None:
            result["id"] = from_union([from_str, from_none], self.id)
        if self.json_file is not None:
            result["jsonFile"] = from_union([from_str, from_none], self.json_file)
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        if self.project_index is not None:
            result["projectIndex"] = from_union([from_int, from_none], self.project_index)
        return result


class Configuration:
    directories: Optional[List[Directory]]
    name: Optional[str]
    projects: Optional[List[Project]]
    targets: Optional[List[Target]]

    def __init__(self, directories: Optional[List[Directory]], name: Optional[str], projects: Optional[List[Project]], targets: Optional[List[Target]]) -> None:
        self.directories = directories
        self.name = name
        self.projects = projects
        self.targets = targets

    @staticmethod
    def from_dict(obj: Any) -> 'Configuration':
        assert isinstance(obj, dict)
        directories = from_union([lambda x: from_list(Directory.from_dict, x), from_none], obj.get("directories"))
        name = from_union([from_str, from_none], obj.get("name"))
        projects = from_union([lambda x: from_list(Project.from_dict, x), from_none], obj.get("projects"))
        targets = from_union([lambda x: from_list(Target.from_dict, x), from_none], obj.get("targets"))
        return Configuration(directories, name, projects, targets)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.directories is not None:
            result["directories"] = from_union([lambda x: from_list(lambda x: to_class(Directory, x), x), from_none], self.directories)
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        if self.projects is not None:
            result["projects"] = from_union([lambda x: from_list(lambda x: to_class(Project, x), x), from_none], self.projects)
        if self.targets is not None:
            result["targets"] = from_union([lambda x: from_list(lambda x: to_class(Target, x), x), from_none], self.targets)
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


class CodeModel:
    configurations: Optional[List[Configuration]]
    kind: Optional[str]
    paths: Optional[Paths]
    version: Optional[Version]

    def __init__(self, configurations: Optional[List[Configuration]], kind: Optional[str], paths: Optional[Paths], version: Optional[Version]) -> None:
        self.configurations = configurations
        self.kind = kind
        self.paths = paths
        self.version = version

    @staticmethod
    def from_dict(obj: Any) -> 'CodeModel':
        assert isinstance(obj, dict)
        configurations = from_union([lambda x: from_list(Configuration.from_dict, x), from_none], obj.get("configurations"))
        kind = from_union([from_str, from_none], obj.get("kind"))
        paths = from_union([Paths.from_dict, from_none], obj.get("paths"))
        version = from_union([Version.from_dict, from_none], obj.get("version"))
        return CodeModel(configurations, kind, paths, version)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.configurations is not None:
            result["configurations"] = from_union([lambda x: from_list(lambda x: to_class(Configuration, x), x), from_none], self.configurations)
        if self.kind is not None:
            result["kind"] = from_union([from_str, from_none], self.kind)
        if self.paths is not None:
            result["paths"] = from_union([lambda x: to_class(Paths, x), from_none], self.paths)
        if self.version is not None:
            result["version"] = from_union([lambda x: to_class(Version, x), from_none], self.version)
        return result


def code_model_from_dict(s: Any) -> CodeModel:
    return CodeModel.from_dict(s)


def code_model_to_dict(x: CodeModel) -> Any:
    return to_class(CodeModel, x)
