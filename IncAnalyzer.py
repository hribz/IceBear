import sys

from IncAnalysis.environment import Environment, ArgumentParser

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--project', type=str, dest='project', default=None,
                                 help='The directory of the project that need to be analyzed.')
        self.parser.add_argument('--build', type=str, dest='build', default=None,
                                 help='The command used to build the project.')

def main(argv):
    parser = RepoParser()
    opts = parser.parse_args(argv)
    env = Environment(opts)

    

if __name__ == '__main__':
    main(sys.argv)