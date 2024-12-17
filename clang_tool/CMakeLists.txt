add_executable(collectIncInfo CollectIncInfo.cpp DiffLineManager.cpp IncInfoCollectASTVisitor.cpp)
target_link_libraries(collectIncInfo PRIVATE
  LLVM
  clangFrontend
  clangSerialization
  clangTooling
  clangBasic
  clangASTMatchers
  clangAST
  clangAnalysis
  clangIndex
)

add_executable(extractCG ExtractCG.cpp)
target_link_libraries(extractCG
  LLVM
  clangTooling
  clangBasic
  clangASTMatchers
  clangAST
  clangIndex
)