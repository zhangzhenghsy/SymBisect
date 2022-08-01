import os,sys
import json

def transfer_charlist2decimal(charlist):
    index_value = {}
    for index in range(len(charlist)):
        intvalue = ord(charlist[index])
        #print(index, intvalue)
        index_value[str(index)] = intvalue
    return index_value

def argu_pointer(charlist):
    #print(charlist)
    return transfer_charlist2decimal(charlist)

def argu_int(intvalue):
    index_value ={}
    index_value["0"] = intvalue
    return index_value

def get_concolicmap(parameterlist):
    all_index_value = {}
    for index in range(len(parameterlist)):
        parameter = parameterlist[index]
        print(index, parameter)
        if parameter == "":
            continue
        if type(parameter) == tuple:
            if parameter[0] == "p":
                index_value = argu_pointer(parameter[1])
                all_index_value[str(index)] = index_value
        elif type(parameter) == int:
            index_value = argu_int(parameter)
            all_index_value[str(index)] = index_value
    return all_index_value

if __name__ == "__main__":
    parameterlist = [("p""tmpfs\000"), ("p","./file0\000"), 0,0,0,"", ("p", "\x6d\x70\x6f\x6c\x3d\x3d\x93\x74\x61\x74\x69\x63\x3a\x36\x2d\x36\x3a")] 
    all_index_value = get_concolicmap(parameterlist)
    
    print(json.dumps(all_index_value, indent=4, sort_keys=True))
    #charlist = "\x6d\x70\x6f\x6c\x3d\x3d\x93\x74\x61\x74\x69\x63\x3a\x36\x2d\x36\x3a"
    #index_value = transfer_charlist2decimal(charlist)
    #print(index_value)

