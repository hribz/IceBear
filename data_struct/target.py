from typing import Optional, Any, List, TypeVar, Callable, Type, cast
from enum import Enum


T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)


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


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


def to_enum(c: Type[EnumT], x: Any) -> EnumT:
    assert isinstance(x, c)
    return x.value


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


class Artifact:
    path: Optional[str]

    def __init__(self, path: Optional[str]) -> None:
        self.path = path

    @staticmethod
    def from_dict(obj: Any) -> 'Artifact':
        assert isinstance(obj, dict)
        path = from_union([from_str, from_none], obj.get("path"))
        return Artifact(path)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.path is not None:
            result["path"] = from_union([from_str, from_none], self.path)
        return result


class Node:
    file: Optional[int]
    command: Optional[int]
    line: Optional[int]
    parent: Optional[int]

    def __init__(self, file: Optional[int], command: Optional[int], line: Optional[int], parent: Optional[int]) -> None:
        self.file = file
        self.command = command
        self.line = line
        self.parent = parent

    @staticmethod
    def from_dict(obj: Any) -> 'Node':
        assert isinstance(obj, dict)
        file = from_union([from_int, from_none], obj.get("file"))
        command = from_union([from_int, from_none], obj.get("command"))
        line = from_union([from_int, from_none], obj.get("line"))
        parent = from_union([from_int, from_none], obj.get("parent"))
        return Node(file, command, line, parent)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.file is not None:
            result["file"] = from_union([from_int, from_none], self.file)
        if self.command is not None:
            result["command"] = from_union([from_int, from_none], self.command)
        if self.line is not None:
            result["line"] = from_union([from_int, from_none], self.line)
        if self.parent is not None:
            result["parent"] = from_union([from_int, from_none], self.parent)
        return result


class BacktraceGraph:
    commands: Optional[List[str]]
    files: Optional[List[str]]
    nodes: Optional[List[Node]]

    def __init__(self, commands: Optional[List[str]], files: Optional[List[str]], nodes: Optional[List[Node]]) -> None:
        self.commands = commands
        self.files = files
        self.nodes = nodes

    @staticmethod
    def from_dict(obj: Any) -> 'BacktraceGraph':
        assert isinstance(obj, dict)
        commands = from_union([lambda x: from_list(from_str, x), from_none], obj.get("commands"))
        files = from_union([lambda x: from_list(from_str, x), from_none], obj.get("files"))
        nodes = from_union([lambda x: from_list(Node.from_dict, x), from_none], obj.get("nodes"))
        return BacktraceGraph(commands, files, nodes)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.commands is not None:
            result["commands"] = from_union([lambda x: from_list(from_str, x), from_none], self.commands)
        if self.files is not None:
            result["files"] = from_union([lambda x: from_list(from_str, x), from_none], self.files)
        if self.nodes is not None:
            result["nodes"] = from_union([lambda x: from_list(lambda x: to_class(Node, x), x), from_none], self.nodes)
        return result


class CompileCommandFragment:
    fragment: Optional[str]

    def __init__(self, fragment: Optional[str]) -> None:
        self.fragment = fragment

    @staticmethod
    def from_dict(obj: Any) -> 'CompileCommandFragment':
        assert isinstance(obj, dict)
        fragment = from_union([from_str, from_none], obj.get("fragment"))
        return CompileCommandFragment(fragment)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.fragment is not None:
            result["fragment"] = from_union([from_str, from_none], self.fragment)
        return result


class Define:
    define: Optional[str]
    backtrace: Optional[int]

    def __init__(self, define: Optional[str], backtrace: Optional[int]) -> None:
        self.define = define
        self.backtrace = backtrace

    @staticmethod
    def from_dict(obj: Any) -> 'Define':
        assert isinstance(obj, dict)
        define = from_union([from_str, from_none], obj.get("define"))
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        return Define(define, backtrace)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.define is not None:
            result["define"] = from_union([from_str, from_none], self.define)
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        return result


class Destination:
    backtrace: Optional[int]
    path: Optional[str]

    def __init__(self, backtrace: Optional[int], path: Optional[str]) -> None:
        self.backtrace = backtrace
        self.path = path

    @staticmethod
    def from_dict(obj: Any) -> 'Destination':
        assert isinstance(obj, dict)
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        path = from_union([from_str, from_none], obj.get("path"))
        return Destination(backtrace, path)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        if self.path is not None:
            result["path"] = from_union([from_str, from_none], self.path)
        return result


class Language(Enum):
    CXX = "CXX"


class CompileGroup:
    compile_command_fragments: Optional[List[CompileCommandFragment]]
    defines: Optional[List[Define]]
    includes: Optional[List[Destination]]
    language: Optional[Language]
    source_indexes: Optional[List[int]]

    def __init__(self, compile_command_fragments: Optional[List[CompileCommandFragment]], defines: Optional[List[Define]], includes: Optional[List[Destination]], language: Optional[Language], source_indexes: Optional[List[int]]) -> None:
        self.compile_command_fragments = compile_command_fragments
        self.defines = defines
        self.includes = includes
        self.language = language
        self.source_indexes = source_indexes

    @staticmethod
    def from_dict(obj: Any) -> 'CompileGroup':
        assert isinstance(obj, dict)
        compile_command_fragments = from_union([lambda x: from_list(CompileCommandFragment.from_dict, x), from_none], obj.get("compileCommandFragments"))
        defines = from_union([lambda x: from_list(Define.from_dict, x), from_none], obj.get("defines"))
        includes = from_union([lambda x: from_list(Destination.from_dict, x), from_none], obj.get("includes"))
        language = from_union([Language, from_none], obj.get("language"))
        source_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("sourceIndexes"))
        return CompileGroup(compile_command_fragments, defines, includes, language, source_indexes)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.compile_command_fragments is not None:
            result["compileCommandFragments"] = from_union([lambda x: from_list(lambda x: to_class(CompileCommandFragment, x), x), from_none], self.compile_command_fragments)
        if self.defines is not None:
            result["defines"] = from_union([lambda x: from_list(lambda x: to_class(Define, x), x), from_none], self.defines)
        if self.includes is not None:
            result["includes"] = from_union([lambda x: from_list(lambda x: to_class(Destination, x), x), from_none], self.includes)
        if self.language is not None:
            result["language"] = from_union([lambda x: to_enum(Language, x), from_none], self.language)
        if self.source_indexes is not None:
            result["sourceIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.source_indexes)
        return result


class Dependency:
    backtrace: Optional[int]
    id: Optional[str]

    def __init__(self, backtrace: Optional[int], id: Optional[str]) -> None:
        self.backtrace = backtrace
        self.id = id

    @staticmethod
    def from_dict(obj: Any) -> 'Dependency':
        assert isinstance(obj, dict)
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        id = from_union([from_str, from_none], obj.get("id"))
        return Dependency(backtrace, id)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        if self.id is not None:
            result["id"] = from_union([from_str, from_none], self.id)
        return result


class Install:
    destinations: Optional[List[Destination]]
    prefix: Optional[Artifact]

    def __init__(self, destinations: Optional[List[Destination]], prefix: Optional[Artifact]) -> None:
        self.destinations = destinations
        self.prefix = prefix

    @staticmethod
    def from_dict(obj: Any) -> 'Install':
        assert isinstance(obj, dict)
        destinations = from_union([lambda x: from_list(Destination.from_dict, x), from_none], obj.get("destinations"))
        prefix = from_union([Artifact.from_dict, from_none], obj.get("prefix"))
        return Install(destinations, prefix)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.destinations is not None:
            result["destinations"] = from_union([lambda x: from_list(lambda x: to_class(Destination, x), x), from_none], self.destinations)
        if self.prefix is not None:
            result["prefix"] = from_union([lambda x: to_class(Artifact, x), from_none], self.prefix)
        return result


class Role(Enum):
    FLAGS = "flags"
    LIBRARIES = "libraries"


class CommandFragment:
    fragment: Optional[str]
    role: Optional[Role]
    backtrace: Optional[int]

    def __init__(self, fragment: Optional[str], role: Optional[Role], backtrace: Optional[int]) -> None:
        self.fragment = fragment
        self.role = role
        self.backtrace = backtrace

    @staticmethod
    def from_dict(obj: Any) -> 'CommandFragment':
        assert isinstance(obj, dict)
        fragment = from_union([from_str, from_none], obj.get("fragment"))
        role = from_union([Role, from_none], obj.get("role"))
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        return CommandFragment(fragment, role, backtrace)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.fragment is not None:
            result["fragment"] = from_union([from_str, from_none], self.fragment)
        if self.role is not None:
            result["role"] = from_union([lambda x: to_enum(Role, x), from_none], self.role)
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        return result


class Link:
    command_fragments: Optional[List[CommandFragment]]
    language: Optional[Language]

    def __init__(self, command_fragments: Optional[List[CommandFragment]], language: Optional[Language]) -> None:
        self.command_fragments = command_fragments
        self.language = language

    @staticmethod
    def from_dict(obj: Any) -> 'Link':
        assert isinstance(obj, dict)
        command_fragments = from_union([lambda x: from_list(CommandFragment.from_dict, x), from_none], obj.get("commandFragments"))
        language = from_union([Language, from_none], obj.get("language"))
        return Link(command_fragments, language)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.command_fragments is not None:
            result["commandFragments"] = from_union([lambda x: from_list(lambda x: to_class(CommandFragment, x), x), from_none], self.command_fragments)
        if self.language is not None:
            result["language"] = from_union([lambda x: to_enum(Language, x), from_none], self.language)
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


class SourceGroup:
    name: Optional[str]
    source_indexes: Optional[List[int]]

    def __init__(self, name: Optional[str], source_indexes: Optional[List[int]]) -> None:
        self.name = name
        self.source_indexes = source_indexes

    @staticmethod
    def from_dict(obj: Any) -> 'SourceGroup':
        assert isinstance(obj, dict)
        name = from_union([from_str, from_none], obj.get("name"))
        source_indexes = from_union([lambda x: from_list(from_int, x), from_none], obj.get("sourceIndexes"))
        return SourceGroup(name, source_indexes)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        if self.source_indexes is not None:
            result["sourceIndexes"] = from_union([lambda x: from_list(from_int, x), from_none], self.source_indexes)
        return result


class Source:
    backtrace: Optional[int]
    path: Optional[str]
    source_group_index: Optional[int]
    compile_group_index: Optional[int]
    is_generated: Optional[bool]

    def __init__(self, backtrace: Optional[int], path: Optional[str], source_group_index: Optional[int], compile_group_index: Optional[int], is_generated: Optional[bool]) -> None:
        self.backtrace = backtrace
        self.path = path
        self.source_group_index = source_group_index
        self.compile_group_index = compile_group_index
        self.is_generated = is_generated

    @staticmethod
    def from_dict(obj: Any) -> 'Source':
        assert isinstance(obj, dict)
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        path = from_union([from_str, from_none], obj.get("path"))
        source_group_index = from_union([from_int, from_none], obj.get("sourceGroupIndex"))
        compile_group_index = from_union([from_int, from_none], obj.get("compileGroupIndex"))
        is_generated = from_union([from_bool, from_none], obj.get("isGenerated"))
        return Source(backtrace, path, source_group_index, compile_group_index, is_generated)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        if self.path is not None:
            result["path"] = from_union([from_str, from_none], self.path)
        if self.source_group_index is not None:
            result["sourceGroupIndex"] = from_union([from_int, from_none], self.source_group_index)
        if self.compile_group_index is not None:
            result["compileGroupIndex"] = from_union([from_int, from_none], self.compile_group_index)
        if self.is_generated is not None:
            result["isGenerated"] = from_union([from_bool, from_none], self.is_generated)
        return result


class Target:
    artifacts: Optional[List[Artifact]]
    backtrace: Optional[int]
    backtrace_graph: Optional[BacktraceGraph]
    compile_groups: Optional[List[CompileGroup]]
    dependencies: Optional[List[Dependency]]
    id: Optional[str]
    install: Optional[Install]
    link: Optional[Link]
    name: Optional[str]
    name_on_disk: Optional[str]
    paths: Optional[Paths]
    source_groups: Optional[List[SourceGroup]]
    sources: Optional[List[Source]]
    type: Optional[str]

    def __init__(self, artifacts: Optional[List[Artifact]], backtrace: Optional[int], backtrace_graph: Optional[BacktraceGraph], compile_groups: Optional[List[CompileGroup]], dependencies: Optional[List[Dependency]], id: Optional[str], install: Optional[Install], link: Optional[Link], name: Optional[str], name_on_disk: Optional[str], paths: Optional[Paths], source_groups: Optional[List[SourceGroup]], sources: Optional[List[Source]], type: Optional[str]) -> None:
        self.artifacts = artifacts
        self.backtrace = backtrace
        self.backtrace_graph = backtrace_graph
        self.compile_groups = compile_groups
        self.dependencies = dependencies
        self.id = id
        self.install = install
        self.link = link
        self.name = name
        self.name_on_disk = name_on_disk
        self.paths = paths
        self.source_groups = source_groups
        self.sources = sources
        self.type = type

    @staticmethod
    def from_dict(obj: Any) -> 'Target':
        assert isinstance(obj, dict)
        artifacts = from_union([lambda x: from_list(Artifact.from_dict, x), from_none], obj.get("artifacts"))
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        backtrace_graph = from_union([BacktraceGraph.from_dict, from_none], obj.get("backtraceGraph"))
        compile_groups = from_union([lambda x: from_list(CompileGroup.from_dict, x), from_none], obj.get("compileGroups"))
        dependencies = from_union([lambda x: from_list(Dependency.from_dict, x), from_none], obj.get("dependencies"))
        id = from_union([from_str, from_none], obj.get("id"))
        install = from_union([Install.from_dict, from_none], obj.get("install"))
        link = from_union([Link.from_dict, from_none], obj.get("link"))
        name = from_union([from_str, from_none], obj.get("name"))
        name_on_disk = from_union([from_str, from_none], obj.get("nameOnDisk"))
        paths = from_union([Paths.from_dict, from_none], obj.get("paths"))
        source_groups = from_union([lambda x: from_list(SourceGroup.from_dict, x), from_none], obj.get("sourceGroups"))
        sources = from_union([lambda x: from_list(Source.from_dict, x), from_none], obj.get("sources"))
        type = from_union([from_str, from_none], obj.get("type"))
        return Target(artifacts, backtrace, backtrace_graph, compile_groups, dependencies, id, install, link, name, name_on_disk, paths, source_groups, sources, type)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.artifacts is not None:
            result["artifacts"] = from_union([lambda x: from_list(lambda x: to_class(Artifact, x), x), from_none], self.artifacts)
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        if self.backtrace_graph is not None:
            result["backtraceGraph"] = from_union([lambda x: to_class(BacktraceGraph, x), from_none], self.backtrace_graph)
        if self.compile_groups is not None:
            result["compileGroups"] = from_union([lambda x: from_list(lambda x: to_class(CompileGroup, x), x), from_none], self.compile_groups)
        if self.dependencies is not None:
            result["dependencies"] = from_union([lambda x: from_list(lambda x: to_class(Dependency, x), x), from_none], self.dependencies)
        if self.id is not None:
            result["id"] = from_union([from_str, from_none], self.id)
        if self.install is not None:
            result["install"] = from_union([lambda x: to_class(Install, x), from_none], self.install)
        if self.link is not None:
            result["link"] = from_union([lambda x: to_class(Link, x), from_none], self.link)
        if self.name is not None:
            result["name"] = from_union([from_str, from_none], self.name)
        if self.name_on_disk is not None:
            result["nameOnDisk"] = from_union([from_str, from_none], self.name_on_disk)
        if self.paths is not None:
            result["paths"] = from_union([lambda x: to_class(Paths, x), from_none], self.paths)
        if self.source_groups is not None:
            result["sourceGroups"] = from_union([lambda x: from_list(lambda x: to_class(SourceGroup, x), x), from_none], self.source_groups)
        if self.sources is not None:
            result["sources"] = from_union([lambda x: from_list(lambda x: to_class(Source, x), x), from_none], self.sources)
        if self.type is not None:
            result["type"] = from_union([from_str, from_none], self.type)
        return result


def target_from_dict(s: Any) -> Target:
    return Target.from_dict(s)


def target_to_dict(x: Target) -> Any:
    return to_class(Target, x)
