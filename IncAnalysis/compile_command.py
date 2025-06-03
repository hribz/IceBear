import json
import os

from IncAnalysis.logger import logger


class CompileCommand:
    def __init__(self, ccmd, file_as_identifier=True):
        self.directory = None
        self.language = "Unknown"
        self.file_as_identifier = file_as_identifier

        if "command" in ccmd:
            self.origin_cmd = ccmd["command"]
        else:
            self.origin_cmd = " ".join(ccmd["arguments"])
        self.parse(ccmd)

    def __str__(self):
        return json.dumps(
            {
                "arguments": self.arguments,
                "directory": self.directory,
                "file": self.file,
                "compiler": self.compiler,
                "language": self.language,
            },
            indent=4,
        )

    def restore_to_json(self):
        return {
            "directory": self.directory,
            "command": self.origin_cmd,
            "file": self.file,
        }

    def parse(self, ccmd):
        # Check the validity of a compile command.
        if not CompileCommand.isValidCompileCommand(ccmd):
            logger.error(
                "W: Invalid compile command object.\n" + json.dumps(ccmd, indent=4)
            )
            return None

        # directoy and file
        self.directory = os.path.abspath(ccmd["directory"])
        self.file = os.path.abspath(os.path.join(self.directory, ccmd["file"]))
        self.identifier = self.file
        self.output = ccmd.get("output")
        if self.output:
            self.output = os.path.abspath(os.path.join(self.directory, ccmd["output"]))

        # File type: clang::driver::types::lookupTypeForExtension
        extname = os.path.splitext(self.file)[1][1:]
        if extname == "c":
            self.language = "c"
        elif extname in {
            "C",
            "cc",
            "CC",
            "cp",
            "cpp",
            "CPP",
            "cxx",
            "CXX",
            "c++",
            "C++",
        }:
            self.language = "c++"
        #       elif extname == 'i':
        #           self.language = 'PP-C'
        #       elif extname == 'ii':
        #           self.language = 'PP-C++'
        else:
            self.language = "Unknown"

        # command => arguments
        arguments = None
        if "command" in ccmd:
            from shlex import split

            arguments = split(ccmd["command"])
        else:
            arguments = ccmd["arguments"]

        # compiler
        self.compiler = arguments[0]

        # Adjust arguments.
        i, n = 0, len(arguments)
        self.arguments = []
        prune1 = {"-c", "-fsyntax-only", "-save-temps"}
        prune2 = {"-o", "-MF", "-MT", "-MQ", "-MJ"}
        prunes2 = {"-M", "-W", "-g"}
        while True:
            i += 1
            if i >= n:
                break
            if arguments[i] in prune1:
                continue
            if arguments[i] in prune2:
                i += 1
                if not self.output:
                    self.output = os.path.abspath(
                        os.path.join(self.directory, arguments[i])
                    )
                continue
            if arguments[i][:3] == "-o=":
                if not self.output:
                    self.output = os.path.abspath(
                        os.path.join(self.directory, arguments[i][3:])
                    )
                continue
            if arguments[i][:2] in prunes2:
                continue
            self.arguments.append(arguments[i])
            # Reset language if provided in command line arguments.
            if arguments[i] == "-x":
                self.language = arguments[i + 1]
            elif arguments[i][:2] == "-x":
                self.language = arguments[i][2:]

        return self

    @staticmethod
    def isValidCompileCommand(ccmd):
        return (
            "file" in ccmd
            and "directory" in ccmd
            and ("arguments" in ccmd or "command" in ccmd)
        )
