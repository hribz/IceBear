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
#include <filesystem>
#include <iostream>
#include <fstream>
#include <llvm-17/llvm/Support/Error.h>
#include <llvm-17/llvm/Support/JSON.h>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <stack>
#include <utility>
#include <vector>

#include "clang/AST/AST.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/FrontendActions.h"
#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"
#include "clang/ASTMatchers/ASTMatchers.h"
#include "clang/ASTMatchers/ASTMatchFinder.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Index/USRGeneration.h"
#include "clang/Analysis/CallGraph.h"
#include "llvm/ADT/PostOrderIterator.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;
using namespace clang::tooling;
using namespace clang::ast_matchers;

bool isChangedLine(const std::optional<std::vector<std::pair<int, int>>>& DiffLines, unsigned int line, unsigned int end_line) {
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

    // 检查前一个范围（如果存在）是否覆盖了给定的行号
    if (it != DiffLines->begin()) {
        --it;  // 找到最后一个不大于 line 的区间
        if (line <= it->first + it->second - 1) {
            return true;  // 如果 line 在这个区间内，返回 true
        }
        ++it;
    }

    while (it != DiffLines->end()) {
        if (it->first > end_line) {
            break;  // 当前区间的起始行号大于 EndLine，说明之后都不会有交集
        }
        if (it->second == 0) {
            ++it;
            continue;
        }

        // 检查是否存在交集
        if (it->first <= end_line && it->first + it->second - 1 >= line) {
            return true;  // 存在交集
        }
        ++it;
    }

    return false;  // 如果没有找到，返回 false
}

void dumpFunctionsNeedReanalyze(std::unordered_set<const Decl *> FunctionsNeedReanalyze,
        std::unordered_map<const Decl *, std::pair<unsigned int, unsigned int>> CG_to_range) {
    llvm::outs() << "--- Functions Need to Reanalyze ---\n";
    for (auto &D : FunctionsNeedReanalyze) {
        llvm::outs() << "  ";
        if (const NamedDecl *ND = llvm::dyn_cast_or_null<NamedDecl>(D)) {
            llvm::outs() << ND->getQualifiedNameAsString();
        } else {
            llvm::outs() << "Unnamed declaration";
        }
        llvm::outs() << ": " << "<" << D->getDeclKindName() << "> ";
        llvm::outs() << CG_to_range[D].first << "-" << CG_to_range[D].second;
        llvm::outs() << "\n";
    }
}

std::optional<std::pair<int, int>> StartAndEndLineOfDecl(SourceManager &SM, const Decl * D) {
    SourceLocation Loc = D->getLocation();
    if (!(Loc.isValid() && Loc.isFileID())) {
        return std::nullopt;
    }
    auto StartLoc = SM.getSpellingLineNumber(D->getBeginLoc());
    auto EndLoc = SM.getSpellingLineNumber(D->getEndLoc());
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
    // 打印 jsonValue 的内容
    if (auto *obj = jsonValue.getAsObject()) {
        // 查看并打印对象内的键值对
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
    explicit IncInfoCollectASTVisitor(ASTContext *Context, const std::optional<std::vector<std::pair<int, int>>>& DiffLines, CallGraph &CG)
        : Context(Context), DiffLines(DiffLines), CG(CG) {}
    
    bool isGlobalConstant(const Decl *D) {
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
    std::unordered_set<const Decl *> FunctionsNeedReanalyze;
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

class MyCallGraph : public CallGraph {
public:
    explicit MyCallGraph(ASTContext *Context) {}

    bool VisitCallExpr(CallExpr *call) {
        if (const FunctionDecl *callee = call->getDirectCallee()) {
            if (!FunctionStack.empty()) {
                const FunctionDecl *caller = FunctionStack.top();
                SmallString<128> callerName;
                index::generateUSRForDecl(caller, callerName);
                SmallString<128> calleeName;
                index::generateUSRForDecl(callee, calleeName);
                callGraph[callerName.c_str()].insert(calleeName.c_str());
            }
        } else if (auto callee = call->getCallee()) {
            
        }
        return true;
    }

    void printCallGraph(const std::string &outputPath) {
        const SourceManager &SM = Context->getSourceManager();
        FileID MainFileID = SM.getMainFileID();
        const FileEntry *FE = SM.getFileEntryForID(MainFileID);
        
        if (FE) {
            // llvm::errs() << "Translation Unit: " << FE->getName() << "\n";
        } else {
            llvm::errs() << "Translation Unit: <unknown>\n";
            return ;
        }
        if (outputPath == "") {
            llvm::outs() << "digraph CallGraph {\n";
            for (const auto &entry : callGraph) {
                for (const auto &callee : entry.second) {
                    llvm::outs() << entry.first.length() << ":" << entry.first << 
                        " -> " << callee.length() << ":" << callee << "\n";
                }
            }
            llvm::outs() << "}\n";
            return;
        }
        std::string DotFileName = outputPath + FE->getName().str() + ".dot";
        std::filesystem::path DotFilePath(DotFileName);
        std::filesystem::create_directories(DotFilePath.parent_path());
        std::ofstream outFile(DotFileName);
        if (!outFile.is_open()) {
            std::cerr << "Error: Could not open file " << DotFileName << " for writing.\n";
            return;
        }
        outFile << "digraph CallGraph {\n";
        for (const auto &entry : callGraph) {
            for (const auto &callee : entry.second) {
                outFile << "  \"" << entry.first << "\" -> \"" << callee << "\";\n";
            }
        }
        outFile << "}\n";
        outFile.close();
    }

private:
    ASTContext *Context;
    std::stack<const FunctionDecl *> FunctionStack;
    std::unordered_map<std::string, std::unordered_set<std::string>> callGraph;
};

class IncInfoCollectConsumer : public clang::ASTConsumer {
public:
    explicit IncInfoCollectConsumer(ASTContext *Context, const std::string &outputPath, const std::optional<llvm::json::Object> GlobalDiffLines)
        : CG(), OutputPath(outputPath), DiffLines(std::nullopt), IncVisitor(Context, DiffLines, CG) {
        if (GlobalDiffLines) {
            const SourceManager &SM = Context->getSourceManager();
            FileID MainFileID = SM.getMainFileID();
            const FileEntry *FE = SM.getFileEntryForID(MainFileID);
            // printJsonObject(*GlobalDiffLines);
            auto diff_array = GlobalDiffLines->getArray(FE->getName());
            if (diff_array) {
                DiffLines = std::vector<std::pair<int, int>>();
                for (auto line: *diff_array) {
                    auto line_arr = line.getAsArray();
                    auto line_start = (*line_arr)[0].getAsInteger();
                    auto line_count = (*line_arr)[1].getAsInteger();
                    if (line_start && line_count) {
                        auto pair = std::make_pair<int, int>(*line_start, *line_count);
                        DiffLines->push_back(pair);
                    }
                }
            } else {
                llvm::errs() << FE->getName() << " has no diff lines information.\n";
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
        CG.print(llvm::outs());
        llvm::ReversePostOrderTraversal<clang::CallGraph*> RPOT(&CG);
        SourceManager &SM = Context.getSourceManager();
        for (CallGraphNode *N : RPOT) {
            if (N == CG.getRoot()) continue;
            Decl *D = N->getDecl();
            auto loc = StartAndEndLineOfDecl(SM, D);
            if (!loc) continue;
            auto StartLoc = loc->first;
            auto EndLoc = loc->second;
            CG_to_range[D] = std::make_pair(StartLoc, EndLoc);
            if (isChangedLine(DiffLines, StartLoc, EndLoc)) {
                FunctionsNeedReanalyze.insert(D);
            }
        }
        dumpFunctionsNeedReanalyze(FunctionsNeedReanalyze, CG_to_range);
        IncVisitor.TraverseDecl(Context.getTranslationUnitDecl());
        IncVisitor.DumpGlobalConstantSet();
        // process Global Constant
        for (auto D: IncVisitor.GlobalConstantSet) {

        }
    }

private:
    CallGraph CG;
    IncInfoCollectASTVisitor IncVisitor;
    std::unordered_map<const Decl *, std::pair<unsigned int, unsigned int>> CG_to_range;
    std::string OutputPath;
    std::deque<Decl *> LocalTUDecls;
    std::optional<std::vector<std::pair<int, int>>> DiffLines; // empty means no change, nullopt means new file
    std::unordered_set<const Decl *> FunctionsNeedReanalyze;
};

class IncInfoCollectAction : public clang::ASTFrontendAction {
public:
    IncInfoCollectAction(const std::string &outputPath, const std::string &diffPath) :
    OutputPath(outputPath), DiffLines(std::nullopt) {
        initDiffLines(diffPath);
    }

    void initDiffLines(const std::string &diffPath) {
        if (diffPath.empty()) {
            llvm::errs() << "No diff lines information.\n";
            return ;
        }
        std::ifstream file(diffPath);
         if (!file.is_open()) {
            llvm::errs() << "Failed to open file.\n";
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
        return std::make_unique<IncInfoCollectConsumer>(&CI.getASTContext(), OutputPath, DiffLines);
    }

private:
    std::string OutputPath;
    // Don't use pointer, because jsonStr is declared at function `initDiffLines`, 
    // and it will be freed automatically while exiting the function.
    std::optional<llvm::json::Object> DiffLines;
};

class IncInfoCollectActionFactory : public FrontendActionFactory {
public:
    IncInfoCollectActionFactory(const std::string &outputPath, const std::string &diffPath):
     OutputPath(outputPath), DiffPath(diffPath) {}

    std::unique_ptr<FrontendAction> create() override {
        return std::make_unique<IncInfoCollectAction>(OutputPath, DiffPath);
    }

private:
    std::string OutputPath;
    std::string DiffPath;
};

static llvm::cl::OptionCategory ToolCategory("Collect Inc Info Options");
static llvm::cl::opt<std::string> OutputPath("o", llvm::cl::desc("Specify output path for dot file"), 
    llvm::cl::value_desc("call graph dir"), llvm::cl::init(""));
static llvm::cl::opt<std::string> DiffPath("diff", llvm::cl::desc("Specify diff info files"),
    llvm::cl::value_desc("diff info files"), llvm::cl::init(""));

int main(int argc, const char **argv) {
    auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCategory);
    if (!ExpectedParser) {
        // Fail gracefully for unsupported options.
        llvm::errs() << ExpectedParser.takeError();
        return 1;
    }
    CommonOptionsParser& OptionsParser = ExpectedParser.get();

    ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());
    IncInfoCollectActionFactory Factory(OutputPath, DiffPath);
    return Tool.run(&Factory);
}
