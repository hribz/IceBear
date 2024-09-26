from pathlib import Path
import subprocess
import shutil
from typing import List, Dict
from subprocess import CompletedProcess, run
from logger import logger
import json
import argparse
import os
import re
import time

from data_struct.reply import Reply
from utils import * 
from compile_command import CompileCommand

PWD = Path(".").absolute()
EXTRACT_II = str(PWD / 'build/clang_tool/collectIncInfo')
PANDA = 'panda'
MY_CLANG = '/home/xiaoyu/llvm/llvm-project/build/bin/clang'
MY_CLANG_PLUS_PLUS = '/home/xiaoyu/llvm/llvm-project/build/bin/clang++'
example_compiler_action_plugin = {
    "comment": "Example plugin for Panda driver.",
    "type": "CompilerAction",
    "action": {
        "title": "Dumping clang cc1 arguments",
        "args": ["-###"],
        "extname": ".d",
        "outopt": None
    }
}
example_clang_tool_plugin = {
    "comment": "Example plugin for Panda driver",
    "type": "ClangToolAction",
    "action": {
        "title": "Executing static analyzer",
        "tool": "clang-check",
        "args": ["-analyze"],
        "extname": ".clang-check",
        "stream": "stderr"
    }
}

LOG_TAG = ''
# 查找cmake命令的位置
CMAKE_PATH = shutil.which('cmake')
if CMAKE_PATH:
    print(f'CMake found at: {CMAKE_PATH}')
else:
    print('CMake not found in the system path')
    exit(1)
DIFF_PATH = shutil.which('diff')
if DIFF_PATH:
    print(f'diff found at: {CMAKE_PATH}')
else:
    print('diff not found in the system path')
    exit(1)
if EXTRACT_II:
    print(f'cg extractor found at: {EXTRACT_II}')
else:
    print('please build cg extractor firstly') 
    exit(1)
if os.path.exists(MY_CLANG):
    print(f'use clang={MY_CLANG}')
else:
    MY_CLANG = shutil.which('clang')
    if not MY_CLANG:
        print('please ensure there is clang in your environment')
        exit(1)
if os.path.exists(MY_CLANG_PLUS_PLUS):
    print(f'use clang++={MY_CLANG_PLUS_PLUS}')
else:
    MY_CLANG = shutil.which('clang++')
    if not MY_CLANG:
        print('please ensure there is clang++ in your environment')
        exit(1)
DEFAULT_PANDA_COMMANDS = [
    PANDA, 
    '-j', '16', '--print-execution-time',
    '--cc', MY_CLANG, 
    '--cxx', MY_CLANG_PLUS_PLUS
]

class Option:
    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value
    
    def __repr__(self) -> str:
        return f"{{'name': {self.name}, 'value': {self.value}}}"
    
    def obj_to_json(self):
        return {"name": self.name, "value": self.value}

class DiffResult:
    file: str
    diff_lines: List
    origin_file: str
    origin_diff_lines: List
    entire_file: bool # entire file different

    def __init__(self, file: str='', entire: bool=False):
        self.file = file
        self.diff_lines = []
        self.origin_diff_lines = []
        if entire:
            self.entire_file = True
        else:
            self.entire_file = False

    def add_diff_line(self, start_line:int, line_count:int):
        self.diff_lines.append([start_line, line_count])

    def add_origin_diff_line(self, start_line:int, line_count:int):
        self.origin_diff_lines.append([start_line, line_count])

    def __repr__(self) -> str:
        if self.entire_file:
            return f"Only my_file: {self.file}\n"
        ret = f"my_file: {self.file}\norigin_file: {self.origin_file}\n"
        for idx, line in enumerate(self.diff_lines):
            ret += f"@@ -{self.origin_diff_lines[idx][0]},{self.origin_diff_lines[idx][1]} +{line[0]},{line[1]} @@\n"
        return ret

class GlobalFunctionSummaries:
    fs: Dict[str, set]

    def __init__(self, fs_file_list: List[str]):
        self.fs = {}
        for fs_file in fs_file_list:
            if not os.path.exists(fs_file):
                logger.error(f"[GFS Init] {fs_file} not exists")
                continue
            with open(fs_file, 'r') as f:
                callers = set()
                fname = ''
                in_callers = False
                for line in f.readlines():
                    if line.startswith('['):
                        callers.clear()
                        in_callers = True
                    elif line.startswith(']'):
                        in_callers = False
                        if fname not in self.fs:
                            self.fs[fname] = callers
                        else:
                            self.fs[fname] = self.fs[fname].union(callers)
                    else:
                        if in_callers:
                            callers.add(line)
                        else:
                            fname = line
                
    def __repr__(self) -> str:
        ret = ""
        for fname, callers in self.fs.items():
            ret += (f'{fname}[\n')
            for caller in callers:
                ret += (f'{caller}')
            ret += (']\n')
        return ret

class FunctionsNeedToBeReanalyzed:
    functions: set

    def __init__(self, fs_file_list: List[str]):
        self.functions = set()
        for fs_file in fs_file_list:
            if not os.path.exists(fs_file):
                continue
            with open(fs_file, 'r') as f:
                for line in f.readlines():
                    self.functions.add(line)

    def __repr__(self) -> str:
        ret = ""
        for fname in self.functions:
            ret += (f'{fname}\n')
        return ret

class Configuration:
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
    diff_file_and_lines: List[DiffResult]
    extract_ii: str = EXTRACT_II
    incrementable: bool
    session_times: dict
    file_list: List[str] # files in workspace
    global_function_summaries: GlobalFunctionSummaries
    functions_need_to_be_reanalyzed: FunctionsNeedToBeReanalyzed

    def __init__(self, name, src_path, options: List[Option], opts, args=None, cmake_path=None, build_path=None):
        self.name = name
        self.analyze_opts = opts
        self.src_path = src_path
        self.update_build_path(build_path)
        self.file_list = None
        if args:
            self.args = args
        else:
            self.args = None
        self.options = []
        self.options.append(Option('CMAKE_EXPORT_COMPILE_COMMANDS', '1'))
        self.options.append(Option('CMAKE_BUILD_TYPE', 'Release'))
        # self.options.append(Option('CMAKE_C_COMPILER', MY_CLANG))
        # self.options.append(Option('CMAKE_CXX_COMPILER', MY_CLANG_PLUS_PLUS))
        self.options.extend(options)
        if cmake_path:
            self.create_configure_script(cmake_path)
        else:
            self.create_configure_script(CMAKE_PATH)
        self.reply_database = []
        self.diff_file_and_lines = []
        self.status = 'WAIT'
        self.incrementable = False
        self.session_times = {}
        
    def create_configure_script(self, cmake_path):
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
        self.preprocess_compile_database = self.preprocess_path / 'preprocess_compile_commands.json'
        self.preprocess_diff_files_path = self.preprocess_path / 'preprocess_diff_files.txt'
        self.edm_path = self.workspace / 'csa-ctu-scan'
        self.csa_path = self.workspace / 'csa-ctu-scan'
        self.inc_info_path = self.workspace / 'inc_info'
        self.diff_files_path = self.workspace / 'diff_files.txt'
        self.diff_lines_path = self.workspace / 'diff_lines.json'

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
            # self.reply_database.append(Reply(self.reply_path, logger))
        except subprocess.CalledProcessError as e:
            self.session_times['configure'] = SessionStatus.Failed
            logger.error(f"[Repo Config Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def get_file_list(self):
        if not os.path.exists(self.compile_database):
            logger.error(f"[Get File List] can't get file list without file {self.compile_database}, make sure configure successfully")
            return
        if self.file_list is not None:
            return
        self.file_list  = []
        with open(self.compile_database, 'r') as f:
            files = json.load(f)
            for file in files:
                file_path = str(self.csa_path) + file['file']
                self.file_list.append(file_path)
    
    def extract_inc_info(self, inc:bool=True):
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
            plugin = example_clang_tool_plugin
            plugin['action']['title'] = 'Extract Inc Info'
            plugin['action']['tool'] = self.extract_ii
            plugin['action']['args'] = ['-diff', str(self.diff_lines_path)]
            plugin['action']['extname'] = ""
            plugin['action']['stream'] = ''
            json.dump(plugin, f, indent=4)

        commands = DEFAULT_PANDA_COMMANDS.copy()
        if self.analyze_opts.verbose:
            commands.extend(['--verbose'])
        commands.extend(['--plugin', str(plugin_path)])
        commands.extend(['-f', str(self.preprocess_compile_database)])
        commands.extend(['-o', str(self.inc_info_path)])
        if inc and self.incrementable:
            commands.extend(['--file-list', f"{self.preprocess_diff_files_path}"])
        
        extract_ii_script = ' '.join(commands)
        logger.debug("[Extract Inc Info Script] " + extract_ii_script)
        try:
            process = run(extract_ii_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['extract_inc_info'] = time.time() - start_time
            if self.incrementable and inc:
                self.generate_functions_need_reanalyzed()
            logger.info(f"[Extract Inc Info Success] {process.stdout} {process.stderr}")
        except subprocess.CalledProcessError as e:
            self.session_times['extract_inc_info'] = SessionStatus.Failed
            logger.error(f"[Extract Inc Info Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def generate_efm(self, inc:bool=True):
        start_time = time.time()
        remake_dir(self.edm_path, "[EDM Files DIR exists]")
        commands = DEFAULT_PANDA_COMMANDS.copy()
        commands.append('-YM')
        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.edm_path)])
        if inc and self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        if self.analyze_opts.verbose:
            commands.extend(['--verbose'])
        edm_script = ' '.join(commands)
        logger.debug("[Generating EFM Files Script] " + edm_script)
        try:
            process = run(edm_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['generate_efm'] = time.time() - start_time
            logger.info(f"[Generating EFM Files Success] {edm_script}")
            if self.analyze_opts.verbose:
                logger.debug(f"[Panda EFM Info]\nstdout: \n{process.stdout}\n stderr: \n{process.stderr}")
        except subprocess.CalledProcessError as e:
            # self.session_times['generate_efm'] = SessionStatus.Failed
            # TODO: 由于panda此处可能返回failed，待修复后再储存为FAILED
            self.session_times['generate_efm'] = time.time() - start_time
            logger.error(f"[Generating EFM Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def execute_csa(self, inc:bool=True):
        start_time = time.time()
        commands = DEFAULT_PANDA_COMMANDS.copy()
        if self.analyze_opts.verbose:
            commands.extend(['--verbose'])

        if self.analyze_opts.fsum:
            args = ['--analyze', '-Xanalyzer', '-analyzer-output=html',
                '-Xanalyzer', '-analyzer-disable-checker=deadcode',
                '-o', str(self.csa_path / 'csa-reports')]
            if self.analyze_opts.verbose:
                args.extend(['-Xanalyzer', '-analyzer-display-progress'])
                
            if self.analyze_opts.analyze == 'ctu':
                ctuConfigs = [
                    'experimental-enable-naive-ctu-analysis=true',
                    'ctu-dir=' + str(self.csa_path),
                    'ctu-index-name=' + str(self.edm_path / 'externalDefMap.txt'),
                    'ctu-invocation-list=' + str(self.edm_path / 'invocations.yaml')
                    ]
                if self.analyze_opts.verbose:
                    ctuConfigs.append('display-ctu-progress=true')
                args += ['-Xanalyzer', '-analyzer-config', '-Xanalyzer', ','.join(ctuConfigs)]

            plugin_path = self.csa_path / 'csa_plugin.json'
            with open(plugin_path, 'w') as f:
                plugin = example_compiler_action_plugin
                plugin['comment'] = 'Plugin used by IncAnalyzer to execute CSA'
                plugin['action']['title'] = 'Execute CSA'
                plugin['action']['args'] = args
                plugin['action']['extname'] = '.fs'
                # incompatiable with panda, because panda consider this as one parameter
                plugin['action']['outopt'] = ['-Xanalyzer', '-analyzer-dump-fsum=']
                json.dump(plugin, f, indent=4)
            commands.extend(['--plugin', str(plugin_path)])
        else:
            # just use panda to execute CSA
            commands.append('--analyze')
            if self.analyze_opts.analyze == 'ctu':
                commands.append('ctu')
            else:
                commands.append('no-ctu')

        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.csa_path)])
        
        if inc and self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        csa_script = ' '.join(commands)
        logger.debug("[Executing CSA Files Script] " + csa_script)
        try:
            process = run(csa_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['execute_csa'] = time.time() - start_time
            logger.info(f"[Executing CSA Files Success] {csa_script}")
            self.generate_global_function_summaries()
            if self.analyze_opts.verbose:
                logger.debug(f"[Panda Debug Info]\nstdout: \n{process.stdout}\n stderr: \n{process.stderr}")
        except subprocess.CalledProcessError as e:
            # self.session_times['execute_csa'] = SessionStatus.Failed
            # TODO: 由于panda此处可能返回failed，待修复后再储存为FAILED
            self.session_times['execute_csa'] = time.time() - start_time
            logger.error(f"[Executing CSA Files Failed]\nstdout: \n{e.stdout}\n stderr: \n{e.stderr}")
        
    def preprocess_repo(self):
        start_time = time.time()
        remake_dir(self.preprocess_path, "[Preprocess Files DIR exists]")
        plugin_path = self.preprocess_path / 'compile_action.json'
        with open(plugin_path, 'w') as f:
            plugin = example_compiler_action_plugin
            plugin['action']['title'] = 'Preprocess Files'
            # '-P' will clean line information in preprocessed files 
            plugin['action']['args'] = ['-E', "-P"] 
            plugin['action']['extname'] = ['.i', '.ii']
            json.dump(plugin, f, indent=4)
        commands = DEFAULT_PANDA_COMMANDS.copy()
        commands.extend(['--plugin', str(plugin_path)])
        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.preprocess_path)])
        if self.analyze_opts.verbose:
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
                    # preprocessed file does not need compile flags
                    if file_command.get("command"):
                        file_command["command"] = compile_command.compiler + " -x " + compile_command.language
                    else:
                        file_command["arguments"] = [compile_command.compiler, "-x" + compile_command.language]
                pre_cdb = open(self.preprocess_compile_database, 'w')
                json.dump(json_file, pre_cdb, indent=4)
                pre_cdb.close()
            logger.info(f"[Preprocess Files Success] {preprocess_script}")
            logger.debug(f"[Preprocess Files Success] stdout: {process.stdout}\n stderr: {process.stderr}")
        except subprocess.CalledProcessError as e:
            self.session_times['preprocess_repo'] = SessionStatus.Failed
            logger.error(f"[Preprocess Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
    
    def diff_with_other(self, other):
        if self == other:
            logger.info(f"[Skip Diff] Repo {str(self.build_path)} is the same as {str(other.build_path)}")
            self.session_times['diff_with_other'] = SessionStatus.Skipped
            return
        start_time = time.time()
        if not self.preprocess_path.exists():
            logger.error(f"Preprocess files DIR {self.preprocess_path} not exists")
            return
        if not other.preprocess_path.exists():
            logger.error(f"Preprocess files DIR {other.preprocess_path} not exists")
            return
        self.diff_two_dir(self.preprocess_path, other.preprocess_path, other)
        if self.status == 'DIFF':
            logger.info(f"[Parse Diff Result Success] diff file number: {len(self.diff_file_and_lines)}")
            with open(self.diff_files_path, 'w') as f:
                for i in self.diff_file_and_lines:
                    f.write(self.get_origin_file_name(i.file, str(self.preprocess_path), ['.i', '.ii']) + '\n')
            with open(self.preprocess_diff_files_path, 'w') as f:
                for i in self.diff_file_and_lines:
                    f.write(i.file + '\n')
            with open(self.diff_lines_path, 'w') as f:
                diff_json = {}
                for i in self.diff_file_and_lines:
                    if i.entire_file:
                        diff_json[i.file] = 1
                    else:
                        diff_json[i.file] = i.diff_lines
                json.dump(diff_json, f, indent=4)
            self.incrementable = True
            self.session_times['diff_with_other'] = time.time() - start_time
        else:
            self.session_times['diff_with_other'] = SessionStatus.Failed

    def diff_two_dir(self, my_dir: Path, other_dir: Path, other):
        commands = [DIFF_PATH]
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

    def get_origin_file_name(self, file:str, prefix: List[str], extnames: List[str]):
        file = file[len(prefix):]
        for ext in extnames:
            if file.endswith(ext):
                file = file[:-len(ext)]
                break
        return file

    def parse_diff_result(self, diff_out, other):
        diff_line_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$')
        file: str
        origin_file: str
        my_build_dir_in_preprocess_path = None
        other_build_dir_in_preprocess_path = None
        for line in (diff_out).split('\n'):
            line: str
            if line.startswith('@@'):
                match = diff_line_pattern.match(line)
                if match:
                    # diff lines range [my_start, my_start + my_count)
                    origin_start = int(match.group(1))
                    origin_count = int(match.group(2)) if match.group(2) else 1
                    start = int(match.group(3))
                    count = int(match.group(4)) if match.group(4) else 1
                    self.diff_file_and_lines[-1].add_diff_line(start, count)
                    self.diff_file_and_lines[-1].add_origin_diff_line(origin_start, origin_count)
            elif line.startswith('---'):
                spilt_line = line.split()
                origin_file = spilt_line[1]
                # origin_file = self.get_origin_file_name(origin_file, str(other.preprocess_path), ['.i', '.ii'])
                self.diff_file_and_lines.append(DiffResult())
                self.diff_file_and_lines[-1].origin_file = origin_file
            elif line.startswith('+++'):
                spilt_line = line.split()
                file = spilt_line[1]
                # file = self.get_origin_file_name(file, str(self.preprocess_path), ['.i', '.ii'])
                self.diff_file_and_lines[-1].file = file
            elif line.startswith("Only in"):
                spilt_line = line.split()
                diff = Path(spilt_line[2][:-1]) / spilt_line[3]
                logger.debug(f"[Parse Diff Result Only in] {diff}")
                try:
                    diff.relative_to(self.preprocess_path)
                    is_my_file_or_dir = True
                except ValueError:
                    is_my_file_or_dir = False
                
                if diff.is_file():
                    # is file
                    if is_my_file_or_dir:
                        # only record new file in my build directory
                        # diff = self.get_origin_file_name(str(diff), str(self.preprocess_path), ['.i', '.ii'])
                        self.diff_file_and_lines.append(DiffResult(str(diff), True))
                else:
                    # is directory
                    if is_my_file_or_dir:
                        # diff = /path_to_preprocess/path_to_build0
                        # relative_dir = path_to_build0
                        relative_dir = diff.relative_to(self.preprocess_path)
                        logger.debug(f"[Parse Diff Result] Find my dir: {diff} relative_dir : {relative_dir} build_path {self.build_path}")
                        if "/" + str(relative_dir) == str(self.build_path):
                            my_build_dir_in_preprocess_path = str(diff)
                    else:
                        # diff = /path_to_preprocess/path_to_build
                        # relative_dir = path_to_build
                        relative_dir = diff.relative_to(other.preprocess_path)
                        logger.debug(f"[Parse Diff Result] Find other dir: {diff} relative_dir : {relative_dir} build_path {other.build_path}")
                        if "/" + str(relative_dir) == str(other.build_path):
                            other_build_dir_in_preprocess_path = str(diff)
                    if my_build_dir_in_preprocess_path or other_build_dir_in_preprocess_path:
                        if my_build_dir_in_preprocess_path and other_build_dir_in_preprocess_path:
                            # eliminate the impact of different build path
                            logger.debug(f"[Parse Diff Result Recursively] diff build directory {diff} in preprocess path")
                            self.diff_two_dir(my_build_dir_in_preprocess_path, other_build_dir_in_preprocess_path, other)
                            my_build_dir_in_preprocess_path = other_build_dir_in_preprocess_path = None
                    elif is_my_file_or_dir:
                        logger.debug(f"[Parse Diff Directory] find dir {diff} only in one build path")
                        for diff_file in diff.rglob("*"):
                            if diff_file.is_file():
                                file = str(diff_file)
                                # file = self.get_origin_file_name(str(diff_file), str(self.preprocess_path), ['.i', '.ii'])
                                self.diff_file_and_lines.append(DiffResult(file, True))

    def generate_global_function_summaries(self):
        start_time = time.time()
        self.session_times['generate_global_function_summaries'] = SessionStatus.Failed
        self.get_file_list()
        assert (self.file_list is not None)
        file_list = [(i + '.fs') for i in self.file_list]
        self.global_function_summaries = GlobalFunctionSummaries(file_list)
        with open(str(self.csa_path / "global_function_summaries.fs"), 'w') as f:
            f.write(self.global_function_summaries.__repr__())
        self.session_times['generate_global_function_summaries'] = time.time() - start_time

    def generate_functions_need_reanalyzed(self):
        self.get_file_list()
        assert (self.file_list is not None)
        file_list = [(i + '.rf') for i in self.file_list]
        self.functions_need_reanalyzed = FunctionsNeedToBeReanalyzed(file_list)
        with open(str(self.inc_info_path / "functions_need_reanalyzed.rf"), 'w') as f:
            f.write(self.functions_need_reanalyzed.__repr__())

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
        if len(self.diff_file_and_lines) > 0:
            ret += "DIFF:\n"
            for diff_res in self.diff_file_and_lines:
                ret += str(diff_res)
        ret += f"execution time: {self.get_session_times()}\n"
        return ret


class Repository:
    name: str
    src_path: Path
    cmake_path: str = CMAKE_PATH
    default_config: Configuration
    configurations: List[Configuration]
    cmakeFile: Path
    running_status: bool # whether the repository sessions should keep running

    def __init__(self, name, src_path, opts, options_list:List[List[Option]]=None, cmake_path=None):
        self.name = name
        self.analyze_opts = opts
        self.src_path = Path(src_path)
        self.cmakeFile = self.src_path / 'CMakeLists.txt'
        self.running_status = True
        if not self.cmakeFile.exists():
            print(f'Please make sure there is CMakeLists.txt in {self.src_path}')
            exit(1)
        if cmake_path is not None:
            self.cmake_path = cmake_path
        logger.TAG = self.name
        self.default_config = Configuration(self.name, self.src_path, [], opts=self.analyze_opts)
        self.configurations = [self.default_config]
        if options_list:
            for idx, options in enumerate(options_list):
                self.configurations.append(Configuration(self.name, self.src_path, options, build_path=f'build/build_{idx + 1}', opts=self.analyze_opts))

    def process_all_session(self, inc:bool=True):
        self.build_every_config()
        self.preprocess_every_config()
        # if need incremental analyze, please excute diff session after preprocess immediately
        self.diff_every_config()
        self.extract_ii_every_config(inc)
        self.generate_efm_for_every_config(inc)

    def is_incremental_session(self, session):
        incremental_sessions = [Configuration.extract_inc_info, Configuration.generate_efm, Configuration.execute_csa]
        if session in incremental_sessions:
            return True
        return False

    def process_every_config(self, session, inc:bool=True, **kwargs):
        if not self.running_status:
            return
        for config in self.configurations:
            if self.is_incremental_session(session):
                getattr(config, session.__name__)(inc, **kwargs)
            else:
                getattr(config, session.__name__)(**kwargs)
            if config.session_times[session.__name__] == SessionStatus.Failed:
                print(f"Session {session.__name__} failed, stop all sessions.")
                self.running_status = False
                return

    def build_every_config(self):
        self.process_every_config(Configuration.configure)

    def extract_ii_every_config(self):
        self.process_every_config(Configuration.extract_inc_info, inc=self.analyze_opts.inc)

    def diff_every_config(self):
        self.process_every_config(Configuration.diff_with_other, other=self.default_config)

    def preprocess_every_config(self):
        self.process_every_config(Configuration.preprocess_repo)

    def generate_efm_for_every_config(self):
        self.process_every_config(Configuration.generate_efm, inc=self.analyze_opts.inc)

    def execute_csa_for_every_config(self):
        self.process_every_config(Configuration.execute_csa, inc=self.analyze_opts.inc)
    
    def generate_global_fsum(self):
        self.process_every_config(Configuration.generate_global_function_summaries)
    
    def session_summary(self):
        ret = f"name: {self.name}\nsrc: {self.src_path}\n"
        for config in self.configurations:
            ret += str(config)
        return ret

def main():
    parser = argparse.ArgumentParser(prog='IncAnalyzer', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-d', '--dir', default='.', help="Path of Source Files")
    parser.add_argument('-b', '--build', default='./build', help='Path of Build Directory')
    parser.add_argument('-n', '--name', help='name of the project')
    parser.add_argument('--inc', action='store_true', dest='inc', help='Incremental analyze all sessions.')
    parser.add_argument('--verbose', action='store_true', dest='verbose', help='Record debug information.')
    parser.add_argument('--analyze', type=str, dest='analyze', choices=['ctu', 'no-ctu'],
            help='Execute Clang Static Analyzer.')
    parser.add_argument('--fsum', action='store_true', dest='fsum', help='Generate function summary files.')
    opts = parser.parse_args()
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

    for repo in repo_info:
        repo_db = Repository(repo['name'], repo['src_path'], options_list=repo['options_list'], opts=opts)
        repo_list.append(repo_db)
        logger.info('-------------BEGIN SUMMARY-------------\n')
        repo_db.build_every_config()
        repo_db.preprocess_every_config()
        repo_db.diff_every_config()
        repo_db.extract_ii_every_config()
        repo_db.generate_efm_for_every_config()
        repo_db.execute_csa_for_every_config()
        repo_db.generate_global_fsum()

    for repo_db in repo_list:
        logger.TAG = repo_db.name
        logger.info('---------------END SUMMARY-------------\n'+repo_db.session_summary())

if __name__ == '__main__':
    main()