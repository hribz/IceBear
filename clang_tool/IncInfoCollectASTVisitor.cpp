#include "IncInfoCollectASTVisitor.h"
#include <clang/AST/DeclCXX.h>
#include <llvm/Support/Casting.h>

bool IncInfoCollectASTVisitor::isGlobalConstant(const Decl *D) {
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

bool IncInfoCollectASTVisitor::VisitDecl(Decl *D) {
    // record all changed global constants def
    if (isGlobalConstant(D)) {
        auto loc = DLM.StartAndEndLineOfDecl(D);
        if (loc && DLM.isChangedLine(loc->first, loc->second)) {
            // Should we just record canonical decl?
            InsertCanonicalDeclToSet(GlobalConstantSet, D);
            InsertCanonicalDeclToSet(TaintDecls, D);
        } else {
            // this global constant is not changed, but maybe propogate by changed global constant
            DRFinder.TraverseDecl(D);
            for (auto RefD: DRFinder.getFoundedRefDecls()) {
                if (CountCanonicalDeclInSet(GlobalConstantSet, RefD)) {
                    InsertCanonicalDeclToSet(GlobalConstantSet, D);
                    InsertCanonicalDeclToSet(TaintDecls, D);
                    break;
                }
            }
            DRFinder.clearRefDecls();
            // No need to traverse this decl node and its children
            // note: It seems that `return false` will stop the visitor.
            // return false;
        }
    }
    
    if (isa<RecordDecl>(D)) {
        return true;
        // TODO: Is it neccessary to consider type change?
        RecordDecl *RD = dyn_cast<RecordDecl>(D);
        auto loc = DLM.StartAndEndLineOfDecl(RD);
        if (loc && DLM.isChangedLine(loc->first, loc->second)) {
            InsertCanonicalDeclToSet(TaintDecls, RD);
        } else if(auto CXXRD = llvm::dyn_cast_or_null<CXXRecordDecl>(RD)) {
            // Traverse all base records.
            for (const auto &base: CXXRD->bases()) {
                auto *BaseDecl = base.getType()->getAsCXXRecordDecl();
                if (CountCanonicalDeclInSet(TaintDecls, BaseDecl)) {
                    InsertCanonicalDeclToSet(TaintDecls, CXXRD);
                    break;
                }
            }
        }
    } else if (isa<FieldDecl>(D)) {
        return true;
        FieldDecl *FD = dyn_cast<FieldDecl>(D);
        auto loc = DLM.StartAndEndLineOfDecl(FD);
        // record changed field
        if ((loc && DLM.isChangedLine(loc->first, loc->second))) {
            InsertCanonicalDeclToSet(TaintDecls, FD);
        }
        // TODO: if this field is used in `CXXCtorInitializer`, the correspond `CXXCtor` should be reanalyze
        
    } else {
        if (CG.getNode(D)) {
            inFunctionOrMethodStack.push_back(D);
        }
    }
    return true;
}

bool IncInfoCollectASTVisitor::TraverseDecl(Decl *D) {
    if (!D) {
        // D maybe nullptr when VisitTemplateTemplateParmDecl.
        return true;
    }
    if (CountCanonicalDeclInSet(FunctionsNeedReanalyze, D)) {
        // If this `Decl` has been confirmed need to be reanalyzed, we don't need to traverse it.
        return true;
    }
    bool Result = clang::RecursiveASTVisitor<IncInfoCollectASTVisitor>::TraverseDecl(D);
    if (!inFunctionOrMethodStack.empty() && inFunctionOrMethodStack.back() == D->getCanonicalDecl()) {
        inFunctionOrMethodStack.pop_back(); // exit function/method
    }
    return Result;
}

// process all global constants use
bool IncInfoCollectASTVisitor::ProcessDeclRefExpr(Expr * const E, NamedDecl * const ND) {
    if (CountCanonicalDeclInSet(GlobalConstantSet, ND)) {
        
    }
    return true;
}

bool IncInfoCollectASTVisitor::VisitDeclRefExpr(DeclRefExpr *DR) {
    auto ND = DR->getFoundDecl();
    if (!inFunctionOrMethodStack.empty() && CountCanonicalDeclInSet(TaintDecls, ND)) {
        // use changed decl, reanalyze this function
        InsertCanonicalDeclToSet(FunctionsNeedReanalyze, inFunctionOrMethodStack.back());
    }
    return ProcessDeclRefExpr(DR, ND);
}

bool IncInfoCollectASTVisitor::VisitMemberExpr(MemberExpr *ME) {
    auto member = ME->getMemberDecl();
    if (!inFunctionOrMethodStack.empty() && CountCanonicalDeclInSet(TaintDecls, member)) {
        InsertCanonicalDeclToSet(FunctionsNeedReanalyze, inFunctionOrMethodStack.back());
    }
    // member could be VarDecl, EnumConstantDecl, CXXMethodDecl, FieldDecl, etc.
    if (isa<VarDecl, EnumConstantDecl>(member)) {
        ProcessDeclRefExpr(ME, member);
    } else {
        if (isa<CXXMethodDecl>(member)) {

        } else {
            const auto *field = cast<FieldDecl>(member);
        }
    }
    return true;
}

void IncInfoCollectASTVisitor::DumpGlobalConstantSet() {
    if (GlobalConstantSet.empty() || IncOpt.DumpToFile) {
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

void IncInfoCollectASTVisitor::DumpTaintDecls() {
    if (TaintDecls.empty() || IncOpt.DumpToFile) {
        return;
    }
    llvm::outs() << "--- Taint Decls ---\n";
    for (auto &D : TaintDecls) {
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