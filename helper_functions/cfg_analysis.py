import networkx as net                                                                                                                
import matplotlib.pyplot as plt
import pydot
import json
import sys,os
import subprocess

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

def write_dompng(PATH, funcname):
    dotpath = PATH+"/cfgs/."+funcname+".dot"
    output = PATH+"/cfgs/"+funcname+".png"
    graphs = pydot.graph_from_dot_file(dotpath)
    graph = graphs[0]
    graph.write_png(output)

def get_BB_reachBBs(PATH, func):
    dotpath = PATH+"/cfgs/."+func+".dot"
    #if not os.path.exists(dotpath):
    #    get_cfg_files(PATH)
    if not os.path.exists(dotpath):
        print("no cfg for func", func)
        return None    
    write_dompng(PATH, func)
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

if __name__ == "__main__":
    #PATH = "/data/zzhan173/Qemu/OOBW/pocs/c7a91bc7/e69ec487b2c7/"
    #func = "do_mount"
    PATH = sys.argv[1]
    func = sys.argv[2]
    #get_cfg_files(PATH)
    #func = sys.argv[1]
    write_dompng(PATH, func)
    #BB_reachBBs = get_BB_reachBBs(PATH, func)
    #print(json.dumps(BB_reachBBs, sort_keys=True, indent=4))

    #BB_childBBs = get_BB_childBBs(PATH, func)
    #print(json.dumps(BB_childBBs, sort_keys=True, indent=4))

