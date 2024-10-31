from git import Repo
import argparse
import sys
import pandas as pd
from build_controller import Configuration, Repository
from utils import *
from logger import logger

def get_repo_csv(csv_path: str) -> pd.DataFrame:
    commit_df = pd.read_csv(csv_path)
    return commit_df

def clone_project(repo_name: str) -> None:
    try:
        repo_dir = f"/repos/{repo_name}"
        if os.path.exists(repo_dir):
            logger.info(f"[Clone Project] repository {repo_dir} has exists.")
            return True
        makedir(repo_dir)
        Repo.clone_from("https://github.com/"+repo_name+".git", repo_dir)
        return True
    except Exception:
        # clone error, repository no longer exists
        return False

def checkout_target_commit(repo_name: str, commit: str) -> bool:
    repo = Repo(f"../subject/{repo_name}")

    try:
        repo.git.checkout(commit)
        return True

    except Exception:
        print("error while checking out commit")
        return False

def reset_repository(repo_name: str):
    repo_dir = f"/repos/{repo_name}"
    repo = Repo(repo_dir)
    repo.git.reset("--hard")
    repo.git.clean("-xdf")

def get_local_repo_commit_parents(repo_name: str, commit: str) -> list:
    repo = Repo(f"/repos/{repo_name}")

    # ensure head commit
    assert repo.head.commit.hexsha == commit

    # return parent commits
    return [commit.hexsha for commit in repo.head.commit.parents]

class RepoConfig():
    def __init__(self, name, src_path):
        self.name = name
        self.src_path = src_path

def main(args):
    parser = ArgumentParser()
    opts = parser.parse_args(args)
    env = Environment(opts)
    repo_list = 'repos/repos.csv'
    
    repo_csv = get_repo_csv(repo_list)
    previous_repo_name = ""
    repo_config = None
    Repo = None

    for _, repo in repo_csv:
        repo_name = repo["project"]
        commit_sha = repo["hash"]

        if previous_repo_name != repo_name:
            clone_project(repo_name)
            # Analysis first commit as baseline.
            if checkout_target_commit(repo_name, commit_sha):
                previous_repo_name = repo_name
                repo_dir = Path(f"/repos/{repo_name}")
                repo_config = RepoConfig(repo_name, str(repo_dir))
                Repo = Repository(repo_config.name, repo_config.src_path, env, build_root=f"{str(repo_dir.absolute())}_build")
                Repo.process_one_config(Repo.configurations[-1])
            else:
                logger.error(f"[Checkout Commit] {repo_name} checkout to {commit_sha} failed!")
        else:
            # Analysis subsequent commit incrementally.
            if checkout_target_commit(repo_name, commit_sha):
                Repo.add_configuration([])
                Repo.process_one_config(Repo.configurations[-1])
            else:
                logger.error(f"[Checkout Commit] {repo_name} checkout to {commit_sha} failed!")


if __name__ == "__main__":
    main(sys.argv[1:])