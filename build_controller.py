from pathlib import Path
import subprocess
import shutil
import threading
from typing import List, Dict
from subprocess import CompletedProcess, run
from logger import logger
import json
import argparse
import os
import sys
import re
import time
import multiprocessing as mp
from functools import partial

from data_struct.reply import Reply
from utils import * 
from compile_command import CompileCommand

class Option:
    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value
    
    def __repr__(self) -> str:
        return f"{{'name': {self.name}, 'value': {self.value}}}"
    
    def obj_to_json(self):
        return {"name": self.name, "value": self.value}

class DiffResult:
    def __init__(self, file, entire: bool=False):
        self.file: FileInCDB = file
        self.diff_lines: List = []
        self.origin_file: FileInCDB = None
        self.origin_diff_lines: List = []
        # This is a new file
        self.entire_file: bool = False
        if entire:
            self.entire_file = True

    def add_diff_line(self, start_line:int, line_count:int):
        self.diff_lines.append([start_line, line_count])

    def add_origin_diff_line(self, start_line:int, line_count:int):
        self.origin_diff_lines.append([start_line, line_count])

    def __repr__(self) -> str:
        if self.entire_file:
            return f"Only my_file: {self.file.file_name}\n"
        ret = f"my_file: {self.file.prep_file}\norigin_file: {self.origin_file.prep_file}\n"
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
        self.file: FileInCDB = file

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
    def __init__(self, parent, file_name: str, extname: str = None):
        # The Configuration instance
        self.parent: Configuration = parent
        self.file_name: str = file_name
        self.csa_file: str = str(self.parent.csa_path) + self.file_name
        self.functions_changed: List = None
        self.diff_info: DiffResult = None
        self.call_graph: CallGraph = None
        self.efm: Dict[str, str] = {}
        if extname:
            self.prep_file: str = str(self.parent.preprocess_path) + self.file_name + extname
            self.diff_file: str = str(self.parent.diff_path) + self.file_name + extname
    
    def is_changed(self):
        return self.diff_file is not None

    def get_baseline_file(self):
        assert not self.is_changed()
        return self.parent.baseline.get_file(self.file_name)

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
            return (self.prep_file) + '.cg'
        elif kind == FileKind.CF:
            return (self.prep_file) + '.cf'
        elif kind == FileKind.RF:
            return (self.csa_file) + '.rf'
        elif kind == FileKind.FS:
            return (self.csa_file) + '.fs'
        else:
            logger.error(f"[Get File Path] Unknown file kind {kind}")

    def parse_cg_file(self):
        # .cg file format: 
        # caller
        # [
        # callees
        # ]
        cg_file = self.get_file_path(FileKind.CG)
        if not os.path.exists(cg_file):
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
        if not os.path.exists(cf_file):
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
                        if self.parent.env.analyze_opts.analyze == 'ctu':
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
        if not baseline_cg_with_fs:
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
                logger.error(f"[Propagate Func Reanalyze] Can not found {fname} in call graph")
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
        with open(self.get_file_path(FileKind.RF), 'w') as f:
            for fname in self.call_graph.functions_need_reanalyzed:
                f.write(fname + '\n')

class Configuration:
    env: Environment
    name: str
    options: List[Option]
    args: List[str]
    configure_script: str
    src_path: Path
    build_path: Path
    reply_path: Path
    workspace: Path
    compile_database: Path
    reply_database: List[Reply]
    diff_file_list: List[FileInCDB]
    diff_origin_file_list: List[str]
    incrementable: bool
    session_times: Dict
    # We traverse file_list most of the time, so we don't use dict[str, FileInCDB]
    file_list_index: Dict[str, int]
    file_list: List[FileInCDB]      # Files in workspace

    def __init__(self, name, src_path, env, options: List[Option], args=None, build_path=None):
        self.name = name
        self.src_path = src_path
        self.env = env
        self.update_build_path(build_path)
        self.file_list_index = None
        self.file_list = None
        if args:
            self.args = args
        else:
            self.args = None
        self.create_configure_script(self.env.CMAKE_PATH, options)
        self.reply_database = []
        self.diff_file_list = []
        self.status = 'WAIT'
        self.incrementable = False
        self.session_times = {}
        # Baseline Configuration
        self.baseline: Configuration = self
        self.global_efm: Dict[str, FileInCDB] = None
        if os.path.exists(self.compile_database):
            # If there is compile_commands.json exists, we can prepare file list early.
            # Otherwise, we need execute configure to generate compile_commands.json.
            self.prepare_file_list()

    def create_configure_script(self, cmake_path, options):
        self.options = []
        self.options.append(Option('CMAKE_EXPORT_COMPILE_COMMANDS', '1'))
        self.options.append(Option('CMAKE_BUILD_TYPE', 'Release'))
        self.options.append(Option('CMAKE_C_COMPILER', self.env.CLANG))
        self.options.append(Option('CMAKE_CXX_COMPILER', self.env.CLANG_PLUS_PLUS))
        self.options.extend(options)

        commands = [cmake_path]
        commands.append(str(self.src_path))
        for option in self.options:
            commands.append(f"-D{option.name}={option.value}")
        if self.args:
            commands.extend(self.args)
        self.configure_script = ' '.join(commands)
    
    def update_build_path(self, build_path=None):
        if build_path is None:
            self.build_path = self.src_path / 'build/build_0'
        else:
            tmp_path = Path(build_path)
            if tmp_path.is_absolute():
                self.build_path = tmp_path
            else:
                self.build_path = self.src_path / build_path
        self.cmake_api_path = self.build_path / '.cmake/api/v1'
        self.query_path = self.cmake_api_path / 'query'
        self.reply_path = self.cmake_api_path / 'reply'
        self.compile_database = self.build_path / 'compile_commands.json'
        self.workspace = self.build_path / 'workspace_for_cdb'
        self.preprocess_path = self.workspace / 'preprocess'
        self.compile_commands_used_by_pre = self.preprocess_path / 'compile_commands_used_by_pre.json'
        self.preprocess_compile_database = self.preprocess_path / 'preprocess_compile_commands.json'
        self.preprocess_diff_files_path = self.preprocess_path / 'preprocess_diff_files.txt'
        self.csa_path = self.workspace / 'csa-ctu-scan'
        self.diff_path = self.workspace / 'diff'
        self.inc_info_path = self.workspace / 'inc_info'
        self.diff_files_path = self.workspace / 'diff_files.txt'
        self.diff_lines_path = self.workspace / 'diff_lines.json'
            
    def prepare_file_list(self):
        if not os.path.exists(self.compile_database):
            logger.error(f"[Prepare File List] Please make sure {self.compile_database} exists, may be you should configure first.")
            return
        if self.file_list is not None:
            return
        self.file_list_index = {}
        self.file_list  = []
        with open(self.compile_database, 'r') as f:
            cdb = json.load(f)
            for (idx, ccdb) in enumerate(cdb):
                compile_command = CompileCommand(ccdb)
                if compile_command.language == 'c++':
                    extname = '.ii'
                elif compile_command.language == 'c':
                    extname = '.i'
                else:
                    extname = ''
                self.file_list.append(FileInCDB(self, compile_command.file, extname))
                self.file_list_index[compile_command.file] = idx

    def get_file(self, file_path: str) -> FileInCDB:
        idx = self.file_list_index.get(file_path, None)
        if idx is None:
            logger.error(f"[Get File] {file_path} not exists in file_list_index")
            return None
        return self.file_list[idx]

    def get_file_path(self, kind: FileKind, file_path: str) -> str:
        return self.get_file(file_path).get_file_path(kind)

    def create_cmake_api_file(self):
        if self.cmake_api_path.exists():
            shutil.rmtree(self.cmake_api_path)
        os.makedirs(self.query_path)
        query_list = ['codemodel-v2', 'cache-v2', 'cmakeFiles-v1']
        for query in query_list:
            with open(self.query_path / query, 'w') as f:
                f.write('')

    def configure(self):
        start_time = time.time()
        remake_dir(self.build_path, "[Config Build DIR exists]")
        self.create_cmake_api_file()
        logger.debug("[Repo Config Script] " + self.configure_script)
        try:
            os.chdir(self.build_path)
            process = run(self.configure_script, shell=True, capture_output=True, text=True, check=True)
            logger.info(f"[Repo Config Success] {process.stdout}")
            self.session_times['configure'] = time.time() - start_time
            with open(self.build_path / 'options.json', 'w') as f:
                tmp_json_data = {"options": []}
                for option in self.options:
                    tmp_json_data['options'].append(option.obj_to_json())
                json.dump(tmp_json_data, f, indent=4)
            self.prepare_file_list()
            # self.reply_database.append(Reply(self.reply_path, logger))
        except subprocess.CalledProcessError as e:
            self.session_times['configure'] = SessionStatus.Failed
            logger.error(f"[Repo Config Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def preprocess_repo(self):
        start_time = time.time()
        remake_dir(self.preprocess_path, "[Preprocess Files DIR exists]")

        with open(self.compile_database, 'r') as f:
            json_file = json.load(f)
            for ccdb in json_file:
                if ccdb.get("command"):
                    ccdb["command"] += ' -D__clang_analyzer__ '
                else:
                    ccdb["arguments"].append('-D__clang_analyzer__')
            pre_cdb = open(self.compile_commands_used_by_pre, 'w')
            json.dump(json_file, pre_cdb, indent=4)
            pre_cdb.close()
        plugin_path = self.preprocess_path / 'compile_action.json'
        with open(plugin_path, 'w') as f:
            plugin = self.env.example_compiler_action_plugin.copy()
            plugin['action']['title'] = 'Preprocess Files'
            # '-P' will clean line information in preprocessed files.
            # Error! Line information should not ignored!
            plugin['action']['args'] = ['-E'] 
            plugin['action']['extname'] = ['.i', '.ii']
            json.dump(plugin, f, indent=4)
        commands = self.env.DEFAULT_PANDA_COMMANDS.copy()
        # commands.extend(['--plugin', str(plugin_path)])
        commands.append('-E')
        commands.extend(['-f', str(self.compile_commands_used_by_pre)])
        commands.extend(['-o', str(self.preprocess_path)])
        if self.env.analyze_opts.verbose:
            commands.extend(['--verbose'])
        preprocess_script = ' '.join(commands)
        logger.debug("[Preprocess Files Script] " + preprocess_script)
        try:
            process = run(preprocess_script, shell=True, capture_output=True, text=True, check=True)
            self.status = 'PREPROCESSED'
            self.session_times['preprocess_repo'] = time.time() - start_time
            with open(self.compile_database, 'r') as f:
                json_file = json.load(f)
                for file_command in json_file:
                    compile_command = CompileCommand(file_command)
                    if compile_command.language == 'c++':
                        extname = '.ii'
                    elif compile_command.language == 'c':
                        extname = '.i'
                    else:
                        extname = ''
                    file_command["file"] = str(self.preprocess_path) + compile_command.file + extname
                    # Preprocessed files still need compile options, such as c++ version and so on.
                    # And it's no need to add flags like '-xc++', because clang is able to identify
                    # preprocessed files automatically, unless open the '-P' option. 
                    #
                    # When use CSA analyze the file, macro `__clang_analyzer__` will defined automatically.
                    compile_command.arguments.append('-D__clang_analyzer__')
                    if file_command.get("command"):
                        file_command["command"] = " ".join(compile_command.arguments)
                    else:
                        file_command["arguments"] = compile_command.arguments
                pre_cdb = open(self.preprocess_compile_database, 'w')
                json.dump(json_file, pre_cdb, indent=4)
                pre_cdb.close()
            logger.info(f"[Preprocess Files Success] {preprocess_script}")
            logger.debug(f"[Preprocess Files Success] stdout: {process.stdout}\n stderr: {process.stderr}")
        except subprocess.CalledProcessError as e:
            self.session_times['preprocess_repo'] = SessionStatus.Failed
            logger.error(f"[Preprocess Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
    
    def extract_inc_info(self):
        '''
        use clang_tool/CollectIncInfo.cpp to generate information used by incremental analysis
        '''
        if not self.compile_database.exists():
            logger.error(f"[Extract Inc Info] can't extract inc info without file {self.compile_database}")
            return
        start_time = time.time()
        remake_dir(self.inc_info_path, "[Inc Info Files DIR exists]")
        plugin_path = self.inc_info_path / 'cg_plugin.json'
        with open(plugin_path, 'w') as f:
            plugin = self.env.example_clang_tool_plugin.copy()
            plugin['action']['title'] = 'Extract Inc Info'
            plugin['action']['tool'] = self.env.EXTRACT_II
            plugin['action']['args'] = ['-diff', str(self.diff_lines_path)]
            plugin['action']['extname'] = ""
            plugin['action']['stream'] = ''
            json.dump(plugin, f, indent=4)

        commands = self.env.DEFAULT_PANDA_COMMANDS.copy()
        if self.env.analyze_opts.verbose:
            commands.extend(['--verbose'])
        commands.extend(['--plugin', str(plugin_path)])
        commands.extend(['-f', str(self.preprocess_compile_database)])
        commands.extend(['-o', str(self.inc_info_path)])
        if self.incrementable:
            commands.extend(['--file-list', f"{self.preprocess_diff_files_path}"])
        
        extract_ii_script = ' '.join(commands)
        logger.debug("[Extract Inc Info Script] " + extract_ii_script)
        try:
            process = run(extract_ii_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['extract_inc_info'] = time.time() - start_time
            if self.env.analyze_opts.verbose:
                logger.info(f"[Extract Inc Info Success] {process.stdout} {process.stderr}")
        except subprocess.CalledProcessError as e:
            self.session_times['extract_inc_info'] = SessionStatus.Failed
            logger.error(f"[Extract Inc Info Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def generate_efm(self):
        start_time = time.time()
        # remake_dir(self.csa_path, "[EDM Files DIR exists]")
        commands = self.env.DEFAULT_PANDA_COMMANDS.copy()
        commands.append('--ctu-loading-ast-files') # Prepare CTU analysis for loading AST files.
        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.csa_path)])
        if self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        if self.env.analyze_opts.verbose:
            commands.extend(['--verbose'])
        edm_script = ' '.join(commands)
        logger.debug("[Generating EFM Files Script] " + edm_script)
        try:
            process = run(edm_script, shell=True, capture_output=True, text=True, check=True)
            logger.info(f"[Generating EFM Files Success] {edm_script}")
            self.session_times['generate_efm'] = time.time() - start_time
            if self.env.analyze_opts.verbose:
                logger.debug(f"[Panda EFM Info]\nstdout: \n{process.stdout}\n stderr: \n{process.stderr}")
        except subprocess.CalledProcessError as e:
            self.session_times['generate_efm'] = SessionStatus.Failed
            logger.error(f"[Generating EFM Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
    
    def merge_efm(self):
        start_time = time.time()
        self.global_efm = {}
        if self.incrementable:
            # Combine baseline efm and new efm, reserve `usr`s which not appear in new efm
            # cover `usr`s updated in new efm
            baseline_edm_file = self.baseline.csa_path / 'externalDefMap.txt'
            if not baseline_edm_file.exists():
                logger.error(f"[Generate EFM Files Failed] Please make sure baseline Configuration has generate_efm successfully,\
                             can not find {baseline_edm_file}")
                self.session_times['generate_efm'] = SessionStatus.Failed
                return
            
            def GenerateFinalExternalFunctionMapIncrementally(opts, file_list: List[FileInCDB], origin_edm=None):
                output = os.path.join(str(self.csa_path), 'externalDefMap.txt')
                print('Generating global external function map: ' + output)
                # copy origin efm
                if origin_edm:
                    with open(origin_edm, 'r') as f:
                        for line in f.readlines():
                            usr, path = parse_efm(line)
                            if usr and path:
                                path_file = self.get_file(get_origin_file_name(path, str(self.baseline.csa_path), ['.ast']))
                                if path_file:
                                    self.global_efm[usr] = path_file
                with mp.Pool(opts.jobs) as p:
                    for efmcontent in p.map(getExtDefMap, [i.get_file_path(FileKind.EFM) for i in file_list]):
                        for efmline in efmcontent.split('\n'):
                            usr, path = parse_efm(efmline)
                            if usr and path:
                                path_file = self.get_file(path)
                                if path_file:
                                    self.global_efm[usr] = path_file
                                else:
                                    logger.error(f"[Generate Global EFM] Can't find {path} in compile database!")
                with open(output, 'w') as fout:
                    for usr in self.global_efm:
                        if self.global_efm[usr].is_changed():
                            fout.write('%s %s\n' % (usr, self.global_efm[usr].get_file_path(FileKind.AST)))
                        else:
                            fout.write('%s %s\n' % (usr, self.baseline.get_file(self.global_efm[usr].file_name).get_file_path(FileKind.AST)))

            GenerateFinalExternalFunctionMapIncrementally(self.env.analyze_opts, self.diff_file_list, str(baseline_edm_file))
        else:
            with open(self.csa_path / 'externalDefMap.txt', 'r') as f:
                for line in f.readlines():
                    usr, path = parse_efm(line)
                    if usr and path:
                        self.global_efm[usr] = self.get_file(get_origin_file_name(path, str(self.csa_path), ['.ast']))
        self.session_times['merge_efm'] = time.time() - start_time

    def execute_csa(self):
        start_time = time.time()
        commands = [
            self.env.PANDA, 
            '-j', str(self.env.analyze_opts.jobs), '--print-execution-time',
        ]
        # We need to use revised Clang Static Analyzer to analyze functions incrementally.
        if self.env.analyze_opts.inc:
            commands.extend([
                '--cc', self.env.MY_CLANG,
                '--cxx', self.env.MY_CLANG_PLUS_PLUS
            ])
        else:
            commands.extend([
                '--cc', self.env.CLANG,
                '--cxx', self.env.CLANG_PLUS_PLUS
            ])

        if self.env.analyze_opts.verbose:
            commands.extend(['--verbose'])

        if self.env.analyze_opts.fsum:
            # We need to use revised Clang Static Analyzer to output function summmary.
            args = ['--analyze', '-Xanalyzer', '-analyzer-output=html',
                '-Xanalyzer', '-analyzer-disable-checker=deadcode',
                '-o', str(self.csa_path / 'csa-reports')]
            if self.env.analyze_opts.verbose:
                args.extend(['-Xanalyzer', '-analyzer-display-progress'])
                
            if self.env.analyze_opts.analyze == 'ctu':
                ctuConfigs = [
                    'experimental-enable-naive-ctu-analysis=true',
                    'ctu-dir=' + str(self.csa_path),
                    'ctu-index-name=' + str(self.csa_path / 'externalDefMap.txt'),
                    'ctu-invocation-list=' + str(self.csa_path / 'invocations.yaml')
                ]
                if self.env.analyze_opts.verbose:
                    ctuConfigs.append('display-ctu-progress=true')
                args += ['-Xanalyzer', '-analyzer-config', '-Xanalyzer', ','.join(ctuConfigs)]

            plugin_path = self.csa_path / 'csa_plugin.json'
            with open(plugin_path, 'w') as f:
                plugin = self.env.example_compiler_action_plugin.copy()
                plugin['comment'] = 'Plugin used by IncAnalyzer to execute CSA'
                plugin['action']['title'] = 'Execute CSA'
                plugin['action']['args'] = args
                plugin['action']['extname_inopt'] = '.rf'
                plugin['action']['extname'] = '.fs'
                # Incompatiable with panda, because panda consider this as one parameter.
                # So we need to revise panda to support two parameters.
                plugin['action']['inopt'] = ['-Xanalyzer', '-analyze-function-file=']
                plugin['action']['outopt'] = ['-Xanalyzer', '-analyzer-dump-fsum=']
                json.dump(plugin, f, indent=4)
            commands.extend(['--plugin', str(plugin_path)])
        else:
            # just use panda to execute CSA
            commands.append('--analyze')
            if self.env.analyze_opts.analyze == 'ctu':
                commands.append('ctu')
            else:
                commands.append('no-ctu')

        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.csa_path)])
        
        if self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        csa_script = ' '.join(commands)
        logger.debug("[Executing CSA Files Script] " + csa_script)
        try:
            process = run(csa_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['execute_csa'] = time.time() - start_time
            logger.info(f"[Executing CSA Files Success] {csa_script}")
            if self.env.analyze_opts.verbose:
                logger.debug(f"[Panda Debug Info]\nstdout: \n{process.stdout}\n stderr: \n{process.stderr}")
        except subprocess.CalledProcessError as e:
            # self.session_times['execute_csa'] = SessionStatus.Failed
            # TODO: 由于panda此处可能返回failed，待修复后再储存为FAILED
            self.session_times['execute_csa'] = time.time() - start_time
            logger.error(f"[Executing CSA Files Failed]\nstdout: \n{e.stdout}\n stderr: \n{e.stderr}")
    
    def prepare_diff_dir(self):
        remake_dir(self.diff_path, "[Diff Files DIR exists]")
        with mp.Pool(self.env.analyze_opts.jobs) as p:
            p.map(replace_loc_info, [(file.prep_file, file.diff_file) for file in self.file_list])

    def diff_with_other(self, other):
        # Replace all preprocess location info to empty lines.
        self.prepare_diff_dir()
        if self == other:
            logger.info(f"[Skip Diff] Repo {str(self.build_path)} is the same as {str(other.build_path)}")
            self.session_times['diff_with_other'] = SessionStatus.Skipped
            return
        start_time = time.time()
        self.baseline = other
        if not self.diff_path.exists():
            logger.error(f"Preprocess files DIR {self.diff_path} not exists")
            return
        if not other.diff_path.exists():
            logger.error(f"Preprocess files DIR {other.diff_path} not exists")
            return
        self.diff_two_dir(self.diff_path, other.diff_path, other)
        if self.status == 'DIFF':
            logger.info(f"[Parse Diff Result Success] diff file number: {len(self.diff_file_list)}")
            
            f_diff_files = open(self.diff_files_path, 'w')
            f_prep_diff_files = open(self.preprocess_diff_files_path, 'w')
            f_diff_lines = open(self.diff_lines_path, 'w')
            diff_json = {}

            for diff_file in self.diff_file_list:
                f_diff_files.write(diff_file.file_name + '\n')
                f_prep_diff_files.write(diff_file.prep_file + '\n')
                if diff_file.diff_info.entire_file:
                    diff_json[diff_file.prep_file] = 1
                else:
                    diff_json[diff_file.prep_file] = diff_file.diff_info.diff_lines
            
            json.dump(diff_json, f_diff_lines, indent=4)
            f_diff_files.close()
            f_prep_diff_files.close()
            f_diff_lines.close()

            self.incrementable = self.env.analyze_opts.inc and True
            self.session_times['diff_with_other'] = time.time() - start_time
        else:
            self.session_times['diff_with_other'] = SessionStatus.Failed

    def diff_two_dir(self, my_dir: Path, other_dir: Path, other):
        commands = [self.env.DIFF_PATH]
        commands.extend(['-r', '-u0'])
        # -d: Use the diff algorithm which may find smaller set of change
        # -r: Recursively compare any subdirectories found.
        # -x: Don't compare files or directories matching the given patterns.
        commands.extend(['-d', '--exclude=*.json'])
        commands.extend([str(other_dir), str(my_dir)])
        diff_script = ' '.join(commands)
        logger.debug("[Diff Files Script] " + diff_script)
        self.status = 'DIFF FAILED'
        process = run(diff_script, shell=True, capture_output=True, text=True)
        if process.returncode == 0 or process.returncode == 1:
            self.status = 'DIFF'
            logger.info(f"[Diff Files Success] {diff_script}")
            self.parse_diff_result(process.stdout, other)
            # logger.debug(f"[Diff Files Output] \n{process.stdout}")
        else:
            logger.error(f"[Diff Files Failed] stdout: {process.stdout}\n stderr: {process.stderr}")

    def parse_diff_result(self, diff_out, other):
        diff_line_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$')
        file: str
        file_in_cdb: FileInCDB
        origin_file: str
        my_build_dir_in_diff_path = None
        my_build_dir_in_diff_path = None
        for line in (diff_out).split('\n'):
            line: str
            if line.startswith('@@'):
                if not file_in_cdb:
                    continue
                match = diff_line_pattern.match(line)
                if match:
                    # diff lines range [my_start, my_start + my_count)
                    origin_start = int(match.group(1))
                    origin_count = int(match.group(2)) if match.group(2) else 1
                    start = int(match.group(3))
                    count = int(match.group(4)) if match.group(4) else 1
                    file_in_cdb.diff_info.add_diff_line(start, count)
                    file_in_cdb.diff_info.add_origin_diff_line(origin_start, origin_count)
            elif line.startswith('---'):
                file_in_cdb = None
                spilt_line = line.split()
                origin_file = get_origin_file_name(spilt_line[1], str(other.diff_path), ['.i', '.ii'])
            elif line.startswith('+++'):
                spilt_line = line.split()
                file = spilt_line[1]
                file_in_cdb = self.get_file(get_origin_file_name(file, str(self.diff_path), ['.i', '.ii']))
                if file_in_cdb:
                    self.diff_file_list.append(file_in_cdb)
                    file_in_cdb.diff_info = DiffResult(file_in_cdb)
                    file_in_cdb.diff_info.origin_file = other.get_file(origin_file)
            elif line.startswith("Only in"):
                spilt_line = line.split()
                file_in_cdb = None
                diff = Path(spilt_line[2][:-1]) / spilt_line[3]
                logger.debug(f"[Parse Diff Result Only in] {diff}")
                try:
                    diff.relative_to(self.diff_path)
                    is_my_file_or_dir = True
                except ValueError:
                    is_my_file_or_dir = False
                
                if diff.is_file():
                    # is file
                    if is_my_file_or_dir:
                        # only record new file in my build directory
                        # diff = get_origin_file_name(str(diff), str(self.diff_path), ['.i', '.ii'])
                        file_in_cdb = self.get_file(get_origin_file_name(str(diff), str(self.diff_path), ['.i', '.ii']))
                        if file_in_cdb:
                            file_in_cdb.diff_info = DiffResult(file_in_cdb, True)
                            self.diff_file_list.append(file_in_cdb)
                else:
                    # is directory
                    if is_my_file_or_dir:
                        # diff = /path_to_preprocess/path_to_build0
                        # relative_dir = path_to_build0
                        relative_dir = diff.relative_to(self.diff_path)
                        logger.debug(f"[Parse Diff Result] Find my dir: {diff} relative_dir : {relative_dir} build_path {self.build_path}")
                        if "/" + str(relative_dir) == str(self.build_path):
                            my_build_dir_in_diff_path = str(diff)
                    else:
                        # diff = /path_to_preprocess/path_to_build
                        # relative_dir = path_to_build
                        relative_dir = diff.relative_to(other.diff_path)
                        logger.debug(f"[Parse Diff Result] Find other dir: {diff} relative_dir : {relative_dir} build_path {other.build_path}")
                        if "/" + str(relative_dir) == str(other.build_path):
                            my_build_dir_in_diff_path = str(diff)
                    if my_build_dir_in_diff_path or my_build_dir_in_diff_path:
                        if my_build_dir_in_diff_path and my_build_dir_in_diff_path:
                            # eliminate the impact of different build path
                            logger.debug(f"[Parse Diff Result Recursively] diff build directory {diff} in preprocess path")
                            self.diff_two_dir(my_build_dir_in_diff_path, my_build_dir_in_diff_path, other)
                            my_build_dir_in_diff_path = my_build_dir_in_diff_path = None
                    elif is_my_file_or_dir:
                        logger.debug(f"[Parse Diff Directory] find dir {diff} only in one build path")
                        for diff_file in diff.rglob("*"):
                            if diff_file.is_file():
                                file = str(diff_file)
                                file = get_origin_file_name(str(diff_file), str(self.diff_path), ['.i', '.ii'])
                                file_in_cdb = self.get_file(file)
                                if file_in_cdb:
                                    file_in_cdb.diff_info = DiffResult(file_in_cdb, True)
                                    self.diff_file_list.append(file_in_cdb)

    def process_file_list(self, method):
        file_list = self.diff_file_list \
            if self.incrementable else self.file_list
        # Can't use mutilprocessing, because every process has its own memory space.
        # with mp.Pool(self.env.analyze_opts.jobs) as p:
        #     p.starmap(virtualCall, [(file, method, False) for file in file_list])
        threads = []
        for file in file_list:
            thread = threading.Thread(target=getattr(file, method.__name__))
            thread.start()
            threads.append(thread)
            # getattr(file, method.__name__)()

        for thread in threads:
            thread.join()

    def parse_function_summaries(self):
        self.session_times['parse_function_summaries'] = SessionStatus.Skipped
        if not (self.env.analyze_opts.fsum and self.env.analyze_opts.use_fsum):
            return
        start_time = time.time()
        self.session_times['parse_function_summaries'] = SessionStatus.Failed
        assert (self.file_list is not None)
        self.process_file_list(FileInCDB.parse_fs_file)
        logger.info(f"[Parse Function Summaries] Parse function summaries successfully.")
        self.session_times['parse_function_summaries'] = time.time() - start_time

    def parse_call_graph(self):
        start_time = time.time()
        self.session_times['parse_call_graph'] = SessionStatus.Failed
        assert (self.file_list is not None)
        self.process_file_list(FileInCDB.parse_cg_file)
        logger.info(f"[Parse Call Graph] Parse call graph successfully.")
        self.session_times['parse_call_graph'] = time.time() - start_time

    def parse_functions_changed(self):
        start_time = time.time()
        self.session_times['parse_functions_changed'] = SessionStatus.Failed
        assert (self.file_list is not None)
        self.process_file_list(FileInCDB.parse_cf_file)
        logger.info(f"[Parse Function Changed] Parse function changed successfully.")
        self.session_times['parse_functions_changed'] = time.time() - start_time

    def propagate_reanalyze_attr(self):
        self.session_times['propagate_reanalyze_attr'] = SessionStatus.Skipped
        if not self.incrementable:
            return
        start_time = time.time()
        self.session_times['propagate_reanalyze_attr'] = SessionStatus.Failed
        threads = []
        for file in self.diff_file_list:
            arg = None
            if self.env.analyze_opts.fsum and self.env.analyze_opts.use_fsum:
                # with mp.Pool(self.env.analyze_opts.jobs) as p:
                #     p.starmap(virtualCall, [(file, FileInCDB.propagate_reanalyze_attribute, True, \
                #                                 None if file.diff_info.entire_file \
                #                                 else file.diff_info.origin_file.call_graph \
                #                                 ) for file in file_list])
                arg = None if file.diff_info.entire_file else file.diff_info.origin_file.call_graph
            else:
                # with mp.Pool(self.env.analyze_opts.jobs) as p:
                #     p.starmap(virtualCall, [(file, FileInCDB.propagate_reanalyze_attribute, False) for file in file_list])
                arg = None
            # thread = threading.Thread(target=FileInCDB.propagate_reanalyze_attribute, args=[arg])
            # thread.start()
            # threads.append(thread)
            file.propagate_reanalyze_attribute(arg)
            file.output_functions_need_reanalyze()
        # for thread in threads:
        #     thread.join()

        logger.info(f"[Propagate Reanalyze Attr] Propagate reanalyze attribute successfully.")
        self.session_times['propagate_reanalyze_attr'] = time.time() - start_time

    def get_session_times(self):
        ret = "{\n"
        for session in self.session_times.keys():
            exe_time = self.session_times[session]
            if isinstance(exe_time, SessionStatus):
                ret += ("   %s: %s\n" % (session, exe_time._name_))
            else:
                ret += ("   %s: %.3lf sec\n" % (session, exe_time))
        ret += "}\n"
        return ret
    
    def __repr__(self) -> str:
        ret = f"build path: {self.build_path}\n"
        ret += "OPTIONS:\n"
        for option in self.options:
            ret += f"   {option.name:<40} | {option.value}\n"    
        ret += f"execution time: {self.get_session_times()}\n"
        return ret


class Repository:
    name: str
    src_path: Path
    default_config: Configuration
    configurations: List[Configuration]
    cmakeFile: Path
    running_status: bool # whether the repository sessions should keep running
    env: Environment

    def __init__(self, name, src_path, env: Environment, options_list:List[List[Option]]=None, build_root = None):
        self.name = name
        self.src_path = Path(src_path)
        self.env = env
        self.cmakeFile = self.src_path / 'CMakeLists.txt'
        self.running_status = True
        if not self.cmakeFile.exists():
            print(f'Please make sure there is CMakeLists.txt in {self.src_path}')
            exit(1)
        logger.TAG = self.name
        self.build_root = build_root if build_root is not None else str(self.src_path / 'build')
        self.default_config = Configuration(self.name, self.src_path, self.env, [], build_path=f"{self.build_root}/build_0")
        self.configurations = [self.default_config]
        if options_list:
            for idx, options in enumerate(options_list):
                self.configurations.append(
                    Configuration(self.name, self.src_path, self.env, options, build_path=f'{self.build_root}/build_{idx + 1}')
                )

    def add_configuration(self, options):
        self.configurations.append(
            Configuration(self.name, self.src_path, self.env, options, build_path=f'{self.build_root}/build_{len(self.configurations)}')
        )

    def process_all_session(self):
        self.build_every_config()
        self.preprocess_every_config()
        # if need incremental analyze, please excute diff session after preprocess immediately
        self.diff_every_config()
        self.extract_ii_every_config()
        self.generate_efm_for_every_config()

    def process_one_config(self, config: Configuration):
        # 1. build
        config.configure()
        # 2. preprocess and diff
        config.preprocess_repo()
        config.diff_with_other(self.default_config)
        # 3. extract inc info
        config.extract_inc_info()
        config.parse_call_graph()
        config.parse_functions_changed()
        # 4. prepare for CSA
        config.generate_efm()
        config.merge_efm()
        # 5. execute CSA
        config.propagate_reanalyze_attr()
        config.execute_csa()
        config.parse_function_summaries()

    def process_every_config(self, sessions, **kwargs):
        if not self.running_status:
            return
        for config in self.configurations:
            if isinstance(sessions, list):
                for session in sessions:
                    getattr(config, session.__name__)(**kwargs)
                    if config.session_times[session.__name__] == SessionStatus.Failed:
                        print(f"Session {session.__name__} failed, stop all sessions.")
                        self.running_status = False
                        return
            else:
                getattr(config, sessions.__name__)(**kwargs)
                if config.session_times[sessions.__name__] == SessionStatus.Failed:
                    print(f"Session {sessions.__name__} failed, stop all sessions.")
                    self.running_status = False
                    return


    def build_every_config(self):
        self.process_every_config(Configuration.configure)

    def extract_ii_every_config(self):
        self.process_every_config([
            Configuration.extract_inc_info,
            Configuration.parse_call_graph,
            Configuration.parse_functions_changed
        ])

    def diff_every_config(self):
        self.process_every_config(Configuration.diff_with_other, other=self.default_config)

    def preprocess_every_config(self):
        self.process_every_config(Configuration.preprocess_repo)

    def generate_efm_for_every_config(self):
        self.process_every_config(Configuration.generate_efm)
        self.process_every_config(Configuration.merge_efm)

    def execute_csa_for_every_config(self):
        self.process_every_config([
            Configuration.propagate_reanalyze_attr,
            Configuration.execute_csa,
            Configuration.parse_function_summaries
        ])

    def session_summary(self):
        ret = f"name: {self.name}\nsrc: {self.src_path}\n"
        for config in self.configurations:
            ret += str(config)
        return ret

def main(args):
    parser = ArgumentParser()
    opts = parser.parse_args(args)
    logger.verbose = opts.verbose

    repo_info = [
        # {
        #     'name': 'json', 
        #     'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/json', 
        #     'options_list': [
        #     ]
        # },
        # {
        #     'name': 'xgboost', 
        #     'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/xgboost', 
        #     'options_list': [
        #         [Option('GOOGLE_TEST', 'ON')]
        #     ]
        # },
        # {
        #     'name': 'opencv', 
        #     'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/opencv', 
        #     'options_list': [
        #         [Option('WITH_CLP', 'ON')]
        #     ]
        # },
        {
            'name': 'ica-demo',
            'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/ica-demo',
            'options_list': [
                [Option('CHANGE_ALL', 'ON')],
                # [Option('GLOBAL_CONSTANT', 'ON')],
                # [Option('VIRTUAL_FUNCTION', 'ON')],
                # [Option('RECORD_FIELD', 'ON')],
                # [Option('FEATURE_UPGRADE', 'ON')],
                # [Option('COMMON_CHANGE', 'ON')],
            ]
        }
    ]

    repo_list: List[Repository] = []
    env = Environment(opts)

    for repo in repo_info:
        repo_db = Repository(repo['name'], repo['src_path'], env, options_list=repo['options_list'])
        repo_list.append(repo_db)
        logger.info('-------------BEGIN SUMMARY-------------\n')
        repo_db.build_every_config()
        repo_db.preprocess_every_config()
        repo_db.diff_every_config()
        repo_db.extract_ii_every_config()
        repo_db.generate_efm_for_every_config()
        repo_db.execute_csa_for_every_config()

        # Copy compile_commands.json to build dir for clangd.
        shutil.copy(str(repo_db.default_config.compile_database), str(repo_db.src_path / 'build'))

    for repo_db in repo_list:
        logger.TAG = repo_db.name
        logger.info('---------------END SUMMARY-------------\n'+repo_db.session_summary())

if __name__ == '__main__':
    main(sys.argv[1:])