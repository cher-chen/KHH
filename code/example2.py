from typing import List
from datetime import datetime
from algo.estimator import Estimator
from algo.model import Task, Tug


def my_dispatch(tasks: List[Task], tugs: List[Tug], sys_time: datetime) -> List[List[Tug]]:
    """
    Args:
        tasks: tasks to be dispatched
        tugs: tugs currently available
        sys_time: current time in simulator

    Returns:
        a list of lists of tugs in the same order as the given tasks
        a list of expected starting time of the tasks

    Notes:
        Please implement your own dispatching algorithm with the given input and output format
        Avoid directly modifing attributes of tasks and tugs
    """

    # TODO: dispatch all tasks
    lists_of_tugs = [[]]
    start_times = []

    return lists_of_tugs, start_times


def estimate_my_algorithm():
    """
    The way to estimate your algorithm
    """
    from algo.greedy.cool import cool_dispatch
    from algo.greedy.send2 import my_dispatch
    from algo.greedy.Timeline import gogo_dispatch
    est = Estimator()
    est.pick_day('most')
    # est.set_range(140, 160)
    result = est.run(gogo_dispatch)
    # print(est.multi_run([my_dispatch, cool_dispatch], 30, verbose=True))

    # If detailed information of tasks is needed
    est.print_result(result, verbose=True)
    est.draw(result)
    
    # print("==== MOST====")
    # est.pick_day('most')
    # print("Task number:", est.row_end-est.row_start+1)
    # print("Row start:", est.row_start)
    # print("Row end:", est.row_end)
    # est.print_result(est.run(my_dispatch, True))
    # est.print_result(est.run_hist())
# # # Example # # # 

def estimate_example():
    """
    An example to estimate the build-in dispatching algorithm
    See cool_dispatch in algo/greedy/cool.py for reference
    """
    est = Estimator()
    from algo.greedy.cool import cool_dispatch
    from algo.greedy.Timeline import gogo_dispatch
    from algo.greedy.send2 import my_dispatch
    from algo.greedy.efficient import efficient_dispatch
    # est.pick_day('most')
    est.set_range(10, 20)
    result = est.run(gogo_dispatch)
    # print(est.multi_run([cool_dispatch, efficient_dispatch], 7))
    est.print_result(result, verbose=True)
    est.draw(result)

# estimate_my_algorithm()

estimate_example()
