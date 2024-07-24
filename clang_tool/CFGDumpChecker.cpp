#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/CheckerManager.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugType.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/CheckerContext.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/AnalysisManager.h"
#include "clang/StaticAnalyzer/Frontend/CheckerRegistry.h"
#include <clang/Basic/LangOptions.h>

using namespace clang;
using namespace ento;

class CFGDumpChecker : public Checker<check::ASTCodeBody> {
public:
    void checkASTCodeBody(const Decl *D, AnalysisManager &Mgr, BugReporter &BR) const {
        if (const FunctionDecl *FD = dyn_cast<FunctionDecl>(D)) {
            const CFG *cfg = Mgr.getCFG(FD);
            if (cfg) {
                llvm::errs() << "CFG for function: " << FD->getNameInfo().getAsString() << "\n";
                cfg->dump(LangOptions(), true);
            }
        }
    }
};

extern "C" void clang_registerCheckers(CheckerRegistry &registry) {
    registry.addChecker<CFGDumpChecker>("example.CFGDumpChecker", "Dump CFG for each function", "");
}

extern "C" const char clang_analyzerAPIVersionString[] = "17";
