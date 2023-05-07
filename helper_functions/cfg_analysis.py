import networkx as net                                                                                                                
import matplotlib.pyplot as plt
import pydot
import json
import sys,os
import subprocess
import dot_analysis

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

def get_cfg_files(PATH):
    string1 = "cd "+PATH+";mkdir cfgs;cd cfgs;/home/zzhan173/Linux_kernel_UC_KLEE/install/bin/opt  -dot-cfg-only ../built-in_tag.bc"
    print(string1)
    result = command(string1)

def get_node_BB(PATH):
    graphs = pydot.graph_from_dot_file(PATH)
    graph = graphs[0]
    name_label = {}
    for node in graph.get_node_list():
        name = node.get_name()
        label = node.get("label")
        if not label:
            continue
        label = label[2:-2]
        if "|" in label:
            label = label.split("|")[0]
        #print(label)
        name_label[name] = label
    return name_label

def write_dompng(PATH, funcname, node_colors = {}):
    dotpath = PATH+"/cfgs/."+funcname+".dot"
    output = PATH+"/cfgs/"+funcname+".png"
    name_label = get_node_BB(dotpath)
    graphs = pydot.graph_from_dot_file(dotpath)
    graph = graphs[0]
    #print(json.dumps(node_colors, indent=4))
    for node in graph.get_nodes():
        name = node.get_name()
        if name not in name_label:
            continue
        label = name_label[name]
        if label in node_colors:
            fillcolor = node_colors[label]
            node.set_fillcolor(fillcolor)
            #print(label, fillcolor)
    graph.write_png(output)

def get_BB_reachBBs(PATH, func):
    dotpath = PATH+"/cfgs/."+func+".dot"
    #if not os.path.exists(dotpath):
    #    get_cfg_files(PATH)
    if not os.path.exists(dotpath):
        print("no cfg for func", func)
        return None    
    #write_dompng(PATH, func)
    name_label = get_node_BB(dotpath)
    BB_reachBBs = {}
    netG = net.drawing.nx_agraph.read_dot(dotpath)
    for node in netG.nodes:
        BB = name_label[node]
        reachnodes = net.descendants(netG, node)
        reachBBs = [name_label[No] for No in reachnodes]
        BB_reachBBs[BB] = reachBBs
        BB_reachBBs[BB].sort()
    return BB_reachBBs

def get_BB_directBBs(PATH, func):
    dotpath = PATH+"/cfgs/."+func+".dot"
    graph = pydot.graph_from_dot_file(dotpath)[0]
    name_label = get_node_BB(dotpath)
    #print(json.dumps(name_label, indent=4))

    BB_directBBs = {}
    for edge in graph.get_edges():
        srcnode = edge.get_source()
        if ":" in srcnode:
            srcnode = srcnode.split(":")[0]
        srclabel = name_label[srcnode]
        if srclabel not in BB_directBBs:
            BB_directBBs[srclabel] = []
        child_node = edge.get_destination()
        dstlabel = name_label[child_node]
        BB_directBBs[srclabel] += [dstlabel]

    return BB_directBBs
    #print(json.dumps(BB_directBBs, indent=4))

def get_BB_childBBs(PATH, func):
    dotpath = PATH+"/cfgs/."+func+".dot"
    if not os.path.exists(dotpath):
        print("no cfg for func", func)
        return None
    
    name_label = get_node_BB(dotpath)
    BB_childBBs = {}
    netG = net.drawing.nx_agraph.read_dot(dotpath)

    for node in netG.nodes:
        BB = name_label[node]
        children = list(netG.successors(node))
        children = list(set(children).difference({node}))

        childBBs = [name_label[No] for No in children]
        BB_childBBs[BB] = childBBs
        BB_childBBs[BB].sort()
    return BB_childBBs

#
def get_func_BB_blacklist(PATH, MustBB):
    #Part I : the BBs which cannot reach targetBB
    func = MustBB.split("built-in.bc-")[1].split("-")[0]
    BB_reachBBs = get_BB_reachBBs(PATH, func)
    blackBBs = [BB for BB in BB_reachBBs if MustBB not in BB_reachBBs[BB]]
    blackBBs.remove(MustBB)

    #Part II : the BBs in blacklinelist
    with open(PATH + "/lineguidance/line_blacklist_doms.json", "r") as f:
        low_priority_line_list_doms = json.load(f)
    with open(PATH+"/lineguidance/BB_lineinfo.json") as f:
        BB_lineinfo = json.load(f)
    for BB in BB_reachBBs:
        if any(line in low_priority_line_list_doms for line in BB_lineinfo[BB]):
            blackBBs += [BB]
    blackBBs = list(set(blackBBs))
    blackBBs.sort()
    return blackBBs

def get_func_BB_mustlist(PATH, MustBB):
    func = MustBB.split("built-in.bc-")[1].split("-")[0]
    func_BB_mustBBs = dot_analysis.get_node_premustnodes(PATH, func)
    #print("get_func_BB_mustlist() func_BB_mustBBs:", func_BB_mustBBs)
    if MustBB in func_BB_mustBBs:
        mustBBs = [MustBB] + func_BB_mustBBs[MustBB]
    else:
        mustBBs = [MustBB]
    return mustBBs

def get_node_colors(MustBB, mustBBs, blackBBs):
    node_colors = {}
    node_colors[MustBB] = "green"
    for mustBB in mustBBs:
        node_colors[mustBB] = "green"
    for blackBB in blackBBs:
        node_colors[blackBB] = "blue"
    return node_colors

def write_color_png(PATH, MustBB):
    func = MustBB.split("built-in.bc-")[1].split("-")[0]
    blackBBs = get_func_BB_blacklist(PATH, MustBB)
    print("blackBBs:", blackBBs)
    mustBBs = get_func_BB_mustlist(PATH, MustBB)
    print("mustBBs:", mustBBs)
    node_colors = get_node_colors(MustBB, mustBBs, blackBBs)

    coverBBs = get_func_BB_coverlist(PATH, func)
    for coverBB in  coverBBs:
        if coverBB not in node_colors:
            node_colors[coverBB] = "yellow"
    write_dompng(PATH, func, node_colors)

# Get the BBs executed. Note that there may be FPs (the BBs which cannot reach targetBB)
# and FNs (can be alleviated with dom trees)
def get_func_BB_coverlist(PATH, func):
    with open(PATH+"/lineguidance/func_BB_whitelist_predoms.json") as f:
        func_BB_whitelist_predoms = json.load(f)
    return func_BB_whitelist_predoms[func]

def get_func_BB_targetBBs(PATH):
    with open(PATH+"/mustBBs", "r") as f:
        s_buf = f.readlines()
    MustBBlist = [line[:-1] for line in s_buf]
    total_BB_targetBB = {}
    for MustBB in MustBBlist:
        BB_targetBB = get_func_BB_targetBB(PATH, MustBB)
        total_BB_targetBB.update(BB_targetBB)

    with open(PATH+"/lineguidance/BB_targetBB.json", "w") as f:
        json.dump(total_BB_targetBB, f, indent=4)

    with open(PATH+"/lineguidance/BB_lineinfo.json", "r") as f:
        BB_lineinfo = json.load(f)
    for BB in BB_targetBB:
        print("\n"+BB, BB_lineinfo[BB])
        print(BB_targetBB[BB], BB_lineinfo[BB_targetBB[BB]])

# I'm trying to summarize some patterns where there is a guidance that BB1 -> BB2.
# In symbolic execution if it doesn't happen, I will try to under-constraint the condition
def get_func_BB_targetBB(PATH, MustBB):
    BB_targetBB = {}

    func = MustBB.split("built-in.bc-")[1].split("-")[0]
    BB_directBBs = get_BB_directBBs(PATH, func)

    blackBBs = get_func_BB_blacklist(PATH, MustBB)
    #print("blackBBs:", blackBBs)
    mustBBs = get_func_BB_mustlist(PATH, MustBB)
    #print("mustBBs:", mustBBs)
    coverBBs = get_func_BB_coverlist(PATH, func)

    for BB in BB_directBBs:
        directBBs = BB_directBBs[BB]
        if len(directBBs) == 1:
            continue
        if BB in blackBBs:
            continue

        count_mustBBs = 0
        count_blackBBs = 0
        for targetBB in directBBs:
            if targetBB in blackBBs:
                count_blackBBs += 1
            elif targetBB in mustBBs:
                count_mustBBs += 1
        if count_blackBBs == len(directBBs) -1:
            for targetBB in directBBs:
                if targetBB not in blackBBs:
                    BB_targetBB[BB] = targetBB
        elif count_mustBBs == 1:
            for targetBB in directBBs:
                if targetBB in mustBBs:
                    BB_targetBB[BB] = targetBB

    BB_targetBB = {k: BB_targetBB[k] for k in sorted(BB_targetBB)}
    BB_targetBB = {k: BB_targetBB[k] for k in sorted(BB_targetBB, key=lambda x:len(x))}
    write_color_png(PATH, MustBB)
    return BB_targetBB

if __name__ == "__main__":
    #PATH = "/data/zzhan173/Qemu/OOBW/pocs/c7a91bc7/e69ec487b2c7/"
    #func = "do_mount"
    PATH = sys.argv[1]
    MustBB = sys.argv[2]
    func = MustBB.split("built-in.bc-")[1].split("-")[0]
    #get_cfg_files(PATH)
    #func = sys.argv[1]
    #write_dompng(PATH, func)
    #write_color_png(PATH, MustBB)
    #get_BB_directBBs(PATH, func)
    get_func_BB_targetBB(PATH, MustBB)
    #BB_reachBBs = get_BB_reachBBs(PATH, func)
    #print(json.dumps(BB_reachBBs, sort_keys=True, indent=4))

    #BB_childBBs = get_BB_childBBs(PATH, func)
    #print(json.dumps(BB_childBBs, sort_keys=True, indent=4))

