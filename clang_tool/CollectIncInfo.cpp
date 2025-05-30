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
#include <fstream>
#include <iostream>
#include <llvm/ADT/DenseSet.h>
#include <llvm/ADT/StringRef.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/Error.h>
#include <llvm/Support/JSON.h>
#include <llvm/Support/Timer.h>
#include <llvm/Support/raw_ostream.h>
#include <memory>
#include <ostream>
#include <string>

#include "llvm/Support/CommandLine.h"
#include <clang/Analysis/AnalysisDeclContext.h>
#include <clang/Frontend/CompilerInstance.h>
#include <clang/Frontend/FrontendAction.h>
#include <clang/Index/USRGeneration.h>
#include <clang/Tooling/CommonOptionsParser.h>
#include <clang/Tooling/Tooling.h>
#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/Support/raw_ostream.h>

#include "IncInfoCollectASTVisitor.h"
#include "ReverseCallGraph.h"

using namespace clang;
using namespace clang::tooling;

void DisplayTime(llvm::TimeRecord &Time) {
  llvm::errs() << " : " << llvm::format("%1.1f", Time.getWallTime() * 1000)
               << " ms\n";
}

class IncInfoCollectConsumer : public clang::ASTConsumer {
public:
  explicit IncInfoCollectConsumer(CompilerInstance &CI, std::string &diffPath,
                                  const IncOptions &incOpt)
      : Context(CI.getASTContext()), CG(), IncOpt(incOpt),
        DLM(CI.getASTContext().getSourceManager()), PP(CI.getPreprocessor()),
        SM(CI.getASTContext().getSourceManager()),
        IncVisitor(&CI.getASTContext(), DLM, CG, FunctionsChanged, AffectedVFs,
                   AN, IncOpt) {
    std::unique_ptr<llvm::Timer> consumerTimer = std::make_unique<llvm::Timer>(
        "Consumer Timer", "Consumer Constructor Time");
    consumerTimer->startTimer();
    llvm::TimeRecord consumerStart = consumerTimer->getTotalTime();

    FileID MainFileID = SM.getMainFileID();
    const FileEntry *FE = SM.getFileEntryForID(MainFileID);
    MainFilePath = FE->tryGetRealPathName();
    DLM.Initialize(diffPath, MainFilePath.str());
    // Don't print location information.
    auto PrintPolicy = Context.getPrintingPolicy();
    PrintPolicy.TerseOutput = false;
    PrintPolicy.SuppressInlineNamespace = false;
    PrintPolicy.UseVoidForZeroParams = false;
    Context.setPrintingPolicy(PrintPolicy);

    consumerTimer->stopTimer();
    llvm::TimeRecord consumerStop = consumerTimer->getTotalTime();
    consumerStop -= consumerStart;
    llvm::errs() << "Consumer Time:";
    DisplayTime(consumerStop);
  }

  bool HandleTopLevelDecl(DeclGroupRef DG) override {
    storeTopLevelDecls(DG);
    return true;
  }

  void HandleTopLevelDeclInObjCContainer(DeclGroupRef DG) override {
    storeTopLevelDecls(DG);
  }

  void storeTopLevelDecls(DeclGroupRef DG) {
    for (auto &I : DG) {
      // Skip ObjCMethodDecl, wait for the objc container to avoid
      // analyzing twice.
      if (isa<ObjCMethodDecl>(I))
        continue;
      LocalTUDecls.push_back(I);
    }
  }

  void HandleTranslationUnit(clang::ASTContext &Context) override {
    std::unique_ptr<llvm::Timer> toolTimer =
        std::make_unique<llvm::Timer>("tu timer", "TU analysis time");
    toolTimer->startTimer();
    llvm::TimeRecord toolStart = toolTimer->getTotalTime();
    // Don't run the actions if an error has occurred with parsing the file.
    DiagnosticsEngine &Diags = PP.getDiagnostics();
    if (Diags.hasErrorOccurred() || Diags.hasFatalErrorOccurred())
      return;

    if (DLM.isNoChange()) {
      // If there is no change in this file, just use old call graph.
      // DO NOTHING.
      llvm::errs() << DLM.MainFilePath << " has no change, do nothing.\n";
      DumpIncSummary(0);
      return;
    }

    if (DLM.isNewFile()) {
      // If this is a new file, we just output its callgraph.
      DumpIncSummary(1);
      llvm::errs() << DLM.MainFilePath
                   << " is new, do not analyze changed functions.\n";
      return;
    }

    // Same as CSA, we just consider initialzed local decl, ignore
    // addition declarations from pch deserialization.
    const unsigned LocalTUDeclsSize = LocalTUDecls.size();
    for (int i = 0; i < LocalTUDeclsSize; i++) {
      auto D = LocalTUDecls[i];
      CG.addToReverseCallGraph(D);
    }
    DumpCallGraph();

    toolTimer->stopTimer();
    llvm::errs() << "Prepare CG ";
    llvm::TimeRecord toolPrepare = toolTimer->getTotalTime();
    toolPrepare -= toolStart;
    DisplayTime(toolPrepare);
    toolTimer->startTimer();

    // Find changed functions on the call graph.
    llvm::ReversePostOrderTraversal<clang::ReverseCallGraph *> RPOT(&CG);
    SourceManager &SM = Context.getSourceManager();
    for (ReverseCallGraphNode *N : RPOT) {
      if (N == CG.getRoot())
        continue;
      Decl *D = N->getDecl();
      // CG only record canonical decls, so it's neccessary to
      // judge if there are changes in Function Definition scope.
      if (DLM.isChangedDecl(D)) {
        FunctionsChanged.insert(D);
        if (auto MD = llvm::dyn_cast<CXXMethodDecl>(D)) {
          if (MD->isVirtual()) {
            // Record changed virtual function and all functions it overrides.
            AffectedVFs.insert(D);
            for (auto method : MD->overridden_methods()) {
              AffectedVFs.insert(method);
            }
          }
        }
      }
    }

    // Consider other factors on AST which make functions need to reanalyze.
    IncVisitor.TraverseDecl(Context.getTranslationUnitDecl());

    // Propogate the reanalyze flag on call graph.
    Propogate();

    // Output the result.
    IncVisitor.DumpGlobalConstantSet();
    IncVisitor.DumpTaintDecls();
    DumpFunctionsNeedReanalyze();

    toolTimer->stopTimer();
    llvm::TimeRecord toolEnd = toolTimer->getTotalTime();
    toolEnd -= toolPrepare;
    llvm::errs() << "Analysis CF ";
    DisplayTime(toolEnd);

    DumpIncSummary(2);
    DumpAffectedNodesRanges();
    DumpFunctionsNeedReanalyzeForCppcheck();
    DumpFunctionsNeedReanalyzeForGCC();
  }

  void Propogate() {
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

  static void getUSRName(const Decl *D, std::string &Str) {
    // Don't use this function if don't need USR representation
    // to avoid redundant string copy.
    D = D->getCanonicalDecl();
    SmallString<128> usr;
    index::generateUSRForDecl(D, usr);
    Str = std::to_string(usr.size());
    Str += ":";
    Str += usr.c_str();
  }

  void DumpCallGraph() {
    if (!IncOpt.DumpCG) {
      return;
    }
    std::ostream *OS = &std::cout;
    // `outFile`'s life time should persist until dump finished.
    // And don't create file if don't need to dump to file.
    std::shared_ptr<std::ofstream> outFile;
    if (IncOpt.DumpToFile) {
      std::string CGFile = MainFilePath.str() + ".cg";
      outFile = std::make_shared<std::ofstream>(CGFile);
      if (!outFile->is_open()) {
        llvm::errs() << "Error: Could not open file " << CGFile
                     << " for writing.\n";
        return;
      }
      OS = outFile.get();
    } else {
      *OS << "--- Call Graph ---\n";
    }

    llvm::ReversePostOrderTraversal<clang::ReverseCallGraph *> RPOT(&CG);
    for (ReverseCallGraphNode *N : RPOT) {
      if (N == CG.getRoot())
        continue;
      Decl *D = N->getDecl();
      if (IncOpt.DumpUSR) {
        std::string ret;
        getUSRName(D, ret);
        *OS << ret;
      } else {
        *OS << AnalysisDeclContext::getFunctionName(D->getCanonicalDecl());
      }
      if (IncOpt.PrintLoc) {
        auto loc = DLM.StartAndEndLineOfDecl(D);
        if (!loc)
          continue;
        auto StartLoc = loc->first;
        auto EndLoc = loc->second;
        *OS << " -> " << StartLoc << ", " << EndLoc;
      }
      *OS << "\n[\n";
      SetOfConstDecls CalleeSet;
      for (ReverseCallGraphNode *CR : N->callers()) {
        Decl *Callee = CR->getDecl();
        if (CalleeSet.contains(Callee))
          continue;
        CalleeSet.insert(Callee);
        if (IncOpt.DumpUSR) {
          std::string ret;
          getUSRName(Callee, ret);
          *OS << ret;
        } else {
          *OS << AnalysisDeclContext::getFunctionName(
              Callee->getCanonicalDecl());
        }
        if (IncOpt.PrintLoc) {
          auto loc = DLM.StartAndEndLineOfDecl(Callee);
          if (!loc)
            continue;
          auto StartLoc = loc->first;
          auto EndLoc = loc->second;
          *OS << " -> " << StartLoc << "-" << EndLoc;
        }
        *OS << "\n";
      }
      *OS << "]\n";
    }
    (*OS).flush();
    if (IncOpt.DumpToFile)
      outFile->close();
  }

  void DumpFunctionsNeedReanalyze() {
    if (FunctionsNeedReanalyze.empty()) {
      return;
    }
    std::ostream *OS = &std::cout;
    std::shared_ptr<std::ofstream> outFile;
    if (IncOpt.DumpToFile) {
      std::string ReanalyzeFunctionsFile = MainFilePath.str() + ".rf";
      if (!IncOpt.RFPath.empty()) {
        ReanalyzeFunctionsFile = IncOpt.RFPath;
      }
      outFile = std::make_shared<std::ofstream>(ReanalyzeFunctionsFile);
      if (!outFile->is_open()) {
        llvm::errs() << "Error: Could not open file " << ReanalyzeFunctionsFile
                     << " for writing.\n";
        return;
      }
      OS = outFile.get();
    } else {
      *OS << "--- Functions Need to Reanalyze ---\n";
    }

    for (auto &D : FunctionsNeedReanalyze) {
      if (IncOpt.DumpUSR) {
        std::string ret;
        getUSRName(D, ret);
        *OS << ret;
      } else {
        *OS << AnalysisDeclContext::getFunctionName(D->getCanonicalDecl());
      }
      if (IncOpt.PrintLoc) {
        auto loc = DLM.StartAndEndLineOfDecl(D);
        if (!loc)
          continue;
        auto StartLoc = loc->first;
        auto EndLoc = loc->second;
        *OS << " -> " << StartLoc << "-" << EndLoc;
      }
      *OS << "\n";
    }
    (*OS).flush();
    if (IncOpt.DumpToFile)
      outFile->close();
  }

  void DumpFunctionsNeedReanalyzeForCppcheck() {
    /*
        filename.c:
        func
        ...
    */
    if (IncOpt.CppcheckRFPath.empty()) {
      return;
    }
    std::ofstream outFile;
    std::string ReanalyzeFunctionsFile = IncOpt.CppcheckRFPath;
    outFile = std::ofstream(ReanalyzeFunctionsFile);
    if (!outFile.is_open()) {
      llvm::errs() << "Error: Could not open file " << ReanalyzeFunctionsFile
                   << " for writing.\n";
      return;
    }

    outFile << IncOpt.FilePath << ":\n";

    for (auto &D : FunctionsNeedReanalyze) {
      if (auto *FD = llvm::dyn_cast<FunctionDecl>(D->getCanonicalDecl())) {
        // Cppcheck use raw name.
        outFile << FD->getNameAsString();
        outFile << "\n";
      }
    }
    (outFile).flush();
    outFile.close();
  }

  void DumpFunctionsNeedReanalyzeForGCC() {
    if (IncOpt.GCCRFPath.empty()) {
      return;
    }
    std::ofstream outFile;
    std::string ReanalyzeFunctionsFile = IncOpt.GCCRFPath;
    outFile = std::ofstream(ReanalyzeFunctionsFile);
    if (!outFile.is_open()) {
      llvm::errs() << "Error: Could not open file " << ReanalyzeFunctionsFile
                   << " for writing.\n";
      return;
    }

    for (auto &D : FunctionsNeedReanalyze) {
      if (auto *FD = llvm::dyn_cast<FunctionDecl>(D->getCanonicalDecl())) {
        std::string Str;
        llvm::raw_string_ostream SOS(Str);
        auto PrintPolicy = Context.getPrintingPolicy();
        FD->printQualifiedName(SOS, PrintPolicy);

        SOS << '(';
        // Only match paramter numbers.
        SOS << FD->getNumParams();
        SOS << ')';
        
        if (!Str.empty()) {
          outFile << Str;
          outFile << "\n";
        }
      }
    }
    (outFile).flush();
    outFile.close();
  }

  void DumpAffectedNodesRanges() {
    if (!IncOpt.DumpANR) {
      return;
    }
    std::ostream *OS = &std::cout;
    std::shared_ptr<std::ofstream> outFile;
    if (IncOpt.DumpToFile) {
      std::string ANRFile = MainFilePath.str() + ".anr";
      outFile = std::make_shared<std::ofstream>(ANRFile);
      if (!outFile->is_open()) {
        llvm::errs() << "Error: Could not open file " << ANRFile
                     << " for writing.\n";
        return;
      }
      OS = outFile.get();
    } else {
      *OS << "--- Affected node ranges ---\n";
    }

    AN.insert(IncVisitor.TaintDecls.begin(), IncVisitor.TaintDecls.end());
    // All Decls in FunctionsChanged are canonical decl.
    // Record correspond definition (if exist) in AN.
    for (auto *D : FunctionsChanged) {
      if (auto *FD = llvm::dyn_cast<FunctionDecl>(D)) {
        auto *Definition = FD->getDefinition();
        if (Definition) {
          AN.insert(Definition);
        }
      }
    }

    std::map<std::string, std::set<std::pair<unsigned, unsigned>>> FileToRange;
    for (auto D : AN) {
      auto Loc = D->getLocation();
      if (!Loc.isValid() || SM.isInSystemHeader(Loc))
        continue;
      auto FileAndLine = DLM.OriginFilenameAndLineNumberOfDecl(D);
      if (!FileAndLine)
        continue;
      auto filename = FileAndLine->first;
      auto loc = FileAndLine->second;
      if (FileToRange.count(filename))
        FileToRange[filename].insert(loc);
      else
        FileToRange[filename] = {loc};
    }

    for (auto item : FileToRange) {
      auto filename = item.first;
      *OS << filename << ":\n";
      auto RangeSet = item.second;
      for (const auto &Range : RangeSet) {
        *OS << Range.first << "," << Range.second << ";";
      }
      *OS << "\n";
    }

    (*OS).flush();
    if (IncOpt.DumpToFile)
      outFile->close();
  }

  void DumpIncSummary(int mode) {
    std::ostream *OS = &std::cout;
    std::shared_ptr<std::ofstream> outFile;
    if (IncOpt.DumpToFile) {
      std::string IncSummaryFile = MainFilePath.str() + ".ics";
      outFile = std::make_shared<std::ofstream>(IncSummaryFile);
      if (!outFile->is_open()) {
        llvm::errs() << "Error: Could not open file " << IncSummaryFile
                     << " for writing.\n";
        return;
      }
      OS = outFile.get();
    } else {
      *OS << "--- Inc Summary ---\n";
    }

    if (mode == 0) {
      // no change
    } else if (mode == 1) {
      // new file
      *OS << "new file\n";
    } else {
      *OS << "changed functions" << ":" << FunctionsChanged.size() << "\n";
      *OS << "reanalyze functions" << ":" << FunctionsNeedReanalyze.size()
          << "\n";
      *OS << "cg nodes" << ":" << CG.size() - 1 << "\n";
      *OS << "affected virtual functions" << ":" << AffectedVFs.size() << "\n";
      *OS << "affected vf indirect calls" << ":"
          << IncVisitor.AffectedIndirectCallByVF << "\n";
      *OS << "function pointer types" << ":"
          << IncVisitor.TypesMayUsedByFP.size() << "\n";
      *OS << "affected fp indirect calls" << ":"
          << IncVisitor.AffectedIndirectCallByFP << "\n";
    }

    (*OS).flush();
    if (IncOpt.DumpToFile)
      outFile->close();
  }

private:
  ASTContext &Context;
  const IncOptions &IncOpt;
  llvm::StringRef MainFilePath;
  DiffLineManager DLM;
  ReverseCallGraph CG;
  IncInfoCollectASTVisitor IncVisitor;
  std::deque<Decl *> LocalTUDecls;
  llvm::DenseSet<const Decl *> FunctionsChanged;
  llvm::DenseSet<const Decl *> AffectedVFs;
  std::vector<const Decl *> FunctionsNeedReanalyze;
  llvm::DenseSet<const Decl *> AN;
  Preprocessor &PP;
  const clang::SourceManager &SM;
};

class IncInfoCollectAction : public clang::ASTFrontendAction {
public:
  IncInfoCollectAction(std::string &diffPath, std::string &fsPath,
                       const IncOptions &incOpt)
      : DiffPath(diffPath), FSPath(fsPath), IncOpt(incOpt) {}

  std::unique_ptr<clang::ASTConsumer>
  CreateASTConsumer(clang::CompilerInstance &CI,
                    llvm::StringRef file) override {
    return std::make_unique<IncInfoCollectConsumer>(CI, DiffPath, IncOpt);
  }

private:
  std::string &DiffPath;
  std::string &FSPath;
  const IncOptions &IncOpt;
};

class IncInfoCollectActionFactory : public FrontendActionFactory {
public:
  IncInfoCollectActionFactory(std::string &diffPath, std::string &fsPath,
                              const IncOptions &incOpt)
      : DiffPath(diffPath), FSPath(fsPath), IncOpt(incOpt) {}

  std::unique_ptr<FrontendAction> create() override {
    return std::make_unique<IncInfoCollectAction>(DiffPath, FSPath, IncOpt);
  }

private:
  std::string &DiffPath;
  std::string &FSPath;
  const IncOptions &IncOpt;
};

static llvm::cl::OptionCategory ToolCategory("Collect Inc Info Options");
static llvm::cl::opt<std::string>
    DiffPath("diff", llvm::cl::desc("Specify diff info files"),
             llvm::cl::value_desc("diff info files"), llvm::cl::init(""));
static llvm::cl::opt<std::string>
    FSPath("fs-file",
           llvm::cl::desc("Function summary files, use under inline mode"),
           llvm::cl::value_desc("function summary files"), llvm::cl::init(""));
static llvm::cl::opt<bool> PrintLoc(
    "loc", llvm::cl::desc("Print location information in FunctionName or not"),
    llvm::cl::value_desc("AnonymousTagLocations"), llvm::cl::init(false));
static llvm::cl::opt<bool>
    ClassLevel("class", llvm::cl::desc("Propogate type change by class level"),
               llvm::cl::value_desc("class level change"),
               llvm::cl::init(true));
static llvm::cl::opt<bool>
    FieldLevel("field", llvm::cl::desc("Propogate type change by field level"),
               llvm::cl::value_desc("field level change"),
               llvm::cl::init(false));
static llvm::cl::opt<bool> DumpCG("dump-cg", llvm::cl::desc("Dump CG or not"),
                                  llvm::cl::value_desc("dump cg"),
                                  llvm::cl::init(false));
static llvm::cl::opt<bool>
    DumpToFile("dump-file", llvm::cl::desc("Dump CG and CF to file"),
               llvm::cl::value_desc("dump to file or stream"),
               llvm::cl::init(true));
static llvm::cl::opt<bool> DumpUSR("dump-usr",
                                   llvm::cl::desc("Dump USR function name"),
                                   llvm::cl::value_desc("dump usr fname"),
                                   llvm::cl::init(false));
static llvm::cl::opt<bool>
    DumpANR("dump-anr", llvm::cl::desc("Dump affected nodes line ranges"),
            llvm::cl::value_desc("dump ANR"), llvm::cl::init(false));
static llvm::cl::opt<bool> CTU("ctu", llvm::cl::desc("Consider CTU analysis"),
                               llvm::cl::value_desc("consider CTU analysis"),
                               llvm::cl::init(false));
static llvm::cl::opt<std::string>
    RFPath("rf-file", llvm::cl::desc("Output RF to the path"),
           llvm::cl::value_desc("dump rf file"), llvm::cl::init(""));
static llvm::cl::opt<std::string> CppcheckRFPath(
    "cppcheck-rf-file", llvm::cl::desc("Output Cppcheck RF to the path"),
    llvm::cl::value_desc("dump cppcheck rf file"), llvm::cl::init(""));
static llvm::cl::opt<std::string>
    GCCRFPath("gcc-rf-file", llvm::cl::desc("Output GCC RF to the path"),
              llvm::cl::value_desc("dump gcc rf file"), llvm::cl::init(""));
static llvm::cl::opt<std::string>
    FilePath("file-path", llvm::cl::desc("File path before preprocess"),
             llvm::cl::value_desc("origin file"), llvm::cl::init(""));

int main(int argc, const char **argv) {
  std::unique_ptr<llvm::Timer> toolTimer =
      std::make_unique<llvm::Timer>("tool timer", "tool analysis time");
  toolTimer->startTimer();
  llvm::TimeRecord toolStart = toolTimer->getTotalTime();

  auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCategory);
  if (!ExpectedParser) {
    // Fail gracefully for unsupported options.
    llvm::errs() << ExpectedParser.takeError();
    return 1;
  }
  CommonOptionsParser &OptionsParser = ExpectedParser.get();

  ClangTool Tool(OptionsParser.getCompilations(),
                 OptionsParser.getSourcePathList());
  IncOptions IncOpt{.PrintLoc = PrintLoc,
                    .ClassLevelTypeChange = ClassLevel,
                    .FieldLevelTypeChange = FieldLevel,
                    .DumpCG = DumpCG,
                    .DumpToFile = DumpToFile,
                    .DumpUSR = DumpUSR,
                    .DumpANR = DumpANR,
                    .CTU = CTU,
                    .RFPath = RFPath,
                    .CppcheckRFPath = CppcheckRFPath,
                    .GCCRFPath = GCCRFPath,
                    .FilePath = FilePath};
  IncInfoCollectActionFactory Factory(DiffPath, FSPath, IncOpt);

  toolTimer->stopTimer();
  llvm::TimeRecord toolPrepare = toolTimer->getTotalTime();
  toolPrepare -= toolStart;
  llvm::errs() << "Tool Prepare ";
  DisplayTime(toolPrepare);
  toolTimer->startTimer();

  auto ret = Tool.run(&Factory);

  toolTimer->stopTimer();
  llvm::TimeRecord toolStop = toolTimer->getTotalTime();
  toolStop -= toolStart;
  llvm::errs() << "Tool Stop ";
  DisplayTime(toolStop);

  return ret;
}