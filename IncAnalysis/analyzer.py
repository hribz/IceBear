from typing import List
import multiprocessing as mp
import subprocess as proc
from abc import ABC, abstractmethod

from IncAnalysis.analyzer_config import *
from IncAnalysis.file_in_cdb import FileInCDB, FileKind
from IncAnalysis.utils import makedir
from IncAnalysis.logger import logger

class Analyzer(ABC):
    def __init__(self, analyzer_config: AnalyzerConfig, file_list: List[FileInCDB]):
        super().__init__()
        self.analyzer_config: AnalyzerConfig = analyzer_config
        self.file_list: List[FileInCDB] = file_list
    
    @abstractmethod
    def analyze_one_file(self, file: FileInCDB):
        pass

    def analyze_all_files(self):
        makedir(self.analyzer_config.workspace)
        ret = True
        with mp.Pool(self.analyzer_config.env.analyze_opts.jobs) as p:
            for retcode in p.map(self.analyze_one_file, [i for i in self.file_list]):
                ret = ret and retcode
        return ret
    
    def get_analyzer_name(self):
        return self.__class__.__name__

class CSA(Analyzer):
    def __init__(self, analyzer_config: CSAConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        env = self.analyzer_config.env
        self.compilers = {
            'c': env.MY_CLANG,
            'c++': env.MY_CLANG_PLUS_PLUS
        }
        if env.inc_mode.value <= IncrementalMode.FileLevel.value:
            self.compilers = {
                'c': env.CLANG,
                'c++': env.CLANG_PLUS_PLUS
            }

    def analyze_one_file(self, file: FileInCDB):
        compiler = self.compilers[file.compile_command.language]
        commands = [compiler] + file.compile_command.arguments
        commands.extend(self.analyzer_config.analyze_args())
        # Add file specific args.
        if self.analyzer_config.env.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            if file.parent.incrementable:
                commands.extend(['-Xanalyzer', f'-analyze-function-file={file.get_file_path(FileKind.RF)}'])
            if self.analyzer_config.env.inc_mode == IncrementalMode.InlineLevel:
                commands.extend(['-Xanalyzer', f'-analyzer-dump-fsum={file.get_file_path(FileKind.FS)}'])
        with proc.Popen(commands, cwd=file.compile_command.directory) as p:
            ret = p.wait()
            if ret != 0:
                stdout = p.stdout.read().decode('utf-8') if p.stdout else ""
                stderr = p.stderr.read().decode('utf-8') if p.stderr else ""
                logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {commands}\nstdout:\n{stdout}\nstderr:\n{stderr}")
            else:
                logger.info(f"[{self.get_analyzer_name()} Analyze Success] {file.file_name}")                
        return ret == 0