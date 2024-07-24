from typing import Optional, Any, List, Union, TypeVar, Callable, Type, cast


T = TypeVar("T")


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
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


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


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


class ExportTarget:
    id: Optional[str]
    index: Optional[int]

    def __init__(self, id: Optional[str], index: Optional[int]) -> None:
        self.id = id
        self.index = index

    @staticmethod
    def from_dict(obj: Any) -> 'ExportTarget':
        assert isinstance(obj, dict)
        id = from_union([from_str, from_none], obj.get("id"))
        index = from_union([from_int, from_none], obj.get("index"))
        return ExportTarget(id, index)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.id is not None:
            result["id"] = from_union([from_str, from_none], self.id)
        if self.index is not None:
            result["index"] = from_union([from_int, from_none], self.index)
        return result


class PathClass:
    path_from: Optional[str]
    to: Optional[str]

    def __init__(self, path_from: Optional[str], to: Optional[str]) -> None:
        self.path_from = path_from
        self.to = to

    @staticmethod
    def from_dict(obj: Any) -> 'PathClass':
        assert isinstance(obj, dict)
        path_from = from_union([from_str, from_none], obj.get("from"))
        to = from_union([from_str, from_none], obj.get("to"))
        return PathClass(path_from, to)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.path_from is not None:
            result["from"] = from_union([from_str, from_none], self.path_from)
        if self.to is not None:
            result["to"] = from_union([from_str, from_none], self.to)
        return result


class Installer:
    backtrace: Optional[int]
    component: Optional[str]
    destination: Optional[str]
    paths: Optional[List[Union[PathClass, str]]]
    type: Optional[str]
    export_name: Optional[str]
    export_targets: Optional[List[ExportTarget]]

    def __init__(self, backtrace: Optional[int], component: Optional[str], destination: Optional[str], paths: Optional[List[Union[PathClass, str]]], type: Optional[str], export_name: Optional[str], export_targets: Optional[List[ExportTarget]]) -> None:
        self.backtrace = backtrace
        self.component = component
        self.destination = destination
        self.paths = paths
        self.type = type
        self.export_name = export_name
        self.export_targets = export_targets

    @staticmethod
    def from_dict(obj: Any) -> 'Installer':
        assert isinstance(obj, dict)
        backtrace = from_union([from_int, from_none], obj.get("backtrace"))
        component = from_union([from_str, from_none], obj.get("component"))
        destination = from_union([from_str, from_none], obj.get("destination"))
        paths = from_union([lambda x: from_list(lambda x: from_union([PathClass.from_dict, from_str], x), x), from_none], obj.get("paths"))
        type = from_union([from_str, from_none], obj.get("type"))
        export_name = from_union([from_str, from_none], obj.get("exportName"))
        export_targets = from_union([lambda x: from_list(ExportTarget.from_dict, x), from_none], obj.get("exportTargets"))
        return Installer(backtrace, component, destination, paths, type, export_name, export_targets)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.backtrace is not None:
            result["backtrace"] = from_union([from_int, from_none], self.backtrace)
        if self.component is not None:
            result["component"] = from_union([from_str, from_none], self.component)
        if self.destination is not None:
            result["destination"] = from_union([from_str, from_none], self.destination)
        if self.paths is not None:
            result["paths"] = from_union([lambda x: from_list(lambda x: from_union([lambda x: to_class(PathClass, x), from_str], x), x), from_none], self.paths)
        if self.type is not None:
            result["type"] = from_union([from_str, from_none], self.type)
        if self.export_name is not None:
            result["exportName"] = from_union([from_str, from_none], self.export_name)
        if self.export_targets is not None:
            result["exportTargets"] = from_union([lambda x: from_list(lambda x: to_class(ExportTarget, x), x), from_none], self.export_targets)
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


class Directory:
    backtrace_graph: Optional[BacktraceGraph]
    installers: Optional[List[Installer]]
    paths: Optional[Paths]

    def __init__(self, backtrace_graph: Optional[BacktraceGraph], installers: Optional[List[Installer]], paths: Optional[Paths]) -> None:
        self.backtrace_graph = backtrace_graph
        self.installers = installers
        self.paths = paths

    @staticmethod
    def from_dict(obj: Any) -> 'Directory':
        assert isinstance(obj, dict)
        backtrace_graph = from_union([BacktraceGraph.from_dict, from_none], obj.get("backtraceGraph"))
        installers = from_union([lambda x: from_list(Installer.from_dict, x), from_none], obj.get("installers"))
        paths = from_union([Paths.from_dict, from_none], obj.get("paths"))
        return Directory(backtrace_graph, installers, paths)

    def to_dict(self) -> dict:
        result: dict = {}
        if self.backtrace_graph is not None:
            result["backtraceGraph"] = from_union([lambda x: to_class(BacktraceGraph, x), from_none], self.backtrace_graph)
        if self.installers is not None:
            result["installers"] = from_union([lambda x: from_list(lambda x: to_class(Installer, x), x), from_none], self.installers)
        if self.paths is not None:
            result["paths"] = from_union([lambda x: to_class(Paths, x), from_none], self.paths)
        return result


def directory_from_dict(s: Any) -> Directory:
    return Directory.from_dict(s)


def directory_to_dict(x: Directory) -> Any:
    return to_class(Directory, x)
