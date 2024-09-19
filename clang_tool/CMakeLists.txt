# traversal AST and generate CallGraph
add_executable(collectIncInfo CollectIncInfo.cpp)
target_link_libraries(collectIncInfo
  LLVM
  clangTooling
  clangBasic
  clangASTMatchers
  clangAST
  clangIndex
)