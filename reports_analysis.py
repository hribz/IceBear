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

def list_files(directory: str):
    if not os.path.exists(directory):
        return []
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def list_dir(directory: str):
    if not os.path.exists(directory):
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
                logger.info(report)
        if len(diff2) > 0:
            logger.info(f"Sad! There are {len(diff2)} reports only in {dir2}:")
            for report in diff2:
                logger.info(report)

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--repo', type=str, dest='repo', help='Only analyse specific repos.')
        self.parser.add_argument('--workspace1', type=str, dest='workspace1', help='Result path1.')
        self.parser.add_argument('--workspace2', type=str, dest='workspace2', help='Result path2.')

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

def main(args):
    parser = RepoParser()
    opts = parser.parse_args(args)
    if not opts.workspace1 or not opts.workspace2:
        print("Please specify workspace1 and workspace2.")
        exit(1)
    env = Environment(opts)
    repos = 'repos/repos.json'

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

        dir1 = os.path.join(repo_info.workspace, 'csa/csa-reports')
        dir2 = os.path.join(repo_info2.workspace, 'csa/csa-reports')
        reports1 = all_reports(collect_reports(dir1))
        reports2 = all_reports(collect_reports(dir2))
        
        diff_reports(reports1, reports2, dir1, dir2)

if __name__ == "__main__":
    main(sys.argv[1:])
    
