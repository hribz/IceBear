add_executable(collectIncInfo CollectIncInfo.cpp DiffLineManager.cpp IncInfoCollectASTVisitor.cpp)

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

# add_executable(extractCG ExtractCG.cpp)
# target_link_libraries(extractCG
#   LLVM
#   clangTooling
#   clangBasic
#   clangASTMatchers
#   clangAST
#   clangIndex
# )