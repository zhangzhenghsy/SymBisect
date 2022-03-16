//
// Created by yuhao on 2/3/22.
//

#include "UCListener.h"
#include "../ToolLib/log.h"
#include "../ToolLib/llvm_related.h"
#include "../../Core/Executor.h"
#include "klee/Support/ErrorHandling.h"


kuc::UCListener::UCListener(klee::Executor *executor) : Listener(executor) {

}

kuc::UCListener::~UCListener() = default;

void kuc::UCListener::beforeRun(klee::ExecutionState &initialState) {

}

void kuc::UCListener::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    //yhao_log(1, inst_to_strID(ki->inst));
    //yhao_log(1, dump_inst_booltin(ki->inst));
    yhao_print(ki->inst->print, str)
    klee::klee_message("%s", str.c_str());

    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::GetElementPtr: {
            break;
        }
        case llvm::Instruction::Load: {

            klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;
            yhao_print(base->print, str)
            klee::klee_message("base: %s", str.c_str());

            // yhao: symbolic execution
            this->symbolic_before_load(state, ki);
            break;
        }
        case llvm::Instruction::Store: {

            klee::ref<klee::Expr> value = executor->eval(ki, 0, state).value;
            yhao_print(value->print, str)
            klee::klee_message("value: %s", str.c_str());
            if (value->getKind() != klee::Expr::Constant) {
                klee::klee_message("non-constant store value");
            }
            klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;
            yhao_print(base->print, str)
            klee::klee_message("base: %s", str.c_str());

            // yhao: symbolic execution: this should only happen when pointer in arguments
            this->symbolic_before_store(state, ki);
            break;
        }
        default: {

        }
    }
}

void kuc::UCListener::afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::GetElementPtr: {
            break;
        }
        case llvm::Instruction::Load: {
            yhao_print(executor->getDestCell(state, ki).value->print, str)
            klee::klee_message("value: %s", str.c_str());
            symbolic_after_load(state, ki);
            break;
        }
        case llvm::Instruction::Call: {
            this->symbolic_after_call(state, ki);
            break;
        }
        case llvm::Instruction::BitCast: {
            yhao_print(ki->inst->getType()->print, str)
            klee::klee_message("BitCast: %s", str.c_str());
            yhao_print(ki->inst->getOperand(0)->getType()->print, str)
            klee::klee_message("BitCast: %s", str.c_str());
            break;
        }
        default: {
            break;
        }
    }
}

void kuc::UCListener::afterRun(klee::ExecutionState &state) {

}

void kuc::UCListener::executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) {

}

std::string kuc::UCListener::create_global_var_name(llvm::Instruction *i, int64_t index, const std::string &kind) {
    std::string name;
    name += inst_to_strID(i);
    name += "-" + std::to_string(index);
    name += "-" + kind;
    if (this->count.find(name) == this->count.end()) {
        this->count[name] = 0;
    }
    name += "-" + std::to_string(this->count[name]);
    this->count[name] = this->count[name] + 1;
    return name;
}

void kuc::UCListener::symbolic_before_load(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;

    auto *real_address = llvm::dyn_cast<klee::ConstantExpr>(base);
    if (real_address) {
        klee::klee_message("real_address");
    } else if (map_symbolic_address.find(base) != map_symbolic_address.end()) {
        klee::klee_message("find load symbolic");
        executor->un_eval(ki, 0, state).value = map_symbolic_address[base];
    } else {
        klee::klee_message("make load symbolic");
        auto ty = ki->inst->getOperand(0)->getType();
        if (ty->getTypeID() == llvm::Type::IntegerTyID || ty->getTypeID() == llvm::Type::PointerTyID) {

            // yhao: create mo for non constant address
            // e.g. value load symbolic_address
            // create new mo and symbolic_address = mo->getBaseExpr();
            // do not consider address calculation
            // mainly for the case concrete address + symbolic offset
            auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            klee::MemoryObject *mo = executor->create_mo(state, ty, ki->inst, name);
            executor->un_eval(ki, 0, state).value = mo->getBaseExpr();
            this->map_symbolic_address[base] = mo->getBaseExpr();
            this->map_address_symbolic[mo->getBaseExpr()] = base;
            yhao_print(mo->getBaseExpr()->print, str);
            klee::klee_message("%s", str.c_str());
        } else {
            klee::klee_message("symbolic address, type is not integer or pointer");
        }
    }
}

void kuc::UCListener::symbolic_before_store(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;

    auto *real_address = llvm::dyn_cast<klee::ConstantExpr>(base);
    if (real_address) {
        klee::klee_message("real_address");
    } else if (map_symbolic_address.find(base) != map_symbolic_address.end()) {
        klee::klee_message("find store symbolic");
        executor->un_eval(ki, 0, state).value = map_symbolic_address[base];
    } else {
        klee::klee_message("make store symbolic");
        auto ty = ki->inst->getOperand(0)->getType();
        if (ty->getTypeID() == llvm::Type::IntegerTyID || ty->getTypeID() == llvm::Type::PointerTyID) {

            // yhao: create mo for non constant address
            // e.g. value load symbolic_address
            // create new mo and symbolic_address = mo->getBaseExpr();
            // do not consider address calculation
            // mainly for the case concrete address + symbolic offset
            auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            klee::MemoryObject *mo = executor->create_mo(state, ty, ki->inst, name);
            executor->un_eval(ki, 1, state).value = mo->getBaseExpr();
            this->map_symbolic_address[base] = mo->getBaseExpr();
            this->map_address_symbolic[mo->getBaseExpr()] = base;
            yhao_print(mo->getBaseExpr()->print, str);
            klee::klee_message("%s", str.c_str());
        } else {
            klee::klee_message("symbolic address, type is not integer or pointer");
        }
    }
}

void kuc::UCListener::symbolic_after_load(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    // check value of load, if it is pointer, create mo and symbolic os
    auto ty = ki->inst->getType();
    if (ty->isPointerTy() && ty->getPointerElementType()->isSized()) {
        auto ret = executor->getDestCell(state, ki).value;
        if (ret->getKind() == klee::Expr::Constant) {
            return;
        }
        klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;

        if (map_symbolic_address.find(ret) != map_symbolic_address.end()) {
            klee::klee_message("find load ret symbolic");
            auto value = map_symbolic_address[ret];
            executor->bindLocal(ki, state, value);
            executor->executeMemoryOperation(state, true, base, value, nullptr);
        } else {
            /// yu hao: create mo for non-constant pointer
            // e.g. symbolic pointer load address
            // create new mo and symbolic pointer = mo->getBaseExpr();
            klee::klee_message("make load ret symbolic");
            auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            klee::klee_message("name: %s", name.c_str());
            yhao_print(ty->getPointerElementType()->print, str);
            klee::klee_message("pointer element type: %s", str.c_str());
            klee::MemoryObject *mo = executor->create_mo(state, ty->getPointerElementType(), ki->inst, name);
            executor->bindLocal(ki, state, mo->getBaseExpr());
            executor->executeMemoryOperation(state, true, base, mo->getBaseExpr(), nullptr);
            this->map_symbolic_address[base] = mo->getBaseExpr();
            this->map_address_symbolic[mo->getBaseExpr()] = base;
            yhao_print(mo->getBaseExpr()->print, str);
            klee::klee_message("mo base: %s", str.c_str());
        }

    }
}

void kuc::UCListener::symbolic_after_call(klee::ExecutionState &state, klee::KInstruction *ki) {
    auto cs = llvm::cast<llvm::CallBase>(ki->inst);
    llvm::Value *fp = cs->getCalledOperand();
    llvm::Function *f = executor->getTargetFunction(fp, state);
    if (llvm::isa<llvm::InlineAsm>(fp)) {
        goto create_return;;
    }
    if (f && f->isDeclaration()) {
        switch (f->getIntrinsicID()) {
            case llvm::Intrinsic::not_intrinsic: {
                if (executor->special_function(f)) {
                    return;
                }
                yhao_log(1, "case llvm::Intrinsic::not_intrinsic:");
                goto create_return;
            }
            default: {
                return;
            }
        }
    } else if (!f) {
        klee::klee_message("!f");
        goto create_return;
    } else {
        return;
    }

    create_return:
    llvm::Type *resultType = cs->getType();
    if (!resultType->isVoidTy()) {
        klee::klee_message("make call return symbolic");

        auto name = create_global_var_name(ki->inst, -1, "call_return");
        auto ty = ki->inst->getType();
        unsigned int size = executor->kmodule->targetData->getTypeStoreSize(ty);
        klee::Expr::Width width = executor->getWidthForLLVMType(ty);
        klee::ref<klee::Expr> symbolic = klee::Executor::manual_make_symbolic(name, size, width);
        executor->bindLocal(ki, state, symbolic);

//            auto cs = llvm::cast<llvm::CallBase>(ki->inst);
//            for (unsigned j = 0; j < cs->getNumArgOperands(); ++j) {
//                auto arg_name = create_global_var_name(ki->inst, j, "call_arg");
//                Expr::Width arg_size = executor->getWidthForLLVMType(cs->getArgOperand(j)->getType());
//                ref<Expr> arg = manual_make_symbolic(arg_name, size);
//                executor->uneval(ki, j + 1, state).value = arg;
//            }
    }
}

std::string kuc::UCListener::get_name(klee::ref<klee::Expr> value) {
    klee::ReadExpr *revalue;
    if (value->getKind() == klee::Expr::Concat) {
        auto *c_value = llvm::cast<klee::ConcatExpr>(value);
        revalue = llvm::cast<klee::ReadExpr>(c_value->getKid(0));
    } else if (value->getKind() == klee::Expr::Read) {
        revalue = llvm::cast<klee::ReadExpr>(value);
    } else {
        assert(0 && "getGlobalName");
    }
    std::string globalName = revalue->updates.root->name;
    return globalName;
}

void kuc::UCListener::resolve_symbolic_expr(const klee::ref<klee::Expr> &symbolicExpr,
                                            std::set<std::string> &relatedSymbolicExpr) {
    if (symbolicExpr->getKind() == klee::Expr::Read) {
        std::string name = get_name(symbolicExpr);
        if (relatedSymbolicExpr.find(name) == relatedSymbolicExpr.end()) {
            relatedSymbolicExpr.insert(name);
        }
        return;
    } else {
        unsigned kidsNum = symbolicExpr->getNumKids();
        if (kidsNum == 2 && symbolicExpr->getKid(0) == symbolicExpr->getKid(1)) {
            resolve_symbolic_expr(symbolicExpr->getKid(0), relatedSymbolicExpr);
        } else {
            for (unsigned int i = 0; i < kidsNum; i++) {
                resolve_symbolic_expr(symbolicExpr->getKid(i), relatedSymbolicExpr);
            }
        }
    }
}