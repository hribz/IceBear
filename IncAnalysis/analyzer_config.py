from enum import Enum, auto
import json
from abc import ABC, abstractmethod
import os
from pathlib import Path
from typing import Optional
import tempfile

from IncAnalysis.environment import Environment, IncrementalMode
from IncAnalysis.analyzer_utils import *
from IncAnalysis.utils import remove_file

class AnalyzerConfig(ABC):
    def __init__(self, env: Environment, workspace: Path, checker_file: Optional[str] = None, config_file: Optional[str] = None):
        super().__init__()
        self.json_config = {}
        self.json_checkers = None

        self.inc_mode: IncrementalMode = env.inc_mode
        self.ctu = env.ctu
        self.jobs = env.analyze_opts.jobs
        self.verbose = env.analyze_opts.verbose

        self.workspace: Path = workspace
        self.args = None
        self.ready_to_run = True
        self.max_workers = -1 # The max parallel workers for this analyzer, -1 means no limit.
        if config_file is not None:
            self.init_from_file(config_file)
        if checker_file is not None:
            self.load_checkers(checker_file)
    
    def init_from_file(self, config_file):
        with open(config_file, 'r') as f:
            self.json_config = json.load(f)
    
    def load_checkers(self, checker_file):
        with open(checker_file, 'r') as f:
            self.json_checkers = json.load(f)

    @abstractmethod
    def analyze_args(self):
        # Arguments shared between every file.
        return []

csa_default_config = {
    "CSAOptions": [
        # "-analyzer-disable-all-checks",
        # "-analyzer-opt-analyze-headers",
        # "-analyzer-inline-max-stack-depth=5",
        # "-analyzer-inlining-mode=noredundancy",
        "-analyzer-note-analysis-entry-points",
        "-analyzer-disable-checker=deadcode",
        "-analyzer-stats", # Output time cost.
    ],
    "CSAConfig": [
        "crosscheck-with-z3=false",
        "expand-macros=true",
        "unroll-loops=true",
        # "mode=deep",
        # "ipa=dynamic-bifurcate",
        # "ctu-import-cpp-threshold=8",
        # "ctu-import-threshold=24",
        # "ipa-always-inline-size=3",
    ]
}

cppcheck_default_config = [
    "--check-level=exhaustive",
    "--max-ctu-depth=2",
    "--output-format=sarif"
]

clang_tidy_default_config = {
    "HeaderFilterRegex": ".*"
}

infer_default_config = {
}

gsa_default_config = {
}

class IPAKind(Enum):
    # Perform only intra-procedural analysis.
    IPAK_None = auto(),
    # Inline C functions and blocks when their definitions are available.
    IPAK_BasicInlining = auto(),
    # Inline callees(C, C++, ObjC) when their definitions are available.
    IPAK_Inlining = auto(),
    # Enable inlining of dynamically dispatched methods.
    IPAK_DynamicDispatch = auto(),
    # Enable inlining of dynamically dispatched methods, bifurcate paths when
    # exact type info is unavailable.
    IPAK_DynamicDispatchBifurcate = auto()

class CSAConfig(AnalyzerConfig):
    def __init__(self, env: Environment, csa_workspace: Path, config_file: Optional[str]=None):
        checker_file = str(env.PWD / "config/clangsa_checkers.json")
        super().__init__(env, csa_workspace, checker_file, config_file)
        self.compilers = {
            'c': env.CLANG,
            'c++': env.CLANG_PLUS_PLUS
        }
        if not os.path.exists(env.CLANG) or not os.path.exists(env.CLANG_PLUS_PLUS): # type: ignore
            logger.error(f"CSA need command `clang/clang++` exists in environment.")
            self.ready_to_run = False
        self.inc_level_check()

        if not config_file:
            self.json_config = csa_default_config.copy()
        # Options may influence incremental analysis.
        self.AnalyzeAll = False
        self.IPAMode = IPAKind.IPAK_DynamicDispatchBifurcate
        self.CTUImportCppThreshold = 8
        self.CTUImportThreshold = 24
        self.parse_json_config()

    def inc_level_check(self):
        # func/inline-level incremental mode need to build custom Clang from 'llvm-project-ica'.
        if self.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            clang = self.compilers['c']
            result = subprocess.check_output([clang, '-cc1', '-help'], universal_newlines=True, encoding="utf-8")
            
            func_level_enable = False
            inline_level_enable = False

            for line in result.splitlines():
                line = line.strip()
                if line.startswith('-analyze-function-file'):
                    func_level_enable = True
                if line.startswith('-analyzer-dump-fsum'):
                    inline_level_enable = True
            
            if self.inc_mode == IncrementalMode.FuncitonLevel and not func_level_enable:
                logger.error(f"[CSA Inc Level Check] Please use customized clang build from llvm-project-ica,"
                             " and make sure there is `-analyze-function-file` in `clang -cc1 -help`'s output.")
                self.ready_to_run = False
            if self.inc_mode == IncrementalMode.InlineLevel and not inline_level_enable:
                logger.error(f"[CSA Inc Level Check] Please use customized clang build from llvm-project-ica,"
                             " and make sure there are `-analyze-function-file` and `-analyzer-dump-fsum` in `clang -cc1 -help`'s output.")
                self.ready_to_run = False

    def parse_json_config(self):
        self.csa_options = []
        # checker options place before CSAOptions, to make sure
        # -analyzer-disable-checker comes into effect.
        if self.json_checkers is not None:
            enable_checkers = CSAUtils.get_enable_checkers(self.compilers['c'], self.json_checkers)
            self.csa_options.extend(['-analyzer-checker=' + ','.join(enable_checkers)])

        json_config = self.json_config.get("CSAOptions")
        if json_config:
            for cmd in self.json_config:
                cmd = cmd.split()
                if cmd == "-analyzer-opt-analyze-headers":
                    self.AnalyzeAll = True
            self.csa_options.extend(json_config)

        self.csa_config = self.json_config["CSAConfig"]
        if self.csa_config:
            for cmd in self.csa_config:
                cmd_pair = cmd.split("=")
                if cmd_pair[0] == "ipa":
                    if cmd_pair[1] == "none":
                        self.IPAMode = IPAKind.IPAK_None 
                    elif cmd_pair[1] == "basic-inlining":
                        self.IPAMode = IPAKind.IPAK_BasicInlining
                    elif cmd_pair[1] == "inlining":
                        self.IPAMode = IPAKind.IPAK_Inlining
                    elif cmd_pair[1] == "dynamic":
                        self.IPAMode = IPAKind.IPAK_DynamicDispatch
                    elif cmd_pair[1] == "dynamic-bifurcate":
                        self.IPAMode = IPAKind.IPAK_DynamicDispatchBifurcate
                elif cmd_pair[0] == 'ctu-import-cpp-threshold':
                    self.CTUImportCppThreshold = int(cmd_pair[1])
                elif cmd_pair[0] == 'ctu-import-threshold':
                    self.CTUImportThreshold = int(cmd_pair[1])
        else:
            self.csa_config = []
        self.csa_config.extend(["aggressive-binary-operation-simplification=true"])
        
        self.csa_options.append('-analyzer-output=html')
        # self.csa_options.append('-analyzer-disable-checker=deadcode')

        if self.ctu:
            self.csa_config.extend([
                'experimental-enable-naive-ctu-analysis=true',
                'ctu-dir=' + str(self.workspace),
                'ctu-index-name=' + str(self.workspace / 'externalDefMap.txt'),
                'ctu-invocation-list=' + str(self.workspace / 'invocations.yaml')
            ])
            if self.verbose:
                self.csa_config.append('display-ctu-progress=true')

    def analyze_args(self):
        if self.args is not None:
            return self.args
        self.args = []
        for option in self.csa_options:
            self.args += ['-Xanalyzer', option]
        if len(self.csa_config) > 0:
            self.args += ['-Xanalyzer', '-analyzer-config', '-Xanalyzer', ','.join(self.csa_config)]
        return self.args
        
class ClangTidyConfig(AnalyzerConfig):
    def __init__(self, env: Environment, clang_tidy_workspace: Path, config_file: Optional[str]=None):
        checker_file = str(env.PWD / "config/clang-tidy_checkers.json")
        super().__init__(env, clang_tidy_workspace, checker_file, config_file)

        self.clang_tidy = env.clang_tidy
        self.diagtool = env.diagtool
        if not os.path.exists(env.clang_tidy):
            logger.error(f"Clang-tidy need command `clang-tidy` exists in environment.")
            self.ready_to_run = False

        if not config_file:
            self.json_config = clang_tidy_default_config.copy()
        self.checkers = []
        self.compiler_warnings = []
        self.parse_json_config()

    def parse_json_config(self):
        if self.json_checkers is not None:
            self.checkers, self.compiler_warnings = ClangTidyUtils.get_checkers_and_warning(self.clang_tidy, self.diagtool, self.json_checkers)

    def analyze_args(self):
        if self.args is not None:
            return self.args
        self.args = []
        if len(self.checkers)>0:
            self.args.append(f"-checks={','.join(self.checkers)}")
        self.args.append("-config=" + str(clang_tidy_default_config))
        return self.args

class CppCheckConfig(AnalyzerConfig):
    def __init__(self, env: Environment, cppcheck_workspace: Path, config_file: Optional[str]=None):
        checker_file = str(env.PWD / "config/cppcheck_checkers.json")
        super().__init__(env, cppcheck_workspace, checker_file, config_file)

        self.cppcheck = env.cppcheck
        if env.cppcheck is None or not os.path.exists(env.cppcheck):
            logger.error(f"Cppcheck need command `cppcheck` exists in environment.")
            self.ready_to_run = False
        self.inc_level_check()        

        if not config_file:
            self.json_config = cppcheck_default_config.copy()
        self.disable_checkers = []
        self.MaxCTUDepth = 2
        self.Sarif = True # Generate sarif format result file defaultly.
        self.parse_json_config()

    def inc_level_check(self):
        # func/inline-level incremental mode need to build custom Cppcheck from 'cppcheck-ica'.
        if self.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            cppcheck = self.cppcheck
            if cppcheck is None:
                return
            result = subprocess.check_output([cppcheck, '--help'], universal_newlines=True, encoding="utf-8")
            
            func_level_enable = False

            for line in result.splitlines():
                line = line.strip()
                if line.startswith('--analyze-function-file'):
                    func_level_enable = True
            
            if self.inc_mode == IncrementalMode.FuncitonLevel and not func_level_enable:
                logger.error(f"[Cppcheck Inc Level Check] Please use customized cppcheck build from cppcheck-ica,"
                             " and make sure there is `--analyze-function-file` in `cppcheck --help`'s output.")
                self.ready_to_run = False

    def parse_json_config(self):
        if self.json_checkers is not None:
            self.disable_checkers = CppCheckUtils.get_disable_checkers(self.cppcheck, self.json_checkers)
        if self.json_config:
            for config in self.json_config:
                cmd_pair = config.split("=")
                if cmd_pair[0] == '--max-ctu-depth':
                    self.MaxCTUDepth = int(cmd_pair[1])
                elif cmd_pair[0] == '--output-format':
                    if cmd_pair[1] == 'sarif':
                        self.Sarif = True
                    else:
                        self.Sarif = False

    @staticmethod
    def parse_analyzer_config(analyzer_options):
        return CppCheckUtils.parse_analyzer_config(analyzer_options)

    def analyze_args(self):
        if self.args is not None:
            return self.args
        self.args = list(self.json_config)
        self.args.append('--enable=all')
        
        if len(self.disable_checkers) > 0:
            for checker_name in self.disable_checkers:
                if checker_name.startswith("cppcheck-"):
                    checker_name = checker_name[9:]
                self.args.append('--suppress=' + checker_name)
        
        # unusedFunction check is for whole program analysis,
        # which is not compatible with per source file analysis.
        # self.args.append('--suppress=unusedFunction')

        return self.args
    
class InferConfig(AnalyzerConfig):
    def __init__(self, env: Environment, infer_workspace: Path, config_file: Optional[str]=None, checker_file: str="config/infer_checkers.json"):
        super().__init__(env, infer_workspace, checker_file, config_file)

        self.infer = env.infer
        if env.infer is None or not os.path.exists(env.infer):
            logger.error(f"infer need command `infer` exists in environment.")
            self.ready_to_run = False

        if not config_file:
            self.json_config = infer_default_config.copy()
        self.parse_json_config()

    def parse_json_config(self):
        pass

    def analyze_args(self):
        if self.args is not None:
            return self.args
        self.args = []

        return self.args
    
class GSAConfig(AnalyzerConfig):
    def __init__(self, env: Environment, gsa_workspace: Path, config_file: Optional[str]=None, checker_file: str="config/gsa_checkers.json"):
        checker_file = str(env.PWD / "config/gsa_checkers.json")
        super().__init__(env, gsa_workspace, checker_file, config_file)
        self.max_workers = 4 # GCC Static Analyzer doesn't scale well.
        self.compilers = {
            'c': env.GCC,
            'c++': env.GXX
        }
        if not os.path.exists(env.GCC) or not os.path.exists(env.GCC): # type: ignore
            logger.error(f"GSA need command `gcc/g++` exists in environment.")
            self.ready_to_run = False
        self.inc_level_check()

        if not config_file:
            self.json_config = gsa_default_config.copy()

    def inc_level_check(self):
        # func-level incremental mode need to build custom gcc from 'gcc-ica'.
        if self.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            gcc = self.compilers['c']
            with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tmp_file:
                param_value = tmp_file.name
            with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as main_file:
                main_file_path = main_file.name
                main_file.write("int main() { return 0; }".encode())
            
            result = subprocess.run([gcc, f'--param=analyzer-function-file={param_value}', '-x', 'c', '-o/dev/null', main_file_path],
                text=True,
                capture_output=True,
                timeout=5
            )
            func_level_enable = result.returncode == 0
            if not func_level_enable:
                logger.error(f"[GSA Inc Level Check] {result.stderr}")
            
            os.unlink(param_value)
            os.unlink(main_file_path)
            
            if self.inc_mode == IncrementalMode.FuncitonLevel and not func_level_enable:
                logger.error(f"[GSA Inc Level Check] Please use customized gcc build from gcc-ica,"
                             " and make sure `gcc --param=analyzer-function-file=file.tmp -x -c -o/dev/null main.c`"
                             " returncode is right.")
                self.ready_to_run = False
    
    def analyze_args(self):
        if self.args is not None:
            return self.args
        self.args = []
        self.args.append('-fdiagnostics-format=sarif-stderr')
        self.args.append('-Wno-analyzer-too-complex')
        return self.args