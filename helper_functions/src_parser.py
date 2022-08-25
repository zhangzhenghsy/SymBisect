#!/usr/bin/python

import sys,os
import re
from pygments.lexers import get_lexer_by_name
from pygments.token import Token
#from pycparser import c_parser
import json
dbg_out = False

#The array's base index is 0, but base line number used by addr2line is 1, so we need adjustments when necessary.
LINE_BASE = 1

#It seems that the line number is based on 1 instead of 0 for DWARF, so we need to +1 for each line number.
def adj_lno_tuple(t):
    return tuple(map(lambda x:x+LINE_BASE,t))

def _adj_lno_patch(inf):
    for k in inf:
        if 'add' in inf[k]:
            for t in list(inf[k]['add']):
                inf[k]['add'][(t[0]+LINE_BASE,t[1]+LINE_BASE)] = inf[k]['add'][t]
                inf[k]['add'].pop(t)
        if 'del' in inf[k]:
            for t in list(inf[k]['del']):
                inf[k]['del'][(t[0]+LINE_BASE,t[1]+LINE_BASE)] = inf[k]['del'][t]
                inf[k]['del'].pop(t)

def _trim_lines(buf):
    for i in range(len(buf)):
        if len(buf[i]) == 0:
            continue
        if buf[i][-1] == '\n':
            buf[i] = buf[i][:-1]

#cur_func_inf = {}
#cur_func_inf_r = {}
#This function parse a C source file, extract all the function definitions in it.
def build_func_map(s_buf):
    #global cur_func_inf
    #global cur_func_inf_r
    #cur_func_inf.clear()
    #cur_func_inf_r.clear()
    cur_func_inf = {}
    cur_func_inf_r = {}
    cnt = 0
    prev_pos = (0,0)
    in_str = False
    in_comment = 0
    ifelse=False
    numberif=0
    #TODO: Maybe we should utilize lexer to avoid all the mess below.
    for i in range(len(s_buf)):
        print(i, s_buf[i])
        #print("size of cur_func_inf_r:", len(cur_func_inf_r))
        if s_buf[i].startswith('#else'):
            #print "#else",i
            numberif +=1
            ifelse=True
        if ifelse:
            if s_buf[i].startswith('#if'):
                numberif +=1
            elif s_buf[i].startswith('#endif'):
                numberif -=1
                if numberif==0:
                    ifelse=False
            continue
        for j in range(len(s_buf[i])):
            if s_buf[i][j] == '{':
                if in_str or in_comment > 0:
                    continue
                if cnt == 0:
                    prev_pos = (i,j)
                cnt += 1
            elif s_buf[i][j] == '}':
                if in_str or in_comment > 0:
                    continue
                cnt -= 1
                if cnt == 0:
                    #We have found a out-most {} pair, it *may* be a function. 
                    func_head = _detect_func_head(s_buf,prev_pos)
                    #print("func_head:",func_head)
                    if func_head:
                        (func,arg_cnt) = func_head
                        #update: head contains multiple lines
                        if func_head[0]+'(' not in s_buf[prev_pos[0]-LINE_BASE]:
                            startline=prev_pos[0]-1
                            funcname=func_head[0]
                            while True:
                                print("startline:",startline)
                                if funcname+'(' in s_buf[startline-1]:
                                    break
                                if s_buf[startline-1].startswith("(") and funcname in s_buf[startline-2]:
                                    break
                                startline -=1
                            cur_func_inf[(startline,i+LINE_BASE)] = func_head
                            cur_func_inf_r[(func,startline)] = ((startline,i+LINE_BASE),arg_cnt)
                            #cur_func_inf[(prev_pos[0]-1,i+1)] = func_head
                            #cur_func_inf_r[(func,prev_pos[0]-1)] = ((prev_pos[0]-1,i+1),arg_cnt)
                        else:
                            cur_func_inf[(prev_pos[0],i+LINE_BASE)] = func_head
                        #NOTE: Sometimes one file can have multiple functions with same name, due to #if...#else.
                        #So to mark a function we need both name and its location.
                            cur_func_inf_r[(func,prev_pos[0])] = ((prev_pos[0],i+LINE_BASE),arg_cnt)
                elif cnt < 0:
                    print('!!! Syntax error: ' + s_buf[i])
                    print('prev_pos: %d:%d' % adj_lno_tuple(prev_pos))
                    print('------------Context Dump--------------')
                    l1 = max(i-5,0)
                    l2 = min(i+5,len(s_buf)-1)
                    print(''.join([s_buf[i] for i in range(l1,l2+1)]))
                    return
            elif s_buf[i][j] == '"' and in_comment == 0:
                in_str = not in_str
            elif s_buf[i][j] == '/' and j + 1 < len(s_buf[i]) and s_buf[i][j+1] == '/' and not in_str:
                #Line comment, skip this line
                break
            elif s_buf[i][j] == '/' and j + 1 < len(s_buf[i]) and s_buf[i][j+1] == '*' and not in_str:
                #Block comment start
                in_comment += 1
            elif s_buf[i][j] == '*' and j + 1 < len(s_buf[i]) and s_buf[i][j+1] == '/' and not in_str:
                #Block comment end
                in_comment -= 1
        #print(len(cur_func_inf_r))
    #print("before return:",len(cur_func_inf_r))
    return cur_func_inf_r

#pos is the position of leading '{' of a potential function.
def _detect_func_head(s_buf,pos):
    #print(" _detect_func_head pos:", pos)
    def _back(pos):
        i = pos[0]
        j = pos[1]
        return (i,j-1) if j > 0 else (i-1,len(s_buf[i-1])-1) if i > 0 else None
    #First ensure that there is nothing between the '{' and a ')'
    p = pos
    while True:
        p = _back(p)
        if not p:
            break
        if s_buf[p[0]][p[1]] in ('\n',' ','\t', '\\'):
            continue
        elif s_buf[p[0]][p[1]] == ')':
            cnt = 1
            comma_cnt = 0
            any_arg = False
            while True:
                p = _back(p)
                if not p:
                    break
                if s_buf[p[0]][p[1]] == ')':
                    cnt += 1
                elif s_buf[p[0]][p[1]] == '(':
                    cnt -= 1
                elif s_buf[p[0]][p[1]] == ',':
                    comma_cnt += 1
                elif not s_buf[p[0]][p[1]] in ('\n',' ','\t'):
                    any_arg = True
                if cnt == 0:
                    break
            arg_cnt = comma_cnt + 1 if comma_cnt > 0 else 1 if any_arg else 0
            if cnt == 0:
                #It should be a function, extract the func name.
                #First skip the tailing spaces
                while True:
                    p = _back(p)
                    if not p:
                        break
                    if not s_buf[p[0]][p[1]] in ('\n',' ','\t'):
                        break
                if not p:
                    return None
                #Record the function name
                func = [s_buf[p[0]][p[1]]]
                while True:
                    p = _back(p)
                    if not p:
                        break
                    if s_buf[p[0]][p[1]] in ('\n',' ','\t','*'):
                        break
                    func.append(s_buf[p[0]][p[1]])
                func.reverse()
                return (''.join(func),arg_cnt)
            else:
                return None
        else:
            return None
    return None

def get_file_funcrange(repo, filename):
    PATH = repo+filename
    with open(PATH,"r") as f:
        f_buf=f.readlines()
    try:
        cur_func_inf_r = build_func_map(f_buf)
    except:
        return None
    if not cur_func_inf_r:
        return None

    func_range = {}
    for element in cur_func_inf_r:
        func = element[0]
        st,ed = cur_func_inf_r[element][0]
        if func not in func_range:
            func_range[func] = []
        func_range[func] += range(st, ed+1)
    for func in func_range:
        func_range[func] = [filename+":"+str(line) for line in func_range[func]]
        func_range[func].sort()
    return func_range

def get_files_funcrange(repo, filenamelist):
    total_func_range = {}
    for filename in filenamelist:
        func_range = get_file_funcrange(repo, filename)
        if not func_range:
            continue
        for func in func_range:
            if func not in total_func_range:
                total_func_range[func] = func_range[func]
            else:
                total_func_range[func] += func_range[func]
    return total_func_range

if __name__ == "__main__":
    repo = "/home/zzhan173/repos/linux/"
    #filename = "security/tomoyo/audit.c"
    filename = sys.argv[1]
    func_range = get_file_funcrange(repo, filename)
    print(func_range)
    print(json.dumps(func_range, sort_keys=True, indent=4))
