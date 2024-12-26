#ifndef PROPOGATE_ON_CG_H
#define PROPOGATE_ON_CG_H

#include <unordered_set>
#include "ReverseCallGraph.h"

using namespace clang;

class PropogateOnCG {
public:
    PropogateOnCG(ReverseCallGraph &, std::unordered_set<const Decl *> &, std::vector<const Decl *> &);

    void Propogate();

private:
    ReverseCallGraph &CG;
    std::unordered_set<const Decl *> &FunctionsChanged;
    std::vector<const Decl *> &FunctionsNeedReanalyze;
};

#endif // PROPOGATE_ON_CG_H