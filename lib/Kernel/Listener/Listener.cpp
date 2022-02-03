//
// Created by yuhao on 2/2/22.
//

#include "Listener.h"

kuc::Listener::Listener(klee::Executor *executor) {
    this->kind = listener_kind::default_listener;
    this->executor = executor;
}

kuc::Listener::~Listener() = default;
