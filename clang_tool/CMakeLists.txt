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

# add_executable(extractCG ExtractCG.cpp)
# target_link_libraries(extractCG
#   LLVM
#   clangTooling
#   clangBasic
#   clangASTMatchers
#   clangAST
#   clangIndex
# )