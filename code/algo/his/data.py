"""Process history data"""

import os
import pandas as pd
import numpy as np
from sys import stderr
from datetime import timedelta
from random import random, sample
from algo.model import Ship, Task, Side, ShipState, TaskState, Tug, ChargeType, TaskPriority
from algo.utils.utility import get_pier_latlng
from algo.settings import SYSTEM_TIME, TUG_STARTING_PLACE


DIR = os.path.dirname(__file__)
FILE = os.path.join(DIR, "2017.pkl")
print("Reading {}\n".format(FILE))
df = pd.DataFrame(pd.read_pickle(FILE))


def tug_no_to_hp(tug_no):
    dict = {143: 1800,
            145: 1800,
            151: 2400,
            152: 2400,
            153: 2400,
            155: 2400,
            112: 2400,
            241: 2400,
            245: 2400,
            321: 3200,
            322: 3200,
            101: 3200,
            302: 3200,
            104: 3200,
            106: 3200,
            108: 3200,
            109: 3200,
            303: 3300,
            306: 3400,
            308: 3500,
            301: 3600,
            161: 4000,
            162: 4000,
            163: 4200,
            165: 4200,
            401: 4400,
            451: 4500,
            171: 5200,
            172: 5200,
            181: 6400,
            182: 6400
            }
    return dict[tug_no]


def hp_to_charge_type(hp):
    if hp <= 1800:
        return ChargeType.TYPE_117
    elif hp <= 2400:
        return ChargeType.TYPE_118
    elif hp <= 3200:
        return ChargeType.TYPE_119
    elif hp <= 4000:
        return ChargeType.TYPE_120
    else:
        return ChargeType.TYPE_0


def find_side(v):
    res = [member for _, member in Side.__members__.items() if member.value == v]
    return res[0] if len(res) > 0 else None


def find_state(v):
    res = [member for _, member in ShipState.__members__.items()
           if member.value == v]
    return res[0] if len(res) > 0 else None


def tug_last_info(df, row, tug_no):
    last_pier = 0  
    for i in range(row-1, -1, -1):
        sh = df.iloc[i, :]
        if sh.tug1_no == tug_no or sh.tug2_no == tug_no or sh.tug3_no == tug_no:
            if sh.sailing_status == 'I':
                last_pier = sh.place2
            elif sh.sailing_status == 'O':
                last_pier = int(sh.port) + 9000
            elif sh.sailing_status == 'T':
                last_pier = sh.place2
            last_time = sh.max_end_time
            return get_pier_latlng(last_pier), last_time

    # no last place in history data
    return get_pier_latlng(TUG_STARTING_PLACE), SYSTEM_TIME

def clip_tugs_num(tug_list, n_tugs=8):
    tug_type_list = np.array([ tug.type for tug in tug_list])
    tug_type_total = np.unique(tug_type_list) 
    cnt_type_list = np.array([ list(tug_type_list).count(i) for i in tug_type_total])
    remain_list = np.array([1 if cnt >= 1 else 0 for cnt in cnt_type_list])
    choose_index = np.array([])

    ## select at least one tug for each type
    for cnt, i in enumerate(remain_list) :
        total_list = (np.where(tug_type_list == tug_type_total[cnt]))[0]
        idx = np.random.choice(total_list, i)
        choose_index =  np.append(choose_index,idx[0])
    
    ## random select remain tugs
    idx = list(set(range(len(tug_list))) -  set(choose_index))
    idx = np.random.choice(idx, n_tugs-len(choose_index)) 
    choose_index = np.append(choose_index, idx)

    ## return the select tugs by index
    selected_tugs = []
    for cnt, tug in enumerate(tug_list):
        if cnt in choose_index:
            selected_tugs.append(tug)

    return selected_tugs

def get_data(row_start, row_end, from_hist=False):

    cnt = 0
    tid_list = set()
    history_tugs = []
    history_tasks = []
    history_ships = []

    def get_tug_instance(tug_id):
        return [tug for tug in history_tugs if tug.tug_id == tug_id][0]

    for row in (range(row_start, row_end+1)):
        sh = df.iloc[row, :]
        if sh.tug_cnt > 2:
            continue
        if sh.sailing_status == 'I':
            ship = Ship(ship_id=int(sh.ship_no),
                        cur_pos=(0, 0),
                        weight=sh.total_weight)  # temp place
            task = Task(i=cnt+1,
                        ship=ship,
                        tug_cnt=sh.tug_cnt,
                        ship_state=ShipState.IN,
                        start_time=sh.start_time,
                        start=int(sh.port) + 9000,
                        dest=int(sh.place2),
                        side=find_side(sh.park),
                        priority=TaskPriority.URGENT,
                        wind_lev=sh.wind)

        elif sh.sailing_status == 'O':
            ship = Ship(ship_id=int(sh.ship_no),
                        cur_pos=get_pier_latlng(sh.place2),
                        weight=sh.total_weight)
            task = Task(i=cnt+1,
                        ship=ship,
                        tug_cnt=sh.tug_cnt,
                        ship_state=ShipState.OUT,
                        start_time=sh.start_time,
                        start=int(sh.place2),
                        dest=int(sh.port) + 9000,
                        side=find_side(sh.park),
                        wind_lev=sh.wind)

        elif sh.sailing_status == 'T':
            ship = Ship(ship_id=int(sh.ship_no),
                        cur_pos=get_pier_latlng(sh.place1),
                        weight=sh.total_weight)
            task = Task(i=cnt+1,
                        ship=ship,
                        tug_cnt=sh.tug_cnt,
                        ship_state=ShipState.TRANSFER,
                        start_time=sh.start_time,
                        start=int(sh.place1),
                        dest=int(sh.place2),
                        side=find_side(sh.park),
                        wind_lev=sh.wind)

        history_ships.append(ship)
        history_tasks.append(task)

        cnt += 1
        
        for i in range(15, 18):
            if pd.isnull(sh[i]):
                break
            elif sh[i] not in tid_list:
                tug_no = int(sh[i])
                tid_list.add(tug_no)
                hp = tug_no_to_hp(tug_no)
                place, time = tug_last_info(df, row, tug_no)
                new_tug = Tug(tug_no, place, hp_to_charge_type(hp), hp, time)
                history_tugs.append(new_tug)
                if from_hist:
                    task.tugs.append(new_tug)
            elif from_hist:
                task.tugs.append(get_tug_instance(sh[i]))
        
        if from_hist:
            task.task_state = TaskState.PROCESSED
            task.start_time_real = sh.start_time + timedelta(minutes=sh.pilot_wait_time.item())
            task.work_time = timedelta(minutes=sh.mean_work_time.item())

    num_tugs = 10
    if len(history_tugs) > num_tugs:
        history_tugs = clip_tugs_num(history_tugs, num_tugs)

    # print(len(history_tugs))
    history_tasks.sort(key=lambda task: task.start_time)
    history_tugs.sort(key=lambda tug: tug.type)
    return history_tasks, history_tugs