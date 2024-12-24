#ifndef PROPOGATE_ON_CG_H
#define PROPOGATE_ON_CG_H

#include <unordered_set>
#include <string>

#include "clang/Analysis/CallGraph.h"

using namespace clang;

class PropogateOnCG {
public:
    PropogateOnCG(CallGraph &, std::unordered_set<const Decl *> &);

    void Propogate();

private:
    CallGraph &CG;
    std::unordered_set<const Decl *> &FunctionsNeedReanalyze;
};

#endif // PROPOGATE_ON_CG_H