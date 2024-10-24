#include "IncInfoCollectASTVisitor.h"

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
        auto loc = DLM.StartAndEndLineOfDecl(FD);
        // record changed field
        if ((loc && DLM.isChangedLine(loc->first, loc->second))) {
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

bool IncInfoCollectASTVisitor::TraverseDecl(Decl *D) {
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
bool IncInfoCollectASTVisitor::ProcessDeclRefExpr(Expr * const E, NamedDecl * const ND) {
    if (GlobalConstantSet.count(ND)) {
        
    }
    return true;
}

bool IncInfoCollectASTVisitor::VisitDeclRefExpr(DeclRefExpr *DR) {
    auto ND = DR->getFoundDecl();
    if (!inFunctionOrMethodStack.empty() && TaintDecls.count(ND)) {
        // use changed decl, reanalyze this function
        FunctionsNeedReanalyze.insert(inFunctionOrMethodStack.back());
    }
    return ProcessDeclRefExpr(DR, ND);
}

bool IncInfoCollectASTVisitor::VisitMemberExpr(MemberExpr *ME) {
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

void IncInfoCollectASTVisitor::DumpGlobalConstantSet() {
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