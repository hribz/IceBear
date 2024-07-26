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

PWD = Path(".").absolute()
EXTRACT_CG = str(PWD / 'build/clang_tool/FunctionCallGraph')
PANDA = '/usr/bin/panda'
example_compiler_action_plugin = {
    "comment": "Example plugin for Panda driver.",
    "type": "CompilerAction",
    "action": {
        "title": "Dumping clang cc1 arguments",
        "args": ["-###"],
        "extname": ".d"
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
    other_file: str
    other_diff_lines: List
    entire_file: bool # entire file different

    def __init__(self, file: str, entire: bool=False):
        self.file = file
        self.diff_lines = []
        self.other_diff_lines = []
        if entire:
            self.entire_file = True
        else:
            self.entire_file = False

    def add_diff_line(self, start_line:int, line_count:int):
        self.diff_lines.append([start_line, line_count])

    def add_other_diff_line(self, start_line:int, line_count:int):
        self.other_diff_lines.append([start_line, line_count])

    def __repr__(self) -> str:
        if self.entire_file:
            return f"Only my_file: {self.file}\n"
        ret = f"my_file: {self.file}\nother_file: {self.other_file}\n"
        for idx, line in enumerate(self.diff_lines):
            ret += f"@@ -{line[0]},{line[1]} +{self.other_diff_lines[idx][0]},{self.other_diff_lines[idx][1]} @@\n"
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
    extract_cg: str = EXTRACT_CG
    status: str # {WAIT, SUCCESS, FAILED}
    incrementable: bool

    def __init__(self, name, src_path, options: List[Option], args=None, cmake_path=None, build_path=None):
        self.name = name
        self.src_path = src_path
        self.update_build_path(build_path)
        if args:
            self.args = args
        else:
            self.args = None
        self.options = []
        self.options.append(Option('CMAKE_EXPORT_COMPILE_COMMANDS', '1'))
        self.options.append(Option('CMAKE_BUILD_TYPE', 'Release'))
        self.options.extend(options)
        if cmake_path:
            self.create_configure_script(cmake_path)
        else:
            self.create_configure_script(CMAKE_PATH)
        self.reply_database = []
        self.diff_file_and_lines = []
        self.status = 'WAIT'
        self.incrementable = False
        
    def create_configure_script(self, cmake_path):
        commands = [cmake_path]
        commands.append('..')
        for option in self.options:
            commands.append(f"-D{option.name}={option.value}")
        if self.args:
            commands.extend(self.args)
        self.configure_script = ' '.join(commands)
    
    def update_build_path(self, build_path=None):
        if build_path is None:
            self.build_path = self.src_path / 'build'
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
        self.edm_path = self.workspace / 'csa-ctu-scan'
        self.cg_path = self.workspace / 'call_graph'
        self.diff_files_path = self.workspace / 'diff_files.txt'

    def create_cmake_api_file(self):
        if self.cmake_api_path.exists():
            shutil.rmtree(self.cmake_api_path)
        os.makedirs(self.query_path)
        query_list = ['codemodel-v2', 'cache-v2', 'cmakeFiles-v1']
        for query in query_list:
            with open(self.query_path / query, 'w') as f:
                f.write('')

    def configure(self):
        remake_dir(self.build_path, "[Config Build DIR exists]")
        self.create_cmake_api_file()
        logger.debug("[Repo Config Script] " + self.configure_script)
        try:
            os.chdir(self.build_path)
            process = run(self.configure_script, shell=True, capture_output=True, text=True, check=True)
            logger.info(f"[Repo Config Success] {process.stdout}")
            self.status = 'SUCCESS'
            with open(self.build_path / 'options.json', 'w') as f:
                tmp_json_data = {"options": []}
                for option in self.options:
                    tmp_json_data['options'].append(option.obj_to_json())
                json.dump(tmp_json_data, f, indent=4)
            # self.reply_database.append(Reply(self.reply_path, logger))
        except subprocess.CalledProcessError as e:
            self.status = 'FAILED'
            logger.error(f"[Repo Config Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def extract_call_graph(self, inc:bool=True):
        '''
        use clang_tool/extractCG.cpp to generate call graph
        '''
        if not self.compile_database.exists():
            logger.error(f"[Extract Call Graph] can't extract call graph without file {self.compile_database}")
            return
        remake_dir(self.cg_path, "[Call Graph Files DIR exists]")
        plugin_path = self.cg_path / 'cg_plugin.json'
        with open(plugin_path, 'w') as f:
            plugin = example_clang_tool_plugin
            plugin['action']['title'] = 'Extract Call Graph'
            plugin['action']['tool'] = self.extract_cg
            plugin['action']['args'] = []
            plugin['action']['extname'] = ".cg"
            plugin['action']['stream'] = 'stdout'
            json.dump(plugin, f, indent=4)

        commands = [PANDA]
        commands.extend(['-j', '16', '--print-execution-time', '--verbose'])
        commands.extend(['--plugin', str(plugin_path)])
        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.cg_path)])
        if inc and self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        
        extract_cg_script = ' '.join(commands)
        logger.debug("[Extract CG Script] " + extract_cg_script)
        try:
            process = run(extract_cg_script, shell=True, capture_output=True, text=True, check=True)
            # logger.info(f"[Extract CG Success] {process.stdout} {process.stderr}")
        except subprocess.CalledProcessError as e:
            logger.error(f"[Extract CG Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def generate_edm(self, inc:bool=True):
        remake_dir(self.edm_path, "[EDM Files DIR exists]")
        commands = [PANDA]
        commands.append('-YM')
        commands.extend(['-j', '16', '--print-execution-time'])
        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.edm_path)])
        if inc and self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        edm_script = ' '.join(commands)
        logger.debug("[Generating EDM Files Script] " + edm_script)
        try:
            process = run(edm_script, shell=True, capture_output=True, text=True, check=True)
            logger.info(f"[Generating EDM Files Success] {process.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"[Generating EDM Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")

    def preprocess_repo(self):
        remake_dir(self.preprocess_path, "[Preprocess Files DIR exists]")
        plugin_path = self.preprocess_path / 'compile_action.json'
        with open(plugin_path, 'w') as f:
            plugin = example_compiler_action_plugin
            plugin['action']['title'] = 'Preprocess Files'
            # '-P' will clean line information in preprocessed files 
            plugin['action']['args'] = ['-E', "-P"] 
            plugin['action']['extname'] = ['.i', '.ii']
            json.dump(plugin, f, indent=4)
        commands = [PANDA]
        commands.extend(['-j', '16', '--print-execution-time'])
        # commands.extend(['--cc', 'gcc', '--cxx', 'g++'])
        commands.extend(['--plugin', str(plugin_path)])
        commands.extend(['-f', str(self.compile_database)])
        commands.extend(['-o', str(self.preprocess_path)])
        preprocess_script = ' '.join(commands)
        logger.debug("[Preprocess Files Script] " + preprocess_script)
        try:
            process = run(preprocess_script, shell=True, capture_output=True, text=True, check=True)
            self.status = 'PREPROCESSED'
            logger.info(f"[Preprocess Files Success] {preprocess_script}")
        except subprocess.CalledProcessError as e:
            logger.error(f"[Preprocess Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
    
    def diff_with_other(self, other):
        if not self.preprocess_path.exists():
            logger.error(f"Preprocess files DIR {self.preprocess_path} not exists")
            return
        if not other.preprocess_path.exists():
            logger.error(f"Preprocess files DIR {other.preprocess_path} not exists")
            return
        self.diff_two_dir(self.preprocess_path, other.preprocess_path, other)
        logger.info(f"[Parse Diff Result Success] diff file number: {len(self.diff_file_and_lines)}")
        with open(self.diff_files_path, 'w') as f:
            for i in self.diff_file_and_lines:
                f.write(i.file + "\n")
        self.incrementable = True

    def diff_two_dir(self, my_dir: Path, other_dir: Path, other):
        commands = [DIFF_PATH]
        commands.extend(['-r', '-u0'])
        commands.extend([str(my_dir), str(other_dir)])
        diff_script = ' '.join(commands)
        logger.debug("[Diff Files Script] " + diff_script)
        try:
            process = run(diff_script, shell=True, capture_output=True, text=True, check=True)
            logger.error(f"[Diff Files Failed] stdout: {process.stdout}\n stderr: {process.stderr}")
        except subprocess.CalledProcessError as e:
            # diff return no-zero when success
            self.status = 'DIFF'
            logger.info(f"[Diff Files Success] {diff_script}")
            self.parse_diff_result(e.stdout, other)

    def get_origin_file_name(self, file:str, prefix: List[str], extnames: List[str]):
        file = file[len(prefix):]
        for ext in extnames:
            if file.endswith(ext):
                file = file[:-len(ext)]
                break
        return file

    def parse_diff_result(self, diff_out, other):
        diff_line_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$')
        my_file: str
        other_file: str
        for line in (diff_out).split('\n'):
            line: str
            if line.startswith('@@'):
                match = diff_line_pattern.match(line)
                if match:
                    # diff lines range [my_start, my_start + my_count)
                    my_start = int(match.group(1))
                    my_count = int(match.group(2)) if match.group(2) else 1
                    other_start = int(match.group(3))
                    other_count = int(match.group(4)) if match.group(4) else 1
                    self.diff_file_and_lines[-1].add_diff_line(my_start, my_count)
                    self.diff_file_and_lines[-1].add_other_diff_line(other_start, other_count)
            elif line.startswith('---'):
                spilt_line = line.split()
                my_file = spilt_line[1]
                my_file = self.get_origin_file_name(my_file, str(self.preprocess_path), ['.i', '.ii'])
                self.diff_file_and_lines.append(DiffResult(my_file))
            elif line.startswith('+++'):
                spilt_line = line.split()
                other_file = spilt_line[1]
                self.diff_file_and_lines[-1].other_file = self.get_origin_file_name(other_file, str(other.preprocess_path), ['.i', '.ii'])
            elif line.startswith("Only in"):
                spilt_line = line.split()
                diff = Path(spilt_line[2][:-1]) / spilt_line[3]
                is_my_file_or_dir = diff.is_relative_to(self.preprocess_path)
                logger.debug(f"[Parse Diff Result Only in] {diff}")
                if diff.is_file():
                    # is file
                    if is_my_file_or_dir:
                        # only record new file in my build directory
                        diff = self.get_origin_file_name(str(diff), str(self.preprocess_path), ['.i', '.ii'])
                        self.diff_file_and_lines.append(DiffResult(str(diff), True))
                else:
                    # is directory
                    my_build_dir_in_preprocess_path = None
                    other_build_dir_in_preprocess_path = None
                    if is_my_file_or_dir:
                        relative_dir = diff.relative_to(self.preprocess_path)
                        logger.debug(f"[Parse Diff Result] Find my dir: {diff} relative_dir : {relative_dir} build_path {self.build_path}")
                        if "/" + str(relative_dir) == str(self.build_path):
                            my_build_dir_in_preprocess_path = relative_dir
                    else:
                        relative_dir = diff.relative_to(other.preprocess_path)
                        logger.debug(f"[Parse Diff Result] Find other dir: {diff} relative_dir : {relative_dir} build_path {other.build_path}")
                        if "/" + str(relative_dir) == str(other.build_path):
                            other_build_dir_in_preprocess_path = relative_dir
                    if my_build_dir_in_preprocess_path or other_build_dir_in_preprocess_path:
                            if my_build_dir_in_preprocess_path and other_build_dir_in_preprocess_path:
                                # eliminate the impact of different build path
                                logger.debug(f"[Parse Diff Result Recursively] diff build directory {diff} in preprocess path")
                                my_build_dir_in_preprocess_path = other_build_dir_in_preprocess_path = None
                                self.diff_two_dir(my_build_dir_in_preprocess_path, other_build_dir_in_preprocess_path, other)
                    elif is_my_file_or_dir:
                        logger.debug(f"[Parse Diff Directory] find dir {diff} only in one build path")
                        for diff_file in diff.rglob("*"):
                            if diff_file.is_file():
                                file = self.get_origin_file_name(str(diff_file), str(self.preprocess_path), ['.i', '.ii'])
                                self.diff_file_and_lines.append(DiffResult(file, True))

    def __repr__(self) -> str:
        ret = f"build path: {self.build_path}\n"
        ret += "OPTIONS:\n"
        for option in self.options:
            ret += f"   {option.name:<40} | {option.value}\n"
        if len(self.diff_file_and_lines) > 0:
            ret += "DIFF:\n"
            for diff_res in self.diff_file_and_lines:
                ret += str(diff_res)
        ret += f"status: {self.status}\n"
        return ret 


class Repository:
    name: str
    src_path: Path
    cmake_path: str = CMAKE_PATH
    default_config: Configuration
    configurations: List[Configuration]
    cmakeFile: Path

    def __init__(self, name, src_path, options_list:List[List[Option]]=None, cmake_path=None):
        self.name = name
        self.src_path = Path(src_path)
        self.cmakeFile = self.src_path / 'CMakeLists.txt'
        if not self.cmakeFile.exists():
            print(f'Please make sure there is CMakeLists.txt in {self.src_path}')
            exit(1)
        if cmake_path is not None:
            self.cmake_path = cmake_path
        logger.TAG = self.name
        self.default_config = Configuration(self.name, self.src_path, [])
        self.configurations = [self.default_config]
        if options_list:
            for idx, options in enumerate(options_list):
                self.configurations.append(Configuration(self.name, self.src_path, options, build_path=f'build_{idx}'))

    def process_all_session(self, inc:bool=True):
        self.build_every_config()
        self.preprocess_every_config()
        # if need incremental analyze, please excute diff session after preprocess immediately
        self.diff_every_config()
        self.extract_cg_every_config(inc)
        self.generate_edm_for_every_config(inc)

    def build_every_config(self):
        for config in self.configurations:
            config.configure()

    def extract_cg_every_config(self, inc:bool=True):
        for config in self.configurations:
            config.extract_call_graph(inc)

    def diff_every_config(self):
        for config in self.configurations:
            if config != self.default_config:
                config.diff_with_other(self.default_config)

    def preprocess_every_config(self):
        for config in self.configurations:
            config.preprocess_repo()

    def generate_edm_for_every_config(self, inc:bool=True):
        for config in self.configurations:
            config.generate_edm(inc) 
    
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
    opts = parser.parse_args()

    repo_info = [
        {
            'name': 'json', 
            'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/json', 
            'options_list': [
            ]
        },
        {
            'name': 'opencv', 
            'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/opencv', 
            'options_list': [
                [Option('WITH_CLP', 'ON')]
            ]
        }
    ]

    repo_list: List[Repository] = []

    for repo in repo_info:
        repo_db = Repository(repo['name'], repo['src_path'], options_list=repo['options_list'])
        repo_list.append(repo_db)
        logger.info('-------------BEGIN SUMMARY-------------\n'+repo_db.session_summary())
        # repo_db.build_every_config()
        # repo_db.preprocess_every_config()
        repo_db.diff_every_config()
        repo_db.extract_cg_every_config(opts.inc)
        repo_db.generate_edm_for_every_config(opts.inc)

    for repo_db in repo_list:
        logger.TAG = repo_db.name
        logger.info('---------------END SUMMARY-------------\n'+repo_db.session_summary())

if __name__ == '__main__':
    main()