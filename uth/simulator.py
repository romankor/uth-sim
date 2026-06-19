"""Monte Carlo driver and statistics aggregation.

Two modes:

* ``"ev"`` (default) — for each random deal, compute the *exact* EV integrated
  over all 990 possible dealer holdings. Unbiased and low-variance, so the house
  edge converges in a few million hands instead of tens of millions.
* ``"play"`` — deal a single random dealer hand and settle the realized result.
  Use this to study the distribution a player actually experiences (bankroll
  swings, risk of ruin).
"""

import math
import multiprocessing
import os
import random
from concurrent.futures import ProcessPoolExecutor

from .game import Config, play_hand, exact_hand_ev
from .paytables import trips_analytics, blind_cv_mean

_DECISIONS = ("4x", "2x", "1x", "fold")


class Stats:
    """Aggregated results; combine partials from parallel workers with ``+``.

    Two exact, zero-bias variance-reduction tricks are applied:

    * The Trips bet (a pure function of the player's hand) is added
      analytically via ``trips_ev_const`` / ``trips_m2_const`` — no sampling.
    * The blind multiplier ``cv`` is used as a *control variate* with mean
      ``blind_cv_mean``. Subtracting its centred, optimally-scaled value cancels
      the dominant royal-flush (500:1) variance from the house-edge estimate.

    ``sum_ev`` holds the sampled Ante+Blind+Play net per hand.
    """

    def __init__(self, mode="ev"):
        self.mode = mode
        self.hands = 0
        self.sum_ev = 0.0          # sum of per-hand net
        self.sum_ev_sq = 0.0       # sum of net^2
        self.sum_cv = 0.0          # sum of control variate (blind multiplier)
        self.sum_cv_sq = 0.0       # sum of cv^2
        self.sum_ev_cv = 0.0       # sum of net * cv
        self.sum_m2 = 0.0          # sum of per-hand E[net^2] (result variance)
        self.sum_wagered = 0.0
        self.sum_play_wagered = 0.0
        self.sum_trips = 0.0
        self.sum_ante = 0.0
        self.sum_blind = 0.0
        self.sum_play = 0.0
        self.decisions = {d: 0 for d in _DECISIONS}
        self.trips_ev_const = 0.0  # exact Trips EV per hand
        self.trips_m2_const = 0.0  # exact Trips second moment per hand
        self.trips_bet = 0.0       # Trips stake in ante units
        self.cv_mean = 0.0         # analytical E[blind multiplier]

    def _record(self, net, m2, cv, r):
        self.hands += 1
        self.sum_ev += net
        self.sum_ev_sq += net * net
        self.sum_cv += cv
        self.sum_cv_sq += cv * cv
        self.sum_ev_cv += net * cv
        self.sum_m2 += m2
        self.sum_wagered += r.wagered
        self.sum_play_wagered += r.play_bet
        self.sum_ante += r.ante_ev if self.mode == "ev" else r.ante_net
        self.sum_blind += r.blind_ev if self.mode == "ev" else r.blind_net
        self.sum_play += r.play_ev if self.mode == "ev" else r.play_net
        self.sum_trips += 0.0 if self.mode == "ev" else r.trips_net
        self.decisions[r.decision] += 1

    def record_ev(self, r):
        self._record(r.ev, r.m2, r.cv, r)

    def record_play(self, r):
        self._record(r.net, r.net * r.net, r.cv, r)

    def __add__(self, other):
        out = Stats(self.mode)
        out.hands = self.hands + other.hands
        for attr in ("sum_ev", "sum_ev_sq", "sum_cv", "sum_cv_sq", "sum_ev_cv",
                     "sum_m2", "sum_wagered", "sum_play_wagered", "sum_trips",
                     "sum_ante", "sum_blind", "sum_play"):
            setattr(out, attr, getattr(self, attr) + getattr(other, attr))
        out.decisions = {d: self.decisions[d] + other.decisions[d] for d in _DECISIONS}
        out.trips_ev_const = self.trips_ev_const or other.trips_ev_const
        out.trips_m2_const = self.trips_m2_const or other.trips_m2_const
        out.trips_bet = self.trips_bet or other.trips_bet
        out.cv_mean = self.cv_mean or other.cv_mean
        return out

    # --- Control variate -----------------------------------------------------
    @property
    def _beta(self):
        """Optimal control-variate coefficient Cov(net, cv) / Var(cv)."""
        n = self.hands
        if n < 2:
            return 0.0
        var_cv = self.sum_cv_sq / n - (self.sum_cv / n) ** 2
        if var_cv <= 0:
            return 0.0
        cov = self.sum_ev_cv / n - (self.sum_ev / n) * (self.sum_cv / n)
        return cov / var_cv

    @property
    def base_ev_per_hand(self):
        """Control-variated mean of the Ante+Blind+Play net per hand."""
        if not self.hands:
            return 0.0
        beta = self._beta
        return self.sum_ev / self.hands - beta * (self.sum_cv / self.hands - self.cv_mean)

    # --- Derived metrics -----------------------------------------------------
    @property
    def ev_per_hand(self):
        """Total expected net per hand, including the analytical Trips EV."""
        return self.base_ev_per_hand + self.trips_ev_const

    @property
    def trips_ev_per_hand(self):
        if self.mode == "ev":
            return self.trips_ev_const
        return self.sum_trips / self.hands if self.hands else 0.0

    @property
    def base_house_edge(self):
        """Base-game (Ante+Blind+Play) house edge as a % of the Ante.

        This is the standard UTH "house edge on the Ante" figure and excludes
        the optional Trips side bet, which carries its own edge on its own stake.
        """
        return -self.base_ev_per_hand * 100.0

    @property
    def trips_house_edge(self):
        """House edge of the Trips bet as a % of the Trips stake."""
        if not self.trips_bet:
            return 0.0
        return -(self.trips_ev_per_hand / self.trips_bet) * 100.0

    @property
    def house_edge(self):
        """Total expected loss as a percentage of the Ante (base game + Trips)."""
        return -self.ev_per_hand * 100.0

    @property
    def element_of_risk(self):
        """Expected loss as a percentage of total amount wagered."""
        total = self.ev_per_hand * self.hands
        return -total / self.sum_wagered * 100.0 if self.sum_wagered else 0.0

    @property
    def result_std_dev(self):
        """Std dev of a single hand's realized result, in ante units.

        In EV mode this combines the exact dealer-integrated base-game variance
        with the exact analytical Trips variance, treating the two as
        independent (the small big-hand correlation is negligible). In play mode
        it is the directly observed realized variance.
        """
        if self.hands < 1:
            return 0.0
        base_mean = self.sum_ev / self.hands
        base_var = self.sum_m2 / self.hands - base_mean ** 2
        trips_var = self.trips_m2_const - self.trips_ev_const ** 2
        return math.sqrt(max(0.0, base_var + trips_var))

    @property
    def _estimator_std_error(self):
        """Std error of the (control-variated) house-edge estimate."""
        n = self.hands
        if n < 2:
            return 0.0
        beta = self._beta
        # Variance of the controlled variate  net - beta*cv.
        mean_c = self.sum_ev / n - beta * (self.sum_cv / n)
        sum_c_sq = self.sum_ev_sq - 2 * beta * self.sum_ev_cv + beta * beta * self.sum_cv_sq
        var_c = sum_c_sq / n - mean_c * mean_c
        return math.sqrt(max(0.0, var_c)) / math.sqrt(n)

    @property
    def house_edge_ci95(self):
        return 1.96 * self._estimator_std_error * 100.0

    @property
    def avg_total_bet(self):
        return self.sum_wagered / self.hands if self.hands else 0.0


def _run_chunk(args):
    n, seed, cfg, mode = args
    rng = random.Random(seed)
    deck = list(range(52))
    stats = Stats(mode)
    if mode == "ev":
        for _ in range(n):
            stats.record_ev(exact_hand_ev(deck, rng, cfg))
    else:
        for _ in range(n):
            stats.record_play(play_hand(deck, rng, cfg))
    return stats


def simulate(hands, seed=0, cfg=None, workers=1, mode="ev", progress=None):
    """Run ``hands`` hands and return aggregated :class:`Stats`."""
    cfg = cfg or Config()

    if workers <= 1:
        total = _run_chunk_progress(hands, seed + 1, cfg, mode, progress)
    else:
        base, rem = divmod(hands, workers)
        tasks = [(base + (1 if w < rem else 0), seed + w + 1, cfg, mode)
                 for w in range(workers) if base + (1 if w < rem else 0)]
        total = Stats(mode)
        done = 0
        with ProcessPoolExecutor(max_workers=workers, mp_context=_mp_context()) as ex:
            for part in ex.map(_run_chunk, tasks):
                total = total + part
                done += part.hands
                if progress:
                    progress(done, hands)

    # Analytical E[blind multiplier] anchors the control variate (both modes).
    total.cv_mean = blind_cv_mean(cfg.blind_table)
    total.trips_bet = cfg.trips_bet
    # In EV mode the Trips bet is added analytically (exact, zero variance).
    if mode == "ev" and cfg.trips_bet:
        ev, m2 = trips_analytics(cfg.trips_table, cfg.trips_bet)
        total.trips_ev_const = ev
        total.trips_m2_const = m2
    return total


def _run_chunk_progress(n, seed, cfg, mode, progress):
    rng = random.Random(seed)
    deck = list(range(52))
    stats = Stats(mode)
    step = max(1, n // 100)
    record = stats.record_ev if mode == "ev" else stats.record_play
    deal = exact_hand_ev if mode == "ev" else play_hand
    for i in range(n):
        record(deal(deck, rng, cfg))
        if progress and (i + 1) % step == 0:
            progress(i + 1, n)
    if progress:
        progress(n, n)
    return stats


def _mp_context():
    """Prefer the ``fork`` start method.

    On macOS / Python 3.12+ the default is ``spawn``, which re-imports the entry
    module in each worker and crashes plain scripts that call ``simulate`` with
    ``workers > 1`` at top level. ``fork`` avoids the re-import entirely; we fall
    back to the platform default (e.g. on Windows, where fork is unavailable).
    """
    try:
        return multiprocessing.get_context("fork")
    except ValueError:
        return multiprocessing.get_context()


def default_workers():
    return max(1, (os.cpu_count() or 1))
