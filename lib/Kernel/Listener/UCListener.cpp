//
// Created by yuhao on 2/3/22.
//

#include "UCListener.h"
#include "../ToolLib/log.h"
#include "../ToolLib/llvm_related.h"
#include "../../Core/Executor.h"
#include "klee/Support/ErrorHandling.h"

using namespace klee;
using namespace llvm;

kuc::UCListener::UCListener(klee::Executor *executor) : Listener(executor) {
    config = executor->config;
    if (config.contains("13_skip_function_list") && config["13_skip_function_list"].is_array()) {
        for (const auto &temp: config["13_skip_function_list"]) {
            skip_functions.insert(temp.get<std::string>());
        }
    }

    if (config.contains("91_print_inst")) {
        print_inst = config["91_print_inst"];
    }
    else {
        print_inst = false;
    }

    if (config.contains("92_indirectcall")){
        indirectcall_map = config["92_indirectcall"];
    }

    if (config.contains("95_kernelversion")){
        kernelversion = config["95_kernelversion"];
    } else {
        kernelversion = "v5.4";
    }

    if (config.contains("96_concolic_map")){
        concolic_map = config["96_concolic_map"];
    }
}

kuc::UCListener::~UCListener() = default;

// used for concolic execution
void kuc::UCListener::beforeRun(klee::ExecutionState &state) {
    klee_message("\nUCListener::beforeRun");
    KInstruction *ki = state.pc;
    KFunction *kf = state.stack.back().kf;
    Function *f = kf->function;
    Function::arg_iterator ai = f->arg_begin(), ae = f->arg_end();
    uint64_t index = 0;
    std::string str;
    int base = 10;
    char *end;

    for (; ai != ae; ai++) {
        if (concolic_map.find(std::to_string(index)) == concolic_map.end()) {continue;}
        // map of {nth byte, value}
        std::map<std::string, uint64_t> local_concolic_map = concolic_map[std::to_string(index)];

        auto argument = state.stack.back().locals[kf->getArgRegister(index)].value;
        klee_message("index: %lu Argument type: %d argument: %s", index, ai->getType()->getTypeID(), argument.get_ptr()->dump2().c_str());
        auto ty = ai->getType();

        if(ty->getTypeID() == llvm::Type::PointerTyID ){
            std::string name = "input_"+std::to_string(index)+"(pointer)";
            klee::klee_message("name: %s", name.c_str());
            yhao_print(ty->getPointerElementType()->print, str);
            klee::klee_message("pointer element type: %s", str.c_str());
            // create an object corresponding to the pointer
            klee::MemoryObject *mo = executor->create_mo(state, ty->getPointerElementType(), ki->inst, name);
            this->map_symbolic_address[argument] = mo->getBaseExpr();
            this->map_address_symbolic[mo->getBaseExpr()] = argument;
            klee_message("mo base: %lu mo size: %u", mo->address, mo->size);

            klee::ObjectPair op;
            state.addressSpace.resolveOne(mo->getBaseExpr(), op);
            const ObjectState *os = op.second;
            // add constraint for each byte in local_concolic_map
            for (auto it = local_concolic_map.begin(); it != local_concolic_map.end(); ++it){
                // it-> first is string
                uint64_t offset_value =  std::strtoull(it->first.c_str(), &end, base);
                uint64_t value = it->second;
                ref<Expr> offset = klee::ConstantExpr::create(offset_value, Context::get().getPointerWidth());
                ref<Expr> readvalue = os->read(offset, 8);

                ref<Expr> cond = EqExpr::create(readvalue, klee::ConstantExpr::create(value, 8));
                klee_message("add constraint: %s", cond.get_ptr()->dump2().c_str());
                state.addConstraint(cond);
            }
        } else if (ty->getTypeID() == llvm::Type::IntegerTyID) {
            // if the argument type is IntegerTy (int, char......) then no need to create an object, add the constraint directly 
            uint64_t value = local_concolic_map["0"];
            klee_message("cast<IntegerType>(ty)->getBitWidth(): %u", cast<IntegerType>(ty)->getBitWidth());
            ref<Expr> cond = EqExpr::create(argument, klee::ConstantExpr::create(value, cast<IntegerType>(ty)->getBitWidth()));
            klee_message("add constraint: %s", cond.get_ptr()->dump2().c_str());
            state.addConstraint(cond);
        }
        index ++;
    }
}

void print_constraints(klee::ExecutionState &state) {
    klee::klee_message("----- Br Inst print current constraints: -----");
    klee::ConstraintSet constraints = state.constraints;
    std::set<std::string> constraint_strs;
    std::string str;
    std::map<const std::string, std::set<std::string>> constraint_lines = state.constraint_lines;
	for (auto it = constraints.begin(), ie = constraints.end(); it != ie;) {
		klee::ref<klee::Expr> value = *it;
		yhao_print(value->print, str);
        if (constraint_strs.find(str) == constraint_strs.end())
        {
            klee::klee_message("Br constraint: %s", str.c_str());
            if (constraint_lines.find(str) != constraint_lines.end()){
                //klee::klee_message("constraint_lines:");
                for (auto it2 = constraint_lines[str].begin(); it2 != constraint_lines[str].end(); it2++)
                {
                    klee::klee_message("line: %s", (*it2).c_str());/* code */
                }
            }
            constraint_strs.insert(str);
        }
		++it;
	}
	klee::klee_message("----------------"); 
}

void kuc::UCListener::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    klee::klee_message("\n\nUCListener::beforeExecuteInstruction()");
    std::string str;
    //yhao_log(1, inst_to_strID(ki->inst));
    //yhao_log(1, dump_inst_booltin(ki->inst));
    if (print_inst){
        yhao_print(ki->inst->print, str)
        klee::klee_message("inst: %s", str.c_str());
    }
    
    klee::klee_message("ExecutionState &state: %p", &state);
    klee::klee_message("bb name i->getParent()->getName().str() %s",ki->inst->getParent()->getName().str().c_str());
    std::string sourceinfo = dump_inst_booltin(ki->inst, kernelversion);
    if (sourceinfo!= ""){
    klee::klee_message("line sourceinfo %s",sourceinfo.c_str());
    }
    klee::klee_message("target->dest: %d", ki->dest);
    int inst_type[] = {llvm::Instruction::GetElementPtr, llvm::Instruction::Load, llvm::Instruction::Store, llvm::Instruction::Ret,
    llvm::Instruction::ICmp, llvm::Instruction::Call, llvm::Instruction::Or, llvm::Instruction::Add,
    llvm::Instruction::Xor};
    int *find = std::find(std::begin(inst_type), std::end(inst_type), ki->inst->getOpcode());
    if (find != std::end(inst_type)){
    size_t i = 0;
    klee::klee_message("ki->inst->getNumOperands(): %d", ki->inst->getNumOperands());
    
    while (i < ki->inst->getNumOperands())
    {
        //klee::klee_message("ki->operands[%zu] vnumber: %d", i, ki->operands[i]);
        if(ki->operands[i]==-1)
        {  
            i++;
            continue;
        }
        klee::ref<klee::Expr> operand = executor->eval(ki, i, state).value;
        yhao_print(operand->print, str);
        klee::klee_message("Inst operand %zu: %s", i, str.c_str());
        i++;
    }
    }
    

    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::GetElementPtr: {
            break;
        }
        case llvm::Instruction::Load: {
            //klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;
            //yhao_print(base->print, str);
            //klee::klee_message("Load Inst base: %s", str.c_str());

            // yhao: symbolic execution
            this->symbolic_before_load(state, ki);
            break;
        }
        case llvm::Instruction::Store: {
            /*
            klee::MemoryMap objects = state.addressSpace.objects;
            klee::MemoryMap::iterator tmp=objects.begin();
            klee_message("list all current objects:");
            for (; tmp!=objects.end(); ++tmp) {
                const auto &mo = tmp->first;
                const klee::ObjectState *os = tmp->second.get();
                klee::klee_message("mo->address: %lu  mo->size: %u  mo->issymsize: %s", mo->address, mo->size, mo->issymsize.c_str());
                //klee::ref<klee::Expr> result = os->read(klee::ConstantExpr::create(0, 4),  8);
                //klee::klee_message("read result: %s", (result.ptr)->dump2().c_str());
            }
            */

            /*klee::klee_message("ki->operands[0] vnumber: %d", ki->operands[0]);
            klee::ref<klee::Expr> value = executor->eval(ki, 0, state).value;
            yhao_print(value->print, str)
            klee::klee_message("value: %s", str.c_str());
            if (value->getKind() != klee::Expr::Constant) {
                klee::klee_message("non-constant store value");
            }
            klee::klee_message("ki->operands[1] vnumber: %d", ki->operands[1]);
            klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;
            yhao_print(base->print, str);
            klee::klee_message("Store Inst base: %s", str.c_str());*/

            // yhao: symbolic execution: this should only happen when pointer in arguments
            this->symbolic_before_store(state, ki);
            break;
        }
        case llvm::Instruction::Ret: {
//            klee::klee_message("ki->operands[0] vnumber: %d", ki->operands[0]);
//            klee::ref<klee::Expr> value = executor->eval(ki, 0, state).value;
//            yhao_print(value->print, str);
//            klee::klee_message("Ret Inst value: %s", str.c_str());
            break;
        }
        case llvm::Instruction::ICmp: {
            llvm::Instruction *i = ki->inst;
            CmpInst *ci = cast<CmpInst>(i);
            ICmpInst *ii = cast<ICmpInst>(ci);

            switch(ii->getPredicate()) {
                case llvm::ICmpInst::ICMP_EQ: {
                    klee::ref<Expr> left = executor->eval(ki, 0, state).value;
                    klee::ref<Expr> right = executor->eval(ki, 1, state).value;
                    //if (left.ptr->dump2() == "0"){
                    if (this->map_address_symbolic.find(right) != this->map_address_symbolic.end()){
                        klee::ref<Expr> symbolic_pointer = this->map_address_symbolic[right];
                        executor->un_eval(ki, 1, state).value = symbolic_pointer;
                    }
                    //}
                    //else if (right.ptr->dump2() == "0"){
                    if (this->map_address_symbolic.find(left) != this->map_address_symbolic.end()){
                        klee::ref<Expr> symbolic_pointer = this->map_address_symbolic[left];
                        executor->un_eval(ki, 0, state).value = symbolic_pointer;
                    }
                    //}
                    break;
                }
                case llvm::ICmpInst::ICMP_NE: {
                    klee::ref<Expr> left = executor->eval(ki, 0, state).value;
                    klee::ref<Expr> right = executor->eval(ki, 1, state).value;
                    //if (left.ptr->dump2() == "0"){
                    if (this->map_address_symbolic.find(right) != this->map_address_symbolic.end()){
                        klee::ref<Expr> symbolic_pointer = this->map_address_symbolic[right];
                        executor->un_eval(ki, 1, state).value = symbolic_pointer;
                    }
                    //}
                    //else if (right.ptr->dump2() == "0"){
                    //    klee_message("icmp NE right expr is 0");
                    if (this->map_address_symbolic.find(left) != this->map_address_symbolic.end()){
                        klee_message("icmp NE left expr is symbolic in fact");
                        klee::ref<Expr> symbolic_pointer = this->map_address_symbolic[left];
                        klee_message("symbolic pointer: %s", symbolic_pointer.ptr->dump2().c_str());
                        executor->un_eval(ki, 0, state).value = symbolic_pointer;
                    }
                    //}
                    break;
                }
                default:
                    break;
            }
            break;
        }
        case llvm::Instruction::Br: {
            print_constraints(state);
            break;
    	}
        case llvm::Instruction::Call: {
            print_constraints(state);
    	}
        default: {

        }
    }
}

//added by zheng
// if skip OOB error, we need to symbolize the dest value
void kuc::UCListener::symbolize_Inst_return(klee::ExecutionState &state, klee::KInstruction *ki){
    llvm::Type *ty = ki->inst->getType();
    auto sym_name = this->create_global_var_name(ki->inst, 0, "symbolic_Inst_return");
    klee_message("create symbolic return for Load Inst: %s", sym_name.c_str());
    unsigned int size =  executor->kmodule->targetData->getTypeStoreSize(ty);
    Expr::Width width = executor->getWidthForLLVMType(ty);
    ref<Expr> symbolic = executor->manual_make_symbolic(sym_name, size, width);
    executor->getDestCell(state, ki).value = symbolic;
}

void kuc::UCListener::afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    klee::klee_message("UCListener::afterExecuteInstruction()");

    unsigned index = ki->dest;
    klee::klee_message("ki->dest: %u", ki->dest);

    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::GetElementPtr: {
            yhao_print(executor->getDestCell(state, ki).value->print, str);
            klee::klee_message("GetElementPtr Inst value: %s", str.c_str());
            break;
        }
        case llvm::Instruction::Load: {
            // if skip OOB error, we need to symbolize the dest value
            auto result = executor->getDestCell(state, ki).value;
            if(!result){
                klee::klee_message("no return value");
                symbolize_Inst_return(state, ki);
            }
            yhao_print(executor->getDestCell(state, ki).value->print, str);
            klee::klee_message("Load Inst value: %s", str.c_str());
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
        case llvm::Instruction::ICmp: {
            yhao_print(executor->getDestCell(state, ki).value->print, str);
            klee::klee_message("ICMP Inst value: %s", str.c_str());
            break;
        }
        case llvm::Instruction::Br: {
            /*
            BranchInst *bi = cast<BranchInst>(ki->inst);
            if (bi->isUnconditional()) {
                break;
            }
            std::string sourceinfo = dump_inst_booltin(ki->inst);
            // what if the cond is a And cond? we will miss the first one?
            if(state.constraints.size() > 0){
                std::string finalconstraint_str;
                auto ie = state.constraints.end()-1;
                klee::ref<klee::Expr> value = *ie;
                yhao_print(value->print, finalconstraint_str);
                state.constraint_lines[finalconstraint_str].insert(sourceinfo);
                klee_message("add constraint: %s\n at line: %s", finalconstraint_str.c_str(), sourceinfo.c_str());
            }
            */
            break;
        }
        default: {
            break;
        }
    }
}

void kuc::UCListener::afterRun(klee::ExecutionState &state) {

}

bool kuc::UCListener::CallInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    auto cs = llvm::cast<llvm::CallBase>(ki->inst);
    llvm::Value *fp = cs->getCalledOperand();
    llvm::Function *f = executor->getTargetFunction(fp, state);
    if (llvm::isa<llvm::InlineAsm>(fp)) {
        return false;
    }
    if (!f) {
        klee::klee_message("skip function: unrecognized f");
        return false;
    }
    std::string name = f->getName().str();
    if (skip_functions.find(name) != skip_functions.end()) {
        klee::klee_message("skip function: %s",name.c_str());
        return true;
    }
    if (f && f->isDeclaration()) {
        switch (f->getIntrinsicID()) {
            case llvm::Intrinsic::not_intrinsic: {
                if (executor->special_function(f)) {
                    return false;
                }
                klee::klee_message("function: Intrinsic::not_intrinsic");
                return true;
            }
            default: {
            }
        }
    }
    return false;
}

void kuc::UCListener::executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) {

}

std::string kuc::UCListener::create_global_var_name(llvm::Instruction *i, int64_t index, const std::string &kind) {
    std::string name;
    name += inst_to_strID(i);
    //add by zheng
    std::string sourceinfo = dump_inst_booltin(i, kernelversion);
    std::size_t pos = sourceinfo.find("#");
    std::string linenum = sourceinfo.substr(pos);
    name += linenum;

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
        klee::klee_message("find corresponding real_address of store symbolic address %s", map_symbolic_address[base].get_ptr()->dump2().c_str());
        executor->un_eval(ki, 1, state).value = map_symbolic_address[base];
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
        // the return value (a pointer) of load instruction
        auto ret = executor->getDestCell(state, ki).value;
        if (ret->getKind() == klee::Expr::Constant) {
            return;
        }
        // type of base is pointer of pointer (char ** for example)
        klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;

        klee_message("load ret symbolic: %s", ret.get_ptr()->dump2().c_str());
        if (map_symbolic_address.find(ret) != map_symbolic_address.end()) {
            klee::klee_message("find load ret symbolic");
            auto value = map_symbolic_address[ret];
            executor->bindLocal(ki, state, value);
            executor->executeMemoryOperation(state, true, base, value, nullptr);
        } else {
            /// yu hao: create mo for non-constant pointer
            // e.g. symbolic pointer load address
            // create new mo and symbolic pointer = mo->getBaseExpr();
            klee::klee_message("make symbolic load ret concolic with creating a concolic object");
            std::string name;
            std::string retstr = ret.get_ptr()->dump2();
            if(retstr.substr(0,21) == "(ReadLSB w64 0 input_") {
                name = "input_"+retstr.substr(21,22)+"(pointer)";
            } else {
                name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            }
            klee::klee_message("name: %s", name.c_str());
            yhao_print(ty->getPointerElementType()->print, str);
            klee::klee_message("pointer element type: %s", str.c_str());
            klee::MemoryObject *mo = executor->create_mo(state, ty->getPointerElementType(), ki->inst, name);
            executor->bindLocal(ki, state, mo->getBaseExpr());
            executor->executeMemoryOperation(state, true, base, mo->getBaseExpr(), nullptr);
            this->map_symbolic_address[ret] = mo->getBaseExpr();
            this->map_address_symbolic[mo->getBaseExpr()] = ret;
            yhao_print(mo->getBaseExpr()->print, str);
            klee::klee_message("mo base: %s", str.c_str());
        }

    }
}

void kuc::UCListener::symbolic_after_call(klee::ExecutionState &state, klee::KInstruction *ki) {
    klee::klee_message("symbolic_after_call");
    auto cs = llvm::cast<llvm::CallBase>(ki->inst);
    llvm::Value *fp = cs->getCalledOperand();
    llvm::Function *f = executor->getTargetFunction(fp, state);

    auto line_info = dump_inst_sourceinfo(ki->inst);
    std::size_t pos = line_info.find("source/");
    line_info = line_info.substr(pos+1);
    
    //ref<Expr> prevvalue = executor->getDestCell(state, ki).value;
    klee_message("previous target ptr: %p", executor->getDestCell(state, ki).value.ptr);

    if (llvm::isa<llvm::InlineAsm>(fp)) {
        goto create_return;
    }
    if (f && f->isDeclaration()) {
        klee::klee_message("f->isDeclaration()");
        std::string name = f->getName().str();
        if (skip_functions.find(name) != skip_functions.end()) {
            goto create_return;
        }
        switch (f->getIntrinsicID()) {
            case llvm::Intrinsic::not_intrinsic: {
                if (executor->special_function(f)) {
                    return;
                }
                klee::klee_message("case llvm::Intrinsic::not_intrinsic:");
                goto create_return;
            }
            default: {
                return;
            }
        }
    } else if (f && !f->isDeclaration()) {
        std::string name = f->getName().str();
        if (skip_functions.find(name) != skip_functions.end()) {
            klee::klee_message("in skip_functions");
            goto create_return;
        } else {
            return;
        }
    } else if (!f) {
        klee::klee_message("!f");
        if (this->indirectcall_map.find(line_info) != this->indirectcall_map.end()){
            klee_message("concrete target for indirect call, no need for symbolic call return");
            return;
        }
        //due to some reason it already call executeCall
        if(executor->getDestCell(state, ki).value.ptr){
            klee_message("due to some reason it already call executeCall");
            return;
        }
        /*
        ref<Expr> v = executor->eval(ki, 0, state).value;
        if (const klee::ConstantExpr *CE = llvm::dyn_cast<klee::ConstantExpr>(v)){
            uint64_t addr = CE->getZExtValue();
            if (executor->legalFunctions.count(addr)) {
                return;
            }
        }*/
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
        klee_message("symbolic return: %s", symbolic.get_ptr()->dump2().c_str());
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
