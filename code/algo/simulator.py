import copy
import math
import numpy as np
from typing import List, Dict
from datetime import timedelta, datetime
from sys import stderr
from random import random, randint, choice
from collections import deque
from .model import Task, Tug, Ship, TmpTask, TaskState, ShipState, TugState, ChargeType
from .event import Event, ConfirmTask, ChangeTypes, StartWork, StartTimeDelay, Canceled
from .event import WorkTimeDelay, TempNeed, EndWork, Routine
from .simu_params import *
from .settings import WINDOW_SIZE, PENALTY, ExecState
from .utils.utility import count_move_time, get_pier_latlng, calculate_revenue


class Simulator:

    events: List[Event] = []
    change_events: List[ChangeTypes] = []
    start_events: List[StartWork] = []
    confirm_events: List[ConfirmTask] = []

    tmp_tasks: List[TmpTask] = []
    done_tmp_tasks: List[TmpTask] = []
    tasks = []

    result = {}

    def __init__(self, tasks: List[Task], tugs: List[Tug], verbose=True):
        self.all_tasks = tasks
        self.tasks_que = deque(sorted(tasks, key=lambda task: task.start_time))
        self.tugs = tugs
        self.system_time = self.tasks_que[0].start_time
        self.verbose = verbose
        
    def segment(self, time):
        new_tasks = []
        while self.tasks_que and self.tasks_que[0].start_time <= time + WINDOW_SIZE:
           new_tasks.append(self.tasks_que.popleft())
        if new_tasks:
            self.tasks.extend(new_tasks)
            self.gen_init_events(new_tasks)

    def run(self, method) -> Dict:
        """Simulator's main function, handle events and schedule the tugs
        """
        self.method = method
        while self.tasks_que:
            self.segment(self.tasks_que[0].start_time)
            self.schedule()
            self.events.sort(key=lambda event: (event.time, event.order))

            while self.events:
                event = self.events.pop(0)
                self.system_time = event.time
                self.segment(event.time)

                if type(event) is not Routine and event.task.task_state is TaskState.CANCELED:
                    continue

                if self.verbose:
                    print(event)
                handle_state = event.handle()

                # additional process according to event type
                if type(event) is ConfirmTask and type(event.task) is TmpTask:
                    event.task.ori_task.tugs.extend(event.task.tugs)
                    self.done_tmp_tasks.append(event.task)
                    self.tmp_tasks.remove(event.task)

                elif type(event) is ChangeTypes or type(event) is StartTimeDelay:
                    if handle_state is ExecState.PROBLEM:
                        confirm = next(eve for eve in event.task.events if type(eve) is ConfirmTask)
                        self.events.append(confirm)

                elif type(event) is StartWork:
                    self.insert_event(self.gen_work_delay_event(event.task))

                    need_event = self.gen_temp_need_event(event.task)
                    if need_event is not None:
                        self.insert_event(need_event)
                    
                    self.start_events.remove(event)

                elif type(event) is WorkTimeDelay:
                    self.insert_event(self.gen_end_event(event.task))

                elif type(event) is TempNeed:
                    if event.task.task_state is TaskState.PROCESSED:
                        continue
                    self.handle_tmp_task(event)
                
                elif type(event) is EndWork:
                    self.tasks.remove(event.task)

                # call dispatch algorithm
                if type(event) in [Routine, WorkTimeDelay, StartTimeDelay,
                    ChangeTypes, TempNeed, Canceled]:
                    self.schedule()

                # Check if gap between events is too large
                if any(task.task_state is TaskState.UNPROCESSED_UNASSIGNED \
                    for task in self.all_tasks):
                    i = 0
                    while i < len(self.events) and \
                        type(self.events[i]) in [ConfirmTask, StartWork, EndWork]:
                        i += 1
                    if i != 0 and (i == len(self.events) or \
                        self.events[i].time - event.time > timedelta(minutes=ROUTINE_DISPATCH)):
                        self.insert_event(Routine(None, event.time+timedelta(hours=1)))

                self.events.sort(key=lambda event: (event.time, event.order))

        self.collect_result()
        return self.result


    ## ------------ Methods dispatching tasks and assign tugs to tasks ------------

    def schedule(self):
        """Execute the dispatching algorithm
        """
        task_dp = [t for t in self.tasks if t.task_state == TaskState.UNPROCESSED_UNASSIGNED]
        task_dp.sort(key=lambda task: task.start_time)
        all_tasks = self.tmp_tasks + task_dp
        if all_tasks:
            if self.verbose:
                print("\n[Scheduling] Dispatch {} tasks with {}...".format(len(all_tasks), 
                    self.method.__name__), file=stderr)

            tug_sets, times = self.method(all_tasks, self.tugs, self.system_time)
            self.assign(all_tasks, tug_sets, times)
            
            # Update confirming and starting time
            self.update_tasks_time(all_tasks)

            # If a tug which is serving a task delayed by temp need,
            # its next available time will be updated in update_tmp_task
            # and the starting time of the undone tasks served by the tug
            # will also be delayed, so we need to redispatch
            if self.tmp_tasks: 
                changed = True
                while changed:
                    if self.verbose:
                        print("\n[Scheduling] Update tasks affected by delayed temp need...")
                    tug_sets, times = self.method(all_tasks, self.tugs, self.system_time)
                    ori_start_times = [task.start_time for task in all_tasks]
                    self.assign(all_tasks, tug_sets, times)
                    self.update_tasks_time(all_tasks)
                    for old_time, new_time in \
                        zip(ori_start_times, times):
                        if old_time != new_time:
                            changed = True
                            break
                    changed = False

            for event in self.confirm_events:
                event.time = event.task.last_tug_move
            for event in self.start_events:
                event.time = event.task.start_time_real

            if self.verbose:
                print("")

    def assign(self, tasks, tugss, times):
        """Assign tugs and generate new ComfirmTask if tugs change after comfirmation
        """
        for task, tugs, start_time in zip(tasks, tugss, times):
            if type(task) is TmpTask:
                for tug in task.tugs:
                    assert tug not in task.ori_task.tugs, \
                        "Tugs for TmpTask should be different from the original task's tugs"
            task.assign_tugs(tugs, start_time)

    
    ## ------------ Methods updating times of events and tasks ------------

    def update_tasks_time(self, tasks):
        """Rearrange ConfirmTask and StartWork according to new starting time
        """

        tasks.sort(key=lambda task: task.start_time_real)
        
        # Initial tugs with their current state
        poses = {}
        for tug in self.tugs:
            poses[tug.tug_id] = tug.pos

        # rearrange events so that ConfirmTask happens 
        # no later than the last tug starts moving
        for task in tasks:
            if not task.tugs:
                continue
            start_move_times = []
            for tug in task.tugs:
                start = task.start_time_real - count_move_time(poses[tug.tug_id], task.start)
                start_move_times.append(start)
                poses[tug.tug_id] = get_pier_latlng(task.to)
            task.last_tug_move = max(start_move_times)

            if task.id < 0:
                self.update_task_end_by_tmp_need(task.ori_task, task)


    ## ---------------- Methods dealing with temp tasks ----------------

    def handle_tmp_task(self, event):

        # Create a temporary task for the new requirement
        tmp_task = TmpTask(event.task, event.req_types, event.time)
        self.tmp_tasks.append(tmp_task)

        new_cf = ConfirmTask(tmp_task, event.time)
        self.insert_event(new_cf)
        self.confirm_events.append(new_cf)

    def update_task_end_by_tmp_need(self, task, tmp_task):
        """Modify the working time by the waiting time caused by the temp need tugs
        """
        extra_wait = tmp_task.start_time_real - tmp_task.start_time
        past_extra = task.extra_wait
        task.extra_wait = extra_wait
        task.work_time += extra_wait - past_extra
        for tug in task.tugs:
            tug.next_available_time += extra_wait - past_extra
        for eve in task.events:
            if type(eve) is EndWork:
                eve.time += extra_wait - past_extra
        
        tmp_task.work_time = task.start_time_real + task.work_time \
            - tmp_task.start_time_real


    ## ------ Methods generating events before the all tasks being processed ------

    def gen_init_events(self, tasks):
        ch, cf, st = self.gen_change_events(tasks), self.gen_confirm_events(tasks), \
            self.gen_start_events(tasks)
        self.change_events.extend(ch)
        self.confirm_events.extend(cf)
        self.start_events.extend(st)
        self.events.extend(ch+cf+self.gen_start_delay_events(tasks)+
            st+self.gen_canceled_events(tasks))
        self.events.sort(key=lambda event: event.time)

    def gen_confirm_events(self, tasks) -> List[ConfirmTask]:
        events = []
        for task in tasks:
            event = ConfirmTask(task, task.start_time)
            task.events.append(event)
            events.append(event)
        return events

    def gen_change_events(self, tasks) -> List[ChangeTypes]:
        events = []
        for task in tasks:
            time = task.start_time - timedelta(minutes=randint(10, 20))
            prob = random()
            TEMP_ADD_TUG_PROB = ADD_TUG_PROB_SEVERE if task.wind_lev >= 5 else ADD_TUG_PROB
            if prob <= ADD_POWER_PROB:  # replace with a more powerful tug, few cases
                if all([ttype is ChargeType.TYPE_0 for ttype in task.req_types]):
                    continue

                be_replaced = randint(0, len(task.req_types)-1)
                new_types = copy.copy(task.req_types)

                while new_types[be_replaced] is ChargeType.TYPE_0:
                    be_replaced = randint(0, len(task.req_types)-1)

                rpl_type = choice(list(ChargeType))
                while rpl_type <= new_types[be_replaced]:
                    rpl_type = choice(list(ChargeType))

                del new_types[be_replaced]
                new_types.append(rpl_type)
                new_types.sort(key=lambda ttype: ttype.value)
                event = ChangeTypes(task, time, new_types)
                task.events.append(event)
                events.append(event)

            elif prob <= ADD_POWER_PROB + TEMP_ADD_TUG_PROB:  # need more tugs
                add_type = ChargeType.TYPE_0
                new_types = copy.copy(task.req_types)

                # the additional required type is never over the existed maximum type
                while add_type > task.req_types[-1]:
                    add_type = choice(list(ChargeType))
                new_types.append(add_type)
                new_types.sort(key=lambda ttype: ttype.value)
                event = ChangeTypes(task, time, new_types)
                task.events.append(event)
                events.append(event)
        return events

    def gen_start_events(self, tasks) -> List[StartWork]:
        events = []
        for task in tasks:
            event = StartWork(task, task.start_time)
            task.events.append(event)
            events.append(event)
        return events

    def gen_start_delay_events(self, tasks) -> List[StartTimeDelay]:
        events = []
        for task in tasks:
            prob = 1
            delay = 0
            if task.ship_state == ShipState.IN:
                prob = START_DELAY_PROB_IN
                delay=randint(1, MAX_START_DELAY_IN)
            elif task.ship_state == ShipState.OUT:
                prob = START_DELAY_PROB_OUT
                delay=randint(1, MAX_START_DELAY_OUT)
            else:
                prob = START_DELAY_PROB_TR
                delay=randint(1, MAX_START_DELAY_TR)

            if random() <= prob:
                event = StartTimeDelay(
                    task,
                    task.start_time-timedelta(minutes=randint(0, NOTICE_BEFOREHAND)),
                    timedelta(minutes=delay))
                task.events.append(event)
                events.append(event)
        return events

    def gen_canceled_events(self, tasks) -> List[Canceled]:
        events = []
        for task in tasks:
            prob = 1
            if task.ship_state == ShipState.IN:
                prob = CANCEL_PROB_IN
            elif task.ship_state == ShipState.OUT:
                prob = CANCEL_PROB_OUT
            else:
                prob = CANCEL_PROB_TR
            
            if random() <= prob:
                event = Canceled(task,
                    task.start_time-timedelta(minutes=randint(0, NOTICE_BEFOREHAND)))
                task.events.append(event)
                events.append(event)
        return events


    ## ---------------- Methods generating a functional event ----------------

    def gen_work_delay_event(self, task: Task) -> WorkTimeDelay:
        work_time = math.floor(task.work_time.seconds / 60)-1
        last_for = randint(0, work_time) # the delay happens during operation

        # negative delay time cannot less than to terminate the task immediately 
        delay = max(self.gen_delay_time(task), timedelta(minutes=last_for-work_time))
        delay_event = WorkTimeDelay(
            task,
            task.start_time_real+timedelta(minutes=last_for),
            delay)
        return delay_event

    def gen_temp_need_event(self, task: Task) -> TempNeed:
        work_time = math.floor(task.work_time.seconds / 60)
        last_for = randint(1, work_time)

        prob = TEMP_NEED_PROB_IN
        if task.ship_state is ShipState.OUT:
            prob = TEMP_NEED_PROB_OUT
        elif task.ship_state is ShipState.TRANSFER:
            prob = TEMP_NEED_PROB_TR
        
        if random() <= prob:
            return TempNeed(task, task.start_time_real+timedelta(minutes=last_for),
                [choice(list(ChargeType))])

    def gen_end_event(self, task: Task) -> EndWork:
        return EndWork(task, task.start_time_real+task.work_time)

    
    ## ------------------------ Helper methods ------------------------

    def insert_event(self, event: Event):
        if event.task is not None:
            event.task.events.append(event)
        for i, eve in enumerate(self.events):
            if eve.time >= event.time:
                self.events.insert(i, event)
                return
        self.events.insert(len(self.events), event)

    def grade_result(self, req_types, tugs):
        if not tugs:
            return 0, 0, 0
        matched, over, under = 0, 0, 0
        for req_type, tug in zip(req_types, tugs):
            if req_type == tug.type:
                matched += 1
            elif req_type > tug.type:
                under += 1
            else:
                over += 1
        return matched/len(tugs), over/len(tugs), under/len(tugs)


    def collect_result(self):
        total_moving_cost = 0
        total_moving_time = timedelta(0)
        total_waiting_time = timedelta(0)
        total_revenue = 0
        mean_matched = 0
        mean_over = 0
        mean_under = 0

        for task in self.done_tmp_tasks:
            ori_task = task.ori_task
            
            # Update the original task
            ori_task.tugs_start_time.extend(task.tugs_start_time)
            ori_task.moving_time += task.moving_time
            ori_task.moving_cost += task.moving_cost
            
            # Calculate the task revenue
            profit_period = [ori_task.start_time_real + ori_task.work_time - start \
                for start in task.tugs_start_time]
            ori_task.revenue += calculate_revenue(profit_period, task.req_types, task.tugs)

        for task in self.all_tasks:
            if task.task_state is TaskState.CANCELED:
                task.start_time_real = task.start_time
            task.waiting_time += task.start_time_real - task.start_time
            task.waiting_cost = task.waiting_time.seconds / 60 * PENALTY * task.priority

            profit_period = [task.start_time_real + task.work_time - start \
            for start in task.tugs_start_time]
            task.revenue += calculate_revenue(profit_period[:task.tug_cnt], 
                task.req_types[:task.tug_cnt], task.tugs[:task.tug_cnt])
            task.profit = task.revenue - task.waiting_cost - task.moving_cost

            total_moving_cost += task.moving_cost
            total_moving_time += task.moving_time
            total_waiting_time += task.waiting_time
            total_revenue += task.revenue
            matched, over, under = self.grade_result(task.req_types, task.tugs)
            mean_matched += matched
            mean_over += over
            mean_under += under

        mean_matched /= len(self.all_tasks)
        mean_over /= len(self.all_tasks)
        mean_under /= len(self.all_tasks)
        
        self.result['tasks'] = self.all_tasks
        self.result['tugs'] = self.tugs
        self.result['moving_cost'] = total_moving_cost
        self.result['moving_time'] = total_moving_time
        self.result['waiting_time'] = total_waiting_time
        self.result['matched'] = mean_matched
        self.result['oversize'] = mean_over
        self.result['undersize'] = mean_under
        self.result['waiting_cost'] = total_waiting_time.seconds / 60 * PENALTY
        self.result['revenue'] = total_revenue
        self.result['profit'] = total_revenue-total_moving_cost-self.result['waiting_cost']

    def get_delay_prob(self, task):

        if task.ship_state == ShipState.IN:
            return ([0.08403361344537816,
                    0.4957983193277311,
                    0.2647058823529412,
                    0.13865546218487396,
                    0.01680672268907563,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0],)
 
        elif task.ship_state == ShipState.OUT:
            return ([0.0,
                    0.05263157894736842,
                    0.10047846889952153,
                    0.20095693779904306,
                    0.2727272727272727,
                    0.19138755980861244,
                    0.0430622009569378,
                    0.06698564593301436,
                    0.03349282296650718,
                    0.03827751196172249],)

        else:
            return ([0.2222222222222222,
                    0.48148148148148145,
                    0.18518518518518517,
                    0.1111111111111111,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0])


    def gen_delay_time(self, task):
        probs = self.get_delay_prob(task)
        ran_num = np.random.uniform(0.0, 1.0)

        prob_agg = probs[0]
        result = -0.9
        for prob in probs[1:]:
            if ran_num <= prob_agg:
                break
            prob_agg += prob
            result += 0.2

        return(timedelta(minutes= -1 * result * task.work_time.seconds/60))
    
