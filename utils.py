import argparse
from pathlib import Path
import os
import shutil
from logger import logger
from enum import Enum, auto
from typing import List
import re

class Environment:
    def __init__(self, opts):
        self.analyze_opts = opts
        # Environment path
        self.PWD = Path(".").absolute()
        self.EXTRACT_II = str(self.PWD / 'build/clang_tool/collectIncInfo')
        self.EXTRACT_CG = str(self.PWD / 'build/clang_tool/extractCG')
        self.PANDA = str(self.PWD / 'panda/panda')
        # CSA revised version
        self.MY_CLANG = 'clang'
        self.MY_CLANG_PLUS_PLUS = 'clang++'
        self.CLANG = 'clang-19'
        self.CLANG_PLUS_PLUS = 'clang++-19'
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
            '--cc', self.CLANG, 
            '--cxx', self.CLANG_PLUS_PLUS
        ]

class ArgumentParser:
    def __init__(self):
        self.parser = argparse.ArgumentParser(prog='IncAnalyzer', formatter_class=argparse.RawTextHelpFormatter)
        self.parser.add_argument('-d', '--dir', default='.', help="Path of Source Files")
        self.parser.add_argument('-b', '--build', default='./build', help='Path of Build Directory')
        self.parser.add_argument('-n', '--name', help='name of the project')
        self.parser.add_argument('--inc', action='store_true', dest='inc', help='Incremental analyze all sessions.')
        self.parser.add_argument('--verbose', action='store_true', dest='verbose', help='Record debug information.')
        self.parser.add_argument('--analyze', type=str, dest='analyze', choices=['ctu', 'no-ctu'],
                help='Execute Clang Static Analyzer.')
        self.parser.add_argument('--fsum', action='store_true', dest='fsum', help='Generate function summary files.')
        self.parser.add_argument('--use_fsum', action='store_true', dest='use_fsum', help='Generate function summary files.')
        self.parser.add_argument('-j', '--jobs', type=int, dest='jobs', default=1, help='Number of jobs can be executed in parallel.')
    
    def parse_args(self, args):
        return self.parser.parse_args(args)

def makedir(path: str):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except FileExistsError:  # may happen when multi-thread
            pass

def remake_dir(path: Path, debug_TAG=None):
    if path.exists():
        if debug_TAG:
            logger.debug(f"{debug_TAG} remove: {path}")
        shutil.rmtree(path)
    os.makedirs(path)

class SessionStatus(Enum):
    Skipped = auto()
    Success = auto()
    Failed = auto()

class FileKind(Enum):
    Preprocessed = auto()
    DIFF = auto()
    AST = auto()
    EFM = auto()
    CG = auto()
    CF = auto()
    RF = auto()
    FS = auto()


def getExtDefMap(efmfile): return open(efmfile).read()

def virtualCall(file, method, has_arg, arg = None): 
    if has_arg:
        getattr(file, method.__name__)(arg)
    else:
        getattr(file, method.__name__)()

def replace_loc_info(pair):
    src, dest = pair
    try:
        pattern = re.compile(r'^# \d+')
        with open(src, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = ["\n" if pattern.match(line) else line for line in lines]
        makedir(os.path.dirname(dest))
        with open(dest, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Error processing {src}: {e}")

def get_origin_file_name(file:str, prefix: List[str], extnames: List[str]):
    file = file[len(prefix):]
    for ext in extnames:
        if file.endswith(ext):
            file = file[:-len(ext)]
            break
    return file

def parse_efm(efmline: str):
    efmline = efmline.strip()
    if not efmline:
        return None, None
    try: # The new "<usr-length>:<usr> <path>" format (D102669).
        lenlen = efmline.find(':')
        usrlen = int(efmline[:lenlen])
        usr = efmline[:lenlen + usrlen + 1]
        path = efmline[lenlen + usrlen + 2:]
        return usr, path
    except ValueError: # When <usr-length> is not available.
        efmitem = efmline.split(' ')
        if len(efmitem) == 2:
            return efmitem[0], efmitem[1]
        logger.error(f"[Parse EFM] efmline {efmline} format error.")
        return None, None