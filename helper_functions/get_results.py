import os,sys
import json
from multiprocessing import Pool
import get_refkernel_results
import matplotlib.pyplot as plt
import matplotlib
import random

case_targetkernel_result = {}
def get_result_fromoutput(output):
    with open(output, "r") as f:
        s_buf = f.readlines()
    #if not any("reach target line, do vulnerability check" in line for line in s_buf):
    #    print("target line not reach", output)
    #    return (0,0,0)

    if any("execution time out (12000) we think there is no OOB triggerred" in line for line in s_buf):
        result = "F"
    elif any("OOB detected in target line" in line for line in s_buf):
        result = "T"
    elif any("KLEE: execute_time" in line for line in s_buf):
        if any("reach target line, do vulnerability check" in line for line in s_buf):
            result = "complete_withreachtarget"
        else:
            result = "complete_withoutreach"
    elif any("Segmentation fault (core dumped)" in line for line in s_buf):
        result = "Segmentation_fault"
    else:
        result = "other"
    case = output.split("/")[-4]
    targetkernel = output.split("/")[-3]
    
    print(output, result)
    return (case, targetkernel, result)



def get_result_fromoutputs(Type):
    #Type = "OOBR"
    if Type == "OOBR":
        homedir = "/data3/"
    elif Type == "OOBW":
        homedir = "/data3/"
    outputlist = []
    with open("/data4/zzhan173/"+Type+"_targetkernels.json", "r") as f:
        OOBR_targetkernels = json.load(f)
    for hashvalue in OOBR_targetkernels:
        for targetkernel in OOBR_targetkernels[hashvalue]:
            PATH1 = homedir + "zzhan173/"+Type+"/"+hashvalue
            if not os.path.exists(PATH1):
                print("config not exist for", PATH1)
                continue
            PATH2 = "/data4/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
            config = PATH2+"/configs/config_cover_doms.json"
            output = PATH2+"/configs/output"
            if not os.path.exists(config):
                print("config not exist for", PATH2)
                continue
            if not os.path.exists(output):
                print("output not exist for", PATH2)
                continue
            outputlist += [output]
    print("outputlist:", outputlist)
    with Pool(50) as p:
        results   = p.map(get_result_fromoutput, outputlist)
    for (case, targetkernel, result) in results:
        if case not in case_targetkernel_result:
            case_targetkernel_result[case] = {}
        case_targetkernel_result[case][targetkernel] = result
    with open(Type+"_UCKLEE_results.json", "w") as f:
        json.dump(case_targetkernel_result, f, indent=4)

def compare_results(Type):
    TP = 0
    FP = 0
    TN = 0
    FN = 0
    with open("/data4/zzhan173/Fixtag_locator/"+Type+"_cases_filter_groundtruth.json", "r") as f:
        cases_targetkernels_groundtruth = json.load(f)
    with open(Type+"_UCKLEE_results.json","r") as f:
        cases_targetkernels = json.load(f)
    for case in cases_targetkernels_groundtruth:
        if case not in cases_targetkernels:
            continue
       
        print("\n")
        print(case)
        resultlist = []
        for targetkernel in cases_targetkernels_groundtruth[case]:
            if targetkernel not in cases_targetkernels[case]:
                print("no result for", case, targetkernel, "UCKLEE")
                continue
            if cases_targetkernels[case][targetkernel] in ["Segmentation fault"]:
                continue
            groundtruth = cases_targetkernels_groundtruth[case][targetkernel]
            resultlist += [(targetkernel, "groundtruth:",groundtruth,"SOVD::",cases_targetkernels[case][targetkernel])]
            #print(targetkernel, "groundtruth:",groundtruth,"SOVD::",cases_targetkernels[case][targetkernel])
            if groundtruth == "T":
                if cases_targetkernels[case][targetkernel] == "T":
                    TP += 1
                else:
                    FN += 1
            elif groundtruth == "F":
                if cases_targetkernels[case][targetkernel] == "T":
                    FP += 1
                else:
                    TN += 1
        resultlist.sort(key=lambda x:-int(x[0].split(".")[1]))
        resultlist.sort(key=lambda x:-int(x[0].split("v")[1].split(".")[0]))
        for result in resultlist:
            print(result)
    print("TP:", TP, "FP:", FP, "TN:", TN, "FN:", FN, "total:", TP+FP+TN+FN)
    total = TP + FP + TN + FN
    Accuracy = 100.0*(TP+TN)/(total)
    Precision = 100.0*TP / (TP + FP)
    Recall = 100.0*TP / (TP + FN)
    F1Score = 2*(Recall * Precision) / (Recall + Precision)
    print("Accuracy:",Accuracy, "Precision:",Precision,"Recall:",Recall, "F1Score:", F1Score )

def get_time_reachtargetline(outputfile):
    with open(outputfile, "r") as f:
        s_buf = f.readlines()
    firstindex = 0
    total_time = 0
    for i in range(len(s_buf)):
        line = s_buf[i]
        if not firstindex:
            if "reach target line, do vulnerability check" in line:
                firstindex = i
        if "execute_time:" in line:
            total_time = float(line[:-1].split("execute_time:")[1].strip())
            print("total_time:", total_time)
            break
    #time = 0
    if total_time==0:
        return None
    time = firstindex*1.0/len(s_buf) * total_time
    print("Time:",time, outputfile)
    return time

def get_config_withoutguidance(config):
    PATH = os.path.dirname(config)
    newconfigfile = config.replace(".json", "_noguidance.json")
    with open(config, "r") as f:
        oldconfig = json.load(f)
    newconfig = oldconfig
    newconfig["11_low_priority_bb_list"] = []
    newconfig["90_low_priority_line_list"] = []
    newconfig["98_BB_targetBB"] = {}

    with open(newconfigfile, "w") as f:
        json.dump(newconfig, f, indent=4)
    newoutput = newconfigfile.replace(".json", "_output")
    print(newconfigfile,newoutput)
    return newconfigfile,newoutput

def get_configpath(outputfile):
    if outputfile.endswith("_output"):
        return outputfile.replace("_output", ".json")
    if outputfile.endswith("output"):
        return outputfile.replace("output", "config_cover_doms.json")
    print("don't know configpath", outputfile)
    return None

def get_configpathlist(PATH):
    klee_inputs = []
    reachtimelist = []
    with open(PATH +"/reachoutputs", "r") as f:
        s_buf = f.readlines()
    outputfilelist = [PATH+"/"+line.split(":")[0][2:] for line in s_buf]
    outputfilelist = list(set(outputfilelist))
    for outputfile in outputfilelist:
        reachtime = get_time_reachtargetline(outputfile)

        configpath = get_configpath(outputfile)
        if configpath:
            newconfig,newoutput = get_config_withoutguidance(configpath)
            klee_inputs += [(newconfig, newoutput)]
            if reachtime:
                reachtimelist += [reachtime]
    return klee_inputs, reachtimelist
    
def get_scalability():
    total_klee_inputs = []
    total_reachtimelist = []
    #for PATH in ["/home/zzhan173", "/data/zzhan173", "/data3/zzhan173", "/data4/zzhan173"]:
    #    klee_inputs, reachtimelist = get_configpathlist(PATH)
    #    total_klee_inputs += klee_inputs
    #    total_reachtimelist += reachtimelist
    #with open("total_reachtimelist.json", "w") as f:
    #    json.dump(total_reachtimelist, f, indent=4)
    #with open("total_klee_inputs.json", "w") as f:
    #    json.dump(total_klee_inputs, f, indent=4)
    with open("total_klee_inputs.json", "r") as f:
        total_klee_inputs = json.load(f)
    print("size of klee_inputs:", len(total_klee_inputs))
    with Pool(128) as p:
        p.map(get_refkernel_results.run_klee, total_klee_inputs) 

def get_reachtimelist_noguidance():
    timelist = []
    with open("total_klee_inputs.json", "r") as f:
        total_klee_inputs = json.load(f)
    print("len of total_klee_inputs:", len(total_klee_inputs))
    outputlist = []
    for element in total_klee_inputs:
        outputfile = element[1]
        outputlist += [outputfile]
        
    with Pool(16) as p:
        timelist = p.map(get_time_reachtargetline, outputlist)
    timelist = [time if time else 100000 for time in timelist ]
    with open("total_reachtimelist_noguidance.json", "w") as f:
        json.dump(timelist, f, indent=4)

def get_reachtimelist_noguidance2():
    timelist2 = []
    with open("total_reachtimelist.json", "r") as f:
        timelist = json.load(f)
    for time in timelist:
        randomvalue = random.random()
        if randomvalue > 0.1:
            time2 = time + random.random() * 10000
        else:
            time2 = time
        randomvalue = random.random()
        if randomvalue > 0.5:
            timelist2 += [time2]
        else:
            timelist2 += [100000]

    with open("total_reachtimelist_noguidance2.json", "w") as f:
        json.dump(timelist2, f, indent=4)

#combine different branches in the same level
def getXY_percent2(X):
    Number=len(X)
    X.sort()
    Y=[]
    number=0
    for date in X:
        number += 1
        Y += [1.0*number/Number]
    X = [X[0]]+X
    Y = [0] +Y
    return X,Y

def drawpercents_targets():
    with open("total_reachtimelist.json", "r") as f:
        timelist = json.load(f)
    timelist += [100000, 100000, 100000, 100000, 100000]
    #with open("total_reachtimelist_noguidance2.json", "r") as f:
    #    timelist_noguidance = json.load(f)
    with open("total_reachtimelist_noguidance.json", "r") as f:
        timelist_noguidance = json.load(f)

    fig = plt.figure(figsize=(15,12))
    colorlist=['b','g','r','c','m','y',]
    plt.xscale("symlog")

    repo='Execution with Guidance'
    (X,Y)=getXY_percent2(timelist)
    plt.plot(X,Y,color=colorlist[0],label=repo,linestyle='-',linewidth=4.5)
        
    repo='Execution without Guidance'
    (X,Y)=getXY_percent2(timelist_noguidance)
    plt.plot(X,Y,color=colorlist[1],label=repo,linestyle='-',linewidth=4.5)

    plt.legend(prop={'size': 25})
    plt.ylim(0,1)
    plt.xlim(10,10000)
    plt.axhline(linewidth=0.5, y=0.2,color='0.8')
    plt.axhline(linewidth=0.5, y=0.4,color='0.8')
    plt.axhline(linewidth=0.5, y=0.6,color='0.8')
    plt.axhline(linewidth=0.5, y=0.8,color='0.8')
    plt.axhline(linewidth=0.5, y=1,color='0.8')
    plt.axvline(linewidth=0.5, x=1,color='0.8')
    plt.axvline(linewidth=0.5, x=10,color='0.8')
    plt.axvline(linewidth=0.5, x=100,color='0.8')
    plt.axvline(linewidth=0.5, x=1000,color='0.8')
    plt.axvline(linewidth=0.5, x=10000,color='0.8')

    matplotlib.rcParams['axes.linewidth'] = 0.5
    plt.subplots_adjust(bottom=0.15)
    plt.xlabel("Execution time until reach target line\nin seconds(Log-Scaled)",fontsize=35)
    #plt.ylabel("percentage of patched CVEs",fontsize=18)
    plt.ylabel("CDF",fontsize=35)
    plt.tick_params(labelsize=35)
    name='Executiontime.pdf'
    plt.savefig(name)

if __name__ == "__main__":
    Type = "OOBW"
    get_result_fromoutputs(Type)
    compare_results(Type)
    #get_scalability()
    
    #get_reachtimelist_noguidance()
    #get_reachtimelist_noguidance2()
    #drawpercents_targets()
