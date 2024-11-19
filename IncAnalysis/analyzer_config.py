from enum import Enum, auto
import json
from abc import ABC, abstractmethod
from pathlib import Path

from IncAnalysis.environment import Environment, IncrementalMode

class AnalyzerConfig(ABC):
    def __init__(self, env: Environment, workspace: Path, config_file: str = None):
        super().__init__()
        self.json_config = {}
        self.env: Environment = env
        self.workspace: Path = workspace
        if config_file is not None:
            self.init_from_file(config_file)
    
    def init_from_file(self, config_file):
        with open(config_file, 'r') as f:
            self.json_config = json.load(f)
    
    @abstractmethod
    def analyze_args(self):
        return []

csa_default_config = {
    "CSAOptions": [
        # "-analyzer-disable-all-checks",
        # "-analyzer-opt-analyze-headers",
        "-analyzer-inline-max-stack-depth=5",
        "-analyzer-inlining-mode=noredundancy"
    ],
    "CSAConfig": [
        "crosscheck-with-z3=true",
        "mode=deep",
        "ipa=dynamic-bifurcate",
        "crosscheck-with-z3=true",
        "ctu-import-cpp-threshold=8",
        "ctu-import-threshold=24",
        "ipa-always-inline-size=3"
    ]
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
    def __init__(self, env: Environment, csa_path: Path, config_file: str=None):
        super().__init__(env, csa_path, config_file)
        if not config_file:
            self.config_json = csa_default_config
        # Options may influence incremental analysis.
        self.AnalyzeAll = False
        self.IPAMode = IPAKind.IPAK_DynamicDispatchBifurcate
        self.parse_config_json()

    def parse_config_json(self):
        self.csa_options = self.config_json.get("CSAOptions")
        if self.csa_options:
            for cmd in self.csa_options:
                cmd_pair = cmd.split("=")
                if cmd_pair[0] == "-analyzer-opt-analyze-headers":
                    self.AnalyzeAll = True
        else:
            self.csa_options = []
        self.csa_config = self.config_json.get("CSAConfig")
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
        else:
            self.csa_config = []
        
        self.csa_options.extend(['-analyzer-output=html', '-analyzer-disable-checker=deadcode'])
        if self.env.ctu:
            self.csa_config.extend([
                'experimental-enable-naive-ctu-analysis=true',
                'ctu-dir=' + str(self.workspace),
                'ctu-index-name=' + str(self.workspace / 'externalDefMap.txt'),
                'ctu-invocation-list=' + str(self.workspace / 'invocations.yaml')
            ])
            if self.env.analyze_opts.verbose:
                self.csa_config.append('display-ctu-progress=true')

    def analyze_args(self):
        args = ['--analyze', '-o', str(self.workspace / 'csa-reports')]
        for option in self.csa_options:
            args += ['-Xanalyzer', option]
        args += ['-Xanalyzer', '-analyzer-config', '-Xanalyzer', ','.join(self.csa_config)]
        return args
        