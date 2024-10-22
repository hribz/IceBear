cmake_minimum_required(VERSION 3.10)
project(FunctionCallGraph)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True) 

# Align LLVM version with CSA.
set(MY_LLVM_VERSION 20)
find_package(LLVM ${MY_LLVM_VERSION} REQUIRED CONFIG)
message(STATUS "Found LLVM: ${LLVM_INCLUDE_DIRS}")

find_package(Clang ${MY_LLVM_VERSION} REQUIRED CONFIG)
message(STATUS "Found Clang: ${CLANG_INCLUDE_DIRS}")

# Set the LLVM and Clang header and library paths.
include_directories(SYSTEM "${LLVM_INCLUDE_DIRS};${CLANG_INCLUDE_DIRS}")

add_definitions(${LLVM_DEFINITIONS})
# LLVM default option disable RTTI.
add_compile_options(-fno-rtti)
add_subdirectory(clang_tool)
