import helper
import os, subprocess
import json

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

OOBW_skipcases = ["6087eafb76a94c4ac9eb", "b055b1a6b2b958707a21", "a42d84593d6a89a76f26", "838eb0878ffd51f27c41", "cfc0247ac173f597aaaa"]
OOBR_skipcases = ["35101610ff3e83119b1b", "37ba33391ad5f3935bbd","983cb8fb2d17a7af549d","a22c6092d003d6fe1122", "d29e9263e13ce0b9f4fd", "7d027845265d531ba506", "f68108fed972453a0ad4"]
UAFR_skipcases = ["6720d64f31c081c2f708","cbb289816e728f56a4e2c1b854a3163402fe2f88", "9f43bb6a66ff96a21931", "5be8aebb1b7dfa90ef31"]
UAFW_skipcases = ["c7d9ec7a1a7272dd71b3"]
if __name__ == "__main__":
    #with open("/home/zzhan173/Linux_kernel_UC_KLEE/cases/OOBRcases", "r") as f:
    #    s_buf = f.readlines()
    #Type = "UAFR"
    Type = "OOBR"
    PATH = "/data4/zzhan173/Fixtag_locator/"+Type+"_cases_filter.json"
    with open(PATH, "r") as f:
        syzbothash_info = json.load(f)
    for syzbothash in syzbothash_info:
        if syzbothash in OOBW_skipcases:
            continue
        if syzbothash in OOBR_skipcases:
            continue
        if syzbothash in UAFR_skipcases:
            continue
        if syzbothash in UAFW_skipcases:
            continue
        PATH = "/data3/zzhan173/"+Type+"/"+syzbothash+"/refkernel"
        if not os.path.exists(PATH):
            os.makedirs(PATH)
        if os.path.exists(PATH+"/configs/config_cover_doms.json"):
            print("\nAlready generated config_cover_doms.json, skip", PATH,"\n")
            continue
        else:
            print("\nHave not generated  config_cover_doms.json", PATH)
            get_prioritylist(PATH)
