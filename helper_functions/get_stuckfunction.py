import os, sys

def get_callstack_functions(configfile):
    with open(configpath) as f:
        config = json.load(f)
    funcnames = config["97_calltrace"]
    return funcnames

def get_func_percent_2(lineoutputfile):
    with open(lineoutputfile, "r") as f:
        s_buf = f.readlines()
    func_count = {}
    func_percentage = []
    func_callers = {}
    calltracelist = []
    for line in s_buf:
        if "call trace:" in line:
            calltrace = line.split("call trace:")[1][:-1]
            calltracelist = calltrace.split("--")
            caller_func = calltracelist[0]
            func = calltracelist[-1]
            if func not in func_callers:
                func_callers[func] = []
            if calltrace not in func_callers[func]:
                func_callers[func] += [calltrace]
        if len(line.split(" ")) < 3:
            continue
        funcname = line.split(" ")[3]
        if not calltracelist or funcname != calltracelist[-1]:
            continue
        if "sourcecodeLine:" in line or "call trace:" in line:
            for func in calltracelist:
                if func not in func_count:
                    func_count[func] = 0
                func_count[func] += 1
    
    total = func_count[caller_func]
    for func in func_count:
        func_percentage += [(func, 100.0*func_count[func]/total)]
    func_percentage.sort(key= lambda x:-x[1])
    print("total lines:", total)

    skipfuncname = None
    for (func,percent) in func_percentage:
        #if percent < 5:
        #    continue
        func = func.strip()
        print(func, percent)
        if func in func_callers:
            print(func_callers[func])

def get_func_percent(PATH, callstack_functions = []):
    print("\nget_func_percent")
    #callstack_functions = get_callstack_functions(PATH)
    print("callstack_functions: ", callstack_functions)

    with open(PATH+"/lineoutput", "r") as f:
        s_buf = f.readlines()
    
    func_count = {}
    func_percentage = []
    func_callers = {}
    calltracelist = []
    for line in s_buf:
        if "call trace:" in line:
            calltrace = line.split("call trace:")[1][:-1]
            calltracelist = calltrace.split("--")
            caller_func = calltracelist[0]
            func = calltracelist[-1]
            if func not in func_callers:
                func_callers[func] = []
            if calltrace not in func_callers[func]:
                func_callers[func] += [calltrace]
        if len(line.split(" ")) < 3:
            continue
        funcname = line.split(" ")[3]
        if not calltracelist or funcname != calltracelist[-1]:
            continue
        if "sourcecodeLine:" in line or "call trace:" in line:
            for func in calltracelist:
                if func not in func_count:
                    func_count[func] = 0
                func_count[func] += 1
    
    total = func_count[caller_func]
    for func in func_count:
        func_percentage += [(func, 100.0*func_count[func]/total)]
    func_percentage.sort(key= lambda x:-x[1])
    print("total lines:", total)

    skipfuncname = None
    for (func,percent) in func_percentage:
        if percent < 5:
            continue
        func = func.strip()
        print(func, percent)
        if not skipfuncname and func not in callstack_functions:
            skipfuncname = func
        if func in func_callers:
            print(func_callers[func])
    return skipfuncname



if __name__ == "__main__":
    #PATH = "/home/zzhan173/Linux_kernel_UC_KLEE/lineoutput"
    PATH = sys.argv[1]
    get_func_percent_2(PATH)
