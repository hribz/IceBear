# IncAnalyzer
`IncAnalyzer` is a C/C++ static analysis tools incremental scheduler. Support static analysis tools as follow: [CSA(Clang Static Analyzer)](https://clang-analyzer.llvm.org/), [Clang-Tidy](https://clang.llvm.org/extra/clang-tidy/), [CppCheck](https://cppcheck.sourceforge.io/), [Infer](https://fbinfer.com/).
`IncAnalyzer` can incrementally schedule these tools, with all tools supporting file-level incremental scheduling, and CSA supporting function-level incremental scheduling.

## Installation

`IncAnalyzer` is an analysis tools scheduler, so it's neccessary that the tools you want to use is available in your environment.

```bash
# Dependencies
sudo apt-get install clang cmake

# Build function-level incremental information collector.
mkdir build && cd build
cmake .. -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Release -DLLVM_DIR=path/to/cmake/llvm/ -DClang_DIR=path/to/cmake/clang
make
```