import sys
import os
from pathlib import Path

from IncAnalysis.environment import Environment, ArgumentParser
from IncAnalysis.repository import UpdateConfigRepository
from IncAnalysis.logger import logger
from IncAnalysis.utils import makedir
from IncAnalysis.reports_postprocess import postprocess_workspace

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--repo', type=str, dest='repo', default=".",
                                 help='The directory of the project that need to be analyzed.')
        self.parser.add_argument('--build', type=str, dest='build', default=None,
                                 help='The command used to build the project.')
        self.parser.add_argument('-o', '--output', type=str, dest='output', default='./ice-bear-output',
                                 help='Store analysis results to directory.')
        self.parser.add_argument('-f', '--compilation-database', type=str, dest='cdb',
                                 help='Customize the input compilation database',
                                 default='./compile_commands.json')
        self.parser.add_argument('-bp', '--build-dir', type=str, dest='build_path', default='.',
                                 help='The directory to build the project.')

def main(argv):
    parser = RepoParser()
    opts = parser.parse_args(argv)
    ice_bear_path = os.path.abspath(__file__)
    env = Environment(opts, os.path.dirname(ice_bear_path))

    if not os.path.exists(opts.repo):
        logger.info(f"Please make sure repository {opts.repo} exists.")
        exit(1)
    repo = os.path.abspath(opts.repo)
    
    workspace = os.path.abspath(opts.output)
    makedir(workspace)

    build_command = opts.build
    build_root = os.path.abspath(opts.build_path)
    if build_command is None and not os.path.exists(opts.cdb):
        logger.info(f"Please make sure compilation database file {opts.cdb} exists.")
        exit(1)
    cdb = os.path.abspath(opts.cdb)

    Repo = UpdateConfigRepository(os.path.basename(repo), repo, env, 
                                  workspace=workspace,
                                  configure_scripts=[],
                                  build_script=build_command,
                                  build_root=build_root,
                                  cdb=cdb,
                                  need_build=build_command is not None,
                                  need_configure=False,
                                  version_stamp=env.timestamp,
                                  default_build_type="unknown"
                                  )
    Repo.process_one_config(summary_path="logs", reports_statistics=False)
    postprocess_workspace(workspace=workspace, this_version=env.timestamp)

if __name__ == '__main__':
    main(sys.argv[1:])