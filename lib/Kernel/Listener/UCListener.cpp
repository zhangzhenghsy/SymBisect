//
// Created by yuhao on 2/3/22.
//

#include "UCListener.h"
#include "../ToolLib/log.h"
#include "../ToolLib/llvm_related.h"
#include "../../Core/Executor.h"
#include "klee/Support/ErrorHandling.h"
#include <string>

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
    // example: "97_calltrace": ["ethnl_set_features", "ethnl_parse_bitset", "bitmap_from_arr32"]
    if (config.contains("97_calltrace")){
        for (const auto &temp: config["97_calltrace"]) {
            Calltrace.push_back(temp.get<std::string>());
        }
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

    klee_message("print concolic_map:");
    for(const auto& elem : concolic_map)
    {
        klee_message("\nindex of argu: %s", elem.first.c_str());
        for(const auto& localelem : elem.second){
            klee_message("index: %s  value: %lu", localelem.first.c_str(), localelem.second);
        }
    }

    for (; ai != ae; ai++) {
        klee_message("\nindex: %s", std::to_string(index).c_str());
        if (concolic_map.find(std::to_string(index)) == concolic_map.end()) {index ++;continue;}
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

void kuc::UCListener::get_key_unsat_constraint(klee::ExecutionState &state, klee::ref<klee::Expr> cond) {
    klee::ConstraintSet constraints = state.constraints;
    std::map<const std::string, std::set<std::string>> constraint_lines = state.constraint_lines;

    klee::ConstraintSet new_constraints = ConstraintSet();
    bool result;
    ConstraintManager m(new_constraints);
    for (const auto &constraint : constraints) {
        m.addConstraint(constraint);
        bool success = executor->solver->mustBeFalse(new_constraints, cond, result,
                                      state.queryMetaData);
        if(result){
            std::string str;
            yhao_print(constraint->print, str);
            klee_message("get_key_unsat_constraint: %s", str.c_str());
            if (constraint_lines.find(str) != constraint_lines.end()){
                for (auto it2 = constraint_lines[str].begin(); it2 != constraint_lines[str].end(); it2++)
                {
                    klee::klee_message("line: %s", (*it2).c_str());/* code */
                }
            }
            break;
        }
    }
}
void kuc::UCListener::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    klee::klee_message("\n\nUCListener::beforeExecuteInstruction()");
    std::string str;
    //yhao_log(1, inst_to_strID(ki->inst));
    //yhao_log(1, dump_inst_booltin(ki->inst));
    klee::klee_message("ExecutionState &state: %p", &state);
    klee::klee_message("bb name i->getParent()->getName().str() %s",ki->inst->getParent()->getName().str().c_str());
    klee::klee_message("sourcecodeLine: %s %u:%u", ki->info->file.c_str(), ki->info->line, ki->info->column);
    std::string sourcecodeline = ki->info->file + ":"+ std::to_string(ki->info->line);
    //klee::klee_message("ki->inst->getOpcodeName(): %s", ki->inst->getOpcodeName());
    if (print_inst){
        yhao_print(ki->inst->print, str)
        klee::klee_message("inst: %s", str.c_str());
        //size_t i = 0;
        //while (i < ki->inst->getNumOperands()) {
        //    yhao_print(ki->inst->getOperand(i)->print, str);
        //    klee::klee_message("Operand%u: %s", i, str.c_str());
        //    i +=1;
            //klee::klee_message("%s", ki->inst->getOperand(i)->dump().c_str());
        //}
        
    }
    //klee::klee_message("target->dest: %d", ki->dest);
    int inst_type[] = {llvm::Instruction::GetElementPtr, llvm::Instruction::Load, llvm::Instruction::Store, llvm::Instruction::Ret,
    llvm::Instruction::ICmp, llvm::Instruction::Call, llvm::Instruction::Or, llvm::Instruction::Add,
    llvm::Instruction::Xor, llvm::Instruction::Mul};
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
        //yhao_print(operand->print, str);
        if (operand.get_ptr()){
            klee::klee_message("Inst operand %zu: %s", i, operand.get_ptr()->dump2().c_str());
        }
        i++;
    }
    }
    OOBWcheck(state, ki);
    //print_constraints(state);
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
            //klee::MemoryMap objects = state.addressSpace.objects;
            //klee::MemoryMap::iterator tmp=objects.begin();
            //klee_message("list all current objects:");
            //for (; tmp!=objects.end(); ++tmp) {
            //    const auto &mo = tmp->first;
            //    if(std::to_string(mo->address) == executor->eval(ki, 0, state).value->dump2()){
            //        klee::klee_message("mo->address: %s  mo->size: %u  mo->issymsize: %s",  std::to_string(mo->address).c_str(), mo->size, mo->issymsize.c_str());
            //    }
            //}

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
            if (sourcecodeline != "drivers/video/fbdev/core/sysimgblt.c:226"){
                break;
            }
            BranchInst *bi = cast<BranchInst>(ki->inst);
            if (bi->isUnconditional()) {
                break;
            }
            klee::ref<klee::Expr> cond = executor->eval(ki, 0, state).value;

            klee::ConstraintSet constraints = state.constraints;

            bool result;
            bool success = executor->solver->mustBeFalse(state.constraints, cond, result,
                                      state.queryMetaData);
            if (!success)
                break;
            if (result){
                klee_message("cond must be False");
                get_key_unsat_constraint(state, cond);
                break;
            }
            cond = Expr::createIsZero(cond);
            success = executor->solver->mustBeFalse(state.constraints, cond, result,
                                      state.queryMetaData);
            if (!success)
                break;
            if (result){
                klee_message("cond must be True");
                get_key_unsat_constraint(state, cond);
                break;
            }
            //print_constraints(state);
            break;
    	}
        // For the modelled functions, we should concretize symbolic addr if necessary
        case llvm::Instruction::Call: {
            auto cs = llvm::cast<llvm::CallBase>(ki->inst);
            llvm::Value *fp = cs->getCalledOperand();
            llvm::Function *f = executor->getTargetFunction(fp, state);
            if(!f) {
                break;}
            std::string name = f->getName().str();

            if (name == "strcmp"){
                klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;
                auto ty = ki->inst->getOperand(1)->getType();
                //Question: what's the size of object should we create?
                //Note that we will match all the corresponding symaddrs (within the size) to the object
                klee::ref<klee::Expr> concrete_addr = create_symaddr_object(state, ki, base, ty, 64);
                executor->un_eval(ki, 1, state).value = concrete_addr;
            }
            else if (name == "strchr") {
                klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;
                auto ty = ki->inst->getOperand(1)->getType();
                klee::ref<klee::Expr> concrete_addr = create_symaddr_object(state, ki, base, ty, 64);
                executor->un_eval(ki, 1, state).value = concrete_addr;
            }
        }
        default: {

        }
    }
}

//added by zheng
// if skip OOB error, we need to symbolize the dest value
void kuc::UCListener::symbolize_Inst_return(klee::ExecutionState &state, klee::KInstruction *ki){
    llvm::Type *ty = ki->inst->getType();
    auto sym_name = this->create_global_var_name(ki, 0, "symbolic_Inst_return");
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
    //klee::klee_message("ki->dest: %u", ki->dest);
    int inst_type[] = {llvm::Instruction::GetElementPtr, llvm::Instruction::Load, 
    llvm::Instruction::ICmp, llvm::Instruction::Or, llvm::Instruction::Add, 
    llvm::Instruction::Xor, llvm::Instruction::Mul, llvm::Instruction::ZExt};
    int *find = std::find(std::begin(inst_type), std::end(inst_type), ki->inst->getOpcode());
    if (find != std::end(inst_type)){
        if(executor->getDestCell(state, ki).value.get_ptr()){
            klee::klee_message("Inst value: %s", executor->getDestCell(state, ki).value.get_ptr()->dump2().c_str());
        } else {
            klee::klee_message("Inst value: Null");
        }
    }
    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::GetElementPtr: {
            //yhao_print(executor->getDestCell(state, ki).value->print, str);
            //klee::klee_message("GetElementPtr Inst value: %s", str.c_str());
            ObjectPair op;
            bool success;
            klee::ref<klee::Expr> baseaddr = executor->eval(ki, 0, state).value;
            klee::ref<klee::Expr> index = executor->eval(ki, 1, state).value;
            // if the index is concrete, we don't need to log the mapping between symbolic addr and base object
            if (klee::ConstantExpr* CE1 = dyn_cast<klee::ConstantExpr>(index)) {
                break;
            }
            if (klee::ConstantExpr* CE2 = dyn_cast<klee::ConstantExpr>(baseaddr)) {
                success = state.addressSpace.resolveOne(CE2, op);
            } else{
                break;
            }
            if(success) {
                state.symaddr_base[executor->getDestCell(state, ki).value] = baseaddr;
                klee_message("symaddr_base symaddr %s base addr %s\n", executor->getDestCell(state, ki).value.get_ptr()->dump2().c_str(), baseaddr.get_ptr()->dump2().c_str());
                const klee::MemoryObject * object = op.first;
                klee_message("Base corresponding obj addr: %lu obj size: %u", object->address, object->size);
            }
            break;
        }
        case llvm::Instruction::Store: {
            ObjectPair op;
            bool success;
            symbolic_after_store(state, ki);
            klee::ref<klee::Expr> value = executor->eval(ki, 0, state).value;
            klee::ref<klee::Expr> address = executor->eval(ki, 1, state).value;
            // if the address is really concrete (no mapped symbolic address), we don't need to check the mapping between symbolic addr and base object
            if (this->map_address_symbolic.find(address) == this->map_address_symbolic.end()){
                break;
            }
            // there is a symbolic address such as: concretebase+symoffset, thus we create a concrete address corresponding it
            // However, sometimes what we really need to access is the object at concretebase
            // Here we need to restore the concrete base and write to it
            // klee_message("restore sym address with concrete addr: %s", address.get_ptr()->dump2().c_str());
            //address = this->map_address_symbolic[address];
            //klee_message("sym address: %s", address.get_ptr()->dump2().c_str());
            if (klee::ConstantExpr* CE1 = dyn_cast<klee::ConstantExpr>(address)) {
                break;
            }
            if (state.symaddr_base.find(address) != state.symaddr_base.end()){                
                klee::ref<klee::Expr> baseaddr = state.symaddr_base[address];
                klee_message("find address in symaddr_base mapping, the base addr: %s", baseaddr.get_ptr()->dump2().c_str());
                success = state.addressSpace.resolveOne(dyn_cast<klee::ConstantExpr>(baseaddr), op);
                if (!success) {break;}
                const klee::MemoryObject * object = op.first;
                const ObjectState *os = op.second;
                klee_message("Base corresponding obj addr: %lu obj size: %u", object->address, object->size);
                auto ty = ki->inst->getOperand(0)->getType();
                uint64_t size = executor->kmodule->targetData->getTypeStoreSize(ty).getKnownMinSize();
                klee_message("size of operand0 : %lu", size);
                uint64_t offset;
                // our starting address
                klee::ref<klee::Expr> objectbase = klee::ConstantExpr::create(object->address, klee::Context::get().getPointerWidth());
                klee::ref<klee::Expr> currentaddr;
                int loop = 0;
                // Now the offset if symbolic, for every offset at the object which may equal the symoffset, we try to make the value there to be original value or the new writing value 
                for (offset = 0 ; offset < (uint64_t)object->size; offset += size) {
                    loop ++;
                    if (loop > 32) break;
                    ref<Expr> Offset = klee::ConstantExpr::create(offset, klee::Context::get().getPointerWidth());
                    klee_message("objectbase: %s", objectbase.get_ptr()->dump2().c_str());
                    klee_message("Offset: %s", Offset.get_ptr()->dump2().c_str());
                    ref<Expr> currentaddr = AddExpr::create(objectbase, Offset);
                    //ref<Expr> oldvalue = os->read(offset, size*8);

                    bool res;
                    klee_message("currentaddr: %s", currentaddr.get_ptr()->dump2().c_str());
                    klee_message("address: %s", address.get_ptr()->dump2().c_str());
                    //klee_message("oldvalue: %s", oldvalue.get_ptr()->dump2().c_str());
                    ref<Expr> condition = EqExpr::create(currentaddr, address);
                    bool success = executor->solver->mayBeTrue(state.constraints, condition, res,
                                  state.queryMetaData);
                    if (!res) { 
                        klee_message("sym address cannot equal current address, skip. currentaddr: %s", currentaddr.get_ptr()->dump2().c_str());
                        continue; 
                    }
                    // create a new symvalue which can equal old value at current address or new written value, then write the symvalue back to current address
                    auto name = "["+currentaddr.get_ptr()->dump2()+"]" + "(symvar)";
                    ref<Expr> currentvalue = executor->manual_make_symbolic(name, size, size*8);
                    //ref<Expr> newconstraint = OrExpr::create(EqExpr::create(currentvalue, oldvalue), EqExpr::create(currentvalue, value));
                    //klee_message("newconstraint: %s", newconstraint.get_ptr()->dump2().c_str());
                    executor->executeMemoryOperation(state, true, currentaddr, currentvalue, 0);
                    //executor->addConstraint(state, newconstraint);
                }
            }
            break;
        }
        case llvm::Instruction::Load: {
            // if skip OOB error, we need to symbolize the dest value
            auto result = executor->getDestCell(state, ki).value;
            if(!result||!executor->getDestCell(state, ki).value.ptr){
                klee::klee_message("no return value");
                symbolize_Inst_return(state, ki);
            }
            yhao_print(executor->getDestCell(state, ki).value->print, str);
            //klee::klee_message("Load Inst value: %s", str.c_str());
            // restore the symbolic address
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
            //klee::klee_message("ICMP Inst value: %s", str.c_str());
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

std::string simplifyfuncname(std::string funcname) {
    size_t found = funcname.find(".");
    if (found != std::string::npos) {
        funcname = funcname.substr(0, found);
        klee_message("simplifyfuncname: %s", funcname.c_str());
    }
    return funcname;
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
    std::string simplifyname = simplifyfuncname(name);
    std::string local_skipfunctions[] = {"llvm.read_register.i64", "llvm.write_register.i64", "nla_data", "console_lock", "console_unlock", "klee_div_zero_check", "klee_overshift_check", "kmem_cache_alloc", "kmem_cache_alloc_node",
    "syscall_enter_from_user_mode ", "_raw_spin_lock_irqsave", "irqentry_enter", "__schedule", "preempt_schedule_irq", "bad_range", "update_curr", "_raw_spin_lock_irq", "finish_task_switch", "call_rcu",
    "__free_object", "free_unref_page", "rcu_read_unlock", "rcu_lock_release", "ERR_PTR"};
    for (std::string local_skipfunction:local_skipfunctions)
    {
        skip_functions.insert(local_skipfunction);
    }

    if (skip_functions.find(name) != skip_functions.end()) {
        klee::klee_message("skip function: %s",name.c_str());
        return true;
    }
    if (skip_functions.find(simplifyname) != skip_functions.end()) {
        klee::klee_message("skip function: %s",name.c_str());
        return true;
    }
    if(skip_calltrace_distance(state, ki, name)){
        skip_calltrace = true;
        return true;
    }
    skip_calltrace = false;

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

// used to calculate the distance between current function and target vulnerable function.
// If it's over the threshold (return true), then we wan't do deeper function call
// add a check:  if there is a cyclic call (A->B->C->A), then just skip
bool kuc::UCListener::skip_calltrace_distance(klee::ExecutionState &state, klee::KInstruction *ki, std::string targetfuncname) {
    // if there is no "97_calltrace" in config, we don't want to skip any functions.
    if (Calltrace.size() == 0){
        return false;
    }
    int threshold_distance = Calltrace.size();
    int default_depth = 3;
    if(threshold_distance < default_depth) {
        threshold_distance = default_depth;
    }
    //klee::klee_message("threshold_distance: %d", threshold_distance);
    bool Insametrace = true;
    int currentdistance = Calltrace.size();

    int endIndex = state.stack.size() - 1;
    klee_message("index: %d", endIndex);
    std::string calltracefuncname;

    llvm::Function* f = NULL;
    klee_message("targetfuncname: %s", targetfuncname.c_str());
    for (int i = 0; i <= endIndex; i++) {
      //klee::klee_message("i: %d", i);
      auto const &sf = state.stack.at(i);
      klee::KFunction* kf = sf.kf;
      f = kf ? kf->function : NULL;
      if (Insametrace && i < Calltrace.size()) {
        calltracefuncname = Calltrace[i];
      }
      if (f)
      {
            // check cyclic callchain
            std::string funcname = f->getName().str();
            if(targetfuncname == funcname) {
                klee::klee_message("detected cyclic call chain: %s skipped", targetfuncname.c_str());
                return true;
            }
            //klee_message("calltracefuncname:%s  funcname:%s ", calltracefuncname.c_str(), funcname.c_str());
            if (funcname != calltracefuncname) {
                Insametrace = false;
            }
            //klee_message("Insametrace: %s", Insametrace ? "true" : "false");
            if (Insametrace) {
                currentdistance -= 1;
            } else {
                int count = 0;
                for(auto &BB: *f) {count++;}
                if (count > 1) {
                    currentdistance += 1;
                }
            }
      }
    }
    
    klee::klee_message("currentdistance :%d threshold_distance: %d ", currentdistance, threshold_distance);
    if (currentdistance >= threshold_distance)
    {
        klee::klee_message("currentdistance :%d threshold_distance: %d skip the function due calltrace_distance", currentdistance, threshold_distance);
        return true;
    }
    return false;
}
void kuc::UCListener::executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) {

}

std::string kuc::UCListener::create_global_var_name(klee::KInstruction *ki, int64_t index, std::string kind) {
    std::string name;
    //klee_message("inst_to_strID(ki->inst): %s", inst_to_strID(ki->inst).c_str());
    //name += inst_to_strID(ki->inst);
    //add by zheng
    std::string filename = ki->info->file.c_str();
    std::string linenum = std::to_string(ki->info->line);
    name = filename+":"+ linenum;

    //name += "-" + std::to_string(index);
    name += "-" + kind;
    klee_message("create_global_var_name(), name:%s", name.c_str());
    if (this->count.find(name) == this->count.end()) {
        this->count[name] = 0;
    } else {
        this->count[name] = this->count[name] + 1;
    }
    klee_message("create_global_var_name(), count:%s", std::to_string(this->count[name]).c_str());
    name += "-" + std::to_string(this->count[name]);
    return name;
}

klee::ref<klee::Expr> kuc::UCListener::create_symaddr_object(klee::ExecutionState &state, klee::KInstruction *ki, klee::ref<klee::Expr> base, llvm::Type *ty, unsigned size = 0) {
    for (auto& pair:map_symbolic_address){
        klee::ref<klee::Expr> symbolic_address = pair.first;
        ref<Expr> equal_expr = EqExpr::create(symbolic_address, base);
        //klee_message("equal_expr:%s", equal_expr.get_ptr()->dump2().c_str());
        bool equal_result;
        bool success = executor->solver->mustBeTrue(state.constraints, equal_expr, equal_result,
                                                state.queryMetaData);
        if(equal_result){
            klee_message("base equals to previous sym_addr:%s", symbolic_address.get_ptr()->dump2().c_str());
            base = symbolic_address;
            break;
        }
    }
    auto *real_address = llvm::dyn_cast<klee::ConstantExpr>(base);
    if (real_address) {
        klee::klee_message("real_address");
        return base;
    } else if (map_symbolic_address.find(base) != map_symbolic_address.end()) {
        // question: is it possible that the previous allocated object size is too limited for the new use?
        klee::klee_message("find corresponding real_address of load symbolic address %s", map_symbolic_address[base].get_ptr()->dump2().c_str());
        return map_symbolic_address[base];
    } else {
        klee::klee_message("create_symaddr_object");
        // yhao: create mo for non constant address
        // e.g. value load symbolic_address
        // create new mo and symbolic_address = mo->getBaseExpr();
        // do not consider address calculation
        // mainly for the case concrete address + symbolic offset
        //auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
        auto name = "obj("+base.get_ptr()->dump2()+")";
        klee::MemoryObject *mo = executor->create_mo(state, ty, ki->inst, name);
        //executor->un_eval(ki, 0, state).value = mo->getBaseExpr();
        klee::ref<klee::Expr> concrete_addr = mo->getBaseExpr();
        this->map_symbolic_address[base] = concrete_addr;
        this->map_address_symbolic[mo->getBaseExpr()] = base;
        klee::klee_message("Symaddr:%s Concreteaddr: %s", base.get_ptr()->dump2().c_str(), concrete_addr.get_ptr()->dump2().c_str());

        klee::ref<klee::Expr> one = klee::ConstantExpr::create(1, klee::Context::get().getPointerWidth());
        for(unsigned i=1; i< size; i++){
            base = AddExpr::create(base, one);
            concrete_addr =  AddExpr::create(concrete_addr, one);
            this->map_symbolic_address[base] = concrete_addr;
            this->map_address_symbolic[concrete_addr] = base;
            klee::klee_message("Symaddr:%s Concreteaddr: %s", base.get_ptr()->dump2().c_str(), concrete_addr.get_ptr()->dump2().c_str());
        }
        return mo->getBaseExpr();
    }
}

void kuc::UCListener::symbolic_before_load(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;
    klee_message("symbolic_before_load() base:%s", base.get_ptr()->dump2().c_str());
    //klee_message("executor->optimizer.optimizeExpr(base, true):%s", executor->optimizer.optimizeExpr(base, true).get_ptr()->dump2().c_str());
    //klee_message("klee::ConstraintManager::simplifyExpr(state.constraints, base):%s", klee::ConstraintManager::simplifyExpr(state.constraints, base).get_ptr()->dump2().c_str());
    auto *real_address = llvm::dyn_cast<klee::ConstantExpr>(base);
    if (real_address) {
        klee::klee_message("real_address");
    } else if (map_symbolic_address.find(base) != map_symbolic_address.end()) {
        klee::klee_message("find corresponding real_address of load symbolic address %s", map_symbolic_address[base].get_ptr()->dump2().c_str());
        executor->un_eval(ki, 0, state).value = map_symbolic_address[base];
    } else {
        bool find_equalsymaddr_result = false;
        find_equalsymaddr(state, base, find_equalsymaddr_result);
        if(find_equalsymaddr_result){
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
            //auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            auto name = "obj("+base.get_ptr()->dump2()+")";
            klee::MemoryObject *mo = executor->create_mo(state, ty, ki->inst, name);
            executor->un_eval(ki, 0, state).value = mo->getBaseExpr();
            this->map_symbolic_address[base] = mo->getBaseExpr();
            this->map_address_symbolic[mo->getBaseExpr()] = base;
            //yhao_print(mo->getBaseExpr()->print, str);
            klee::klee_message("Concrete base: %s", mo->getBaseExpr().get_ptr()->dump2().c_str());
        } else {
            klee::klee_message("symbolic address, type is not integer or pointer");
        }
        }
    }
}

// restore the symbolic address
void kuc::UCListener::symbolic_after_load(klee::ExecutionState &state, klee::KInstruction *ki) {
    klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;
    if (this->map_address_symbolic.find(base) != this->map_address_symbolic.end()){
        executor->un_eval(ki, 0, state).value = this->map_address_symbolic[base];
        klee_message("symbolic_after_load() restore sym addr:%s", this->map_address_symbolic[base].get_ptr()->dump2().c_str());
    }
}

void kuc::UCListener::symbolic_before_store(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;

    auto *real_address = llvm::dyn_cast<klee::ConstantExpr>(base);
    klee_message("symbolic_before_store() base:%s", base.get_ptr()->dump2().c_str());
    //klee_message("executor->optimizer.optimizeExpr(base, true):%s", executor->optimizer.optimizeExpr(base, true).get_ptr()->dump2().c_str());
    //klee_message("klee::ConstraintManager::simplifyExpr(state.constraints, base):%s", klee::ConstraintManager::simplifyExpr(state.constraints, base).get_ptr()->dump2().c_str());
    if (real_address) {
        klee::klee_message("real_address");
    } else if (map_symbolic_address.find(base) != map_symbolic_address.end()) {
        klee::klee_message("find corresponding real_address of store symbolic address %s", map_symbolic_address[base].get_ptr()->dump2().c_str());
        executor->un_eval(ki, 1, state).value = map_symbolic_address[base];
    } else {
        bool find_equalsymaddr_result = false;
        find_equalsymaddr(state, base, find_equalsymaddr_result);
        if(find_equalsymaddr_result){
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
            //auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            std::string name = base.get_ptr()->dump2();
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
}

// restore the symbolic address
void kuc::UCListener::symbolic_after_store(klee::ExecutionState &state, klee::KInstruction *ki) {
    klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;
    if (this->map_address_symbolic.find(base) != this->map_address_symbolic.end()){
        executor->un_eval(ki, 1, state).value = this->map_address_symbolic[base];
        klee_message("symbolic_after_store() restore sym addr:%s", this->map_address_symbolic[base].get_ptr()->dump2().c_str());
    }
}

void kuc::UCListener::find_equalsymaddr(klee::ExecutionState &state, klee::ref<klee::Expr> base, bool& find_equalsymaddr_result){
    // To Improve the performance, try to do the solve for once?
    ref<Expr> total_equal_expr = klee::ConstantExpr::create(0, Expr::Bool);
    bool any_equal_result = false;
    for (auto& pair:map_symbolic_address){
        klee::ref<klee::Expr> symbolic_address = pair.first;
        ref<Expr> equal_expr = EqExpr::create(symbolic_address, base);
        total_equal_expr = OrExpr::create(total_equal_expr, equal_expr);    
    }
    bool success = executor->solver->mustBeTrue(state.constraints, total_equal_expr, any_equal_result,
                                            state.queryMetaData);
    if (!any_equal_result){
        klee_message("find_equalsymaddr() no sym_addr equal base. No need to check one by one");
        return;
    }

    for (auto& pair:map_symbolic_address){
        klee::ref<klee::Expr> symbolic_address = pair.first;
        ref<Expr> equal_expr = EqExpr::create(symbolic_address, base);
        //klee_message("equal_expr:%s", equal_expr.get_ptr()->dump2().c_str());
        bool equal_result;
        bool success = executor->solver->mustBeTrue(state.constraints, equal_expr, equal_result,
                                                state.queryMetaData);
        if(equal_result){
            klee_message("base equals to previous sym_addr:%s", symbolic_address.get_ptr()->dump2().c_str());
            //base = symbolic_address;
            map_symbolic_address[base] = map_symbolic_address[symbolic_address];
            find_equalsymaddr_result = true;
            break;
        }
    }
    klee_message("find_equalsymaddr() map_symbolic_address.size():%u find_equalsymaddr_result:%d", map_symbolic_address.size(), find_equalsymaddr_result);
}

/*
void kuc::UCListener::symbolic_after_load(klee::ExecutionState &state, klee::KInstruction *ki) {
    std::string str;
    // check value of load, if it is pointer, create mo and symbolic os
    auto ty = ki->inst->getType();
    if (ty->isPointerTy() && ty->getPointerElementType()->isSized()) {
        // ignore the 0-sized type
        auto size = executor->kmodule->targetData->getTypeStoreSize(ty->getPointerElementType());
        klee_message("size : %lu", size.getKnownMinSize());
        if (size == 0) {
            klee_message("struct size is 0. don't create object for it");
            return;
        }
        // the return value (a pointer) of load instruction
        auto ret = executor->getDestCell(state, ki).value;
        if (ret->getKind() == klee::Expr::Constant) {
            return;
        }
        // type of base is pointer of pointer (char ** for example)
        klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;

        //klee_message("load ret symbolic: %s", ret.get_ptr()->dump2().c_str());
        if (map_symbolic_address.find(ret) != map_symbolic_address.end()) {
            klee::klee_message("find load ret symbolic in map_symbolic_address");
            auto value = map_symbolic_address[ret];
            klee::klee_message("corresponding concrete address: %s:", value.get_ptr()->dump2().c_str());
            executor->bindLocal(ki, state, value);
            executor->executeMemoryOperation(state, true, base, value, nullptr);
        } else {
            /// yu hao: create mo for non-constant pointer
            // e.g. symbolic pointer load address
            // create new mo and symbolic pointer = mo->getBaseExpr();
            klee::klee_message("make symbolic load ret concolic with creating a concolic object");
            std::string name;
            //std::string retstr = ret.get_ptr()->dump2();
            //klee::klee_message("retstr: %s  retstr.length():%u", retstr.c_str(), retstr.length());
            //if(retstr.substr(0,21) == "(ReadLSB w64 0 input_" && (retstr.length() == 23)) {
            //    name = "input_"+retstr.substr(21,1)+"(pointer)";
            //} else {
            //    name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            //}
            name = ret.get_ptr()->dump2();
            //std::string name = retstr;
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
*/

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
        if(skip_calltrace){
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
        if(skip_calltrace){
            goto create_return;
        }
        if (skip_functions.find(name) != skip_functions.end()) {
            klee::klee_message("in skip_functions");
            goto create_return;
        } 
        else if (skip_functions.find(simplifyfuncname(name)) != skip_functions.end()){
            klee::klee_message("in skip_functions");
            goto create_return;
        }
        else {
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
        std::string funcname;
        if (llvm::isa<llvm::InlineAsm>(fp)) {
            funcname = "asmcall";
        } else {
            if (f)
            {
                funcname = f->getName().str();
            } else {
                funcname = "indirectcall";
            }
        }
        auto name = create_global_var_name(ki, -1, funcname+"-call_return");
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

void kuc::UCListener::OOBWcheck(klee::ExecutionState &state, klee::KInstruction *ki) {
    bool OOBW = state.OOBW;
    if(OOBW) return;

    Expr::Width type;
    unsigned bytes;
    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::Load:{
            klee::ref<klee::Expr> base = executor->eval(ki, 0, state).value;
            type = executor->getWidthForLLVMType(ki->inst->getType());
            bytes = Expr::getMinBytesForWidth(type);
            OOB_check(state, base, bytes);
            break;
        }
        case llvm::Instruction::Store:{
            klee::ref<klee::Expr> base = executor->eval(ki, 1, state).value;
            klee::ref<klee::Expr> value = executor->eval(ki, 0, state).value;
            type = value->getWidth();
            bytes = Expr::getMinBytesForWidth(type);
            OOB_check(state, base, bytes);
            break;
        }
        case llvm::Instruction::GetElementPtr: {
            break;
            /*
            klee::ObjectPair op;
            bool success;
            klee::ref<klee::Expr> address = executor->eval(ki, 0, state).value;
            auto access_address = executor->getDestCell(state, ki).value;
            klee::ref<klee::Expr> GEPoffset = SubExpr::create(access_address, address);
            klee_message("GEP offset: %s", GEPoffset.get_ptr()->dump2().c_str());
            // if the address is really concrete (no mapped symbolic address), we don't need to check the mapping between symbolic addr and base object
            if (this->map_address_symbolic.find(address) == this->map_address_symbolic.end()){
                break;
            }
            // there is a symbolic address such as: concretebase+symoffset, thus we create a concrete address corresponding it
            // However, sometimes what we really need to access is the object at concretebase
            // Here we need to restore the concrete base and write to it
            klee_message("restore sym address with concrete addr: %s", address.get_ptr()->dump2().c_str());
            address = this->map_address_symbolic[address];
            klee_message("sym address: %s", address.get_ptr()->dump2().c_str());

            if (state.symaddr_base.find(address) != state.symaddr_base.end()){                
                klee::ref<klee::Expr> baseaddr = state.symaddr_base[address];
                klee_message("find address in symaddr_base mapping, the base addr: %s", baseaddr.get_ptr()->dump2().c_str());
                success = state.addressSpace.resolveOne(dyn_cast<klee::ConstantExpr>(baseaddr), op);
                if (!success) {break;}
                const klee::MemoryObject * object = op.first;
                const ObjectState *os = op.second;
                klee_message("Base corresponding obj addr: %lu obj size: %u", object->address, object->size);

                klee::ref<klee::Expr> objectbase = klee::ConstantExpr::create(object->address, klee::Context::get().getPointerWidth());
                ref<Expr> offset = object->getOffsetExpr(address);
                klee_message("symaddr offset at the base object: %s", offset.get_ptr()->dump2().c_str());
                offset = AddExpr::create(offset, GEPoffset);
                klee_message("GEP offset at the base object: %s", offset.get_ptr()->dump2().c_str());
                //SubExpr::create(address, objectbase);
                ref<Expr> check = UltExpr::create(offset, klee::ConstantExpr::create(object->size, klee::Context::get().getPointerWidth()));

                if(!object->issymsize.compare("True")){
                    ref<Expr> symsize = object->symsize;
                    klee_message("symbolic size of the base object: %s", symsize.get_ptr()->dump2().c_str());
                    check = UltExpr::create(offset, symsize);
                }

                bool inBounds;
                bool success = executor->solver->mustBeTrue(state.constraints, check, inBounds,
                                                state.queryMetaData);
                if (!success) { break;}
                if (!inBounds) {
                    klee_message("state.OOBW = true");
                    state.OOBW = true;
                }

            }*/

        }
        // For the modelled functions, we should check if OOB happen in advance
        case llvm::Instruction::Call: {
            auto cs = llvm::cast<llvm::CallBase>(ki->inst);
            llvm::Value *fp = cs->getCalledOperand();
            llvm::Function *f = executor->getTargetFunction(fp, state);
            if(!f) {
                break;}
            std::string name = f->getName().str();

            if (name == "memcpy"){
                ref<Expr> targetaddr = executor->eval(ki, 1, state).value;
                ref<Expr> len = executor->eval(ki, 3, state).value;
                targetaddr = AddExpr::create(targetaddr, len);
                targetaddr = SubExpr::create(targetaddr, klee::ConstantExpr::create(1, Context::get().getPointerWidth()));
                OOB_check(state, targetaddr, 1);
            }
        }
    }
}

// zheng
// used for separate symbolic parts and concrete parts of a given symbolic expression
// It may be used for finding the base of an symbolic address
void kuc::UCListener::separateConstantAndSymbolic(const ref<Expr> &expr, std::set<ref<Expr>> &constants, std::set<ref<Expr>> &symbolics) {
    if (expr->getKind() == Expr::Constant) {
        constants.insert(expr);
    } else if (expr->getKind() == Expr::Read || expr->getKind() == Expr::Concat) {
        // Read and Concat expressions are considered symbolic
        symbolics.insert(expr);
    } else {
        // Recursively process child expressions
        for (unsigned i = 0; i < expr->getNumKids(); ++i) {
            separateConstantAndSymbolic(expr->getKid(i), constants, symbolics);
        }
    }
}

// When there are multiple
void kuc::UCListener::extract_baseaddr(ref<Expr> &symaddr, ref<Expr> &baseaddr) {
    std::set<ref<Expr>> constants;
    std::set<ref<Expr>> symbolics;
    separateConstantAndSymbolic(symaddr, constants, symbolics);

    //int64_t largest_address = 0;
    klee_message("extract_baseaddr symaddr:%s", symaddr.get_ptr()->dump2().c_str());
    for (ref<Expr> constant : constants) {
        klee::ConstantExpr *CE = dyn_cast<klee::ConstantExpr>(constant);
        klee::klee_message("constant: %s", constant.get_ptr()->dump2().c_str());
        // Is it possible that there is no such a constant?
        if(CE->getZExtValue() > 1000000){
            klee::klee_message("baseaddr: %s", constant.get_ptr()->dump2().c_str());
            baseaddr = constant;
        }
    }
}

void kuc::UCListener::OOB_check(klee::ExecutionState &state, ref<Expr> targetaddr, unsigned bytes) {

    //Expr::Width type = (isWrite ? value->getWidth() :
    //                 getWidthForLLVMType(target->inst->getType()));
    //unsigned bytes = Expr::getMinBytesForWidth(type);
    klee_message("OOB_check() for targetaddr %s  bytes:%u", targetaddr.get_ptr()->dump2().c_str(), bytes);
    ref<Expr> baseaddress = klee::ConstantExpr::create(0, klee::Context::get().getPointerWidth());;
    extract_baseaddr(targetaddr, baseaddress);
    // Do we need a check whether targetbaseaddr is initialized?

    // Some objects are allocated outside the symbolic execution scope. 
    // For example, (Add w64 2 (ReadLSB w64 0 input_0)) (pointed by argument)
    klee::ConstantExpr *CE = dyn_cast<klee::ConstantExpr>(baseaddress);
    if(CE->getZExtValue() == 0){
        return;
    }

    ObjectPair op;
    bool success;
    success = state.addressSpace.resolveOne(cast<klee::ConstantExpr>(baseaddress), op);

    if (!success){
        klee_message("L1116 OOB may happen state.OOBW = true");
        state.OOBW = true;
        return;
    }

    const MemoryObject *mo = op.first;
    ref<Expr> offset = mo->getOffsetExpr(targetaddr);
    ref<Expr> check = mo->getBoundsCheckOffset(offset, bytes);
    klee::klee_message("check: %s", check.get_ptr()->dump2().c_str());

    if (!mo->issymsize.compare("True")){
        ref<Expr> symsize = mo->symsize;
        ref<Expr> offset2 = AddExpr::create(offset, klee::ConstantExpr::create(bytes, Context::get().getPointerWidth()));
        check = UleExpr::create(offset2, symsize);
        klee::klee_message("mo->issymsize True new check: %s", check.get_ptr()->dump2().c_str());
    }

    bool inBounds;
    success =  executor->solver->mustBeTrue(state.constraints, check, inBounds,
                                  state.queryMetaData);
    if (!success) {
        klee::klee_message("timeout in OOB_check");
        return;
    }

    if (!inBounds) {
        klee_message("L1123 OOB may happen state.OOBW = true");
        state.OOBW = true;
    } else {
        klee_message("L1123 OOB should not happen");
    }
}