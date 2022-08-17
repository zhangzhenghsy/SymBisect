import pydot
import json
import sys,os
import time
import copy

testPATH = "/home/zzhan173/repos/Linux_kernel_UC_KLEE/configs/033724d6/04300d66f0a0/domfiles/domonly.fbcon_modechanged.dot"

def write_dompng(PATH, funcname):
    PATH = PATH+"/doms/domonly."+funcname+".dot"
    output = PATH.replace(".dot", ".png")
    graphs = pydot.graph_from_dot_file(PATH)
    graph = graphs[0]
    graph.write_png(output)

def write_postdompng(PATH, funcname):
    PATH += "/postdoms/postdomonly."+funcname+".dot"
    output = PATH.replace(".dot", ".png")
    graphs = pydot.graph_from_dot_file(PATH)
    graph = graphs[0]
    graph.write_png(output)

# get dictionary of dominator: dominatees
def get_domdic(PATH):
    jsonfile = PATH.replace(".dot", "_node_all_doms.json")
    if os.path.exists(jsonfile):
        with open(jsonfile) as f:
            node_all_doms = json.load(f)
        #print(jsonfile, "already exists")
        return node_all_doms
    
    print("generate node_all_doms for ", PATH)
    graphs = pydot.graph_from_dot_file(PATH)
    graph = graphs[0]
    
    name_label = {}
    node_domnodes = {}
    for node in graph.get_node_list():
        name = node.get_name()
        label = node.get("label")
        #print(label)
        name_label[name] = label
    
    node_direct_doms = {}
    for edge in graph.get_edge_list():
        # return name of src node
        src = edge.get_source()
        dst = edge.get_destination()
        srclabel = name_label[src][2:-2]
        dstlabel = name_label[dst][2:-2]
        if srclabel not in node_direct_doms:
            node_direct_doms[srclabel] = [dstlabel]
        else:
            node_direct_doms[srclabel] += [dstlabel]
    #for node in node_direct_doms:
    #    print(node)
    #    print(node_direct_doms[node])

    node_all_doms = {}
    for node in node_direct_doms:
        if node not in node_all_doms:
            alldoms = get_alldoms(node_direct_doms, node, node_all_doms)
            node_all_doms[node] = alldoms
        #print(node)
        #print(node_all_doms[node])
    with open(jsonfile, 'w') as f:
        json.dump(node_all_doms, f, indent=4, sort_keys=True)
    return node_all_doms

def get_alldoms(node_direct_doms, node, node_all_doms):
    if node in node_all_doms:
        return node_all_doms[node]
    if node in node_direct_doms:
        doms = node_direct_doms[node]
    else:
        return []
    #print(" l68 node_direct_doms[node]:",node, node_direct_doms[node])
    # this deep copy is very important
    direct_doms = copy.deepcopy( node_direct_doms[node])
    for domnode in direct_doms:
        #print("L69", node, domnode)
        if domnode in node_all_doms:
            t0 = time.time()
            localdoms = node_all_doms[domnode]
            doms += localdoms
            #print("L73 ",node,domnode,"time:",(time.time()-t0))
        elif domnode in node_direct_doms:
            t0 = time.time()
            localdoms = get_alldoms(node_direct_doms, domnode, node_all_doms)
            doms += localdoms
            #print("L78 ",node,domnode,"time:",(time.time()-t0))
    doms = list(set(doms))
    doms.sort(key = lambda x:int(x.split("-")[-1]))
    node_all_doms[node] = doms
    #print("add node",node,"to node_all_doms")
    return doms

# requiremt: domfiles and postdomfiles generated
def get_node_mustnodes(PATH, funcname):
    t0 = time.time()
    domPATH = PATH+"/doms/domonly."+funcname+".dot"
    domdic = get_domdic(domPATH)
    #print("get_domdic(domPATH) done:",time.time()-t0)
    #print("\ndomdic:\n",json.dumps(domdic, sort_keys=True, indent=4))
    postdomPATH = PATH+"/postdoms/postdomonly."+funcname+".dot"
    postdomdic = get_domdic(postdomPATH)
    #print("get_domdic(domPATH) done:",time.time()-t0)
    #print("\npostdomdic:\n",json.dumps(postdomdic, sort_keys=True, indent=4))
    #print("\ncombineddomdic:\n",json.dumps(domdic, sort_keys=True, indent=4))

    node_mustnodes = {}

    node_premustnodes = get_node_premustnodes(PATH, funcname)
    node_postmustnodes = get_node_postmustnodes(PATH, funcname)
    node_mustnodes = node_premustnodes
    for dom in node_postmustnodes:
        if dom not in node_mustnodes:
            node_mustnodes[dom] = node_postmustnodes[dom]
        else:
            node_mustnodes[dom] += node_postmustnodes[dom]
    for node in node_mustnodes:
        node_mustnodes[node].sort(key = lambda x:int(x.split("-")[-1]))
    #print("\nnode_mustnodes:\n",json.dumps(node_mustnodes, sort_keys=True, indent=4))
    return node_mustnodes

# requirement: domfiles
# if a BB is reached, what previous BBs must be executed
def get_node_premustnodes(PATH, funcname):
    domPATH = PATH+"/doms/domonly."+funcname+".dot"
    domdic = get_domdic(domPATH)

    node_mustnodes = {}
    for node in domdic:
        doms = domdic[node]
        for dom in doms:
            if dom not in node_mustnodes:
                node_mustnodes[dom] = [node]
            else:
                node_mustnodes[dom] += [node]

    for node in node_mustnodes:
        node_mustnodes[node].sort(key = lambda x:int(x.split("-")[-1]))
    return node_mustnodes

def get_node_postmustnodes(PATH, funcname):
    domPATH = PATH+"/postdoms/postdomonly."+funcname+".dot"
    domdic = get_domdic(domPATH)

    node_mustnodes = {}
    for node in domdic:
        if node == "Post dominance root node":
            continue
        doms = domdic[node]
        for dom in doms:
            if dom not in node_mustnodes:
                node_mustnodes[dom] = [node]
            else:
                node_mustnodes[dom] += [node]

    for node in node_mustnodes:
        node_mustnodes[node].sort(key = lambda x:int(x.split("-")[-1]))
    return node_mustnodes

def get_func_BB_premustBBs(PATH, funclist):
    #BB:BBlist: if BB is executed, then all BBs in BBlist must be executed
    BB_mustBBs = {}
    for func in funclist:
        func_BB_mustBBs = get_node_premustnodes(PATH, func)
        BB_mustBBs.update(func_BB_mustBBs)
    return BB_mustBBs

def get_func_BB_postmustBBs(PATH, funclist):
    #BB:BBlist: if BB is executed, then all BBs in BBlist must be executed
    BB_mustBBs = {}
    for func in funclist:
        func_BB_mustBBs = get_node_postmustnodes(PATH, func)
        BB_mustBBs.update(func_BB_mustBBs)
    return BB_mustBBs

if __name__ == "__main__":
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/033724d6/04300d66f0a0/"
    PATH = "/home/zzhan173/Qemu/OOBW/pocs/c7a91bc7/e69ec487b2c7/"
    #funcname = "fbcon_modechanged"
    funcname = sys.argv[1]
    write_dompng(PATH, funcname)
    write_postdompng(PATH, funcname)
    node_mustnodes = get_node_mustnodes(PATH, funcname)
    print(json.dumps(node_mustnodes, sort_keys=True, indent=4))
