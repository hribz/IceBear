from typing import List
import multiprocessing as mp
import subprocess
from subprocess import run
from abc import ABC, abstractmethod
import os
import concurrent.futures

from IncAnalysis.analyzer_config import *
from IncAnalysis.file_in_cdb import FileInCDB, FileKind
from IncAnalysis.utils import makedir, process_file_list
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
        for file in self.file_list:
            makedir(os.path.dirname(file.csa_file))
        ret = True
        
        # with mp.Pool(self.analyzer_config.env.analyze_opts.jobs) as p:
        #     for retcode in p.map(self.analyze_one_file, [i for i in self.file_list]):
        #         ret = ret and retcode
        
        # Open one process in every thread to simulate multi-process.
        ret = True
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.analyzer_config.env.analyze_opts.jobs) as executor:
            futures = [executor.submit(self.analyze_one_file, file) for file in self.file_list]

            for future in concurrent.futures.as_completed(futures):
                result = future.result()  # 获取任务结果，如果有的话
                ret = ret and result
        return ret
    
    def get_analyzer_name(self):
        return self.__class__.__name__

class CSA(Analyzer):
    def __init__(self, analyzer_config: CSAConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.analyzer_config: CSAConfig
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
            if file.cf_num == 0 or file.rf_num == 0:
                logger.info(f"[{self.get_analyzer_name()} No Functions] Don't need to analyze {file.file_name}")
                return True
            if file.parent.incrementable and file.has_rf:
                commands.extend(['-Xanalyzer', f'-analyze-function-file={file.get_file_path(FileKind.RF)}'])
            if self.analyzer_config.env.inc_mode == IncrementalMode.InlineLevel:
                commands.extend(['-Xanalyzer', f'-analyzer-dump-fsum={file.get_file_path(FileKind.FS)}'])
        csa_script = ' '.join(commands)
        
        process = run(csa_script, shell=True, capture_output=True, text=True, cwd=file.compile_command.directory)
        logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {csa_script}")
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success] {file.file_name}")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {' '.join(commands)}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        # Record time cost.
        if process.stderr:
            for line in process.stderr.splitlines():
                if line.startswith("  Total Execution Time"):
                    file.analyze_time = (line.split(' ')[5])
                    break
        return process.returncode == 0
    
class CppCheck(Analyzer):
    def __init__(self, analyzer_config: CppCheckConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.cppcheck = 'cppcheck'

    def analyze_one_file(self, file: FileInCDB):
        pass