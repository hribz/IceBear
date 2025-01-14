add_executable(collectIncInfo CollectIncInfo.cpp DiffLineManager.cpp IncInfoCollectASTVisitor.cpp ReverseCallGraph.cpp)

# Ensure the LLVM and Clang include directories are added
target_include_directories(collectIncInfo PRIVATE ${LLVM_INCLUDE_DIRS} ${CLANG_INCLUDE_DIRS})

target_link_libraries(collectIncInfo PRIVATE
  LLVMSupport
  LLVMOption
  clangFrontend
  clangSerialization
  clangTooling
  clangBasic
  clangASTMatchers
  clangAST
  clangAnalysis
  clangIndex
  clangDriver
  clangParse
  clangSema
  clangEdit
  clangLex
)