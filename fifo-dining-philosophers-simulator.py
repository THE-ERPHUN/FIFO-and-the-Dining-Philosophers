#!/usr/bin/env python3
"""
FIFO Dining Philosophers Simulator
==================================

Runnable companion code for the article:
    "FIFO and the Dining Philosophers: Deadlock, Starvation, and a Fair
     Ticket-Queue Solution, Executed Step by Step"

What this file contains
-----------------------
1. A REAL threaded implementation of the article's main solution -- the
   FIFO ticket-queue dining philosophers -- built with
   ``threading.Thread``, ``threading.Lock``, ``threading.Condition``
   and ``time.sleep``.  Every philosopher thread thinks, takes a ticket,
   waits until (a) its ticket is at the head of the queue AND
   (b) both of its forks are free, eats, then releases the forks.
   Granting a ticket advances the serving counter immediately, so
   non-neighbours can eat concurrently -- but never out of turn.

   Why it works:
   * No deadlock  -- tickets impose a single global order, so the
     circular-wait condition (Coffman) can never form.
   * No starvation -- tickets are served strictly in arrival order, so
     every hungry philosopher is guaranteed to eat within a bounded
     number of meals by the others (head-of-line blocking is the price:
     if the head's forks are busy, later tickets wait even when their
     own forks happen to be free).

2. A discrete-event (tick) simulation with two grant policies, FIFO and
   unordered, so you can reproduce the article's Chapter-14 experiment:
   20,000 ticks, seed 42.  See ``run_simulation()`` below and the honest
   note on numbers next to it.

3. An optional naive pickup mode (simulation only) in which every
   philosopher picks up the left fork and then waits for the right one.
   Under the adversarial schedule used here it deadlocks within a few
   ticks, exactly like the 10-step hand execution in the article.

Usage
-----
    python3 fifo-dining-philosophers-simulator.py                # threaded FIFO demo (default)
    python3 fifo-dining-philosophers-simulator.py --mode compare # tick simulation, both policies
    python3 fifo-dining-philosophers-simulator.py --mode fifo-sim
    python3 fifo-dining-philosophers-simulator.py --mode unordered
    python3 fifo-dining-philosophers-simulator.py --mode naive    # watch it deadlock
    python3 fifo-dining-philosophers-simulator.py --philosophers 7 --meals 5

No third-party dependencies.  Press Ctrl-C to stop the threaded demo.
"""

from __future__ import annotations

import argparse
import random
import sys
import threading
import time
from collections import deque


# ======================================================================
# PART 1 -- Real threaded implementation: FIFO ticket-queue table
# ======================================================================

class FifoTable:
    """A dining table guarded by a FIFO ticket queue.

    Shared state (all protected by ``self.cond``'s lock):
      * ``next_ticket``  -- ticket number handed to the next arrival.
      * ``now_serving``  -- the oldest ticket not yet granted a seat.
      * ``fork_free[i]`` -- True while fork i lies on the table.
      * ``queue``        -- tickets currently waiting, in arrival order.

    Philosopher i needs fork i (left) and fork (i + 1) % n (right).
    A philosopher may start eating only when its ticket equals
    ``now_serving`` *and* both forks are free.  Granting a ticket
    advances ``now_serving`` at once, so the next ticket is considered
    immediately: two non-neighbours may eat at the same time, but
    grants always happen strictly in arrival (FIFO) order, and a
    blocked head blocks everyone behind it (head-of-line blocking).
    """

    def __init__(self, n: int) -> None:
        self.n = n
        self.cond = threading.Condition(threading.Lock())
        self.next_ticket = 0
        self.now_serving = 0
        self.fork_free = [True] * n
        self.queue: deque[int] = deque()
        self.meals = [0] * n          # completed meals per philosopher
        self.total_wait = [0.0] * n   # seconds spent hungry, per philosopher
        self.wait_samples = [0] * n   # number of waits measured

    # -- internal helper: may philosopher with this ticket eat now? --
    def _can_eat(self, phil: int, ticket: int) -> bool:
        left, right = phil, (phil + 1) % self.n
        return (
            ticket == self.now_serving
            and self.fork_free[left]
            and self.fork_free[right]
        )

    def take_forks(self, phil: int) -> None:
        """Take a ticket and block until it is our turn and forks are free."""
        with self.cond:
            ticket = self.next_ticket
            self.next_ticket += 1
            self.queue.append(ticket)
            started = time.monotonic()
            # Condition-variable wait: re-check the predicate after
            # every wakeup (spurious wakeups are harmless).
            while not self._can_eat(phil, ticket):
                self.cond.wait()
            self.queue.popleft()  # our ticket leaves the head of the queue
            self.total_wait[phil] += time.monotonic() - started
            self.wait_samples[phil] += 1
            left, right = phil, (phil + 1) % self.n
            self.fork_free[left] = False
            self.fork_free[right] = False
            # Granting us advances the serving counter: wake everyone
            # so the new head ticket can try its own forks right away.
            self.now_serving += 1
            self.cond.notify_all()

    def put_forks(self, phil: int) -> None:
        """Return both forks and wake everyone (the head may proceed)."""
        with self.cond:
            left, right = phil, (phil + 1) % self.n
            self.fork_free[left] = True
            self.fork_free[right] = True
            self.meals[phil] += 1
            # notify_all (not notify): the head ticket holder must wake
            # even if it is not the first thread in the wait set.
            self.cond.notify_all()



def philosopher_thread(
    phil: int,
    table: FifoTable,
    meals_wanted: int,
    think_time: float,
    eat_time: float,
    stop: threading.Event,
    rng: random.Random,
) -> None:
    """Life of one philosopher: think -> hungry (ticket) -> eat -> repeat."""
    while not stop.is_set() and table.meals[phil] < meals_wanted:
        # THINKING (outside the lock -- never hold the lock while sleeping)
        time.sleep(rng.uniform(0.5, 1.5) * think_time)
        if stop.is_set():
            break
        # HUNGRY: take a ticket and wait for our turn + both forks
        table.take_forks(phil)
        try:
            # EATING
            print(f"  P{phil} is eating "
                  f"(meal #{table.meals[phil] + 1})", flush=True)
            time.sleep(rng.uniform(0.5, 1.5) * eat_time)
        finally:
            # Always return the forks, even if interrupted mid-meal.
            table.put_forks(phil)


def run_threaded_fifo(args: argparse.Namespace) -> None:
    """Run the real threaded FIFO solution and print a summary table."""
    n = args.philosophers
    table = FifoTable(n)
    stop = threading.Event()
    threads: list[threading.Thread] = []
    print(f"Threaded FIFO ticket-queue demo: {n} philosophers, "
          f"{args.meals} meal(s) each. Ctrl-C stops early.\n")
    started = time.monotonic()
    try:
        for i in range(n):
            t = threading.Thread(
                target=philosopher_thread,
                args=(i, table, args.meals, args.think_time,
                      args.eat_time, stop, random.Random(args.seed + i)),
                name=f"P{i}",
                daemon=True,
            )
            t.start()
            threads.append(t)
        for t in threads:
            # Join in small slices so Ctrl-C stays responsive.
            while t.is_alive():
                t.join(timeout=0.2)
    except KeyboardInterrupt:
        print("\nCtrl-C received -- stopping philosophers ...")
        stop.set()
    elapsed = time.monotonic() - started
    print_threaded_summary(table, elapsed)


def print_threaded_summary(table: FifoTable, elapsed: float) -> None:
    """Per-philosopher meal counts, spread and average waiting time."""
    n = table.n
    total = sum(table.meals)
    spread = (max(table.meals) - min(table.meals)) if n else 0
    print("\n=== Threaded FIFO run -- summary ===")
    print(f"{'Philosopher':<14}{'Meals':>7}{'Avg wait (s)':>14}")
    print("-" * 35)
    for i in range(n):
        avg_wait = (table.total_wait[i] / table.wait_samples[i]
                    if table.wait_samples[i] else 0.0)
        print(f"P{i:<13}{table.meals[i]:>7}{avg_wait:>14.3f}")
    print("-" * 35)
    print(f"Total meals: {total}   Min: {min(table.meals)}   "
          f"Max: {max(table.meals)}   Spread (max-min): {spread}")
    print(f"Elapsed: {elapsed:.1f}s")
    if spread <= 1:
        print("Fairness check: spread <= 1 -- the ticket queue kept "
              "everyone within one meal of each other, as promised.")



# ======================================================================
# PART 2 -- Discrete-event (tick) simulation: FIFO vs unordered vs naive
# ======================================================================
#
# Model (one tick = one discrete time step, as in the article):
#   * Each philosopher cycles THINKING -> HUNGRY -> EATING -> THINKING.
#   * Thinking takes a uniformly random number of ticks in
#     [SIM_THINK_MIN, SIM_THINK_MAX]; eating takes a uniformly random
#     number of ticks in [SIM_EAT_MIN, SIM_EAT_MAX].
#   * Philosopher i conflicts with neighbours (i-1) % n and (i+1) % n:
#     two neighbours can never eat in the same tick (shared fork).
#   * FIFO policy: hungry philosophers join a ticket queue. Only the
#     ticket at the HEAD of the queue may start eating, and only when
#     neither neighbour is eating. If the head is blocked, everyone
#     behind it waits too (head-of-line blocking) -- that is exactly
#     why FIFO is fair but slower.
#   * Unordered policy: every hungry philosopher whose neighbours are
#     not eating may start immediately (hungry set scanned in random
#     order each tick). Faster, but nothing bounds anyone's wait.
#   * Waiting time of a meal = ticks from becoming hungry to starting
#     to eat. Averages below are over all meals actually started.
#
# Honest note on the article's numbers: Chapter 14 of the article
# reports, for 20,000 ticks and seed 42, FIFO = 4,865 meals with a
# spread of 8 and average wait 8.47 ticks, versus unordered = 6,154
# meals and average wait 4.20 ticks. Those figures came from the
# article's own simulator, whose exact think/eat distributions are not
# published, so this re-implementation -- with the distributions stated
# openly above -- lands close to, but not exactly on, those numbers.
# The qualitative result is identical and robust: FIFO trades roughly
# a fifth of the throughput and about double the average wait for a
# hard fairness guarantee (a tiny meal spread), while unordered is
# faster on average with no bound on individual waiting.

SIM_THINK_MIN = 3
SIM_THINK_MAX = 8
SIM_EAT_MIN = 5
SIM_EAT_MAX = 8


class SimResult:
    """Counters collected by one simulation run."""

    def __init__(self, n: int) -> None:
        self.meals = [0] * n
        self.waits: list[int] = []
        self.timeline: list[frozenset[int]] = []  # eaters per tick
        self.deadlocked_at: int | None = None

    @property
    def total(self) -> int:
        return sum(self.meals)

    @property
    def spread(self) -> int:
        return max(self.meals) - min(self.meals) if self.meals else 0

    @property
    def avg_wait(self) -> float:
        return sum(self.waits) / len(self.waits) if self.waits else 0.0

    @property
    def max_wait(self) -> int:
        return max(self.waits) if self.waits else 0



def run_simulation(n: int, ticks: int, seed: int, policy: str) -> SimResult:
    """Run the tick simulation under policy 'fifo' or 'unordered'.

    A single ``random.Random(seed)`` drives everything, so a run is
    fully reproducible for a given (n, ticks, seed, policy) triple.
    """
    if policy not in ("fifo", "unordered"):
        raise ValueError(f"unknown simulation policy: {policy!r}")
    rng = random.Random(seed)
    THINKING, HUNGRY, EATING = 0, 1, 2
    state = [THINKING] * n
    timer = [rng.randint(SIM_THINK_MIN, SIM_THINK_MAX) for _ in range(n)]
    hungry_since: list[int | None] = [None] * n
    queue: deque[int] = deque()          # FIFO ticket queue (phil ids)
    eating: set[int] = set()
    res = SimResult(n)

    def neighbours_eating(i: int) -> bool:
        return ((i - 1) % n in eating) or ((i + 1) % n in eating)

    def start_eating(i: int, t: int) -> None:
        state[i] = EATING
        timer[i] = rng.randint(SIM_EAT_MIN, SIM_EAT_MAX)
        eating.add(i)
        res.waits.append(t - (hungry_since[i] or t))
        hungry_since[i] = None

    for t in range(ticks):
        # 1) Advance timers; collect this tick's state changes first so
        #    iteration order never biases the outcome.
        finished, became_hungry = [], []
        for i in range(n):
            if state[i] in (THINKING, EATING):
                timer[i] -= 1
                if timer[i] <= 0:
                    (finished if state[i] == EATING
                     else became_hungry).append(i)
        for i in finished:
            eating.discard(i)
            res.meals[i] += 1
            state[i] = THINKING
            timer[i] = rng.randint(SIM_THINK_MIN, SIM_THINK_MAX)
        for i in became_hungry:
            state[i] = HUNGRY
            hungry_since[i] = t
            if policy == "fifo":
                queue.append(i)          # take a ticket

        # 2) Admission: who may start eating this tick?
        if policy == "fifo":
            # Only the head ticket is considered. Admitting it may
            # unblock the next head within the same tick, so loop --
            # but stop at the first blocked head (head-of-line blocking).
            while queue:
                head = queue[0]
                if neighbours_eating(head):
                    break
                queue.popleft()
                start_eating(head, t)
        else:  # unordered: anyone with free forks, in random order
            hungry = [i for i in range(n) if state[i] == HUNGRY]
            rng.shuffle(hungry)
            for i in hungry:
                if not neighbours_eating(i):
                    start_eating(i, t)

        # 3) Record who is eating during this tick (for the Gantt view)
        res.timeline.append(frozenset(eating))
    return res



def run_naive_simulation(n: int, ticks: int, seed: int) -> SimResult:
    """Naive pickup: grab the left fork, then wait for the right one.

    Uses the adversarial schedule from the article's hand execution:
    in every tick, each hungry philosopher who can take its LEFT fork
    does so *before* anyone tries for the right fork. After the first
    round everyone holds exactly one fork and waits forever -- the
    classic circular wait. The run stops and reports the tick at
    which the deadlock becomes permanent.
    """
    rng = random.Random(seed)
    res = SimResult(n)
    holder: list[int | None] = [None] * n   # fork i held by whom?
    has_left = [False] * n
    state = ["hungry"] * n                  # everyone starts hungry
    eat_left = [0] * n                      # ticks of eating remaining

    for t in range(ticks):
        res.timeline.append(frozenset(
            i for i in range(n) if state[i] == "eating"))
        # Eating philosophers finish and release both forks.
        for i in range(n):
            if state[i] == "eating":
                eat_left[i] -= 1
                if eat_left[i] <= 0:
                    holder[i] = None
                    holder[(i + 1) % n] = None
                    res.meals[i] += 1
                    state[i] = "hungry"
                    has_left[i] = False
        # Phase A: everyone takes their left fork if it is free.
        for i in range(n):
            if state[i] == "hungry" and not has_left[i] and holder[i] is None:
                holder[i] = i
                has_left[i] = True
        # Phase B: holders of a left fork try for the right fork.
        for i in range(n):
            if state[i] == "hungry" and has_left[i]:
                right = (i + 1) % n
                if holder[right] is None:
                    holder[right] = i
                    state[i] = "eating"
                    eat_left[i] = rng.randint(SIM_EAT_MIN, SIM_EAT_MAX)
        # Deadlock test: everyone holds their left fork, nobody is
        # eating, and every right fork is held by the neighbour.
        if (all(has_left[i] and state[i] == "hungry" for i in range(n))
                and all(holder[(i + 1) % n] is not None for i in range(n))):
            res.deadlocked_at = t
            break
    return res


def print_gantt(timeline: list[frozenset[int]], n: int,
                max_ticks: int = 60) -> None:
    """Print a compact ASCII Gantt chart of the first ``max_ticks`` ticks.

    '#' means the philosopher is eating in that tick, '.' means not.
    """
    shown = min(len(timeline), max_ticks)
    print(f"\nASCII Gantt -- first {shown} ticks "
          f"(# = eating, . = thinking/hungry):")
    print("      " + "".join(str((t // 10) % 10) for t in range(shown)))
    print("      " + "".join(str(t % 10) for t in range(shown)))
    for i in range(n):
        row = "".join("#" if i in timeline[t] else "."
                      for t in range(shown))
        print(f"  P{i}  {row}")



def print_sim_summary(label: str, res: SimResult, ticks: int,
                      seed: int) -> None:
    """Summary table for one simulation run."""
    n = len(res.meals)
    print(f"\n=== {label} ===")
    print(f"ticks={ticks}  seed={seed}  philosophers={n}")
    print(f"{'Philosopher':<14}{'Meals':>7}")
    print("-" * 21)
    for i in range(n):
        print(f"P{i:<13}{res.meals[i]:>7}")
    print("-" * 21)
    print(f"Total meals: {res.total}   Min: {min(res.meals)}   "
          f"Max: {max(res.meals)}   Spread (max-min): {res.spread}")
    print(f"Average wait: {res.avg_wait:.2f} ticks   "
          f"Max wait: {res.max_wait} ticks")


def print_compare(fifo: SimResult, unord: SimResult, ticks: int,
                  seed: int) -> None:
    """Side-by-side comparison, mirroring the article's Chapter 14 table."""
    print_sim_summary("Simulation -- FIFO ticket queue", fifo, ticks, seed)
    print_sim_summary("Simulation -- Unordered grant", unord, ticks, seed)
    print("\n=== Head-to-head (this run) ===")
    print(f"{'Metric':<26}{'FIFO':>12}{'Unordered':>12}")
    print("-" * 50)
    print(f"{'Total meals':<26}{fifo.total:>12}{unord.total:>12}")
    print(f"{'Spread (max-min meals)':<26}{fifo.spread:>12}"
          f"{unord.spread:>12}")
    print(f"{'Average wait (ticks)':<26}{fifo.avg_wait:>12.2f}"
          f"{unord.avg_wait:>12.2f}")
    print(f"{'Max wait (ticks)':<26}{fifo.max_wait:>12}{unord.max_wait:>12}")
    print("-" * 50)
    if unord.total:
        loss = 100.0 * (unord.total - fifo.total) / unord.total
        print(f"FIFO fairness cost in this run: {loss:.1f}% fewer meals, "
              f"in exchange for a spread of {fifo.spread} meal(s) and a "
              f"bounded wait for everyone.")
    print("\nArticle, Chapter 14 (20,000 ticks, seed 42), for reference: "
          "FIFO 4,865 meals, spread 8, avg wait 8.47 -- unordered "
          "6,154 meals, avg wait 4.20. This re-implementation uses openly "
          "stated think/eat distributions, so expect close-but-not-"
          "identical figures with the same conclusion.")



# ======================================================================
# PART 3 -- Command-line interface
# ======================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="FIFO dining philosophers: threaded ticket-queue "
                    "demo plus a tick simulation (FIFO vs unordered "
                    "vs naive). Companion code for the article 'FIFO "
                    "and the Dining Philosophers'.")
    p.add_argument(
        "--mode",
        choices=["fifo", "fifo-sim", "unordered", "naive", "compare"],
        default="fifo",
        help="'fifo' (default): real threaded ticket-queue demo. "
             "'fifo-sim' / 'unordered': tick simulation with that "
             "policy. 'compare': run both simulations side by side. "
             "'naive': simulation of naive pickup -- deadlocks fast.")
    p.add_argument("--philosophers", type=int, default=5,
                   help="number of philosophers (default: 5)")
    p.add_argument("--meals", type=int, default=3,
                   help="meals per philosopher in threaded mode "
                        "(default: 3)")
    p.add_argument("--ticks", type=int, default=20_000,
                   help="simulation length in ticks (default: 20000, "
                        "as in the article)")
    p.add_argument("--seed", type=int, default=42,
                   help="random seed (default: 42, as in the article)")
    p.add_argument("--think-time", type=float, default=0.4,
                   help="base thinking time in seconds, threaded mode "
                        "(default: 0.4)")
    p.add_argument("--eat-time", type=float, default=0.3,
                   help="base eating time in seconds, threaded mode "
                        "(default: 0.3)")
    p.add_argument("--gantt", action="store_true",
                   help="also print an ASCII Gantt chart of the first "
                        "60 ticks (simulation modes)")
    args = p.parse_args(argv)
    if args.philosophers < 2:
        p.error("--philosophers must be at least 2")
    if args.ticks < 1:
        p.error("--ticks must be at least 1")
    if args.meals < 1:
        p.error("--meals must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    n, ticks, seed = args.philosophers, args.ticks, args.seed
    try:
        if args.mode == "fifo":
            run_threaded_fifo(args)
        elif args.mode == "fifo-sim":
            res = run_simulation(n, ticks, seed, "fifo")
            print_sim_summary("Simulation -- FIFO ticket queue",
                              res, ticks, seed)
            if args.gantt:
                print_gantt(res.timeline, n)
        elif args.mode == "unordered":
            res = run_simulation(n, ticks, seed, "unordered")
            print_sim_summary("Simulation -- Unordered grant",
                              res, ticks, seed)
            if args.gantt:
                print_gantt(res.timeline, n)
        elif args.mode == "compare":
            fifo = run_simulation(n, ticks, seed, "fifo")
            unord = run_simulation(n, ticks, seed, "unordered")
            print_compare(fifo, unord, ticks, seed)
            if args.gantt:
                print("\nFIFO timeline:")
                print_gantt(fifo.timeline, n)
                print("\nUnordered timeline:")
                print_gantt(unord.timeline, n)
        elif args.mode == "naive":
            res = run_naive_simulation(n, ticks, seed)
            if res.deadlocked_at is not None:
                print(f"Naive pickup: DEADLOCK at tick "
                      f"{res.deadlocked_at}. Every philosopher holds "
                      f"its left fork and waits forever for the right "
                      f"one -- circular wait, no one can ever eat. "
                      f"This is why the plain solution fails; the "
                      f"ticket queue exists to prevent exactly this.")
            else:
                print(f"Naive pickup survived {ticks} ticks this time "
                      f"({res.total} meals) -- deadlock needs the "
                      f"unlucky interleaving, which the adversarial "
                      f"schedule in this mode normally forces at once.")
            print_sim_summary("Simulation -- Naive pickup",
                              res, ticks, seed)
    except KeyboardInterrupt:
        print("\nInterrupted by user (Ctrl-C). Bye.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
