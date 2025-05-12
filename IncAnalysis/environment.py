import os
from pathlib import Path
import re
import shutil
import argparse
from enum import Enum, auto
from datetime import datetime
import subprocess

from IncAnalysis.logger import logger

class IncrementalMode(Enum):
    NoInc = auto()
    FileLevel = auto()
    FuncitonLevel = auto()
    InlineLevel = auto()
    ALL = auto() # Experiment option, executing [noinc, file, func] incremental strategies.

    def __str__(self) -> str:
        if self == IncrementalMode.NoInc:
            return 'noinc'
        elif self == IncrementalMode.FileLevel:
            return 'file'
        elif self == IncrementalMode.FuncitonLevel:
            return 'func'
        elif self == IncrementalMode.InlineLevel:
            return 'inline'
        elif self == IncrementalMode.ALL:
            return 'all'
        return 'unknown'

class Environment:
    def __init__(self, opts, ice_bear_path):
        # Analysis Options
        self.analyze_opts = opts
        self.inc_mode = IncrementalMode.NoInc
        if opts.inc == 'file':
            self.inc_mode = IncrementalMode.FileLevel
        elif opts.inc == 'func':
            self.inc_mode = IncrementalMode.FuncitonLevel
        elif opts.inc == 'inline':
            self.inc_mode = IncrementalMode.InlineLevel
        elif opts.inc == 'all':
            self.inc_mode = IncrementalMode.ALL
        
        self.ctu = opts.analyze == 'ctu'
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        logger.verbose = opts.verbose
        self.prepare_env_path(ice_bear_path)

        self.env = dict(os.environ)
        self.env['CC'] = self.CC
        self.env['CXX'] = self.CXX

    def check_conflict(self):
        if self.analyze_opts.file_identifier != 'file' and self.ctu:
            logger.error(f"[Option Conflict] File identidier must be \'file\' if turn on ctu analysis.")
            exit(1)
    
    def prepare_compiler_path(self, compiler_path):
        if compiler_path in self.system_dir:
            return
        compiler = os.path.basename(compiler_path)
        if 'cc' in compiler or 'c++' in compiler:
            compiler = subprocess.run(["readlink", "-f", compiler_path], capture_output=True).stdout.decode('utf-8').strip()
        if 'clang' in compiler:
            self.system_dir[compiler_path] = subprocess.run([compiler_path, '-print-resource-dir'], capture_output=True).stdout.decode('utf-8').strip()
        elif 'gcc' in compiler or 'g++' in compiler:
            gcc_info = subprocess.run([compiler_path, "-print-search-dirs"], capture_output=True).stdout.decode('utf-8').strip()
            for line in gcc_info.splitlines():
                if line.startswith('install:'):
                    self.system_dir[compiler_path] = line[8:].strip()
                    break

    def prepare_env_path(self, ice_bear_path):
        # Environment path
        self.PWD: Path = Path(ice_bear_path).absolute()
        self.EXTRACT_II = str(self.PWD / 'build/clang_tool/collectIncInfo')
        self.PANDA = str(self.PWD / 'external/panda/panda')
        if self.analyze_opts.basic_info:
            self.EXTRACT_BASIC_II = shutil.which(self.analyze_opts.basic_info)
            if not self.EXTRACT_BASIC_II:
                logger.error(f"Cannot find {self.analyze_opts.basic_info}")
                exit(1)

        # Environment CC/CXX Compiler
        self.CC = shutil.which(self.analyze_opts.cc)
        self.CXX = shutil.which(self.analyze_opts.cxx)
        self.system_dir = {}
        self.prepare_compiler_path(self.CC)
        self.prepare_compiler_path(self.CXX)

        # Customized clang path.
        if self.analyze_opts.clang:
            self.CLANG = shutil.which(self.analyze_opts.clang)
        else:
            self.CLANG = shutil.which('clang')
        
        def exit_if_inc():
            if self.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
                exit(1)
            
        if self.CLANG is None or not os.path.exists(self.CLANG):
            logger.error(f'Please ensure that {self.CLANG} exists in your environment')
            exit_if_inc()
        
        assert self.CLANG is not None
        logger.info(f'Use clang={self.CLANG}')
        clang_bin = os.path.dirname(self.CLANG) # type: ignore
        self.CLANG_PLUS_PLUS = os.path.join(clang_bin, os.path.basename(self.CLANG).replace('clang', 'clang++'))
        self.prepare_compiler_path(self.CLANG)
        self.prepare_compiler_path(self.CLANG_PLUS_PLUS)
        # Other tools.
        self.clang_tidy = os.path.join(clang_bin, 'clang-tidy')
        self.diagtool = os.path.join(clang_bin, 'diagtool')
        if self.analyze_opts.cppcheck:
            self.cppcheck = shutil.which(self.analyze_opts.cppcheck)
        else:
            self.cppcheck = shutil.which('cppcheck')
        self.infer = shutil.which('infer')
        # Customized gcc path.
        if self.analyze_opts.gcc:
            self.GCC = shutil.which(self.analyze_opts.gcc)
        else:
            self.GCC = shutil.which('gcc')
        if self.GCC is None or not os.path.exists(self.GCC):
            logger.error(f'Please ensure that {self.GCC} exists in your environment')
        else:
            gcc_bin = os.path.dirname(self.GCC)
            self.GXX = os.path.join(gcc_bin, os.path.basename(self.GCC).replace('gcc', 'g++'))
            self.prepare_compiler_path(self.GCC)
            self.prepare_compiler_path(self.GXX)

        self.analyzers = ['clangsa']
        if os.path.exists(self.clang_tidy):
            self.analyzers.append('clang-tidy')
        if self.cppcheck and os.path.exists(self.cppcheck):
            self.analyzers.append('cppcheck')
        # Don't support infer.
        # if os.path.exists(self.infer):
        #     self.analyzers.append('infer')
        if self.GCC and os.path.exists(self.GCC):
            self.analyzers.append('gsa')

        self.example_compiler_action_plugin = {
            "comment": "Example plugin for Panda driver.",
            "type": "CompilerAction",
            "action": {
                "title": "Dumping clang cc1 arguments",
                "args": ["-###"],
                "extname": ".d",
                "outopt": None
            }
        }
        self.example_clang_tool_plugin = {
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

        # 查找cmake命令的位置
        self.CMAKE_PATH = shutil.which('cmake')
        self.DIFF_PATH = shutil.which('diff')
        
        if self.DIFF_PATH:
            logger.info(f'diff found at: {self.CMAKE_PATH}')
            # -b, -B: Try to ignore more space.
            # -d: Identify smaller changes.
            self.DIFF_COMMAND = [self.DIFF_PATH, '-b', '-B', '-d']
            if not self.analyze_opts.udp:
                self.DIFF_COMMAND.extend(['-I', "'^# [[:digit:]]'"])
            # Only output line change, don't output specific code.
            self.DIFF_COMMAND.extend(["--old-group-format='%de,%dn %dE,%dN\n'", "--unchanged-group-format=''", 
                                      "--new-group-format='%de,%dn %dE,%dN\n'", "--changed-group-format='%de,%dn %dE,%dN\n'"])
        else:
            logger.error('diff not found in the system path')
            exit_if_inc()
        if self.EXTRACT_II:
            logger.info(f'Inc info extractor found at: {self.EXTRACT_II}')
        else:
            logger.error('Please build inc info extractor firstly') 
            exit_if_inc()
        
        self.DEFAULT_PANDA_COMMANDS = [
            self.PANDA, 
            '-j', str(self.analyze_opts.jobs), '--print-execution-time',
            '--cc', self.CC, 
            '--cxx', self.CXX
        ]

        self.bear = shutil.which("bear")
        if self.bear is None or not os.path.exists(self.bear):
            logger.error("Please ensure that bear exists in your envrionment")
        
        def get_bear_version(bear):
            try:
                result = subprocess.run([bear, "--version"], capture_output=True, text=True, check=True)
                match = re.match(r'bear (\d+)\.', result.stdout)
                if match:
                    return int(match.group(1))
                return 2
            except (subprocess.CalledProcessError, OSError):
                return 2
        self.bear_version = get_bear_version(self.bear)

class ArgumentParser:
    def __init__(self):
        self.parser = argparse.ArgumentParser(prog='IceBear', formatter_class=argparse.RawTextHelpFormatter)
        self.parser.add_argument('--inc', type=str, dest='inc', choices=['noinc', 'file', 'func', 'all'], default='file',
                                 help='Incremental analysis mode: noinc, file, func')
        self.parser.add_argument('--verbose', action='store_true', dest='verbose', help='Record debug information.')
        self.parser.add_argument('--analyze', type=str, dest='analyze', choices=['ctu', 'no-ctu'], default='no-ctu',
                                 help='Enable Clang Static Analyzer cross translation units analysis or not.')
        self.parser.add_argument('--cc', type=str, dest='cc', default='clang', help='Customize the C compiler for configure & build.')
        self.parser.add_argument('--cxx', type=str, dest='cxx', default='clang++', help='Customize the C++ compiler for configure & build.')
        self.parser.add_argument('-j', '--jobs', type=int, dest='jobs', default=1, help='Number of jobs can be executed in parallel.')
        self.parser.add_argument('-d', '--udp', action='store_true', dest='udp', help='Use files in diff path to `diff`.')
        supported_analyzers = ['clangsa', 'clang-tidy', 'cppcheck', 'gsa']
        self.parser.add_argument('--analyzers', nargs='+', dest='analyzers', metavar='ANALYZER', required=False, choices=supported_analyzers,
                               default=None, help="Run analysis only with the analyzers specified. Currently supported analyzers "
                                    "are: " + ', '.join(supported_analyzers) + ".")
        self.parser.add_argument('--clang', type=str, dest='clang', default=None, 
                                 help='Customize the Clang compiler for CSA func level incremental analysis.')
        self.parser.add_argument('--cppcheck', type=str, dest='cppcheck', default=None, 
                                 help='Customize the Cppcheck path for func level incremental analysis.')
        self.parser.add_argument('--gcc', type=str, dest='gcc', default=None, 
                                 help='Customize the Gcc compiler for GSA func level incremental analysis.')
        self.parser.add_argument('--csa-config', type=str, dest='csa_config', default=None, 
                                 help='CSA config file, an example is config/clangsa_config.json.')
        self.parser.add_argument('--clang-tidy-config', type=str, dest='clang_tidy_config', default=None, 
                                 help='Clang-tidy config file, an example is config/clang-tidy_config.json.')
        self.parser.add_argument('--cppcheck-config', type=str, dest='cppcheck_config', default=None, 
                                 help='Cppcheck config file, an example is config/cppcheck_config.json.')
        # self.parser.add_argument('--infer-config', type=str, dest='infer_config', default=None, help='Infer config file.')
        self.parser.add_argument('--gsa-config', type=str, dest='gsa_config', default=None, 
                                 help='GSA config file, an example is config/gsa_config.json.')
        self.parser.add_argument('--file-identifier', type=str, dest='file_identifier', choices=['file', 'target'], default='file name', 
                                 help='Identify analysis unit by file or target.')
        self.parser.add_argument('--basic-info', type=str, dest='basic_info', 
                                 help='Record basic information (CG node number, etc.).')
        self.parser.add_argument('--no-clean-inc', dest='clean_inc', action='store_false',
                                 help='Disable cleaning incremental files after analysis.')
    
    def parse_args(self, args):
        return self.parser.parse_args(args)