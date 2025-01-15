# IceBear: A Fine-Grained Incremental Scheduler for Static Analyzers
*IceBear* is a scheduler for C/C++ static analysis tools, supports static analyzers as follow: [CSA(Clang Static Analyzer)](https://clang-analyzer.llvm.org/), [Clang-Tidy](https://clang.llvm.org/extra/clang-tidy/), [CppCheck](https://cppcheck.sourceforge.io/).
*IceBear* can incrementally schedule these tools, with all tools supporting *file-level* incremental scheduling, and *CSA, CppCheck* supporting *function-level* incremental analysis (need install our modified version).

## Docker Image
### Prerequisites
- Docker

### For Usage
This is a simple version for 

### For Expriments
The experiments in Section 3 require building 8 C/C++ projects and involve setting up a relatively complex environment with various dependencies.
To facilitate the reproduction of the experimental results, we recommend using the Docker image we provide.

```
docker pull hribz/icebear-fse-expriments
docker run -it hribz/icebear-fse-expriments
```

## Installation
*IceBear* is an analysis tools scheduler, so it's neccessary that the tools you want to use is available in your environment.

### CSA & Cppcheck
If you want to enable *function-level* incremental scheduling, please install our modified version.

It is recommended to use our [precompiled version](https://github.com/hribz/IceBear/releases/tag/v0.1) for the Linux x86 environment.

```bash
cd /path/to/
tar -zxvf cppcheck-ica.tar.gz
tar -zxvf llvm-project-ica.tar.gz
# The path to CSA is /path/to/LLVM-19.1.5-Linux/bin/clang
# The path to cppcheck is /path/to/cppcheck-ica/bin/cppcheck
```
Or build them from source code ([CSA](https://github.com/hribz/llvm-project-ica/tree/main) and [Cppcheck](https://github.com/hribz/cppcheck-ica/tree/2.16.ica)) by yourself.

### IceBear
You need to install:
- clang-19
- bear
- cmake >= 3.10
- git

Follow these commands to install *IncBear*:
```bash
git clone https://github.com/hribz/IceBear.git
cd IceBear
pip install -r requirements.py
python build.py -j8
# Move icebear to any environment path.
mv icebear ~/.local/bin/
```

## Usage
To perform static analysis on a project using *IceBear*, you first need to ensure that the project can be successfully built.

You can use *IceBear* to build the project, and the analysis will automatically start after the build is complete.

```bash
cd path/to/project
icebear --repo . --build 'make -j16' -o ice-bear-output -j 16 --inc func --clang /path/to/LLVM-19.1.5-Linux/bin/clang --cppcheck /path/to/cppcheck-ica/bin/cppcheck
```

You can also use [Bear (Build EAR)](https://github.com/rizsotto/Bear) to record the [JSON Compilation Database](https://clang.llvm.org/docs/JSONCompilationDatabase.html) from the build process. Then, pass the compilation database to IceBear, and IceBear will analyze the files recorded in the compilation database.

```bash
cd path/to/project
bear --output compile_commands.json -- make -j16
icebear --repo . -f compile_commands.json -o ice-bear-output -j 16 --inc func --clang /path/to/LLVM-19.1.5-Linux/bin/clang --cppcheck /path/to/cppcheck-ica/bin/cppcheck
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
- `--clang`: the clang used to analyze (CSA is a part of clang). Please use our modified version of clang if `--inc` is set to `func`.
- `--cppcheck`: the cppcheck used to analyze. Please use our modified version of cppcheck if `--inc` is set to `func`.

And the analysis result can be found at the `csa`, `cppcheck`, `clang-tidy` folders in the output directory. The `all_reports.json` file provides a brief summary of all reports.