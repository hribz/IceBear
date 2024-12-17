import re
import subprocess
from typing import List

from IncAnalysis.logger import logger
from IncAnalysis.environment import Environment

# Copy from CodeChecker analyzer/codechecker_analyzer/analyzers/clangsa/analyzer.py
def get_analyzer_checkers(
        compiler: str,
        alpha: bool = True,
        debug: bool = False
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

    return parse_clang_help_page(command, 'CHECKERS:')

# Copy from CodeChecker analyzer/codechecker_analyzer/analyzers/clangsa/analyzer.py
def parse_clang_help_page(
    command: List[str],
    start_label: str
) -> List[str]:
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
            errors="ignore")
    except (subprocess.CalledProcessError, OSError):
        logger.debug("Failed to run '%s' command!", command)
        return []

    try:
        help_page = help_page[help_page.index(start_label) + len(start_label):]
    except ValueError:
        return []

    # This regex will match lines which contain only a flag or a flag and a
    # description: '  <flag>', '  <flag> <description>'.
    start_new_option_rgx = \
        re.compile(r"^\s{2}(?P<flag>\S+)(\s(?P<desc>[^\n]+))?$")

    # This regex will match lines which contain description for the previous
    # flag: '     <description>'
    prev_help_desc_rgx = \
        re.compile(r"^\s{3,}(?P<desc>[^\n]+)$")

    res = []

    flag = None
    desc = []
    for line in help_page.splitlines():
        m = start_new_option_rgx.match(line)
        if m:
            if flag and desc:
                res.append((flag, ' '.join(desc)))
                flag = None
                desc = []

            flag = m.group("flag")
        else:
            m = prev_help_desc_rgx.match(line)

        if m and m.group("desc"):
            desc.append(m.group("desc").strip())

    if flag and desc:
        res.append((flag, ' '.join(desc)))

    return res