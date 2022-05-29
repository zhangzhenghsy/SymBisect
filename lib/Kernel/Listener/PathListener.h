//
// Created by yuhao on 2/3/22.
//

#ifndef KLEE_PATHLISTENER_H
#define KLEE_PATHLISTENER_H

#include "Listener.h"
#include "../ToolLib/json.hpp"
#include "../MLTA/Analyzer.hh"

namespace kuc {
    class PathListener : public Listener {
    public:
        explicit PathListener(klee::Executor *executor);

        ~PathListener() override;

        void beforeRun(klee::ExecutionState &initialState) override;

        void beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void afterRun(klee::ExecutionState &state) override;

        bool CallInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) override;

    public:
        nlohmann::json config;
        std::set<std::string> target_bbs;
        std::set<std::string> low_priority_bbs;
        std::set<std::string> low_priority_functions;
        //added by zheng
        std::set<std::string> low_priority_lines;

        std::string temp_call_cond_name = "temp_call_cond";
        uint64_t temp_call_cond_count = 0;
        // yu hao: todo: read function map from json
        //std::map<llvm::CallInst *, std::set<llvm::Function *>> function_map;
        // zheng: indirect call map
        std::map<std::string, std::string> indirectcall_map;
        std::map<std::string, std::set<std::string>> whitelist_map;
        std::uint32_t looplimit;
        GlobalContext GlobalCtx;
    };
}


#endif //KLEE_PATHLISTENER_H
