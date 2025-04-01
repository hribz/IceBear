#include <clang/AST/ASTContext.h>
#include <clang/AST/Decl.h>
#include <clang/AST/DeclCXX.h>
#include <clang/AST/Expr.h>
#include <clang/AST/Type.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/raw_ostream.h>

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
  // if (auto FD = dyn_cast_or_null<FieldDecl>(D)) {
  //     if (FD->getType().isConstQualified()) {
  //         return true;
  //     }
  //     return false;
  // }
  return false;
}

bool IncInfoCollectASTVisitor::VisitDecl(Decl *D) {
  // record all changed global constants def
  if (isGlobalConstant(D)) {
    if (DLM.isChangedDecl(D)) {
      // Should we just record canonical decl?
      InsertCanonicalDeclToSet(GlobalConstantSet, D);
      InsertCanonicalDeclToSet(TaintDecls, D);
    } else {
      // this global constant is not changed, but maybe propogate by changed
      // global constant
      DRFinder.TraverseDecl(D);
      for (auto RefD : DRFinder.getFoundedRefDecls()) {
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
    if (DLM.isChangedDecl(RD)) {
      InsertCanonicalDeclToSet(TaintDecls, RD);
    } else if (auto CXXRD = llvm::dyn_cast_or_null<CXXRecordDecl>(RD)) {
      // Traverse all base records.
      for (const auto &base : CXXRD->bases()) {
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
    // record changed field
    if (DLM.isChangedDecl(FD)) {
      InsertCanonicalDeclToSet(TaintDecls, FD);
    }
    // TODO: if this field is used in `CXXCtorInitializer`, the correspond
    // `CXXCtor` should be reanalyze
  }
  return true;
}

bool IncInfoCollectASTVisitor::TraverseDecl(Decl *D) {
  if (!D) {
    // D maybe nullptr when VisitTemplateTemplateParmDecl.
    return true;
  }
  // Record Affected Nodes
  if (isa<TypedefDecl, FieldDecl, VarDecl, FunctionDecl>(D)) {
    if (!AN.count(D) && DLM.isChangedDecl(D)) {
      AN.insert(D);
      auto *FirstDecl = D->getCanonicalDecl();
      // All relevant decls should be added to AN.
      for (auto *curr = FirstDecl; curr != nullptr;
           curr = curr->getNextDeclInContext()) {
        AN.insert(D);
        // // Function definition should be added to AN.
        // if (auto *FD = llvm::dyn_cast<FunctionDecl>(D)) {
        //     auto *Definition = FD->getDefinition();
        //     if (Definition) {
        //         AN.insert(Definition);
        //     }
        // }
      }
    }
  }

  bool isFunctionDecl = isa<FunctionDecl>(D);
  if (isFunctionDecl) {
    if (!CG.getNode(D)) {
      // Don't care functions not exist in CallGraph.
      return true;
    }
    auto FD = dyn_cast<FunctionDecl>(D);
    if (!FD->isThisDeclarationADefinition()) {
      // Just handle function definition, functions don't have definition
      // maybe inlined only when ctu analysis.
      return true;
    }
    if (CountCanonicalDeclInSet(FunctionsChanged, D) || DLM.isChangedDecl(D)) {
      // If this `Decl` has been confirmed need to be reanalyzed, we don't need
      // to traverse it.
      InsertCanonicalDeclToSet(FunctionsChanged, D);
      return true;
    }
    inFunctionOrMethodStack.push_back(
        D->getCanonicalDecl()); // enter function/method
  }
  bool Result =
      clang::RecursiveASTVisitor<IncInfoCollectASTVisitor>::TraverseDecl(D);
  if (isFunctionDecl) {
    inFunctionOrMethodStack.pop_back(); // exit function/method
  }
  return Result;
}

// process all global constants use
bool IncInfoCollectASTVisitor::ProcessDeclRefExpr(Expr *const E,
                                                  NamedDecl *const ND) {
  if (CountCanonicalDeclInSet(GlobalConstantSet, ND)) {
  }
  return true;
}

bool maybeIndirectCall(ASTContext *Context, DeclRefExpr *DR) {
  auto parents = Context->getParents(*DR);

  while (!parents.empty()) {
    if (auto CE = parents[0].get<CallExpr>()) {
      if (CE->getCalleeDecl() == DR->getFoundDecl()) {
        return false;
      }
      return true;
    }

    if (parents[0].get<clang::ImplicitCastExpr>()) {
      parents = Context->getParents(parents[0]);
      continue;
    }
    break;
  }

  return true;
}

QualType getCanonicalFunctionType(clang::QualType type) {
  if (auto *ptrType = type->getAs<clang::PointerType>()) {
    return ptrType->getPointeeType().getCanonicalType();
  }
  return type.getCanonicalType();
}

bool IncInfoCollectASTVisitor::VisitDeclRefExpr(DeclRefExpr *DR) {
  auto ND = DR->getFoundDecl();
  if (!inFunctionOrMethodStack.empty() &&
      CountCanonicalDeclInSet(TaintDecls, ND)) {
    // use changed decl, reanalyze this function
    InsertCanonicalDeclToSet(FunctionsChanged, inFunctionOrMethodStack.back());
    // add it to AN.
    // InsertCanonicalDeclToSet(AN, inFunctionOrMethodStack.back());
  }

  // TODO: May need a pre-pass to collect MayUsedAsFP before IncInfoCollectASTVisitor.
  if (isa<FunctionDecl>(ND) && CountCanonicalDeclInSet(FunctionsChanged, ND)) {
    // If this dereference is not a direct function call.
    if (maybeIndirectCall(Context, DR)) {
      auto FD = dyn_cast<FunctionDecl>(ND);
      TypesMayUsedByFP.insert(FD->getType().getCanonicalType());
    }
  }

  return ProcessDeclRefExpr(DR, ND);
}

bool IncInfoCollectASTVisitor::VisitMemberExpr(MemberExpr *ME) {
  auto member = ME->getMemberDecl();
  if (!inFunctionOrMethodStack.empty() &&
      CountCanonicalDeclInSet(TaintDecls, member)) {
    InsertCanonicalDeclToSet(FunctionsChanged, inFunctionOrMethodStack.back());
    // InsertCanonicalDeclToSet(AN, inFunctionOrMethodStack.back());
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

bool isFunctionTypeMatch(clang::ASTContext &Context, clang::QualType funcType,
                         clang::QualType targetType) {
  if (auto *ptrType = targetType->getAs<clang::PointerType>()) {
    targetType = ptrType->getPointeeType();
  }

  auto *funcTypePtr = funcType->getAs<clang::FunctionType>();
  auto *targetTypePtr = targetType->getAs<clang::FunctionType>();

  if (!funcTypePtr || !targetTypePtr) {
    return false;
  }

  if (!Context.hasSameType(funcTypePtr->getReturnType(),
                           targetTypePtr->getReturnType())) {
    return false;
  }

  if (auto *funcProto = llvm::dyn_cast<clang::FunctionProtoType>(funcTypePtr)) {
    auto *targetProto = llvm::dyn_cast<clang::FunctionProtoType>(targetTypePtr);
    if (!targetProto) {
      return false;
    }

    if (funcProto->getNumParams() != targetProto->getNumParams()) {
      return false;
    }

    for (unsigned i = 0; i < funcProto->getNumParams(); ++i) {
      if (!Context.hasSameType(funcProto->getParamType(i),
                               targetProto->getParamType(i))) {
        return false;
      }
    }

    if (funcProto->isVariadic() != targetProto->isVariadic()) {
      return false;
    }
  }
  else if (llvm::isa<clang::FunctionNoProtoType>(funcTypePtr)) {
    return false;
  }

  return true;
}

bool IncInfoCollectASTVisitor::VisitCallExpr(CallExpr *CE) {
  Expr *callee = CE->getCallee()->IgnoreImpCasts();
  // Identify indirect call: function pointer.
  if (callee->getType()->isFunctionPointerType()) {
    // Reanalyze this function if its type match.
    bool foundMatch = false;
    for (const auto Ty : TypesMayUsedByFP) {
      // The callee has the same type as the function pointer.
      if (isFunctionTypeMatch(*Context, Ty, getCanonicalFunctionType(callee->getType()))) {
        foundMatch = true;
        break;
      }
    }
    if (foundMatch) {
      AffectedIndirectCallByFP++;
      FunctionsChanged.insert(inFunctionOrMethodStack.back());
    }
  } 
  // Identify indirect call: virtual function.
  else if (clang::MemberExpr *memberExpr =
                 llvm::dyn_cast<clang::MemberExpr>(callee)) {
    clang::ValueDecl *decl = memberExpr->getMemberDecl();
    if (clang::CXXMethodDecl *methodDecl =
            llvm::dyn_cast<clang::CXXMethodDecl>(decl)) {
      if (methodDecl->isVirtual()) {
        if (CountCanonicalDeclInSet(AffectedVFs, methodDecl)) {
          AffectedIndirectCallByVF++;
          FunctionsChanged.insert(inFunctionOrMethodStack.back());
        }
      }
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
    if (IncOpt.PrintLoc) {
      auto loc = DLM.StartAndEndLineOfDecl(D);
      if (loc)
        llvm::outs() << " -> " << loc->first << "-" << loc->second;
    }
    llvm::outs() << "\n";
  }
  llvm::outs().flush();
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
    if (IncOpt.PrintLoc) {
      auto loc = DLM.StartAndEndLineOfDecl(D);
      if (loc)
        llvm::outs() << " -> " << loc->first << "-" << loc->second;
    }
    llvm::outs() << "\n";
  }
  llvm::outs().flush();
}