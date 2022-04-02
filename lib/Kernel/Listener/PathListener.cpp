//
// Created by yuhao on 2/3/22.
//

#include "PathListener.h"
#include "../ToolLib/log.h"
#include "../ToolLib/llvm_related.h"
#include "../../Core/Executor.h"

#include "../MLTA/TypeInitializer.hh"
#include "../MLTA/CallGraph.hh"

#include "klee/Support/ErrorHandling.h"


kuc::PathListener::PathListener(klee::Executor *executor) : Listener(executor) {
    config = executor->config;
    if (config.contains("10_target_bb_list") && config["10_target_bb_list"].is_array()) {
        for (const auto &temp: config["10_target_bb_list"]) {
            target_bbs.insert(temp.get<std::string>());
        }
    }
    if (config.contains("11_low_priority_bb_list") && config["11_low_priority_bb_list"].is_array()) {
        for (const auto &temp: config["11_low_priority_bb_list"]) {
            low_priority_bbs.insert(temp.get<std::string>());
        }
    }
    if (config.contains("12_low_priority_function_list") && config["12_low_priority_function_list"].is_array()) {
        for (const auto &temp: config["12_low_priority_function_list"]) {
            low_priority_functions.insert(temp.get<std::string>());
        }
    }
    if (config.contains("13_low_priority_line_list") && config["13_low_priority_line_list"].is_array()) {
        for (const auto &temp: config["13_low_priority_line_list"]) {
            low_priority_lines.insert(temp.get<std::string>());
        }
    }

    // for MLTA indirect function call
    auto MName = this->executor->get_module()->getName();
    GlobalCtx.Modules.push_back(make_pair(this->executor->get_module(), MName));
    GlobalCtx.ModuleMaps[this->executor->get_module()] = this->executor->get_module()->getName();
    // Initialize global type map
    TypeInitializerPass TIPass(&GlobalCtx);
    TIPass.run(GlobalCtx.Modules);
    TIPass.BuildTypeStructMap();
    // Build global call graph.
    CallGraphPass CGPass(&GlobalCtx);
    CGPass.run(GlobalCtx.Modules);
}

kuc::PathListener::~PathListener() = default;

void kuc::PathListener::beforeRun(klee::ExecutionState &initialState) {

}

void kuc::PathListener::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {

    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::Call: {
            if (isa<DbgInfoIntrinsic>(ki->inst))
                break;

            auto *ci = llvm::cast<llvm::CallInst>(ki->inst);
            Value *fp = ci->getCalledOperand();
            if (isa<InlineAsm>(fp)) {
                break;
            }
            Function *f = this->executor->getTargetFunction(fp, state);
            if (f) {
                break;
            }

            // pick function form function_map(json) or GlobalCtx(MLTA)
            std::set<llvm::Function *> callee_function_set;
            if (this->function_map.find(ci) != this->function_map.end()) {
                for (auto temp_f: this->function_map[ci]) {
                    callee_function_set.insert(temp_f);
                }
            } else {
                auto callee = GlobalCtx.Callees[ci];
                for (auto temp_f: callee) {
                    callee_function_set.insert(temp_f);
                }
            }

            // get function address
            std::set<klee::ref<klee::Expr>> callee_function_address;
            for (auto temp_f: callee_function_set) {
                callee_function_address.insert(klee::Expr::createPointer(reinterpret_cast<std::uint64_t>(&temp_f)));
            }

            if (callee_function_address.empty()) {

            } else {
                // encode function
                auto v = klee::ConstantExpr::create(0, 1);
                for (const auto &temp_address: callee_function_address) {
                    auto name = temp_call_cond_name + std::to_string(temp_call_cond_count++);
                    klee::ref<klee::Expr> temp_symbolic_cond = klee::Executor::manual_make_symbolic(name, 1, 8);
                    v = klee::SelectExpr::create(temp_symbolic_cond, temp_address, v);
                }
                executor->un_eval(ki, 0, state).value = v;
            }
            break;
        }
    }
}

void kuc::PathListener::afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    auto bb = ki->inst->getParent();
    auto name_bb = bb->getName().str();
    if (target_bbs.find(name_bb) != target_bbs.end()) {
        this->executor->haltExecution = true;
    }
    // for low_priority_bbs
    if (low_priority_bbs.find(name_bb) != low_priority_bbs.end()) {
        this->executor->terminateState(state);
    }
    // for low_priority_functions
    auto name_f = get_real_function_name(bb->getParent());
    if (low_priority_functions.find(name_f) != low_priority_functions.end()) {
        this->executor->terminateState(state);
    }
    auto name_l = dump_inst_sourceinfo(ki->inst);
    if (low_priority_lines.find(name_l) != low_priority_lines.end()) {
        klee::klee_message("reach low priority line list");
        this->executor->terminateState(state);
    }
}

void kuc::PathListener::afterRun(klee::ExecutionState &state) {

}

void kuc::PathListener::executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) {

}