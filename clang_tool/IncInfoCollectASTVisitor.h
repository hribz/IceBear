#ifndef INC_INFO_COLLECT_AST_VISITOR_H
#define INC_INFO_COLLECT_AST_VISITOR_H

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
#include <llvm/ADT/DenseSet.h>
#include <llvm/ADT/StringRef.h>
#include <llvm/Support/Error.h>
#include <llvm/Support/JSON.h>
#include <llvm/Support/raw_ostream.h>
#include <unordered_set>
#include <vector>

#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Index/USRGeneration.h"
#include "clang/Analysis/AnalysisDeclContext.h"

#include "DiffLineManager.h"
#include "ReverseCallGraph.h"

using namespace clang;
using SetOfConstDecls = llvm::DenseSet<const Decl *>;

class IncOptions {
public:
    bool PrintLoc = false;
    bool ClassLevelTypeChange = true;
    bool FieldLevelTypeChange = false;

    bool DumpCG = false;
    bool DumpToFile = true;
    bool DumpUSR = false;
    bool CTU = false;

    std::string RFPath;
    std::string CppcheckRFPath;
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
        ReverseCallGraph &CG, llvm::DenseSet<const Decl *> &FuncsChanged, llvm::DenseSet<const Decl *> &ICC, const IncOptions &incOpt)
        : Context(Context), DLM(dlm), CG(CG), FunctionsChanged(FuncsChanged), ICChanged(ICC), IncOpt(incOpt) {}
    
    bool isGlobalConstant(const Decl *D);

    // Def
    bool VisitDecl(Decl *D);

    bool TraverseDecl(Decl *D);

    bool ProcessDeclRefExpr(Expr * const E, NamedDecl * const ND);

    // Use
    bool VisitDeclRefExpr(DeclRefExpr *DR);
    // Use
    bool VisitMemberExpr(MemberExpr *ME);

    // Process indirect call.
    bool VisitCallExpr(CallExpr *CE);

    void InsertCanonicalDeclToSet(llvm::DenseSet<const Decl *> &set, const Decl *D) {
        set.insert(D->getCanonicalDecl());
    }

    int CountCanonicalDeclInSet(llvm::DenseSet<const Decl *> &set, const Decl *D) {
        return set.count(D->getCanonicalDecl());
    }

    void DumpGlobalConstantSet();

    void DumpTaintDecls();

private:
    ASTContext *Context;
    llvm::DenseSet<const Decl *> GlobalConstantSet;
    // Decls have changed, the function/method use these should reanalyze.
    // Don't record changed functions and methods, they are recorded in 
    // FunctionsChanged. Just consider indirect factors which make
    // functions/methods need to reanalyze. Such as GlobalConstant and 
    // class/struct change.
    llvm::DenseSet<const Decl *> TaintDecls; 
    llvm::DenseSet<const Decl *> &FunctionsChanged;
    llvm::DenseSet<const Decl *> &ICChanged;
    llvm::DenseSet<const Decl *> FPChanged;
    DiffLineManager &DLM;
    ReverseCallGraph &CG;
    DeclRefFinder DRFinder;
    std::vector<const Decl *> inFunctionOrMethodStack;
    const IncOptions &IncOpt;
};

#endif // INC_INFO_COLLECT_AST_VISITOR_H