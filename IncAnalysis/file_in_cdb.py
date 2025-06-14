import hashlib
import os
import subprocess
from enum import Enum, auto
from subprocess import run
from typing import Dict, List, Optional

from IncAnalysis.analyzer_config import *
from IncAnalysis.compile_command import CompileCommand
from IncAnalysis.logger import logger
from IncAnalysis.utils import commands_to_shell_script, makedir, remove_file


def get_sha256_hash(data, encoding="utf-8"):
    sha256 = hashlib.sha256()
    sha256.update(data.encode(encoding))
    return sha256.hexdigest()


class FileKind(Enum):
    Preprocessed = auto()
    DIFF = auto()
    DIFF_INFO = (auto(),)
    AST = auto()
    EFM = auto()
    CG = auto()
    CF = auto()
    INCSUM = auto()
    BASIC = auto()
    RF = auto()
    FS = auto()
    TM = auto()
    FIX = auto()  # clang-tidy fixit file.
    CPPCHECK = auto()
    INFER = auto()
    GCC = auto()
    ANR = auto()
    CPPRF = auto()
    GCCRF = auto()


class FileStatus(Enum):
    # Abnormal status
    UNKNOWN = auto()  # File's extname is unknown.
    UNEXIST = auto()  # File does not exist.
    # Normal status
    DELETED = auto()
    UNCHANGED = auto()
    CHANGED = auto()
    NEW = auto()
    PREPROCESS_FAILED = auto()  # Fail to preprocess file, just consider it as new.
    DIFF_FAILED = auto()  # Fail to get diff info, just consider it as new.

    @staticmethod
    def abnormal_status(status):
        return status == FileStatus.UNKNOWN or status == FileStatus.UNEXIST


class DiffResult:
    def __init__(self, file, baseline_file):
        self.file: FileInCDB = file
        self.diff_lines: List = []
        self.baseline_file: FileInCDB = baseline_file
        self.origin_diff_lines: List = []

    def add_diff_line(self, start_line: int, line_count: int):
        self.diff_lines.append([int(start_line), int(line_count)])

    def add_origin_diff_line(self, start_line: int, line_count: int):
        self.origin_diff_lines.append([int(start_line), int(line_count)])

    def __repr__(self) -> str:
        ret = f"my_file: {self.file.prep_file}\norigin_file: {self.baseline_file.prep_file}\n"
        for idx, line in enumerate(self.diff_lines):
            ret += f"@@ -{self.origin_diff_lines[idx][0]},{self.origin_diff_lines[idx][1]} +{line[0]},{line[1]} @@\n"
        return ret


class FunctionSummary:
    def __init__(self, fs: List[int]) -> None:
        self.TotalBasicBlocks = fs[0]
        self.InlineChecked = fs[1]
        self.MayInline = fs[2]
        self.TimesInlined = fs[3]

    def __repr__(self) -> str:
        return f"[TB:{self.TotalBasicBlocks}, IC:{self.InlineChecked}, MI:{self.MayInline}, TI:{self.TimesInlined}]"

    def ok_to_ignore(self):
        return (
            self.InlineChecked != 0 and self.MayInline == 0 and self.TimesInlined == 0
        )


class CallGraphNode:
    def __init__(self, fname):
        # Function name
        self.fname: str = fname
        self.callers: List[CallGraphNode] = []
        self.callers_set: set = set()
        self.should_reanalyze = False

    def add_caller(self, caller):
        self.callers_set.add(caller.fname)
        self.callers.append(caller)

    def in_callers(self, fname):
        # Maybe there should be a `callers_set` to accelerate this function.
        return fname in self.callers_set

    def __repr__(self) -> str:
        ret = f"{self.fname}" + ":{"
        for caller in self.callers:
            ret += "\t"
            ret += f"{caller.fname}\n"
        ret += "}\n"
        return ret


class CallGraph:
    def __init__(self, cg_file_path: str, is_baseline=False):
        self.fname_to_cg_node: Dict[str, CallGraphNode] = {}
        self.is_baseline: bool = is_baseline
        self.functions_need_reanalyzed: set = set()
        self.cg_file_path = cg_file_path

    def get_node_if_exist(self, fname: str):
        if fname in self.fname_to_cg_node:
            return self.fname_to_cg_node[fname]
        return None

    def get_or_insert_node(self, fname: str) -> CallGraphNode:
        assert fname
        if fname not in self.fname_to_cg_node:
            self.fname_to_cg_node[fname] = CallGraphNode(fname)
        return self.fname_to_cg_node[fname]

    def add_node(self, caller, callee=None):
        caller_node = self.get_or_insert_node(caller)
        if callee:
            callee_node = self.get_or_insert_node(callee)
            callee_node.add_caller(caller_node)

    def mark_as_reanalye(self, node: CallGraphNode):
        node.should_reanalyze = True
        self.functions_need_reanalyzed.add(node.fname)

    def __repr__(self) -> str:
        ret = ""
        for cn in self.fname_to_cg_node.values():
            ret += cn.__repr__()
        return ret


class FileInCDB:
    def __init__(
        self, parent, compile_command: Optional[CompileCommand], cache_file=None
    ):
        if cache_file:
            self.prep_file: str = cache_file
            self.baseline_file = None
            return
        assert compile_command is not None
        # The Configuration instance
        from IncAnalysis.configuration import Configuration

        self.parent: Configuration = parent
        self.file_name: str = compile_command.file
        self.identifier: str = compile_command.identifier
        self.sha256 = get_sha256_hash(self.identifier)
        self.status = FileStatus.NEW
        self.csa_file: str = str(self.parent.csa_path) + self.identifier
        self.compile_command: CompileCommand = compile_command
        self.efm: Dict[str, str] = {}

        # Statistics field.
        self.cf_num = "Unknown"
        self.has_cf = False  # File has .cf.
        # self.call_graph: CallGraph = None
        self.cg_node_num = "Skip"
        self.has_cg = False  # File has .cg.
        self.rf_num = "All"
        self.has_rf = False  # Propagate reanalyze attribute(if needed) successfully.
        self.affected_virtual_functions = 0
        self.affected_vf_indirect_calls = 0
        self.function_pointer_types = 0
        self.affected_fp_indirect_calls = 0
        self.basline_fs_num = "Skip"
        self.baseline_has_fs = False  # Analysis finished successfully.
        self.csa_analyze_time = "Unknown"
        self.analyzers_time = {i: 0.0 for i in self.parent.analyzers_keys}
        self.extname = ""
        if self.compile_command.language == "c++":
            self.extname = ".ii"
        elif self.compile_command.language == "c":
            self.extname = ".i"
        else:
            logger.error(
                f"[Create FileInCDB] Encounter unknown extname when parse {self.file_name}"
            )

        if self.extname:
            self.prep_file = (
                str(self.parent.preprocess_path) + self.identifier + self.extname
            )
        else:
            self.status = FileStatus.UNKNOWN
            return
        if not os.path.exists(self.file_name):
            self.status = FileStatus.UNEXIST
            return
        self.baseline_file: Optional[FileInCDB] = None
        if self.parent.update_mode:
            old_file = self.parent.global_file_dict.get(self.identifier)
            if old_file is not None:
                self.status = FileStatus.UNCHANGED
                self.baseline_file = old_file
                # We don't need old version file before baseline_file,
                # so just deref its baseline_file and let GC collect file version older than it.
                if old_file.baseline_file is not None:
                    old_file.baseline_file.clean_cache()
                old_file.baseline_file = None
            else:
                pass
                # logger.debug(f"[FileInCDB Init] Find new file {self.file_name}")
        else:
            if self.parent.baseline != self.parent:
                # Find baseline file.
                self.baseline_file = self.parent.baseline.get_file(
                    self.identifier, False
                )
                if self.baseline_file:
                    self.status = FileStatus.UNCHANGED
                else:
                    pass
                    # logger.debug(f"[FileInCDB Init] Find new file {self.file_name}")

    def clean_cache(self):
        if hasattr(self, "prep_file"):
            remove_file(self.prep_file)

    def clean_files(self):
        # These files don't need to be cached.
        remove_file(self.get_file_path(FileKind.DIFF_INFO))
        remove_file(self.get_file_path(FileKind.RF))
        remove_file(self.get_file_path(FileKind.CPPRF))
        remove_file(self.get_file_path(FileKind.GCCRF))
        remove_file(self.get_file_path(FileKind.INCSUM))
        remove_file(self.get_file_path(FileKind.ANR))

    def is_new(self):
        return self.status == FileStatus.NEW or self.status == FileStatus.DIFF_FAILED

    def is_changed(self):
        return self.status.value >= FileStatus.CHANGED.value

    def get_baseline_file(self):
        assert self.status != FileStatus.NEW
        return self.baseline_file

    def get_file_path(self, kind: FileKind):
        if kind == FileKind.DIFF:
            return str(self.parent.diff_path) + self.identifier + self.extname
        elif kind == FileKind.DIFF_INFO:
            # Should not rely on the prep_file, because it may change to baseline path.
            return str(self.parent.preprocess_path) + self.identifier + ".txt"
        elif kind == FileKind.AST:
            return (self.csa_file) + ".ast"
        elif kind == FileKind.EFM:
            return (self.csa_file) + ".extdef"
        elif kind == FileKind.FS:
            return (self.csa_file) + ".fs"
        elif kind == FileKind.TM:
            return (self.csa_file) + ".time"
        elif kind == FileKind.FIX:
            return (
                str((self.parent.clang_tidy_output_path))
                + "/"
                + os.path.basename(self.identifier)
                + "_clang-tidy_"
                + self.sha256
                + ".yaml"
            )
        elif kind == FileKind.CPPCHECK:
            # Cppcheck cannot specify output plist file, but the output plist directory.
            return str(self.parent.cppcheck_output_path) + "/" + self.sha256
        elif kind == FileKind.INFER:
            return str(self.parent.infer_output_path) + "/" + self.sha256
        elif kind == FileKind.GCC:
            return str(self.parent.gsa_output_path) + "/" + self.sha256 + ".sarif"
        elif kind == FileKind.CG:
            return (self.prep_file) + ".cg"
        elif kind == FileKind.CF:
            return (self.prep_file) + ".cf"
        elif kind == FileKind.INCSUM:
            return (self.prep_file) + ".ics"
        elif kind == FileKind.BASIC:
            return (self.prep_file) + ".json"
        elif kind == FileKind.RF:
            return (self.prep_file) + ".rf"
        elif kind == FileKind.ANR:
            return (self.prep_file) + ".anr"
        elif kind == FileKind.CPPRF:
            return (self.prep_file) + ".cpprf"
        elif kind == FileKind.GCCRF:
            return (self.prep_file) + ".gccrf"
        else:
            logger.error(f"[Get File Path] Unknown file kind {kind}")
            return ""

    def preprocess_file(self) -> bool:
        commands = [
            (
                self.parent.env.analyze_opts.cc
                if self.compile_command.language == "c"
                else self.parent.env.analyze_opts.cxx
            )
        ]
        commands.extend(self.compile_command.arguments + ["-D__clang_analyzer__"])
        commands.extend(["-E"])
        commands.extend(["-o", f"{self.prep_file}"])
        makedir(os.path.dirname(self.prep_file))

        try:
            logger.debug(f"[Preprocess Script] {commands_to_shell_script(commands)}")
            run(
                commands_to_shell_script(commands),
                capture_output=True,
                text=True,
                check=True,
                shell=True,
                cwd=self.compile_command.directory,
            )
        except subprocess.CalledProcessError as e:
            self.status = FileStatus.PREPROCESS_FAILED
            logger.error(
                f"[Preprocess Failed] {self.prep_file}\nscript:\n{commands_to_shell_script(commands)}\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}"
            )
            return False

        return True

    def diff_with_baseline(self) -> bool:
        if self.baseline_file is None:
            # This is a new file.
            with open(self.get_file_path(FileKind.DIFF_INFO), "w") as f:
                f.write("new")
            return True
        commands = self.parent.env.DIFF_COMMAND.copy()
        if self.parent.env.analyze_opts.udp:
            commands.extend(
                [
                    str(self.baseline_file.get_file_path(FileKind.DIFF)),
                    str(self.get_file_path(FileKind.DIFF)),
                ]
            )
        else:
            commands.extend([str(self.baseline_file.prep_file), str(self.prep_file)])
        diff_script = " ".join(commands)
        # logger.debug("[Diff Files Script] " + diff_script)
        process = run(diff_script, shell=True, capture_output=True, text=True)
        if process.returncode == 0 or process.returncode == 1:
            if process.returncode == 0:
                # There is no change between this file and baseline.
                self.status = FileStatus.UNCHANGED
                return True
            self.status = FileStatus.CHANGED
            # Don't record diff_info anymore, but write them to correspond files.
            with open(self.get_file_path(FileKind.DIFF_INFO), "w") as f:
                f.write(process.stdout)
            # logger.debug(f"[Diff Files Output] \n{process.stdout}")
        else:
            self.status = FileStatus.DIFF_FAILED
            logger.error(
                f"[Diff Files Failed] stdout: {process.stdout}\n stderr: {process.stderr}"
            )
            return False
        return True

    def extract_inc_info(self) -> bool:
        commands = [self.parent.env.EXTRACT_II]
        commands.append(self.prep_file)
        if self.parent.incrementable:
            commands.extend(["-diff", self.get_file_path(FileKind.DIFF_INFO)])
        if self.parent.env.ctu:
            commands += ["-ctu"]
        commands.extend(["-rf-file", self.get_file_path(FileKind.RF)])
        # ClangTidy line-level filter.
        if self.parent.enable_clangtidy:
            commands.extend(["--dump-anr"])
        # Cppcheck function-level incremental.
        if self.parent.enable_cppcheck:
            commands.extend(["-file-path", self.identifier])
            commands.extend(["-cppcheck-rf-file", self.get_file_path(FileKind.CPPRF)])
        # GSA function-level incremental.
        if self.parent.enable_gsa:
            commands.extend(["-gcc-rf-file", self.get_file_path(FileKind.GCCRF)])
        commands += (
            ["--", "-w"] + self.compile_command.arguments + ["-D__clang_analyzer__"]
        )
        ii_script = commands_to_shell_script(commands)
        try:
            run(commands, capture_output=True, text=True, check=True)
            logger.debug(f"[File Inc Info Success] {ii_script}")
            # Parse rf_num to skip some files not need to be reanalyzed.
            self.parse_inc_sum()
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                f"[File Inc Info Failed] {ii_script}\n stdout: {e.stdout}\n stderr: {e.stderr}"
            )
            return False

    def parse_inc_sum(self) -> bool:
        inc_sum_file = self.get_file_path(FileKind.INCSUM)
        if self.status == FileStatus.UNCHANGED:
            return True
        if not os.path.exists(inc_sum_file):
            logger.error(f"[Parse Inc Sum] File {inc_sum_file} doesn't exist.")
            return False
        with open(inc_sum_file, "r") as f:
            for line in f.readlines():
                line = line.strip()
                if not line:
                    break
                if line == "new file":
                    self.has_rf = False
                    break
                tag, val = line.split(":")
                if tag == "changed functions":
                    self.cf_num = int(val)
                elif tag == "reanalyze functions":
                    self.rf_num = int(val)
                    self.has_rf = True
                elif tag == "cg nodes":
                    self.cg_node_num = int(val)
                elif tag == "affected virtual functions":
                    self.affected_virtual_functions = int(val)
                elif tag == "affected vf indirect calls":
                    self.affected_vf_indirect_calls = int(val)
                elif tag == "function pointer types":
                    self.function_pointer_types = int(val)
                elif tag == "affected fp indirect calls":
                    self.affected_fp_indirect_calls = int(val)
        return True

    def extract_basic_info(self) -> bool:
        if not self.parent.env.EXTRACT_BASIC_II:
            # Can not find extract basic info tool.
            return True
        commands = [self.parent.env.EXTRACT_BASIC_II]
        commands.append(self.file_name)
        commands.extend(["-o", self.get_file_path(FileKind.BASIC)])
        commands += (
            ["--", "-w"] + self.compile_command.arguments + ["-D__clang_analyzer__"]
        )
        compiler = self.compile_command.compiler
        commands += [
            "-isystem",
            os.path.join(self.parent.env.system_dir[compiler], "include"),
        ]
        basic_ii_script = commands_to_shell_script(commands)
        try:
            run(
                commands,
                capture_output=True,
                text=True,
                check=True,
                cwd=self.compile_command.directory,
            )
            logger.debug(f"[Basic Info Success] {basic_ii_script}")
            statistics_json = json.load(open(self.get_file_path(FileKind.BASIC), "r"))
            for file, statistics in statistics_json.items():
                if statistics["kind"] == "SYSTEM":
                    # Some times user header will be recognize as system header.
                    # Fix it by checking if the file is in src or build directory.
                    if file.startswith(str(self.parent.src_path)) or file.startswith(
                        str(self.parent.build_path)
                    ):
                        statistics["kind"] = "USER"
            json.dump(statistics_json, open(self.get_file_path(FileKind.BASIC), "w"))
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                f"[Basic Info Failed] {basic_ii_script}\n stdout: {e.stdout}\n stderr: {e.stderr}"
            )
            return False

    def parse_cg_file(self) -> Optional[CallGraph]:
        # .cg file format:
        # caller
        # [
        # callees
        # ]
        cg_file = self.get_file_path(FileKind.CG)
        if not cg_file or not os.path.exists(cg_file):
            # The reason of .cg file doesn't exists maybe the file in compile_commands.json
            # cannot preprocess correctly.
            logger.error(f"[Parse CG File] Callgraph file {cg_file} doesn't exist.")
            return None
        call_graph = CallGraph(cg_file)
        self.has_cg = True
        with open(cg_file, "r") as f:
            caller, callee = None, None
            is_caller = True
            for line in f.readlines():
                line = line.strip()
                if line.startswith("["):
                    is_caller = False
                elif line.startswith("]"):
                    is_caller = True
                else:
                    if is_caller:
                        caller = line
                        call_graph.add_node(caller)
                    else:
                        callee = line
                        call_graph.add_node(caller, callee)
        self.cg_node_num = len(call_graph.fname_to_cg_node.keys())
        return call_graph

    def parse_cf_file(self) -> Optional[list]:
        cf_file = self.get_file_path(FileKind.CF)
        if not cf_file or not os.path.exists(cf_file):
            logger.error(
                f"[Parse CF File] It's seems no functions changed, check if {cf_file} exists."
            )
            return None
        functions_changed = []
        self.has_cf = True
        with open(cf_file, "r") as f:
            for line in f.readlines():
                line = line.strip()
                functions_changed.append(line)
        self.cf_num = len(functions_changed)
        return functions_changed

    def parse_baseline_fs_file(self) -> Optional[Dict[str, FunctionSummary]]:
        # .fs file format
        # func_name
        # TotalBasicBlocks,InlineChecked,MayInline,TimesInlined
        if self.baseline_file is None:
            return None
        fs_file = self.baseline_file.get_file_path(FileKind.FS)
        if fs_file is None or not os.path.exists(fs_file):
            logger.error(
                f"[Parse FS File] Function Summary file {fs_file} doesn't exist."
            )
            return None
        function_summaries: Dict = {}
        with open(fs_file, "r") as f:
            is_func = True
            func_name = None
            for line in f.readlines():
                line: str = line.strip()
                if not line:
                    break
                if is_func:
                    func_name = line
                else:
                    fs = line.split(",")
                    fs = [int(i) for i in fs]
                    function_summaries[func_name] = FunctionSummary(fs)
                is_func = not is_func
        self.baseline_has_fs = True
        self.basline_fs_num = len(function_summaries)
        return function_summaries

    def output_reanalyzed_functions(self, functions_need_reanalyzed):
        self.rf_num = len(functions_need_reanalyzed)
        rf_path = self.get_file_path(FileKind.RF)
        makedir(os.path.dirname(rf_path))
        with open(rf_path, "w") as f:
            for fname in functions_need_reanalyzed:
                f.write(fname + "\n")
        self.has_rf = True

    def propagate_reanalyze_attribute_without_fs(
        self, functions_changed: List[str], call_graph: CallGraph
    ):
        # Without function summary information, we have to mark all caller as reanalyzed.
        # And the terminative rule is cannot find caller anymore, or caller has been mark as reanalyzed.
        for fname in functions_changed:
            # Propagate to all callers
            node_from_cf = call_graph.get_node_if_exist(fname)
            if not node_from_cf:
                logger.error(
                    f"[Propagate Func Reanalyze] Can not found {fname} in call graph"
                )
                continue
            worklist = [node_from_cf]
            while len(worklist) != 0:
                node = worklist.pop()
                if node.should_reanalyze:
                    continue
                call_graph.mark_as_reanalye(node)
                for caller in node.callers:
                    worklist.append(caller)
        self.output_reanalyzed_functions(call_graph.functions_need_reanalyzed)

    def propagate_reanalyze_attribute(self):
        if self.is_new():
            logger.info(
                f"[Propagate Func Reanalyze] {self.prep_file} is a new file, just do file-level ica."
            )
            return

        # Step 1:Parse changed functions file.
        functions_changed = self.parse_cf_file()

        if functions_changed is None:
            return

        if len(functions_changed) == 0:
            self.output_reanalyzed_functions([])
            return

        # Step 2:Parse call graph file.
        call_graph = self.parse_cg_file()
        if call_graph is None:
            return

        if self.parent.env.inc_mode != IncrementalMode.InlineLevel:
            self.propagate_reanalyze_attribute_without_fs(functions_changed, call_graph)
            return

        # Step 3:Parse function summaries.
        baseline_fs: Optional[Dict[str, FunctionSummary]] = (
            self.parse_baseline_fs_file()
        )
        if baseline_fs is None:
            return

        # logger.debug(f"[propagate_reanalyze_attribute] Dump CallGraph\n{self.call_graph.__repr__()}")
        # logger.debug(f"[propagate_reanalyze_attribute] Dump Baseline CG\n{baseline_cg_with_fs.__repr__()}")

        # Make sure function_need_reanalyzed_from_rf sorted by reverse post order.
        # Note: Traverse by reverse post order seem to be not neccessary, `node.should_reanalyze`
        #       will skip
        # There are two more terminative rules when node is in baseline call graph:
        # 1. Caller is in baseline call graph, we just need to traverse upward it if it's
        #    in inline_callers.
        # 2. Caller is not in baseline call graph, which means it is a new function. Because we
        #    traverse `fname` by reverse post order, this kind of callers have been processed before,
        #    it's ok to terminate at these callers.
        for fname in functions_changed:
            node_from_cf = call_graph.get_node_if_exist(fname)
            if not node_from_cf:
                # If the changed function's definition in other translation unit, it may not appear
                # in CallGraph.
                logger.error(
                    f"[Propagate Func Reanalyze] Can not found {fname} in {self.get_file_path(FileKind.CG)}"
                )
                continue
            call_graph.mark_as_reanalye(node_from_cf)
            # For soundness, don't use the two terminative rules on `node_from_cf`'s callers,
            # because changes on `node_from_cf` may affect inline behavior of CSA. We assume
            # that if caller doesn't change, the inline behavior of it will not change.(If
            # inline behavior changes actually, it doesn't influence soundness, beacuse the
            # caller or more high level caller must be changed and mark as reanalyze.)
            # WRONG! CSA's inline strategy consider inline times as criteria, so that inline
            # behavior will change even caller doesn't change.
            worklist = [caller for caller in node_from_cf.callers]
            while len(worklist) != 0:
                node: CallGraphNode = worklist.pop()
                if node.should_reanalyze:
                    continue
                call_graph.mark_as_reanalye(node)
                fs_in_baseline: Optional[FunctionSummary] = baseline_fs.get(node.fname)
                if fs_in_baseline is not None:
                    if not fs_in_baseline.ok_to_ignore():
                        worklist.extend(node.callers)
                else:
                    # New function node, don't need to consider its inline information.
                    for caller in node.callers:
                        worklist.append(caller)
        # Step 4:Output functions need reanalyze.
        self.output_reanalyzed_functions(call_graph.functions_need_reanalyzed)
