import os
from subprocess import CompletedProcess, run
from typing import List, Dict
from enum import Enum, auto

from IncAnalysis.utils import makedir
from IncAnalysis.analyzer_config import *
from IncAnalysis.logger import logger
from IncAnalysis.compile_command import CompileCommand

class FileKind(Enum):
    Preprocessed = auto()
    DIFF = auto()
    AST = auto()
    EFM = auto()
    CG = auto()
    CF = auto()
    RF = auto()
    FS = auto()

class FileStatus(Enum):
    UNKNOWN = auto() # File's extname is unknown.
    UNEXIST = auto() # File does not exist.
    NEW = auto()
    UNCHANGED = auto()
    CHANGED = auto()
    DELETED = auto()

class DiffResult:
    def __init__(self, file, baseline_file):
        self.file: FileInCDB = file
        self.diff_lines: List = []
        self.baseline_file: FileInCDB = baseline_file
        self.origin_diff_lines: List = []

    def add_diff_line(self, start_line:int, line_count:int):
        self.diff_lines.append([start_line, line_count])

    def add_origin_diff_line(self, start_line:int, line_count:int):
        self.origin_diff_lines.append([start_line, line_count])

    def __repr__(self) -> str:
        ret = f"my_file: {self.file.prep_file}\norigin_file: {self.baseline_file.prep_file}\n"
        for idx, line in enumerate(self.diff_lines):
            ret += f"@@ -{self.origin_diff_lines[idx][0]},{self.origin_diff_lines[idx][1]} +{line[0]},{line[1]} @@\n"
        return ret

class CallGraphNode:
    def __init__(self, fname):
        # Function name
        self.fname: str = fname 
        self.callers: List[CallGraphNode] = []
        self.callers_set: set = set()
        # Callers which had inline this function during CSA analysis
        self.inline_callers = set()
        self.is_entry = True
        self.should_reanalyze = False
    
    def add_caller(self, caller):
        self.callers_set.add(caller.fname)
        self.callers.append(caller)

    def add_inline_caller(self, caller_name: str):
        if caller_name:
            self.inline_callers.add(caller_name)

    def in_callers(self, fname):
        # Maybe there should be a `callers_set` to accelerate this function.
        return fname in self.callers_set
    
    def __repr__(self) -> str:
        ret = self.fname + "<-\n"
        ret += '\tcallers: '
        for caller in self.callers:
            ret += f"{caller.fname} "
        ret += '\n\tinline: '
        for inline_caller in self.inline_callers:
            ret += f"{inline_caller} "
        ret += '\n'
        return ret


class CallGraph:
    root: CallGraphNode
    fname_to_cg_node: Dict[str, CallGraphNode]
    is_baseline: bool
    functions_need_reanalyzed: set

    def __init__(self, file, is_baseline = False):
        self.root = CallGraphNode('')
        self.fname_to_cg_node = {}
        self.is_baseline = is_baseline
        self.functions_need_reanalyzed = set()
        self.file = file

    def get_node_if_exist(self, fname:str):
        if fname in self.fname_to_cg_node:
            return self.fname_to_cg_node[fname]
        return None

    def get_or_insert_node(self, fname: str):
        assert fname
        if fname not in self.fname_to_cg_node:
            self.fname_to_cg_node[fname] = CallGraphNode(fname)
        return self.fname_to_cg_node.get(fname)

    def add_node(self, caller, callee=None):
        caller_node = self.get_or_insert_node(caller)
        if callee:
            callee_node = self.get_or_insert_node(callee)
            callee_node.add_caller(caller_node)

    def add_fs_node(self, caller, callee, efm:Dict=None):
        if callee not in self.fname_to_cg_node:
            if efm and callee in efm:
                logger.debug(f"[Add CTU FS Node] {callee} is analyzed by CTU inline")
                other_cg:CallGraph = efm[callee].call_graph
                ctu_callee_node = other_cg.fname_to_cg_node[callee]
                ctu_callee_node.add_inline_caller(caller)
            else:
                logger.error(f"[Add FS Node] {callee} is not in {self.file.get_file_path(FileKind.CG)}")
                return
        callee_node = self.fname_to_cg_node[callee]
        callee_node.add_inline_caller(caller)

    def mark_as_reanalye(self, node: CallGraphNode):
        node.should_reanalyze = True
        self.functions_need_reanalyzed.add(node.fname)

    def __repr__(self) -> str:
        ret = ""
        for cn in self.fname_to_cg_node.values():
            ret += cn.__repr__()
        return ret

class FileInCDB:
    def __init__(self, parent, compile_command: CompileCommand):
        # The Configuration instance
        from IncAnalysis.configuration import Configuration
        self.parent: Configuration = parent
        self.file_name: str = compile_command.file
        self.status = FileStatus.NEW
        self.csa_file: str = str(self.parent.csa_path) + self.file_name
        self.functions_changed: List = None
        self.diff_info: DiffResult = None
        self.call_graph: CallGraph = None
        self.efm: Dict[str, str] = {}
        self.compile_command: CompileCommand = compile_command
        extname = ""
        if self.compile_command.language == 'c++':
            extname = '.ii'
        elif self.compile_command.language == 'c':
            extname = '.i'
        else:
            logger.error(f"[Create FileInCDB] Encounter unknown extname when parse {self.file_name}")

        if extname:
            self.prep_file: str = str(self.parent.preprocess_path) + self.file_name + extname
            self.diff_file: str = str(self.parent.diff_path) + self.file_name + extname
        else:
            self.prep_file = None
            self.diff_file = None
            self.status = FileStatus.UNKNOWN
            return
        if not os.path.exists(self.file_name):
            self.status = FileStatus.UNEXIST
            return
        self.baseline_file: FileInCDB = None
        if self.parent.baseline != self.parent:
            # Find baseline file.
            self.baseline_file = self.parent.baseline.get_file(self.file_name, False)
            if self.baseline_file:
                self.status = FileStatus.UNCHANGED
            else:
                logger.debug(f"[FileInCDB Init] Find new file {self.file_name}")
    
    def is_new(self):
        return self.status == FileStatus.NEW

    def is_changed(self):
        return self.status == FileStatus.CHANGED or self.status == FileStatus.NEW

    def get_baseline_file(self):
        assert self.status != FileStatus.NEW
        return self.baseline_file

    def get_file_path(self, kind: FileKind=None):
        if not kind:
            return self.file_name
        if kind == FileKind.DIFF:
            return (self.diff_file)
        elif kind == FileKind.AST:
            return (self.csa_file) + '.ast'
        elif kind == FileKind.EFM:
            return (self.csa_file) + '.extdef'
        elif kind == FileKind.CG:
            if not self.prep_file:
                return None
            return (self.prep_file) + '.cg'
        elif kind == FileKind.CF:
            if not self.prep_file:
                return None
            return (self.prep_file) + '.cf'
        elif kind == FileKind.RF:
            return (self.csa_file) + '.rf'
        elif kind == FileKind.FS:
            return (self.csa_file) + '.fs'
        else:
            logger.error(f"[Get File Path] Unknown file kind {kind}")

    def diff_with_baseline(self):
        if not self.baseline_file:
            # This is a new file.
            return
        commands = self.parent.env.DIFF_COMMAND.copy()
        if self.parent.env.analyze_opts.udp:
            commands.extend([str(self.baseline_file.diff_file), str(self.diff_file)])
        else:
            commands.extend([str(self.baseline_file.prep_file), str(self.prep_file)])
        diff_script = ' '.join(commands)
        process = run(diff_script, shell=True, capture_output=True, text=True)
        if process.returncode == 0 or process.returncode == 1:
            if process.returncode == 0:
                # There is no change between this file and baseline.
                return
            self.diff_info = DiffResult(self, self.baseline_file)
            self.status = FileStatus.CHANGED
            for line in (process.stdout).split('\n'):
                line: str = line.strip()
                if not line:
                    continue
                # line format: old_begin,old_line_number new_begin,new_line_number
                old_and_new = line.split(' ')
                old_begin, old_line_number = old_and_new[0].split(",")
                new_begin, new_line_number = old_and_new[1].split(",")
                self.diff_info.add_origin_diff_line(old_begin, old_line_number)
                self.diff_info.add_diff_line(new_begin, new_line_number)
            # logger.debug(f"[Diff Files Output] \n{process.stdout}")
        else:
            logger.debug("[Diff Files Script] " + diff_script)
            logger.error(f"[Diff Files Failed] stdout: {process.stdout}\n stderr: {process.stderr}")

    def parse_cg_file(self):
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
            return
        self.call_graph = CallGraph(self)
        with open(cg_file, 'r') as f:
            caller, callee = None, None
            is_caller = True
            for line in f.readlines():
                line = line.strip()
                if line.startswith('['):
                    is_caller = False
                elif line.startswith(']'):
                    is_caller = True
                else:
                    if is_caller:
                        caller = line
                        self.call_graph.add_node(caller)
                    else:
                        callee = line
                        self.call_graph.add_node(caller, callee)

    def parse_cf_file(self):
        cf_file = self.get_file_path(FileKind.CF)
        if not cf_file or not os.path.exists(cf_file):
            return
        self.functions_changed = []
        with open(cf_file, 'r') as f:
            for line in f.readlines():
                line = line.strip()
                self.functions_changed.append(line)
    
    def parse_fs_file(self):
        # .fs file format
        # callee
        # [
        # callers
        # ]
        fs_file = self.get_file_path(FileKind.FS)
        if not os.path.exists(fs_file):
            logger.error(f"[Parse FS File] Function Summary file {fs_file} doesn't exist.")
            return
        with open(fs_file, 'r') as f:
            caller, callee = None, None
            is_caller = False
            for line in f.readlines():
                line = line.strip()
                if line.startswith('['):
                    is_caller = True
                elif line.startswith(']'):
                    is_caller = False
                else:
                    if is_caller:
                        caller = line
                        if self.parent.env.ctu:
                            self.call_graph.add_fs_node(caller, callee, self.parent.global_efm)
                        else:
                            self.call_graph.add_fs_node(caller, callee)
                    else:
                        callee = line

    def propagate_reanalyze_attribute_without_fs(self):
        # Without function summary information, we have to mark all caller as reanalyzed.
        # And the terminative rule is cannot find caller anymore, or caller has been mark as reanalyzed.
        for fname in self.functions_changed:
            # Propagate to all callers
            node_from_cf = self.call_graph.get_node_if_exist(fname)
            if not node_from_cf:
                logger.error(f"[Propagate Func Reanalyze] Can not found {fname} in call graph")
                continue
            worklist = [node_from_cf]
            while len(worklist) != 0:
                node = worklist.pop()
                if node.should_reanalyze:
                    continue
                self.call_graph.mark_as_reanalye(node)
                for caller in node.callers:
                    worklist.append(caller)

    def propagate_reanalyze_attribute(self, baseline_cg_with_fs: CallGraph = None):
        if not self.functions_changed:
            logger.error(f"[Propagate Func Reanalyze] It's seems no functions changed, check if {self.get_file_path(FileKind.CF)} exists.")
            return
        if not baseline_cg_with_fs or self.parent.env.inc_mode != IncrementalMode.InlineLevel:
            self.propagate_reanalyze_attribute_without_fs()
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
        for fname in self.functions_changed:
            node_from_cf = self.call_graph.get_node_if_exist(fname)
            if not node_from_cf:
                # If the changed function's definition in other translation unit, it may not appear
                # in CallGraph.
                logger.error(f"[Propagate Func Reanalyze] Can not found {fname} in {self.get_file_path(FileKind.CG)}")
                continue
            self.call_graph.mark_as_reanalye(node_from_cf)
            # For soundness, don't use two new terminative rules on `node_from_cf`'s callers,
            # because changes on `node_from_cf` may affect inline behavior of CSA. We assume
            # that if caller doesn't change, the inline behavior of it will not change.(If 
            # inline behavior changes actually, it doesn't influence soundness, beacuse the
            # caller or more high level caller must be changed and mark as reanalyze.)
            worklist = [caller for caller in node_from_cf.callers]
            while len(worklist) != 0:
                node: CallGraphNode = worklist.pop()
                if node.should_reanalyze:
                    continue
                self.call_graph.mark_as_reanalye(node)
                node_in_baseline_cg = baseline_cg_with_fs.get_node_if_exist(node.fname)
                if node_in_baseline_cg:
                    for caller in node.callers:
                        if node_in_baseline_cg.in_callers(caller.fname):
                            if caller.fname in node_in_baseline_cg.inline_callers:
                                worklist.append(caller)
                        else:
                            worklist.append(caller)
                else:
                    # New function node, don't need to consider its inline information.
                    for caller in node.callers:
                        worklist.append(caller)
    
    def output_functions_need_reanalyze(self):
        rf_path = self.get_file_path(FileKind.RF)
        makedir(os.path.dirname(rf_path))
        with open(rf_path, 'w') as f:
            for fname in self.call_graph.functions_need_reanalyzed:
                f.write(fname + '\n')