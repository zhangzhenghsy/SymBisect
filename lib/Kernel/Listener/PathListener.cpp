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
#include <iostream>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <queue>
using namespace std;

kuc::PathListener::PathListener(klee::Executor *executor) : Listener(executor) {
    config = executor->config;
    if (config.contains("4_target_line_list") && config["4_target_line_list"].is_array()) {
        for (const auto &temp: config["4_target_line_list"]) {
            target_lines.insert(temp.get<std::string>());
        }
    }

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
    if (config.contains("90_low_priority_line_list") && config["90_low_priority_line_list"].is_array()) {
        for (const auto &temp: config["90_low_priority_line_list"]) {
            low_priority_lines.insert(temp.get<std::string>());
        }
    }

    if (config.contains("92_indirectcall")){
        indirectcall_map = config["92_indirectcall"];
    }
    if (config.contains("93_whitelist")){
        std::map<std::string, std::vector<std::string>> whitelist = config["93_whitelist"];
        for (const auto &temp: whitelist) {
            for (const auto &whiteline: temp.second){
                whitelist_map[temp.first].insert(whiteline);
            }
        }
    }
    if (config.contains("95_kernelversion")){
        kernelversion = config["95_kernelversion"];
    } else {
        kernelversion = "v5.4";
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

void kuc::PathListener:: BB_reachableBBs(BasicBlock * BB) {
    std::string keyBBname = BB->getName().str();
    if(BB_reachBBs.find(keyBBname) != BB_reachBBs.end()){
        return;
    }
    std::unordered_set<BasicBlock *> reachable;
    std::queue<BasicBlock *> worklist;
    worklist.push(BB);
    while (!worklist.empty()) {
        BasicBlock *front = worklist.front();
        worklist.pop();
        for (BasicBlock *succ : successors(front)) {
            if (reachable.count(succ) == 0) {
            /// We need the check here to ensure that we don't run infinitely if the CFG has a loop in it
            /// i.e. the BB reaches itself directly or indirectly
                worklist.push(succ);
                reachable.insert(succ);
            }
        }
    }
    for (BasicBlock * localBB:reachable) {
        BB_reachBBs[keyBBname].insert(localBB->getName().str());
    }
  //return reachable;
}

bool kuc::PathListener::BB1_reach_BB2(BasicBlock * A, BasicBlock * B){
    std::string keyBBname = A->getName().str();
    set<std::string> AreachableBBs = BB_reachBBs[keyBBname];
    if (AreachableBBs.find(B->getName().str()) != AreachableBBs.end()){
      return true;
    }
    return false;
}

// Br Inst, A->B, A->C.  if C->A or B->A, then we know it's a loop
bool kuc::PathListener::Isaloop(BasicBlock * A, BasicBlock * B, BasicBlock * C){
  return BB1_reach_BB2(B, A) || BB1_reach_BB2(C, A);
}


void kuc::PathListener::beforeExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {

    //klee::ref<klee::ConstantExpr> True = klee::ConstantExpr::create(true, 8);
    //klee::klee_message("test True expr: %s",True.ptr->dump2().c_str());
    klee::klee_message("PathListener::beforeExecuteInstruction()");

    auto line_info = dump_inst_sourceinfo(ki->inst);
    if (line_info != ""){
        std::size_t pos = line_info.find("source/");
        line_info = line_info.substr(pos+1);
        state.completecoveredLines.insert(line_info);
        klee::klee_message("insert new line in completecoveredLines: %s", line_info.c_str());

        std::set<std::string> coveredlines = state.completecoveredLines;
        // Can be used for, given a line, we must execute line2 before. Otherwise terminate the state
        if (this->whitelist_map.find(line_info) != this->whitelist_map.end())
        {
                std::set<std::string> whitelist = this->whitelist_map[line_info];
                for (auto whiteline:whitelist){
                    klee::klee_message("whiteline: %s", whiteline.c_str());
                    if (coveredlines.find(whiteline) == coveredlines.end()){
                        klee::klee_message("%s not in coveredlines, terminate the state", whiteline.c_str());
                        this->executor->terminateState(state);
                    }
                }
        }
    }

    int endIndex = state.stack.size() - 1;
    string calltrace = "";
    for (int i = 0; i <= endIndex; i++) {
        auto const &sf = state.stack.at(i);
        klee::KFunction* kf = sf.kf;
        llvm::Function* f = kf ? kf->function : 0;
        if (f)
        {
            calltrace.append(f->getName().str());
            calltrace.append("--");
        }
    }
    calltrace.pop_back();
    calltrace.pop_back();
    klee::klee_message("call trace: %s",calltrace.c_str());

    switch (ki->inst->getOpcode()) {
        case llvm::Instruction::Call: {
            //klee::klee_message("print state.completecoveredLines");
            std::set<std::string> coveredlines = state.completecoveredLines;

            auto line_info = dump_inst_sourceinfo(ki->inst);
            std::size_t pos = line_info.find("source/");
            line_info = line_info.substr(pos+1);
            //klee::klee_message("key line_info: %s", line_info.c_str());

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



            // pick function form function_map(json)
            if (this->indirectcall_map.find(line_info) != this->indirectcall_map.end())
            {
                std::string callee_func = this->indirectcall_map[line_info];
                auto m = this->executor->get_module();
                llvm::Function *f = m->getFunction(callee_func);
                auto f_address = klee::Expr::createPointer(reinterpret_cast<std::uint64_t>(f));
                klee::klee_message("callee_func found: %s f(p): %p f(s): %s", f->getName().str().c_str(), f, f_address.ptr->dump2().c_str());
                executor->un_eval(ki, 0, state).value = f_address;
                break;
            }

	    break;

            // pick function form GlobalCtx(MLTA)
            std::set<llvm::Function *> callee_function_set;
            auto callee = GlobalCtx.Callees[ci];
            for (auto temp_f: callee) {
                callee_function_set.insert(temp_f);
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
                    //klee::ref<klee::ConstantExpr> True = klee::ConstantExpr::create(true, 8);
                    klee::ref<klee::Expr> temp_symbolic_cond =klee::EqExpr::create(klee::Executor::manual_make_symbolic(name, 1, 8), temp_address);
                    v = klee::SelectExpr::create(temp_symbolic_cond, temp_address, v);
                }
                executor->un_eval(ki, 0, state).value = v;
            }
            break;
        }
        case llvm::Instruction::Br:{
	    // implement BB choice code later (now they are in executor)
            /*BranchInst *bi = cast<BranchInst>(ki->inst);
            if (bi->isUnconditional())
                break;
            BasicBlock * BB = bi->getParent();
            BB_reachableBBs(BB);

            std::string keyBBname = BB->getName().str();
            if (bi->isUnconditional()) break;
            BasicBlock * BB1 = bi->getSuccessor(0);
            BB_reachableBBs(BB1);
            BasicBlock * BB2 = bi->getSuccessor(1);
            BB_reachableBBs(BB2);*/
            // generate the BB_reachBBs and store the info in BB_reachBBs
            break;
            // move the loop limit terminate to Executor.cpp
            /*
            Instruction *i = ki->inst;
            BranchInst *bi = cast<BranchInst>(i);
            if (bi->isUnconditional()) {
                break;
            }
            klee::ref<klee::Expr> cond = executor->eval(ki, 0, state).value;
            std::string conditionstr = cond.get_ptr()->dump2();
            //std::string conditionstr = executor->eval(ki, 0, state).value.get_ptr()->dump2();
            if (conditionstr == "true" || conditionstr == "false")
            {
                break;
            }
            string BBname = ki->inst->getParent()->getName().str();
            // for Intrinsic function no need to set the limit
            if (BBname.find("bc-") == std::string::npos){
                break;
            }
            BBname = BBname.substr(BBname.find("bc-")+3);
            BBname = BBname.substr(BBname.find("-")+1);
            string BBkey = calltrace+"-"+BBname;
            if (state.BBcount.find(BBkey) == state.BBcount.end()){
                state.BBcount[BBkey] = 1;
            } else {
                state.BBcount[BBkey] += 1;
            }
            klee::klee_message("BBkey: %s  count: %u", BBkey.c_str(), state.BBcount[BBkey]);
            // qestion: what if there is an constant time loop which requires loop for more than 100
            // maybe just do this check when both branches are possible?
            if (state.BBcount[BBkey] > looplimit) {
                klee::klee_message("reach loop limit, terminate the state");
                this->executor->terminateState(state);
            }
            */
        }
    }
}

bool kuc::PathListener::OOBWcheck(klee::ExecutionState &state, klee::KInstruction *ki) {
    bool OOBW = state.OOBW;
    return OOBW;
}

std::string simplifylineinfo(string lineinfo) {
    stringstream test(lineinfo);
    string segment;
    vector<std::string> seglist;

    while(std::getline(test, segment, '/'))
    {
        seglist.push_back(segment);
    }

    vector<string> vector1, vector2;
    vector<string>::iterator pos;
    while (find(seglist.begin(), seglist.end(), "..") != seglist.end()) {
        pos  = std::find(seglist.begin(), seglist.end(), "..");
        vector1 = std::vector<string>(seglist.begin(), pos-1);
        vector2 = std::vector<string>(pos+1, seglist.end());
        vector1.insert(vector1.end(), vector2.begin(), vector2.end());
        seglist = vector1;
    }

    string simplifylineinfo ;
    for (pos = seglist.begin(); pos < seglist.end(); pos++) {
        if(*pos == ".") continue;
        simplifylineinfo += *pos;
        simplifylineinfo += "/";
    }
    simplifylineinfo = simplifylineinfo.substr(0, simplifylineinfo.length()-1);
    return simplifylineinfo;
}
void kuc::PathListener::afterExecuteInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {

    auto bb = ki->inst->getParent();
    auto name_bb = bb->getName().str();
    auto name_l = dump_inst_sourceinfo(ki->inst);
    auto name_f = get_real_function_name(bb->getParent());
    string simple_name_l = simplifylineinfo(name_l);
    if (target_bbs.find(name_bb) != target_bbs.end()) {
        this->executor->haltExecution = true;
    }
    // for low_priority_bbs
    if (low_priority_bbs.find(name_bb) != low_priority_bbs.end()) {
        klee::klee_message("%s is in low_priority_bbs terminate the state", name_bb.c_str());
        this->executor->terminateState(state);
        klee::klee_message("tmptest terminate the state done");
    }
    // for low_priority_functions   
    else if (low_priority_functions.find(name_f) != low_priority_functions.end()) {
        this->executor->terminateState(state);
    }
    else if (low_priority_lines.find(name_l) != low_priority_lines.end()) {
        klee::klee_message("reach low priority line list terminate the state %s", name_l.c_str());
        this->executor->terminateState(state);
    }
    else if (simple_name_l != name_l) {
        if (low_priority_lines.find(simple_name_l) != low_priority_lines.end()) {
            klee::klee_message("reach low priority line list(after simplify) terminate the state %s", simple_name_l.c_str());
            this->executor->terminateState(state);
        }
    }
    //klee::klee_message("simple_name_l: %s", simple_name_l.c_str());
    else if (target_lines.find(simple_name_l) != target_lines.end()) {
        klee::klee_message("reach target line, do vulnerability check");
        bool result = OOBWcheck(state, ki);
        if (result) {
            klee::klee_message("OOB detected in target line");
            this->executor->haltExecution = true;
        }
    }
    state.OOBW = false;
}


void kuc::PathListener::afterRun(klee::ExecutionState &state) {

}

bool kuc::PathListener::CallInstruction(klee::ExecutionState &state, klee::KInstruction *ki) {
    return false;
}

void kuc::PathListener::executionFailed(klee::ExecutionState &state, klee::KInstruction *ki) {

}
