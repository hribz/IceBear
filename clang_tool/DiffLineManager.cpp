#include "DiffLineManager.h"
#include <utility>
#include <vector>

void DiffLineManager::Initialize(std::string &DiffPath, std::string mainFilePath) {
    MainFilePath = mainFilePath;

    if (DiffPath.empty()) {
        llvm::errs() << "No diff lines information.\n";
        return ;
    }
    std::ifstream file(DiffPath);
    if (!file.is_open()) {
        llvm::errs() << "Failed to open " << DiffPath << ".\n";
        return ;
    }

    std::string line;
    DiffLines = std::vector<std::pair<int, int>>();
    while (std::getline(file, line)) {
        if (line == "new") {
            DiffLines = std::nullopt;
            llvm::outs() << MainFilePath << " is new file.\n";
            break;
        }
        if (line.empty()) {
            continue;
        }

        int x1, y1, line_start, line_count;
        char leftParen, rightParen, space;
        if (std::sscanf(line.c_str(), "%d,%d %d,%d", &x1, &y1, &line_start, &line_count) != 4) {
            llvm::errs() << "Error parsing line: " << line << "";
        } else {
            auto pair = std::make_pair(line_start, line_count);
            DiffLines->push_back(pair);
        }
    }
    file.close();
}

std::optional<std::pair<int, int>> DiffLineManager::StartAndEndLineOfDecl(const Decl *D) {
    if (auto FD = D->getAsFunction()) {
        // Just care about changes in function definition
        if (auto Definition = FD->getDefinition())
            D = FD->getDefinition();
    }
    
    SourceLocation Loc = D->getLocation();
    if (!(Loc.isValid() && Loc.isFileID())) {
        return std::nullopt;
    }
    auto StartLoc = SM.getExpansionLineNumber(D->getBeginLoc());
    auto EndLoc = SM.getExpansionLineNumber(D->getEndLoc());
    return std::make_pair(StartLoc, EndLoc);
}

bool DiffLineManager::isChangedLine(unsigned int line, unsigned int end_line) {
    if (!DiffLines) {
        return true;
    }
    if (DiffLines->empty()) {
        return false;
    }
    // 使用 lambda 表达式来定义比较函数
    auto it = std::lower_bound(DiffLines->begin(), DiffLines->end(), std::make_pair(line + 1, 0),
                            [](const std::pair<int, int> &a, const std::pair<int, int> &b) {
                                return a.first < b.first;
                            });
    auto it_begin_and_end = [] (__gnu_cxx::__normal_iterator<const std::pair<int, int> *, std::vector<std::pair<int, int>>> it) {
        auto it_begin = it->first;
        auto it_end = it->first + it->second - 1;
        // it->second 是变化的行数，但是 it->second == 0 并不意味着没有发生变化，而是 it->first 行之后发生了删除
        // 这种情况可以视为 [it->first+1, 1]
        if (!it->second) {
            it_begin = it_end = it->first + 1;
        }
        return std::make_pair(it_begin, it_end);
    };
    // 检查前一个范围（如果存在）是否覆盖了给定的行号
    if (it != DiffLines->begin()) {
        --it;  // 找到最后一个不大于 line 的区间
        auto [it_begin, it_end] = it_begin_and_end(it);
        if (line <= it_end) {
            return true;  // 如果 line 在这个区间内，返回 true
        }
        ++it;
    }

    while (it != DiffLines->end()) {
        auto [it_begin, it_end] = it_begin_and_end(it);
        if (it_begin > end_line) {
            break;  // 当前区间的起始行号大于 EndLine，说明之后都不会有交集
        }
        // 检查是否存在交集
        if (it_begin<= end_line && it_end >= line) {
            return true;  // 存在交集
        }
        ++it;
    }

    return false;  // 如果没有找到，返回 false
}

bool DiffLineManager::isChangedDecl(const Decl *D) {
    auto loc = StartAndEndLineOfDecl(D);
    return loc && isChangedLine(loc->first, loc->second);
}

void DiffLineManager::printJsonObject(const llvm::json::Object &obj) {
    for (const auto &pair : obj) {
        llvm::errs() << pair.first << ": ";
        if (auto str = pair.second.getAsString()) {
            llvm::errs() << *str << "\n";
        } else if (auto num = pair.second.getAsInteger()) {
            llvm::errs() << *num << "\n";
        } else if (auto boolean = pair.second.getAsBoolean()) {
            llvm::errs() << (*boolean ? "true" : "false") << "\n";
        } else if (auto *arr = pair.second.getAsArray()) {
            llvm::errs() << "[";
            for (const auto &elem : *arr) {
                if (auto str = elem.getAsString()) {
                    llvm::errs() << *str << " ";
                } else if (auto i = elem.getAsInteger()) {
                    llvm::errs() << *i << " ";
                }
            }
            llvm::errs() << "]" << "\n";
        } else {
            llvm::errs() << "Unknown type" << "\n";
        }
    }
}

void DiffLineManager::printJsonValue(const llvm::json::Value &jsonValue) {
    if (auto *obj = jsonValue.getAsObject()) {
        printJsonObject(*obj);
    } else {
        llvm::errs() << "Failed to get JSON object" << "\n";
    }
}