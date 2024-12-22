import shlex
from typing import List
import multiprocessing as mp
import subprocess
from subprocess import run
from abc import ABC, abstractmethod
import os
import concurrent.futures

from IncAnalysis.analyzer_config import *
from IncAnalysis.file_in_cdb import FileInCDB, FileKind
from IncAnalysis.utils import makedir, process_file_list, commands_to_shell_script
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
        
        # with mp.Pool(self.analyzer_config.env.analyze_opts.jobs) as p:
        #     for retcode in p.map(self.analyze_one_file, [i for i in self.file_list]):
        #         ret = ret and retcode
        
        # Open one process in every thread to simulate multi-process.
        ret = True
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.analyzer_config.jobs) as executor:
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

    def analyze_one_file(self, file: FileInCDB):
        compiler = self.analyzer_config.compilers[file.compile_command.language]
        commands = [compiler] + file.compile_command.arguments
        commands.extend(['--analyze', '-o', str(file.parent.csa_output_path)])
        commands.extend(self.analyzer_config.analyze_args())
        makedir(os.path.dirname(file.csa_file))
        # Add file specific args.
        if self.analyzer_config.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            if file.cf_num == 0 or file.rf_num == 0:
                logger.info(f"[{self.get_analyzer_name()} No Functions] Don't need to analyze {file.file_name}")
                return True
            if file.parent.incrementable and file.has_rf:
                commands.extend(['-Xanalyzer', f'-analyze-function-file={file.get_file_path(FileKind.RF)}'])
            if self.analyzer_config.inc_mode == IncrementalMode.InlineLevel:
                commands.extend(['-Xanalyzer', f'-analyzer-dump-fsum={file.get_file_path(FileKind.FS)}'])
        csa_script = commands_to_shell_script(commands)
        
        process = run(csa_script, shell=True, capture_output=True, text=True, cwd=file.compile_command.directory)
        logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {csa_script}")
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success] {file.file_name}")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {csa_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        # Record time cost.
        if process.stderr:
            for line in process.stderr.splitlines():
                if line.startswith("  Total Execution Time"):
                    file.csa_analyze_time = (line.split(' ')[5])
                    break
        return process.returncode == 0

class ClangTidy(Analyzer):
    def __init__(self, analyzer_config: ClangTidyConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)

    def analyze_one_file(self, file: FileInCDB):
        analyzer_cmd = [self.analyzer_config.clang_tidy]
        analyzer_cmd.extend(self.analyzer_config.analyze_args())
        analyzer_cmd.append(file.file_name)
        fix_path = file.get_file_path(FileKind.FIX)
        makedir(os.path.dirname(fix_path))
        analyzer_cmd.extend(['--export-fixes', fix_path])
        if self.analyzer_config.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            # TODO: add --line-filter to filter warnings related to diff lines.
            pass
        analyzer_cmd.append("--")
        analyzer_cmd.extend(file.compile_command.arguments)
        analyzer_cmd.extend(self.analyzer_config.compiler_warnings)

        clang_tidy_script = commands_to_shell_script(analyzer_cmd)

        process = run(clang_tidy_script, shell=True, capture_output=True, text=True, cwd=file.compile_command.directory)
        # logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {clang_tidy_script}")
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success] {file.file_name}")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {clang_tidy_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        return process.returncode == 0

class CppCheck(Analyzer):
    def __init__(self, analyzer_config: CppCheckConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.cppcheck = 'cppcheck'

    def analyze_all_files(self):
        # return super().analyze_all_files()
        # Just use `cppcheck --project=compile_commands.json --cppcheck-build-dir=cppcheck/build`
        # to analyze all files in compile_commands.json.
        if len(self.file_list) == 0:
            logger.debug(f"[{self.get_analyzer_name()}] No file need to analyze.")
            return True
        config = self.file_list[0].parent
        makedir(config.cppcheck_build_path)
        makedir(config.cppcheck_output_path)
        analyzer_cmd = [self.analyzer_config.cppcheck, f"--project={config.compile_database}", f"-j{config.env.analyze_opts.jobs}"]
        analyzer_cmd.append(f"--cppcheck-build-dir={config.cppcheck_build_path}")
        analyzer_cmd.append(f"--plist-output={config.cppcheck_output_path}")
        result_extname = ".json" if self.analyzer_config.Sarif else ".xml"
        analyzer_cmd.append(f"--output-file={config.cppcheck_output_path}/result{result_extname}")
        analyzer_cmd.extend(self.analyzer_config.analyze_args())

        cppcheck_script = commands_to_shell_script(analyzer_cmd)
        logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {cppcheck_script}")
        process = run(cppcheck_script, shell=True, capture_output=True, text=True, cwd=config.cppcheck_output_path)
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success]")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {cppcheck_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        return process.returncode == 0

    def analyze_one_file(self, file: FileInCDB):
        analyzer_cmd = [self.analyzer_config.cppcheck]
        analyzer_cmd.extend(self.analyzer_config.analyze_args())

        # Pass whitelisted parameters
        params = CppCheckConfig.parse_analyzer_config(file.compile_command.arguments)
        analyzer_cmd.extend(params)

        output_path = file.get_file_path(FileKind.CPPCHECK)
        makedir(output_path)
        analyzer_cmd.append('--plist-output=' + output_path)
        analyzer_cmd.append(file.file_name)

        cppcheck_script = commands_to_shell_script(analyzer_cmd)

        process = run(cppcheck_script, shell=True, capture_output=True, text=True, cwd=file.compile_command.directory)
        # logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {cppcheck_script}")
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success] {file.file_name}")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {cppcheck_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        return process.returncode == 0

class Infer(Analyzer):
    def __init__(self, analyzer_config: InferConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.infer = 'infer'

    def analyze_all_files(self):
        # return super().analyze_all_files()
        # Just use `infer --compilation-database` to analyze all files in compile_commands.json.
        if len(self.file_list) == 0:
            logger.debug(f"[{self.get_analyzer_name()}] No file need to analyze.")
            return True
        config = self.file_list[0].parent
        makedir(config.infer_output_path)
        analyzer_cmd = [self.analyzer_config.infer, "--compilation-database", f"{config.compile_database}", "-o", f"{config.infer_output_path}"]

        infer_script = commands_to_shell_script(analyzer_cmd)
        logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {infer_script}")
        process = run(infer_script, shell=True, capture_output=True, text=True, cwd=config.infer_output_path)
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success]")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {infer_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        return process.returncode == 0

    
    def analyze_one_file(self, file: FileInCDB):
        analyzer_cmd = [self.analyzer_config.infer, 'run', '--keep-going',
                        '--project-root', '/']
        analyzer_cmd.extend(self.analyzer_config.analyze_args())

        output_path = file.get_file_path(FileKind.INFER)
        makedir(output_path)
        analyzer_cmd.extend(['-o', output_path])
        analyzer_cmd.append("--")

        cmd_filtered = []

        if file.compile_command.origin_cmd is not None:
            for cmd in shlex.split(file.compile_command.origin_cmd):
                if IGNORED_OPTIONS_GCC.match(cmd) and \
                        file.compile_command.language in ['c', 'c++']:
                    continue
                cmd_filtered.append(cmd)

            if file.compile_command.language == 'c++':
                cmd_filtered.append('-stdlib=libc++')

            analyzer_cmd.extend(cmd_filtered)
        else:
            logger.debug(f"[Skip Infer Analyze] {file.file_name} doesn't have compile commands.")
            return False
        infer_script = commands_to_shell_script(analyzer_cmd)

        process = run(infer_script, shell=True, capture_output=True, text=True, cwd=file.compile_command.directory)
        # logger.debug(f"[{self.get_analyzer_name()} Analyze Script] {infer_script}")
        if process.returncode == 0:
            logger.info(f"[{self.get_analyzer_name()} Analyze Success] {file.file_name}")
        else:
            logger.error(f"[{self.get_analyzer_name()} Analyze Failed] {infer_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        return process.returncode == 0