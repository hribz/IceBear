import json
from logger import logger
import os

class CompileCommand:
    def __init__(self, ccmd=None):
        self.compiler = None
        self.file = None
        self.directory = None
        self.arguments = None
        self.language = None
        if ccmd:
            self.parse(ccmd)

    def __str__(self):
        return json.dumps(
                {
                    'arguments': self.arguments,
                    'directory': self.directory,
                    'file': self.file,
                    'compiler': self.compiler,
                    'language': self.language,
                }, indent=4)

    def parse(self, ccmd):
        # Check the validity of a compile command.
        if not CompileCommand.isValidCompileCommand(ccmd):
            logger.error('W: Invalid compile command object.\n' +
                     json.dumps(ccmd, indent=4))
            return None

        # directoy and file
        self.directory = os.path.abspath(ccmd['directory'])
        self.file = os.path.abspath(os.path.join(
            self.directory, ccmd['file']))

        # File type: clang::driver::types::lookupTypeForExtension
        extname = os.path.splitext(self.file)[1][1:]
        if extname == 'c':
            self.language = 'c'
        elif extname in {'C', 'cc', 'CC', 'cp', 'cpp', 'CPP',
                'cxx', 'CXX', 'c++', 'C++'}:
            self.language = 'c++'
#       elif extname == 'i':
#           self.language = 'PP-C'
#       elif extname == 'ii':
#           self.language = 'PP-C++'
        else:
            self.language = 'Unknown'

        # command => arguments
        arguments = None
        if 'command' in ccmd:
            from shlex import split
            arguments = split(ccmd['command'])
        else:
            arguments = ccmd['arguments']

        # compiler
        self.compiler = arguments[0]

        # Adjust arguments.
        i, n = 0, len(arguments)
        self.arguments = []
        prune1 = {'-c', '-fsyntax-only', '-save-temps'}
        prune2 = {'-o', '-MF', '-MT', '-MQ', '-MJ'}
        prunes2 = {'-M', '-W', '-g'}
        while True:
            i += 1
            if i >= n:
                break
            if arguments[i] in prune1:
                continue
            if arguments[i] in prune2:
                i += 1
                continue
            if arguments[i][:3] == '-o=':
                continue
            if arguments[i][:2] in prunes2:
                continue
            self.arguments.append(arguments[i])
            # Reset language if provided in command line arguments.
            if arguments[i] == '-x':
                self.language = arguments[i + 1]
            elif arguments[i][:2] == '-x':
                self.language = arguments[i][2:]

        return self


    @staticmethod
    def isValidCompileCommand(ccmd):
        return 'file' in ccmd and 'directory' in ccmd and \
                ('arguments' in ccmd or 'command' in ccmd)