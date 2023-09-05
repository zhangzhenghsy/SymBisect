import helper
import os, subprocess
import sys
import json
import get_syzkaller
def get_prioritylist(PATH):
    print("get_prioritylist()")
    string1 = "cd /home/zzhan173/Linux_kernel_UC_KLEE;python3 helper_functions/get_prioritylist.py all "+PATH+">"+PATH+"/get_prioritylist_log 2>&1"
    print(string1)
    resultlines = helper.command(string1)
    #with open(PATH+"/get_prioritylist_log", "w") as f:
    #    for line in resultlines:
    #        f.write(line)
    if os.path.exists(PATH+"/configs/config_cover_doms.json"):
        print("generate config_cover_doms.json successfully")
    else:
        print("generate config_cover_doms.json fail")
    return

def clean_files(PATH):
    string1 = "cd "+PATH+"; rm -rf klee-*"
    print(string1)
    helper.command(string1)

OOBW_skipcases = ["6087eafb76a94c4ac9eb", "b055b1a6b2b958707a21", "a42d84593d6a89a76f26", "838eb0878ffd51f27c41",  "59af7bf76d795311da8c","cfc0247ac173f597aaaa", "dc3b1cf9111ab5fe98e7", "59b7daa4315e07a994f1"]
OOBR_skipcases = ["35101610ff3e83119b1b", "37ba33391ad5f3935bbd","983cb8fb2d17a7af549d","a22c6092d003d6fe1122", "d29e9263e13ce0b9f4fd", "7d027845265d531ba506", "f68108fed972453a0ad4"]
UAFR_skipcases = ["6720d64f31c081c2f708","cbb289816e728f56a4e2c1b854a3163402fe2f88", "9f43bb6a66ff96a21931", "5be8aebb1b7dfa90ef31"]
UAFW_skipcases = ["c7d9ec7a1a7272dd71b3"]
#Reproducers don't trigger the vulnerability
UAF_skipcases = ["373ce58a5e9ddec1b8ee55d9f7353db5b565cdc3", "ad1f53726c3bd11180cb", "b75c138e9286ac742647" , "7be8b464a3a27e6dc5c73d3ffe3b56dc0cf51e52" , "13bef047dbfffa5cd1af"]
total_skipcases = OOBW_skipcases + OOBR_skipcases + UAFR_skipcases + UAFW_skipcases + UAF_skipcases
if __name__ == "__main__":
    #with open("/home/zzhan173/Linux_kernel_UC_KLEE/cases/OOBRcases", "r") as f:
    #    s_buf = f.readlines()
    #Type = "UAFR"
    #Type = "OOBW"
    Type = "UAF"
    PATH = "/data4/zzhan173/Fixtag_locator/"+Type+"_cases_filter.json"
    specific_case = None
    if len(sys.argv) > 1:
        specific_case = sys.argv[1]
    with open(PATH, "r") as f:
        syzbothash_info = json.load(f)
    for syzbothash in syzbothash_info:
        if specific_case and syzbothash!=specific_case:
            continue
        if syzbothash in total_skipcases:
            continue
        PATH = "/data3/zzhan173/"+Type+"/"+syzbothash+"/refkernel"
        if not os.path.exists(PATH):
            os.makedirs(PATH)
        i386 = None
        if "386" in syzbothash_info[syzbothash]["manager"]:
            i386 = True

        if not specific_case and os.path.exists(PATH+"/configs/config_cover_doms.json"):
            print("\nAlready generated config_cover_doms.json, skip", PATH,"\n")
            continue
        syzkaller_commit = syzbothash_info[syzbothash]["syzkaller"]
        print("\nHave not generated  config_cover_doms.json", PATH)
        get_syzkaller.compile_syzkaller(PATH, syzkaller_commit, i386)
        get_prioritylist(PATH)
