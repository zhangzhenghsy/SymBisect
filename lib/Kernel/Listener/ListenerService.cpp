//
// Created by yuhao on 2/2/22.
//

#include "ListenerService.h"
#include "../ToolLib/log.h"
#include "UCListener.h"
#include "PathListener.h"
#include "../../Core/Executor.h"

namespace kuc {
    ListenerService::ListenerService(klee::Executor *executor) {
        yhao_start_log();
        this->executor = executor;
    }

    ListenerService::~ListenerService() = default;

    void ListenerService::pushListener(Listener *listener) {
        listeners.push_back(listener);
    }

    void ListenerService::removeListener(Listener *listener) {
        for (auto it = listeners.begin(), ie = listeners.end(); it != ie; ++it) {
            if ((*it) == listener) {
                listeners.erase(it);
                break;
            }
        }
    }

    void ListenerService::removeListener(listener_kind kind) {
        for (auto it = listeners.begin(), ie = listeners.end(); it != ie; ++it) {
            if ((*it)->kind == kind) {
                listeners.erase(it);
                break;
            }
        }
    }

    Listener *ListenerService::popListener() {
        auto ret = listeners.back();
        listeners.pop_back();
        return ret;
    }

    void ListenerService::beforeRun(klee::ExecutionState &state) {
        for (auto &listener: listeners) {
            listener->beforeRun(state);
        }
    }

    void ListenerService::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
        for (auto &listener: listeners) {
            listener->beforeExecuteInstruction(state, ki);
        }
    }

    void ListenerService::afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
        for (auto es: this->executor->removedStates) {
            if (&state == es) {
                return;
            }
        }
        for (auto &listener: listeners) {
            listener->afterExecuteInstruction(state, ki);
        }
    }

    void ListenerService::afterRun(klee::ExecutionState &state) {
        for (auto &listener: listeners) {
            listener->afterRun(state);
        }
    }

    bool ListenerService::CallInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
        for (auto es: this->executor->removedStates) {
            if (&state == es) {
                return false;
            }
        }
        bool ret = false;
        for (auto &listener: listeners) {
            ret = ret || listener->CallInstruction(state, ki);
        }
        return ret;
    }

    void ListenerService::executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) {
        for (auto &listener: listeners) {
            listener->executionFailed(state, ki);
        }
    }

    void ListenerService::preparation() {
        Listener *temp;
        temp = new UCListener(this->executor);
        this->pushListener(temp);
        temp = new PathListener(this->executor);
        this->pushListener(temp);
    }
}
