#include <filesystem>
#include <iostream>
#include <fstream>
#include <llvm-17/llvm/Support/raw_ostream.h>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <stack>

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

using namespace clang;
using namespace clang::tooling;
using namespace clang::ast_matchers;

class CallGraphVisitor : public RecursiveASTVisitor<CallGraphVisitor> {
public:
    explicit CallGraphVisitor(ASTContext *Context)
        : Context(Context) {}

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
        }
        return true;
    }

    bool VisitFunctionDecl(FunctionDecl *func) {
        FunctionStack.push(func);
        return true;
    }

    bool TraverseFunctionDecl(FunctionDecl *func) {
        if (!func->hasBody())
            return true;

        FunctionStack.push(func);
        RecursiveASTVisitor<CallGraphVisitor>::TraverseFunctionDecl(func);
        FunctionStack.pop();
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

class CallGraphConsumer : public clang::ASTConsumer {
public:
    explicit CallGraphConsumer(ASTContext *Context, const std::string &outputPath)
        : Visitor(Context), OutputPath(outputPath) {}

    void HandleTranslationUnit(clang::ASTContext &Context) override {
        Visitor.TraverseDecl(Context.getTranslationUnitDecl());
        Visitor.printCallGraph(OutputPath);
    }

private:
    CallGraphVisitor Visitor;
    std::string OutputPath;
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
};

static llvm::cl::OptionCategory ToolCategory("callgraph-tool");
static llvm::cl::opt<std::string> OutputPath("o", llvm::cl::desc("Specify output path for dot file"), 
    llvm::cl::value_desc("graph dir"), llvm::cl::init(""));

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
