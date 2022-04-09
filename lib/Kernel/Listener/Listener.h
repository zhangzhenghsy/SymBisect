//
// Created by yuhao on 2/2/22.
//

#ifndef KLEE_LISTENER_H
#define KLEE_LISTENER_H

#include "../../Core/ExecutionState.h"

namespace klee {
    class Executor;
}

namespace kuc {
    enum listener_kind {
        default_listener,
    };

    class Listener {
    public:
        listener_kind kind;
        klee::Executor *executor{};
    public:
        explicit Listener(klee::Executor *executor);
        virtual ~Listener();

        virtual void beforeRun(klee::ExecutionState &state) = 0;
        virtual void beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) = 0;
        virtual void afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) = 0;
        virtual void afterRun(klee::ExecutionState &state) = 0;
        virtual bool CallInstruction(klee::ExecutionState &state, klee::KInstruction *ki) = 0;
        virtual void executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) = 0;
    };
}


#endif //KLEE_LISTENER_H
