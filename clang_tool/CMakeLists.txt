# traversal AST and generate CallGraph
add_executable(FunctionCallGraph extractCG.cpp)
target_link_libraries(FunctionCallGraph
  LLVM
  clangTooling
  clangBasic
  clangASTMatchers
  clangAST
)

# clang static checker: dump cfg
add_library(CFGDumpChecker MODULE CFGDumpChecker.cpp)

set_target_properties(CFGDumpChecker PROPERTIES
  COMPILE_FLAGS "-fno-rtti"
)