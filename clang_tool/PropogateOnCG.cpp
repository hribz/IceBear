#include "PropogateOnCG.h"

PropogateOnCG::PropogateOnCG(CallGraph &cg,
                             std::unordered_set<const Decl *> &rf_set)
    : CG(cg), FunctionsNeedReanalyze(rf_set) {}

void PropogateOnCG::Propogate() {
    
}