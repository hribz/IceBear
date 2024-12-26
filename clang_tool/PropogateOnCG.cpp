#include "PropogateOnCG.h"

PropogateOnCG::PropogateOnCG(ReverseCallGraph &cg,
                             std::unordered_set<const Decl *> &rf_set)
    : CG(cg), FunctionsNeedReanalyze(rf_set) {}

void PropogateOnCG::Propogate() {
    
}