#include "PropogateOnCG.h"
#include <llvm/ADT/SmallVector.h>
#include <vector>

PropogateOnCG::PropogateOnCG(ReverseCallGraph &CG, std::unordered_set<const Decl *> &CF, std::vector<const Decl *> &RF)
    : CG(CG), FunctionsChanged(CF), FunctionsNeedReanalyze(RF) {}

void PropogateOnCG::Propogate() {
    for (auto &decl : FunctionsChanged) {
        ReverseCallGraphNode *node_from_cf = CG.getNode(decl);
        auto worklist = std::vector<ReverseCallGraphNode *>({node_from_cf});
        while (!worklist.empty()) {
            auto node = worklist.back();
            worklist.pop_back();
            if (node->needsReanalyze()) {
                continue;
            }
            node->markAsReanalyze();
            FunctionsNeedReanalyze.push_back(node->getDecl());
            for (auto &caller : node->callers()) {
                worklist.push_back(caller);
            }
        }
    }
}