# -------------------------------------------------------------------------
#
#  Part of the CodeChecker project, under the Apache License v2.0 with
#  LLVM Exceptions. See LICENSE for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# -------------------------------------------------------------------------

# Modified by Yu Xiao for IceBear analysis configuration on 2024-12-17.

from enum import Enum
import re
import subprocess
from typing import Iterable, List, Set, Tuple
from abc import ABCMeta, abstractmethod
import xml.etree.ElementTree as ET

from IncAnalysis.logger import logger
from IncAnalysis.environment import Environment

# The functions in this file is copy from CodeChecker, to make sure
# analyzer behavior is same as CodeChecker.


class CheckerType(Enum):
    ANALYZER = 0  # A checker which is not a compiler warning.
    COMPILER = 1  # A checker which specified as "-W<name>" or "-Wno-<name>".


class CheckerState(Enum):
    DISABLED = 1
    ENABLED = 2


def determine_checkers_state(checkers, json_checkers):
    checkers_and_state = []
    for checker_name, _ in checkers:
        check_info = json_checkers["labels"].get(checker_name)
        if check_info and "profile:default" in check_info:
            # Only turn on default checkers.
            checkers_and_state.append((checker_name, CheckerState.ENABLED))
        else:
            checkers_and_state.append((checker_name, CheckerState.DISABLED))
    return checkers_and_state


def index_of(iterable, lambda_func) -> int:
    """Return the index of the first element in iterable for which
    lambda_func returns True.
    """
    for i, item in enumerate(iterable):
        if lambda_func(item):
            return i

    return -1


class CSAUtils:
    @staticmethod
    def get_enable_checkers(clang, json_checkers):
        checkers = CSAUtils.get_analyzer_checkers(clang)
        checkers_and_state = determine_checkers_state(checkers, json_checkers)
        return [
            checker[0]
            for checker in list(
                filter(lambda x: x[1] == CheckerState.ENABLED, checkers_and_state)
            )
        ]

    # Copy from CodeChecker analyzer/codechecker_analyzer/analyzers/clangsa/analyzer.py
    @staticmethod
    def get_analyzer_checkers(
        compiler: str, alpha: bool = True, debug: bool = False
    ) -> List[str]:
        """
        Return the list of the supported checkers.
        """
        command = [compiler, "-cc1"]

        command.append("-analyzer-checker-help")
        if alpha:
            command.append("-analyzer-checker-help-alpha")
        if debug:
            command.append("-analyzer-checker-help-developer")

        return CSAUtils.parse_clang_help_page(command, "CHECKERS:")

    # Copy from CodeChecker analyzer/codechecker_analyzer/analyzers/clangsa/analyzer.py
    @staticmethod
    def parse_clang_help_page(command: List[str], start_label: str) -> List[str]:
        """
        Parse the clang help page starting from a specific label.
        Returns a list of (flag, description) tuples.
        """
        try:
            help_page = subprocess.check_output(
                command,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
            )
        except (subprocess.CalledProcessError, OSError):
            logger.debug("Failed to run '%s' command!" % command)
            return []

        try:
            help_page = help_page[help_page.index(start_label) + len(start_label) :]
        except ValueError:
            return []

        # This regex will match lines which contain only a flag or a flag and a
        # description: '  <flag>', '  <flag> <description>'.
        start_new_option_rgx = re.compile(r"^\s{2}(?P<flag>\S+)(\s(?P<desc>[^\n]+))?$")

        # This regex will match lines which contain description for the previous
        # flag: '     <description>'
        prev_help_desc_rgx = re.compile(r"^\s{3,}(?P<desc>[^\n]+)$")

        res = []

        flag = None
        desc = []
        for line in help_page.splitlines():
            m = start_new_option_rgx.match(line)
            if m:
                if flag and desc:
                    res.append((flag, " ".join(desc)))
                    flag = None
                    desc = []

                flag = m.group("flag")
            else:
                m = prev_help_desc_rgx.match(line)

            if m and m.group("desc"):
                desc.append(m.group("desc").strip())

        if flag and desc:
            res.append((flag, " ".join(desc)))

        return res


class ClangTidyUtils:
    def __init__(self):
        self.checker_description = None

    @staticmethod
    def get_checkers_and_warning(clang_tidy, diagtool, json_checkers):
        checker_description = ClangTidyUtils.get_analyzer_checkers(clang_tidy, diagtool)
        checkers_and_state = determine_checkers_state(
            checker_description, json_checkers
        )
        return ClangTidyUtils.get_checker_list(checkers_and_state, checker_description)

    @staticmethod
    def get_warnings(diagtool_bin):
        """
        Returns list of warning flags by using diagtool.
        """
        if not diagtool_bin:
            return []

        try:
            result = subprocess.check_output(
                [diagtool_bin, "tree"],
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
            )
            return [w[2:] for w in result.split() if w.startswith("-W") and w != "-W"]
        except subprocess.CalledProcessError as exc:
            logger.error(
                "'diagtool' encountered an error while retrieving the "
                "checker list. If you are using a custom compiled clang, "
                "you may have forgotten to build the 'diagtool' target "
                "alongside 'clang' and 'clang-tidy'! Error message: %s" % exc.output
            )

            raise

    # Copy from CodeChecker analyzer/codechecker_analyzer/analyzers/clangtidy/analyzer.py
    @staticmethod
    def get_analyzer_checkers(clang_tidy, diagtool):
        """
        Return the list of the all of the supported checkers.
        """
        try:
            result = subprocess.check_output(
                [clang_tidy, "-list-checks", "-checks=*"],
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
            )
            checker_description = ClangTidyUtils.parse_checkers(result)

            checker_description.extend(
                ("clang-diagnostic-" + warning, "")
                for warning in ClangTidyUtils.get_warnings(diagtool)
            )

            return checker_description
        except (subprocess.CalledProcessError, OSError):
            return []

    @staticmethod
    def parse_checkers(tidy_output):
        """
        Parse clang tidy checkers list.
        Skip clang static analyzer checkers.
        Store them to checkers.
        """
        checkers = []
        pattern = re.compile(r"^\S+$")
        for line in tidy_output.splitlines():
            line = line.strip()
            if line.startswith("Enabled checks:") or line == "":
                continue

            if line.startswith("clang-analyzer-"):
                continue

            match = pattern.match(line)
            if match:
                checkers.append((match.group(0), ""))
        return checkers

    @staticmethod
    def get_compiler_warning_name_and_type(checker_name):
        """
        Removes 'W' or 'Wno' from the compiler warning name, if this is a
        compiler warning and returns the name and CheckerType.compiler.
        If it is a clang-diagnostic-<name> warning then it returns the name
        and CheckerType.analyzer.
        Otherwise returns None and CheckerType.analyzer.
        """
        # Checker name is a compiler warning.
        if checker_name.startswith("W"):
            name = (
                checker_name[4:]
                if checker_name.startswith("Wno-")
                else checker_name[1:]
            )
            return name, CheckerType.COMPILER
        elif checker_name.startswith("clang-diagnostic-"):
            return checker_name[17:], CheckerType.ANALYZER
        else:
            return None, CheckerType.ANALYZER

    @staticmethod
    def _add_asterisk_for_group(
        subset_checkers: Iterable[str], all_checkers: Set[str]
    ) -> List[str]:
        """
        Since CodeChecker interprets checker name prefixes as checker groups, they
        have to be added a '*' joker character when using them at clang-tidy
        -checks flag. This function adds a '*' for each item in "checkers" if it's
        a checker group, i.e. identified as a prefix for any checker name in
        "all_checkers".
        For example "readability-container" is a prefix of multiple checkers, so
        this is converted to "readability-container-*". On the other hand
        "performance-trivially-destructible" is a full checker name, so it remains
        as is.
        """

        def is_group_prefix_of(prefix: str, long: str) -> bool:
            """
            Returns True if a checker(-group) name is prefix of another
            checker name. For example bugprone-string is prefix of
            bugprone-string-constructor but not of
            bugprone-stringview-nullptr.
            """
            prefix_split = prefix.split("-")
            long_split = long.split("-")
            return prefix_split == long_split[: len(prefix_split)]

        def need_asterisk(checker: str) -> bool:
            return any(
                is_group_prefix_of(checker, long) and checker != long
                for long in all_checkers
            )

        result = []

        for checker in subset_checkers:
            result.append(checker + ("*" if need_asterisk(checker) else ""))

        return result

    @staticmethod
    def get_checker_list(
        checkers_and_state, checker_description
    ) -> Tuple[List[str], List[str]]:
        compiler_warnings = []
        enabled_checkers = []

        # Config handler stores which checkers are enabled or disabled.
        for checker_name, state in checkers_and_state:
            warning_name, warning_type = (
                ClangTidyUtils.get_compiler_warning_name_and_type(checker_name)
            )

            # This warning must be given a parameter separated by either '=' or
            # space. This warning is not supported as a checker name so its
            # special usage is avoided.
            if warning_name and warning_name.startswith("frame-larger-than"):
                continue

            if warning_name is not None:
                # -W and clang-diagnostic- are added as compiler warnings.
                if warning_type == CheckerType.COMPILER:
                    logger.debug(
                        "As of CodeChecker v6.22, the following usage"
                        f"of '{checker_name}' compiler warning as a "
                        "checker name is deprecated, please use "
                        f"'clang-diagnostic-{checker_name[1:]}' "
                        "instead."
                    )
                    if state == CheckerState.ENABLED:
                        compiler_warnings.append("-W" + warning_name)
                        enabled_checkers.append(checker_name)

                # If a clang-diagnostic-... is enabled add it as a compiler
                # warning as -W..., if it is disabled, tidy can suppress when
                # specified in the -checks parameter list, so we add it there
                # as -clang-diagnostic-... .
                elif warning_type == CheckerType.ANALYZER:
                    if state == CheckerState.ENABLED:
                        if checker_name == "clang-diagnostic-error":
                            # Disable warning of clang-diagnostic-error to
                            # avoid generated compiler errors.
                            compiler_warnings.append("-Wno-" + warning_name)
                        else:
                            compiler_warnings.append("-W" + warning_name)
                        enabled_checkers.append(checker_name)
                    else:
                        compiler_warnings.append("-Wno-" + warning_name)

                continue

            if state == CheckerState.ENABLED:
                enabled_checkers.append(checker_name)

        # By default all checkers are disabled and the enabled ones are added
        # explicitly.
        checkers = ["-*"]

        checkers += ClangTidyUtils._add_asterisk_for_group(
            enabled_checkers, set(x[0] for x in checker_description)
        )

        return checkers, compiler_warnings


class CppCheckUtils:
    @staticmethod
    def get_disable_checkers(cppcheck, json_checkers):
        checkers = CppCheckUtils.get_analyzer_checkers(cppcheck)
        # Cppcheck can and will report with checks that have a different
        # name than marked in the --errorlist xml. To be able to suppress
        # these reports, the checkerlist needs to be extended by those found
        # in the label file.
        checkers_from_label = json_checkers["labels"].keys()
        parsed_set = set(data[0] for data in checkers)
        for checker in set(checkers_from_label):
            if checker not in parsed_set:
                checkers.append((checker, ""))
        checkers_and_state = determine_checkers_state(checkers, json_checkers)
        return [
            checker[0]
            for checker in list(
                filter(lambda x: x[1] == CheckerState.DISABLED, checkers_and_state)
            )
        ]

    @staticmethod
    def parse_checkers(cppcheck_output):
        """
        Parse cppcheck checkers list given by '--errorlist' flag. Return a list of
        (checker_name, description) pairs.
        """
        checkers = []

        tree = ET.ElementTree(ET.fromstring(cppcheck_output))
        root = tree.getroot()
        errors = root.find("errors")
        if errors is None:
            return checkers
        for error in errors.findall("error"):
            name = error.attrib.get("id")
            if name:
                name = "cppcheck-" + name
            msg = str(error.attrib.get("msg") or "")
            # TODO: Check severity handling in cppcheck
            # severity = error.attrib.get('severity')

            # checkers.append((name, msg, severity))
            checkers.append((name, msg))

        return checkers

    @staticmethod
    def get_analyzer_checkers(cppcheck):
        """
        Return the list of the supported checkers.
        """
        command = [cppcheck, "--errorlist"]
        try:
            result = subprocess.check_output(command)
            return CppCheckUtils.parse_checkers(result)
        except subprocess.CalledProcessError as e:
            logger.error(e.stderr)
        except OSError as e:
            logger.error(e.errno)
        return []

    @staticmethod
    def get_analyzer_config():
        """
        Config options for cppcheck.
        """
        return [
            ("addons", "A list of cppcheck addon files."),
            ("libraries", "A list of cppcheck library definiton files."),
            ("platform", "The platform configuration .xml file."),
            ("inconclusive", "Enable inconclusive reports."),
        ]

    @staticmethod
    def parse_analyzer_config(analyzer_options):
        """
        Parses a set of a white listed compiler flags.
        Cppcheck can only use a subset of the parametes
        found in compilation commands.
        These are:
        * -I: flag for specifing include directories
        * -D: for build time defines
        * -U: for undefining names
        * -std: The languange standard
        Any other parameter different from the above list will be dropped.
        """
        params = []
        interesting_option = re.compile("-[IUD].*")
        # the std flag is different. the following are all valid flags:
        # * --std c99
        # * -std=c99
        # * --std=c99
        # BUT NOT:
        # * -std c99
        # * -stdlib=libc++
        std_regex = re.compile("-(-std$|-?std=.*)")

        # Mapping is needed, because, if a standard version not known by
        # cppcheck is used, then it will assume the latest available version
        # before cppcheck-2.15 or fail the analysis from cppcheck-2.15.
        # https://gcc.gnu.org/onlinedocs/gcc/C-Dialect-Options.html#index-std-1
        standard_mapping = {
            "c90": "c89",
            "c18": "c17",
            "iso9899:2017": "c17",
            "iso9899:2018": "c17",
            "iso9899:1990": "c89",
            "iso9899:199409": "c89",  # Good enough
            "c9x": "c99",
            "iso9899:1999": "c99",
            "iso9899:199x": "c99",
            "c1x": "c11",
            "iso9899:2011": "c11",
            "c2x": "c23",
            "iso9899:2024": "c23",
            "c++98": "c++03",
            "c++0x": "c++11",
            "c++1y": "c++14",
            "c++1z": "c++17",
            "c++2a": "c++20",
            "c++2b": "c++23",
            "c++2c": "c++26",
        }

        for i, analyzer_option in enumerate(analyzer_options):
            if interesting_option.match(analyzer_option):
                params.extend([analyzer_option])
                # The above extend() won't properly insert the analyzer_option
                # in case of the following format -I <path/to/include>.
                # The below check will add the next item in the
                # analyzer_options list if the parameter is specified with a
                # space, as that should be actual path to the include.
                if interesting_option.match(analyzer_option).span() == (0, 2):  # type: ignore
                    params.extend([analyzer_options[i + 1]])
            elif std_regex.match(analyzer_option):
                standard = ""
                if "=" in analyzer_option:
                    standard = analyzer_option.split("=")[-1]
                # Handle space separated parameter
                # The else clause is never executed until a log parser
                # limitation is addressed, as only this "-std=xxx" version
                # of the paramter is forwareded in the analyzer_option list.
                else:
                    standard = analyzer_options[i + 1]
                standard = standard.lower().replace("gnu", "c")
                standard = standard_mapping.get(standard, standard)
                params.extend(["--std=" + standard])
        return params


# The compilation flags of which the prefix is any of these regular expressions
# will not be included in the output Clang command.
# These flags should be ignored only in case the original compiler is gcc.
IGNORED_OPTIONS_GCC = [
    # --- UNKNOWN BY CLANG --- #
    "-fallow-fetchr-insn",
    "-fcall-saved-",
    "-fcond-mismatch",
    "-fconserve-stack",
    "-fcrossjumping",
    "-fcse-follow-jumps",
    "-fcse-skip-blocks",
    "-fcx-limited-range$",
    "-fext-.*-literals",
    "-ffixed-r2",
    "-ffp$",
    "-mfp16-format",
    "-mmitigate-rop",
    "-fgcse-lm",
    "-fhoist-adjacent-loads",
    "-findirect-inlining",
    "-finline-limit",
    "-finline-local-initialisers",
    "-fipa-sra",
    "-fmacro-prefix-map",
    "-fmerge-constants",
    "-fno-aggressive-loop-optimizations",
    "-f(no-)?allow-store-data-races",
    "-fno-canonical-system-headers",
    "-f(no-)?code-hoisting",
    "-fno-delete-null-pointer-checks",
    "-fno-defer-pop",
    "-fno-extended-identifiers",
    "-fno-freestanding",
    "-fno-jump-table",
    "-fno-keep-inline-dllexport" "-fno-keep-static-consts",
    "-fno-lifetime-dse",
    "-f(no-)?printf-return-value",
    "-f(no-)?reorder-functions",
    "-fno-strength-reduce",
    "-fno-toplevel-reorder",
    "-fno-unit-at-a-time",
    "-fno-var-tracking-assignments",
    "-fno-tree-dominator-opts",
    "-fobjc-link-runtime",
    "-fpartial-inlining",
    "-fpeephole2",
    "-fr$",
    "-fregmove",
    "-frename-registers",
    "-frerun-cse-after-loop",
    "-fs$",
    "-fsanitize=bounds-strict",
    "-fsched-pressure",
    "-fsched-spec",
    "-fstack-usage",
    "-fstack-reuse",
    "-fthread-jumps",
    "-ftree-pre",
    "-ftree-switch-conversion",
    "-ftree-tail-merge",
    "-m(no-)?abm",
    "-m(no-)?sdata",
    "-m(no-)?spe",
    "-m(no-)?string$",
    "-m(no-)?dsbt",
    "-m(no-)?fixed-ssp",
    "-m(no-)?pointers-to-nested-functions",
    "-m(no-)?word-relocations",
    "-mno-fp-ret-in-387",
    "-mpreferred-stack-boundary",
    "-mpcrel-func-addr",
    "-mrecord-mcount$",
    "-maccumulate-outgoing-args",
    "-mcall-aixdesc",
    "-mppa3-addr-bug",
    "-mtraceback=",
    "-mtext=",
    "-misa=",
    "-mfunction-return=",
    "-mindirect-branch-register",
    "-mindirect-branch=",
    "-mfix-cortex-m3-ldrd$",
    "-mmultiple$",
    "-msahf$",
    "-mskip-rax-setup$",
    "-mthumb-interwork$",
    "-mupdate$",
    # Deprecated ARM specific option
    # to Generate a stack frame that is compliant
    # with the ARM Procedure Call Standard.
    "-mapcs",
    "-fno-merge-const-bfstores$",
    "-fno-ipa-sra$",
    "-mno-thumb-interwork$",
    # ARM specific option.
    # Prevent the reordering of
    # instructions in the function prologue.
    "-mno-sched-prolog",
    # This is not unknown but we want to preserve asserts to improve the
    # quality of analysis.
    "-DNDEBUG$",
    # --- IGNORED --- #
    "-save-temps",
    # Clang gives different warnings than GCC. Thus if these flags are kept,
    # '-Werror', '-Wno-error', '-pedantic-errors' the analysis with Clang can
    # fail even if the compilation passes with GCC.
    "-Werror",
    "-Wno-error",
    "-pedantic-errors",
    # Profiling flags are different or behave differently in GCC
    "-fprofile",
    # Remove the option disabling the warnings.
    "-w",
    "-g(.+)?$",
    # Link Time Optimization:
    "-flto",
    # MicroBlaze Options:
    "-mxl",
    # PowerPC SPE Options:
    "-mfloat-gprs",
    "-mabi",
]

IGNORED_OPTIONS_GCC = re.compile("|".join(IGNORED_OPTIONS_GCC))
