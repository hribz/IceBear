# IceBear: Fine-Grained Incremental Scheduling C/C++ Static Analysis Tools
`IceBear` is a C/C++ static analysis tools incremental scheduler. Support static analysis tools as follow: [CSA(Clang Static Analyzer)](https://clang-analyzer.llvm.org/), [Clang-Tidy](https://clang.llvm.org/extra/clang-tidy/), [CppCheck](https://cppcheck.sourceforge.io/).
`IceBear` can incrementally schedule these tools, with all tools supporting file-level incremental scheduling, and `CSA, CppCheck` supporting function-level incremental analysis.

## Installation

`IceBear` is an analysis tools scheduler, so it's neccessary that the tools you want to use is available in your environment.

```bash
# Dependencies
$ sudo apt-get install clang-19 clang-tidy cmake bear
$ curl -fsSL https://github.com/Snape3058/panda/raw/demo/panda | sudo tee /usr/bin/panda >/dev/null
$ sudo chmod +x /usr/bin/panda

# Build incremental information collector.
$ mkdir build && cd build
$ cmake .. -DCMAKE_BUILD_TYPE=Release -DLLVM_DIR=path/to/cmake/llvm/
$ make 
```

## Usage
```bash
IncAnalyer 
```