import os
from pathlib import Path
import sys
import json

from IncAnalysis.repository import UpdateConfigRepository, BuildType
from IncAnalysis.utils import *
from IncAnalysis.environment import *
from IncAnalysis.logger import logger
from IncAnalysis.utils import add_to_csv
from git_utils import *
from matplotlib_venn import venn2

def list_files(directory: str):
    if not os.path.exists(directory):
        return []
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def list_dir(directory: str, filt_set: set=None):
    if not os.path.exists(directory):
        logger.info(f"{directory} does not exist.")
        return []
    dir_list = [f for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]
    if filt_set:
        return list(filter(lambda x: (x in filt_set), dir_list))
    else:
        return dir_list

def collect_reports(analyzer_output_path: str):
    commit_to_reports = {}
    sub_dirs = list_dir(analyzer_output_path)
    for dir in sub_dirs:
        reports = list_files(os.path.join(analyzer_output_path, dir))
        commit_to_reports[dir] = reports
    return commit_to_reports

def all_reports(commit_to_reports) -> set:
    total_reports = set()
    for dir in commit_to_reports.keys():
        reports = commit_to_reports[dir]
        total_reports.update(set(reports))
    return total_reports

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--repo', type=str, dest='repo', help='Only analyse specific repos.')
        self.parser.add_argument('--workspace1', type=str, dest='workspace1', help='Result path1.')
        self.parser.add_argument('--workspace2', type=str, dest='workspace2', help='Result path2.')
        self.parser.add_argument('--json1', type=str, dest='json1', help='Reports1 json statistics.')
        self.parser.add_argument('--json2', type=str, dest='json2', help='Reports2 json statistics.')

class RepoInfo:
    def __init__(self, repo, env: Environment, workspace):
        self.repo_name = repo["project"]
        self.repo_dir = Path(env.PWD / f"repos/{self.repo_name}")
        self.build_type = repo["build_type"]
        self.default_options = repo["config_options"] if repo.get("config_options") else []
        self.branch = repo["branch"]
        self.out_of_tree = True if repo.get("out_of_tree") is None else repo.get("out_of_tree")
        
        self.abs_repo_path = str(self.repo_dir.absolute())
        self.workspace = f"{self.abs_repo_path}_workspace/{workspace}"

class Report:
    def __init__(self, version, report_name, specific_info):
        self.version = version
        self.report_name = report_name
        self.speicific_info = specific_info

    def __eq__(self, other):
        if isinstance(other, Report):
            return self.report_name == other.report_name and self.speicific_info == other.speicific_info
        return False

    def __hash__(self):
        return hash((self.report_name, self.speicific_info.__str__()))


def diff_reports(reports1: set, reports2: set, dir1, dir2):
    diff1 = reports1.difference(reports2)
    diff2 = reports2.difference(reports1)
    diff = diff1.union(diff2)
    if len(diff) == 0:
        logger.info(f"Congratulations! There is no difference between reports in {dir1} and {dir2}")
    else:
        if len(diff1) > 0:
            logger.info(f"Sad! There are {len(diff1)} reports only in {dir1}:")
            for report in diff1:
                logger.info(dir1 + '/' + report.version + '/' + report.report_name)
        if len(diff2) > 0:
            logger.info(f"Sad! There are {len(diff2)} reports only in {dir2}:")
            for report in diff2:
                logger.info(dir2 + '/' + report.version + '/' + report.report_name)

def main(args):
    parser = RepoParser()
    opts = parser.parse_args(args)
    if not opts.workspace1 or not opts.workspace2:
        print("Please specify workspace1 and workspace2.")
        exit(1)
    env = Environment(opts)
    repos = 'repos/benchmark.json'

    repo_list = repos
    
    with open(repo_list, 'r') as f:
        repo_json = json.load(f)

    for repo in repo_json:
        os.chdir(env.PWD)
        repo_info = RepoInfo(repo, env, opts.workspace1)
        repo_info2 = RepoInfo(repo, env, opts.workspace2)
        logger.TAG = repo_info.repo_name
        
        if opts.repo and opts.repo != repo_info.repo_name and opts.repo != os.path.basename(repo_info.repo_dir):
            continue
        if repo_info.repo_name in ignore_repos:
            logger.info(f"{repo_info.repo_name} is in ignore repo list")
            continue

        def get_statistics_from_workspace(workspace):
            analyzers = ['csa', 'clang-tidy', 'cppcheck', 'infer']
            analyzers_floder = [os.path.join(workspace, analyzer) for analyzer in list_dir(workspace, analyzers)]
            statistics = {k: [] for k in analyzers}

            for analyzer in analyzers_floder:
                if analyzer.endswith('csa'):
                    reports_path = os.path.join(analyzer, 'csa-reports')
                elif analyzer.endswith('clang-tidy'):
                    reports_path = os.path.join(analyzer, 'clang-tidy-reports')
                elif analyzer.endswith('cppcheck'):
                    reports_path = os.path.join(analyzer, 'cppcheck-reports')
                elif analyzer.endswith('infer'):
                    reports_path = os.path.join(analyzer, 'infer-reports')

                versions = list_dir(reports_path)
                for version in versions:
                    output_path = os.path.join(reports_path, version)
                    reports = []
                    if analyzer not in statistics:
                        statistics[analyzer] = []
                    if analyzer.endswith('csa'):
                        analyzer_name = 'csa'
                        if not os.path.exists(output_path):
                            continue
                        reports = list_files(output_path)
                    elif analyzer.endswith('clang-tidy'):
                        analyzer_name = 'clang-tidy'
                        if not os.path.exists(output_path):
                            continue
                        reports = list_files(output_path)
                    elif analyzer.endswith('cppcheck'):
                        analyzer_name = 'cppcheck'
                        if not os.path.exists(output_path / 'result.json'):
                            continue
                        with open(output_path / 'result.json', 'r') as f:
                            cppcheck_result = json.load(f)
                            results = cppcheck_result["runs"][0]["results"]
                            reports = [{k: v for k, v in result.items() if k != 'locations'} for result in results]
                    elif analyzer.endswith('infer'):
                        analyzer_name = 'infer'
                        if not os.path.exists(output_path / 'report.json'):
                            continue
                        with open(output_path / 'report.json', 'r') as f:
                            infer_result = json.load(f)
                            key_set = {'bug_type', 'qualifier', 'severity', 'category', 'procedure', 'file', 'key', 'bug_type_hum'}
                            reports = [{k: v for k, v in result.items() if k in key_set} for result in infer_result]
                    
                    statistics[analyzer_name].append({
                        'version': version,
                        'reports': reports
                    })
                    
            return statistics
        
        statistics1 = get_statistics_from_workspace(repo_info.workspace)['csa']
        statistics2 = get_statistics_from_workspace(repo_info2.workspace)['csa']

        # [
        #     {'version': commit['version'], 'reports': [Report1, Report2, ...]},
        #     ......
        # ]
        def versions_and_reports(statistics: list) -> dict:
            versions_and_reports = {}
            for commit in statistics:
                version = commit['version']
                reports_from_this_commit = commit['reports']
                reports = set()
                for report in reports_from_this_commit:
                    report_name = report
                    specific_info = {}
                    reports.add(Report(version, report_name, specific_info))
                versions_and_reports[version] = reports
            return versions_and_reports
        
        def dump_veen_diagram(versions_and_reports, figure):
            if len(versions_and_reports.keys()) == 0:
                return 
            # Draw Venn diagram
            import matplotlib.pyplot as plt
            from venn import venn

            # 绘制Venn图
            plt.figure()
            venn(versions_and_reports, fmt='{size}', cmap='tab10')
            plt.savefig(figure)
        
        versions_and_reports1 = versions_and_reports(statistics1)
        dump_veen_diagram(versions_and_reports1, f"{repo_info.workspace}/veen.png")
        versions_and_reports2 = versions_and_reports(statistics2)
        dump_veen_diagram(versions_and_reports2, f"{repo_info2.workspace}/veen.png")

        def all_reports_from_json(statistics: list) -> set:
            reports = set()
            for commit in statistics:
                version = commit['version']
                reports_from_this_commit = commit['reports']
                for report in reports_from_this_commit:
                    report_name = report
                    specific_info = {}
                    reports.add(Report(version, report_name, specific_info))
            return reports
        
        reports1 = all_reports_from_json(statistics1)
        reports2 = all_reports_from_json(statistics2)

        dir1 = os.path.join(repo_info.workspace, 'csa/csa-reports')
        dir2 = os.path.join(repo_info2.workspace, 'csa/csa-reports')

        diff_reports(reports1, reports2, dir1, dir2)

if __name__ == "__main__":
    main(sys.argv[1:])
    
