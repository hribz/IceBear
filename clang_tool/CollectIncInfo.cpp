#include <clang/AST/ASTContext.h>
#include <clang/AST/ComputeDependence.h>
#include <clang/AST/Decl.h>
#include <clang/AST/DeclBase.h>
#include <clang/AST/DeclCXX.h>
#include <clang/AST/DeclTemplate.h>
#include <clang/AST/Expr.h>
#include <clang/AST/ExprCXX.h>
#include <clang/AST/Stmt.h>
#include <clang/Basic/LLVM.h>
#include <iostream>
#include <fstream>
#include <iterator>
#include <llvm/ADT/StringRef.h>
#include <llvm/Support/Error.h>
#include <llvm/Support/JSON.h>
#include <llvm/Support/raw_ostream.h>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Index/USRGeneration.h"
#include "clang/Analysis/AnalysisDeclContext.h"
#include "clang/Analysis/CallGraph.h"
#include "llvm/ADT/PostOrderIterator.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;
using namespace clang::tooling;
using SetOfConstDecls = llvm::DenseSet<const Decl *>;

static bool isChangedLine(const std::optional<std::vector<std::pair<int, int>>>& DiffLines, unsigned int line, unsigned int end_line) {
    if (!DiffLines) {
        return true;
    }
    if (DiffLines->empty()) {
        return false;
    }
    // 使用 lambda 表达式来定义比较函数
    auto it = std::lower_bound(DiffLines->begin(), DiffLines->end(), std::make_pair(line + 1, 0),
                            [](const std::pair<int, int> &a, const std::pair<int, int> &b) {
                                return a.first < b.first;
                            });
    auto it_begin_and_end = [] (__gnu_cxx::__normal_iterator<const std::pair<int, int> *, std::vector<std::pair<int, int>>> it) {
        auto it_begin = it->first;
        auto it_end = it->first + it->second - 1;
        // it->second 是变化的行数，但是 it->second == 0 并不意味着没有发生变化，而是 it->first 行之后发生了删除
        // 这种情况可以视为 [it->first+1, 1]
        if (!it->second) {
            it_begin = it_end = it->first + 1;
        }
        return std::make_pair(it_begin, it_end);
    };
    // 检查前一个范围（如果存在）是否覆盖了给定的行号
    if (it != DiffLines->begin()) {
        --it;  // 找到最后一个不大于 line 的区间
        auto [it_begin, it_end] = it_begin_and_end(it);
        if (line <= it_end) {
            return true;  // 如果 line 在这个区间内，返回 true
        }
        ++it;
    }

    while (it != DiffLines->end()) {
        auto [it_begin, it_end] = it_begin_and_end(it);
        if (it_begin > end_line) {
            break;  // 当前区间的起始行号大于 EndLine，说明之后都不会有交集
        }
        // 检查是否存在交集
        if (it_begin<= end_line && it_end >= line) {
            return true;  // 存在交集
        }
        ++it;
    }

    return false;  // 如果没有找到，返回 false
}

static void DumpCallGraph(CallGraph &CG, llvm::StringRef MainFilePath, 
    std::unordered_map<const Decl *, std::pair<unsigned int, unsigned int>>& CGToRange, const bool printLoc) {
    if (!CG.size()) {
        return;
    }
    std::string CGFile = MainFilePath.str() + ".cg";
    std::ofstream outFile(CGFile);
    if (!outFile.is_open()) {
        llvm::errs() << "Error: Could not open file " << CGFile << " for writing.\n";
        return;
    }
    llvm::ReversePostOrderTraversal<clang::CallGraph*> RPOT(&CG);
    for (CallGraphNode *N : RPOT) {
        if (N == CG.getRoot()) continue;
        Decl *D = N->getDecl();
        outFile << AnalysisDeclContext::getFunctionName(D->getCanonicalDecl());
        if (printLoc) {
            outFile << " -> " << CGToRange[D].first << ", " << CGToRange[D].second;
        }
        outFile << "\n[\n";
        SetOfConstDecls CalleeSet;
        for (CallGraphNode::CallRecord &CR : N->callees()) {
            Decl *Callee = CR.Callee->getDecl();
            if (CalleeSet.contains(Callee))
                continue;
            CalleeSet.insert(Callee);
            // SmallString<128> usr;
            // std::string ret;
            // index::generateUSRForDecl(Callee, usr);
            // ret += std::to_string(usr.size());
            // ret += ":";
            // ret += usr.c_str();
            // outFile << ret << "\n]\n";
            outFile << AnalysisDeclContext::getFunctionName(Callee->getCanonicalDecl());
            if (printLoc) {
                outFile << " -> " << CGToRange[Callee].first << ", " << CGToRange[Callee].second;
            }
            outFile << "\n";
        }
        outFile << "]\n";
    }
}

static void DumpFunctionsNeedReanalyze(std::unordered_set<const Decl *> FunctionsNeedReanalyze,
        std::unordered_map<const Decl *, std::pair<unsigned int, unsigned int>>& CGToRange, llvm::StringRef MainFilePath) {
    if (FunctionsNeedReanalyze.empty()) {
        return;
    }
    std::string ReanalyzeFunctionsFile = MainFilePath.str() + ".cf";
    std::ofstream outFile(ReanalyzeFunctionsFile);
    if (!outFile.is_open()) {
        llvm::errs() << "Error: Could not open file " << ReanalyzeFunctionsFile << " for writing.\n";
        return;
    }
    llvm::outs() << "--- Functions Need to Reanalyze ---\n";
    for (auto &D : FunctionsNeedReanalyze) {
        // SmallString<128> usr;
        // std::string ret;
        // index::generateUSRForDecl(D, usr);
        // ret += std::to_string(usr.size());
        // ret += ":";
        // ret += usr.c_str();
        // outFile << ret << " ";
        const std::string &fname = AnalysisDeclContext::getFunctionName(D->getCanonicalDecl());
        outFile << fname << "\n";
        llvm::outs() << "  ";
        llvm::outs() << fname;
        llvm::outs() << ": " << "<" << D->getDeclKindName() << "> ";
        llvm::outs() << CGToRange[D].first << "-" << CGToRange[D].second;
        llvm::outs() << "\n";
    }
    
}

static std::optional<std::pair<int, int>> StartAndEndLineOfDecl(SourceManager &SM, const Decl * D) {
    if (auto FD = D->getAsFunction()) {
        // Just care about changes in function definition
        if (auto Definition = FD->getDefinition())
            D = FD->getDefinition();
    }
    
    SourceLocation Loc = D->getLocation();
    if (!(Loc.isValid() && Loc.isFileID())) {
        return std::nullopt;
    }
    auto StartLoc = SM.getExpansionLineNumber(D->getBeginLoc());
    auto EndLoc = SM.getExpansionLineNumber(D->getEndLoc());
    return std::make_pair(StartLoc, EndLoc);
}

const static void printJsonObject(const llvm::json::Object &obj) {
    for (const auto &pair : obj) {
        llvm::errs() << pair.first << ": ";
        if (auto str = pair.second.getAsString()) {
            llvm::errs() << *str << "\n";
        } else if (auto num = pair.second.getAsInteger()) {
            llvm::errs() << *num << "\n";
        } else if (auto boolean = pair.second.getAsBoolean()) {
            llvm::errs() << (*boolean ? "true" : "false") << "\n";
        } else if (auto *arr = pair.second.getAsArray()) {
            llvm::errs() << "[";
            for (const auto &elem : *arr) {
                if (auto str = elem.getAsString()) {
                    llvm::errs() << *str << " ";
                } else if (auto i = elem.getAsInteger()) {
                    llvm::errs() << *i << " ";
                }
            }
            llvm::errs() << "]" << "\n";
        } else {
            llvm::errs() << "Unknown type" << "\n";
        }
    }
}

const static void printJsonValue(const llvm::json::Value &jsonValue) {
    if (auto *obj = jsonValue.getAsObject()) {
        printJsonObject(*obj);
    } else {
        std::cerr << "Failed to get JSON object" << "\n";
    }
}

class DeclRefFinder : public RecursiveASTVisitor<DeclRefFinder> {
public:
    bool VisitDeclRefExpr(DeclRefExpr *DRE) {
        FoundedDecls.push_back(DRE->getFoundDecl());
        return true;
    }

    bool VisitMemberExpr(MemberExpr *E) {
        auto member = E->getMemberDecl();
        FoundedDecls.push_back(member);
        return true;
    }

    bool VisitCXXConstructExpr(CXXConstructExpr *E) {
        // Global constant will not propogate through CXXConstructExpr
        return false;
    }

    std::vector<const Decl *> getFoundedRefDecls() const { return FoundedDecls; }

    void clearRefDecls() {
        FoundedDecls.clear();
    }

private:
    std::vector<const Decl *> FoundedDecls;
};

class IncInfoCollectASTVisitor : public RecursiveASTVisitor<IncInfoCollectASTVisitor> {
public:
    explicit IncInfoCollectASTVisitor(
        ASTContext *Context, 
        const std::optional<std::vector<std::pair<int, int>>>& DiffLines, 
        CallGraph &CG, std::unordered_set<const Decl *> &FuncsNeedRA)
        : Context(Context), DiffLines(DiffLines), CG(CG), FunctionsNeedReanalyze(FuncsNeedRA) {}
    
    bool isGlobalConstant(const Decl *D) {
        D = D->getCanonicalDecl();
        if (!D->getDeclContext()) {
            // Top level Decl Context
            return false;
        }
        if (D->getDeclContext()->isFunctionOrMethod()) {
            return false;
        }
        if (auto VD = dyn_cast_or_null<VarDecl>(D)) {
            if (VD->getType().isConstQualified()) {
                return true;
            }
            return false;
        }
        if (auto EC = dyn_cast_or_null<EnumConstantDecl>(D)) {
            return true;
        }
        if (auto FD = dyn_cast_or_null<FieldDecl>(D)) {
            if (FD->getType().isConstQualified()) {
                return true;
            }
            return false;
        }
        return false;
    }

    bool VisitDecl(Decl *D) {
        // record all changed global constants def
        if (isGlobalConstant(D)) {
            auto loc = StartAndEndLineOfDecl(Context->getSourceManager(), D);
            if (loc && isChangedLine(DiffLines, loc->first, loc->second)) {
                // Should we just record canonical decl?
                GlobalConstantSet.insert(D);
                TaintDecls.insert(D);
            } else {
                // this global constant is not changed, but maybe propogate by changed global constant
                DRFinder.TraverseDecl(D);
                for (auto RefD: DRFinder.getFoundedRefDecls()) {
                    if (GlobalConstantSet.count(RefD)) {
                        GlobalConstantSet.insert(D);
                        TaintDecls.insert(D);
                        break;
                    }
                }
                DRFinder.clearRefDecls();
                // no need to traverse this decl node and its children
                // note: It seems that `return false` will stop the visitor.
                // return false;
            }
        }
        
        if (isa<RecordDecl>(D)) {
            // RecordDecl *RD = dyn_cast<RecordDecl>(D);
            // auto loc = StartAndEndLineOfDecl(Context->getSourceManager(), RD);
        } else if (isa<FieldDecl>(D)) {
            FieldDecl *FD = dyn_cast<FieldDecl>(D);
            auto loc = StartAndEndLineOfDecl(Context->getSourceManager(), FD);
            // record changed field
            if ((loc && isChangedLine(DiffLines, loc->first, loc->second))) {
                TaintDecls.insert(FD);
            }
            // TODO: if this field is used in `CXXCtorInitializer`, the correspond `CXXCtor` should be reanalyze
            
        } else {
            if (CG.getNode(D)) {
                inFunctionOrMethodStack.push_back(D);
            }
        }
        return true;
    }

    bool TraverseDecl(Decl *D) {
        if (FunctionsNeedReanalyze.count(D)) {
            // If this `Decl` has been confirmed need to be reanalyzed, we don't need to traverse it.
            return false;
        }
        bool Result = clang::RecursiveASTVisitor<IncInfoCollectASTVisitor>::TraverseDecl(D);
        if (!inFunctionOrMethodStack.empty() && inFunctionOrMethodStack.back() == D) {
            inFunctionOrMethodStack.pop_back(); // exit function/method
        }
        return Result;
    }

    // process all global constants use
    bool ProcessDeclRefExpr(Expr * const E, NamedDecl * const ND) {
        if (GlobalConstantSet.count(ND)) {
            
        }
        return true;
    }

    bool VisitDeclRefExpr(DeclRefExpr *DR) {
        auto ND = DR->getFoundDecl();
        if (!inFunctionOrMethodStack.empty() && TaintDecls.count(ND)) {
            // use changed decl, reanalyze this function
            FunctionsNeedReanalyze.insert(inFunctionOrMethodStack.back());
        }
        return ProcessDeclRefExpr(DR, ND);
    }

    bool VisitMemberExpr(MemberExpr *ME) {
        auto member = ME->getMemberDecl();
        // member could be VarDecl, EnumConstantDecl, CXXMethodDecl, FieldDecl, etc.
        if (isa<VarDecl, EnumConstantDecl>(member)) {
            ProcessDeclRefExpr(ME, member);
        } else {
            if (isa<CXXMethodDecl>(member)) {
            }
        }
        return true;
    }

    void DumpGlobalConstantSet() {
        if (GlobalConstantSet.empty()) {
            return;
        }
        llvm::outs() << "--- Decls in GlobalConstantSet ---\n";
        for (auto &D : GlobalConstantSet) {
            llvm::outs() << "  ";
            if (const NamedDecl *ND = llvm::dyn_cast_or_null<NamedDecl>(D)) {
                llvm::outs() << ND->getQualifiedNameAsString();
            } else {
                llvm::outs() << "Unnamed declaration";
            }
            llvm::outs() << ": " << "<" << D->getDeclKindName() << "> ";
            llvm::outs() << "\n";
        }
    }
    ASTContext *Context;
    std::unordered_set<const Decl *> GlobalConstantSet;
    std::unordered_set<const Decl *> TaintDecls; // Decls have changed, the function/method use these should reanalyze
    std::unordered_set<const Decl *> &FunctionsNeedReanalyze;
    const std::optional<std::vector<std::pair<int, int>>>& DiffLines;
    CallGraph &CG;
    DeclRefFinder DRFinder;
    std::vector<const Decl *> inFunctionOrMethodStack;
private:
    // 提供一个静态的 std::optional 对象，表示 std::nullopt 的引用
    static const std::optional<std::vector<std::pair<int, int>>>& getNullOptReference() {
        static const std::optional<std::vector<std::pair<int, int>>> nulloptRef = std::nullopt;
        return nulloptRef;
    }
};

class IncInfoCollectConsumer : public clang::ASTConsumer {
public:
    explicit IncInfoCollectConsumer(ASTContext *Context, const std::string &outputPath, const std::optional<llvm::json::Object> GlobalDiffLines, const bool printLoc)
    : CG(), OutputPath(outputPath), DiffLines(std::vector<std::pair<int, int>>()), 
      IncVisitor(Context, DiffLines, CG, FunctionsNeedReanalyze), PrintLoc(printLoc) {
        const SourceManager &SM = Context->getSourceManager();
        FileID MainFileID = SM.getMainFileID();
        const FileEntry *FE = SM.getFileEntryForID(MainFileID);
        MainFilePath = FE->tryGetRealPathName();
        // Don't print location information.
        // auto PrintPolicy = Context->getPrintingPolicy();
        // PrintPolicy.FullyQualifiedName = true;
        // PrintPolicy.TerseOutput = true;
        // PrintPolicy.PrintInjectedClassNameWithArguments = true;
        // Context->setPrintingPolicy(PrintPolicy);
        if (GlobalDiffLines) {
            // printJsonObject(*GlobalDiffLines);
            if (auto diff_array = GlobalDiffLines->getArray(MainFilePath)) {
                for (auto line: *diff_array) {
                    auto line_arr = line.getAsArray();
                    auto line_start = (*line_arr)[0].getAsInteger();
                    auto line_count = (*line_arr)[1].getAsInteger();
                    if (line_start && line_count) {
                        auto pair = std::make_pair<int, int>(*line_start, *line_count);
                        DiffLines->push_back(pair);
                    }
                }
            } else if (auto new_file = GlobalDiffLines->getInteger(MainFilePath)) {
                DiffLines = std::nullopt;
                llvm::outs() << MainFilePath << " is new file.\n";
            } else {
                llvm::errs() << MainFilePath << " has no diff lines information.\n";
            }
        }
    }

    bool HandleTopLevelDecl(DeclGroupRef DG) override {
        storeTopLevelDecls(DG);
        return true;
    }

    void HandleTopLevelDeclInObjCContainer(DeclGroupRef DG) override {
        storeTopLevelDecls(DG);
    }

    void storeTopLevelDecls(DeclGroupRef DG) {
        for (auto &I : DG) {
            // Skip ObjCMethodDecl, wait for the objc container to avoid
            // analyzing twice.
            if (isa<ObjCMethodDecl>(I))
                continue;
            LocalTUDecls.push_back(I);
        }
    }

    void HandleTranslationUnit(clang::ASTContext &Context) override {
        CG.addToCallGraph(Context.getTranslationUnitDecl());
        llvm::ReversePostOrderTraversal<clang::CallGraph*> RPOT(&CG);
        SourceManager &SM = Context.getSourceManager();
        for (CallGraphNode *N : RPOT) {
            if (N == CG.getRoot()) continue;
            Decl *D = N->getDecl();
            auto loc = StartAndEndLineOfDecl(SM, D);
            if (!loc) continue;
            auto StartLoc = loc->first;
            auto EndLoc = loc->second;
            CGToRange[D] = std::make_pair(StartLoc, EndLoc);
            if (isChangedLine(DiffLines, StartLoc, EndLoc)) {
                FunctionsNeedReanalyze.insert(D);
            }
        }
        DumpCallGraph(CG, MainFilePath, CGToRange, PrintLoc);
        IncVisitor.TraverseDecl(Context.getTranslationUnitDecl());
        IncVisitor.DumpGlobalConstantSet();
        DumpFunctionsNeedReanalyze(FunctionsNeedReanalyze, CGToRange, MainFilePath);
    }

private:
    CallGraph CG;
    IncInfoCollectASTVisitor IncVisitor;
    std::unordered_map<const Decl *, std::pair<unsigned int, unsigned int>> CGToRange;
    std::string OutputPath;
    std::deque<Decl *> LocalTUDecls;
    std::optional<std::vector<std::pair<int, int>>> DiffLines; // empty means no change, nullopt means new file
    std::unordered_set<const Decl *> FunctionsNeedReanalyze;
    llvm::StringRef MainFilePath;
    const bool PrintLoc;
};

class IncInfoCollectAction : public clang::ASTFrontendAction {
public:
    IncInfoCollectAction(const std::string &outputPath, const std::string &diffPath, const bool printLoc) :
    OutputPath(outputPath), DiffLines(std::nullopt), PrintLoc(printLoc) {
        initDiffLines(diffPath);
    }

    void initDiffLines(const std::string &diffPath) {
        if (diffPath.empty()) {
            llvm::errs() << "No diff lines information.\n";
            return ;
        }
        std::ifstream file(diffPath);
         if (!file.is_open()) {
            llvm::errs() << "Failed to open " << diffPath << ".\n";
            return ;
        }
        std::string jsonStr((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        file.close();
        llvm::Expected<llvm::json::Value> jsonValue = llvm::json::parse(jsonStr);
        if (!jsonValue) {
            llvm::errs() << "Failed to parse JSON.\n";
            return ;
        }

        DiffLines = *(jsonValue->getAsObject());
        // printJsonObject(*DiffLines);
    }

    std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(clang::CompilerInstance &CI, llvm::StringRef file) override {
        return std::make_unique<IncInfoCollectConsumer>(&CI.getASTContext(), OutputPath, DiffLines, PrintLoc);
    }

private:
    std::string OutputPath;
    // Don't use pointer, because jsonStr is declared at function `initDiffLines`, 
    // and it will be freed automatically while exiting the function.
    std::optional<llvm::json::Object> DiffLines;
    const bool PrintLoc;
};

class IncInfoCollectActionFactory : public FrontendActionFactory {
public:
    IncInfoCollectActionFactory(const std::string &outputPath, const std::string &diffPath, const bool printLoc):
     OutputPath(outputPath), DiffPath(diffPath), PrintLoc(printLoc) {}

    std::unique_ptr<FrontendAction> create() override {
        return std::make_unique<IncInfoCollectAction>(OutputPath, DiffPath, PrintLoc);
    }

private:
    const std::string OutputPath;
    const std::string DiffPath;
    const bool PrintLoc;
};

static llvm::cl::OptionCategory ToolCategory("Collect Inc Info Options");
static llvm::cl::opt<std::string> OutputPath("o", llvm::cl::desc("Specify output path for dot file"), 
    llvm::cl::value_desc("call graph dir"), llvm::cl::init(""));
static llvm::cl::opt<std::string> DiffPath("diff", llvm::cl::desc("Specify diff info files"),
    llvm::cl::value_desc("diff info files"), llvm::cl::init(""));
static llvm::cl::opt<bool> PrintAnonLoc("loc", llvm::cl::desc("Print location information in FunctionName or not"),
    llvm::cl::value_desc("AnonymousTagLocations"), llvm::cl::init(false));

int main(int argc, const char **argv) {
    auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCategory);
    if (!ExpectedParser) {
        // Fail gracefully for unsupported options.
        llvm::errs() << ExpectedParser.takeError();
        return 1;
    }
    CommonOptionsParser& OptionsParser = ExpectedParser.get();

    ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());
    IncInfoCollectActionFactory Factory(OutputPath, DiffPath, PrintAnonLoc);
    return Tool.run(&Factory);
}