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

# def onlyone_tug(tasks):
#     for task in tasks:
#         if len(task.tug_available) == 1:
#             return True

def insertjob2(tgs, nt, task):
    min_mt = timedelta(minutes=9999)
    opt_i  = -1
    opt_tg = tgs[0]
    for tg in tgs:
        work_time = predict_worktime(task, [tg])
        nt[1] = nt[1] + work_time   
        if len(tg.jobs) == 0:
            temp_move_time = count_move_time(tg.pos, nt[2])
            if temp_move_time < min_mt:
                min_mt = temp_move_time    
                opt_tg = tg
                opt_i = 0
        else:
            for i in range(len(tg.jobs)):
                if i == 0:
                    prev = tg.next_available_time
                    temp_move_time = count_move_time(tg.pos, nt[2])
                    temp_move_time2 = count_move_time(get_pier_latlng(nt[3]), tg.jobs[i][2])
                    nt[0] = nt[0] - temp_move_time
                    nt[1] = nt[1] + temp_move_time2
                else:
                    prev = tg.jobs[i-1][1]
                    temp_move_time = count_move_time(get_pier_latlng(tg.jobs[i-1][3]), nt[2]) 
                    temp_move_time2 = count_move_time(get_pier_latlng(nt[3]), tg.jobs[i][2])
                    nt[0] = nt[0] - temp_move_time
                    nt[1] = nt[1] + temp_move_time2

                if nt[1] < tg.jobs[i][0] and nt[0] > prev: # able to insert
                    # ??????nt
                    nt[0] = nt[0] + temp_move_time 
                    nt[1] = nt[1] - temp_move_time2
                    if temp_move_time < min_mt:
                        min_mt = temp_move_time    
                        opt_tg = tg
                        opt_i = i    
                else: # ??????nt
                    nt[0] = nt[0] + temp_move_time
                    nt[1] = nt[1] - temp_move_time2

    if opt_i != -1:
        opt_tg.jobs.insert(opt_i, nt)
        return True, opt_tg
    else:
        return False, opt_tg


        
def insertjob(tg, nt, jobs):
    temp_move_time = 0
    temp_move_time2 = 0
    if len(jobs) == 0:
        temp_move_time = count_move_time(tg.pos, nt[2])
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
                prev = jobs[i-1][1]
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

def insert_to_last(tgs, nt):

    min_delay_time = timedelta(minutes=9999)
    for tg in tgs:
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
        


def gogo_dispatch(tasks, tugs, time):
    """
    Args:
        tasks ([Task]): a list which stores the tasks to be planned
        tugs ([Tug]): a list of tugs avaiable 

    Returns:
        [[Tug]]: a list of lists of tugs in the same order as the given tasks
        [datetime]: a list of times at which the tasks actually start
    """
    
    tasks = [GTask(task) for task in tasks]
    tugs = [GTug(tug) for tug in tugs]
    # tugs = copy.deepcopy(tugs)
    tugs.sort(key = lambda x: x.type)
    tasks.sort(key = lambda x: x.start_time)
    
    stderr.write("Dispatching {} tasks with Gogo ...\n".format(len(tasks)))


    # # ?????????task???????????????
    # for task in tasks:
    #     tug_available = []
    #     for req_type in task.req_types:
    #         for tug in list(tugs):
    #             if tug_to_charge_type([tug])[0] >= req_type:
    #                 tug_available.append(tug)
    #     tug_available.sort(key = lambda x: x.type)
    #     task.tug_available = copy.deepcopy(tug_available)

    # # ?????????????????????????????????????????????task
    # while onlyone_tug(tasks_plan):
    #     for task in tasks_plan:
    #         check == False
    #         if len(task.tug_available) == 1:
    #             disp_tug = task.tug_available[0]
    #             work_time = predict_worktime(task, disp_tug)
    #             nt = [task.start_time-timedelta(minutes=20), task.start_time+timedelta(minutes=work_time),task.start,task.to]
    #             disp_tug.jobs, check = insertjob(disp_tug, nt, disp_tug.jobs)
                
    #             if check == True:
    #                 print(disp_tug.jobs)
    #                 stderr.write("Dispathching task {} ...\n".format(task.id))
    #                 task_i.tug_match.append(disp_tug)
    #                 tasks_plan.remove(task)
    #                 continue

    # ???????????????????????????2??????
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
        check = False  
        for i in task.req_types:
            nt = [task.start_time, task.start_time, task.start, task.to]
            atugs = []
            for tug in tugs:
                if tug.type>=i:
                    atugs.append(tug)
            check, opt_tug = insertjob2(atugs, nt, task)
            if check == True:
                print("Dispatching task {} ...\n".format(task.id), file=stderr)
                for tug in tugs:
                    if tug.id == opt_tug.id:
                        tug = opt_tug
                        best_set.append(tug)
                # print('Task id:', task.id,' best_set:', best_set)

            if check == False:
                print('Dispatch to the end')
                opt_tug, delay_time = insert_to_last(tugs, nt)
                task.start_time = task.start_time + timedelta(delay_time)
                for tug in tugs:
                    if tug.id == opt_tug.id:
                        tug = opt_tug
                        best_set.append(tug)
                        
        # ??????tasks??????task: ????????????, ??????????????????
        for t in range(len(tasks)): 
            if tasks[t].id == task.id:
                tasks[t].tug_match = [best for best in best_set]
                tasks[t].start_time = task.start_time


   
    # ????????????task: ??????????????????1
    for task in tasks_plan:
        best_set = []
        check = False  
        for i in task.req_types:
            nt = [task.start_time, task.start_time, task.start, task.to]
            atugs = []
            for tug in tugs:
                if tug.type>=i:
                    atugs.append(tug)
            check, opt_tug = insertjob2(atugs, nt, task)
            if check == True:
                print("Dispatching task {} ...\n".format(task.id), file=stderr)
                for tug in tugs:
                    if tug.id == opt_tug.id:
                        tug = opt_tug
                        best_set.append(tug)
                # print('Task id:', task.id,' best_set:', best_set)

            if check == False:
                print('Dispatch to the end')
                opt_tug, delay_time = insert_to_last(tugs, nt)
                task.start_time = task.start_time + timedelta(delay_time)
                for tug in tugs:
                    if tug.id == opt_tug.id:
                        tug = opt_tug
                        best_set.append(tug)
                        
        # ??????tasks??????task: ????????????, ??????????????????
        for t in range(len(tasks)): 
            if tasks[t].id == task.id:
                tasks[t].tug_match = [best for best in best_set]
                tasks[t].start_time = task.start_time


    # for tug in tugs:
    #     print('id:', tug.tug_id,'jobs:', tug.jobs)
                 
                   
        
    

    return [task.tug_match for task in tasks], [task.start_time for task in tasks]