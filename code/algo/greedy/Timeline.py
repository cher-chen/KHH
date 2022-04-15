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
from itertools import combinations

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
        # self.company = tug.company
        

    @property
    def type(self):
        return self.tug.type

    @property
    def hp(self):
        return self.tug.hp

    @property
    def tug_id(self):
        return self.tug.tug_id


def candSet(tsk, tgs, match):
    # 產生所有的候選組合
    requires = tsk.req_types
    cands = []
    if match == 'over':
        for i in range(len(requires)):
            for tg in tgs:
                if tg in cands:
                    continue
                if tg.type >= requires[i]:
                    cands.append(tg)
    elif match == 'every':
        for tg in tgs:
            cands.append(tg)

    cands_comb = combinations(cands, len(requires))   

    return cands_comb

def elongate(tsk, tg_set):
    # for each tug in tg_set, for each of its job, elongate its starting and ending times 
    # according to its location and the new job tsk's location
    original_lst = []
    
    if len(tg_set) == 1:
        for i in range(len(tg_set[0].jobs)):
            s = tg_set[0].jobs[i][0] - count_move_time(get_pier_latlng(tsk.to), tg_set[0].jobs[i][2])
            e = tg_set[0].jobs[i][1] + count_move_time(get_pier_latlng(tg_set[0].jobs[i][3]), tsk.start)
            original_lst.append([s,e])
    else:    
        for i in tg_set:
            original_lst.append([]) 
        for i in range(len(tg_set)):
            for j in range(len(tg_set[i].jobs)):
                original_lst[i].append(tg_set[i].jobs[j][0] - count_move_time(get_pier_latlng(tsk.to), tg_set[i].jobs[j][2]))
                original_lst[i].append(tg_set[i].jobs[j][1] + count_move_time(get_pier_latlng(tg_set[i].jobs[j][3]), tsk.start))

    return original_lst

def mergeTimeline(tsk, tg_set):

    elong_lst = elongate(tsk, tg_set)
    final_lst = []
    for tg_times in elong_lst:
        for i in range(len(tg_times) // 2):
            final_lst.append([tg_times[2 * i], tg_times[2 * i + 1]])

    final_lst.sort(key=lambda x: x[0])
    if len(final_lst)==0:
        merged = []
    else:
        merged = [final_lst[0]]
    for current in final_lst:
        previous = merged[-1]
        if current[0] <= previous[1]:
            previous[1] = max(previous[1], current[1])
        else:
            merged.append(current)

    return merged


def cal_delay(tsk, tg_set):
    # for two or three tug set
    work_time = predict_worktime(tsk, tg_set)
    next_available_time = max([tg.next_available_time for tg in tg_set])
    if len(tg_set)==1:
        merged = elongate(tsk, tg_set)
        # print('mergelist:',merged)
    else:
        merged = mergeTimeline(tsk, tg_set) 
    # merged 存的是合併後的已加上移動時間的工作時間軸e.g.[[2, 6], [12, 18], [22, 30]]兩兩一組
    s_time = tsk.start_time
    e_time = tsk.start_time+work_time
    delaytime = timedelta(seconds=0)
    if len(merged) == 0:
        delaytime = timedelta(seconds=0)
        return delaytime
    else:
        for i in range(len(merged)):
            if i == 0:
                prev = next_available_time
            else:
                prev = merged[i-1][1]

            if s_time > prev:

                if e_time < merged[i][0]: # can insert
                    delaytime = timedelta(seconds=0)
                    return delaytime
                else:
                    for j in range(i+1, len(merged)):
                        if work_time <= (merged[j][0] - merged[j-1][1]): # can delay insert
                            delaytime = merged[j-1][1] - s_time
                            return delaytime

                    delaytime = merged[len(merged)-1][1] - s_time         
    return delaytime


def insertjob(nt, tg, jobs):
    # update jobs list of tug
    mt_f = timedelta(seconds=0)
    mt_b = timedelta(seconds=0)
    if len(jobs)==0:
        jobs.insert(0, nt)
        return jobs, True
    else:
        for i in range(len(jobs)):
            if i==0:
                prev = tg.next_available_time
                mt_f = count_move_time(tg.pos, nt[2])
                mt_b = count_move_time(get_pier_latlng(nt[3]), jobs[i][2])
                nt[0] = nt[0] - mt_f
                nt[1] = nt[1] + mt_b
            else:
                prev = jobs[i-1][1]
                mt_f = count_move_time(get_pier_latlng(jobs[i-1][3]), nt[2]) 
                mt_b = count_move_time(get_pier_latlng(nt[3]), jobs[i][2])
                nt[0] = nt[0] - mt_f
                nt[1] = nt[1] + mt_b

            if nt[1] < jobs[i][0] and nt[0] > prev: 
                nt[0] = nt[0] + mt_f
                nt[1] = nt[1] - mt_b
                jobs.insert(i, nt)
                return jobs, True

            else:
                nt[0] = nt[0] + mt_f
                nt[1] = nt[1] - mt_b
                
        if nt[0] > jobs[len(jobs) - 1][1]:
            jobs.append(nt)
            return jobs, True

    return jobs, False



def gogo_dispatch(tsks, tgs, time):
    """
    Args:
        tasks ([Task]): a list which stores the tasks to be planned
        tugs ([Tug]): a list of tugs avaiable 

    Returns:
        [[Tug]]: a list of lists of tugs in the same order as the given tasks
        [datetime]: a list of times at which the tasks actually start
    """
    print('TASK:',[task.id for task in tsks])    
    tasks = copy.deepcopy(tsks)
    tugs = [GTug(tg) for tg in tgs]
    # tugs = copy.deepcopy(tugs)
    tugs.sort(key = lambda x: x.type)
    tasks.sort(key = lambda x: x.start_time)
    print('TASK_order:',[task.id for task in tasks])
    stderr.write("Dispatching {} tasks with Gogo ...\n".format(len(tasks)))
    # 將task分成拖船需求二以上跟拖船需求一
    tasks_priority = []
    tasks_ones = []
    tasks_tempNeed = []
    for task in tasks:
        if task.id < 0: # temp need
            tasks_tempNeed.append(task)
        elif len(task.req_types) >= 2:
            tasks_priority.append(task)
        else:
            tasks_ones.append(task)

    # 處理 temp need
    for task in tasks_tempNeed:
        stderr.write("Dispatching TEMP NEED task {} \n".format(task.id))
        print('requires:',task.req_types)
        best_set = []
        delayList = []
        for tug in tugs:
            if tug not in task.ori_task.tugs and tug.type >= task.req_types[0]: #已經排給他的tug
                delaytime = cal_delay(task,[tug])
                if delaytime == timedelta(seconds=0):
                    best_set.append(tug)
                    task.delay_time = delaytime
                    break
                delayList.append([tug, delaytime])
            if len(delayList)!=0 and len(best_set)==0:
                opt = min(delayList, key=lambda x: x[1])
                best_set.append(opt[0])
                task.delay_time = opt[1]
        print('>>> best_set1:', [best.id for best in best_set])
        # 如果往上沒有符合型號的拖船
        if len(best_set) == 0: 
            # 往下派拖船型號
            delayList = []
            for tug in tugs:
                if tug not in task.ori_task.tugs and tug.type < task.req_types[0]:
                    delaytime = cal_delay(task, [tug])
                    if delaytime == timedelta(seconds=0):
                        best_set.append(tug)
                        task.delay_time = delaytime
                        break
                    delayList.append([tug, delaytime])
            if len(delayList)!=0 and len(best_set)==0:
                opt = min(delayList, key = lambda x: x[1])
                best_set.append(opt[0])
                task.delay_time = opt[1]
            print('>>> best_set2:', [best.id for best in best_set])


        # update jobs list of best set
        task.start_time = task.start_time+max(timedelta(0),best_set[0].next_available_time-task.start_time)+count_move_time(best_set[0].pos, task.start)
        nt = [task.start_time, task.start_time+predict_worktime(task, best_set), task.start, task.to]
        check = False
        for tug in best_set:
            tug.jobs, check = insertjob(nt, tug, tug.jobs)
            for i in range(len(tugs)):
                if tugs[i].id == tug.id:
                    tugs[i].jobs = tug.jobs

        if check==True:
            print('good insert')
            for t in tasks:
                if t.id == task.id:
                    print('tid:',t.id,'///',task.id)
                    t.tugs = [best.tug for best in best_set]
                    t.start_time = task.start_time
        else: 
            print('!!!!!error insert')


    '''--------處理拖船需求二以上---------'''
    for task in tasks_priority:
        stderr.write("Dispatching task {} \n".format(task.id))
        best_set = []
        delayList = []
        cands = candSet(task, tugs, 'over')
        for cand in list(cands):
            delaytime = cal_delay(task, list(cand))
            if delaytime == timedelta(seconds=0):
                best_set.extend(list(cand))
                task.delay_time = delaytime
                break
            delayList.append([list(cand), delaytime])
        
        if len(delayList)!=0 and len(best_set)==0:
            opt = min(delayList, key = lambda x: x[1])
            best_set.extend(opt[0])
            task.delay_time = opt[1]
        print('>>> best_set3:',[best.id for best in best_set])

        # 往上沒有符合型號的拖船，傳入的拖船型號沒有最高型號'type 0'
        if len(best_set) == 0:
            # 往下派拖船型號
            delayList = []
            cands = candSet(task, tugs, 'every')
            for cand in list(cands):
                delaytime = cal_delay(task, list(cand))
                if delaytime == timedelta(seconds=0):
                    best_set.extend(list(cand))
                    task.delay_time = delaytime
                    break
                delayList.append([list(cand), delaytime])
            
            if len(delayList)!=0 and len(best_set)==0:
                opt = min(delayList, key = lambda x: x[1])
                best_set.append(opt[0])
                task.delay_time = opt[1]
            print('>>> best_set4:', [best.id for best in best_set])

        # update jobs list of best set
        task.start_time = task.start_time + task.delay_time
        nt = [task.start_time, task.start_time+predict_worktime(task, best_set), task.start, task.to]
        check = False
        for tug in best_set:
            tug.jobs, check = insertjob(nt, tug, tug.jobs)
            for i in range(len(tugs)):
                if tugs[i].id == tug.id:
                    tugs[i].jobs = tug.jobs

        if check==True:
            print('good insert')
            for t in tasks:
                if t.id == task.id:
                    t.tugs = [best.tug for best in best_set]
                    t.start_time = task.start_time
        else: 
            print('!!!!!error insert')

    '''----------處理拖船需求一----------'''
    for task in tasks_ones:
        stderr.write("Dispatching task {} \n".format(task.id))
        best_set = []
        delayList = []
        for tug in tugs:
            # find tug with smallest delay
            if tug.type >= task.req_types[0]:
                delaytime = cal_delay(task, [tug])
                if delaytime == timedelta(seconds=0):
                    best_set.append(tug)
                    task.delay_time = delaytime
                    break
                delayList.append([tug, delaytime])
        
        if len(delayList)!=0 and len(best_set)==0:
            opt = min(delayList, key = lambda x: x[1])
            best_set.append(opt[0])
            task.delay_time = opt[1]
        print('>>> best_set5:', [best.id for best in best_set])

        # 往上沒有符合型號的拖船，傳入的拖船型號沒有最高型號'type 0'
        if len(best_set)==0:
            # 往下派拖船型號
            delayList = []
            for tug in tugs:
                if tug.type < task.req_types[0]:
                    delaytime = cal_delay(task, [tug])
                    if delaytime == timedelta(seconds=0):
                        best_set.append(tug)
                        task.delay_time = delaytime
                        break
                    delayList.append([tug, delaytime])

            if len(delayList)!=0 and len(best_set)==0:
                opt = min(delayList, key = lambda x: x[1])
                best_set.append(opt[0])
                task.delay_time = opt[1]
            print('>>> best_set6:', [best.id for best in best_set])

        
        # update jobs list of best set
        task.start_time = task.start_time + task.delay_time
        nt = [task.start_time, task.start_time+predict_worktime(task, best_set), task.start, task.to]
        check = False
        for tug in best_set:
            tug.jobs, check = insertjob(nt, tug, tug.jobs)
            for i in range(len(tugs)):
                if tugs[i].id == tug.id:
                    tugs[i].jobs = tug.jobs

        if check==True:
            print('good insert')
            for t in tasks:
                if t.id == task.id:
                    t.tugs = [best.tug for best in best_set]
                    t.start_time = task.start_time
        else: 
            print('!!!!!error insert')


    print('outcome:\n',[(task.id,task.tugs) for task in tasks])
    return [task.tugs for task in tasks], [task.start_time for task in tasks]
