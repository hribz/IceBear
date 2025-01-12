# IceBear: A Fine-Grained Incremental Scheduler for C/C++ Static Analysis Tools
`IceBear` is a C/C++ static analysis tools incremental scheduler. Support static analysis tools as follow: [CSA(Clang Static Analyzer)](https://clang-analyzer.llvm.org/), [Clang-Tidy](https://clang.llvm.org/extra/clang-tidy/), [CppCheck](https://cppcheck.sourceforge.io/).
`IceBear` can incrementally schedule these tools, with all tools supporting file-level incremental scheduling, and `CSA, CppCheck` supporting function-level incremental analysis (need install our modified version).

## Installation
### CSA & Cppcheck
`IceBear` is an analysis tools scheduler, so it's neccessary that the tools you want to use is available in your environment.

If you want to enable function-level incremental scheduling, please install our modified version [CSA](https://github.com/hribz/llvm-project-ica/tree/main) and [Cppcheck](https://github.com/hribz/cppcheck-ica/tree/2.16.ica).

```bash

```

### IceBear
```bash
# Dependencies
$ sudo apt-get install clang-19 clang-tidy bear cmake

# Build icebear.
$ git clone https://github.com/hribz/IceBear.git
$ cd IceBear
$ python build.py -j8

# Move icebear to any environment path.
$ mv icebear ~/.local/bin/
```

## Usage

```bash
cd path/to/project
icebear --repo /path/to/project --build 'make -j16' -o ice-bear-output -j 16 --inc func --clang path/to/clang --cppcheck path/to/cppcheck
```