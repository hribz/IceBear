import concurrent.futures
import os
import shlex
import shutil
import subprocess
from abc import ABC, abstractmethod
from subprocess import run
from typing import List

from IncAnalysis.analyzer_config import *
from IncAnalysis.file_in_cdb import FileInCDB, FileKind
from IncAnalysis.logger import logger
from IncAnalysis.process import Process
from IncAnalysis.utils import commands_to_shell_script, makedir


class Analyzer(ABC):
    def __init__(self, analyzer_config: AnalyzerConfig, file_list: List[FileInCDB]):
        super().__init__()
        self.analyzer_config: AnalyzerConfig = analyzer_config
        self.file_list: List[FileInCDB] = file_list

    @abstractmethod
    def get_analyzer_name(self):
        pass

    @abstractmethod
    def generate_analyzer_cmd(self, file: FileInCDB):
        pass

    def update_inc_mode(self, inc_mode: IncrementalMode):
        self.analyzer_config.inc_mode = inc_mode

    def analyze_all_files(self):
        makedir(str(self.analyzer_config.workspace))
        ret = True

        # with mp.Pool(self.analyzer_config.env.analyze_opts.jobs) as p:
        #     for retcode in p.map(self.analyze_one_file, [i for i in self.file_list]):
        #         ret = ret and retcode

        # Open one process in every thread to simulate multi-process.
        ret = True
        workers = self.analyzer_config.jobs
        if self.analyzer_config.max_workers > 0:
            workers = min(workers, self.analyzer_config.max_workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self.analyze_one_file, file) for file in self.file_list
            ]

            for idx, future in enumerate(
                concurrent.futures.as_completed(futures), start=1
            ):
                stat, file_identifier = future.result()
                logger.info(
                    f"[{self.get_analyzer_name()} ({self.analyzer_config.inc_mode}) Analyze {idx}/{len(self.file_list)}] [{stat}] {file_identifier}"
                )
                ret = ret and stat == Process.Stat.ok
        return ret

    def analyze_one_file(self, file: FileInCDB):
        analyzer_cmd = self.generate_analyzer_cmd(file)
        if analyzer_cmd is None:
            return Process.Stat.skipped, file.identifier
        script = commands_to_shell_script(analyzer_cmd)
        if not isinstance(self, ClangTidy):
            # ClangTidy commands are too long to be printed.
            logger.debug(
                f"[{self.get_analyzer_name()} ({self.analyzer_config.inc_mode}) Analyze Script] {script}"
            )

        process = Process(analyzer_cmd, file.compile_command.directory)
        file.analyzers_time[f"{self.get_analyzer_name()} ({self.analyzer_config.inc_mode})"] = process.timecost  # type: ignore
        if process.stat == Process.Stat.ok:
            stat = Process.Stat.ok
            # logger.debug(f"[{self.get_analyzer_name()} ({self.analyzer_config.inc_mode}) Analyze OK]\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}")
        else:
            stat = (process.stat)[0]
            logger.error(
                f"[{self.get_analyzer_name()} ({self.analyzer_config.inc_mode}) Analyze {stat}] {script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}"
            )

        # Record time cost.
        if isinstance(self, CSA):
            if process.stderr:
                for line in process.stderr.splitlines():
                    if line.startswith("  Total Execution Time"):  # type: ignore
                        file.csa_analyze_time = line.split(" ")[5]  # type: ignore
                        break
        elif isinstance(self, GSA):
            if process.stat == Process.Stat.ok and process.stderr:
                makedir(file.parent.gsa_output_path)
                with open(file.get_file_path(FileKind.GCC), "w") as f:
                    f.write(process.stderr)  # type: ignore
        return stat, file.identifier

    @staticmethod
    def __str_to_analyzer_class__(analyzer_name: str):
        if analyzer_name == "clangsa":
            return CSA
        elif analyzer_name == "clang-tidy":
            return ClangTidy
        elif analyzer_name == "cppcheck":
            return CppCheck
        elif analyzer_name == "infer":
            return Infer
        elif analyzer_name == "gsa":
            return GSA
        else:
            return None


class CSA(Analyzer):
    def __init__(self, analyzer_config: CSAConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.analyzer_config: CSAConfig

    def generate_analyzer_cmd(self, file: FileInCDB):
        compiler = self.analyzer_config.compilers[file.compile_command.language]
        analyzer_cmd = (
            [compiler] + file.compile_command.arguments + ["-Qunused-arguments"]
        )
        output_path = str(file.parent.csa_output_path / file.identifier[1:])
        makedir(output_path)
        analyzer_cmd.extend(["--analyze", "-o", output_path])
        analyzer_cmd.extend(self.analyzer_config.analyze_args())
        # Add file specific args.
        if self.analyzer_config.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            if file.cf_num == 0 or file.rf_num == 0:
                logger.debug(
                    f"[{__class__.__name__} No Functions] Don't need to analyze {file.identifier}"
                )
                return None
            if file.parent.incrementable and file.has_rf:
                analyzer_cmd.extend(
                    [
                        "-Xanalyzer",
                        f"-analyze-function-file={file.get_file_path(FileKind.RF)}",
                    ]
                )
            if self.analyzer_config.inc_mode == IncrementalMode.InlineLevel:
                makedir(os.path.dirname(file.csa_file))
                analyzer_cmd.extend(
                    [
                        "-Xanalyzer",
                        f"-analyzer-dump-fsum={file.get_file_path(FileKind.FS)}",
                    ]
                )
        return analyzer_cmd

    def get_analyzer_name(self):
        return __class__.__name__


class ClangTidy(Analyzer):
    def __init__(self, analyzer_config: ClangTidyConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.analyzer_config: ClangTidyConfig

    def generate_analyzer_cmd(self, file):
        analyzer_cmd = [self.analyzer_config.clang_tidy]
        analyzer_cmd.extend(self.analyzer_config.analyze_args())
        analyzer_cmd.append(file.file_name)
        fix_path = file.get_file_path(FileKind.FIX)
        makedir(os.path.dirname(fix_path))
        analyzer_cmd.extend(["--export-fixes", fix_path])
        if self.analyzer_config.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            # TODO: add --line-filter to filter warnings related to diff lines.
            anr_file = file.get_file_path(FileKind.ANR)
            # If ANR file doesn't exist, meaning it's a new file, do not filter its results.
            if file.parent.incrementable and os.path.exists(anr_file):
                line_filter_json = []
                with open(anr_file, "r") as f:
                    for line in f.readlines():
                        line = line.strip()
                        if len(line) == 0:
                            continue
                        if line.endswith(":"):
                            filename = line[:-1]
                            line_filter_json.append({"name": filename, "lines": []})
                        else:
                            for s_and_e in line.split(";"):
                                if len(s_and_e) != 0:
                                    line_filter_json[-1]["lines"].append(
                                        [int(i) for i in s_and_e.split(",")]
                                    )
                if len(line_filter_json) == 0:
                    logger.debug(
                        f"[{__class__.__name__} No ANR] Don't need to analyze {file.identifier}"
                    )
                    return None
                line_filter_str = json.dumps(line_filter_json, separators=(",", ":"))
                analyzer_cmd.append("-line-filter=" + line_filter_str)
        analyzer_cmd.append("--")
        analyzer_cmd.extend(file.compile_command.arguments)
        analyzer_cmd.extend(self.analyzer_config.compiler_warnings)
        return analyzer_cmd

    def get_analyzer_name(self):
        return __class__.__name__


class CppCheck(Analyzer):
    def __init__(self, analyzer_config: CppCheckConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.analyzer_config: CppCheckConfig
        self.cppcheck = "cppcheck"

    def merge_all_cppcheckrf(self, output_file):
        with open(output_file, "w") as out_file:
            for file in self.file_list:
                cpprf_file = file.get_file_path(FileKind.CPPRF)
                if os.path.exists(cpprf_file):
                    with open(cpprf_file, "r") as in_file:
                        shutil.copyfileobj(in_file, out_file)

    def parse_analysis_time(self, output):
        if not output:
            return
        file_to_idx = {file.file_name: idx for idx, file in enumerate(self.file_list)}
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("Check time:"):
                line_split = line.split(" ")
                file_name = line_split[2][:-1]
                analysis_time = float(line_split[3][:-1])
                self.file_list[file_to_idx[file_name]].analyzers_time[
                    f"{self.get_analyzer_name()} ({self.analyzer_config.inc_mode})"
                ] += analysis_time

    def analyze_all_files(self):
        # return super().analyze_all_files()
        # Just use `cppcheck --project=compile_commands.json --cppcheck-build-dir=cppcheck/build`
        # to analyze all files in compile_commands.json.
        if len(self.file_list) == 0:
            logger.debug(f"[{__class__.__name__}] No file need to analyze.")
            return True
        config = self.file_list[0].parent
        makedir(str(config.cppcheck_build_path))
        makedir(str(config.cppcheck_output_path))
        cdb = (
            config.compile_commands_used_by_analyzers
            if self.analyzer_config.inc_mode != IncrementalMode.NoInc
            else config.compile_database
        )
        analyzer_cmd = [
            self.analyzer_config.cppcheck,
            f"--project={cdb}",
            f"-j{config.env.analyze_opts.jobs}",
        ]
        analyzer_cmd.append("--showtime=file-total")
        analyzer_cmd.append(f"--cppcheck-build-dir={config.cppcheck_build_path}")
        # analyzer_cmd.append(f"--plist-output={config.cppcheck_output_path}")
        result_extname = ".json" if self.analyzer_config.Sarif else ".xml"
        analyzer_cmd.append(
            f"--output-file={config.cppcheck_output_path}/result{result_extname}"
        )
        if self.analyzer_config.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            all_cppcheckrf = str(config.preprocess_path / "cppcheck.cpprf")
            if config.incrementable:
                self.merge_all_cppcheckrf(all_cppcheckrf)
                analyzer_cmd.append(f"--analyze-function-file={all_cppcheckrf}")
        analyzer_cmd.extend(self.analyzer_config.analyze_args())

        cppcheck_script = commands_to_shell_script(analyzer_cmd)
        logger.info("[Cppcheck Analyzing] ......")
        logger.info(
            f"[{__class__.__name__} ({self.analyzer_config.inc_mode}) Analyze Script] {cppcheck_script}"
        )
        process = run(
            analyzer_cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=config.cppcheck_output_path,
        )
        logger.info(f"[{__class__.__name__} Stdout] {process.stdout}")
        # logger.info(f"[{__class__.__name__} Stderr] {process.stderr}")
        self.parse_analysis_time(process.stdout)
        if process.returncode == 0:
            logger.info(
                f"[{__class__.__name__} ({self.analyzer_config.inc_mode}) Analyze Success]"
            )
        else:
            logger.error(
                f"[{__class__.__name__} ({self.analyzer_config.inc_mode}) Analyze Failed]"
            )
        return process.returncode == 0

    def generate_analyzer_cmd(self, file: FileInCDB):
        analyzer_cmd = [self.analyzer_config.cppcheck]
        analyzer_cmd.extend(self.analyzer_config.analyze_args())

        # Pass whitelisted parameters
        params = CppCheckConfig.parse_analyzer_config(file.compile_command.arguments)
        analyzer_cmd.extend(params)

        output_path = file.get_file_path(FileKind.CPPCHECK)
        makedir(output_path)
        analyzer_cmd.append("--plist-output=" + output_path)
        analyzer_cmd.append(file.file_name)
        return analyzer_cmd

    def get_analyzer_name(self):
        return __class__.__name__


class Infer(Analyzer):
    def __init__(self, analyzer_config: InferConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.analyzer_config: InferConfig
        self.infer = "infer"

    def analyze_all_files(self):
        # return super().analyze_all_files()
        # Just use `infer --compilation-database` to analyze all files in compile_commands.json.
        if len(self.file_list) == 0:
            logger.debug(f"[{__class__.__name__}] No file need to analyze.")
            return True
        config = self.file_list[0].parent
        makedir(config.infer_output_path)
        cdb = (
            config.compile_commands_used_by_analyzers
            if self.analyzer_config.inc_mode != IncrementalMode.NoInc
            else config.compile_database
        )
        analyzer_cmd = [
            self.analyzer_config.infer,
            "--compilation-database",
            f"{cdb}",
            "-o",
            f"{config.infer_output_path}",
        ]

        infer_script = commands_to_shell_script(analyzer_cmd)
        logger.debug(
            f"[{__class__.__name__} ({self.analyzer_config.inc_mode}) Analyze Script] {infer_script}"
        )
        process = run(
            infer_script,
            shell=True,
            capture_output=True,
            text=True,
            cwd=config.infer_output_path,
        )
        if process.returncode == 0:
            logger.info(
                f"[{__class__.__name__} ({self.analyzer_config.inc_mode}) Analyze Success]"
            )
        else:
            logger.error(
                f"[{__class__.__name__} ({self.analyzer_config.inc_mode}) Analyze Failed] {infer_script}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}"
            )
        return process.returncode == 0

    def generate_analyzer_cmd(self, file: FileInCDB):
        analyzer_cmd = [
            self.analyzer_config.infer,
            "run",
            "--keep-going",
            "--project-root",
            "/",
        ]
        analyzer_cmd.extend(self.analyzer_config.analyze_args())

        output_path = file.get_file_path(FileKind.INFER)
        makedir(output_path)
        analyzer_cmd.extend(["-o", output_path])
        analyzer_cmd.append("--")

        cmd_filtered = []

        if file.compile_command.origin_cmd is not None:
            for cmd in shlex.split(file.compile_command.origin_cmd):
                if IGNORED_OPTIONS_GCC.match(cmd) and file.compile_command.language in [
                    "c",
                    "c++",
                ]:
                    continue
                cmd_filtered.append(cmd)

            if file.compile_command.language == "c++":
                cmd_filtered.append("-stdlib=libc++")

            analyzer_cmd.extend(cmd_filtered)
        else:
            logger.debug(
                f"[Skip Infer Analyze] {file.file_name} doesn't have compile commands."
            )
            return None
        return analyzer_cmd

    def get_analyzer_name(self):
        return __class__.__name__


class GSA(Analyzer):
    def __init__(self, analyzer_config: GSAConfig, file_list: List[FileInCDB]):
        super().__init__(analyzer_config, file_list)
        self.analyzer_config: GSAConfig
        self.clang_to_gcc = {
            "-fopenmp=libomp": "-fopenmp",
            "-stdlib=libc++": "-lstdc++",
            "-flto=thin": "-flto",
            "-mllvm": None,
            "-fcoroutines-ts": "-fcoroutines",
            "-fopenacc": None,
            "-static-libstdc++": None,
            "-rdynamic": "-Wl,-export-dynamic",
            "-foptimize-sibling-calls": None,
            "-fmodules": None,
            "-fprofile-instr-generate": "-fprofile-generate",
            "-fprofile-instr-use": "-fprofile-use",
            "-fcolor-diagnostics": "-fdiagnostics-color=always",
            "-Xclang": None,
            "-Qunused-arguments": None,
        }
        self.skip_argument_headers = [
            "-fsanitize",
            "-mstack-alignment",
            "-fdeclspec",
            "-W",
        ]

    def generate_analyzer_cmd(self, file: FileInCDB):
        compiler = self.analyzer_config.compilers[file.compile_command.language]
        analyzer_cmd = [compiler] + ["-fanalyzer", "-c", "-o/dev/null"]
        analyzer_cmd.append("-O0")
        for argument in file.compile_command.arguments:
            skip_argument = False
            for skip_header in self.skip_argument_headers:
                if argument.startswith(skip_header):
                    skip_argument = True
                    break
            if skip_argument:
                continue
            if argument in self.clang_to_gcc:
                if self.clang_to_gcc[argument] is not None:
                    analyzer_cmd.append(self.clang_to_gcc[argument])
            elif argument.startswith("-O"):
                # Optimization level will affect GSA results, replace all '-O*' to '-O0'
                continue
            else:
                analyzer_cmd.append(argument)
        analyzer_cmd.extend(self.analyzer_config.analyze_args())
        # Add file specific args.
        if self.analyzer_config.inc_mode.value >= IncrementalMode.FuncitonLevel.value:
            if file.cf_num == 0 or file.rf_num == 0:
                logger.debug(
                    f"[{__class__.__name__} No Functions] Don't need to analyze {file.identifier}"
                )
                return None
            if file.parent.incrementable and file.has_rf:
                analyzer_cmd.extend(
                    [
                        f"--param=analyzer-function-file={file.get_file_path(FileKind.GCCRF)}"
                    ]
                )
        return analyzer_cmd

    def get_analyzer_name(self):
        return __class__.__name__
