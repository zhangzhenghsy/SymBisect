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

void kuc::UCListener::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    klee::klee_message("\n\nUCListener::beforeExecuteInstruction()");
    std::string str;
    //yhao_log(1, inst_to_strID(ki->inst));
    //yhao_log(1, dump_inst_booltin(ki->inst));
    klee::klee_message("ExecutionState &state: %p", &state);
    klee::klee_message("bb name i->getParent()->getName().str() %s",ki->inst->getParent()->getName().str().c_str());
    klee::klee_message("sourcecodeLine: %s %u:%u", ki->info->file.c_str(), ki->info->line, ki->info->column);
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
        yhao_print(operand->print, str);
        klee::klee_message("Inst operand %zu: %s", i, str.c_str());
        i++;
    }
    }
    
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
            print_constraints(state);
            break;
    	}
        case llvm::Instruction::Call: {
            //print_constraints(state);
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
            klee::ref<klee::Expr> value = executor->eval(ki, 0, state).value;
            klee::ref<klee::Expr> address = executor->eval(ki, 1, state).value;
            // if the address is really concrete (no mapped symbolic address), we don't need to check the mapping between symbolic addr and base object
            if (this->map_address_symbolic.find(address) == this->map_address_symbolic.end()){
                break;
            }
            address = this->map_address_symbolic[address];
            klee_message("sym address: %s", address.get_ptr()->dump2().c_str());
            //if (klee::ConstantExpr* CE1 = dyn_cast<klee::ConstantExpr>(address)) {
            //    break;
            //}
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
                for (offset = 0 ; offset < (uint64_t)object->size; offset += size) {
                    loop ++;
                    if (loop > 32) break;
                    ref<Expr> Offset = klee::ConstantExpr::create(offset, klee::Context::get().getPointerWidth());
                    ref<Expr> currentaddr = AddExpr::create(objectbase, Offset);
                    ref<Expr> oldvalue = os->read(offset, size*8);

                    bool res;
                    klee_message("currentaddr: %s", currentaddr.get_ptr()->dump2().c_str());
                    klee_message("address: %s", address.get_ptr()->dump2().c_str());
                    ref<Expr> condition = EqExpr::create(currentaddr, address);
                    bool success = executor->solver->mayBeTrue(state.constraints, condition, res,
                                  state.queryMetaData);
                    if (!res) { 
                        klee_message("address cannot equal current address, skip. currentaddr: %s", currentaddr.get_ptr()->dump2().c_str());
                        continue; 
                    }
                    auto name = "["+currentaddr.get_ptr()->dump2()+"]" + "(symvar)";
                    ref<Expr> currentvalue = executor->manual_make_symbolic(name, size, size*8);
                    ref<Expr> newconstraint = OrExpr::create(EqExpr::create(currentvalue, oldvalue), EqExpr::create(currentvalue, value));
                    klee_message("newconstraint: %s", newconstraint.get_ptr()->dump2().c_str());
                    executor->executeMemoryOperation(state, true, currentaddr, currentvalue, 0);
                    executor->addConstraint(state, newconstraint);
                }
            }
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
            //klee::klee_message("Load Inst value: %s", str.c_str());
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
    skip_functions.insert("llvm.read_register.i64");
    skip_functions.insert("llvm.write_register.i64");
    skip_functions.insert("nla_data");
    if (skip_functions.find(name) != skip_functions.end()) {
        klee::klee_message("skip function: %s",name.c_str());
        return true;
    }
    if (simplifyname == "")
     if (skip_functions.find(simplifyname) != skip_functions.end()) {
        klee::klee_message("skip function: %s",name.c_str());
        return true;
    }
    if(skip_calltrace_distance(state, ki)){
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
bool kuc::UCListener::skip_calltrace_distance(klee::ExecutionState &state, klee::KInstruction *ki) {
    // if there is no "97_calltrace" in config, we don't want to skip any functions.
    if (Calltrace.size() == 0){
        return false;
    }
    int threshold_distance = Calltrace.size() + 1;
    if(threshold_distance < 6) {
        threshold_distance = 6;
    }
    //klee::klee_message("threshold_distance: %d", threshold_distance);
    bool Insametrace = true;
    int currentdistance = Calltrace.size();

    int endIndex = state.stack.size() - 1;
    std::string calltracefuncname;
    for (int i = 0; i <= endIndex; i++) {
      auto const &sf = state.stack.at(i);
      klee::KFunction* kf = sf.kf;
      llvm::Function* f = kf ? kf->function : 0;
      if (Insametrace) {
        calltracefuncname = Calltrace[i];
      }
      if (f)
      {
          std::string funcname = f->getName().str();
            if (funcname != calltracefuncname) {
                Insametrace = false;
            }
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
    
    if (currentdistance > threshold_distance)
    {
        klee::klee_message("currentdistance :%d threshold_distance: %d skip the function due calltrace_distance", currentdistance, threshold_distance);
        return true;
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
    } else {
        this->count[name] = this->count[name] + 1;
    }
    name += "-" + std::to_string(this->count[name]);
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
            //auto name = this->create_global_var_name(ki->inst, 0, "symbolic_address");
            auto name = base.get_ptr()->dump2();
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
