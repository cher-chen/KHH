"""Cool dispatch, a dispatching algorithm example
"""

from sys import stderr
from datetime import timedelta, datetime
from typing import List
from collections import deque
from algo.model import TaskState, Task, Tug, ChargeType
from algo.settings import PENALTY, WAITING_TIME
from algo.utils.utility import count_move_time, get_oil_price, count_move_dis, get_pier_latlng
from algo.predict_worktime import predict_worktime


class CoolTug():

    def __init__(self, tug: Tug):
        self.tug = tug
        self.next_available_time = tug.next_available_time
        self.pos = tug.pos

    @property
    def type(self):
        return self.tug.type

    @property
    def hp(self):
        return self.tug.hp


def cool_dispatch(tasks: List[Task], tugs: List[Tug], sys_time: datetime, verbose=False):
    """
    Args:
        tasks: tasks to be dispatched
        tugs: tugs currently available
        sys_time: current time in simulator

    Returns:
        [[Tug]]: a list of lists of tugs in the same order as the given tasks
        [datetime]: a list of times at which the tasks actually start
    """

    tugs = [CoolTug(tug) for tug in sorted(tugs, key=lambda t: t.type)]
    
    res = []
    times = []

    for task in tasks:
        if verbose:
            print("Dispathching task {} ...".format(task.id))

        # check if it's tmp need task
        tugs_que = deque([ct for ct in tugs if ct.tug not in task.ori_task.tugs]) \
            if task.id < 0 else deque(tugs)

        # Find require charge type and remove unqualified tugs from available tug set
        required_tugs_list = task.req_types
        while tugs_que and tugs_que[0].type < required_tugs_list[0]:
            tugs_que.popleft()

        my_waiting_time = WAITING_TIME
        best_set = []
        for req in required_tugs_list:
            candid_tugs = deque([])
            min_cost = 0
            elected_tug = None
            give_up = False
            req_type = req

            while not give_up:
                # First look up type-matched tugs
                while tugs_que and tugs_que[0].type < req_type:
                    tugs_que.popleft()

                while tugs_que and tugs_que[0].type == req_type:
                    tug = tugs_que.popleft()
                    candid_tugs.append(tug)
                    time_cost = (tug.next_available_time + count_move_time(tug.pos, task.start)
                                 - task.start_time_real)

                    if time_cost <= my_waiting_time:
                        cost = time_cost.seconds / 60 * PENALTY + get_oil_price(tug.hp) * \
                            count_move_dis(tug.pos, task.start)
                        if min_cost == 0:
                            min_cost = cost
                            elected_tug = tug
                        elif cost < min_cost:
                            min_cost = cost
                            elected_tug = tug
                
                if elected_tug:
                    best_set.append(elected_tug)
                    # Put other tugs back to tugs queue
                    while candid_tugs:
                        tug = candid_tugs.pop()
                        if tug is not elected_tug:
                            tugs_que.appendleft(tug)
                    break

                # No type-matched tugs available within the maximum waiting time
                elif req_type < ChargeType.TYPE_0:
                    req_type = ChargeType(req_type+1)

                elif my_waiting_time <= timedelta(hours=2.5):
                    my_waiting_time += timedelta(minutes=20)
                    while candid_tugs:
                        tug = candid_tugs.pop()
                        tugs_que.appendleft(tug)
                    req_type = req

                else:
                    give_up = True
                    if verbose:
                        print("> Give up!", file=stderr)
         
        if len(best_set) != len(required_tugs_list):
            if verbose:
                print("Task", task.task_id, "No good choices!")
            res.append([])
            times.append(None)
            continue
        
        choices = [best.tug for best in best_set]
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
        if verbose:
            print("> Tugs:", [tug.tug_id for tug in choices], start_time_real.strftime("%H:%M"))

    return res, times

