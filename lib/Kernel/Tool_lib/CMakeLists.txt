#===------------------------------------------------------------------------===#
#
#                     The KLEE Symbolic Virtual Machine
#
# This file is distributed under the University of Illinois Open Source
# License. See LICENSE.TXT for details.
#
#===------------------------------------------------------------------------===#

klee_add_component(Tool_lib
        json.hpp
        basic.h
        log.h
        llvm_related.h
        llvm_related.cpp)

set(LLVM_COMPONENTS
        core
        executionengine
        mcjit
        native
        support
        )
klee_get_llvm_libs(LLVM_LIBS ${LLVM_COMPONENTS})
set_target_properties(Tool_lib PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(Tool_lib PUBLIC ${LLVM_LIBS})
