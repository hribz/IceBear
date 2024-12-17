import os
from pathlib import Path
import shutil
import argparse
from enum import Enum, auto
from datetime import datetime

class IncrementalMode(Enum):
    NoInc = auto()
    FileLevel = auto()
    FuncitonLevel = auto()
    InlineLevel = auto()

class Environment:
    def __init__(self, opts):
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
        self.prepare_env_path()

        self.env = dict(os.environ)
        self.env['CC'] = self.CLANG
        self.env['CXX'] = self.CLANG_PLUS_PLUS

    def prepare_env_path(self):
        # Environment path
        self.PWD: Path = Path(".").absolute()
        self.EXTRACT_II = str(self.PWD / 'build/clang_tool/collectIncInfo')
        self.EXTRACT_CG = str(self.PWD / 'build/clang_tool/extractCG')
        self.PANDA = str(self.PWD / 'panda/panda')
        # CSA revised version
        self.MY_CLANG = 'clang'
        self.MY_CLANG_PLUS_PLUS = 'clang++'
        self.CLANG = 'clang'
        self.CLANG_PLUS_PLUS = 'clang++'
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

        self.LOG_TAG = ''
        # 查找cmake命令的位置
        self.CMAKE_PATH = shutil.which('cmake')
        if self.CMAKE_PATH:
            print(f'CMake found at: {self.CMAKE_PATH}')
        else:
            print('CMake not found in the system path')
            exit(1)
        self.DIFF_PATH = shutil.which('diff')
        if self.DIFF_PATH:
            print(f'diff found at: {self.CMAKE_PATH}')
            # -b, -B: Try to ignore more space.
            # -d: Identify smaller changes.
            self.DIFF_COMMAND = [self.DIFF_PATH, '-b', '-B', '-d']
            if not self.analyze_opts.udp:
                self.DIFF_COMMAND.extend(['-I', "'^# [[:digit:]]'"])
            # Only output line change, don't output specific code.
            self.DIFF_COMMAND.extend(["--old-group-format='%de,%dn %dE,%dN\n'", "--unchanged-group-format=''", 
                                      "--new-group-format='%de,%dn %dE,%dN\n'", "--changed-group-format='%de,%dn %dE,%dN\n'"])
        else:
            print('diff not found in the system path')
            exit(1)
        if self.EXTRACT_II:
            print(f'cg extractor found at: {self.EXTRACT_II}')
        else:
            print('please build cg extractor firstly') 
            exit(1)
        if os.path.exists(self.MY_CLANG):
            print(f'use clang={self.MY_CLANG}')
        else:
            self.MY_CLANG = shutil.which('clang')
            if not self.MY_CLANG:
                print('please ensure there is clang in your environment')
                exit(1)
        if os.path.exists(self.MY_CLANG_PLUS_PLUS):
            print(f'use clang++={self.MY_CLANG_PLUS_PLUS}')
        else:
            self.MY_CLANG_PLUS_PLUS = shutil.which('clang++')
            if not self.MY_CLANG_PLUS_PLUS:
                print('please ensure there is clang++ in your environment')
                exit(1)
        
        self.DEFAULT_PANDA_COMMANDS = [
            self.PANDA, 
            '-j', str(self.analyze_opts.jobs), '--print-execution-time',
            '--cc', self.MY_CLANG, 
            '--cxx', self.MY_CLANG_PLUS_PLUS
        ]

        if self.inc_mode.value <= IncrementalMode.FileLevel.value:
            self.DEFAULT_PANDA_COMMANDS[5] = self.CLANG
            self.DEFAULT_PANDA_COMMANDS[7] = self.CLANG_PLUS_PLUS


class ArgumentParser:
    def __init__(self):
        self.parser = argparse.ArgumentParser(prog='IncAnalyzer', formatter_class=argparse.RawTextHelpFormatter)
        self.parser.add_argument('--inc', type=str, dest='inc', choices=['file', 'func', 'inline'], 
                                 help='Incremental analysis mode: file, func, inline')
        self.parser.add_argument('--verbose', action='store_true', dest='verbose', help='Record debug information.')
        self.parser.add_argument('--analyze', type=str, dest='analyze', choices=['ctu', 'no-ctu'],
                help='Execute Clang Static Analyzer.')
        self.parser.add_argument('-j', '--jobs', type=int, dest='jobs', default=1, help='Number of jobs can be executed in parallel.')
        self.parser.add_argument('-d', '--udp', action='store_true', dest='udp', help='Use files in diff path to `diff`.')
        self.parser.add_argument('--csa-config', type=str, dest='csa_config', default=None, help='Incremental analysis mode: file, func, inline')
    
    def parse_args(self, args):
        return self.parser.parse_args(args)