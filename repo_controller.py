import datetime
from git import Repo
import argparse
import sys
import pandas as pd
from build_controller import Configuration, Repository
from utils import *
from logger import logger
import csv
import subprocess

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
        update_submodules(repo_dir)
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

def get_local_repo_commit_parents(repo_dir: str, commit: str) -> list:
    assert os.path.isabs(repo_dir)
    repo = Repo(repo_dir)

    # ensure head commit
    assert repo.head.commit.hexsha == commit

    # return parent commits
    return [commit.hexsha for commit in repo.head.commit.parents]

init_csv = True

def add_to_csv(headers, data, csv_file):
    with open(csv_file, 'w' if init_csv else 'a', newline='') as f:
        writer = csv.writer(f)
        if init_csv:
            writer.writerow(headers)
        writer.writerows(data)

def main(args):
    global init_csv
    parser = ArgumentParser()
    opts = parser.parse_args(args)
    env = Environment(opts)
    # repo_list = 'repos/repos.csv'
    repo_list = 'repos/test.csv'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = f'result/repos/result_{timestamp}.csv'
    result_file_specific = f'result/repos/result_specific_{timestamp}.csv'
    
    repo_csv = get_repo_csv(repo_list)
    previous_repo_name = ""
    Repo = None
    
    class STATUS(Enum):
        BEGIN = auto()
        NORMAL = auto()
        CLONE_FAILED = auto()
        CHECK_FAILED = auto()
    status = STATUS.BEGIN

    for _, repo in repo_csv.iterrows():
        repo_name = repo["project"]
        os.chdir(env.PWD)
        repo_dir = Path(env.PWD / f"repos/{repo_name}")
        abs_repo_path = str(repo_dir.absolute())
        print(abs_repo_path)
        commit_sha = repo["hash"]

        if previous_repo_name != repo_name:
            if status == STATUS.NORMAL:
                logger.info('---------------END SUMMARY-------------\n'+Repo.session_summary())
                headers, data = Repo.summary_to_csv_specific()
                add_to_csv(headers, data, result_file_specific)
                headers, data = Repo.summary_to_csv()
                add_to_csv(headers, data, result_file)
                init_csv = False
            status = STATUS.NORMAL
            if not clone_project(repo_name):
                status = STATUS.CLONE_FAILED
                continue
        status = STATUS.NORMAL
        if checkout_target_commit(abs_repo_path, commit_sha):
            if previous_repo_name != repo_name:
                # Analysis first commit as baseline.
                previous_repo_name = repo_name
                Repo = Repository(repo_name, abs_repo_path, env, build_root=f"{abs_repo_path}_build")
                Repo.process_one_config(Repo.configurations[-1])
            else:
                # Analysis subsequent commit incrementally.
                Repo.add_configuration([])
                Repo.process_one_config(Repo.configurations[-1])
        else:
            status = STATUS.CHECK_FAILED
            logger.error(f"[Checkout Commit] {repo_name} checkout to {commit_sha} failed!")
    if Repo:
        logger.info('---------------END SUMMARY-------------\n'+Repo.session_summary())
        headers, data = Repo.summary_to_csv_specific()
        add_to_csv(headers, data, result_file_specific)
        headers, data = Repo.summary_to_csv()
        add_to_csv(headers, data, result_file)

if __name__ == "__main__":
    main(sys.argv[1:])