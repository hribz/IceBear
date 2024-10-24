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

#include "DiffLineManager.h"

using namespace clang;
using SetOfConstDecls = llvm::DenseSet<const Decl *>;

class IncOptions {
public:
    bool PrintLoc = false;
    bool ClassLevelTypeChange = true;
    bool FieldLevelTypeChange = false;
};

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
    explicit IncInfoCollectASTVisitor(ASTContext *Context, DiffLineManager &dlm, 
        CallGraph &CG, std::unordered_set<const Decl *> &FuncsNeedRA, const IncOptions &incOpt)
        : Context(Context), DLM(dlm), CG(CG), FunctionsNeedReanalyze(FuncsNeedRA), IncOpt(incOpt) {}
    
    bool isGlobalConstant(const Decl *D);

    bool VisitDecl(Decl *D);

    bool TraverseDecl(Decl *D);

    bool ProcessDeclRefExpr(Expr * const E, NamedDecl * const ND);

    bool VisitDeclRefExpr(DeclRefExpr *DR);

    bool VisitMemberExpr(MemberExpr *ME);

    void DumpGlobalConstantSet();

private:
    ASTContext *Context;
    std::unordered_set<const Decl *> GlobalConstantSet;
    std::unordered_set<const Decl *> TaintDecls; // Decls have changed, the function/method use these should reanalyze
    std::unordered_set<const Decl *> &FunctionsNeedReanalyze;
    DiffLineManager &DLM;
    CallGraph &CG;
    DeclRefFinder DRFinder;
    std::vector<const Decl *> inFunctionOrMethodStack;
    const IncOptions &IncOpt;
};