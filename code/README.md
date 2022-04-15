# Estimation System of Dispatching Algorithm

This is a system estimating tug-dispatching algorithm by event simulation. The implemantation details are all in module _algo_. The following is the introduction of classes necessary for algorithms, and some useful functions providing additional information, such as oil price.

## Environment

The main module was developed in Mac OS 10.14.3 with python 3.7.0. Other packages with versions are shown in requirement.txt. Please consider creating and developing in a virtual environment to easily maintain versions of modules. Then all modules can be installed by

```bash
pip install -r requirements.txt
```

Then to build the extension module written in C. Use

```bash
make
```

## Algorithm Development

The basic idea of a dispatching algorithm is to assign tugs to tasks based on tasks' starting time, working time, starting piers and ending piers. It should be implemented as a function taking a python list of tasks and a list of tugs as arguments, and returning a list of lists of dispatched tugs and a list of starting time of tasks in the same order as the given tasks. Please also take a look at an example algorithm `cool_dispatch` in _algo/greedy/cool.py_ for input and output format; and do not directly modify any attributes of the given tasks. Other attributes about classes are covered in the paragraph _Model_ below.

## Estimation

After finishing an algorithm, please take a look at _example.py_, a simple demo showing how to estimate an algorithm with the system.

We implemented two ways to estimate algorithms:

1. Estimate one algorithm

    ```python
    est.run(my_dispatch)
    ```

    The return object is a python dictionary which contains keys listed below. Please access them as, for example, `result["tasks"]`.

    * `tasks`: a list of tasks read from history data used in simulation
    * `tugs`: a list of tugs read from history data for algorithms to dispatch
    * `moving_time`: the sum of times taken by tugs moving from current positions to the starting places of tasks
    * `moving_cost`: the sum of oil cost caused by tugs moving from current positions to the starting places of tasks
    * `waiting_time`: the sum of pilots' waiting times
    * `waiting_cost`: the sum of cost calculated with waiting time and _penalty_ defined in _algo/settings.py_
    * `revenue`: the sum of revenue of tasks
    * `profit`: the difference between the total revenue and the sum of waiting cost and moving cost

    There are also `print_result` and `draw` to show the dispatching result. In addition, you could use `set_range(start: int, end: int)` to set the range of rows in _algo/his/2017.xlsx_ to read for simulation, or use `pick_day(day: str)` to pick the day with the most or least tasks.

2. Calculate historical result

    ```python
    est.run_hist()
    ```

    Read historical result made by dispatcher. Return type is the same as `run()`

3. Estimate multiple algorithms

    ```python
    est.multi_run([my_dispatch_1, my_dispatch_2,...], sample_size, benchmark, verbose)
    ```

    The return object is a panda DataFrame of p-value, which is the comparing results between different algorithms.

### Tasks

To respectively estimate the results of tasks, there are also some member variables available in tasks. Please access them as, for example, `task.revenue`.

* `task.req_types`: the required types of tugs
* `task.tugs`: the tugs which served the task
* `task.events`: a list of events happened to the task
* `task.tugs_start_time`: a list of timestamps when the tugs of the task started moving
* `task.start_time_real`: the timestamp when the task actually started
* `task.work_time`: the predicted working time
* `task.extra_wait`: the extra waiting time due to temp need (0 if no temp need event)
* `task.tmp_need_time`: the timestamp when temp need happens (None if no temp need)
* `task.moving_cost`, `task.moving_time`, `task.waiting_cost` and `task.waiting_time` have also been recorded for each task.

### Tugs

* `tug.tasks`: a python deque object recording tasks served by the tug
* `tug.ts`: a python deque object recording timestamps when the tug started moving, started working and completed for all tasks it served

### Parameters of Events in Simulation

We estimate algorithms by generating lots of events. By changing the parameters, you can meet different results. All parameters can be accessed in _algo/simu_params.py_

#### Tug-changing-related parameters

* `ADD_TUG_PROB`: the propability of adding tug per task before dispatching
* `ADD_POWER_PROB`: the propability of changing tug to huger size per task before dispatching

* `TEMP_NEED_PROB_IN` , `TEMP_NEED_PROB_OUT`, `TEMP_NEED_PROB_TR` : the probability
 for task to temporarily require additional tugs when it is going to enter, leave the habor and transfer between ports.

#### Delay-related parameters

* `START_DELAY_PROB_IN`,`START_DELAY_PROB_OUT`, `START_DELAY_PROB_TR`: the delay probability
 for task when it is going to enter, leave the habor and transfer between ports.

* `NOTICE_BEFOREHAND`: the latest time to know whether the task start time will changed.

* `MAX_START_DELAY_IN`,`MAX_START_DELAY_OUT`,`MAX_START_DELAY_TR`: the max start time delay cased by other reason excluding tug delay.

* `CANCEL_PROB_IN`,`CANCEL_PROB_OUT`,`CANCEL_PROB_TR`: the probability of canceling the task.

## Model

Implementations and documentations of predifined classes, such as Task, Tug and Ship, can be found in _algo/model.py_
If you need other attributes for the predefined classes, please do inheritance or wrapping them in a new class. Example for wrapping can be found in _algo/greedy/cool.py_

### Example for Inheritance

```python
from algo.model import task
class MyTask(Task):
    def __init__({attributes defined based on your algorithm}):
        super().__init___(i, ship, tug_cnt, ship_state, start_time, start, dest, side, priority):
        # other attributes
```

## Utility Funtions

Functions in _algo/utils/utility.py_ providing fixed information which may help in dispathcing algorithms. Detailed documentation can be found in the implementation of each function.

## Distance and Coordinates

There are two more functions in module _algo/port.py_ provides distance and coordinates.

* `get_pierToPier_dist(port: int, pier: int) -> float` offers Euclidean distance between piers. Notice that port 1 and port 2 are represented as pier 9001 and 9002.
* `get_pier_latlng(pier: int) -> (float, float)` offers a python tuple of latitude and longitude of given piers or ports.

## Working time Prediction

Working time prediction can be easily done with a given task and a list of tugs. Please import the module from `algo.predict_worktime`

### Example

```python
working_time = predict_worktime(task, tugs)
```

## Remark

Here are three more important things you should know.

1. When a temp need event occurs, the required types are represented as a TmpTask object which inherits Task with its id being 0 - id of the original task, and the original task are stored in the attribute `ori_task`. When deciding the starting time of a TmpTask, please make sure the tugs you dispatch to serve the task moves after the temp need event occurs. The time when the event occurs can be found in the attribute `tmp_need_time` of `ori_task`.
2. Please also consider dispatch tugs according to the priority of tasks. The task with ships coming in the port and temp need event are often urgent and dangerous in reality, so waiting time of such tasks should be as short as possible.
3. The simulation system will call the dispatching algorithm with tasks sorted by their starting time and tugs as input when WorkTimeDelay, StartTimeDelay, ChangeTypes and TempNeed events happen. See _algo/event.py_ for more information about events.
4. For tasks with higher priority, such as ships coming in and temp needs, the waiting cost is muliplied by `URGENT_COST` defined in _algo/settings.py_, default 10.