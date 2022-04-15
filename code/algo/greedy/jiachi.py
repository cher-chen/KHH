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
        # stderr.write("Dispathching task {} ...\n".format(task.id))
        required_tugs_list = task.req_types
        cand=[]
        if task.tug_cnt==1:
            for i in tugs_category[required_tugs_list[0]]:
                move = count_move_time(i.pos, task.start)
                early=task.start_time-i.next_available_time-move
                cand.append([[i], move, early, early])
        elif task.tug_cnt==2:
            one=required_tugs_list[0]
            two=required_tugs_list[1]
            if one == two and len(tugs_category[one])==1:
                if two==ChargeType.TYPE_117:
                    two=ChargeType.TYPE_118
                elif two==ChargeType.TYPE_118:
                    two=ChargeType.TYPE_119
                elif two==ChargeType.TYPE_119:
                    two=ChargeType.TYPE_120
                else:
                    two=ChargeType.TYPE_0
            for i in tugs_category[one]:
                for j in tugs_category[two]:
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
            # print("3!!!!!!!")
            one=required_tugs_list[0]
            two=required_tugs_list[1]
            thr=required_tugs_list[2]
            if one == two and len(tugs_category[one])==1:
                if two==ChargeType.TYPE_117:
                    two=ChargeType.TYPE_118
                elif two==ChargeType.TYPE_118:
                    two=ChargeType.TYPE_119
                elif two==ChargeType.TYPE_119:
                    two=ChargeType.TYPE_120
                else:
                    two=ChargeType.TYPE_0
            if two == thr and len(tugs_category[two])==1:
                if two==ChargeType.TYPE_117:
                    thr=ChargeType.TYPE_118
                elif two==ChargeType.TYPE_118:
                    thr=ChargeType.TYPE_119
                elif two==ChargeType.TYPE_119:
                    thr=ChargeType.TYPE_120
                else:
                    thr=ChargeType.TYPE_0
            if one == thr and len(tugs_category[one])==1:
                if len(tugs_category[two])!=1:
                    thr=two
                else:
                    if two==ChargeType.TYPE_117:
                        thr=ChargeType.TYPE_118
                    elif two==ChargeType.TYPE_118:
                        thr=ChargeType.TYPE_119
                    elif two==ChargeType.TYPE_119:
                        thr=ChargeType.TYPE_120
                    else:
                        thr=ChargeType.TYPE_0
            # print(one,two,thr)
            for i in tugs_category[one]:
                for j in tugs_category[two]:
                    for k in tugs_category[thr]:
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
            # print("ontime")
            minpos=timedelta(minutes=100000)
            for c in cand:
                if c[2]>=timedelta(minutes=0) and c[2]<minpos:
                    minpos=c[1]
                    best_set=[i for i in c[0]]
                    break
        else:
            # print("late")
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
        # print([i.tug_id for i in best_set])
        task.tugs = [best.tug for best in best_set]
        work_time = predict_worktime(task, best_set)

        arrival_time = max_arrival_time(task, best_set)
        max_move_time = max([count_move_time(tug.pos, task.start) for tug in best_set])
        task.delay_time = max(timedelta(0), arrival_time-task.start_time)
        task.start_time = task.start_time + task.delay_time

        if task.id < 0: # temp need task
            # print(task.id)
            # print("!!!!!!!!!!!!!!!!\n")
            task.start_time = max(task.start_time-max_move_time, task.start_time-task.delay_time) \
                + max_move_time
            work_time = task.ori_task.start_time + task.ori_task.work_time \
                - (task.start_time-task.delay_time)

        for tug in best_set:
            tug.next_available_time = task.start_time + work_time
            tug.pos = get_pier_latlng(task.to)
        for tug in best_set:
            for i in range(len(tugs)):
                if tugs[i].tug_id == tug.tug_id:
                    tugs[i].next_available_time = task.start_time + work_time
                    tugs[i].pos = get_pier_latlng(task.to)
            
    return [task.tugs for task in tasks], [task.start_time for task in tasks]
