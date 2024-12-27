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

def list_dir(directory: str):
    if not os.path.exists(directory):
        logger.info(f"{directory} does not exist.")
        return []
    return [f for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]

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

        json1 = os.path.join(repo_info.workspace, 'reports_statistics.json')
        json2 = os.path.join(repo_info2.workspace, 'reports_statistics.json')
        statistics1 = json.load(open(json1, 'r'))['CSA']
        statistics2 = json.load(open(json2, 'r'))['CSA']
        
        # [
        #     {'version': commit['version'], 'reports': [Report1, Report2, ...]},
        #     ......
        # ]
        def versions_and_reports(statistics: list) -> dict:
            versions_and_reports = []
            for commit in statistics:
                version = commit['version']
                reports_from_this_commit = commit['reports']
                reports = []
                for report in reports_from_this_commit:
                    report_name = report
                    specific_info = {}
                    reports.add(Report(version, report_name, specific_info))
                versions_and_reports.append({'version': version, 'reports': reports})
            return versions_and_reports
        
        def dump_veen_diagram(versions_and_reports):
            # Group reports by version
            version_reports_dict = {}
            for item in versions_and_reports:
                version = item['version']
                reports = item['reports']
                if version not in version_reports_dict:
                    version_reports_dict[version] = set()
                version_reports_dict[version].update(reports)

            # Draw Venn diagram
            import matplotlib.pyplot as plt

            if len(version_reports_dict) == 2:
                versions = list(version_reports_dict.keys())
                reports1 = version_reports_dict[versions[0]]
                reports2 = version_reports_dict[versions[1]]
                
                plt.figure(figsize=(10, 7))
                venn2([reports1, reports2], set_labels=(versions[0], versions[1]))
                plt.title('Venn Diagram of Reports by Version')
                plt.show()
        
        versions_and_reports1 = versions_and_reports(statistics1)
        versions_and_reports2 = versions_and_reports(statistics2)

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
    
