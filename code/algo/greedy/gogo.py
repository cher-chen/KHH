from sys import stderr
from datetime import timedelta
from algo.greedy.helper import tug_to_charge_type
from algo.greedy.helper import max_arrival_time, count_profit
from algo.model import TaskState, TugState, ShipState, ChargeTypeList, Tug, Task
from algo.settings import PENALTY, WAITING_TIME, SYSTEM_TIME
from algo.port import get_pier_latlng
from algo.predict_worktime import predict_worktime
from algo.utils.utility import count_move_time
import copy

class GTug():

    def __init__(self, tug: Tug):
        self.tug = tug
        self.id = tug.tug_id
        self.next_available_time = tug.next_available_time
        self.pos = tug.pos
        self.jobs = []
        self.state = tug.state
        self.ts = tug.ts
        self.tasks = tug.tasks

    @property
    def type(self):
        return self.tug.type

    @property
    def hp(self):
        return self.tug.hp

    @property
    def tug_id(self):
        return self.tug.tug_id

class GTask():

    def __init__(self, task: Task):
        self.task = task
        self.id = task.id
        self.start = task.start
        self.to = task.to
        self.ship = task.ship
        self.ship_state = task.ship_state
        self.side = task.side
        self.task_state = task.task_state
        self.req_types = task.req_types
        self.tug_available = []
        self.start_time = task.start_time
        self.tug_cnt = task.tug_cnt
        self.tug_match = []

def onlyone_tug(tasks):
    for task in tasks:
        if len(task.tug_available) == 1:
            return True
        
def insertjob(tg, nt, jobs):
    temp_move_time = 0
    temp_move_time2 = 0
    if len(jobs)==0:
        temp_move_time = count_move_time(tg.pos, nt[2])
        # nt[0] = nt[0] - temp_move_time
        jobs.insert(0, nt)
        return jobs, True
    else:
        for i in range(len(jobs)):
            if i==0:
                prev = tg.next_available_time
                temp_move_time = count_move_time(tg.pos, nt[2])
                temp_move_time2 = count_move_time(get_pier_latlng(nt[3]), jobs[i][2])
                nt[0] = nt[0] - temp_move_time
                nt[1] = nt[1] + temp_move_time2
            else:
                prev=jobs[i-1][1]
                temp_move_time = count_move_time(get_pier_latlng(jobs[i-1][3]), nt[2]) 
                temp_move_time2 = count_move_time(get_pier_latlng(nt[3]), jobs[i][2])
                nt[0] = nt[0] - temp_move_time
                nt[1] = nt[1] + temp_move_time2

            if nt[1] < jobs[i][0] and nt[0] > prev: 
                nt[0] = nt[0] + temp_move_time
                nt[1] = nt[1] - temp_move_time2
                jobs.insert(i, nt)
                return jobs, True

            else:
                nt[0] = nt[0] + temp_move_time
                nt[1] = nt[1] - temp_move_time2
                continue

    return jobs, False

def insert_to_last(tgs, nt, task):

    min_delay_time = timedelta(9999)
    for i in task.req_types:
        for tg in tgs:
            if tg.type >= i:
                last = len(tg.jobs)-1
                temp_move_time = count_move_time(get_pier_latlng(tg.jobs[last][3]), nt[2])
                new_start_time = tg.jobs[last][1] + temp_move_time

                delay_time = new_start_time - nt[0] 
                if delay_time < min_delay_time:
                    min_delay_time = delay_time
                    opt_tg = tg
                    opt_new_start_time = new_start_time

    nt[0] = opt_new_start_time
    nt[1] = nt[1] + min_delay_time
    opt_tg.jobs.insert(len(opt_tg.jobs), nt)
    

    return opt_tg, min_delay_time
        


def gogo_dispatch(tsks, tgs, time):
    """
    Args:
        tasks ([Task]): a list which stores the tasks to be planned
        tugs ([Tug]): a list of tugs avaiable 

    Returns:
        [[Tug]]: a list of lists of tugs in the same order as the given tasks
        [datetime]: a list of times at which the tasks actually start
    """
    
    tasks = [GTask(tsk) for tsk in tsks]
    tugs = [GTug(tg) for tg in tgs]
    # tugs = copy.deepcopy(tugs)
    tugs.sort(key = lambda x: x.type)
    tasks.sort(key = lambda x: x.start_time)
    
    stderr.write("Dispatching {} tasks with Gogo ...\n".format(len(tasks)))

    # 優先處理拖船需求數2以上
    tasks_priority = []
    tasks_plan = []
    for task in tasks:
        if task.tug_cnt >= 2:
            tasks_priority.append(task)
        else:
            tasks_plan.append(task)
    # print([t.id for t in tasks_priority])
    # print([t.id for t in tasks_plan])

    for task in tasks_priority:
        best_set = []
        for i in task.req_types:
            check = False   
            for tug in tugs:
                if tug.type >= i: 
                    work_time = predict_worktime(task, [tug])
                    nt = [task.start_time, task.start_time+work_time, task.start, task.to]
                    tug.jobs, check = insertjob(tug, nt, tug.jobs)
                    if check == True:
                        # print("Dispatching task {} ...\n".format(task.id), file=stderr)
                        best_set.append(tug)
                        # print('Task id:', task.id,' best_set:', best_set)
                        break

            if check == False:
                # print('Dispatch to the end')
                opt_tug, delay_time = insert_to_last(tugs, nt, task)
                # print('delay time:', delay_time)
                # print(task.start_time)
                task.start_time = task.start_time + delay_time
                # print(task.start_time)
                for tug in tugs:
                    if tug.id == opt_tug.id:
                        tug = opt_tug
                        best_set.append(opt_tug)
                        
        # 更新tasks裡的task: 拖船分配, 開始時間更新
        for t in range(len(tasks)): 
            if tasks[t].id == task.id:
                tasks[t].tug_match = [best for best in best_set]
                tasks[t].start_time = task.start_time
                print('st:',task.task.start_time)
                print('st2:',task.start_time)
   
    # 分配其他task: 所需拖船數為1
    for task in tasks_plan:
        best_set = []
        for i in task.req_types:
            check = False   
            for tug in tugs:
                if tug.type >= i: 
                    work_time = predict_worktime(task, [tug])
                    nt = [task.start_time, task.start_time+work_time, task.start, task.to]
                    tug.jobs, check = insertjob(tug, nt, tug.jobs)
                    if check == True:
                        # print("Dispatching task {} ...\n".format(task.id), file=stderr)
                        best_set.append(tug)
                        # print('Task id:', task.id,' best_set:', best_set)
                        break

            if check == False:
                # print('Dispatch to the end')
                opt_tug, delay_time = insert_to_last(tugs, nt, task)
                # print('delay time:', delay_time)
                # print(task.start_time)
                task.start_time = task.start_time + delay_time
                # print(task.start_time)
                for tug in tugs:
                    if tug.id == opt_tug.id:
                        tug = opt_tug
                        best_set.append(opt_tug)
                        
        # 更新tasks裡的task: 拖船分配, 開始時間更新
        for t in range(len(tasks)): 
            if tasks[t].id == task.id:
                tasks[t].tug_match = [best for best in best_set]
                tasks[t].start_time = task.start_time
                print('st:',task.task.start_time)
                print('st2:',task.start_time)


    # for tug in tugs:
    #     print('id:', tug.tug_id,'jobs:', tug.jobs)
    for task in tasks:
        print(task.id, ":", task.start_time)

    return [task.tug_match for task in tasks], [task.start_time for task in tasks]
