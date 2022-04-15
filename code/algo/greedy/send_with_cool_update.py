"""greedy dispatch 
"""

import copy
from sys import stderr
from datetime import timedelta

from .helper import tug_to_charge_type
from .helper import max_arrival_time, count_profit
from algo.model import TaskState, TugState, ShipState, ChargeTypeList, Tug, ChargeType
from algo.settings import PENALTY, WAITING_TIME, SYSTEM_TIME
from algo.port import get_pier_latlng
from algo.predict_worktime import predict_worktime
from algo.utils.utility import count_move_time, calculate_revenue


class ETug():

    def __init__(self, tug):
        self.tug = tug
        self.next_available_time = tug.next_available_time
        self.pos = tug.pos

    @property
    def type(self):
        return self.tug.type

    @property
    def hp(self):
        return self.tug.hp

    @property
    def tug_id(self):
        return self.tug.tug_id
def upgrade(one):
    if one==ChargeType.TYPE_117:
        return ChargeType.TYPE_118
    elif one==ChargeType.TYPE_118:
        return ChargeType.TYPE_119
    elif one==ChargeType.TYPE_119:
        return ChargeType.TYPE_120
    elif one==ChargeType.TYPE_120:
        return ChargeType.TYPE_0
    else:
        return ChargeType.TYPE_120#如果是最高型號不夠就往下降
def my_dispatch(tasks, tugs, time):
    tasks = copy.deepcopy(tasks)
    tugs = [ETug(tug) for tug in tugs]
    # tugs = copy.deepcopy(tugs)
    # t=get_system_time()#now?
    #task
    todo = []
    for task in tasks:
        if task.task_state == TaskState.UNPROCESSED_UNASSIGNED:
            todo.append(task)
    todo.sort(key=lambda x: x.start_time)
    #tug
    tugs_category={ChargeType.TYPE_117:[], ChargeType.TYPE_118:[], ChargeType.TYPE_119:[], ChargeType.TYPE_120:[], ChargeType.TYPE_0:[]}
    for t in tugs:
        tugs_category[tug_to_charge_type([t])[0]].append(t)
    #assign
    for task in todo:
        stderr.write("Dispathching task {} ...\n".format(task.id))
        required_tugs_list = task.req_types
        print([t for t in required_tugs_list])
        cand=[]
        if task.tug_cnt==1:
            one=required_tugs_list[0]
            if task.id<0 and (one==task.ori_task.tugs[0].type) and len(tugs_category[one])==1:
                one=upgrade(one)
            for i in tugs_category[one]:
                if task.id<0 and (i in task.ori_task.tugs):
                    continue
                move = count_move_time(i.pos, task.start)
                early=task.start_time-i.next_available_time-move
                cand.append([[i], move, early, early])
        elif task.tug_cnt==2:
            one=required_tugs_list[0]
            two=required_tugs_list[1]
            if one == two and len(tugs_category[one])==1:
                two=upgrade(two)
            for i in tugs_category[one]:
                if task.id<0 and (i in task.ori_task.tugs):
                    continue
                for j in tugs_category[two]:
                    if task.id<0 and (j in task.ori_task.tugs):
                        continue
                    #arrival time
                    if i==j:
                        continue
                    cmti = count_move_time(i.pos, task.start)
                    cmtj = count_move_time(j.pos, task.start)
                    mi = task.start_time-i.next_available_time-cmti
                    mj = task.start_time-j.next_available_time-cmtj
                    early=max(mi,mj)
                    move=max(cmti,cmtj)
                    wait=mi+mj
                    cand.append([[i,j], move, early, wait])
        else:
            print("3!!!!!!!")
            one=required_tugs_list[0]
            two=required_tugs_list[1]
            thr=required_tugs_list[2]
            if one == two and len(tugs_category[one])==1 or (one==two and two==thr and len(tugs_category[one])==2):
                two=upgrade(two)
            if two == thr and len(tugs_category[two])==1:
                thr=upgrade(two)
            if one == thr and len(tugs_category[one])==1:
                if len(tugs_category[two])!=1:
                    thr=two
                else:
                    thr=upgrade(thr)
            print(one,two,thr)
            for i in tugs_category[one]:
                if task.id<0 and (i in task.ori_task.tugs):
                    continue
                for j in tugs_category[two]:
                    if task.id<0 and (j in task.ori_task.tugs):
                        continue
                    for k in tugs_category[thr]:
                        if task.id<0 and (k in task.ori_task.tugs):
                            continue
                        #arrival time
                        if i==j or j==k or i==k:
                            continue
                        cmti = count_move_time(i.pos, task.start)
                        cmtj = count_move_time(j.pos, task.start)
                        cmtk = count_move_time(k.pos, task.start)
                        mi = task.start_time-i.next_available_time-cmti
                        mj = task.start_time-j.next_available_time-cmtj
                        mk = task.start_time-k.next_available_time-cmtk
                        early=max(mi,mj,mk)
                        move=max(cmti,cmtj,cmtk)
                        wait=mi+mj+mk
                        cand.append([[i,j,k], move, early, wait])
        cand.sort(key=lambda x: (x[1], x[2]))
        # print([[c[1],c[2]] for c in cand])
        # exit()
        ontime=False
        for c in cand:
            if c[2]>=timedelta(minutes=0):
                ontime=True
                break
        best_set=[]
        if ontime:
            print("ontime")
            minpos=timedelta(minutes=100000)
            for c in cand:
                if c[2]>=timedelta(minutes=0) and c[2]<minpos:
                    minpos=c[1]
                    best_set=[i for i in c[0]]
                    break
        else:
            print("late")
            print("121----",[t.tug_id for t in tugs_category[ChargeType.TYPE_0]])
            maxneg=timedelta(minutes=-100000)
            for c in cand:
                if c[2]>maxneg:
                    maxneg=c[2]
                    best_set=[i for i in c[0]]
        # 更改每個tasks（複製的tasks）的
        # 1.task_state,
        # 2.work_time,
        # 3.tug(配對的tugs)
        # 4.調整tasks的開始時間
        print([i.tug_id for i in best_set])
        if best_set==[]:
            for i in range(len(required_tugs_list)):
                print([t.tug_id for t in tugs_category[required_tugs_list[i]]])
        task.tugs = [best.tug for best in best_set]
        choices = [best.tug for best in best_set]
        res=[]
        times=[]
        res.append(choices)  
        work_time = predict_worktime(task, choices)
        start_time_real = task.start_time
        max_move_time = timedelta(0)
        for tug in best_set:
            move_time = count_move_time(tug.pos, task.start)
            next_time = tug.next_available_time + move_time
            start_time_real = max(start_time_real, next_time)
            max_move_time = max(max_move_time, move_time)

        if task.id < 0: # temp need task
            start_time_real = max(start_time_real-max_move_time, task.start_time) \
                + max_move_time
            work_time = task.ori_task.start_time_real + task.ori_task.work_time \
                - task.start_time

        times.append(start_time_real)
        
        for tug in best_set:
            tug.next_available_time = start_time_real + work_time
            tug.pos = get_pier_latlng(task.to)
    return res, times
    # return [task.tugs for task in tasks], [task.start_time for task in tasks]
