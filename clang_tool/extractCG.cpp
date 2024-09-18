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
#include <llvm-17/llvm/Support/Casting.h>
#include <llvm-17/llvm/Support/raw_ostream.h>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <stack>
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

using namespace clang;
using namespace clang::tooling;
using namespace clang::ast_matchers;

bool isChangedLine(std::vector<std::pair<int, int>> DiffLines, unsigned int line) {
    if (DiffLines.empty()) {
        return false;
    }
    // 使用 lambda 表达式来定义比较函数
    auto it = std::lower_bound(DiffLines.begin(), DiffLines.end(), std::make_pair(line + 1, 0),
                            [](const std::pair<int, int> &a, const std::pair<int, int> &b) {
                                return a.first < b.first;
                            });

    // 检查前一个范围（如果存在）是否覆盖了给定的行号
    if (it != DiffLines.begin()) {
        --it;  // 找到第一个不大于 line 的区间
        if (line >= it->first && line <= it->first + it->second) {
            return true;  // 如果 line 在这个区间内，返回 true
        }
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
    explicit IncInfoCollectASTVisitor(ASTContext *Context)
        : Context(Context) {}

    explicit IncInfoCollectASTVisitor(ASTContext *Context, std::vector<std::pair<int, int>> DiffLines, CallGraph *CG)
        : Context(Context), DiffLines(DiffLines), CG(CG) {}
    
    bool isGlobalConstant(const Decl *D) {
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
            if (loc && isChangedLine(DiffLines, loc->first)) {
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
            if ((loc && isChangedLine(DiffLines, loc->first))) {
                TaintDecls.insert(FD);
            }
            // TODO: if this field is used in `CXXCtorInitializer`, the correspond `CXXCtor` should be reanalyze
            
        } else {
            if (CG->getNode(D)) {
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
    std::vector<std::pair<int, int>> DiffLines;
    CallGraph *CG;
    DeclRefFinder DRFinder;
    std::vector<const Decl *> inFunctionOrMethodStack;
};

class MyCallGraph : public CallGraph, IncInfoCollectASTVisitor {
public:
    explicit MyCallGraph(ASTContext *Context): IncInfoCollectASTVisitor(Context) {}

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
    std::stack<const FunctionDecl *> FunctionStack;
    std::unordered_map<std::string, std::unordered_set<std::string>> callGraph;
};

class CallGraphConsumer : public clang::ASTConsumer {
public:
    explicit CallGraphConsumer(ASTContext *Context, const std::string &outputPath)
        : CG(), OutputPath(outputPath), DiffLines{{1, 100000000}}, IncVisitor(Context) {
            IncVisitor.DiffLines = DiffLines;
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
            if (isChangedLine(DiffLines, StartLoc)) {
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
    std::vector<std::pair<int, int>> DiffLines;
    std::unordered_set<const Decl *> FunctionsNeedReanalyze;
};

class CallGraphAction : public clang::ASTFrontendAction {
public:
    CallGraphAction(const std::string &outputPath) : OutputPath(outputPath) {}

    std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(clang::CompilerInstance &CI, llvm::StringRef file) override {
        return std::make_unique<CallGraphConsumer>(&CI.getASTContext(), OutputPath);
    }

private:
    std::string OutputPath;
};

class CallGraphActionFactory : public FrontendActionFactory {
public:
    CallGraphActionFactory(const std::string &outputPath) : OutputPath(outputPath) {}

    std::unique_ptr<FrontendAction> create() override {
        return std::make_unique<CallGraphAction>(OutputPath);
    }

private:
    std::string OutputPath;
    std::string DiffPath;
};

static llvm::cl::OptionCategory ToolCategory("callgraph-tool");
static llvm::cl::opt<std::string> OutputPath("o", llvm::cl::desc("Specify output path for dot file"), 
    llvm::cl::value_desc("call graph dir"), llvm::cl::init(""));
static llvm::cl::opt<std::string> DiffInfo("diff", llvm::cl::desc("Specify diff info files"),
    llvm::cl::value_desc("diff info files"), llvm::cl::init(""));
static llvm::cl::opt<bool> IncMode("inc", llvm::cl::desc("Active incremental mode"), llvm::cl::value_desc("incremental mode"), llvm::cl::init(false));

int main(int argc, const char **argv) {
    auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCategory);
    if (!ExpectedParser) {
        // Fail gracefully for unsupported options.
        llvm::errs() << ExpectedParser.takeError();
        return 1;
    }
    CommonOptionsParser& OptionsParser = ExpectedParser.get();

    ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());
    CallGraphActionFactory Factory(OutputPath);
    return Tool.run(&Factory);
}
