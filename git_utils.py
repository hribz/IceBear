import json
import os
from git import Repo
import pandas as pd
import subprocess
from datetime import datetime, timedelta
import requests

from IncAnalysis.logger import logger
from IncAnalysis.utils import makedir, remake_dir, Path

ignore_repos = {'xbmc/xbmc', 'mirror/busybox', 'llvm/llvm-project', 'opencv/opencv', 'c-ares/c-ares'}

def get_repo_csv(csv_path: str) -> pd.DataFrame:
    commit_df = pd.read_csv(csv_path)
    return commit_df

def clone_project(repo_name: str) -> bool:
    try:
        logger.info(f"[Clone Project] cloning repository {repo_name}")
        repo_dir = f"repos/{repo_name}"
        # repo_dir exist and not empty.
        if os.path.exists(repo_dir):
            dir_list = os.listdir(repo_dir)
            if os.path.exists(repo_dir) and len(dir_list) > 0 and dir_list != ['.git']:
                logger.info(f"[Clone Project] repository {repo_dir} already exists.")
                return True
        remake_dir(Path(repo_dir))
        Repo.clone_from(f"git@github.com:{repo_name}.git", repo_dir, multi_options=['--recurse-submodules'])
        return True
    except Exception as e:
        # clone error, repository no longer exists
        logger.error(f"[Clone Project] repository {repo_dir} cannot be cloned.\n{e}")
        return False

def checkout_target_commit(repo_dir: str, commit: str) -> bool:
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)

    try:
        repo.git.checkout(commit)
        return True

    except Exception as e:
        logger.error(f"error while checking out commit.\n{e}")
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
        logger.error(f"error while updating submodules.\n{e}")
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

def get_recent_n_daily_commits(repo_dir: str, n: int, branch, amount):
    assert n>=0
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)
    repo_name = os.path.basename(repo_dir)
    commits_dir = f"{repo_dir}_commits"
    makedir(commits_dir)
    later_commit = None
    later_commit_date = None
    daily_commits = []
    amount_delta = 0
    if not checkout_target_commit(repo_dir, branch):
        logger.error(f"Checkout {branch} failed.")
        exit(1)
    else:
        logger.info(f"Checkout {branch} success.")

    for commit in repo.iter_commits(branch):
        commit_date = datetime.fromtimestamp(commit.committed_date).date()
        amount_delta += 1
        if later_commit is None:
            later_commit = commit
            later_commit_date = commit_date
            daily_commits.append(commit.hexsha)
        else:
            time_delta =  later_commit_date - commit_date
            if amount_delta >= amount:
                daily_commits.append(commit.hexsha)
                later_commit_file = f"{commits_dir}/{repo_name}_{later_commit_date}_{later_commit.hexsha[:6]}.diff"
                with open(later_commit_file, 'w', encoding='utf-8') as f:
                    f.write(f"Old Date: {commit.committed_datetime}\nOld Commit: {commit.hexsha}\nNew Date: {later_commit.committed_datetime}\n"+\
                            f"New Commit: {later_commit.hexsha}\nCommits Amount: {amount_delta}\nAuthor: {later_commit.author}\nMessage:\n{later_commit.message}\n")
                    diff = repo.git.diff(commit.hexsha, later_commit.hexsha)
                    diff = diff.encode('utf-8', 'replace').decode('utf-8')
                    f.write(diff)
                later_commit = commit
                later_commit_date = commit_date
                amount_delta = 0
        if len(daily_commits) >= n:
            break
    daily_commits.reverse()
    return daily_commits

def get_repo_specific_info(repo_name: str) -> dict:
    try:
        repo_url = f"https://api.github.com/repos/{repo_name}"
        response = requests.get(repo_url)
        response.raise_for_status()
        repo_info = response.json()
        stars = repo_info.get('stargazers_count', 0)
        forks = repo_info.get('forks_count', 0)
        watchers = repo_info.get('watchers_count', 0)
        open_issues = repo_info.get('open_issues_count', 0)
        
        repo_dir = f"repos/{repo_name}"
        if not os.path.exists(repo_dir):
            return {
                'project': repo_name,
                'status': 'Not Cloned'
            }
        
        loc = subprocess.check_output(['cloc', repo_dir, '--json', '--timeout', '600', '--exclude-dir=third_party,third-party,3rdparty']).decode('utf-8')
        loc_info = json.loads(loc)

        c_cpp_relate_file_info = {
            'C': loc_info.get('C', {}), 
            'C++': loc_info.get('C++', {}), 
            'C/C++ Header': loc_info.get('C/C++ Header', {})
        }
        c_cpp_file = c_cpp_relate_file_info['C++'].get('nFiles', 0) +\
                    c_cpp_relate_file_info['C'].get('nFiles', 0) +\
                    c_cpp_relate_file_info['C/C++ Header'].get('nFiles', 0)
        c_cpp_loc = c_cpp_relate_file_info['C++'].get('code', 0) +\
                    c_cpp_relate_file_info['C'].get('code', 0) +\
                    c_cpp_relate_file_info['C/C++ Header'].get('code', 0)
        
        return {
            'project': repo_name,
            'stars': stars,
            'forks': forks,
            'watchers': watchers,
            'open_issues': open_issues,
            'C/C++ Files': c_cpp_file,
            'C/C++ lines': c_cpp_loc
        }
    except Exception as e:
        logger.error(f"Error getting repository information for {repo_name}.\n{e}")
        return {}
    
if __name__ == "__main__":
    benchmark = 'repos/benchmark.json'
    repo_list = benchmark
    result_file = 'repos/repos_info.json'

    with open(repo_list, 'r') as f:
        repo_json = json.load(f)
    
    result = []
    for repo in repo_json:
        repo_info = get_repo_specific_info(repo['project'])
        print(repo_info)
        result.append(repo_info)

    with open(result_file, 'w') as f:
        json.dump(result, f, indent=4)