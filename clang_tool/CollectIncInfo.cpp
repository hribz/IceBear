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
#include <memory>
#include <optional>
#include <ostream>
#include <streambuf>
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

#include "IncInfoCollectASTVisitor.h"

using namespace clang;
using namespace clang::tooling;

class IncInfoCollectConsumer : public clang::ASTConsumer {
public:
    explicit IncInfoCollectConsumer(ASTContext *Context, const std::string &outputPath, std::string &diffPath, const IncOptions &incOpt)
    : CG(), OutputPath(outputPath), IncOpt(incOpt), DLM(Context->getSourceManager()), 
      IncVisitor(Context, DLM, CG, FunctionsNeedReanalyze, IncOpt) {
        const SourceManager &SM = Context->getSourceManager();
        FileID MainFileID = SM.getMainFileID();
        const FileEntry *FE = SM.getFileEntryForID(MainFileID);
        MainFilePath = FE->tryGetRealPathName();
        DLM.Initialize(diffPath, MainFilePath.str());
        // Don't print location information.
        // auto PrintPolicy = Context->getPrintingPolicy();
        // PrintPolicy.FullyQualifiedName = true;
        // PrintPolicy.TerseOutput = true;
        // PrintPolicy.PrintInjectedClassNameWithArguments = true;
        // Context->setPrintingPolicy(PrintPolicy);
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
            auto loc = DLM.StartAndEndLineOfDecl(D);
            if (!loc) continue;
            auto StartLoc = loc->first;
            auto EndLoc = loc->second;
            CGToRange[D] = std::make_pair(StartLoc, EndLoc);
            if (DLM.isChangedLine(StartLoc, EndLoc)) {
                FunctionsNeedReanalyze.insert(D);
            }
        }
        DumpCallGraph();
        IncVisitor.TraverseDecl(Context.getTranslationUnitDecl());
        IncVisitor.DumpGlobalConstantSet();
        IncVisitor.DumpTaintDecls();
        DumpFunctionsNeedReanalyze();
    }

    static void getUSRName(const Decl *D, std::string &Str) {
        // Don't use this function if don't need USR representation
        // to avoid redundant string copy.
        D = D->getCanonicalDecl();
        SmallString<128> usr;
        index::generateUSRForDecl(D, usr);
        Str = std::to_string(usr.size());
        Str += ":";
        Str += usr.c_str();
    }

    void DumpCallGraph() {
        if (!CG.size()) {
            return;
        }

        std::ostream* OS = &std::cout;
        // `outFile`'s life time should persist until dump finished.
        // And don't create file if don't need to dump to file.
        std::shared_ptr<std::ofstream> outFile;
        if (IncOpt.DumpToFile) {
            std::string CGFile = MainFilePath.str() + ".cg";
            outFile = std::make_shared<std::ofstream>(CGFile);
            if (!outFile->is_open()) {
                llvm::errs() << "Error: Could not open file " << CGFile << " for writing.\n";
                return;
            }
            OS = outFile.get();
        } else {
            *OS << "--- Call Graph ---\n";
        }

        llvm::ReversePostOrderTraversal<clang::CallGraph*> RPOT(&CG);
        for (CallGraphNode *N : RPOT) {
            if (N == CG.getRoot()) continue;
            Decl *D = N->getDecl();
            if (IncOpt.DumpUSR) {
                std::string ret;
                getUSRName(D, ret);
                *OS << ret;
            } else {
                *OS << AnalysisDeclContext::getFunctionName(D->getCanonicalDecl());
            }
            if (IncOpt.PrintLoc) {
                *OS << " -> " << CGToRange[D].first << ", " << CGToRange[D].second;
            }
            *OS << "\n[\n";
            SetOfConstDecls CalleeSet;
            for (CallGraphNode::CallRecord &CR : N->callees()) {
                Decl *Callee = CR.Callee->getDecl();
                if (CalleeSet.contains(Callee))
                    continue;
                CalleeSet.insert(Callee);
                if (IncOpt.DumpUSR) {
                    std::string ret;
                    getUSRName(Callee, ret);
                    *OS << ret;
                } else {
                    *OS << AnalysisDeclContext::getFunctionName(Callee->getCanonicalDecl());
                }
                if (IncOpt.PrintLoc) {
                    *OS << " -> " << CGToRange[Callee].first << "-" << CGToRange[Callee].second;
                }
                *OS << "\n";
            }
            *OS << "]\n";
        }
        outFile->close();
    }

    void DumpFunctionsNeedReanalyze() {
        if (FunctionsNeedReanalyze.empty()) {
            return;
        }

        std::ostream* OS = &std::cout;
        std::shared_ptr<std::ofstream> outFile;
        if (IncOpt.DumpToFile) {
            std::string ReanalyzeFunctionsFile = MainFilePath.str() + ".cf";
            outFile = std::make_shared<std::ofstream>(ReanalyzeFunctionsFile);
            if (!outFile->is_open()) {
                llvm::errs() << "Error: Could not open file " << ReanalyzeFunctionsFile << " for writing.\n";
                return;
            }
            OS = outFile.get();
        } else {
            *OS << "--- Functions Need to Reanalyze ---\n";
        }

        for (auto &D : FunctionsNeedReanalyze) {
            if (IncOpt.DumpUSR) {
                std::string ret;
                getUSRName(D, ret);
                *OS << ret;
            } else {
                *OS << AnalysisDeclContext::getFunctionName(D->getCanonicalDecl());
            }
            if (IncOpt.PrintLoc) {
                *OS << " -> " << CGToRange[D].first << "-" << CGToRange[D].second;
            }
            *OS << "\n";
        }
        outFile->close();
    }

private:
    const IncOptions &IncOpt;
    llvm::StringRef MainFilePath;
    DiffLineManager DLM;
    CallGraph CG;
    IncInfoCollectASTVisitor IncVisitor;
    std::unordered_map<const Decl *, std::pair<unsigned int, unsigned int>> CGToRange;
    std::string OutputPath;
    std::deque<Decl *> LocalTUDecls;
    std::unordered_set<const Decl *> FunctionsNeedReanalyze;
};

class IncInfoCollectAction : public clang::ASTFrontendAction {
public:
    IncInfoCollectAction(std::string &outputPath, std::string &diffPath, const IncOptions &incOpt) :
    OutputPath(outputPath), DiffPath(diffPath), IncOpt(incOpt) {}

    std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(clang::CompilerInstance &CI, llvm::StringRef file) override {
        return std::make_unique<IncInfoCollectConsumer>(&CI.getASTContext(), OutputPath, DiffPath, IncOpt);
    }

private:
    std::string &OutputPath;
    std::string &DiffPath;
    const IncOptions &IncOpt;
};

class IncInfoCollectActionFactory : public FrontendActionFactory {
public:
    IncInfoCollectActionFactory(std::string &outputPath, std::string &diffPath, const IncOptions &incOpt):
     OutputPath(outputPath), DiffPath(diffPath), IncOpt(incOpt) {}

    std::unique_ptr<FrontendAction> create() override {
        return std::make_unique<IncInfoCollectAction>(OutputPath, DiffPath, IncOpt);
    }

private:
    std::string &OutputPath;
    std::string &DiffPath;
    const IncOptions & IncOpt;
};

static llvm::cl::OptionCategory ToolCategory("Collect Inc Info Options");
static llvm::cl::opt<std::string> OutputPath("o", llvm::cl::desc("Specify output path for dot file"), 
    llvm::cl::value_desc("call graph dir"), llvm::cl::init(""));
static llvm::cl::opt<std::string> DiffPath("diff", llvm::cl::desc("Specify diff info files"),
    llvm::cl::value_desc("diff info files"), llvm::cl::init(""));
static llvm::cl::opt<bool> PrintLoc("loc", llvm::cl::desc("Print location information in FunctionName or not"),
    llvm::cl::value_desc("AnonymousTagLocations"), llvm::cl::init(false));
static llvm::cl::opt<bool> ClassLevel("class", llvm::cl::desc("Propogate type change by class level"),
    llvm::cl::value_desc("class level change"), llvm::cl::init(true));
static llvm::cl::opt<bool> FieldLevel("field", llvm::cl::desc("Propogate type change by field level"),
    llvm::cl::value_desc("field level change"), llvm::cl::init(false));
static llvm::cl::opt<bool> DumpToFile("dump-file", llvm::cl::desc("Dump CG and CF to file"),
    llvm::cl::value_desc("dump to file or stream"), llvm::cl::init(true));
static llvm::cl::opt<bool> DumpUSR("dump-usr", llvm::cl::desc("Dump USR function name"),
    llvm::cl::value_desc("dump usr fname"), llvm::cl::init(false));

int main(int argc, const char **argv) {
    auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCategory);
    if (!ExpectedParser) {
        // Fail gracefully for unsupported options.
        llvm::errs() << ExpectedParser.takeError();
        return 1;
    }
    CommonOptionsParser& OptionsParser = ExpectedParser.get();

    ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());
    IncOptions IncOpt{.PrintLoc=PrintLoc, .ClassLevelTypeChange=ClassLevel, .FieldLevelTypeChange=FieldLevel, 
                      .DumpToFile=DumpToFile, .DumpUSR=DumpUSR};
    IncInfoCollectActionFactory Factory(OutputPath, DiffPath, IncOpt);
    return Tool.run(&Factory);
}