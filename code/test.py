from algo.estimator import Estimator
from algo.greedy.cool import cool_dispatch
from algo.greedy.send2 import my_dispatch


est = Estimator()

print("==== MOST====")
est.pick_day('most')
print("Task number:", est.row_end-est.row_start+1)
print("Row start:", est.row_start)
print("Row end:", est.row_end)
# est.print_result(est.run(my_dispatch, False))
# est.print_result(est.run(cool_dispatch, False))
est.print_result(est.run_hist())

print("\n==== LEAST ====")
est.pick_day('least')
print("Task number:", est.row_end-est.row_start+1)
print("Row start:", est.row_start)
print("Row end:", est.row_end)
# est.print_result(est.run(my_dispatch, False))
# est.print_result(est.run(cool_dispatch, False))
est.print_result(est.run_hist())

print("\n==== MEDIAN ====")
est.pick_day('median')
print("Task number:",est.row_end-est.row_start+1)
print("Row start:", est.row_start)
print("Row end:", est.row_end)
# est.print_result(est.run(my_dispatch, False))
# est.print_result(est.run(cool_dispatch, False))
est.print_result(est.run_hist())

print("\n==== 12/9 ====")
est.set_range(30189, 30277)
print("Task number:", est.row_end-est.row_start+1)
print("Row start:", est.row_start)
print("Row end:", est.row_end)
# est.print_result(est.run(my_dispatch, False))
# est.print_result(est.run(cool_dispatch, False))
est.print_result(est.run_hist())