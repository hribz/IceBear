import os
from pathlib import Path
import shutil
import argparse
from enum import Enum, auto
from datetime import datetime

from IncAnalysis.logger import logger

class IncrementalMode(Enum):
    NoInc = auto()
    FileLevel = auto()
    FuncitonLevel = auto()
    InlineLevel = auto()

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
        
        self.ctu = opts.analyze == 'ctu'
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.prepare_env_path(ice_bear_path)

        self.env = dict(os.environ)
        self.env['CC'] = self.CC
        self.env['CXX'] = self.CXX

    def prepare_env_path(self, ice_bear_path):
        # Environment path
        self.PWD: Path = Path(ice_bear_path).absolute()
        self.EXTRACT_II = str(self.PWD / 'build_rcg/clang_tool/collectIncInfo')
        self.PANDA = str(self.PWD / 'external/panda/panda')
        # Environment CC/CXX Compiler

        self.CC = shutil.which(self.analyze_opts.cc)
        self.CXX = shutil.which(self.analyze_opts.cxx)
        # Customized clang path.
        if self.analyze_opts.clang:
            self.CLANG = shutil.which(self.analyze_opts.clang)
        else:
            self.CLANG = shutil.which('clang')
        clang_bin = os.path.dirname(self.CLANG)
        self.CLANG_PLUS_PLUS = os.path.join(clang_bin, 'clang++')
        self.clang_tidy = os.path.join(clang_bin, 'clang-tidy')
        self.diagtool = os.path.join(clang_bin, 'diagtool')
        if self.analyze_opts.cppcheck:
            self.cppcheck = shutil.which(self.analyze_opts.cppcheck)
        else:
            self.cppcheck = shutil.which('cppcheck')
        self.infer = shutil.which('infer')

        self.analyzers = ['clangsa']
        if os.path.exists(self.clang_tidy):
            self.analyzers.append('clang-tidy')
        if os.path.exists(self.cppcheck):
            self.analyzers.append('cppcheck')
        # Don't support infer.
        # if os.path.exists(self.infer):
        #     self.analyzers.append('infer')

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
            exit(1)
        if self.EXTRACT_II:
            logger.info(f'Inc info extractor found at: {self.EXTRACT_II}')
        else:
            logger.error('Please build inc info extractor firstly') 
            exit(1)
        if os.path.exists(self.CLANG):
            logger.info(f'Use clang={self.CLANG}')
        else:
            logger.error(f'Please ensure that {self.CLANG} exists in your environment')
            exit(1)
        if os.path.exists(self.CLANG_PLUS_PLUS):
            logger.info(f'Use clang++={self.CLANG_PLUS_PLUS}')
        else:
            logger.error(f'Please ensure that {self.CLANG_PLUS_PLUS} exists in your environment')
            exit(1)
        
        self.DEFAULT_PANDA_COMMANDS = [
            self.PANDA, 
            '-j', str(self.analyze_opts.jobs), '--print-execution-time',
            '--cc', self.CLANG, 
            '--cxx', self.CLANG_PLUS_PLUS
        ]

class ArgumentParser:
    def __init__(self):
        self.parser = argparse.ArgumentParser(prog='IceBear', formatter_class=argparse.RawTextHelpFormatter)
        self.parser.add_argument('--inc', type=str, dest='inc', choices=['noinc', 'file', 'func'], default='file',
                                 help='Incremental analysis mode: noinc, file, func')
        self.parser.add_argument('--verbose', action='store_true', dest='verbose', help='Record debug information.')
        self.parser.add_argument('--analyze', type=str, dest='analyze', choices=['ctu', 'no-ctu'], default='no-ctu',
                                 help='Enable Clang Static Analyzer cross translation units analysis or not.')
        self.parser.add_argument('--cc', type=str, dest='cc', default='clang', help='Customize the C compiler for configure & build.')
        self.parser.add_argument('--cxx', type=str, dest='cxx', default='clang++', help='Customize the C++ compiler for configure & build.')
        self.parser.add_argument('-j', '--jobs', type=int, dest='jobs', default=1, help='Number of jobs can be executed in parallel.')
        self.parser.add_argument('-d', '--udp', action='store_true', dest='udp', help='Use files in diff path to `diff`.')
        supported_analyzers = ['clangsa', 'clang-tidy', 'cppcheck']
        self.parser.add_argument('--analyzers', nargs='+', dest='analyzers', metavar='ANALYZER', required=False, choices=supported_analyzers,
                               default=None, help="Run analysis only with the analyzers specified. Currently supported analyzers "
                                    "are: " + ', '.join(supported_analyzers) + ".")
        self.parser.add_argument('--clang', type=str, dest='clang', default=None, 
                                 help='Customize the Clang compiler for CSA func level incremental analysis.')
        self.parser.add_argument('--cppcheck', type=str, dest='cppcheck', default=None, 
                                 help='Customize the Cppcheck path for func level incremental analysis.')
        self.parser.add_argument('--csa-config', type=str, dest='csa_config', default=None, 
                                 help='CSA config file, an example is config/clangsa_config.json.')
        self.parser.add_argument('--clang-tidy-config', type=str, dest='clang_tidy_config', default=None, 
                                 help='Clang-tidy config file, an example is config/clang-tidy_config.json.')
        self.parser.add_argument('--cppcheck-config', type=str, dest='cppcheck_config', default=None, 
                                 help='Cppcheck config file, an example is config/cppcheck_config.json.')
        # self.parser.add_argument('--infer-config', type=str, dest='infer_config', default=None, help='Infer config file.')
    
    def parse_args(self, args):
        return self.parser.parse_args(args)