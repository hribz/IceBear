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
  - generate_efm(): 调用`panda`工具，提取当前变体所有文件的 external function map 和 invocation list

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
  - generate_efm(): 添加增量分析，调用`panda`工具，提取当前变体`变化`文件的 external function map 和 invocation list
  - parse_diff_result(): 根据"diff -r -u0"的输出格式解析diff的结果，记录了文件修改，文件新增的情况，增量分析仅分析变化和新增的文件
- clang_tool
  - extractCG.cpp: 函数调用图提取工具的实现，遍历AST，记录访问到的Func节点，遇到CallExpr时，获取它的callee的USR表示，并用该USR表示与Func节点的USR表示构成一条call graph的边，以`<caller-usr-length>:<caller-usr> -> <callee-usr-length>:<callee-usr>`的格式记录。

## 待完成功能
- Configurations类
  - 增量CSA跨编译单元分析

## 已解决问题
- 关于函数调用图生成工具的效率问题，目前的解决方案是利用`panda`来并行地调用它，可以很大程度上降低时间开销
- 因构建目录名不同导致diff指令认为两个目录不同问题(e.g. `build/`和`build_0/`分别是两个变体的构建目录，虽然目录名不同，但是diff时应该当作相同处理)

# 2024/8/27
## 待完成功能
- Configurations类
  - 记录初次CSA分析的结果，包括AnalysisConsumer::FunctionSummarize
- DiffDB类
  - 记录diff结果，包括文件修改，文件新增，文件删除
  - 在AST上分析diff结果，确定哪些函数入口的检测过程将受到影响
  - 将diff结果以某种形式储存下来
- clang_tool
  extractCG.cpp: 读取文件相关的行号级别diff信息，找到所在行发生变化的函数、类型、全局变量，并确定它们之间的依赖关系

# 2024/8/28
## 问题
- CSA的AnalysisCosumer::FunctionSummarize并没有记录某个函数被哪些函数inline，只记录了

## 解决方案
- 修改CSA，添加参数 `-analyzer-dump-fsum=xxx.fs`，将内联结果输出到某个文件中

# 2024/9/9
## 待完成功能
- 通过行号确定函数：构建CG时，顺便判断每个Decl的Loc范围是否包含变化行号
- 通过行号确定全局常量：通过`VisitDecl`记录所有全局常量声明，通过`ProcessDeclRefExpr`处理全局常量引用，目前考虑`VarDecl, EnumConstantDecl`。首先标记直接发生变化的常量，然后在处理引用时，判断该引用用于全局常量初始化，还是用在函数内部。
- 通过行号确定类型

## 问题
- Sometimes line number will change the semantics of the code, such as `enum` object, the different order of enum constant will lead to different value.
- class和struct中的字段顺序，会影响构造函数初始化时的顺序，因此字段发生变化时，构造函数也必须认为发生了变化
- 全局常量传播问题：某个常量发生变化后，如何确定哪些其它常量发生了变化

## 解决方案
- 关于上述因字段顺序影响语义的例子，必须把整个枚举类型作为整体进行分析，不能只分析枚举类型中的某个枚举常量

# 2024/9/11
## 解决方案
- class和struct中的字段变化问题：字段顺序确实会影响构造函数，但是没必要字段发生变化就认为构造函数发生变化，因为只有构造函数显式的声明`C1(): field1(xxx) {}`才会按照定义顺序进行初始化。因此可以先找到AST中的`CXXCtorInitializer`判断它本身以及对应的字段是否发生了变化，再决定是否重新分析。
- 全局常量传播问题：维护一个集合`GlobalConstantSet`，其中包含了发生修改的全局常量，以及经过赋值规则传播到的全局常量。随后，遍历整个AST，将所有使用了这些常量的函数标记为需要重新分析。

# 2024/9/12
## 问题
- 不应该将处理的常量局限于全局常量，而是函数/方法外的常量。

# 2024/9/18
## 问题
- 突然发现用panda执行`generate-efm`任务时非常缓慢，例如json项目原来只需要20s左右，现在需要500s。后来尝试给panda添加`--efmer /usr/bin/clang-17`参数，恢复正常。原因是之前使用了自己编译的`Debug`版本的llvm，所以运行时间非常长。

# 2024/9/25
## 问题 & 解决方案
- 先用`compile_commands.json`中储存的编译选项生成预处理后文件`xx.cpp.ii`，再用`clang-tool`和同样的编译选项处理`xx.cpp.ii`时出现了大量报错：
  - `unable to handle compilation, expected exactly one compiler job in ...`: 这个报错的原因是未指定文件语言类型，因为无法识别后缀为`.ii`的文件，解决方法是添加`-x c++`（或`-x c`）选项
  - `error: constexpr function never produces a constant expression [-Winvalid-constexpr] floor(long double __x) { return __builtin_floorl(__x); }`: 该报错的原因推测是constexpr函数中调用了内置函数。这个报错似乎并不来自于生成AST的阶段，目前将这种报错忽略，因为似乎不影响`collectIncInfo`工具分析AST。但这可能是一个隐患，因为目前无法说明对预处理文件和原文件的AST进行分析是等价的。

# 2024/9/26
## 问题
- 