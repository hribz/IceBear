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
- 根据EFM拓展CG，从而保证CTU的增量分析的正确性。

# 2024/10/28
## 问题
- 当函数名称中包含行号信息时，可能导致使用FS进行优化时，未发生改变的函数的函数名发生变化，被认为是新的函数，从而无法使用到上次的FS进行优化。不过，此类问题的出现不会太多。

# 2024/10/29
## 问题
- 某些情况下，使用`compile_commands.json`对应指令预处理后的文件并不等价于CSA分析到的文件，例如宏`__clang_analyzer__`在CSA分析代码时会自动开启，但是预处理时并不会。(见`clang_tool/test/function_name.cpp case 4`以及`clang_tool/test/namespace.cpp`)

## 解决方法
- 修改预处理使用的compile database的指令。

# 2024/10/31
## 待完成功能
- 直接在baseline上进行更新的增量分析（需要考虑文件更新后，对应的.ast, .efm, .cg, .rf, .cf, .fs的更新）

## 问题
- 设计实验：
  - 选择一些开源项目的commit，待选项有：之前用CSA得到的真实BUG的修复commit；ISSTA 2024一篇静态分析工具综述的benchmark。
  - 选择项目的某个旧版作为baseline，对每个commit进行增量分析。
  - 设计消融实验，评估文件级、函数级、带inline信息的函数级增量分析分别需要多少分析时间。
  - 验证工具正确性，测试工具是否存在遗漏分析的情况。

# 2024/11/1
## 问题
- panda在处理路径中名称带有`_`的目录时，似乎会忽略掉该目录。(其实不是panda的问题，是因为没有清理上一次的构建目录)
- 增量配置和全量配置生成的`compile_commands.json`可能不同。
- 当某个commit对第三方库进行升级后，可能导致整个项目的大量文件预处理后发生变化，因此有必要在文件变化过大时当作一个新文件。

## 解决方案
- preprocess和diff文件夹必须清理，否则diff信息将被之前的结果污染。
- 对于新文件：不需要关心它的CG是什么，只需要关心它的extern function被哪些具有CG的文件调用。

## 会议纪要
- 根据初步实验结果，为`file, func, inline`三种策略设计启发式方法，对不同文件实施不同的分析策略。
- 关于CTU：
  - 建立跨过程文件调用图；
  - 或许可以放宽标准，不在全局的调用图上进行函数级别的增量；
  - 或者记录每个函数节点的深度，不去传播过深的节点。
- 后续将方案拓展到多配置、多架构分析，从这个角度讲故事，可以不那么看重分析的完整性，从而降低增量准备工作的开销。
- 做一下数据统计：不同类型的修改对应了多少函数需要重分析
- 目前的性能瓶颈在于：
  - diff的解析没有并行地去做，文件多的时候开销较大（需要重新实现diff的调度策略，而不是直接diff两个文件夹）
  - 检查一下为什么`func, inline`策略会导致执行CSA增加这么多开销，验证是否是因为每次分析函数时查表导致。
  - Reanalyze属性在CallGraph上的传播也可以并行地对每个文件做，但目前存在不同进程数据不一致的问题，而这种CPU密集型工作多线程或许并没有效果。

# 2024/11/06
## 待完成功能
- CTU增量分析的适配

# 2024/11/08
## 问题
- 是否需要考虑代码行的来源位置，因为CSA是考虑了函数是来自系统库，头文件，还是主文件的，然后选择不同的分析模式。

# 2024/11/11
## 发现
- 关于CTU的适配，`CodeChecker`以及`Sonar`的IncrementalCSA功能都是基于增量编译来确认发生变化的文件，例如`CodeChecker`利用`intercept-build`生成只记录增量编译的`compile_commands.json`，随后对其中记录的文件进行分析，以达到增量分析效果。`Sonar`同样只对增量编译的文件进行分析，这就导致在增量CTU分析时会出现一个问题，当一个报告的入口文件没有修改，仅修改了其它编译单元的文件时，增量编译可能不会记录入口文件（即使入口文件存在链接依赖），导致存在漏分析。
- 虽然基于增量编译确定重分析文件可能存在问题，但是确定需要重预处理的文件还是没问题的。

# 2024/11/12
## 发现
- 对于`2024/11/08`的问题，CSA只是在进行跨过程分析选择函数入口时考虑函数入口的来源，来自系统库的文件还是可能被跨过程分析到，因此并不能过滤掉这些函数的变化。

## 问题
- 增量分析的inline策略是否过于理想化了？目前的想法是，一个change函数不论是否在上次分析被inline，它的父函数都需要被标记为reanalyze。而父函数继续向上分析传播reanalyze属性时，可以借助上次分析的inline记录来判断本次是否需要inline，如果不需要，则可以截断这条路径上的传播。
- CSA的inline策略实际上还会考虑函数的被inline次数，如果某个函数较大并且超过了inline次数上限，就不再将其inline。假如A->F, B->F, C->F，F的inline上限是2，那么C->F不被inline，根据当前的策略，F被标记为reanalyze后，F向C的传播路径会被截断。但假如A->F被删除，此时C->F就可能会被inline了。

## 解决方案
- 上述策略过滤了那些被inline过但是后续被标记为不再inline的函数，这里可以严格一下要求，只有那些被标记为不再inline且没有被inline过的函数才截断其传播。
- 也可以记录上一次分析的所有作为entry的函数，然后向上传播到entry。

# 2024/11/21
## 问题
- 想要实现`update_mode`的增量分析，从而复用`incremental build`的文件级增量结果，是否需要考虑被删除的文件？
- `compile_commands.json`由CMake在`configure`过程生成，或是由`bear`在`build`过程记录。在发生文件的新增、删除时，似乎不能跳过重新`configure`的步骤，单纯进行`build`并不能感知到新增的文件。并且对于删除的文件，目前的增量编译是不会将它们的编译结果删除的，或许我们暂时也不用管删除文件。

# 2024/11/23
## 一些记录
- 使用`panda -j24 no-ctu`的情况下，`grpc FFmpeg`分析时间为:
  -           grpc        FFmpeg
  - real    8m36.011s    6m15.823s
  - user    78m22.146s   97m36.400s
  - sys     2m17.074s    2m36.201s
- `diff`时间：
  -      grpc(1316/1724)   FFmpeg(11/2048)
  - j24     34.367 s           21.047 s
  - -r      244.457 s          0.380 s
## 优化diff
- 目前的方案是使用多线程为每个文件执行一次`diff`，但是从上面的数据可以看到，`FFmpeg`的效果并不好，因为文件数目多的情况下，为每个文件开一个进程执行diff的开销也很高，并且对diff结果的处理是在多线程下进行的，这部分主要是CPU密集型任务，多线程效果并不好。
- 尝试直接将每个文件的diff结果写入到对应文件中，而不是将其解析并保存下来，因为IceBear并不需要这部分信息，`collectIncInfo`时才需要。修改之后的效果：
  -      grpc(1316/1724)   FFmpeg(11/2048)
  - j24     21.680 s           7.351 s
  - -r      244.457 s          0.380 s

# 2024/11/26
## 问题
- 某些未被使用的重载操作符，某些模板函数的原函数不会出现在`CallGraph`中，当它们发生了修改的情况下，会出现`CallGraph`无法找到changed function的情况。
- 某些虚函数，函数指针，隐式调用的析构函数的调用边不会出现在`CallGraph`上，对这些调用边需要特殊处理。
## 解决方案
- 只分析出现在`CallGraph`上的函数，并对某些`CallExpr`做保守处理。
- 调用边缺失情况应当在`CollectIncInfo`时进行处理，因为生成的`CallGraph`可能并不完整，需要找到那些被忽略的`CallExpr`，包括生命周期上的隐式析构，虚函数，函数指针等不确定的情况，CSA是具备处理这三种情况的能力的，所以必须处理这几种情况：
  - 对于虚函数和函数指针：一种最保守的做法是将出现了这类`CallExpr`的函数都标记为changed。
  - 对于隐式析构函数调用，他们仅出现在CFG上，需要考虑是否值得为此生成CFG，或者仅仅去记录使用了对应class的函数，认为它们都可能调用析构函数，不过这样的开销过大。
- 如果像上面这样处理，那么在`CollectIncInfo`就只需考虑`CallGraph`中的`Decl`，因为`CG`之外的`Decl`即使被标记为`changed`，也无法通过在`CG`上传播找到需要重分析的父节点。并且上方的保守策略可以保证不会漏掉需要重分析的函数。
## 发现
- `FFmpeg`项目出现了不`configure & build`的情况下，`preprocess`得到的文件不同的情况，例如`version.c.i`中`avutil_configuration`返回的字符串记录了`configure`时的配置项，该配置项保存在宏`FFMPEG_CONFIGURATION`内，并且该项目不能做到完全`out of tree`的构建，所以后续每次`preprocess`时，读取的都是最后一次`configure`生成的`config.h`中的宏。因此第一次构建每个commit版本的项目时，出现了一些diff file，这些diff file都是因为`configure`的差异引起的，并不是commit本身修改的代码，后续跳过`configure & build`的情况下，显示这几个版本的预处理后文件没有差别。
- 这就引申出一个新的问题，为什么checkout不同的commit之后，预处理后的文件没有区别？以`FFmpeg aad40fed3376f52006eb519833650a80ab115198`为例，修改了`libavutil/vulkan.c`文件，但是该文件并没有在`compile_commands.json`中出现，换言之当前配置下没有被编译，这也是为什么需要在多配置下进行代码检测。
- 此外，推测`ISSTA 2024`的那篇综述之所以CSA检测的BUG数目较少，原因可能为：
  - CSA没有开启CTU
  - CSA默认配置下没有编译到bug文件，而flawfinder不依赖于编译就能进行检测，codeql确实也需要先编译再检测

# 2024/11/27
## 解决方案
- 尝试实现`update_mode`的`Configuration`，有如下步骤要实现：
  - 首先，维护一个增量变化的`Configuration`
  - 对于每次更新，可选择`configure & build` 或者仅执行 `build`
  - 读取`compile_commmands.json`，更新`file_list`，并维护一个`global_file_dict`，其中记录了每个文件名对应的最新版本的`FileInCDB`
  - 根据`file_list`执行`preprocess & diff`任务
  - 根据`diff_file_list`执行后续准备工作以及执行分析任务

# 2024/12/02
## 问题
- 在CTU分析时，出现了`error: PCH file uses an older PCH format that is no longer supported`。经过分析发现，原因是`CSA`分析使用的clang版本和生成ast的clang版本不同，需要在`environment`初始化`PANDA_COMMAND`时调整clang版本。
- 将`configuration.analyzers=[CSA(CSAConfig(...))]`放在`update_workspace_path()`函数当中，发现CSAConfig的`parse_config_file()`似乎被重复执行，导致CSA指令中存在重复的编译参数。（2024/12/19发现问题出在`self.json_config = default_csa_config`时进行的是浅拷贝，导致后续`self.json_config.append(...)往default_csa_config`里加东西了）
- 进行CTU分析时输出`warning`：AST file shape change.

# 2024/12/03
## 问题
- `compile_commands.json`中，同一个文件可能对应有多个`compile command`，因此使用`global_file_dict`时，使用`file name`作为索引可能不太准确，因为多个`compile command`会重复更新同一个`global_file_dict`。(昨天的AST shape问题也是因此)
- `panda`在生成预处理文件时并不会考虑重复文件名的情况，只会用后出现的文件覆盖之前的文件。

## 解决方案
- 预处理`compile_commands.json`，每个文件保留一个`compile command`，但是该方法实际上改变了编译过程
- 不只用文件名作为索引，而是`file + output`作为索引，但是`panda`生成预处理文件没有考虑这种情况。因此还是采用第1种方案。

## collectIncInfo时间开销分析
- 经过测试，22w行的预处理后文件`/repos/grpc/grpc/src/core/resolver/xds/xds_resolver.cc.ii`:
  - 使用`collectIncInfo`进行处理时，只输出`CallGraph`需要`9.880s`,`CallGraph`的规模为10w行；
  - 将所有行标记为change，输出cf文件需要`10.034s`(包括生成CG)，因此主要的时间开销在于**生成CG**，CF文件的规模为3.6w行。
- 思考：实际上CSA分析过程种也需要生成CG，也就是说，整个执行流程生成了两次CG，并且生成CG的开销不小。能否将这两次生成CG的过程合并？

## CSA时间开销分析
- `grpc_inline_20241203_111640_specific`的`grpc 2024-10-30_265c7b`增量花费的时间异常地长，其中7个diff文件，6个无`changed functions`，最终仅确认8个函数需要重新分析。但是最终的分析时长却比`grpc_file_20241202_231314_specific`的分析时间还长，分别为`inline 51.117 s, file 38.710 s`。
- 原因很可能是那次测试出现了问题1，目前修复了问题1，待检测结果是否正常。
  - file时间比inline少确实是问题1的影响，但还不能确定与更改的`clang`是否也有关系（即使不指定rf的情况下，更改的`clang`可能仍会多花一些判断的时间，以及输出fs的时间）（后续测试发现，输出fs的时间非常短，基本可以忽略不计，rf的判断时间也应该非常短，因此更改的`clang`在没有大量rf的情况下，只会带来轻微的时间开销）
  - 修复后的时间为`inline 51.981 s, file 51.382 s`，已无明显区别，但是inline的时间理应远少于file，因为cf为0。原因在于当changed functions数量为0时，直接跳过了后续解析cg, fs, 生成rf的过程。而在analyzer分析被设置为：rf不存在的情况下需要做全文件的分析。最终表现的效果是inline的时间与file相同，处理方式为当不存在changed functions时，生成一个空的rf文件
- 将`collectIncInfo时间开销分析`部分得到的`3.6w`行的cf文件直接复制为对应的rf文件，用更改后的`clang`进行分析：
  - `无rf，不输出fs`：Analyzer Time: 36.7218s, real time: 48.975s
  - `无rf，但输出fs`：Analyzer Time: 36.5081s, real time: 48.702s
  - `有rf，不输出fs`：Analyzer Time: 35.6839s, real time: 47.864s
  - `有rf，并输出fs`：Analyzer Time: 37.3759s, real time: 50.030s
  - 上面4种情况并无明显区别，可见`3.6w`行量级的rf带来的函数名判断开销其实很小。
- 关闭CTU分析，并关闭更改的clang的rf和fs功能，尝试对比更改的`clang`和`clang-19`用时是否有差别：
  - `更改的 clang`:  Analyzer Time: 36.8609s, real time: 47.459s
  - `clang-19`：     Analyzer Time: 27.4325s, real time: 35.070s
  - 时间差异过于明显，难道真的是因为`getModeForDecl`多加了一行判断？
  - `把判断注释掉`：  Analyzer Time: 36.5321s, real time: 47.146s
  - 注释与否的差别并不大，推测与`clang-19`时间差异大的原因是，`clang-19`是通过包管理安装在`/usr/bin`的，打包时的配置针对平台进行了定制，该`clang`本身就是比自行编译的clang更快。因此后续对比实验不使用`clang-19`进行对比，而是都使用自行编译的`clang`。

# 2024/12/04
## 问题
- 昨天的测试看出，`collectIncInfo`最大的时间开销在于生成`CallGraph`，并且每次CSA分析需要重复一遍该过程。`grpc_inline_20241203_233452_specific`的`2024-10-23_d56c93`CSA的分析时间相对于`file`级别确实从`190s`降低到了`78s`，但是`inline`在`extract inc info`和`propagate reanalyze`分别花费了`76s`和`43s`，导致实际的时间开销并没有变少。
- 并且，从inline得到的`file status`看来，292个文件有2个rf，1个文件有476个rf，并且所有文件的`Analyze time`都非常短(几乎为0s)，但是CSA的总时间却达到了`78s`。这并不是记录错误，而是`Analyze time`没有算上生成`CallGraph`的时间。这也是为什么`CSA`和`extract inc info`的耗时如此相似，因为时间都耗费在了`CallGraph`建立上。

## 解决方案
- 既然CSA分析时本身就需要生成`CallGraph`，能否把`extract inc info`和`propagate reanalyze`的步骤直接集成到`CSA`，令其解析完`CallGraph`后先进行`extract inc info`和`propagate reanalyze`的步骤。

## 一种增量CTU分析的可能实现方法
- EFM文件记录了当前文件的所有可能被其它编译单元调用的函数（称之为public函数）USR名称，然后将整个项目的EFM文件合并得到一个总的EFM文件。
- 对于单个TU可以确定哪些public函数是rf，它会影响的是所有可能调用它的其它TU。想要精确地确认所有受影响的TU，需要建立一个全局的`CallGraph`，在其上进行rf的传播分析。想要做一个`complete`的增量，有如下问题：
  - 开销问题：需要知道所有文件可能调用的public函数，如果遇到无法确定的调用函数，是不是只能假设这可能将会调用其它TU的public函数，然后将其标记为reanalyze？
  - 可行问题：`CallGraph`本身就是不完整的

# 2024/12/09
## 问题
- `extract inc info`集成到`CSA`不太可行，因为`CSA`分析的是源码，而`diff info`记录的是预处理后的代码的变化行号。
- 分析源码时是无法获取预处理后的行号的，但又不可能分析预处理后的文件，这样会导致报告很难看。
- 因此，对于生成`CallGraph`这个问题，要么优化算法，要么让`CSA`读缓存。

# 2024/12/11
## 问题
- 其实时间长的原因不是生成`CallGraph`，而是`clang tool`解析源代码生成`AST`就是需要这么长时间。换言之，这属于启动时间，并不是优化`CallGraph`算法能够解决的。

# 2024/12/13
## CollectIncInfo慢的原因
- 其实是因为使用了`Debug`版本。。。。

# 2024/12/16
## 与CodeChecker的对比
- 首先需要说明为什么要`configure & build`，而不是直接执行`build`。需要用例子说明后者在某些情况下不能保证增量编译的准确性。
- 其次说明某些情况下`configure & build`可能会使得增量编译处理不必要的文件，因为增量编译基于时间戳以及编译依赖决定需要重新编译的文件，如果`configure`改变了某些文件的时间戳，就会导致很多实际没有变化的文件被重新编译(例如`FFmpeg 2024-11-17_bbb0fd`)。因此需要通过`preprocess & diff`进行初筛，忽略预处理后没有变化的文件。
- 而在某些情况下，修改了某些依赖关系中较为顶层的头文件，或是修改了三方库的版本后，确实会有大量的文件发送变化。但是实际发生变化的函数可能并不多(例如`FFmpeg 2024-11-13_322b24`)，这种情况下`func-level`的增量分析效果就很明显。

# 2024/12/18
## 除CSA外的analyzer
- 虽然它们只能做`file-level`的增量，但是可以用diff信息来对报告进行过滤，如`clang-tidy`的`--line-filter`可以指定需要报告的行号，`cppcheck`的`--suppress=[error id]:[filename]:[line]`可以指定需要过滤的报告种类和文件名，文件行号。因此，可以加上一个报告过滤模块，过滤掉无关的reports。
- CTU部分可以说考虑到CTU分析的开销很大，因此加入分析配置参数来辅助确定CTU增量分析可能跨多少层文件进行分析。

# 2024/12/19
## 细粒度的diff
- 目前对预处理后的文件进行diff，当头文件发生较大变化时，导致大量文件产生大量的变化，从而导致标记大量的`changed functions`。
- 将这些头文件作为入口函数，进行跨过程的路径敏感分析大多数情况下是没有必要的。CSA默认的策略是系统头文件的函数不作为入口，用户自定义头文件的函数只进行语法检查。但是`analyzer-opt-analyze-headers`可以强迫CSA考虑将所有函数作为入口进行跨过程的路径敏感分析，并且`CodeChecker`是默认打开这个配置选项的，导致分析时间大大增加，且可以想象存在大量重复分析的函数。
- 在传播`cf`得到`rf`的过程中，可以只考虑主文件的函数节点，以及这些节点连接的库函数。

# 2024/12/27
## diff初筛文件的作用
- 除了`configure`带来的“未知”影响外，增量编译确实存在`Redundant Dependencies`带来无必要的重复增量编译
- 并且，编译依赖并不会考虑文件中的预处理指令，如果修改了其它配置下的代码，对当前配置下的静态分析并不会造成影响，因此通过`diff`将这些不变的文件筛掉。

# 2024/12/29
## 静态分析工具的不同粒度的增量
- 不用`func-level`的说法，而是用`line 粒度`的说法，对于CSA从line映射到func，对于ClangTidy和CppCheck，通过line来抑制某些不必要的报告，而Infer本身就支持file/procedures级别的增量，我们直接将信息给它，对其进行调度即可。
- 对于ClangTidy，加上参数`--line-filter='[{"name":"file.cpp","lines":[[1,10]]}]'`表示只输出1~10行相关的报告。
- 对于CppCheck，加上参数`--suppress-list=<file>`表示抑制匹配file中`<spec>`的报告，`<spec>`的格式为`*:[filename]:[line]`

# 2025/1/3
## 函数指针和虚函数
- 虚函数：如果一个函数在`FunctionsChanged`中的同时，也是虚函数，那么把它的所有父函数记录在`ICChanged`，在遇到虚函数调用时，先在`ICChanged`进行查找，如果存在，才重新分析调用者
- 函数指针：假设一个函数要通过函数指针使用，那么它必然被用于赋值、传参等操作。如果函数既在`FunctionsChanged`中，又被用于赋值，就认为可能存在变化的函数被作为虚函数使用，此时才考虑函数指针。
- isChangedLine存在bug，输入20,22, diff:[[13,14]]返回true。(并不是bug，[13,14]指的是13后的14行)

# 2025/1/4
## ClangTidy一个筛报告的例子
假如修改了`clang_tool/test/class_field.cpp`第4行`int const b = 0;`，将导致第26行发生除0错误。如果只告诉clang-tidy报告第4行相关的错误，将会导致这个新报告丢失。需要将第4行修改的影响传播给其它行，再将所有行都告诉clang-tidy。
```bash
# 无报告
clang-tidy '--line-filter=[{"name":"class_field.cpp","lines":[[4,5]]}]' '-config={"HeaderFilterRegex": ".*"}' class_field.cpp --export-fixes .
```

# 一些报告
- redis/redis_commits/redis_2024-12-23_64a40b.diff：定义了某些宏名称，clang-tidy在这些宏名称中出现了报告。
- 由于报告过多，关闭了`clang-diagnostic-reserved-identifier`, `clang-diagnostic-reserved-macro-identifier`, `clang-diagnostic-unused-parameter`
- 考虑关闭`clang-diagnostic-missing-field-initializers`，`FFmpeg`此类报告过多
- 某些CSA报告仅在func中存在，因为制定了分析的函数，导致原本因时间或资源限制未被检测出的报告被检测出，这样的报告总共有
  - tesseract 
    - 2024-12-31_014b9d 
      - report-13f130.html
  - redis 
    - 2024-12-23_64a40b 
      - report-b12fd9.html 
      - report-4bc9f1.html
  - openssl: 1个cppcheck的新报告，原因未知
  - FFmpeg 
    - noinc 2024-12-23_eecdc2
      - report-e04015.html: 这个报告仅存在于noinc中，原因是CSA的波动
    - func
      - 两个cppcheck报告，其实是相同报告，因为改变了分析入口，导致报错信息，或者是ruleID发生了变化
  - 