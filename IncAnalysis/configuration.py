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

from data_struct.reply import Reply
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
    CMAKE = auto()
    CONFIGURE = auto()
    KBUILD = auto()

    @staticmethod
    def getType(build_type: str):
        if build_type == 'cmake':
            return BuildType.CMAKE
        elif build_type == 'configure':
            return BuildType.CONFIGURE
        elif build_type == 'kbuild':
            return BuildType.KBUILD

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
    # Files in workspace, only record files exists and has normal extname.
    file_list: List[FileInCDB]
    abnormal_file_list: List[FileInCDB]

    def __init__(self, name, src_path, env, options: List[str], args=None, build_path=None, 
                 baseline=None, update_mode:bool=False, build_type: BuildType=BuildType.CMAKE):
        self.name = name
        self.src_path = src_path
        self.env = env
        self.update_build_path(build_path)
        self.file_list_index = None
        self.file_list = None
        self.abnormal_file_list = []
        if args:
            self.args = args
        else:
            self.args = None
        self.options = [Option(i) for i in options]
        self.build_type = build_type
        self.create_configure_script()
        self.create_build_script()
        self.reply_database = []
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
        self.global_efm: Dict[str, FileInCDB] = None
        self.analyzers: List[Analyzer] = [
            CSA(CSAConfig(self.env, self.csa_path, self.env.analyze_opts.csa_config), self.file_list)
        ]

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
        self.diff_files_path = self.workspace / 'diff_files.txt'
    
    def process_this_config(self, skip_configure: bool):
        logger.TAG = f"{self.name}/{os.path.basename(str(self.build_path))}"
        # 1. selfure & build
        if not skip_configure:
            self.configure()
        self.build()
        self.prepare_file_list()
        # 2. preprocess and diff
        self.preprocess_repo()
        if self.env.inc_mode != IncrementalMode.NoInc:
            self.diff_with_other(self.baseline)
        # 3. extract inc info
        if self.env.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            self.extract_inc_info()
        # 4. prepare for CSA
        if self.env.ctu:
            self.generate_efm()
            self.merge_efm()
        # 5. execute analyzers
        if self.env.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            self.propagate_reanalyze_attr()
        self.analyze()

    def prepare_file_list(self):
        # Don't invoke this function after `configure & build` automatically,
        # but invoke and make sure be invoked mannually before any other sessions.
        if not os.path.exists(self.compile_database):
            logger.error(f"[Prepare File List] Please make sure {self.compile_database} exists, may be you should `configure & build` first.")
            return
        if not self.update_mode:
            self.file_list_index = {}
            self.file_list  = []
        self.abnormal_file_list = []
        with open(self.compile_database, 'r') as f:
            cdb = json.load(f)
            for (idx, ccdb) in enumerate(cdb):
                compile_command = CompileCommand(ccdb)
                file_in_cdb = FileInCDB(self, compile_command)
                if file_in_cdb.status == FileStatus.UNKNOWN or file_in_cdb.status == FileStatus.UNEXIST:
                    self.abnormal_file_list.append(file_in_cdb)
                else:
                    self.file_list_index[compile_command.file] = len(self.file_list)
                    self.file_list.append(file_in_cdb)

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

    def create_cmake_api_file(self):
        if self.cmake_api_path.exists():
            shutil.rmtree(self.cmake_api_path)
        os.makedirs(self.query_path)
        query_list = ['codemodel-v2', 'cache-v2', 'cmakeFiles-v1']
        for query in query_list:
            with open(self.query_path / query, 'w') as f:
                f.write('')
    
    def create_configure_script(self):
        if self.build_type == BuildType.CMAKE:
            cmakeFile = self.src_path / 'CMakeLists.txt'
            if not cmakeFile.exists():
                print(f'Please make sure there is CMakeLists.txt in {self.src_path}')
                exit(1)
            self.options.append(Option('CMAKE_EXPORT_COMPILE_COMMANDS=1'))
            self.options.append(Option('CMAKE_BUILD_TYPE=Release'))
            self.options.append(Option(f'CMAKE_C_COMPILER={self.env.CLANG}'))
            self.options.append(Option(f'CMAKE_CXX_COMPILER={self.env.CLANG_PLUS_PLUS}'))
            commands = [self.env.CMAKE_PATH]
            commands.append(f"-S {str(self.src_path)}")
            commands.append(f"-B {str(self.build_path)}")
            for option in self.options:
                commands.append(f"-D{option.name}={option.value}")
        elif self.build_type == BuildType.CONFIGURE:
            commands = [f'{self.src_path}/configure']
            commands.append(f"--prefix={self.build_path}")
            for option in self.options:
                commands.append(option.origin_cmd())
        elif self.build_type == BuildType.KBUILD:
            commands = ['make']
            commands.extend([f'KBUILD_SRC={self.src_path}', '-f', f'{self.src_path}/Makefile'])
            commands.extend(['-C', f'{self.build_path}'])
            for option in self.options:
                commands.append(option.origin_cmd())
        if self.args:
            commands.extend(self.args)
        self.configure_script = ' '.join(commands)

    def create_build_script(self):
        # Use bear to intercept build process and record compile commands.
        commands = ['bear', '-o', f'{self.compile_database}']
        if self.build_type == BuildType.CMAKE:
            commands.extend([self.env.CMAKE_PATH, "--build", f"{self.build_path}"])
            commands.extend([f"-j{self.env.analyze_opts.jobs}"])
        elif self.build_type == BuildType.CONFIGURE:
            commands.extend(['make', f'-j{self.env.analyze_opts.jobs}'])
            # TODO: Change to directory contain Makefile.
            commands.extend(['-C', f'{self.src_path}'])
        elif self.build_type == BuildType.KBUILD:
            commands.extend(['make', f'-j{self.env.analyze_opts.jobs}'])
            # Some KBuild project(like busybox) support out of tree build.
            commands.extend(['-C', f'{self.build_path}'])
        self.build_script = ' '.join(commands)

    def configure(self):
        start_time = time.time()
        # remake_dir(self.build_path, "[Config Build DIR exists]")
        makedir(self.build_path, "[Config Build DIR exists]")
        if self.build_type == BuildType.CMAKE:
            self.create_cmake_api_file()
        logger.debug("[Repo Config Script] " + self.configure_script)
        # Some projects need to `configure & build` in source tree. 
        # CMake will not be influenced by path.
        os.chdir(self.src_path)
        try:
            process = run(self.configure_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['configure'] = time.time() - start_time
            logger.info(f"[Repo Config Success] {process.stdout}")
            
            with open(self.build_path / 'options.json', 'w') as f:
                tmp_json_data = {"options": []}
                for option in self.options:
                    tmp_json_data['options'].append(option.obj_to_json())
                json.dump(tmp_json_data, f, indent=4)
            # self.reply_database.append(Reply(self.reply_path, logger))
        except subprocess.CalledProcessError as e:
            self.session_times['configure'] = SessionStatus.Failed
            logger.error(f"[Repo Config Failed] stdout: {e.stdout}\n stderr: {e.stderr}")
        os.chdir(self.env.PWD)
    
    def build(self):
        start_time = time.time()
        makedir(self.build_path, "[Config Build DIR exists]")
        # Some projects need to `configure & build` in source tree. 
        # CMake will not be influenced by path.
        os.chdir(self.src_path)
        try:
            process = run(self.build_script, shell=True, capture_output=True, text=True, check=True)
            self.session_times['build'] = time.time() - start_time
            logger.info(f"[Repo Build Success] {self.build_script}")
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
        makedir(self.preprocess_path, "[Inc Info Files DIR exists]")
        process_file_list(FileInCDB.extract_inc_info, self.diff_file_list if self.incrementable else self.file_list, self.env.analyze_opts.jobs)
        self.session_times['extract_inc_info'] = time.time() - start_time

    def generate_efm(self):
        start_time = time.time()
        # remake_dir(self.csa_path, "[EDM Files DIR exists]")
        makedir(self.csa_path, "[EDM Files DIR exists]")
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
                            fout.write('%s %s\n' % (usr, self.global_efm[usr].get_baseline_file().get_file_path(FileKind.AST)))

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
            self.session_times[analyzer.get_analyzer_name()] = SessionStatus.Skipped
            if self.incrementable:
                analyzer.file_list = self.diff_file_list
            else:
                analyzer.file_list = self.file_list
            if analyzer.analyze_all_files():
                self.session_times[analyzer.get_analyzer_name()] = time.time() - analyzer_time
            else:
                self.session_times[analyzer.get_analyzer_name()] = SessionStatus.Failed
        self.session_times['analyze'] = time.time() - start_time

    def prepare_diff_dir(self):
        if not self.env.analyze_opts.udp:
            self.diff_path = self.preprocess_path
            return
        # remake_dir(self.diff_path, "[Diff Files DIR exists]")
        makedir(self.diff_path, "[Diff Files DIR exists]")
        with mp.Pool(self.env.analyze_opts.jobs) as p:
            p.map(replace_loc_info, [((file.prep_file, file.diff_file) if file.prep_file else (None, file.file_name)) for file in self.file_list])

    def diff_with_other(self, other):
        # Replace all preprocess location info to empty lines.
        self.prepare_diff_dir()
        if self == other:
            logger.info(f"[Skip Diff] Repo {str(self.build_path)} is the same as {str(other.build_path)}")
            self.session_times['diff_with_other'] = SessionStatus.Skipped
            return
        start_time = time.time()
        self.baseline = other
        if self.env.analyze_opts.udp:
            if not self.diff_path.exists():
                logger.error(f"Preprocess files DIR {self.diff_path} not exists")
                return
            if not other.diff_path.exists():
                logger.error(f"Preprocess files DIR {other.diff_path} not exists")
                return
        self.status = 'DIFF'
        # We just need to diff files in compile database.
        process_file_list(FileInCDB.diff_with_baseline, self.diff_file_list if self.incrementable else self.file_list, self.env.analyze_opts.jobs)
        for file in self.file_list:
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
        changed_function_num = 0
        self.diff_file_with_no_cf = 0
        for file in self.diff_file_list:
            if file.cf_num and isinstance(file.cf_num, int):
                changed_function_num += (file.cf_num)
            else:
                self.diff_file_with_no_cf += 1
        return changed_function_num
    
    def get_reanalyze_function_num(self):
        reanalyze_function_num = 0
        self.diff_file_with_no_cg = 0
        for file in self.diff_file_list:
            if file.rf_num and isinstance(file.rf_num, int):
                reanalyze_function_num += file.rf_num
            else:
                self.diff_file_with_no_cg += 1
        return reanalyze_function_num

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
        for option in self.options:
            ret += f"   {option.name:<40} | {option.value}\n"    
        ret += f"execution time: {self.get_session_times()}\n"
        return ret

    def file_status(self):
        headers = ['file', 'status', 'cg nodes', 'changed functions', 'reanalyze functions', 'function summaries']
        datas = []
        unexists_number, unknown_number = 0, 0
        for ab_file in self.abnormal_file_list:
            datas.append([ab_file.file_name, str(ab_file.status)])
            if ab_file.status == FileStatus.UNEXIST:
                unexists_number += 1
            else:
                unknown_number += 1
        new_file_num, changed_file_num, unchanged_file_num = 0, 0, 0
        for file in self.file_list:
            # file, status, cg nodes num, cf num, rf num, fs num
            data = [file.file_name, str(file.status), 0, 0, 0, 0]
            if not file.has_cg:
                # Parse CG maybe skipped.
                file.parse_cg_file()
            data[2] = (file.cg_node_num)
            data[3] = (file.cf_num)
            data[4] = (file.rf_num)
            if not file.has_fs:
                file.parse_fs_file()
            data[5] = (file.fs_num)
            datas.append(data)
            if file.status == FileStatus.NEW:
                new_file_num += 1
            elif file.status == FileStatus.CHANGED:
                changed_file_num += 1
            elif file.status == FileStatus.UNCHANGED:
                unchanged_file_num += 1
        datas.append([f"unexist files:{unexists_number}", f"unknown files:{unknown_number}", 
                      f"new files:{new_file_num}", f"changed files:{changed_file_num}", f"unchanged files:{unchanged_file_num}"])
        return headers, datas