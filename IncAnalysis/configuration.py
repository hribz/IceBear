from pathlib import Path
import subprocess
import shutil
import threading
from typing import List, Dict
from subprocess import CompletedProcess, run
import json
import argparse
import os
import sys
import re
import time
import multiprocessing as mp
from functools import partial

from IncAnalysis.logger import logger
from IncAnalysis.utils import * 
from IncAnalysis.analyzer_config import *
from IncAnalysis.environment import *
from IncAnalysis.compile_command import CompileCommand
from IncAnalysis.file_in_cdb import *
from IncAnalysis.analyzer import *

class Option:
    def __init__(self, cmd: str):
        split_cmd = cmd.split('=')
        self.name = split_cmd[0]
        self.value = None
        if len(split_cmd) == 2:
            self.value = split_cmd[1]
    
    def __repr__(self) -> str:
        return f"{{'name': {self.name}, 'value': {self.value}}}" if self.value is not None else f"{{'name': {self.name}}}"
    
    def obj_to_json(self):
        return {"name": self.name, "value": self.value} if self.value is not None else {"name": self.name}

    def origin_cmd(self):
        return f"{self.name}={self.value}" if self.value is not None else f"{self.name}"

class BuildType(Enum):
    MAKE = auto()
    CMAKE = auto()
    CONFIGURE = auto()
    KBUILD = auto()
    UNKNOWN = auto()

    @staticmethod
    def getType(build_type: str):
        if build_type == 'cmake':
            return BuildType.CMAKE
        elif build_type == 'configure':
            return BuildType.CONFIGURE
        elif build_type == 'kbuild':
            return BuildType.KBUILD
        elif build_type == 'make':
            return BuildType.MAKE
        else:
            return BuildType.UNKNOWN

class BuildInfo:
    def __init__(self, src_path, build_path, build_type: BuildType, options: List[str], env: Environment, build_script: str=None, 
                 configure_scripts: List[str]=None, cmakefile_path: str=None):
        self.src_path = src_path
        self.build_path = build_path
        self.build_type = build_type

        self.options = [Option(i) for i in options]
        self.env = env

        if self.build_type == BuildType.CMAKE:
            if cmakefile_path is None:
                self.cmakefile_path = self.src_path
            else:
                cmakefile_path = os.path.abspath(str(self.src_path) + '/' + cmakefile_path)
                self.cmakefile_path = Path(cmakefile_path)
        
        self.configure_scripts = configure_scripts
        if not self.configure_scripts:
            self.create_configure_commands()
        self.build_script = build_script
        if not self.build_script:
            self.create_build_commands()
            
    def create_configure_commands(self):
        commands = []
        if self.build_type == BuildType.CMAKE:
            cmakeFile = self.cmakefile_path / 'CMakeLists.txt'
            if not cmakeFile.exists():
                print(f'Please make sure there is CMakeLists.txt in {self.cmakefile_path}')
                exit(1)
            self.options.append(Option('CMAKE_EXPORT_COMPILE_COMMANDS=1'))
            self.options.append(Option('CMAKE_BUILD_TYPE=Release'))
            self.options.append(Option(f'CMAKE_C_COMPILER={self.env.CC}'))
            self.options.append(Option(f'CMAKE_CXX_COMPILER={self.env.CXX}'))
            commands = [self.env.CMAKE_PATH]
            commands.append(f"-S {str(self.cmakefile_path)}")
            commands.append(f"-B {str(self.build_path)}")
            for option in self.options:
                commands.append(f"-D{option.name}={option.value}")
        elif self.build_type == BuildType.CONFIGURE:
            commands = [f'CC={self.env.CC}', f'CXX={self.env.CXX}', f'{self.src_path}/configure']
            commands.append(f"--prefix={self.build_path}")
            for option in self.options:
                commands.append(option.origin_cmd())
        elif self.build_type == BuildType.KBUILD:
            # NEVER set `O=SRC_PATH` or `KBUILD_SRC=SRC_PATH` when build in tree.
            # This will make build process infinitely recurse.
            commands = [f'CC={self.env.CC}', f'CXX={self.env.CXX}']
            commands.extend(['make', 'allyesconfig'])
            commands.extend(['-C', f'{self.build_path}'])
            for option in self.options:
                commands.append(option.origin_cmd())
        self.configure_commands = commands

    def create_build_commands(self):
        # Use bear to intercept build process and record compile commands.
        commands = []
        if self.build_type == BuildType.CMAKE:
            # CMake will generate compile_commands.json in build directory.
            # We want to reverse the compile_commands.json cmake generated.
            commands.extend([self.env.CMAKE_PATH, "--build", f"{self.build_path}"])
            commands.extend([f"-j{self.env.analyze_opts.jobs}"])
            # Don't stop make although error happen.
            # '-i' is not safe, sometimes it cause `make` never stop.
            # commands.extend(["--", "-i"])
        elif self.build_type == BuildType.CONFIGURE:
            commands.extend(['make', f'-j{self.env.analyze_opts.jobs}'])
            # TODO: Change to directory contain Makefile.
            commands.extend(['-C', f'{self.build_path}'])
            # commands.extend(["-i"])
        elif self.build_type == BuildType.KBUILD:
            commands.extend(['make', f'-j{self.env.analyze_opts.jobs}'])
            # Some KBuild project(like busybox) support out of tree build.
            commands.extend(['-C', f'{self.build_path}'])
            # commands.extend(["-i"])
        elif self.build_type == BuildType.MAKE:
            commands.extend(['make', f'-j{self.env.analyze_opts.jobs}'])
            commands.extend(['-C', f'{self.build_path}'])
            # commands.extend(["-i"])
        self.build_commands = commands

    def obj_to_json(self):
        return {"build_type": self.build_type.name, "build_script": self.build_script, "configure_scripts": self.configure_scripts}

    @staticmethod
    def json_to_obj(json_data):
        return BuildInfo(json_data['build_type'], json_data['build_script'], json_data['configure_scripts'])

class Configuration:
    env: Environment
    name: str
    options: List[Option]
    args: List[str]
    src_path: Path
    build_path: Path
    workspace: Path
    compile_database: Path
    diff_file_list: List[FileInCDB]
    diff_origin_file_list: List[str]
    incrementable: bool
    session_times: Dict

    def __init__(self, name, src_path, env, options: List[str], version_stamp, build_path=None, workspace_path=None,
                 baseline=None, update_mode:bool=False, build_type: BuildType=BuildType.CMAKE, build_script = None, configure_scripts = None, 
                 cmakefile_path=None, cdb=None, need_build=True, need_configure=True):
        self.name = name
        self.src_path = src_path
        self.env = env
        self.version_stamp = version_stamp
        self.cdb = cdb
        logger.TAG = f"{self.name}/{self.version_stamp}"
        # Record all files' latest version in repo history.
        self.global_file_dict: Dict[str, FileInCDB] = {}
        # We traverse file_list most of the time, so we don't use Dict[str, FileInCDB].
        self.file_list_index: Dict[str, int] = {}
        # Files in workspace, only record files exists and has normal extname.
        self.file_list: List[FileInCDB] = []
        self.merged_files = 0
        self.abnormal_file_list: List[FileInCDB] = []
        if build_path is None:
            self.build_path = self.src_path
        else:
            tmp_path = Path(build_path)
            if tmp_path.is_absolute():
                self.build_path = tmp_path
            else:
                self.build_path = self.src_path / build_path

        # configure may need multiple scripts.
        self.build_type = build_type
        self.need_build = need_build
        self.need_configure = need_configure
        self.build_info = BuildInfo(self.src_path, self.build_path, build_type, 
                                    options, env, build_script, configure_scripts, cmakefile_path)
        
        self.workspace = Path(workspace_path)
        if workspace_path is None:
            self.workspace = self.build_path / 'workspace_for_cdb'
        makedir(str(self.workspace))
        self.update_workspace_path()

        self.diff_file_list = []
        self.status = 'WAIT'
        self.incrementable = False
        self.session_times = {}
        # Baseline Configuration
        self.baseline: Configuration = self
        if baseline:
            self.baseline = baseline
        # Update One Configuration.
        self.update_mode = update_mode
        self.global_efm: Dict[str, FileInCDB] = {}

        analyzers = self.env.analyzers
        if self.env.analyze_opts.analyzers:
            analyzers = self.env.analyze_opts.analyzers
        self.analyzers: List[Analyzer] = []
        self.enable_clangtidy = False
        self.enable_cppcheck = True
        for analyzer_name in analyzers:
            analyzer = None
            if analyzer_name == 'clangsa':
                analyzer = CSA(CSAConfig(self.env, self.csa_path, self.env.analyze_opts.csa_config), None)
            elif analyzer_name == 'clang-tidy':
                self.enable_clangtidy = True
                analyzer = ClangTidy(ClangTidyConfig(self.env, self.clang_tidy_path, self.env.analyze_opts.clang_tidy_config), None)
            elif analyzer_name == 'cppcheck':
                self.enable_cppcheck = True
                analyzer = CppCheck(CppCheckConfig(self.env, self.cppcheck_path, self.env.analyze_opts.cppcheck_config), None)
            else:
                logger.error(f"Don't support {analyzer_name}.")
                continue
            self.analyzers.append(analyzer)

    def update_workspace_path(self):
        # Compile database.
        if self.build_type == BuildType.CMAKE:
            self.compile_database = self.workspace / 'build_commands.json'
        else:
            self.compile_database = self.workspace / 'compile_commands.json'
        if self.cdb:
            self.compile_database = Path(self.cdb)
        # Preprocess & diff Path.
        self.cache_file = self.workspace / 'preprocess' / 'cache.txt'
        self.preprocess_path = self.workspace / 'preprocess' / self.version_stamp
        self.compile_commands_used_by_pre = self.preprocess_path / 'compile_commands_used_by_pre.json'
        self.preprocess_compile_database = self.preprocess_path / 'preprocess_compile_commands.json'
        self.preprocess_diff_files_path = self.preprocess_path / 'preprocess_diff_files.txt'
        self.diff_files_path = self.preprocess_path / 'diff_files.txt'
        self.diff_path = self.workspace / 'diff' / self.version_stamp
        # Compile database used by analysers.
        self.compile_commands_used_by_analyzers = self.preprocess_path / 'compile_commands_used_by_analyzers.json'
        # CSA Path.
        self.csa_path = self.workspace / 'csa'
        self.csa_output_path = self.csa_path / 'csa-reports' / self.version_stamp
        # Clang-tidy Path.
        self.clang_tidy_path = self.workspace / 'clang-tidy'
        self.clang_tidy_output_path = self.clang_tidy_path / 'clang-tidy-reports' / self.version_stamp
        self.clang_tidy_fixit = self.clang_tidy_output_path / 'fixit'
        # Cppcheck Path.
        self.cppcheck_path = self.workspace / 'cppcheck'
        self.cppcheck_build_path = self.cppcheck_path / 'build'
        self.cppcheck_output_path = self.cppcheck_path / 'cppcheck-reports' / self.version_stamp
        # Infer Path
        self.infer_path = self.workspace / 'infer'
        self.infer_output_path = self.infer_path / 'infer-reports' / self.version_stamp
        # CodeChecker workspace.
        self.codechecker_path = self.workspace / self.version_stamp
        # Reports statistics
        self.reports_statistics_path = self.workspace / 'reports_statistics.json'
    
    def update_version(self, version_stamp):
        self.version_stamp = version_stamp
        logger.TAG = f"{self.name}/{self.version_stamp}"
        if self.update_mode:
            self.update_workspace_path()

    def clean_and_configure(self, can_skip_configure: bool, has_init: bool):
        if not has_init:
            self.clean_build()
        if self.build_type == BuildType.CMAKE or not (can_skip_configure and has_init):
            self.configure()

    def process_this_config(self, can_skip_configure: bool, has_init: bool):
        # 1. configure & build
        has_init = self.read_cache()
        if self.need_configure:
            self.clean_and_configure(can_skip_configure, has_init)
        
        if self.need_build:
            self.build()
        if not self.prepare_file_list():
            logger.info(f"[Process Config] prepare file list failed.")
            return False
        
        # Record real runtime and CPU time for tasks 
        # related to incremental analysis preparation.
        start_real_time = time.time()
        start_cpu_time = os.times()

        # 2. preprocess and diff
        if self.env.inc_mode != IncrementalMode.NoInc:
            self.preprocess_repo()
            self.diff_with_other(self.baseline, not has_init)
        # 3. extract inc info
        if self.env.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            self.extract_inc_info(has_init)
        # This process have been merge in `extract_inc_info`.
        # # 4. execute analyzers
        # if self.env.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
        #     self.propagate_reanalyze_attr()

        end_real_time = time.time()
        end_cpu_time = os.times()
        self.prepare_for_inc_info_real_time = end_real_time - start_real_time
        self.prepare_for_inc_info_cpu_time_user = (end_cpu_time.user - start_cpu_time.user) 
        self.prepare_for_inc_info_cpu_time_sys = (end_cpu_time.system - start_cpu_time.system)

        # 5. prepare for CSA
        if self.env.ctu:
            self.generate_efm()
            self.merge_efm()

        # Record real runtime and CPU time for analyze tasks.
        start_real_time = time.time()
        start_cpu_time = os.times()

        self.analyze()

        end_real_time = time.time()
        end_cpu_time = os.times()
        self.analyze_real_time = end_real_time - start_real_time
        self.analyze_cpu_time_user = (end_cpu_time.user - start_cpu_time.user)
        self.analyze_cpu_time_sys = (end_cpu_time.system - start_cpu_time.system)

        return True
    
    def read_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                for line in f.readlines():
                    line = line.strip()
                    if len(line) == 0:
                        continue
                    (file, cache_file) = line.split(' ')
                    self.global_file_dict[file] = FileInCDB(cache_file=cache_file)
            logger.info("[Read Cache] Read cache successfully.")
            return True
        logger.info("[Read Cache] No cache, do full analysis.")
        return False

    def prepare_file_list(self):
        # Don't invoke this function after `configure & build` automatically,
        # but invoke and make sure be invoked mannually before any other sessions.
        if not os.path.exists(self.compile_database):
            logger.error(f"[Prepare File List] Please make sure {self.compile_database} exists, may be you should `configure & build` first.")
            return False
        self.file_list = []
        self.file_list_index = {}
        self.diff_file_list = []
        self.abnormal_file_list = []
        self.merged_files = 0
        with open(self.compile_database, 'r') as f:
            cdb = json.load(f)
            for (idx, ccdb) in enumerate(cdb):
                compile_command = CompileCommand(ccdb)
                file_in_cdb = FileInCDB(self, compile_command)
                if file_in_cdb.status == FileStatus.UNKNOWN or file_in_cdb.status == FileStatus.UNEXIST:
                    self.abnormal_file_list.append(file_in_cdb)
                else:
                    same_file_idx = self.file_list_index.get(compile_command.file)
                    if same_file_idx is not None:
                        # There maybe same file(different output) in one compile_commands.json,
                        # we only record latest compile command. 
                        self.file_list[same_file_idx] = file_in_cdb
                        self.merged_files += 1
                    else:
                        self.file_list_index[compile_command.file] = len(self.file_list)
                        self.file_list.append(file_in_cdb)
        makedir(self.preprocess_path)
        with open(self.compile_commands_used_by_analyzers, 'w') as f:
            cdb = []
            for file_in_cdb in self.file_list:
                # Update global_file_dict after file_list has been initialzed,
                # make sure there is no duplicate file name.
                self.global_file_dict[file_in_cdb.file_name] = file_in_cdb
                # Remove duplicate file in compile database.
                cdb.append(file_in_cdb.compile_command.restore_to_json())
            json.dump(cdb, f, indent=4)

        # update cache
        with open(self.cache_file, 'w') as f:
            for file_name, file_in_cdb in self.global_file_dict.items():
                f.write(f"{file_name} {file_in_cdb.prep_file}\n")

        return True

    def get_file(self, file_path: str, report=True) -> FileInCDB:
        idx = self.file_list_index.get(file_path, None)
        # Don't use `if not idx:`, because idx maybe 0.
        if idx is None:
            if report:
                logger.error(f"[Get File] {file_path} not exists in file_list_index")
            return None
        return self.file_list[idx]

    def get_file_path(self, kind: FileKind, file_path: str) -> str:
        return self.get_file(file_path).get_file_path(kind)
    
    def clean_build(self):
        makedir(self.build_path)
        clean_script = f"make -C {self.build_path} clean"
        os.chdir(self.build_path)
        try:
            process = run(clean_script, shell=True, capture_output=True, text=True, check=True)
            logger.info(f"[Clean Build Success]")
        except subprocess.CalledProcessError as e:
            logger.error(f"[Clean Build Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
        os.chdir(self.env.PWD)

    def configure(self):
        start_time = time.time()
        # remake_dir(self.build_path, "[Config Build DIR exists]")
        makedir(self.build_path, "[Config Build DIR exists]")
        if self.build_info.configure_scripts:
            configure_scripts = self.build_info.configure_scripts
        else:
            configure_scripts = [commands_to_shell_script(self.build_info.configure_commands)]

        # Some projects need to `configure & build` in source tree. 
        # CMake will not be influenced by path.
        os.chdir(self.build_path)
        for configure_script in configure_scripts:
            logger.info("[Repo Config Script] " + configure_script)
            try:
                process = run(configure_script, shell=True, capture_output=True, text=True, check=True)
                logger.info(f"[Repo Config Success] {process.stdout}")
            except subprocess.CalledProcessError as e:
                self.session_times['configure'] = SessionStatus.Failed
                logger.error(f"[Repo Config Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
                break
        self.session_times['configure'] = time.time() - start_time
        os.chdir(self.env.PWD)
    
    def build(self):
        start_time = time.time()
        makedir(self.build_path, "[Config Build DIR exists]")
        # Some projects need to `configure & build` in source tree. 
        # CMake will not be influenced by path.
        os.chdir(self.build_path)
        commands = ['bear', '--output', f'{self.compile_database}']
        # Update bear version, these parameters have been removed.
        # commands.extend(['--use-cc', f'{self.env.CC}'])
        # commands.extend(['--use-c++', f'{self.env.CXX}'])
        commands.append('--')
        if self.build_info.build_script:
            commands.append(self.build_info.build_script)
        else:
            commands.extend(self.build_info.build_commands)
        build_script = " ".join(commands)
        logger.info(f"[Repo Build Script] {build_script}")
        try:
            process = run(build_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['build'] = time.time() - start_time
            logger.info(f"[Repo Build Success]")
            makedir(os.path.dirname(self.compile_commands_used_by_analyzers))
            shutil.copy(self.compile_database, self.compile_commands_used_by_analyzers)
        except subprocess.CalledProcessError as e:
            self.session_times['build'] = SessionStatus.Failed
            logger.error(f"[Repo Build Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
        os.chdir(self.env.PWD)

    def preprocess_repo(self):
        start_time = time.time()
        # We use preprocessed file to get diff info, so this dir must remake.
        # remake_dir(self.preprocess_path, "[Preprocess Files DIR exists]")
        # We don't diff -r preprocess dir anymore, no need to remake dir.
        makedir(self.preprocess_path, "[Preprocess Files DIR exists]")

        cdb = []
        for file in self.file_list:
            prep_arguments = file.compile_command.arguments + ['-D__clang_analyzer__']
            cdb.append({
                "directory": file.compile_command.directory,
                "command": " ".join([file.compile_command.compiler] + prep_arguments),
                "file": file.file_name
            })
        pre_cdb = open(self.compile_commands_used_by_pre, 'w')
        json.dump(cdb, pre_cdb, indent=4)
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
        preprocess_script = commands_to_shell_script(commands)
        logger.debug("[Preprocess Files Script] " + preprocess_script)
        try:
            process = run(preprocess_script, shell=True, capture_output=True, text=True, check=True)
            self.status = 'PREPROCESSED'
            self.session_times['preprocess_repo'] = time.time() - start_time
            cdb = []
            for file in self.file_list:
                # Preprocessed files still need compile options, such as c++ version and so on.
                # And it's no need to add flags like '-xc++', because clang is able to identify
                # preprocessed files automatically, unless open the '-P' option. 
                #
                # When use CSA analyze the file, macro `__clang_analyzer__` will defined automatically.
                prep_arguments = file.compile_command.arguments + ['-D__clang_analyzer__']
                cdb.append({
                    "directory": file.compile_command.directory,
                    "command": " ".join([file.compile_command.compiler] + prep_arguments),
                    "file": file.prep_file
                })
            with open(self.preprocess_compile_database, 'w') as f:
                json.dump(cdb, f, indent=4)
            logger.info(f"[Preprocess Files Success] {preprocess_script}")
        except subprocess.CalledProcessError as e:
            self.session_times['preprocess_repo'] = SessionStatus.Failed
            logger.error(f"[Preprocess Files Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
    
    def extract_inc_info(self, has_init):
        '''
        use clang_tool/CollectIncInfo.cpp to generate information used by incremental analysis
        '''
        self.session_times['extract_inc_info'] = SessionStatus.Skipped
        if not has_init:
            logger.info(f"[Extract Inc Info] Don't need to extract inc info when baseline analysis.")
            return
        if not self.compile_database.exists():
            logger.error(f"[Extract Inc Info] can't extract inc info without file {self.compile_database}")
            return
        start_time = time.time()
        makedir(self.preprocess_path, "[Inc Info Files DIR exists]")
        process_file_list(FileInCDB.extract_inc_info, self.diff_file_list if self.incrementable else self.file_list, self.env.analyze_opts.jobs)
        logger.info(f"[Extract Inc Info Finish]")
        self.session_times['extract_inc_info'] = time.time() - start_time

    def generate_efm(self):
        start_time = time.time()
        # remake_dir(self.csa_path, "[EDM Files DIR exists]")
        makedir(self.csa_path, "[EDM Files DIR exists]")
        commands = self.env.DEFAULT_PANDA_COMMANDS.copy()
        commands.append('--ctu-loading-ast-files') # Prepare CTU analysis for loading AST files.
        commands.extend(['-f', str(self.compile_commands_used_by_analyzers)])
        commands.extend(['-o', str(self.csa_path)])
        if self.incrementable:
            commands.extend(['--file-list', f"{self.diff_files_path}"])
        if self.env.analyze_opts.verbose:
            commands.extend(['--verbose'])
        edm_script = commands_to_shell_script(commands)
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
        if self.incrementable:
            if not self.update_mode:
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
                        if self.update_mode:
                            fout.write('%s %s\n' % (usr, self.global_efm[usr].get_file_path(FileKind.AST)))
                        else:
                            if self.global_efm[usr].is_changed():
                                fout.write('%s %s\n' % (usr, self.global_efm[usr].get_file_path(FileKind.AST)))
                            else:
                                fout.write('%s %s\n' % (usr, self.global_efm[usr].get_baseline_file().get_file_path(FileKind.AST)))
            
            if self.update_mode:
                GenerateFinalExternalFunctionMapIncrementally(self.env.analyze_opts, self.diff_file_list, None)
            else:
                GenerateFinalExternalFunctionMapIncrementally(self.env.analyze_opts, self.diff_file_list, str(baseline_edm_file))
        else:
            with open(self.csa_path / 'externalDefMap.txt', 'r') as f:
                for line in f.readlines():
                    usr, path = parse_efm(line)
                    if usr and path:
                        self.global_efm[usr] = self.get_file(get_origin_file_name(path, str(self.csa_path), ['.ast']))
        self.session_times['merge_efm'] = time.time() - start_time

    def analyze(self):
        start_time = time.time()
        for analyzer in self.analyzers:
            analyzer_time = time.time()
            self.session_times[analyzer.__class__.__name__] = SessionStatus.Skipped
            if self.incrementable:
                analyzer.file_list = self.diff_file_list
            else:
                analyzer.file_list = self.file_list
            analyzer.analyze_all_files()
            self.session_times[analyzer.__class__.__name__] = time.time() - analyzer_time
        self.session_times['analyze'] = time.time() - start_time
    
    def reports_statistics(self):
        def list_files(directory):
            if not os.path.exists(directory):
                return []
            return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

        if not os.path.exists(self.reports_statistics_path):
            statistics = {
            }
        else:
            statistics = json.load(open(self.reports_statistics_path, 'r'))

        for analyzer in self.analyzers:
            reports = []
            if analyzer.__class__.__name__ not in statistics:
                statistics[analyzer.__class__.__name__] = []
            self.session_times[f"{analyzer.__class__.__name__} reports"] = 0
            if isinstance(analyzer, CSA):
                if not os.path.exists(self.csa_output_path):
                    continue
                reports = list_files(self.csa_output_path)
            elif isinstance(analyzer, ClangTidy):
                if not os.path.exists(self.clang_tidy_output_path):
                    continue
                reports = list_files(self.clang_tidy_output_path)
            elif isinstance(analyzer, CppCheck):
                if not os.path.exists(self.cppcheck_output_path / 'result.json'):
                    continue
                with open(self.cppcheck_output_path / 'result.json', 'r') as f:
                    cppcheck_result = json.load(f)
                    results = cppcheck_result["runs"][0]["results"]
                    reports = [{k: v for k, v in result.items() if k != 'locations'} for result in results]
            elif isinstance(analyzer, Infer):
                if not os.path.exists(self.infer_output_path / 'report.json'):
                    continue
                with open(self.infer_output_path / 'report.json', 'r') as f:
                    infer_result = json.load(f)
                    key_set = {'bug_type', 'qualifier', 'severity', 'category', 'procedure', 'file', 'key', 'bug_type_hum'}
                    reports = [{k: v for k, v in result.items() if k in key_set} for result in infer_result]

            statistics[analyzer.__class__.__name__].append({
                'version': self.version_stamp,
                'reports': reports
            })
            self.session_times[f"{analyzer.__class__.__name__} reports"] = len(reports)

        with open(self.reports_statistics_path, 'w') as f:
            json.dump(statistics, f, indent=4)

    def prepare_diff_dir(self):
        if not self.env.analyze_opts.udp:
            self.diff_path = self.preprocess_path
            return
        # remake_dir(self.diff_path, "[Diff Files DIR exists]")
        makedir(self.diff_path, "[Diff Files DIR exists]")
        with mp.Pool(self.env.analyze_opts.jobs) as p:
            p.map(replace_loc_info, [((file.prep_file, file.diff_file) if file.prep_file else (None, file.file_name)) for file in self.file_list])

    def diff_with_other(self, other, skip_diff: bool = False):
        # Replace all preprocess location info to empty lines.
        self.prepare_diff_dir()
        if skip_diff:
            logger.info(f"[Skip Diff] Skip first diff.")
            self.session_times['diff_with_other'] = SessionStatus.Skipped
            return
        if not self.update_mode:
            if self == other:
                logger.info(f"[Skip Diff] Repo {str(self.build_path)} is the same as {str(other.build_path)}")
                self.session_times['diff_with_other'] = SessionStatus.Skipped
                return
        start_time = time.time()
        if self.env.analyze_opts.udp:
            if not self.diff_path.exists():
                logger.error(f"Preprocess files DIR {self.diff_path} not exists")
                return
            if not other.diff_path.exists():
                logger.error(f"Preprocess files DIR {other.diff_path} not exists")
                return
        self.status = 'DIFF'
        # We just need to diff files in compile database.
        process_file_list(FileInCDB.diff_with_baseline, self.file_list, self.env.analyze_opts.jobs)
        for file in self.file_list:
            if file.baseline_file is not None:
                file.baseline_file.clean_files()
            if file.is_changed():
                self.diff_file_list.append(file)
        if self.status == 'DIFF':
            logger.info(f"[Parse Diff Result Success] diff file number: {len(self.diff_file_list)}")
            
            f_diff_files = open(self.diff_files_path, 'w')
            f_prep_diff_files = open(self.preprocess_diff_files_path, 'w')

            for diff_file in self.diff_file_list:
                f_diff_files.write(diff_file.file_name + '\n')
                f_prep_diff_files.write(diff_file.prep_file + '\n')
            
            f_diff_files.close()
            f_prep_diff_files.close()

            with open(self.compile_commands_used_by_analyzers, 'w') as f:
                cdb = []
                for file in self.diff_file_list:
                    cdb.append(file.compile_command.restore_to_json())
                json.dump(cdb, f, indent=4)

            self.incrementable = self.env.inc_mode != IncrementalMode.NoInc
            self.session_times['diff_with_other'] = time.time() - start_time
        else:
            self.session_times['diff_with_other'] = SessionStatus.Failed

    def propagate_reanalyze_attr(self):
        self.session_times['propagate_reanalyze_attr'] = SessionStatus.Skipped
        if not self.incrementable:
            return
        start_time = time.time()
        self.session_times['propagate_reanalyze_attr'] = SessionStatus.Failed
        process_file_list(FileInCDB.propagate_reanalyze_attribute, self.diff_file_list if self.incrementable else self.file_list, self.env.analyze_opts.jobs)
        logger.info(f"[Propagate Reanalyze Attr] Propagate reanalyze attribute successfully.")
        self.session_times['propagate_reanalyze_attr'] = time.time() - start_time

    def get_changed_function_num(self):
        self.changed_function_num = 0
        self.diff_file_with_no_cf = 0
        for file in self.diff_file_list:
            if file.cf_num and isinstance(file.cf_num, int):
                self.changed_function_num += (file.cf_num)
            else:
                self.diff_file_with_no_cf += 1
        return self.changed_function_num
    
    def get_reanalyze_function_num(self):
        self.reanalyze_function_num = 0
        for file in self.diff_file_list:
            if file.rf_num and isinstance(file.rf_num, int):
                self.reanalyze_function_num += file.rf_num
        return self.reanalyze_function_num
    
    def get_indirect_call_num(self):
        self.indirect_call_num = 0
        for file in self.diff_file_list:
            if file.indirect_call_num and isinstance(file.indirect_call_num, int):
                self.indirect_call_num += file.indirect_call_num
        return self.indirect_call_num

    def get_total_cg_nodes_num(self):
        self.total_cg_nodes = 0
        for file in self.diff_file_list:
            if file.cg_node_num and isinstance(file.cg_node_num, int):
                self.total_cg_nodes += file.cg_node_num
        return self.total_cg_nodes
    
    def get_total_csa_analyze_time(self):
        # CSA analyze time is different with real execution time, it only
        # contains time used for Syntax Analysis, Path sensitive Analysis and 
        # Reports post processing.
        self.total_csa_analyze_time = 0
        file_list = self.diff_file_list if self.incrementable else self.file_list
        for file in file_list:
            if file.csa_analyze_time != 'Unknown':
                self.total_csa_analyze_time += float(file.csa_analyze_time)
        return self.total_csa_analyze_time

    def get_session_times(self):
        ret = "{\n"
        for session in self.session_times.keys():
            exe_time = self.session_times[session]
            if isinstance(exe_time, SessionStatus):
                ret += ("   %s: %s\n" % (session, exe_time._name_))
            elif isinstance(exe_time, int):
                ret += ("   %s: %d\n" % (session, exe_time))
            else:
                ret += ("   %s: %.3lf sec\n" % (session, exe_time))
        ret += "}\n"
        return ret
    
    def __repr__(self) -> str:
        ret = f"build path: {self.build_path}\n"
        ret += "OPTIONS:\n"
        for option in self.build_info.options:
            ret += f"   {option.name:<40} | {option.value}\n"    
        ret += f"execution time: {self.get_session_times()}\n"
        return ret

    def file_status(self):
        headers = ['file', 'status', 'csa analyze time(s)', 'cg nodes', 'changed functions', 'reanalyze functions', 'indirect call']
        datas = []
        unexists_number, unknown_number = 0, 0
        for ab_file in self.abnormal_file_list:
            datas.append([ab_file.file_name, str(ab_file.status)])
            if ab_file.status == FileStatus.UNEXIST:
                unexists_number += 1
            else:
                unknown_number += 1
        new_file_num, changed_file_num, unchanged_file_num = 0, 0, 0
        total_csa_time = 0.0
        for file in self.file_list:
            # file, status, analyze time, cg nodes num, cf num, rf num, baseline fs num
            data = [file.file_name, str(file.status)]
            # if self.env.inc_mode.value >= IncrementalMode.FuncitonLevel.value and file.is_changed():
            #     # Parse CG maybe skipped if it's new file or no function changed.
            #     # Or just because inc_mode < function level.
            #     if not file.has_cg:
            #         file.parse_cg_file()
            # if self.env.inc_mode == IncrementalMode.InlineLevel and not file.baseline_has_fs:
            #     file.parse_baseline_fs_file()
            data.extend([file.csa_analyze_time, file.cg_node_num, file.cf_num, file.rf_num, file.indirect_call_num])
            datas.append(data)
            if file.status == FileStatus.NEW:
                new_file_num += 1
            elif file.status == FileStatus.CHANGED:
                changed_file_num += 1
            elif file.status == FileStatus.UNCHANGED:
                unchanged_file_num += 1
            if file.csa_analyze_time != "Unknown":
                total_csa_time += float(file.csa_analyze_time)
        datas.append([f"unexist files:{unexists_number}", f"unknown files:{unknown_number}", f"merged files:{self.merged_files}",
                      f"new files:{new_file_num}", f"changed files:{changed_file_num}", f"unchanged files:{unchanged_file_num}",
                      f"total csa analyze time:{total_csa_time}"])
        return headers, datas