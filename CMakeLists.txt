cmake_minimum_required(VERSION 3.10)
project(FunctionCallGraph)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True) 

set(MY_LLVM_VERSION 19)
find_package(LLVM ${MY_LLVM_VERSION} REQUIRED CONFIG)
message(STATUS "Found LLVM: ${LLVM_INCLUDE_DIRS}")

set(CLANG_VERSION 19)
list(APPEND CMAKE_PREFIX_PATH "/usr/lib/cmake/llvm-${CLANG_VERSION}/")
list(APPEND CMAKE_PREFIX_PATH "/usr/lib/cmake/clang-${CLANG_VERSION}/")

find_package(Clang ${MY_LLVM_VERSION} REQUIRED CONFIG)
message(STATUS "Found Clang: ${CLANG_VERSION}")

# Set the LLVM and Clang header and library paths
include_directories(SYSTEM "${LLVM_INCLUDE_DIRS};${CLANG_INCLUDE_DIRS}")

add_definitions(${LLVM_DEFINITIONS})
include_directories(SYSTEM "${LLVM_INCLUDE_DIRS};${CLANG_INCLUDE_DIRS}")
add_subdirectory(clang_tool)
