![logo](assets/logo.drawio.svg)

# The IceBear Tool
*IceBear* is a scheduler for C/C++ static analysis tools, built on [*Bear*](https://github.com/rizsotto/Bear) and [*Panda*](https://github.com/SQUARE-RG/panda), supports static analyzers as follow: [CSA(Clang Static Analyzer)](https://clang-analyzer.llvm.org/), [Clang-Tidy](https://clang.llvm.org/extra/clang-tidy/), [CppCheck](https://cppcheck.sourceforge.io/), [GSA(GCC Static Analyzer)](https://gcc.gnu.org/wiki/StaticAnalyzer).
*IceBear* can incrementally schedule these tools, with all tools supporting *file-level* incremental scheduling, and *CSA, CppCheck, GSA* supporting *function-level* incremental analysis (need install our modified version).

## Installation
*IceBear* is an analysis tools scheduler, so it's neccessary that the tools you want to use is available in your environment.

If you want to enable *function-level* incremental scheduling, please install our modified version CSA and Cppcheck.

### CSA
It is recommended to use our [pre-built version CSA](https://github.com/hribz/IceBear/releases/tag/v0.1) for the Linux x86 environment, or build CSA from [source code](https://github.com/hribz/llvm-project-ica/tree/main) by yourself.


```bash
cd /path/to/
tar -zxvf llvm-project-ica.tar.gz
# The path to CSA is /path/to/LLVM-19.1.5-Linux/bin/clang
```

### Cppcheck
If you want to try *function-level* incremental [Cppcheck](https://github.com/hribz/cppcheck-ica/tree/2.16.ica), please build from source code as follows.

```bash
wget https://github.com/hribz/cppcheck-ica/archive/refs/heads/2.16.ica.zip
unzip 2.16.ica.zip
cd cppcheck-ica-2.16.ica
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/path/to/cppcheck-ica
make -j16
make install
# The path to Cppcheck is /path/to/cppcheck-ica/bin/cppcheck
```

### IceBear
You need to install:
- clang-19
- bear
- cmake >= 3.10
- uv

Follow these commands to install *IceBear*:
```bash
git clone https://github.com/hribz/IceBear.git
cd IceBear
uv sync
uv run python build.py -j8
# Move icebear to any environment path.
mv icebear/icebear ~/.local/bin/
```

## Usage
To perform static analysis on a project using *IceBear*, you first need to ensure that the project can be successfully built.

You can use *IceBear* to build the project, and the analysis will automatically start after the build is complete.

```bash
cd path/to/project
icebear --repo . --build 'make -j16' -o ice-bear-output -j 16 --inc func --analyzers csa cppcheck --clang /path/to/LLVM-19.1.5-Linux/bin/clang --cppcheck /path/to/cppcheck-ica/bin/cppcheck
```

You can also use [Bear (Build EAR)](https://github.com/rizsotto/Bear) to record the [JSON Compilation Database](https://clang.llvm.org/docs/JSONCompilationDatabase.html) from the build process. Then, pass the compilation database to IceBear, and IceBear will analyze the files recorded in the compilation database.

```bash
cd path/to/project
bear --output compile_commands.json -- make -j16
icebear --repo . -f compile_commands.json -o ice-bear-output -j 16 --inc func --analyzers csa cppcheck --clang --clang /path/to/LLVM-19.1.5-Linux/bin/clang --cppcheck /path/to/cppcheck-ica/bin/cppcheck
```

The meanings of the *IceBear* parameters are as follows:
- `--repo`: the path to the project you want to analyze.
- `--build`: the command to build the project.
- `--build-dir`: the directory to build the project, default value is current directory.
- `-f`: the path to the compilation database.
- `-o`: the directory to store the analysis results.
- `-j`: the number of parrallel workers to perform analysis.
- `--inc`: the strategy of analysis.
  - `noinc`: all files recorded in compilation database will be analyzed. 
  - `file`: only files whose corresponding preprocessed file changed will be analyzed.
  - `func`: only changed code and affected components (e.g. AST nodes, functions) will be analyzed and generate reports.
- `--analyzers`: the analyzers used to do analyze, selecting from [csa, clang-tidy, cppcheck, gsa].
- `--clang`: the clang used to analyze (CSA is a part of clang). Please use our modified version of clang if `--inc` is set to `func`.
- `--cppcheck`: the cppcheck used to analyze. Please use our modified version of cppcheck if `--inc` is set to `func`.

And the analysis result can be found at the `csa`, `cppcheck`, `clang-tidy` folders in the output directory. The `all_reports.json` file provides a brief summary of all reports.