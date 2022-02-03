#===------------------------------------------------------------------------===#
#
#                     The KLEE Symbolic Virtual Machine
#
# This file is distributed under the University of Illinois Open Source
# License. See LICENSE.TXT for details.
#
#===------------------------------------------------------------------------===#

klee_add_component(Listener
        Listener.cpp
        Listener.h
        ListenerService.cpp
        ListenerService.h)

set_target_properties(Listener PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(Listener PUBLIC Tool_lib)
