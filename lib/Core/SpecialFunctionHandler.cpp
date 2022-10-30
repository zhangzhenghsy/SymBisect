//===-- SpecialFunctionHandler.cpp ----------------------------------------===//
//
//                     The KLEE Symbolic Virtual Machine
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===//

#include "SpecialFunctionHandler.h"

#include "ExecutionState.h"
#include "Executor.h"
#include "Memory.h"
#include "MemoryManager.h"
#include "MergeHandler.h"
#include "Searcher.h"
#include "StatsTracker.h"
#include "TimingSolver.h"

#include "klee/Module/KInstruction.h"
#include "klee/Module/KModule.h"
#include "klee/Solver/SolverCmdLine.h"
#include "klee/Support/Casting.h"
#include "klee/Support/Debug.h"
#include "klee/Support/ErrorHandling.h"
#include "klee/Support/OptionCategories.h"

#include "llvm/ADT/Twine.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"

#include <errno.h>
#include <sstream>

#include "../Kernel/ToolLib/llvm_related.h"

using namespace llvm;
using namespace klee;

namespace {
cl::opt<bool>
    ReadablePosix("readable-posix-inputs", cl::init(false),
                  cl::desc("Prefer creation of POSIX inputs (command-line "
                           "arguments, files, etc.) with human readable bytes. "
                           "Note: option is expensive when creating lots of "
                           "tests (default=false)"),
                  cl::cat(TestGenCat));

cl::opt<bool>
    SilentKleeAssume("silent-klee-assume", cl::init(false),
                     cl::desc("Silently terminate paths with an infeasible "
                              "condition given to klee_assume() rather than "
                              "emitting an error (default=false)"),
                     cl::cat(TerminationCat));
} // namespace

/// \todo Almost all of the demands in this file should be replaced
/// with terminateState calls.

///

// FIXME: We are more or less committed to requiring an intrinsic
// library these days. We can move some of this stuff there,
// especially things like realloc which have complicated semantics
// w.r.t. forking. Among other things this makes delayed query
// dispatch easier to implement.
static SpecialFunctionHandler::HandlerInfo handlerInfo[] = {
#define add(name, handler, ret) { name, \
                                  &SpecialFunctionHandler::handler, \
                                  false, ret, false }
#define addDNR(name, handler) { name, \
                                &SpecialFunctionHandler::handler, \
                                true, false, false }
  addDNR("__assert_rtn", handleAssertFail),
  addDNR("__assert_fail", handleAssertFail),
  addDNR("__assert", handleAssertFail),
  addDNR("_assert", handleAssert),
  addDNR("abort", handleAbort),
  addDNR("_exit", handleExit),
  { "exit", &SpecialFunctionHandler::handleExit, true, false, true },
  addDNR("klee_abort", handleAbort),
  addDNR("klee_silent_exit", handleSilentExit),
  addDNR("klee_report_error", handleReportError),
  add("calloc", handleCalloc, true),
  add("free", handleFree, false),
  add("klee_assume", handleAssume, false),
  add("klee_check_memory_access", handleCheckMemoryAccess, false),
  add("klee_get_valuef", handleGetValue, true),
  add("klee_get_valued", handleGetValue, true),
  add("klee_get_valuel", handleGetValue, true),
  add("klee_get_valuell", handleGetValue, true),
  add("klee_get_value_i32", handleGetValue, true),
  add("klee_get_value_i64", handleGetValue, true),
  add("klee_define_fixed_object", handleDefineFixedObject, false),
  add("klee_get_obj_size", handleGetObjSize, true),
  add("klee_get_errno", handleGetErrno, true),
#ifndef __APPLE__
  add("__errno_location", handleErrnoLocation, true),
#else
  add("__error", handleErrnoLocation, true),
#endif
  add("klee_is_symbolic", handleIsSymbolic, true),
  add("klee_make_symbolic", handleMakeSymbolic, false),
  add("klee_mark_global", handleMarkGlobal, false),
  add("klee_open_merge", handleOpenMerge, false),
  add("klee_close_merge", handleCloseMerge, false),
  add("klee_prefer_cex", handlePreferCex, false),
  add("klee_posix_prefer_cex", handlePosixPreferCex, false),
  add("klee_print_expr", handlePrintExpr, false),
  add("klee_print_range", handlePrintRange, false),
  add("klee_set_forking", handleSetForking, false),
  add("klee_stack_trace", handleStackTrace, false),
  add("klee_warning", handleWarning, false),
  add("klee_warning_once", handleWarningOnce, false),
  add("malloc", handleMalloc, true),
  add("memalign", handleMemalign, true),
  add("realloc", handleRealloc, true),
  add("_klee_eh_Unwind_RaiseException_impl", handleEhUnwindRaiseExceptionImpl, false),

  // operator delete[](void*)
  add("_ZdaPv", handleDeleteArray, false),
  // operator delete(void*)
  add("_ZdlPv", handleDelete, false),

  // operator new[](unsigned int)
  add("_Znaj", handleNewArray, true),
  // operator new(unsigned int)
  add("_Znwj", handleNew, true),

  // FIXME-64: This is wrong for 64-bit long...

  // operator new[](unsigned long)
  add("_Znam", handleNewArray, true),
  // operator new(unsigned long)
  add("_Znwm", handleNew, true),

  // Run clang with -fsanitize=signed-integer-overflow and/or
  // -fsanitize=unsigned-integer-overflow
  add("__ubsan_handle_add_overflow", handleAddOverflow, false),
  add("__ubsan_handle_sub_overflow", handleSubOverflow, false),
  add("__ubsan_handle_mul_overflow", handleMulOverflow, false),
  add("__ubsan_handle_divrem_overflow", handleDivRemOverflow, false),
  add("klee_eh_typeid_for", handleEhTypeid, true),

  // yu hao: handle kernel function
  add("__kmalloc", handleKmalloc, true),
  add("iminor", handleIminor, true),

  // zheng: handle kernel function
  add("memcpy", handleMemcpy, false),
  add("strncpy_from_user", handleStrncpy_from_user, true),
  add("user_path_at", handleUser_path_at, true),
  add("vzalloc", handleVzalloc, true),
  add("_copy_from_user", handleMemcpyRZ, true),
  add("_copy_to_user", handleMemcpyRZ, true),
  add("strcmp", handleStrcmp, true),
  add("strchr", handleStrchr, true),
  add("memset", handleMemset, true),
  // should we consider the page padding for vmalloc?
  add("vmalloc", handleMalloc, true),
#undef addDNR
#undef add
};

SpecialFunctionHandler::const_iterator SpecialFunctionHandler::begin() {
  return SpecialFunctionHandler::const_iterator(handlerInfo);
}

SpecialFunctionHandler::const_iterator SpecialFunctionHandler::end() {
  // NULL pointer is sentinel
  return SpecialFunctionHandler::const_iterator(0);
}

SpecialFunctionHandler::const_iterator& SpecialFunctionHandler::const_iterator::operator++() {
  ++index;
  if ( index >= SpecialFunctionHandler::size())
  {
    // Out of range, return .end()
    base=0; // Sentinel
    index=0;
  }

  return *this;
}

int SpecialFunctionHandler::size() {
	return sizeof(handlerInfo)/sizeof(handlerInfo[0]);
}

SpecialFunctionHandler::SpecialFunctionHandler(Executor &_executor) 
  : executor(_executor) {}

void SpecialFunctionHandler::prepare(
    std::vector<const char *> &preservedFunctions) {
  unsigned N = size();

  for (unsigned i=0; i<N; ++i) {
    HandlerInfo &hi = handlerInfo[i];
    Function *f = executor.kmodule->module->getFunction(hi.name);

    // No need to create if the function doesn't exist, since it cannot
    // be called in that case.
    if (f && (!hi.doNotOverride || f->isDeclaration())) {
      preservedFunctions.push_back(hi.name);
      // Make sure NoReturn attribute is set, for optimization and
      // coverage counting.
      if (hi.doesNotReturn)
        f->addFnAttr(Attribute::NoReturn);

      // Change to a declaration since we handle internally (simplifies
      // module and allows deleting dead code).
      if (!f->isDeclaration())
        f->deleteBody();
    }
  }
}

void SpecialFunctionHandler::bind() {
  unsigned N = sizeof(handlerInfo)/sizeof(handlerInfo[0]);

  for (unsigned i=0; i<N; ++i) {
    HandlerInfo &hi = handlerInfo[i];
    Function *f = executor.kmodule->module->getFunction(hi.name);
    
    if (f && (!hi.doNotOverride || f->isDeclaration()))
      handlers[f] = std::make_pair(hi.handler, hi.hasReturnValue);
  }
}


bool SpecialFunctionHandler::handle(ExecutionState &state, 
                                    Function *f,
                                    KInstruction *target,
                                    std::vector< ref<Expr> > &arguments) {
  handlers_ty::iterator it = handlers.find(f);
  if (it != handlers.end()) {    
    Handler h = it->second.first;
    bool hasReturnValue = it->second.second;
     // FIXME: Check this... add test?
    if (!hasReturnValue && !target->inst->use_empty()) {
      executor.terminateStateOnExecError(state, 
                                         "expected return value from void special function");
    } else {
      (this->*h)(state, target, arguments);
    }
    return true;
  } else {
    return false;
  }
}

/****/

// reads a concrete string from memory
std::string 
SpecialFunctionHandler::readStringAtAddress(ExecutionState &state, 
                                            ref<Expr> addressExpr) {
  ObjectPair op;
  addressExpr = executor.toUnique(state, addressExpr);
  if (!isa<ConstantExpr>(addressExpr)) {
    executor.terminateStateOnError(
        state, "Symbolic string pointer passed to one of the klee_ functions",
        Executor::TerminateReason::User);
    return "";
  }
  ref<ConstantExpr> address = cast<ConstantExpr>(addressExpr);
  if (!state.addressSpace.resolveOne(address, op)) {
    executor.terminateStateOnError(
        state, "Invalid string pointer passed to one of the klee_ functions",
        Executor::TerminateReason::User);
    return "";
  }
  const MemoryObject *mo = op.first;
  const ObjectState *os = op.second;

  auto relativeOffset = mo->getOffsetExpr(address);
  // the relativeOffset must be concrete as the address is concrete
  size_t offset = cast<ConstantExpr>(relativeOffset)->getZExtValue();

  std::ostringstream buf;
  char c = 0;
  for (size_t i = offset; i < mo->size; ++i) {
    ref<Expr> cur = os->read8(i);
    cur = executor.toUnique(state, cur);
    assert(isa<ConstantExpr>(cur) && 
           "hit symbolic char while reading concrete string");
    c = cast<ConstantExpr>(cur)->getZExtValue(8);
    if (c == '\0') {
      // we read the whole string
      break;
    }

    buf << c;
  }

  if (c != '\0') {
      klee_warning_once(0, "String not terminated by \\0 passed to "
                           "one of the klee_ functions");
  }

  return buf.str();
}

/****/

void SpecialFunctionHandler::handleAbort(ExecutionState &state,
                           KInstruction *target,
                           std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==0 && "invalid number of arguments to abort");
  executor.terminateStateOnError(state, "abort failure", Executor::Abort);
}

void SpecialFunctionHandler::handleExit(ExecutionState &state,
                           KInstruction *target,
                           std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 && "invalid number of arguments to exit");
  executor.terminateStateOnExit(state);
}

void SpecialFunctionHandler::handleSilentExit(ExecutionState &state,
                                              KInstruction *target,
                                              std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 && "invalid number of arguments to exit");
  executor.terminateState(state);
}

void SpecialFunctionHandler::handleAssert(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==3 && "invalid number of arguments to _assert");  
  executor.terminateStateOnError(state,
				 "ASSERTION FAIL: " + readStringAtAddress(state, arguments[0]),
				 Executor::Assert);
}

void SpecialFunctionHandler::handleAssertFail(ExecutionState &state,
                                              KInstruction *target,
                                              std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==4 && "invalid number of arguments to __assert_fail");
  executor.terminateStateOnError(state,
				 "ASSERTION FAIL: " + readStringAtAddress(state, arguments[0]),
				 Executor::Assert);
}

void SpecialFunctionHandler::handleReportError(ExecutionState &state,
                                               KInstruction *target,
                                               std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==4 && "invalid number of arguments to klee_report_error");
  
  // arguments[0], arguments[1] are file, line
  executor.terminateStateOnError(state,
				 readStringAtAddress(state, arguments[2]),
				 Executor::ReportError,
				 readStringAtAddress(state, arguments[3]).c_str());
}

void SpecialFunctionHandler::handleOpenMerge(ExecutionState &state,
    KInstruction *target,
    std::vector<ref<Expr> > &arguments) {
  if (!UseMerge) {
    klee_warning_once(0, "klee_open_merge ignored, use '-use-merge'");
    return;
  }

  state.openMergeStack.push_back(
      ref<MergeHandler>(new MergeHandler(&executor, &state)));

  if (DebugLogMerge)
    llvm::errs() << "open merge: " << &state << "\n";
}

void SpecialFunctionHandler::handleCloseMerge(ExecutionState &state,
    KInstruction *target,
    std::vector<ref<Expr> > &arguments) {
  if (!UseMerge) {
    klee_warning_once(0, "klee_close_merge ignored, use '-use-merge'");
    return;
  }
  Instruction *i = target->inst;

  if (DebugLogMerge)
    llvm::errs() << "close merge: " << &state << " at [" << *i << "]\n";

  if (state.openMergeStack.empty()) {
    std::ostringstream warning;
    warning << &state << " ran into a close at " << i << " without a preceding open";
    klee_warning("%s", warning.str().c_str());
  } else {
    assert(executor.mergingSearcher->inCloseMerge.find(&state) ==
               executor.mergingSearcher->inCloseMerge.end() &&
           "State cannot run into close_merge while being closed");
    executor.mergingSearcher->inCloseMerge.insert(&state);
    state.openMergeStack.back()->addClosedState(&state, i);
    state.openMergeStack.pop_back();
  }
}

void SpecialFunctionHandler::handleNew(ExecutionState &state,
                         KInstruction *target,
                         std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==1 && "invalid number of arguments to new");

  executor.executeAlloc(state, arguments[0], false, target);
}

void SpecialFunctionHandler::handleDelete(ExecutionState &state,
                            KInstruction *target,
                            std::vector<ref<Expr> > &arguments) {
  // FIXME: Should check proper pairing with allocation type (malloc/free,
  // new/delete, new[]/delete[]).

  // XXX should type check args
  assert(arguments.size()==1 && "invalid number of arguments to delete");
  executor.executeFree(state, arguments[0]);
}

void SpecialFunctionHandler::handleNewArray(ExecutionState &state,
                              KInstruction *target,
                              std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==1 && "invalid number of arguments to new[]");
  executor.executeAlloc(state, arguments[0], false, target);
}

void SpecialFunctionHandler::handleDeleteArray(ExecutionState &state,
                                 KInstruction *target,
                                 std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==1 && "invalid number of arguments to delete[]");
  executor.executeFree(state, arguments[0]);
}

void SpecialFunctionHandler::handleMalloc(ExecutionState &state,
                                  KInstruction *target,
                                  std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==1 && "invalid number of arguments to malloc");
  executor.executeAlloc(state, arguments[0], false, target);
}

void SpecialFunctionHandler::handleVzalloc(ExecutionState &state,
                                  KInstruction *target,
                                  std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 && "invalid number of arguments to malloc");
  executor.executeAlloc(state, arguments[0], false, target);
}

void SpecialFunctionHandler::handleMemalign(ExecutionState &state,
                                            KInstruction *target,
                                            std::vector<ref<Expr>> &arguments) {
  if (arguments.size() != 2) {
    executor.terminateStateOnError(state,
      "Incorrect number of arguments to memalign(size_t alignment, size_t size)",
      Executor::User);
    return;
  }

  std::pair<ref<Expr>, ref<Expr>> alignmentRangeExpr =
      executor.solver->getRange(state.constraints, arguments[0],
                                state.queryMetaData);
  ref<Expr> alignmentExpr = alignmentRangeExpr.first;
  auto alignmentConstExpr = dyn_cast<ConstantExpr>(alignmentExpr);

  if (!alignmentConstExpr) {
    executor.terminateStateOnError(state,
      "Could not determine size of symbolic alignment",
      Executor::User);
    return;
  }

  uint64_t alignment = alignmentConstExpr->getZExtValue();

  // Warn, if the expression has more than one solution
  if (alignmentRangeExpr.first != alignmentRangeExpr.second) {
    klee_warning_once(
        0, "Symbolic alignment for memalign. Choosing smallest alignment");
  }

  executor.executeAlloc(state, arguments[1], false, target, false, 0,
                        alignment);
}

void SpecialFunctionHandler::handleEhUnwindRaiseExceptionImpl(
    ExecutionState &state, KInstruction *target,
    std::vector<ref<Expr>> &arguments) {
  assert(arguments.size() == 1 &&
         "invalid number of arguments to _klee_eh_Unwind_RaiseException_impl");

  ref<ConstantExpr> exceptionObject = dyn_cast<ConstantExpr>(arguments[0]);
  if (!exceptionObject) {
    executor.terminateStateOnError(state,
                                   "Internal error: Symbolic exception pointer",
                                   Executor::Unhandled);
    return;
  }

  if (isa_and_nonnull<SearchPhaseUnwindingInformation>(
          state.unwindingInformation.get())) {
    executor.terminateStateOnExecError(
        state,
        "Internal error: Unwinding restarted during an ongoing search phase");
    return;
  }

  state.unwindingInformation =
      std::make_unique<SearchPhaseUnwindingInformation>(exceptionObject,
                                                        state.stack.size() - 1);

  executor.unwindToNextLandingpad(state);
}

void SpecialFunctionHandler::handleEhTypeid(ExecutionState &state,
                                            KInstruction *target,
                                            std::vector<ref<Expr>> &arguments) {
  assert(arguments.size() == 1 &&
         "invalid number of arguments to klee_eh_typeid_for");

  executor.bindLocal(target, state, executor.getEhTypeidFor(arguments[0]));
}

void SpecialFunctionHandler::handleAssume(ExecutionState &state,
                            KInstruction *target,
                            std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 && "invalid number of arguments to klee_assume");
  
  ref<Expr> e = arguments[0];
  
  if (e->getWidth() != Expr::Bool)
    e = NeExpr::create(e, ConstantExpr::create(0, e->getWidth()));
  
  bool res;
  bool success __attribute__((unused)) = executor.solver->mustBeFalse(
      state.constraints, e, res, state.queryMetaData);
  assert(success && "FIXME: Unhandled solver failure");
  if (res) {
    if (SilentKleeAssume) {
      executor.terminateState(state);
    } else {
      executor.terminateStateOnError(state,
                                     "invalid klee_assume call (provably false)",
                                     Executor::User);
    }
  } else {
    executor.addConstraint(state, e);
  }
}

void SpecialFunctionHandler::handleIsSymbolic(ExecutionState &state,
                                KInstruction *target,
                                std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 && "invalid number of arguments to klee_is_symbolic");

  executor.bindLocal(target, state, 
                     ConstantExpr::create(!isa<ConstantExpr>(arguments[0]),
                                          Expr::Int32));
}

void SpecialFunctionHandler::handlePreferCex(ExecutionState &state,
                                             KInstruction *target,
                                             std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==2 &&
         "invalid number of arguments to klee_prefex_cex");

  ref<Expr> cond = arguments[1];
  if (cond->getWidth() != Expr::Bool)
    cond = NeExpr::create(cond, ConstantExpr::alloc(0, cond->getWidth()));

  Executor::ExactResolutionList rl;
  executor.resolveExact(state, arguments[0], rl, "prefex_cex");
  
  assert(rl.size() == 1 &&
         "prefer_cex target must resolve to precisely one object");

  rl[0].first.first->cexPreferences.push_back(cond);
}

void SpecialFunctionHandler::handlePosixPreferCex(ExecutionState &state,
                                             KInstruction *target,
                                             std::vector<ref<Expr> > &arguments) {
  if (ReadablePosix)
    return handlePreferCex(state, target, arguments);
}

void SpecialFunctionHandler::handlePrintExpr(ExecutionState &state,
                                  KInstruction *target,
                                  std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==2 &&
         "invalid number of arguments to klee_print_expr");

  std::string msg_str = readStringAtAddress(state, arguments[0]);
  llvm::errs() << msg_str << ":" << arguments[1] << "\n";
}

void SpecialFunctionHandler::handleSetForking(ExecutionState &state,
                                              KInstruction *target,
                                              std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 &&
         "invalid number of arguments to klee_set_forking");
  ref<Expr> value = executor.toUnique(state, arguments[0]);
  
  if (ConstantExpr *CE = dyn_cast<ConstantExpr>(value)) {
    state.forkDisabled = CE->isZero();
  } else {
    executor.terminateStateOnError(state, 
                                   "klee_set_forking requires a constant arg",
                                   Executor::User);
  }
}

void SpecialFunctionHandler::handleStackTrace(ExecutionState &state,
                                              KInstruction *target,
                                              std::vector<ref<Expr> > &arguments) {
  state.dumpStack(outs());
}

void SpecialFunctionHandler::handleWarning(ExecutionState &state,
                                           KInstruction *target,
                                           std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 && "invalid number of arguments to klee_warning");

  std::string msg_str = readStringAtAddress(state, arguments[0]);
  klee_warning("%s: %s", state.stack.back().kf->function->getName().data(), 
               msg_str.c_str());
}

void SpecialFunctionHandler::handleWarningOnce(ExecutionState &state,
                                               KInstruction *target,
                                               std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 &&
         "invalid number of arguments to klee_warning_once");

  std::string msg_str = readStringAtAddress(state, arguments[0]);
  klee_warning_once(0, "%s: %s", state.stack.back().kf->function->getName().data(),
                    msg_str.c_str());
}

void SpecialFunctionHandler::handlePrintRange(ExecutionState &state,
                                  KInstruction *target,
                                  std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==2 &&
         "invalid number of arguments to klee_print_range");

  std::string msg_str = readStringAtAddress(state, arguments[0]);
  llvm::errs() << msg_str << ":" << arguments[1];
  if (!isa<ConstantExpr>(arguments[1])) {
    // FIXME: Pull into a unique value method?
    ref<ConstantExpr> value;
    bool success __attribute__((unused)) = executor.solver->getValue(
        state.constraints, arguments[1], value, state.queryMetaData);
    assert(success && "FIXME: Unhandled solver failure");
    bool res;
    success = executor.solver->mustBeTrue(state.constraints,
                                          EqExpr::create(arguments[1], value),
                                          res, state.queryMetaData);
    assert(success && "FIXME: Unhandled solver failure");
    if (res) {
      llvm::errs() << " == " << value;
    } else { 
      llvm::errs() << " ~= " << value;
      std::pair<ref<Expr>, ref<Expr>> res = executor.solver->getRange(
          state.constraints, arguments[1], state.queryMetaData);
      llvm::errs() << " (in [" << res.first << ", " << res.second <<"])";
    }
  }
  llvm::errs() << "\n";
}

void SpecialFunctionHandler::handleGetObjSize(ExecutionState &state,
                                  KInstruction *target,
                                  std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==1 &&
         "invalid number of arguments to klee_get_obj_size");
  Executor::ExactResolutionList rl;
  executor.resolveExact(state, arguments[0], rl, "klee_get_obj_size");
  for (Executor::ExactResolutionList::iterator it = rl.begin(), 
         ie = rl.end(); it != ie; ++it) {
    executor.bindLocal(
        target, *it->second,
        ConstantExpr::create(it->first.first->size,
                             executor.kmodule->targetData->getTypeSizeInBits(
                                 target->inst->getType())));
  }
}

void SpecialFunctionHandler::handleGetErrno(ExecutionState &state,
                                            KInstruction *target,
                                            std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==0 &&
         "invalid number of arguments to klee_get_errno");
#ifndef WINDOWS
  int *errno_addr = executor.getErrnoLocation(state);
#else
  int *errno_addr = nullptr;
#endif

  // Retrieve the memory object of the errno variable
  ObjectPair result;
  bool resolved = state.addressSpace.resolveOne(
      ConstantExpr::create((uint64_t)errno_addr, Expr::Int64), result);
  if (!resolved)
    executor.terminateStateOnError(state, "Could not resolve address for errno",
                                   Executor::User);
  executor.bindLocal(target, state, result.second->read(0, Expr::Int32));
}

void SpecialFunctionHandler::handleErrnoLocation(
    ExecutionState &state, KInstruction *target,
    std::vector<ref<Expr> > &arguments) {
  // Returns the address of the errno variable
  assert(arguments.size() == 0 &&
         "invalid number of arguments to __errno_location/__error");

#ifndef WINDOWS
  int *errno_addr = executor.getErrnoLocation(state);
#else
  int *errno_addr = nullptr;
#endif

  executor.bindLocal(
      target, state,
      ConstantExpr::create((uint64_t)errno_addr,
                           executor.kmodule->targetData->getTypeSizeInBits(
                               target->inst->getType())));
}
void SpecialFunctionHandler::handleCalloc(ExecutionState &state,
                            KInstruction *target,
                            std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==2 &&
         "invalid number of arguments to calloc");

  ref<Expr> size = MulExpr::create(arguments[0],
                                   arguments[1]);
  executor.executeAlloc(state, size, false, target, true);
}

void SpecialFunctionHandler::handleRealloc(ExecutionState &state,
                            KInstruction *target,
                            std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==2 &&
         "invalid number of arguments to realloc");
  ref<Expr> address = arguments[0];
  ref<Expr> size = arguments[1];

  Executor::StatePair zeroSize = executor.fork(state, 
                                               Expr::createIsZero(size), 
                                               true);
  
  if (zeroSize.first) { // size == 0
    executor.executeFree(*zeroSize.first, address, target);   
  }
  if (zeroSize.second) { // size != 0
    Executor::StatePair zeroPointer = executor.fork(*zeroSize.second, 
                                                    Expr::createIsZero(address), 
                                                    true);
    
    if (zeroPointer.first) { // address == 0
      executor.executeAlloc(*zeroPointer.first, size, false, target);
    } 
    if (zeroPointer.second) { // address != 0
      Executor::ExactResolutionList rl;
      executor.resolveExact(*zeroPointer.second, address, rl, "realloc");
      
      for (Executor::ExactResolutionList::iterator it = rl.begin(), 
             ie = rl.end(); it != ie; ++it) {
        executor.executeAlloc(*it->second, size, false, target, false, 
                              it->first.second);
      }
    }
  }
}

void SpecialFunctionHandler::handleFree(ExecutionState &state,
                          KInstruction *target,
                          std::vector<ref<Expr> > &arguments) {
  // XXX should type check args
  assert(arguments.size()==1 &&
         "invalid number of arguments to free");
  executor.executeFree(state, arguments[0]);
}

void SpecialFunctionHandler::handleCheckMemoryAccess(ExecutionState &state,
                                                     KInstruction *target,
                                                     std::vector<ref<Expr> > 
                                                       &arguments) {
  assert(arguments.size()==2 &&
         "invalid number of arguments to klee_check_memory_access");

  ref<Expr> address = executor.toUnique(state, arguments[0]);
  ref<Expr> size = executor.toUnique(state, arguments[1]);
  if (!isa<ConstantExpr>(address) || !isa<ConstantExpr>(size)) {
    executor.terminateStateOnError(state, 
                                   "check_memory_access requires constant args",
				   Executor::User);
  } else {
    ObjectPair op;

    if (!state.addressSpace.resolveOne(cast<ConstantExpr>(address), op)) {
      executor.terminateStateOnError(state,
                                     "check_memory_access: memory error",
				     Executor::Ptr, NULL,
                                     executor.getAddressInfo(state, address));
    } else {
      ref<Expr> chk = 
        op.first->getBoundsCheckPointer(address, 
                                        cast<ConstantExpr>(size)->getZExtValue());
      if (!chk->isTrue()) {
        executor.terminateStateOnError(state,
                                       "check_memory_access: memory error",
				       Executor::Ptr, NULL,
                                       executor.getAddressInfo(state, address));
      }
    }
  }
}

void SpecialFunctionHandler::handleGetValue(ExecutionState &state,
                                            KInstruction *target,
                                            std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 &&
         "invalid number of arguments to klee_get_value");

  executor.executeGetValue(state, arguments[0], target);
}

void SpecialFunctionHandler::handleDefineFixedObject(ExecutionState &state,
                                                     KInstruction *target,
                                                     std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==2 &&
         "invalid number of arguments to klee_define_fixed_object");
  assert(isa<ConstantExpr>(arguments[0]) &&
         "expect constant address argument to klee_define_fixed_object");
  assert(isa<ConstantExpr>(arguments[1]) &&
         "expect constant size argument to klee_define_fixed_object");
  
  uint64_t address = cast<ConstantExpr>(arguments[0])->getZExtValue();
  uint64_t size = cast<ConstantExpr>(arguments[1])->getZExtValue();
  MemoryObject *mo = executor.memory->allocateFixed(address, size, state.prevPC->inst);
  executor.bindObjectInState(state, mo, false);
  mo->isUserSpecified = true; // XXX hack;
}

void SpecialFunctionHandler::handleMakeSymbolic(ExecutionState &state,
                                                KInstruction *target,
                                                std::vector<ref<Expr> > &arguments) {
  std::string name;

  if (arguments.size() != 3) {
    executor.terminateStateOnError(state, "Incorrect number of arguments to klee_make_symbolic(void*, size_t, char*)", Executor::User);
    return;
  }

  name = arguments[2]->isZero() ? "" : readStringAtAddress(state, arguments[2]);

  if (name.length() == 0) {
    name = "unnamed";
    klee_warning("klee_make_symbolic: renamed empty name to \"unnamed\"");
  }

  Executor::ExactResolutionList rl;
  executor.resolveExact(state, arguments[0], rl, "make_symbolic");
  
  for (Executor::ExactResolutionList::iterator it = rl.begin(), 
         ie = rl.end(); it != ie; ++it) {
    const MemoryObject *mo = it->first.first;
    mo->setName(name);
    
    const ObjectState *old = it->first.second;
    ExecutionState *s = it->second;
    
    if (old->readOnly) {
      executor.terminateStateOnError(*s, "cannot make readonly object symbolic",
                                     Executor::User);
      return;
    } 

    // FIXME: Type coercion should be done consistently somewhere.
    bool res;
    bool success __attribute__((unused)) = executor.solver->mustBeTrue(
        s->constraints,
        EqExpr::create(
            ZExtExpr::create(arguments[1], Context::get().getPointerWidth()),
            mo->getSizeExpr()),
        res, s->queryMetaData);
    assert(success && "FIXME: Unhandled solver failure");
    
    if (res) {
      executor.executeMakeSymbolic(*s, mo, name);
    } else {      
      executor.terminateStateOnError(*s, 
                                     "wrong size given to klee_make_symbolic[_name]", 
                                     Executor::User);
    }
  }
}

void SpecialFunctionHandler::handleMarkGlobal(ExecutionState &state,
                                              KInstruction *target,
                                              std::vector<ref<Expr> > &arguments) {
  assert(arguments.size()==1 &&
         "invalid number of arguments to klee_mark_global");  

  Executor::ExactResolutionList rl;
  executor.resolveExact(state, arguments[0], rl, "mark_global");
  
  for (Executor::ExactResolutionList::iterator it = rl.begin(), 
         ie = rl.end(); it != ie; ++it) {
    const MemoryObject *mo = it->first.first;
    assert(!mo->isLocal);
    mo->isGlobal = true;
  }
}

void SpecialFunctionHandler::handleAddOverflow(ExecutionState &state,
                                               KInstruction *target,
                                               std::vector<ref<Expr> > &arguments) {
  executor.terminateStateOnError(state, "overflow on addition",
                                 Executor::Overflow);
}

void SpecialFunctionHandler::handleSubOverflow(ExecutionState &state,
                                               KInstruction *target,
                                               std::vector<ref<Expr> > &arguments) {
  executor.terminateStateOnError(state, "overflow on subtraction",
                                 Executor::Overflow);
}

void SpecialFunctionHandler::handleMulOverflow(ExecutionState &state,
                                               KInstruction *target,
                                               std::vector<ref<Expr> > &arguments) {
  executor.terminateStateOnError(state, "overflow on multiplication",
                                 Executor::Overflow);
}

void SpecialFunctionHandler::handleDivRemOverflow(ExecutionState &state,
                                               KInstruction *target,
                                               std::vector<ref<Expr> > &arguments) {
  executor.terminateStateOnError(state, "overflow on division or remainder",
                                 Executor::Overflow);
}

// yu hao: handle kernel function
void SpecialFunctionHandler::handleKmalloc(ExecutionState &state,
                                           KInstruction *target,
                                           std::vector<ref<Expr> > &arguments) {
    // XXX should type check args
    assert(arguments.size()==2 && "invalid number of arguments to kmalloc");
    executor.executeAlloc(state, arguments[0], false, target, true);
}

void SpecialFunctionHandler::handleIminor(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
    // XXX should type check args
    assert(arguments.size()==1 && "invalid number of arguments to iminor");
    auto name = "minor";
    auto ty = target->inst->getType();
    unsigned int size = executor.kmodule->targetData->getTypeStoreSize(ty);
    Expr::Width width = executor.getWidthForLLVMType(ty);
    ref<Expr> symbolic = executor.manual_make_symbolic(name, size, width);
    executor.bindLocal(target, state, symbolic);
}

// zheng
// precondition: three arguments, targetaddr and srcaddr must be constant, len can be symbolic
// if len is symbolic, assign an constant value up to 8192. 
void SpecialFunctionHandler::handleMemcpy(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
    // XXX should type check args
    assert(arguments.size()==3 && "invalid number of arguments to memcpy");
    klee::klee_message("SpecialFunctionHandler::handleMemcpy");
    //bool symsize = false;
    uint64_t length = 8192;
    ObjectPair op, op2;
    bool success;

    ref<Expr> targetaddr = arguments[0];
    klee::klee_message("targetaddr: %s",targetaddr.get_ptr()->dump2().c_str());

    if (ConstantExpr* CE1 = dyn_cast<ConstantExpr>(targetaddr)) {
      success = state.addressSpace.resolveOne(CE1, op);
    } else{
      klee::klee_message("memcpy not constant target address. Return directly");
      return;
    }
    if(!success){
      klee::klee_message("Not find the corresponding target object according to the address. Return directly");
      return;
    }

    ref<Expr> srcaddr = arguments[1];
    klee::klee_message("src: %s",srcaddr.get_ptr()->dump2().c_str());
    if (ConstantExpr* CE2 = dyn_cast<ConstantExpr>(srcaddr)) {
      success = state.addressSpace.resolveOne(CE2, op2);
    } else{
      klee::klee_message("memcpy not constant src address. Return directly");
      // todo: Better solution should be continue symbolizing the target struct
      return;
    }
    if(!success){
      klee::klee_message("Not find the corresponding src object according to the address. Return directly");
      return;
    }

    ref<Expr> len = arguments[2];
    klee::klee_message("len: %s",len.get_ptr()->dump2().c_str());
    // object: target object
    const MemoryObject * object = op.first;
    klee_message("target obj addr: %lu obj size: %u", object->address, object->size);
    // object2: source object
    const MemoryObject * object2 = op2.first;
    klee_message("src obj addr: %lu obj size: %u", object2->address, object2->size);
    if(ConstantExpr* CE = dyn_cast<ConstantExpr>(len)){
      length = CE->getZExtValue();
    }
    else{
      //Use hard-coded concrete size.
      //todo: Compare the symbolic memcpy size and the object size to detect potential OOBW
      //symsize = true;
      length = std::min(length, (object->address+object->size-dyn_cast<ConstantExpr>(targetaddr)->getZExtValue()));
      length = std::min(length, (object2->address+object2->size-dyn_cast<ConstantExpr>(srcaddr)->getZExtValue()));
    }
    klee::klee_message("concrete length: %lu",length);

    const ObjectState *os = op2.second;
    // baseoffset: from which byte to start copy
    uint64_t baseoffset = dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() - object2->address;
    klee::klee_message("baseoffset: %lu", baseoffset);
    for(uint64_t i =0; i<length; i++){
      ref<Expr> offset = ConstantExpr::create((baseoffset + i), Context::get().getPointerWidth());
      ref<Expr> value = os->read(offset, 8);

      ref<Expr> base = AddExpr::create(targetaddr, ConstantExpr::create(i, Context::get().getPointerWidth()));
      executor.executeMemoryOperation(state, true, base, value, 0);
    }

}

//  zheng: the difference from handleMemcpy is that  it return length of copy
void SpecialFunctionHandler::handleMemcpyRL(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
    // XXX should type check args
    assert(arguments.size()==3 && "invalid number of arguments to memcpy");
    klee::klee_message("SpecialFunctionHandler::handleMemcpyRL");
    //bool symsize = false;
    uint64_t length = 8192;
    ObjectPair op, op2;
    bool success;

    ref<Expr> targetaddr = arguments[0];
    klee::klee_message("targetaddr: %s",targetaddr.get_ptr()->dump2().c_str());

    if (ConstantExpr* CE1 = dyn_cast<ConstantExpr>(targetaddr)) {
      success = state.addressSpace.resolveOne(CE1, op);
    } else{
      klee::klee_message("memcpy not constant target address. Return directly");
      return;
    }
    if(!success){
      klee::klee_message("Not find the corresponding target object according to the address. Return directly");
      return;
    }

    ref<Expr> srcaddr = arguments[1];
    ref<Expr> len = arguments[2];
    const ObjectState *os;
    klee::klee_message("src: %s",srcaddr.get_ptr()->dump2().c_str());
    if (ConstantExpr* CE2 = dyn_cast<ConstantExpr>(srcaddr)) {
      success = state.addressSpace.resolveOne(CE2, op2);
    } else{
      klee::klee_message("memcpy not constant src address. Return directly");
      // It should be normal in execution now we still want to keep execution. 
      // todo: Better solution should be continue symbolizing the target struct
      goto returnL;
      //return;
    }
    if(!success){
      klee::klee_message("Not find the corresponding src object according to the address. Return directly");
      goto returnL;
      //return;
    }

    klee::klee_message("len: %s",len.get_ptr()->dump2().c_str());
    // object: target object
    const MemoryObject * object;
    object  = op.first;
    klee_message("target obj addr: %lu obj size: %u", object->address, object->size);
    // object2: source object
    const MemoryObject * object2;
    object2 = op2.first;
    klee_message("src obj addr: %lu obj size: %u", object2->address, object2->size);

    if(ConstantExpr* CE = dyn_cast<ConstantExpr>(len)){
      length = CE->getZExtValue();
    }
    else{
      //Use hard-coded concrete size.
      //todo: Compare the symbolic memcpy size and the object size to detect potential OOBW
      //symsize = true;
      length = std::min(length, (object->address+object->size-dyn_cast<ConstantExpr>(targetaddr)->getZExtValue()));
      length = std::min(length, (object2->address+object2->size-dyn_cast<ConstantExpr>(srcaddr)->getZExtValue()));
    }
    klee::klee_message("concrete length: %lu",length);

    os = op2.second;
    // baseoffset: from which byte to start copy
    uint64_t baseoffset;
    baseoffset = dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() - object2->address;
    klee::klee_message("baseoffset: %lu", baseoffset);
    for(uint64_t i =0; i<length; i++){
      ref<Expr> offset = ConstantExpr::create((baseoffset + i), Context::get().getPointerWidth());
      ref<Expr> value = os->read(offset, 8);

      ref<Expr> base = AddExpr::create(targetaddr, ConstantExpr::create(i, Context::get().getPointerWidth()));
      executor.executeMemoryOperation(state, true, base, value, 0);
    }

returnL:
    if(ConstantExpr* CE = dyn_cast<ConstantExpr>(len)){
      executor.bindLocal(target, state, ConstantExpr::alloc(length, Expr::Int64));
    }
    else{
      executor.bindLocal(target, state, len);
    }

}

//  zheng: the difference from handleMemcpy is that  it return 0
void SpecialFunctionHandler::handleMemcpyRZ(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
    ref<Expr> ret = ConstantExpr::alloc(0, Expr::Int64);
    executor.bindLocal(target, state, ret);
    handleMemcpy(state, target, arguments);
}

std::string create_var_name(llvm::Instruction *i, const std::string &kind) {
    // kernelversion doesn't influence the return value
    std::string kernelversion = "v5.4";
    std::string name;
    name += inst_to_strID(i);
    std::string sourceinfo = dump_inst_booltin(i, kernelversion);
    std::size_t pos = sourceinfo.find("#");
    std::string linenum = sourceinfo.substr(pos);
    name += linenum;
    name += "-" + kind;
    return name;
}

//  zheng: the difference from handleMemcpy is that  it return symbolic value between 0 and size
void SpecialFunctionHandler::handleStrncpy_from_user(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
    auto name = create_var_name(target->inst, "strncpy_from_user_size");
    ref<Expr> ret = executor.manual_make_symbolic(name, 8, 64);
    ref<Expr> cond = SleExpr::create(ret, arguments[2]);
    executor.addConstraint(state, cond);
    executor.bindLocal(target, state, ret);
    handleMemcpy(state, target, arguments);
}

// zheng: symbolize the struct pointed by 4th argument; and return 0
void SpecialFunctionHandler::handleUser_path_at(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
    auto ty = target->inst->getOperand(4)->getType();
    auto name = create_var_name(target->inst, "user_path_at_sympath");
    MemoryObject *mo = executor.create_mo(state, ty, target->inst, name);
    executor.un_eval(target, 4, state).value = mo->getBaseExpr();

    ref<Expr> ret = ConstantExpr::alloc(0, Expr::Int32);
    executor.bindLocal(target, state, ret);
}

// int strcmp(const char *cs, const char *ct)
// Assumption: ct points to a constant string , cs points to a symbolic string
// return 1/-1/0
// todo: for the case that ct points to a symbolic string, return symbolic value
void SpecialFunctionHandler::handleStrcmp(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
  klee_message("\nfunction Model handleStrcmp");
  ObjectPair op, op2;
  bool success1, success2;

  ref<Expr> srcaddr = arguments[0];
  if (ConstantExpr* CE1 = dyn_cast<ConstantExpr>(srcaddr)) {
    success1 = state.addressSpace.resolveOne(CE1, op);
  }  else {
    return;
  }
  ref<Expr> targetaddr = arguments[1];
  if (ConstantExpr* CE2 = dyn_cast<ConstantExpr>(targetaddr)) {
    success2 = state.addressSpace.resolveOne(CE2, op2);
  }  else {
    return;
  }
  
  if (!success2) {
    klee_message("dont find target object, return symbolic value");
    auto name = "[strcmp symreturn "+targetaddr.get_ptr()->dump2()+"]" + "(symvar)";
    ref<Expr> symreturn = executor.manual_make_symbolic(name, 4, 32);
    executor.bindLocal(target, state, symreturn);
    return;
  }
  const MemoryObject * sobject = op.first;
  const MemoryObject * tobject = op2.first;
  klee_message("source obj addr: %lu obj size: %u", sobject->address, sobject->size);
  klee_message("target obj addr: %lu obj size: %u", tobject->address, tobject->size);

  uint64_t sbaseoffset = dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() - sobject->address;
  uint64_t tbaseoffset = dyn_cast<ConstantExpr>(targetaddr)->getZExtValue() - tobject->address;
  const ObjectState *os = op.second;
  const ObjectState *os2 = op2.second;
  uint64_t length = tobject->size-tbaseoffset;

  ref<Expr> constraint = ConstantExpr::create(1, Expr::Bool);
  for(uint64_t i = 0; i < length; i++){
      ref<Expr> soffset = ConstantExpr::create((sbaseoffset + i), Context::get().getPointerWidth());
      ref<Expr> toffset = ConstantExpr::create((tbaseoffset + i), Context::get().getPointerWidth());
      ref<Expr> svalue = os->read(soffset, 8);
      // tvalue should be concrete
      ref<Expr> tvalue = os2->read(toffset, 8);
      klee_message("i:%lu svalue: %s tvalue: %s", i, svalue.get_ptr()->dump2().c_str(),tvalue.get_ptr()->dump2().c_str());
      // The logic here is a little different from the original fuction
      // when there is a unequal constant char, we cannot gurantee the return value is 1 or -1
      if (ConstantExpr* CE3 = dyn_cast<ConstantExpr>(svalue)){
        if (CE3->getZExtValue() < dyn_cast<ConstantExpr>(tvalue)->getZExtValue()){
          executor.bindLocal(target, state, ConstantExpr::alloc(-1, Expr::Int32));
          return;
        } 
        else if (CE3->getZExtValue() > dyn_cast<ConstantExpr>(tvalue)->getZExtValue())
        {
          executor.bindLocal(target, state, ConstantExpr::alloc(1, Expr::Int32));
          return;
        }
        continue;
      }
      constraint= AndExpr::create(EqExpr::create(svalue, tvalue), constraint);
      //ref<Expr> base = AddExpr::create(srcaddr, ConstantExpr::create(i, Context::get().getPointerWidth()));
      //executor.executeMemoryOperation(state, true, base, value, 0);
  }
  klee_message("constraint: %s", constraint.get_ptr()->dump2().c_str());
  Executor::StatePair equalstr = executor.fork(state, constraint, true);
  klee::klee_message("branches.first: %p branches.second: %p", equalstr.first, equalstr.second);
  if (equalstr.first) { // symbolic str cs == ct
    executor.bindLocal(target, *(equalstr.first), ConstantExpr::alloc(0, Expr::Int32));
  }
  if (equalstr.second) { // symbolic str cs != ct
    executor.bindLocal(target, *(equalstr.second), ConstantExpr::alloc(1, Expr::Int32));
  }
}

// char *strchr(const char *s, int c)
void SpecialFunctionHandler::handleStrchr(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments) {
  
  // step 1: get the string s object
  ObjectPair op;
  bool success;

  ref<Expr> srcaddr = arguments[0];
  klee_message("straddr: %s", srcaddr.get_ptr()->dump2().c_str());
  if (ConstantExpr* CE1 = dyn_cast<ConstantExpr>(srcaddr)) {
    success = state.addressSpace.resolveOne(CE1, op);
  }  else {
    klee_message("handleStrchr: srcaddr is symbolic");
    return;
  }

  if (!success) {
    klee_message("dont find src object, return symbolic value");
    auto name = "[strchr symreturn "+srcaddr.get_ptr()->dump2()+"]" + "(symvar)";
    ref<Expr> symreturn = executor.manual_make_symbolic(name, 1, 8);
    executor.bindLocal(target, state, symreturn);
    return;
  }

  const MemoryObject *sobject = op.first;
  const ObjectState *os = op.second;
  
  //step2: iterate on the bytes of string s and compare them with c
  //todo: change the length of strc. extract the value and create ConstantExpr again?
  ref<Expr> strc = ConstantExpr::create(dyn_cast<ConstantExpr>(arguments[1])->getZExtValue(), 8);
  klee_message("strc: %s", strc.get_ptr()->dump2().c_str());
  //klee_message("strc: %u", strc.get_ptr()->dump2().c_str());
  //ConstantExpr::create(dyn_cast<ConstantExpr>(arguments[1])->getZExtValue(), 8);

  uint64_t sbaseoffset = dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() - sobject->address;
  uint64_t length = sobject->size-sbaseoffset;
  std::vector<uint64_t> indexs;
  //std::vector<ref<Expr> > constraints;
  // used for store current constraint
  ref<Expr> constraint = ConstantExpr::create(1, Expr::Bool);
  for(uint64_t i = 0; i < length; i++){
    ref<Expr> soffset = ConstantExpr::create((sbaseoffset + i), Context::get().getPointerWidth());
    ref<Expr> svalue = os->read(soffset, 8);
    // If reach the end of the str, just break and return the NULL. 
    // Note that current state contains the constraints that previous bytes cannot be the given char
    if (ConstantExpr* CE3 = dyn_cast<ConstantExpr>(svalue)){
        if (CE3->getZExtValue() == 0){
          klee_message("reach the end of string");
          break;
          //executor.bindLocal(target, state, ConstantExpr::alloc(0, Context::get().getPointerWidth()));
          //return;
        } 
    }
    ref<Expr> returnaddr = ConstantExpr::create((dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() + i), Context::get().getPointerWidth());
    constraint = NeExpr::create(svalue, strc);
    if (i%10 != 0){
      executor.addConstraint(state, constraint);
      continue;
    }
    Executor::StatePair branches = executor.fork(state, constraint, false);
    // this byte must equal the given char. should stop the iteration since the latter addresses cannot be returned;
    if (!branches.first){
      executor.bindLocal(target, *(branches.second),  returnaddr);
      klee_message("state: %p  return value: %s", branches.second, returnaddr.get_ptr()->dump2().c_str());
      return;
    }
    else {
      // This byte cannot equal the given byte; Since we have added this constraint, thus just continue the loop 
      if (!branches.second){
        continue;
      } 
      // This byte can equal the given byte or not
      // branches.first (state): not equal the given byte
      // branches.second: equal the given byte and return current address
      executor.bindLocal(target, *(branches.second),  returnaddr);
      klee_message("state: %p  return value: %s", branches.second, returnaddr.get_ptr()->dump2().c_str());
      indexs.push_back(i);
      // Already fork enough cases that the symbolic byte equals the given byte
      if (indexs.size() >= 2){
        // we need a case that returns 0 to be executed first
        soffset = ConstantExpr::create((sbaseoffset + i+1), Context::get().getPointerWidth());
        svalue = os->read(soffset, 8);
        constraint = EqExpr::create(svalue, strc);
        Executor::StatePair branches = executor.fork(state, constraint, false);
        executor.bindLocal(target, *(branches.second),  ConstantExpr::alloc(0, Context::get().getPointerWidth()));
        klee_message("state: %p  return value: 0",branches.second);
        //executor.bindLocal(target, state, ConstantExpr::alloc(0, Context::get().getPointerWidth()));
        //return;
        break;
      }
    }
   
    //bool res;
    //bool mustnotEqual = executor.solver->mustBeFalse(
    //  state.constraints, EqExpr::create(svalue, strc), res, state.queryMetaData);
    //if (!res){
      //constraint = AndExpr::create(EqExpr::create(svalue, strc), constraint);
    //  constraint = NeExpr::create(svalue, strc);
    //  Executor::StatePair branches = executor.fork(state, constraint, false);
    //  indexs.push_back(i);
      //constraints.push_back(constraint);
    //  if (indexs.size() >= 10){
    //    break;
    //  }
    //} else{
      //constraint= AndExpr::create(NeExpr::create(svalue, strc), constraint);
    //}  
  }
  klee_message("state: %p  return value: 0", &state);
  executor.bindLocal(target, state, ConstantExpr::alloc(0, Context::get().getPointerWidth()));
  return;
  //klee_message("L1311");
  //size_t size = indexs.size();
  //klee_message("size: %lu", size);
  //// not solvable
  //if(size ==0){
  //  klee_message("handleStrchr: no byte in string can equal to given byte");
  //  executor.bindLocal(target, state, ConstantExpr::alloc(0, Context::get().getPointerWidth()));
  //  return;
  //}
  
  /*
  Executor::StatePair branches = executor.fork(state, constraints.at(0), false);
  if(branches.first){
      ref<Expr> returnaddr = ConstantExpr::create((dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() + indexs.at(0)), Context::get().getPointerWidth());
      executor.bindLocal(target, *(branches.first),  returnaddr);
  }
  klee_message("L1323");
  for (size_t i = 1; i < size; i++)
  {
    klee_message("branches.second: %lu", branches.second);
    if(!branches.second){ 
      return;
    }
    uint64_t index = indexs.at(i);
    constraint = constraints.at(i);
    klee_message("index:%lu  constraint:%s", index, constraint.get_ptr()->dump2().c_str());
    Executor::StatePair branches = executor.fork(*branches.second, constraint, false);
    klee_message("L1330");
    ref<Expr> returnaddr = ConstantExpr::create((dyn_cast<ConstantExpr>(srcaddr)->getZExtValue() + index), Context::get().getPointerWidth());
    if(branches.first){
      executor.bindLocal(target, *(branches.first),  returnaddr);
    }
    klee_message("L1335");
  }
  if(branches.second){
    executor.bindLocal(target, *(branches.second), ConstantExpr::alloc(0, Context::get().getPointerWidth()));
  }
  */

}

void SpecialFunctionHandler::handleMemset(ExecutionState &state,
                                          KInstruction *target,
                                          std::vector<ref<Expr> > &arguments){
    assert(arguments.size()==3 && "invalid number of arguments to memset");
    ObjectPair op;

    ref<Expr> targetaddr = arguments[0];
    klee::klee_message("targetaddr: %s",targetaddr.get_ptr()->dump2().c_str());
    bool success;
    
    if (ConstantExpr* CE1 = dyn_cast<ConstantExpr>(targetaddr)) {
      success = state.addressSpace.resolveOne(CE1, op);
    } else{
      klee::klee_message("memset not constant target address. Return directly");
      return;
    }

    if (!success) {
      klee::klee_message("memset dont find object for the given address, is it OOB?");
      executor.bindLocal(target, state, targetaddr);
      return;
    }
    ref<Expr> value = arguments[1];
    ref<Expr> len = arguments[2];
    const MemoryObject * object = op.first;
    //klee_message("target obj addr: %lu obj size: %u", object->address, object->size);
    klee_message("target obj addr: %lu", object->address);

    uint64_t length;
    if(ConstantExpr* CE = dyn_cast<ConstantExpr>(len)){
      length = CE->getZExtValue();
    } else{
      // we should check whether the length can be larger than object size? is it?
      klee::klee_message("memset not constant size; use object size.");
      length = object->size;
      //return;
    }

    for(uint64_t i =0; i<length; i++){
      ref<Expr> base = AddExpr::create(targetaddr, ConstantExpr::create(i, Context::get().getPointerWidth()));
      executor.executeMemoryOperation(state, true, base, value, 0);
    }
    executor.bindLocal(target, state, targetaddr);
}