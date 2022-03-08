//
// Created by yuhao on 2/3/22.
//

#ifndef KLEE_UCLISTENER_H
#define KLEE_UCLISTENER_H

#include "Listener.h"

namespace kuc {
    class UCListener : public Listener {
    public:
        explicit UCListener(klee::Executor *executor);

        ~UCListener() override;

        void beforeRun(klee::ExecutionState &initialState) override;

        void beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) override;

        void afterRun(klee::ExecutionState &state) override;

        void executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) override;

        // count for global var name
        std::map<std::string, int64_t> count;
        // symbolic address <-> mo->getBaseExpr()
        std::map<klee::ref<klee::Expr>, klee::ref<klee::Expr>> map_symbolic_address;
        // mo->getBaseExpr() <-> symbolic address
        std::map<klee::ref<klee::Expr>, klee::ref<klee::Expr>> map_address_symbolic;

    private:
        std::string create_global_var_name(llvm::Instruction *i, int64_t index, const std::string &kind);

        void symbolic_before_load(klee::ExecutionState &state, klee::KInstruction *ki);

        void symbolic_before_store(klee::ExecutionState &state, klee::KInstruction *ki);

        void symbolic_after_load(klee::ExecutionState &state, klee::KInstruction *ki);

        void symbolic_after_call(klee::ExecutionState &state, klee::KInstruction *ki);

        static std::string get_name(klee::ref<klee::Expr> value);

        void resolve_symbolic_expr(const klee::ref<klee::Expr> &symbolicExpr,
                                   std::set<std::string> &relatedSymbolicExpr);
    };
}


#endif //KLEE_UCLISTENER_H
