# 2024/7/24
## 已完成功能
- CMake配置项目构建过程总体建模
- Repository类: 表示一个CMake构建系统管理的项目
  - src_path: 项目源代码路径
  - configurations: 当前项目在不同配置下的所有变体
  - process_all_session(): 对当前项目每个变体执行所有任务：构建、预处理、diff、生成调用图、......
  - xxx_every_config: 对项目的每个配置变体执行xxx任务
- Configurations类: 表示项目在某个确定配置下得到的变体
  - options: 当前配置下所有配置选项以及它们对应的取值
  - build_path: 当前变体所在的构建目录
  - reply_path: cmake_file_api返回构建过程信息所在目录
  - configure(): 在build_path目录下配置本变体
  - workspace: 配置当前变体之后，提取调用图、生成预处理后文件、分析diff文件等任务的工作目录
  - preprocess_repo(): 调用`panda`工具，在当前配置下，生成`compile_commands.json`记录的所有文件预处理后的文件
  - diff_with_other(other): 调用`diff`命令，将当前变体与other变体所有预处理后文件进行比较，记录二者不同的文件以及相同文件的不同行号
- clang_tool
  - extractCG.cpp: 遍历AST，记录访问到的Func节点，遇到CallExpr时，记录它的callee，并用callee与Func节点构成一条call graph的边

## 待完成功能
- Configurations类
  - extract_call_graph(): 调用`clang_tools`中基于`libtooling`实现的函数调用图生成工具，提取当前变体所有文件的调用图
  - generate_edm(): 调用`panda`工具，提取当前变体所有文件的 external function map 和 invocation list

## 问题
- 函数调用图生成工具的生成效率极低，可能因为当前的做法是遍历AST记录`CallExpr->getDirectCallee()`
  - 直接用预处理后的文件生成调用图是否可以提高效率？
  - 对预处理后文件提取调用图可能依赖于编译器？例如`gcc`生成的预处理后文件可能无法用`clang`的`libtooling`提取
- 函数节点应该使用USR格式的函数名来标识，因为存在同名重载函数；USR格式的函数名中可能存在引号`"`，所以储存的时候可能需要转义，或者用`len:func_name`的格式储存，len是func_name的长度
- 调用`panda`工具生成 external function map 时，工具提示`FileNotFoundError`并直接卡死

## 已解决问题
- 预处理后文件中包含一些文件位置信息，这些信息因为构建目录的不同而不同，此类信息对于增量分析无用，而diff后存在许多此类无用信息。通过开启编译器的"-P"选项可取消生成此类信息。
- 调用`panda`工具卡死的原因可能是某些命令不存在，例如`clang-extdef-mapping`未安装

# 2024/7/25
## 已完成功能
- Configurations类
  - incrementable: 表示当前配置变体能否进行增量分析，在解析diff成功后设置为True
  - extract_call_graph(): 添加增量分析，调用`FunctionCallGraph`工具，提取当前变体`变化`文件的调用图
  - generate_edm(): 添加增量分析，调用`panda`工具，提取当前变体`变化`文件的 external function map 和 invocation list
  - parse_diff_result(): 根据"diff -r -u0"的输出格式解析diff的结果，记录了文件修改，文件新增的情况，增量分析仅分析变化和新增的文件
- clang_tool
  - extractCG.cpp: 函数调用图提取工具的实现，遍历AST，记录访问到的Func节点，遇到CallExpr时，获取它的callee的USR表示，并用该USR表示与Func节点的USR表示构成一条call graph的边，以`<caller-usr-length>:<caller-usr> -> <callee-usr-length>:<callee-usr>`的格式记录。

## 待完成功能
- Configurations类
  - 增量CSA跨编译单元分析

## 已解决问题
- 关于函数调用图生成工具的效率问题，目前的解决方案是利用`panda`来并行地调用它，可以很大程度上降低时间开销
- 因构建目录名不同导致diff指令认为两个目录不同问题(e.g. `build/`和`build_0/`分别是两个变体的构建目录，虽然目录名不同，但是diff时应该当作相同处理)