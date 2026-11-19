# FIFO-and-the-Dining-Philosophers

[Uploading fifo-dining-philosophers-readme.md…]()
# FIFO and the Dining Philosophers: Deadlock, Starvation, and a Fair Ticket-Queue Solution, Executed Step by Step

A 40-page article that puts the FIFO (First In, First Out) discipline head-to-head with the classic dining philosophers problem: every solution is written out in pseudocode, executed by hand step by step, and then measured in a real simulation — so the deadlock, the starvation, and the cost of fairness are all shown in numbers, not just claimed.

## At a glance

| Item | Detail |
| --- | --- |
| Format | 40 pages, A4, English |
| Structure | 15 chapters, plus conclusion and 3 appendices |
| Visuals | 6 figures, 3 flowcharts, 20+ tables |
| Code | Pseudocode for all six solutions, a C skeleton with POSIX threads, and a Python simulator |
| Simulation | 20,000 ticks, seed 42, code included in the appendices |
| References | 8 sources |
| Also available | A separate Persian translation: 38 pages, A4, right-to-left, with the same tables, figures, and numbers |

## The problem in brief

Five philosophers sit around a table, alternating between thinking and eating. Between each pair of neighbours there is one fork, and a philosopher needs both neighbouring forks to eat.

That small setup contains two of the hardest problems in concurrency:

- **Deadlock** — if every philosopher picks up the left fork first and then waits for the right one, everyone holds one fork and waits forever. Nobody eats, and nobody ever will.
- **Starvation** — even without deadlock, an unlucky philosopher can be overtaken by the neighbours again and again and never get both forks, while the system as a whole keeps running.

A correct solution has to prevent both, and the interesting question is what each solution gives up in return.

## The approaches in brief

**Naive pickup.** Each philosopher takes the left fork, then the right fork, eats, and puts both down. It is the natural first attempt, and it is the one that deadlocks: the article executes it in 10 steps until every philosopher is holding one fork and waiting on the next, then checks the failure against the four Coffman conditions.

**FIFO ticket queue.** Hungry philosophers take a numbered ticket and join a single queue in front of the table. Only the philosopher at the head of the queue may collect both forks and eat; when they finish, the next ticket is served. Because turns are granted strictly in arrival order, no one can be overtaken — which is what turns "usually fair" into "provably starvation-free", with a bounded wait.

**Footman (semaphore).** A counting semaphore admits at most four philosophers to the table at once. With at most four competing for five forks, at least one can always get both, so the circular wait behind the deadlock cannot form.

**Resource hierarchy.** All forks are numbered, and every philosopher must pick them up in the same global order, lowest number first. One shared order breaks the cycle: someone is always able to complete the pair.

**Asymmetric pickup.** One philosopher — or every odd-numbered one — picks up the forks in the opposite order to the rest. That single exception breaks the symmetry that the deadlock needs.

**Monitor.** All fork bookkeeping moves inside one monitor: a philosopher states "hungry", is granted both forks together when both are free, and signals on putting them down. Granting both forks atomically removes hold-and-wait, at the cost of centralising every decision.

## Worked executions

The article does not stop at the pseudocode. Three executions are traced in full:

- **Deadlock, in 10 steps** — the naive solution is stepped forward until the wait-for graph closes into a cycle and every philosopher is blocked.
- **Starvation, as a repeating schedule** — a dedicated chapter builds a schedule that repeats indefinitely in which philosopher P2, caught between two neighbours who keep alternating, never eats, even though the table never deadlocks.
- **FIFO, in 12 steps** — the ticket queue is executed by hand with a Gantt timeline, including the head-of-line blocking step, where the queue waits on its head even though a later philosopher's forks happen to be free. That step is the honest price of strict order, and the article keeps it visible rather than hiding it.

## Comparison table

All six approaches are scored in the article on the same eight criteria (C1–C8), covering deadlock freedom, starvation freedom, fairness, concurrency, waiting time, and implementation cost. The short version:

| Approach | Deadlock-free | Starvation-free | Main trade-off |
| --- | --- | --- | --- |
| Naive pickup | No | No | Simplest code, fails both ways |
| FIFO ticket queue | Yes | Yes — proven | Lower throughput, head-of-line blocking |
| Footman semaphore | Yes | No | Fairness depends on semaphore wake-up order |
| Resource hierarchy | Yes | No | Needs a global fork ordering everyone follows |
| Asymmetric pickup | Yes | No | One special case in the code |
| Monitor | Yes | No | Centralised control, both forks granted atomically |

FIFO is the only solution in the comparison whose freedom from starvation is proven rather than observed: serving strictly in ticket order means a philosopher's wait is bounded by the philosophers ahead of them in the queue.

## Simulation results

The closing simulation runs the table for 20,000 ticks with seed 42, comparing the FIFO ticket queue against granting forks with no ordering. The simulator's Python code is included in the appendices, so every number below can be reproduced.

| Measure | FIFO ticket queue | No ordering |
| --- | ---: | ---: |
| Total meals served | 4,865 | 6,154 |
| Spread between philosophers | 8 meals | — |
| Mean waiting time | 8.47 | 4.20 |

The reading is straightforward: strict fairness is not free. FIFO serves about a fifth fewer meals and roughly doubles the mean wait — and in exchange, the hungriest and luckiest philosophers end within 8 meals of each other, and nobody can wait forever. The article also includes a fair critique of FIFO, the edge cases N = 1 and N = 2, a comparison with other scheduling disciplines, and worked self-test examples and exercises with answers.

## When to use FIFO, and when not

Use the FIFO ticket queue when:

- Every waiter must be served eventually, with a wait you can bound in advance.
- Fairness between competitors matters more than total throughput.
- You need a guarantee you can prove, not a behaviour you have only observed in tests.

Prefer one of the classic solutions when:

- Throughput is the priority and occasional long waits are acceptable — unordered granting served 6,154 meals in the same simulation.
- A global resource order is easy to impose, making resource hierarchy the smaller change.
- The platform already gives you a well-tested monitor or semaphore primitive and its wake-up policy is fair enough for your case.

## Key takeaway

Deadlock and starvation are different failures and need different defences. The classic dining philosophers solutions are very good at preventing deadlock, but most of them leave starvation to chance. FIFO is the discipline that closes both: a ticket, a queue, and service strictly in arrival order — at a measurable cost of about a fifth of the throughput and about twice the mean wait.
