import os
from git import Repo
import pandas as pd
import subprocess
from datetime import datetime, timedelta

from IncAnalysis.logger import logger
from IncAnalysis.utils import makedir

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
    if not checkout_target_commit(repo_dir, branch):
        print(f"Checkout {branch} failed.")
        exit(1)
    else:
        print(f"Checkout {branch} success.")

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
                    with open(later_commit_file, 'w', encoding='utf-8') as f:
                        f.write(f"Old Date: {commit.committed_datetime}\nOld Commit: {commit.hexsha}\nNew Date: {later_commit.committed_datetime}\n"+\
                                f"New Commit: {later_commit.hexsha}\nAuthor: {later_commit.author}\nMessage:\n{later_commit.message}\n")
                        diff = repo.git.diff(commit.hexsha, later_commit.hexsha)
                        diff = diff.encode('utf-8', 'replace').decode('utf-8')
                        f.write(diff)
                later_commit = commit
                later_commit_date = commit_date
        if len(daily_commits) >= n:
            break
    daily_commits.reverse()
    return daily_commits