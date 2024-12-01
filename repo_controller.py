from git import Repo
import argparse
import sys
import pandas as pd
import json
import subprocess
from datetime import datetime, timedelta

from IncAnalysis.repository import Repository, BuildType
from IncAnalysis.utils import *
from IncAnalysis.environment import *
from IncAnalysis.logger import logger
from IncAnalysis.utils import add_to_csv

def get_repo_csv(csv_path: str) -> pd.DataFrame:
    commit_df = pd.read_csv(csv_path)
    return commit_df

def clone_project(repo_name: str) -> None:
    try:
        repo_dir = f"repos/{repo_name}"
        # repo_dir exist and not empty.
        if os.path.exists(repo_dir) and os.listdir(repo_dir):
            logger.info(f"[Clone Project] repository {repo_dir} has exists.")
            return True
        makedir(repo_dir)
        Repo.clone_from("https://github.com/"+repo_name+".git", repo_dir, multi_options=['--recurse-submodules'])
        return True
    except Exception as e:
        # clone error, repository no longer exists
        logger.error(f"[Clone Project] repository {repo_dir} cannot clone.\n{e}")
        return False

def checkout_target_commit(repo_dir: str, commit: str) -> bool:
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)

    try:
        repo.git.checkout(commit)
        return True

    except Exception as e:
        print(f"error while checking out commit.\n{e}")
        return False

def reset_repository(repo_dir: str):
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)
    repo.git.reset("--hard")
    repo.git.clean("-xdf")

def update_submodules(repo_dir: str):
    try:
        subprocess.run("git submodule init", check=True, shell=True, cwd=repo_dir)
        subprocess.run("git submodule update", check=True, shell=True, cwd=repo_dir)
        return True
    except Exception as e:
        print(f"error while updating submodules.\n{e}")
        return False

def get_head_commit_date(repo_dir: str):
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)
    return datetime.fromtimestamp(repo.head.commit.committed_date).date()

def get_local_repo_commit_parents(repo_dir: str, commit: str) -> list:
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)

    # ensure head commit
    assert repo.head.commit.hexsha == commit

    # return parent commits
    return [commit.hexsha for commit in repo.head.commit.parents]

def get_recent_n_daily_commits(repo_dir: str, n: int, branch):
    assert n>=0
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)
    repo_name = os.path.basename(repo_dir)
    commits_dir = f"{repo_dir}_commits"
    makedir(commits_dir)
    later_commit = None
    later_commit_date = None
    daily_commits = []
    for commit in repo.iter_commits(branch):
        commit_date = datetime.fromtimestamp(commit.committed_date).date()
        if later_commit is None:
            later_commit = commit
            later_commit_date = commit_date
            daily_commits.append(commit.hexsha)
        else:
            time_delta =  later_commit_date - commit_date
            if time_delta >= timedelta(days=1):
                daily_commits.append(commit.hexsha)
                later_commit_file = f"{commits_dir}/{repo_name}_{later_commit_date}_{later_commit.hexsha[:6]}.diff"
                if not os.path.exists(later_commit_file):
                    with open(later_commit_file, 'w') as f:
                        f.write(f"Old Date: {commit.committed_datetime}\nOld Commit: {commit.hexsha}\nNew Date: {later_commit.committed_datetime}\n"+\
                                f"New Commit: {later_commit.hexsha}\nAuthor: {later_commit.author}\nMessage:\n{later_commit.message}\n")
                        diff = repo.git.diff(commit.hexsha, later_commit.hexsha)
                        f.write(diff)
                later_commit = commit
                later_commit_date = commit_date
        if len(daily_commits) >= n:
            break
    daily_commits.reverse()
    return daily_commits

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--repo', type=str, dest='repo', help='Only analyse specific repos.')
        self.parser.add_argument('--daily', type=int, default=10, dest='daily', help='Analyse n daily commits.')

def main(args):
    parser = RepoParser()
    opts = parser.parse_args(args)
    env = Environment(opts)
    repos = 'repos/repos.json'
    test_repos = 'repos/test_grpc.json'
    FFmpeg = 'repos/test_ffmpeg.json'
    grpc = 'repos/test_grpc.json'
    ica_demo = 'repos/test_ica_demo.json'

    repo_list = repos

    result_file = f'repos/result/{opts.inc}_{env.timestamp}_result.csv'
    result_file_specific = f'repos/result/{opts.inc}_{env.timestamp}_result_specific.csv'
    # result_file = 'repos/result/result_all.csv'
    # result_file_specific = 'repos/result/result_all_specific.csv'
    
    with open(repo_list, 'r') as f:
        repo_json = json.load(f)
    Repo = None
    
    class STATUS(Enum):
        BEGIN = auto()
        NORMAL = auto()
        CLONE_FAILED = auto()
        CHECK_FAILED = auto()
    status = STATUS.BEGIN
    init_csv = True

    for repo in repo_json:
        repo_name = repo["project"]
        repo_dir = Path(env.PWD / f"repos/{repo_name}")
        if opts.repo and opts.repo != repo_name and opts.repo != os.path.basename(repo_dir):
            continue
        build_type = repo["build_type"]
        default_options = repo["config_options"] if repo.get("config_options") else []
        branch = repo["branch"]
        os.chdir(env.PWD)
        abs_repo_path = str(repo_dir.absolute())
        print(abs_repo_path)

        if Repo is None:
            if not clone_project(repo_name):
                status = STATUS.CLONE_FAILED
                continue
            update_submodules(repo_dir)

        commits = get_recent_n_daily_commits(repo_dir, opts.daily, branch) if opts.daily>0 else [commit['hash'] for commit in repo['commits']]
        for commit_sha in commits:
            status = STATUS.NORMAL
            if checkout_target_commit(abs_repo_path, commit_sha):
                logger.info(f"[Git Checkout] checkout {repo_name} to {commit_sha}")
                commit_date = get_head_commit_date(repo_dir)
                if Repo is None:
                    # Analysis first commit as baseline.
                    Repo = Repository(repo_name, abs_repo_path, env, build_root=f"{abs_repo_path}_build", default_options=default_options,
                                    build_dir_name=f"build_{commit_date}_{commit_sha[:6]}", default_build_type=build_type)
                    Repo.process_one_config(Repo.configurations[-1])
                else:
                    # Analysis subsequent commit incrementally.
                    Repo.add_configuration(default_options, build_dir_name=f"build_{commit_date}_{commit_sha[:6]}")
                    Repo.process_one_config(Repo.configurations[-1])
            else:
                status = STATUS.CHECK_FAILED
                logger.error(f"[Checkout Commit] {repo_name} checkout to {commit_sha} failed!")
        if Repo:
            logger.info('---------------END SUMMARY-------------\n'+Repo.session_summary())
            headers, data = Repo.summary_to_csv_specific()
            add_to_csv(headers, data, result_file_specific, init_csv)
            headers, data = Repo.summary_to_csv()
            add_to_csv(headers, data, result_file, init_csv)
            init_csv = False
            Repo.file_status_to_csv()
            Repo = None

    if Repo:
        logger.info('---------------END SUMMARY-------------\n'+Repo.session_summary())
        headers, data = Repo.summary_to_csv_specific()
        add_to_csv(headers, data, result_file_specific)
        headers, data = Repo.summary_to_csv()
        add_to_csv(headers, data, result_file)

if __name__ == "__main__":
    main(sys.argv[1:])