//===- ReverseCallGraph.h - AST-based Call graph -----------------------*- C++ -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
//  This file declares the AST-based ReverseCallGraph.
//
//  A call graph for functions whose definitions/bodies are available in the
//  current translation unit. The graph has a "virtual" root node that contains
//  edges to all externally available functions.
//
//===----------------------------------------------------------------------===//

#ifndef LLVM_CLANG_ANALYSIS_REVERSE_CALLGRAPH_H
#define LLVM_CLANG_ANALYSIS_REVERSE_CALLGRAPH_H

#include "clang/AST/Decl.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/GraphTraits.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/SetVector.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/iterator_range.h"
#include <memory>

namespace clang {

class ReverseCallGraphNode;
class Decl;
class DeclContext;
class Stmt;

/// The AST-based call graph.
///
/// The call graph extends itself with the given declarations by implementing
/// the recursive AST visitor, which constructs the graph by visiting the given
/// declarations.
class ReverseCallGraph : public RecursiveASTVisitor<ReverseCallGraph> {
  friend class ReverseCallGraphNode;

  using FunctionMapTy =
      llvm::DenseMap<const Decl *, std::unique_ptr<ReverseCallGraphNode>>;

  /// FunctionMap owns all ReverseCallGraphNodes.
  FunctionMapTy FunctionMap;

  /// This is a virtual root node that has edges to all the functions.
  ReverseCallGraphNode *Root;

public:
  ReverseCallGraph();
  ~ReverseCallGraph();

  /// Populate the call graph with the functions in the given
  /// declaration.
  ///
  /// Recursively walks the declaration to find all the dependent Decls as well.
  void addToReverseCallGraph(Decl *D) {
    TraverseDecl(D);
  }

  /// Determine if a declaration should be included in the graph.
  static bool includeInGraph(const Decl *D);

  /// Determine if a declaration should be included in the graph for the
  /// purposes of being a callee. This is similar to includeInGraph except
  /// it permits declarations, not just definitions.
  static bool includeCalleeInGraph(const Decl *D);

  /// Lookup the node for the given declaration.
  ReverseCallGraphNode *getNode(const Decl *) const;

  /// Lookup the node for the given declaration. If none found, insert
  /// one into the graph.
  ReverseCallGraphNode *getOrInsertNode(Decl *);

  using iterator = FunctionMapTy::iterator;
  using const_iterator = FunctionMapTy::const_iterator;

  /// Iterators through all the elements in the graph. Note, this gives
  /// non-deterministic order.
  iterator begin() { return FunctionMap.begin(); }
  iterator end()   { return FunctionMap.end();   }
  const_iterator begin() const { return FunctionMap.begin(); }
  const_iterator end()   const { return FunctionMap.end();   }

  /// Get the number of nodes in the graph.
  unsigned size() const { return FunctionMap.size(); }

  /// Get the virtual root of the graph, all the functions available externally
  /// are represented as callees of the node.
  ReverseCallGraphNode *getRoot() const { return Root; }

  /// Iterators through all the nodes of the graph that have no parent. These
  /// are the unreachable nodes, which are either unused or are due to us
  /// failing to add a call edge due to the analysis imprecision.
  using nodes_iterator = llvm::SetVector<ReverseCallGraphNode *>::iterator;
  using const_nodes_iterator = llvm::SetVector<ReverseCallGraphNode *>::const_iterator;

  void print(raw_ostream &os) const;
  void dump() const;
  void viewGraph() const;

  void addNodesForBlocks(DeclContext *D);

  /// Part of recursive declaration visitation. We recursively visit all the
  /// declarations to collect the root functions.
  bool VisitFunctionDecl(FunctionDecl *FD) {
    // We skip function template definitions, as their semantics is
    // only determined when they are instantiated.
    if (includeInGraph(FD) && FD->isThisDeclarationADefinition()) {
      // Add all blocks declared inside this function to the graph.
      addNodesForBlocks(FD);
      // If this function has external linkage, anything could call it.
      // Note, we are not precise here. For example, the function could have
      // its address taken.
      addNodeForDecl(FD, FD->isGlobal());
    }
    return true;
  }

  /// Part of recursive declaration visitation.
  bool VisitObjCMethodDecl(ObjCMethodDecl *MD) {
    if (includeInGraph(MD)) {
      addNodesForBlocks(MD);
      addNodeForDecl(MD, true);
    }
    return true;
  }

  // We are only collecting the declarations, so do not step into the bodies.
  bool TraverseStmt(Stmt *S) { return true; }

  bool shouldWalkTypesOfTypeLocs() const { return false; }
  bool shouldVisitTemplateInstantiations() const { return true; }
  bool shouldVisitImplicitCode() const { return true; }

private:
  /// Add the given declaration to the call graph.
  void addNodeForDecl(Decl *D, bool IsGlobal);
};

class ReverseCallGraphNode {
public:
  struct CallRecord {
    ReverseCallGraphNode *Caller;
    Expr *CallExpr;

    CallRecord() = default;

    CallRecord(ReverseCallGraphNode *Caller_, Expr *CallExpr_)
        : Caller(Caller_), CallExpr(CallExpr_) {}

    // The call destination is the only important data here,
    // allow to transparently unwrap into it.
    operator ReverseCallGraphNode *() const { return Caller; }
  };

private:
  /// The function/method declaration.
  Decl *FD;

  /// The list of caller functions from this node.
  SmallVector<CallRecord, 5> CallerFunctions;

public:
  ReverseCallGraphNode(Decl *D) : FD(D) {}

  using iterator = SmallVectorImpl<CallRecord>::iterator;
  using const_iterator = SmallVectorImpl<CallRecord>::const_iterator;

  /// Iterators through all the callers/parent of the node.
  iterator begin() { return CallerFunctions.begin(); }
  iterator end() { return CallerFunctions.end(); }
  const_iterator begin() const { return CallerFunctions.begin(); }
  const_iterator end() const { return CallerFunctions.end(); }

  /// Iterator access to callers/parent of the node.
  llvm::iterator_range<iterator> callers() {
    return llvm::make_range(begin(), end());
  }
  llvm::iterator_range<const_iterator> callers() const {
    return llvm::make_range(begin(), end());
  }

  bool empty() const { return CallerFunctions.empty(); }
  unsigned size() const { return CallerFunctions.size(); }

  void addCaller(CallRecord Call) { CallerFunctions.push_back(Call); }

  Decl *getDecl() const { return FD; }

  FunctionDecl *getDefinition() const {
    return getDecl()->getAsFunction()->getDefinition();
  }

  void print(raw_ostream &os) const;
  void dump() const;
};

// NOTE: we are comparing based on the caller only. So different call records
// (with different call expressions) to the same caller will compare equal!
inline bool operator==(const ReverseCallGraphNode::CallRecord &LHS,
                       const ReverseCallGraphNode::CallRecord &RHS) {
  return LHS.Caller == RHS.Caller;
}

} // namespace clang

namespace llvm {

// Specialize DenseMapInfo for clang::ReverseCallGraphNode::CallRecord.
template <> struct DenseMapInfo<clang::ReverseCallGraphNode::CallRecord> {
  static inline clang::ReverseCallGraphNode::CallRecord getEmptyKey() {
    return clang::ReverseCallGraphNode::CallRecord(
        DenseMapInfo<clang::ReverseCallGraphNode *>::getEmptyKey(),
        DenseMapInfo<clang::Expr *>::getEmptyKey());
  }

  static inline clang::ReverseCallGraphNode::CallRecord getTombstoneKey() {
    return clang::ReverseCallGraphNode::CallRecord(
        DenseMapInfo<clang::ReverseCallGraphNode *>::getTombstoneKey(),
        DenseMapInfo<clang::Expr *>::getTombstoneKey());
  }

  static unsigned getHashValue(const clang::ReverseCallGraphNode::CallRecord &Val) {
    // NOTE: we are comparing based on the caller only.
    // Different call records with the same caller will compare equal!
    return DenseMapInfo<clang::ReverseCallGraphNode *>::getHashValue(Val.Caller);
  }

  static bool isEqual(const clang::ReverseCallGraphNode::CallRecord &LHS,
                      const clang::ReverseCallGraphNode::CallRecord &RHS) {
    return LHS == RHS;
  }
};

// Graph traits for iteration, viewing.
template <> struct GraphTraits<clang::ReverseCallGraphNode*> {
  using NodeType = clang::ReverseCallGraphNode;
  using NodeRef = clang::ReverseCallGraphNode *;
  using ChildIteratorType = NodeType::iterator;

  static NodeType *getEntryNode(clang::ReverseCallGraphNode *CGN) { return CGN; }
  static ChildIteratorType child_begin(NodeType *N) { return N->begin();  }
  static ChildIteratorType child_end(NodeType *N) { return N->end(); }
};

template <> struct GraphTraits<const clang::ReverseCallGraphNode*> {
  using NodeType = const clang::ReverseCallGraphNode;
  using NodeRef = const clang::ReverseCallGraphNode *;
  using ChildIteratorType = NodeType::const_iterator;

  static NodeType *getEntryNode(const clang::ReverseCallGraphNode *CGN) { return CGN; }
  static ChildIteratorType child_begin(NodeType *N) { return N->begin();}
  static ChildIteratorType child_end(NodeType *N) { return N->end(); }
};

template <> struct GraphTraits<clang::ReverseCallGraph*>
  : public GraphTraits<clang::ReverseCallGraphNode*> {
  static NodeType *getEntryNode(clang::ReverseCallGraph *CGN) {
    return CGN->getRoot();  // Start at the external node!
  }

  static clang::ReverseCallGraphNode *
  CGGetValue(clang::ReverseCallGraph::const_iterator::value_type &P) {
    return P.second.get();
  }

  // nodes_iterator/begin/end - Allow iteration over all nodes in the graph
  using nodes_iterator =
      mapped_iterator<clang::ReverseCallGraph::iterator, decltype(&CGGetValue)>;

  static nodes_iterator nodes_begin(clang::ReverseCallGraph *CG) {
    return nodes_iterator(CG->begin(), &CGGetValue);
  }

  static nodes_iterator nodes_end  (clang::ReverseCallGraph *CG) {
    return nodes_iterator(CG->end(), &CGGetValue);
  }

  static unsigned size(clang::ReverseCallGraph *CG) { return CG->size(); }
};

template <> struct GraphTraits<const clang::ReverseCallGraph*> :
  public GraphTraits<const clang::ReverseCallGraphNode*> {
  static NodeType *getEntryNode(const clang::ReverseCallGraph *CGN) {
    return CGN->getRoot();
  }

  static clang::ReverseCallGraphNode *
  CGGetValue(clang::ReverseCallGraph::const_iterator::value_type &P) {
    return P.second.get();
  }

  // nodes_iterator/begin/end - Allow iteration over all nodes in the graph
  using nodes_iterator =
      mapped_iterator<clang::ReverseCallGraph::const_iterator, decltype(&CGGetValue)>;

  static nodes_iterator nodes_begin(const clang::ReverseCallGraph *CG) {
    return nodes_iterator(CG->begin(), &CGGetValue);
  }

  static nodes_iterator nodes_end(const clang::ReverseCallGraph *CG) {
    return nodes_iterator(CG->end(), &CGGetValue);
  }

  static unsigned size(const clang::ReverseCallGraph *CG) { return CG->size(); }
};

} // namespace llvm

#endif // LLVM_CLANG_ANALYSIS_REVERSE_CALLGRAPH_H
