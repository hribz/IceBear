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
#include <iterator>
#include <llvm-17/llvm/ADT/StringRef.h>
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
#include "clang/Analysis/AnalysisDeclContext.h"
#include "clang/Analysis/CallGraph.h"
#include "llvm/ADT/PostOrderIterator.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;
using namespace clang::tooling;
using namespace clang::ast_matchers;
using SetOfConstDecls = llvm::DenseSet<const Decl *>;

static void DumpCallGraph(CallGraph &CG, llvm::StringRef MainFilePath) {
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
        outFile << AnalysisDeclContext::getFunctionName(D) << "\n[\n";
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
            outFile << AnalysisDeclContext::getFunctionName(Callee) << "\n]\n";
        }
    }
}

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
    explicit IncInfoCollectConsumer(ASTContext *Context)
    : CG() {
        const SourceManager &SM = Context->getSourceManager();
        FileID MainFileID = SM.getMainFileID();
        const FileEntry *FE = SM.getFileEntryForID(MainFileID);
        MainFilePath = FE->getName();
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
        DumpCallGraph(CG, MainFilePath);
    }

private:
    CallGraph CG;
    std::deque<Decl *> LocalTUDecls;
    llvm::StringRef MainFilePath;
};

class IncInfoCollectAction : public clang::ASTFrontendAction {
public:
    IncInfoCollectAction() {}

    std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(clang::CompilerInstance &CI, llvm::StringRef file) override {
        return std::make_unique<IncInfoCollectConsumer>(&CI.getASTContext());
    }
};

class IncInfoCollectActionFactory : public FrontendActionFactory {
public:
    IncInfoCollectActionFactory() {}

    std::unique_ptr<FrontendAction> create() override {
        return std::make_unique<IncInfoCollectAction>();
    }
};

static llvm::cl::OptionCategory ToolCategory("Collect Inc Info Options");

int main(int argc, const char **argv) {
    auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCategory);
    if (!ExpectedParser) {
        // Fail gracefully for unsupported options.
        llvm::errs() << ExpectedParser.takeError();
        return 1;
    }
    CommonOptionsParser& OptionsParser = ExpectedParser.get();

    ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());
    IncInfoCollectActionFactory Factory;
    return Tool.run(&Factory);
}
