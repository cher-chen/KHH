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
        stderr.write("Dispathching task {} ...\n".format(task.id))
        required_tugs_list = task.req_types
        cand=[]
        if task.tug_cnt==1:
            for i in tugs_category[required_tugs_list[0]]:
                mi = i.next_available_time+count_move_time(i.pos, task.start)
                early=task.start_time-mi
                cand.append([[i], early, early])
        else:
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
                    mi = task.start_time-i.next_available_time-count_move_time(i.pos, task.start)
                    mj = task.start_time-j.next_available_time-count_move_time(j.pos, task.start)
                    early=max(mi,mj)
                    wait=mi+mj
                    cand.append([[i,j], early, wait])

        cand.sort(key=lambda x: (x[1], x[2]))
        ontime=False
        for c in cand:
            if c[1]>=timedelta(minutes=0):
                ontime=True
                break
        best_set=[]
        if ontime:
            print("ontime")
            minpos=timedelta(minutes=100000)
            for c in cand:
                if c[1]>=timedelta(minutes=0) and c[1]<minpos:
                    minpos=c[1]
                    best_set=[i for i in c[0]]
        else:
            print("late")
            print(task.id)
            # print([c[0] for c in cand])
            print(task.req_types)
            print([t.tug_id for t in tugs_category[ChargeType.TYPE_117]])
            maxneg=timedelta(minutes=-100000)
            for c in cand:
                if c[1]>maxneg:
                    maxneg=c[1]
                    best_set=[i for i in c[0]]
        # 更改每個tasks（複製的tasks）的
        # 1.task_state,
        # 2.work_time,
        # 3.tug(配對的tugs)
        # 4.調整tasks的開始時間
        print([i.tug_id for i in best_set])
        task.tugs = [best.tug for best in best_set]
        work_time = predict_worktime(task, best_set)

        arrival_time = max_arrival_time(task, best_set)
        max_move_time = max([count_move_time(tug.pos, task.start) for tug in best_set])
        task.delay_time = max(timedelta(0), arrival_time-task.start_time)
        task.start_time = task.start_time + task.delay_time

        if task.id < 0: # temp need task
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
def efficient_dispatch(tasks, tugs, time):
    """
    Args:
        tasks ([Task]): a list which stores the tasks to be planned
        tugs ([Tug]): a list of tugs avaiable 
        time (datetime): current time in simulator

    Returns:
        [[Tug]]: a list of lists of tugs in the same order as the given tasks
        [datetime]: a list of times at which the tasks actually start
    """

    # print("Dispatching {} tasks with Efficient Greedy...\n".format(len(tasks)), file=stderr)

    tasks = copy.deepcopy(tasks)
    tugs = [ETug(tug) for tug in tugs]

    for task in tasks:
        # print("Dispathching task {} ...\n".format(task.id), file=stderr)

        # 先用required_tug_set算出這個task的work_time
        required_tugs_list = task.req_types
        tug_set = []
        tug_set = sorted(tugs, key=lambda x: x.type)
        best_set = []

        for i in required_tugs_list:
            l = 0
            while l < len(tug_set):
            # for l in range(len(tug_set)):
                temp_move_time = count_move_time(tug_set[l].pos, task.start)
                if tug_to_charge_type(tug_set)[l] >= i and \
                ((tug_set[l].next_available_time + temp_move_time - task.start_time <= WAITING_TIME ) or \
                (tug_set[l].next_available_time + temp_move_time - SYSTEM_TIME <= WAITING_TIME )):
                    if task.id < 0:
                        found = True
                        for t in task.ori_task.tugs:
                            if tug_set[l].tug_id == t.tug_id:
                                found =False
                                break
                        if found:
                            best_set.append(tug_set[l])
                            del tug_set[l]
                            break
                    else :
                        best_set.append(tug_set[l])
                        del tug_set[l]
                        break
                l += 1
       
        if len(best_set) != len(required_tugs_list) and task.id > 0:
            # stderr.write("No best set!\n")
            best_set = []
            task.start_time += timedelta(minutes = 10)
            task.delay_time += timedelta(minutes = 10)
            continue

        # 更改每個tasks（複製的tasks）的
        # 1.task_state,
        # 2.work_time,
        # 3.tug(配對的tugs)
        # 4.調整tasks的開始時間

        task.tugs = [best.tug for best in best_set]
        work_time = predict_worktime(task, best_set)

        arrival_time = max_arrival_time(task, best_set)
        max_move_time = max([count_move_time(tug.pos, task.start) for tug in best_set])
        task.delay_time = max(timedelta(0), arrival_time-task.start_time)
        task.start_time = task.start_time + task.delay_time

        if task.id < 0: # temp need task
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


