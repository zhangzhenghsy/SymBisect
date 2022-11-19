//
// Created by yuhao on 2/3/22.
//

#ifndef KLEE_UCLISTENER_H
#define KLEE_UCLISTENER_H

#include "Listener.h"
#include "../ToolLib/json.hpp"

namespace kuc {
    class UCListener : public Listener {
    public:
        explicit UCListener(klee::Executor *executor);

        ~UCListener() override;

        void beforeRun(klee::ExecutionState &initialState) override;

        void beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void afterRun(klee::ExecutionState &state) override;

        bool CallInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) override;

        bool skip_calltrace_distance(klee::ExecutionState &state, klee::KInstruction *ki);

        // count for global var name
        std::map<std::string, int64_t> count;
        // symbolic address <-> mo->getBaseExpr()
        std::map<klee::ref<klee::Expr>, klee::ref<klee::Expr>> map_symbolic_address;
        // mo->getBaseExpr() <-> symbolic address
        std::map<klee::ref<klee::Expr>, klee::ref<klee::Expr>> map_address_symbolic;

        nlohmann::json config;
        std::set<std::string> skip_functions;
        bool print_inst;
        std::map<std::string, std::string> indirectcall_map;
        std::string kernelversion;
        std::map<std::string,std::map<std::string, uint64_t>> concolic_map;
        std::vector<std::string> Calltrace;
        bool skip_calltrace;

    private:
        std::string create_global_var_name(klee::KInstruction *ki, int64_t index, std::string kind);

        void symbolic_before_load(klee::ExecutionState &state, klee::KInstruction *ki);

        void symbolic_before_store(klee::ExecutionState &state, klee::KInstruction *ki);

        void symbolic_after_load(klee::ExecutionState &state, klee::KInstruction *ki);

        void symbolic_after_call(klee::ExecutionState &state, klee::KInstruction *ki);

        static std::string get_name(klee::ref<klee::Expr> value);

        void resolve_symbolic_expr(const klee::ref<klee::Expr> &symbolicExpr,
                                   std::set<std::string> &relatedSymbolicExpr);

        //added by zheng
        void symbolize_Inst_return(klee::ExecutionState &state, klee::KInstruction *ki);
    };
}


#endif //KLEE_UCLISTENER_H
