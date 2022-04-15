from .simulator import Simulator
from .his.data import get_data, df
from .utils.plot import ganttplot
from .utils.utility import count_move_dis, move_dis_to_time, get_pier_latlng, get_oil_price
from copy import deepcopy
from collections import deque
from datetime import datetime, timedelta
from sys import stderr
from time import strftime, time
import numpy as np
import scipy.stats as stats
import pandas as pd
import random

class Estimator():
    """A class to estimate the given dispatching algorithm

    Methods: 
        run: estimates the algorithm with randomly generated events 
    """
    def __init__(self):
        self.row_start = 100
        self.row_end = 120

    def set_range(self, start, end):
        """Specify the range in history data for estimation
        
        Args:
            start (int): starting row of his/2017.xlsx
            end (int): ending row of his/2017.xlsx
        """
        assert end-start > 0, "Negative range"
        self.row_start = start
        self.row_end = end

    def pick_day(self, day):
        """Set the range to the day with the most or least tasks

        Args:
            day (str): one of 'most' or 'least'
        """

        picks = ['most', 'least','median','mean']
        if day not in picks:
            raise ValueError("Invalid day. Expected one of {}.".format(picks))
        date = df.start_time.apply(lambda x : x.date())
        all_dates = np.unique(date)
        date_num = np.array([])
        for i in all_dates:
            num = np.count_nonzero(date == i)
            date_num = np.append(date_num, num)
        
        if day == picks[0]:
            max_row = np.where(date == all_dates[date_num.argmax()])
            self.row_start = max_row[0].min()
            self.row_end = max_row[0].max()
        elif day == picks[1]:
            min_row = np.where(date == all_dates[date_num.argmin()])
            self.row_start = min_row[0].min()
            self.row_end = min_row[0].max()
        elif day == picks[2]:
            median_row = np.where(date == all_dates[np.argsort(date_num)[len(date_num)//2]])
            self.row_start = median_row[0].min()
            self.row_end = median_row[0].max()
        elif day == picks[3]:
            mean = np.mean(date_num)
            mean_idx = (np.abs(date_num-mean)).argmin()
            mean_row = np.where(date == all_dates[mean_idx])
            self.row_start = mean_row[0].min()
            self.row_end = mean_row[0].max()


    def run(self, algorithm, verbose=True):
        """
        Arg:
            algorithm (function): The algorithm as a python function to be estimated

        Return:
            result (dict): The result of estimation containing waiting times, tugs, profit, etc
        """
        
        t_start = time()
        self.tasks, self.tugs = get_data(self.row_start, self.row_end)
        if verbose:
            print("Simulation with {} tasks".format(len(self.tasks)))

        simulator = Simulator(self.tasks, self.tugs, verbose)
        result = simulator.run(algorithm)
        t_end = time()

        result['algorithm'] = algorithm
        result['time_usage'] = t_end - t_start

        return result

    def run_hist(self):
        tasks, _ = get_data(self.row_start, self.row_end, from_hist=True)
        for task in tasks:
            task.tugs.sort(key=lambda tug: tug.tug_id)
            for tug in task.tugs:
                move_dis = count_move_dis(tug.pos, task.start)
                move_time = move_dis_to_time(move_dis)
                task.moving_time += move_time
                task.moving_cost += get_oil_price(tug.hp) * move_dis
                task.tugs_start_time.append(task.start_time_real-move_time)
                tug.pos = get_pier_latlng(task.to)
        simulator = Simulator(tasks, [])
        simulator.collect_result()
        result = simulator.result

        def history():
            pass

        result['algorithm'] = history
        result['time_usage'] = 0

        return result

    def multi_run(self, algorithms, n=50, benchmark='profit', with_hist=False, verbose=False, seed=None):
        """
        Args:
            algorithms ([function]): a list of funcionts to be estimated
            n (int): the number of samples to estimate an algorithm
            benchmark (str): estimation targets between algorithms, one of 'profit', 
                'revenue', 'waiting_cost', 'waiting_time', 'moving_cost', 'moving_time',
                'matched', 'oversize', 'undersize'
            with_hist (bool): whether to include comparison with historical result
            verbose (bool): whether to print detailed process of simulation
            seed (int): random seed

        Return:
            pandas.DataFrame: a dict with keys being algorithms' names and values being n times results
        """

        assert len(algorithms), "The list of algorithms to be estimated is empty"
        assert n > 0, "Negative simulation times"
        bms = ['profit', 'revenue', 'waiting_cost', 'waiting_time', 'moving_cost', 
            'moving_time', 'matched', 'oversize', 'undersize']
        if benchmark not in bms:
            raise ValueError("Invalid benchmark. Expected one of {}.".format(bms))
        if not seed:
            seed = datetime.now().microsecond
            
        if with_hist and n != 1:
            print("WARNING: Required to compare with history. The number of samples has been set to 1")
            n = 1

        self.tasks, self.tugs = get_data(self.row_start, self.row_end)

        samples = {}
        times = deque([])
        for algo in algorithms:
            print("Estimating {}...".format(algo.__name__), end="")
            values = []
            if not verbose:
                print('|'+'-'*20+'|', end='', flush=True)
            else:
                print("")
            random.seed(seed)

            t_start = time()
            for i in range(n):
                if verbose:
                    print("Round {}/{}...".format(i+1, n))

                tasks, tugs = deepcopy(self.tasks), deepcopy(self.tugs)
                simulator = Simulator(tasks, tugs, verbose)
                values.append(simulator.run(algo)[benchmark])

                if not verbose:
                    done = min((i+1)*20//n, 20)
                    print('\b'*21+'█'*done+'-'*(20-done)+'|', end='', flush=True)
            t_end = time()
            if not verbose:
                print('')
            samples[algo.__name__] = values
            times.append(t_end-t_start)
            
        if with_hist:
            samples['history'] = self.run_hist()[benchmark]
            times.append(0)

        
        print("\n=== Simulation Result ===")

        for algo, result in samples.items():
            print("Algorithm:", algo)
            print("Mean:", round(np.mean(result), 2))
            print("Std:", round(np.std(result), 2))
            print("Time: ", round(times.popleft(), 4), 's')
            print("")

        return self.compare(samples)
        
    def compare(self, samples):
        """
        Arg:
            samples (dict): a dict with keys being algorithms' names 
                and values being n times results from multi_run()
        Return:
            pandas.DataFrame: a table of p-value
        """
        N = len(samples)
        result = np.zeros((N, N))
        name = list(samples.keys())
        for i in range(N-1):
            for l in range(i+1, N):
                _, pvalue = stats.ttest_rel(samples[name[i]],samples[name[l]])
                result[i][l] = pvalue
                result[l][i] = pvalue
        matrix = pd.DataFrame(result)
        matrix.columns = name
        matrix.index = name
        return matrix

    def print_result(self, result, verbose=False):
        """
        Args:
            result (Dict): Estimation result generated by run().
            verbose (bool): True to print detail information about tasks, False for summary
        """
        if not result:
            print("Printing Error: No result", file=stderr)
            return

        print(("\n"+"="*42+"\n="+"Simulation Result of {}" \
            .center(42-len(result["algorithm"].__name__))+"=\n"+"="*42+"\n") \
            .format(result["algorithm"].__name__.upper()))

        if verbose:
            result['tasks'].sort(key=lambda task: task.id)
            for task in result['tasks']:
                print("=========== Task {} Result ===========".format(task.id))
                print(("* Ship ID: {}\n" +
                    "* Ship State: {}\n" +
                    "* Should Started at: {}\n" +
                    "* Actually Started at: {}\n" +
                    "* Working time: {:02d}:{:02d}\n" +
                    "* State: {}\n" +
                    "* Weight: {}\n\n" +
                    "* Required types: {}\n" +
                    "* Dispatched types: {}\n" +
                    "* Dispatched tugs: {}\n").format(
                        task.ship.ship_id,
                        task.ship_state.name,
                        task.start_time.strftime("%Y-%m-%d %H:%M"),
                        task.start_time_real.strftime("%Y-%m-%d %H:%M"),
                        task.work_time.seconds//3600, (task.work_time.seconds%3600)//60, 
                        task.task_state.name,
                        task.ship.weight,
                        [t.name for t in task.req_types],
                        [t.type.name for t in task.tugs],
                        [t.tug_id for t in task.tugs],
                    ))
                if task.tmp_need_time:
                    print("* Temp need time: {}\n".format(
                        task.tmp_need_time.strftime("%Y-%m-%d %H:%M")))
                        
                print(("* Revenue: {:.2f}\n" + 
                    "* Waiting time: {:02d}:{:02d}\n" +
                    "* Waiting cost: {:.2f} \n" +
                    "* Moving time: {:02d}:{:02d}\n" +
                    "* Moving cost: {:.2f}\n" +
                    "* Profit: {:.2f}\n").format(
                        task.revenue,
                        task.waiting_time.seconds//3600, (task.waiting_time.seconds%3600)//60, 
                        task.waiting_cost,
                        task.moving_time.seconds//3600, (task.moving_time.seconds%3600)//60, 
                        task.moving_cost,
                        task.profit,
                    ))
            print("============== Summary ==============\n")

        print(("• Revenue: {:.4f}\n" +
            "• Waiting_cost: {:.4f}\n" +
            "• Waiting_time: {:02d}:{:02d}\n" +
            "• Moving_cost: {:.4f}\n" + 
            "• Moving_time: {:02d}:{:02d}\n" +
            "• Matched: {:.2%}\n" +
            "• Oversized: {:.2%}\n" +  
            "• Undersized: {:.2%}\n" +   
            "• Profit: {:.4f}\n" +
            "• Time usage: {:.2f} secs").format(
            result["revenue"], 
            result["waiting_cost"], 
            result["waiting_time"].seconds//3600, 
            (result["waiting_time"].seconds%3600)//60,
            result["moving_cost"],
            result["moving_time"].seconds//3600,
            (result["moving_time"].seconds%3600)//60,
            result['matched'],
            result['oversize'],
            result['undersize'],
            result["profit"],
            result['time_usage']))

    def draw(self, result):
        if not result:
            print("Drawing Error: No result", file=stderr)
            return
        ganttplot(result['tasks'], result['tugs'])
