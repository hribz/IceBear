import os
from subprocess import CompletedProcess, run
import subprocess
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
    TM = auto()

class FileStatus(Enum):
    # Abnormal status
    UNKNOWN = auto()     # File's extname is unknown.
    UNEXIST = auto()     # File does not exist.
    # Normal status
    DELETED = auto()
    UNCHANGED = auto()
    CHANGED = auto()
    NEW = auto()
    DIFF_FAILED = auto() # Fail to get diff info, just consider it as new.     

class DiffResult:
    def __init__(self, file, baseline_file):
        self.file: FileInCDB = file
        self.diff_lines: List = []
        self.baseline_file: FileInCDB = baseline_file
        self.origin_diff_lines: List = []

    def add_diff_line(self, start_line:int, line_count:int):
        self.diff_lines.append([int(start_line), int(line_count)])

    def add_origin_diff_line(self, start_line:int, line_count:int):
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
        return self.InlineChecked != 0 \
                and self.MayInline == 0 \
                and self.TimesInlined == 0 

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
        ret += '}\n'
        return ret

class CallGraph:
    def __init__(self, cg_file_path: str, is_baseline = False):
        self.fname_to_cg_node: Dict[str, CallGraphNode] = {}
        self.is_baseline: bool = is_baseline
        self.functions_need_reanalyzed: set = set()
        self.cg_file_path = cg_file_path

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
        self.cf_num = 'Unknown'
        self.has_cf = False # File has .cf.
        # self.call_graph: CallGraph = None
        self.cg_node_num = 'Skip'
        self.has_cg = False # File has .cg.
        self.rf_num = 'All'
        self.has_rf = False # Propogate reanalyze attribute(if needed) successfully.
        self.basline_fs_num = 'Skip'
        self.baseline_has_fs = False # Analysis finished successfully.
        self.efm: Dict[str, str] = {}
        self.analyze_time = "Unknown"
        self.compile_command: CompileCommand = compile_command
        extname = ''
        if self.compile_command.language == 'c++':
            extname = '.ii'
        elif self.compile_command.language == 'c':
            extname = '.i'
        else:
            logger.error(f"[Create FileInCDB] Encounter unknown extname when parse {self.file_name}")

        if extname:
            self.prep_file: str = str(self.parent.preprocess_path) + self.file_name + extname
            self.diff_file: str = str(self.parent.diff_path) + self.file_name + extname
            self.diff_info_file = str(self.parent.preprocess_path) + self.file_name + '.txt'
        else:
            self.prep_file = None
            self.diff_file = None
            self.diff_info_file = None
            self.status = FileStatus.UNKNOWN
            return
        if not os.path.exists(self.file_name):
            self.status = FileStatus.UNEXIST
            return
        self.baseline_file: FileInCDB = None
        if self.parent.update_mode:
            old_file = self.parent.global_file_dict.get(self.file_name)
            if old_file is not None:
                self.status = FileStatus.UNCHANGED
                self.baseline_file = old_file
                # We don't need old version file before baseline_file,
                # so just deref its baseline_file and let GC collect file version older than it.
                old_file.baseline_file = None
            else:
                logger.debug(f"[FileInCDB Init] Find new file {self.file_name}")
        else:
            if self.parent.baseline != self.parent:
                # Find baseline file.
                self.baseline_file = self.parent.baseline.get_file(self.file_name, False)
                if self.baseline_file:
                    self.status = FileStatus.UNCHANGED
                else:
                    logger.debug(f"[FileInCDB Init] Find new file {self.file_name}")
    
    def is_new(self):
        return self.status == FileStatus.NEW or self.status == FileStatus.DIFF_FAILED

    def is_changed(self):
        return self.status.value >= FileStatus.CHANGED.value

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
        elif kind == FileKind.TM:
            return (self.csa_file) + '.time'
        else:
            logger.error(f"[Get File Path] Unknown file kind {kind}")

    def diff_with_baseline(self) -> bool:
        if self.baseline_file is None:
            # This is a new file.
            with open(self.diff_info_file, 'w') as f:
                f.write("new")
            return True
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
                self.status = FileStatus.UNCHANGED
                return True
            self.status = FileStatus.CHANGED
            # Don't record diff_info anymore, but write them to correspond files.
            with open(self.diff_info_file, 'w') as f:
                f.write(process.stdout)
            # logger.debug(f"[Diff Files Output] \n{process.stdout}")
        else:
            self.status = FileStatus.DIFF_FAILED
            logger.debug("[Diff Files Script] " + diff_script)
            logger.error(f"[Diff Files Failed] stdout: {process.stdout}\n stderr: {process.stderr}")
            return False
        return True
    
    def extract_inc_info(self) -> bool:
        commands = [self.parent.env.EXTRACT_II]
        commands.append(self.prep_file)
        if self.parent.incrementable:
            commands.extend(['-diff', self.diff_info_file])
        if self.parent.env.ctu:
            commands += ['-ctu']
        commands += ['--', '-w'] + self.compile_command.arguments + ['-D__clang_analyzer__']
        ii_script = ' '.join(commands)
        try:
            process = run(ii_script, shell=True, capture_output=True, text=True, check=True)
            logger.info(f"[File Inc Info Success] {ii_script}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"[File Inc Info Failed] {ii_script}\n stdout: {e.stdout}\n stderr: {e.stderr}")
            return False

    def parse_cg_file(self) -> CallGraph:
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
                        call_graph.add_node(caller)
                    else:
                        callee = line
                        call_graph.add_node(caller, callee)
        self.cg_node_num = len(call_graph.fname_to_cg_node.keys())
        return call_graph

    def parse_cf_file(self) -> list:
        cf_file = self.get_file_path(FileKind.CF)
        if not cf_file or not os.path.exists(cf_file):
            logger.error(f"[Parse CF File] It's seems no functions changed, check if {cf_file} exists.")
            return None
        functions_changed = []
        self.has_cf = True
        with open(cf_file, 'r') as f:
            for line in f.readlines():
                line = line.strip()
                functions_changed.append(line)
        self.cf_num = len(functions_changed)
        return functions_changed
    
    def parse_baseline_fs_file(self) -> Dict[str, FunctionSummary]:
        # .fs file format
        # func_name
        # TotalBasicBlocks,InlineChecked,MayInline,TimesInlined
        if self.baseline_file is None:
            return None
        fs_file = self.baseline_file.get_file_path(FileKind.FS)
        if not os.path.exists(fs_file):
            logger.error(f"[Parse FS File] Function Summary file {fs_file} doesn't exist.")
            return None
        function_summaries: Dict = {}
        with open(fs_file, 'r') as f:
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
                is_func = (not is_func)
        self.baseline_has_fs = True
        self.basline_fs_num = len(function_summaries)
        return function_summaries
    
    def output_reanalyzed_functions(self, functions_need_reanalyzed):
        self.rf_num = len(functions_need_reanalyzed)
        rf_path = self.get_file_path(FileKind.RF)
        makedir(os.path.dirname(rf_path))
        with open(rf_path, 'w') as f:
            for fname in functions_need_reanalyzed:
                f.write(fname + '\n')
        self.has_rf = True

    def propagate_reanalyze_attribute_without_fs(self, functions_changed: List[str], call_graph: CallGraph):
        # Without function summary information, we have to mark all caller as reanalyzed.
        # And the terminative rule is cannot find caller anymore, or caller has been mark as reanalyzed.
        for fname in functions_changed:
            # Propagate to all callers
            node_from_cf = call_graph.get_node_if_exist(fname)
            if not node_from_cf:
                logger.error(f"[Propagate Func Reanalyze] Can not found {fname} in call graph")
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
            logger.info(f"[Propagate Func Reanalyze] {self.prep_file} is a new file, just do file-level ica.")
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
        baseline_fs: Dict[FunctionSummary] = self.parse_baseline_fs_file()
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
                logger.error(f"[Propagate Func Reanalyze] Can not found {fname} in {self.get_file_path(FileKind.CG)}")
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
                fs_in_baseline: FunctionSummary = baseline_fs.get(node.fname)
                if fs_in_baseline is not None:
                    if not fs_in_baseline.ok_to_ignore():
                        worklist.extend(node.callers)
                else:
                    # New function node, don't need to consider its inline information.
                    for caller in node.callers:
                        worklist.append(caller)
        # Step 4:Output functions need reanalyze.
        self.output_reanalyzed_functions(call_graph.functions_need_reanalyzed)
        