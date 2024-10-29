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

# 2024/10/13
## 问题
- CSA 只关心 Top Level Decl, 为了避免分析到 PCH 文件导入的 Decl ，但是目前的策略是比对预处理后的文件，无法过滤掉来自 PCH 的 Decl 信息。

## 解决方案
- 是否可以在 AST 上添加一个 pass，在 collectIncInfo 之后，遍历预处理前文件，过滤`functions_need_to_be_reanalyzed`中不属于 Top Level Decl 的函数/方法。

# 2024/10/14
## 已完成功能
- 分别实现了不考虑、考虑`fsum`下的重分析函数确定算法

# 2024/10/15
## 问题
- 从预处理后文件收集增量信息时，输出的CallGraph和FunctionReanalyze的函数名称可能包含文件位置信息(如clang_tool/test/function_obj.cpp)。这种信息会由于预处理而发生变化，尤其是行号。不管是`AnalysisDeclContext::getFunctionName`还是`USR`都可能会用到位置信息。这就导致函数名称与CSA的Fcuntion Summaries不匹配，因为不可能让CSA也去分析预处理后的文件，这样会使得报告无法查看。

## 解决方案
- 1. 从预处理前文件中收集增量信息：对预处理前文件做diff，这样就需要考虑预处理指令，使得在AST上分析diff信息变得十分复杂。
- 2. 自行实现一个`getFunctionName`函数：`AnalysisDeclContext::getFunctionName`的实现并不复杂，或许可以自行实现一个不使用loc信息的版本。
- 3. 在生成CallGraph和FunctionReanalyze时，忽略掉包含loc信息的节点：假如包含loc信息的节点确实发生了变化，这不是一个解决方案。

# 2024/10/16
## 问题
- 继续研究了带有loc信息的FunctionName的来源，发现主要来自于lambda函数自动生成的构造函数，或者是匿名的union, struct, class自动生成的构造函数。

## 解决方案
- 重写`getFunctionName`函数，过滤掉可能的loc信息。虽然这会导致不同函数有相同的函数名，但是CSA的`-analyze-function`本身就有这个问题，并且这种带loc信息的函数在项目中可能并没有那么多。
- 已知可以通过调整`ASTContext.PrintingPolicy`的`AnonymousTagLocations`字段为`false`来屏蔽掉部分函数名中的location信息，例如匿名struct/union，但是无法屏蔽掉参数类型的location信息。

# 2024/10/17
## 待完成功能
- 为CSA添加指定多函数分析的功能，现有CSA仅支持指定一个函数进行分析。

## 问题
- 预处理后的文件作为 Clang Tool 的输入时，某些 __builtin 函数会导致前端解析报错，从而导致生成的 AST 不完整，进而导致 CG 不完整，但是直接将原文件作为输入就没这个问题。

# 2024/10/18
## 解决方案
- 上述__builtin和函数名称包含行号问题的原因可能都是因为生成预处理文件时开启了`-P`选项导致，预处理文件中应当包含行号信息，才能保证解析正确，并且可以通过`getSpellingLineNumber`和`getExpansionLineNumber`分别获取原文件和预处理后文件的行号。
- 注意在diff时忽略预处理文件中记录原文件的行号信息。

# 2024/10/20
## 问题
- .fs文件中的函数名与.cg中的函数名可能出现不匹配的情况，主要有下列两种情况：
  - .fs由CSA生成，.cg由CollectIncInfo生成，二者使用的llvm版本不同时，`AnalysisDeclContext::getFunctionName`生成的函数名也不同，因此需要确保llvm版本相同
  - CSA实际分析过程中内联了不存在与CallGraph上的函数（该情况还没找到实际例子）

## 解决方案
- 反转了）其实是collectIncInfo的'-loc'参数默认设置为false的问题，既然行号的问题解决了，就应该设置为true，继续输出行号信息。

# 2024/10/21
## 问题
- 同一个函数在.fs和.cg中的函数名不同，可能因为：
  1. Differences between process file directly and process preprocessed file.
  2. Some tiny differences between function names in .fs and .cg files. 
     (e.g. `const class Config::ConfigIterator` and `const ConfigIterator`;)
     This problem maybe resolved by aligning llvm version between CSA and collectIncInfo.

## 解决方案
- 该问题在同一版本后仍未解决，尝试打印PrettyPolicy比较差异：经过比较，Policy没有区别。
- gpt认为可能原因是AST在解析过程中发生了变化（例如模板实例化），因此输出FunctionName的时机也会影响结果。
- 上面`const class`的差别原因以及其它情况的原因可见clang_tool/test/function_name.cpp

# 2024/10/22
## 问题
- RAII的对象在生命周期结束时会自动调用析构函数，但是AST上并没有显式的调用节点，因此CG上不存在析构函数的调用。但是CSA会考虑生命周期结束时调用析构函数。
- 对象的生命周期不一定是`{}`之间，例如临时对象`A{};`由于没有引用，它的声明周期仅为当前语句。

# 2024/10/23
## 问题
- AST确实没有隐式调用析构函数的节点，CSA之所以能考虑到它们的隐式调用，是因为生成CFG时可以开启选项`addImplicitDtors`使得CFG中包含隐式的析构函数调用。

## 解决方案
- 在分析到FunctionDecl中使用了某个类/结构体时，如果它具有显式的析构函数，就将它的析构函数加入到CG中。
- 如果只考虑类型被修改就重分析使用该类型的函数，那么其实不需要管析构函数是否修改，因为它的调用函数已经被标记为需要重分析。

# 2024/10/24
## 待完成功能
- 分析类型依赖关系，传播类型变化
- 识别虚函数，函数指针调用

## 解决方案
- **Record粒度**：遍历到`RecordDecl`时，如果发生下列情况，就记录为变化Record：
  - 如果`RecordDecl`的声明范围内发生了变化
  - 如果`RecordDecl`的父`RecordDecl`为变化`Record`
  - **传播策略**：
    - 如果函数/方法使用了变化`RecordDecl`，就将函数/方法记录为变化
    - 由于`RecordDecl`一定是作为类型声明使用的，所以只需要考虑`VarDecl`, `FieldDecl`即可，不需要考虑`DeclRef`
- **Field粒度**：遍历到`FieldDecl`时，如果发生下列情况，就记录为变化FieldDecl：
  - 如果`FieldDecl`的声明范围内发生了变化
  - 如果`FieldDecl`的类型发生了变化
  - **传播策略**：
    - 如果函数/方法使用了变化`FieldDecl`，就将函数/方法记录为变化
    - 父`RecordDecl`的`CXXCtorInitializer`也需要考虑进来
    - `FieldDecl`使用时都对应有`MemberExpr`，因此需要考虑所有`MemberExpr`
- **Forward Decl**
  - 从**Record粒度**来看，如果`forward`的定义发生了变化，`C`中的`forward decl`字段`ptr`其实可以不认为发生了变化，因为如果要使用`ptr`指向对象的成员变量，必然要使用`forward`类型，此时`C`类型在这里只起到一个中间作用，用于保存该类型的指针。
  - 从**Field粒度**来看，也不用将`ptr`记录为变化`Field`，因为`ptr`本身的类型`forward *`是一个指针类型，并没有发生变化。
  - note:参考[link](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2020/p0593r6.html#idiomatic-c-code-as-c)，访问对象指针的成员时，需要保证对象被合规创建，否则是未定义行为。
```cpp
class forward;

class C {
  forward *ptr;
}

class forward {
  // forward definition may change
  int x;
}

int main () {
  C c;
  c.ptr = (forward *)malloc(10);
  (c.ptr)->x = 1;
  return 0;
}
```

# 2024/10/25
## 待完成功能
- 根据EFM拓展CG

# 2024/10/28
## 问题
- 当函数名称中包含行号信息时，可能导致使用FS进行优化时，未发生改变的函数的函数名发生变化，被认为是新的函数，从而无法使用到上次的FS进行优化。不过，此类问题的出现不会太多。

# 2024/10/29
## 问题
- 某些情况下，使用`compile_commands.json`对应指令预处理后的文件并不等价于CSA分析到的文件，例如宏`__clang_analyzer__`在CSA分析代码时会自动开启，但是预处理时并不会。(见`clang_tool/test/function_name.cpp case 4`)

## 解决方法
- 修改预处理使用的compile database的指令。