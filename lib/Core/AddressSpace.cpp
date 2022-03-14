//===-- AddressSpace.cpp --------------------------------------------------===//
//
//                     The KLEE Symbolic Virtual Machine
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===//

#include "AddressSpace.h"

#include "ExecutionState.h"
#include "Memory.h"
#include "TimingSolver.h"

#include "klee/Expr/Expr.h"
#include "klee/Statistics/TimerStatIncrementer.h"

#include "CoreStats.h"

/// zheng:
#include <iostream>

using namespace klee;

///

void AddressSpace::bindObject(const MemoryObject *mo, ObjectState *os) {
  assert(os->copyOnWriteOwner==0 && "object already has owner");
  os->copyOnWriteOwner = cowKey;
  objects = objects.replace(std::make_pair(mo, os));
}

void AddressSpace::unbindObject(const MemoryObject *mo) {
  objects = objects.remove(mo);
}

const ObjectState *AddressSpace::findObject(const MemoryObject *mo) const {
  const auto res = objects.lookup(mo);
  return res ? res->second.get() : nullptr;
}

ObjectState *AddressSpace::getWriteable(const MemoryObject *mo,
                                        const ObjectState *os) {
  assert(!os->readOnly);

  // If this address space owns they object, return it
  if (cowKey == os->copyOnWriteOwner)
    return const_cast<ObjectState*>(os);

  // Add a copy of this object state that can be updated
  ref<ObjectState> newObjectState(new ObjectState(*os));
  newObjectState->copyOnWriteOwner = cowKey;
  objects = objects.replace(std::make_pair(mo, newObjectState));
  return newObjectState.get();
}


/// zheng: used to find a corresponding object for a given constant address
bool AddressSpace::resolveOne(const ref<ConstantExpr> &addr, 
                              ObjectPair &result) const {
  uint64_t address = addr->getZExtValue();
  MemoryObject hack(address);
  
  //std::cout << "AddressSpace::resolveOne with 2 args\n";
  //std::cout << "address:" << address << "\n";

  if (const auto res = objects.lookup_previous(&hack)) {
    const auto &mo = res->first;
    // Check if the provided address is between start and end of the object
    // [mo->address, mo->address + mo->size) or the object is a 0-sized object.
    //std::cout << "mo->address: "<< mo->address << " size: " << mo->size <<"\n";
    if ((mo->size==0 && address==mo->address) ||
        (address - mo->address < mo->size)) {
      result.first = res->first;
      result.second = res->second.get();
      return true;
    }
  }

  return false;
}

/// zheng: whether the resolve is executed successfully will be stored in return value. 
/// Whether finding the suitable object will be stored in success variable
/// 1. check if address is concrete value or symbolic, if concrete then call resolveOne with two arguments
/// 2. generate an example concrete address. Check if the address is in an object, if yes, then return
/// 3. if no, split the object lists (ordered list from low address to high address) into two parts with example address.
/// for each part there is a loop, check if the address (symbolic) can be in the object under constraints, if yes, return the object
bool AddressSpace::resolveOne(ExecutionState &state,
                              TimingSolver *solver,
                              ref<Expr> address,
                              ObjectPair &result,
                              bool &success) const {
  //std::cout << "\nAddressSpace::resolveOne 4 args\n";

  // search forwards
  //if the address is constant
  if (ConstantExpr *CE = dyn_cast<ConstantExpr>(address)) {
    success = resolveOne(CE, result);
    //std::cout << "success: " << success <<"\n";
    return true;
  } else {
    TimerStatIncrementer timer(stats::resolveTime);

    // try cheap search, will succeed for any inbounds pointer

    ref<ConstantExpr> cex;
    if (!solver->getValue(state.constraints, address, cex, state.queryMetaData))
      return false;
    uint64_t example = cex->getZExtValue();
    MemoryObject hack(example);
    const auto res = objects.lookup_previous(&hack);
    
    //std::cout << "uint64_t example (writing address) = " << example << "\n";
    /// zheng: check with the nearest previous allocated object, whether the unsigned example offset < size, if so, klee think it's the object we want to find.
    /// zheng: be careful, could we simply use this object? 
    /// We should since we cannot exclude it basically. But if there is no enough constraints, the result may vary
    if (res) {
      const MemoryObject *mo = res->first;
      //std::cout << "find an object for the example address, check if the address is in the range of object\n";
      //std::cout << "mo->address: " << mo->address << "  mo->size: " << mo->size << "\n";
      
      if (example - mo->address < mo->size) {
        result.first = res->first;
        result.second = res->second.get();
        success = true;
        return true;
      }
   }

    // didn't work, now we have to search
       
    MemoryMap::iterator oi = objects.upper_bound(&hack);
    MemoryMap::iterator begin = objects.begin();
    MemoryMap::iterator end = objects.end();
      
    MemoryMap::iterator start = oi;
    while (oi!=begin) {
      --oi;
      const auto &mo = oi->first;

      bool mayBeTrue;
      if (!solver->mayBeTrue(state.constraints,
                             mo->getBoundsCheckPointer(address), mayBeTrue,
                             state.queryMetaData))
        return false;
      if (mayBeTrue) {
        result.first = oi->first;
        result.second = oi->second.get();
        success = true;
        return true;
      } else {
        bool mustBeTrue;
        if (!solver->mustBeTrue(state.constraints,
                                UgeExpr::create(address, mo->getBaseExpr()),
                                mustBeTrue, state.queryMetaData))
          return false;
        if (mustBeTrue)
          break;
      }
    }

    // search forwards
    for (oi=start; oi!=end; ++oi) {
      const auto &mo = oi->first;

      bool mustBeTrue;
      if (!solver->mustBeTrue(state.constraints,
                              UltExpr::create(address, mo->getBaseExpr()),
                              mustBeTrue, state.queryMetaData))
        return false;
      if (mustBeTrue) {
        break;
      } else {
        bool mayBeTrue;

        if (!solver->mayBeTrue(state.constraints,
                               mo->getBoundsCheckPointer(address), mayBeTrue,
                               state.queryMetaData))
          return false;
        if (mayBeTrue) {
          result.first = oi->first;
          result.second = oi->second.get();
          success = true;
          return true;
        }
      }
    }

    success = false;
    return true;
  }
}

int AddressSpace::checkPointerInObject(ExecutionState &state,
                                       TimingSolver *solver, ref<Expr> p,
                                       const ObjectPair &op, ResolutionList &rl,
                                       unsigned maxResolutions) const {
  // XXX in the common case we can save one query if we ask
  // mustBeTrue before mayBeTrue for the first result. easy
  // to add I just want to have a nice symbolic test case first.
  const MemoryObject *mo = op.first;
  ref<Expr> inBounds = mo->getBoundsCheckPointer(p);
  bool mayBeTrue;
  if (!solver->mayBeTrue(state.constraints, inBounds, mayBeTrue,
                         state.queryMetaData)) {
    return 1;
  }

  if (mayBeTrue) {
    rl.push_back(op);

    // fast path check
    auto size = rl.size();
    if (size == 1) {
      bool mustBeTrue;
      if (!solver->mustBeTrue(state.constraints, inBounds, mustBeTrue,
                              state.queryMetaData))
        return 1;
      if (mustBeTrue)
        return 0;
    }
    else
      if (size == maxResolutions)
        return 1;
  }

  return 2;
}

bool AddressSpace::resolve(ExecutionState &state, TimingSolver *solver,
                           ref<Expr> p, ResolutionList &rl,
                           unsigned maxResolutions, time::Span timeout) const {
  if (ConstantExpr *CE = dyn_cast<ConstantExpr>(p)) {
    ObjectPair res;
    if (resolveOne(CE, res))
      rl.push_back(res);
    return false;
  } else {
    TimerStatIncrementer timer(stats::resolveTime);

    // XXX in general this isn't exactly what we want... for
    // a multiple resolution case (or for example, a \in {b,c,0})
    // we want to find the first object, find a cex assuming
    // not the first, find a cex assuming not the second...
    // etc.

    // XXX how do we smartly amortize the cost of checking to
    // see if we need to keep searching up/down, in bad cases?
    // maybe we don't care?

    // XXX we really just need a smart place to start (although
    // if its a known solution then the code below is guaranteed
    // to hit the fast path with exactly 2 queries). we could also
    // just get this by inspection of the expr.

    ref<ConstantExpr> cex;
    if (!solver->getValue(state.constraints, p, cex, state.queryMetaData))
      return true;
    uint64_t example = cex->getZExtValue();
    MemoryObject hack(example);

    MemoryMap::iterator oi = objects.upper_bound(&hack);
    MemoryMap::iterator begin = objects.begin();
    MemoryMap::iterator end = objects.end();

    MemoryMap::iterator start = oi;
    // search backwards, start with one minus because this
    // is the object that p *should* be within, which means we
    // get write off the end with 4 queries
    while (oi != begin) {
      --oi;
      const MemoryObject *mo = oi->first;
      if (timeout && timeout < timer.delta())
        return true;

      auto op = std::make_pair<>(mo, oi->second.get());

      int incomplete =
          checkPointerInObject(state, solver, p, op, rl, maxResolutions);
      if (incomplete != 2)
        return incomplete ? true : false;

      bool mustBeTrue;
      if (!solver->mustBeTrue(state.constraints,
                              UgeExpr::create(p, mo->getBaseExpr()), mustBeTrue,
                              state.queryMetaData))
        return true;
      if (mustBeTrue)
        break;
    }

    // search forwards
    for (oi = start; oi != end; ++oi) {
      const MemoryObject *mo = oi->first;
      if (timeout && timeout < timer.delta())
        return true;

      bool mustBeTrue;
      if (!solver->mustBeTrue(state.constraints,
                              UltExpr::create(p, mo->getBaseExpr()), mustBeTrue,
                              state.queryMetaData))
        return true;
      if (mustBeTrue)
        break;
      auto op = std::make_pair<>(mo, oi->second.get());

      int incomplete =
          checkPointerInObject(state, solver, p, op, rl, maxResolutions);
      if (incomplete != 2)
        return incomplete ? true : false;
    }
  }

  return false;
}

// These two are pretty big hack so we can sort of pass memory back
// and forth to externals. They work by abusing the concrete cache
// store inside of the object states, which allows them to
// transparently avoid screwing up symbolics (if the byte is symbolic
// then its concrete cache byte isn't being used) but is just a hack.

void AddressSpace::copyOutConcretes() {
  for (MemoryMap::iterator it = objects.begin(), ie = objects.end(); 
       it != ie; ++it) {
    const MemoryObject *mo = it->first;

    if (!mo->isUserSpecified) {
      const auto &os = it->second;
      auto address = reinterpret_cast<std::uint8_t*>(mo->address);

      if (!os->readOnly)
        memcpy(address, os->concreteStore, mo->size);
    }
  }
}

bool AddressSpace::copyInConcretes() {
  for (auto &obj : objects) {
    const MemoryObject *mo = obj.first;

    if (!mo->isUserSpecified) {
      const auto &os = obj.second;

      if (!copyInConcrete(mo, os.get(), mo->address))
        return false;
    }
  }

  return true;
}

bool AddressSpace::copyInConcrete(const MemoryObject *mo, const ObjectState *os,
                                  uint64_t src_address) {
  auto address = reinterpret_cast<std::uint8_t*>(src_address);
  if (memcmp(address, os->concreteStore, mo->size) != 0) {
    if (os->readOnly) {
      return false;
    } else {
      ObjectState *wos = getWriteable(mo, os);
      memcpy(wos->concreteStore, address, mo->size);
    }
  }
  return true;
}

/***/

bool MemoryObjectLT::operator()(const MemoryObject *a, const MemoryObject *b) const {
  return a->address < b->address;
}

