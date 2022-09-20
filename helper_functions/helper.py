
def compare_dics(dic1, dic2):
    for ele in dic1:
        if ele not in dic2:
            print(ele,"not in the latter dic")
        if dic1[ele] != dic2[ele]:
            print(ele, dic1[ele], dic2[ele])
