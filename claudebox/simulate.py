"""simulate.py — population cascade simulator (claudebox `simulate` layer).

Pure Python stdlib only. Token-free: no network access anywhere in this module.
Implements the independent-cascade (IC) population model of 01_CONTRACTS.md §1.3-1.5.

Usage:
    python3 simulate.py --config examples/config.yaml --beta examples/beta_placeholder.json
"""
from __future__ import annotations

import argparse
import hashlib
import random
import statistics
import sys
from typing import Any

from common import (
    PLACEHOLDER_BANNER,
    STOCHASTICITY_DISCLAIMER,
    config_hash,
    is_placeholder,
    load_beta_table,
    load_config,
    write_provenance_sidecar,
    write_sim_csv,
)

SOURCE_MODES = ("all_human", "all_orchestrator", "mixed")


# --------------------------------------------------------------------------
# Graph generators (§Task item 1) — hand-rolled, stdlib only.
# Represented as an adjacency list: list[set[int]] of length N.
# --------------------------------------------------------------------------

def er(N: int, k: int, seed: int) -> list[set[int]]:
    """Erdos-Renyi-ish graph with target mean degree k.

    Uses the G(N, p) construction with p = k / (N - 1), which gives an
    Erdos-Renyi graph whose *expected* mean degree is k. Hand-rolled: for
    each unordered pair (u, v) we flip a weighted coin.
    """
    rng = random.Random(seed)
    adj: list[set[int]] = [set() for _ in range(N)]
    if N <= 1:
        return adj
    p = min(1.0, max(0.0, k / (N - 1)))
    for u in range(N):
        for v in range(u + 1, N):
            if rng.random() < p:
                adj[u].add(v)
                adj[v].add(u)
    return adj


def smallworld(N: int, k: int, rewire_p: float, seed: int) -> list[set[int]]:
    """Watts-Strogatz-style ring lattice with rewiring probability rewire_p.

    Start from a ring where each node connects to k nearest neighbors
    (k//2 on each side, k made even by flooring), then rewire each edge
    with probability rewire_p to a random other node (avoiding self-loops
    and duplicate edges).
    """
    rng = random.Random(seed)
    adj: list[set[int]] = [set() for _ in range(N)]
    if N <= 1:
        return adj
    half_k = max(1, k // 2)
    # Build ring lattice: each node connects to half_k neighbors on each side.
    for u in range(N):
        for j in range(1, half_k + 1):
            v = (u + j) % N
            adj[u].add(v)
            adj[v].add(u)
    # Rewire: iterate over each original "forward" edge (u, u+j) and
    # rewire with probability rewire_p to a new random target.
    edges = []
    for u in range(N):
        for j in range(1, half_k + 1):
            v = (u + j) % N
            edges.append((u, v))
    for (u, v) in edges:
        if v not in adj[u]:
            continue  # already rewired away
        if rng.random() < rewire_p:
            adj[u].discard(v)
            adj[v].discard(u)
            # pick a new target w != u, not already a neighbor of u
            candidates = [w for w in range(N) if w != u and w not in adj[u]]
            if not candidates:
                # can't rewire, restore
                adj[u].add(v)
                adj[v].add(u)
                continue
            w = rng.choice(candidates)
            adj[u].add(w)
            adj[w].add(u)
    return adj


def build_graph(topology: str, N: int, k: int, rewire_p: float, seed: int) -> list[set[int]]:
    if topology == "er":
        return er(N, k, seed)
    if topology == "smallworld":
        return smallworld(N, k, rewire_p, seed)
    raise ValueError(f"unknown topology: {topology!r}")


# --------------------------------------------------------------------------
# beta lookup
# --------------------------------------------------------------------------

def _beta_value(beta_table: dict, hardening: str, source: str, dose: int) -> float:
    """Look up beta for (hardening, source) at exposure count `dose` (1-indexed
    per §1.3: d = number of distinct adopted neighbors who have already
    contacted v, and the d-th attempt uses beta_d). Arrays are indexed
    d=0..D; we clamp to the last entry if dose exceeds the measured curve
    length (nondecreasing dose-response, so this is the conservative,
    documented extrapolation)."""
    arr = beta_table["beta"][hardening][source]
    idx = min(dose, len(arr) - 1)
    idx = max(idx, 0)
    return arr[idx]


def _pick_source_label(source_mode: str, phi: float, rng: random.Random) -> str:
    if source_mode == "all_human":
        return "human"
    if source_mode == "all_orchestrator":
        return "orchestrator"
    if source_mode == "mixed":
        return "orchestrator" if rng.random() < phi else "human"
    raise ValueError(f"unknown source_mode: {source_mode!r}")


# --------------------------------------------------------------------------
# run_once — independent cascade, dose x one-shot-per-exposer (§1.3 AUDIT rule)
# --------------------------------------------------------------------------

def run_once(
    G: list[set[int]],
    rho: float,
    h: float,
    source_mode: str,
    phi: float,
    beta: dict,
    seed: int,
) -> tuple[float, int, int]:
    """Run one independent-cascade simulation on graph G.

    Returns (R, tau, cascade) where:
      R = final adopted fraction,
      tau = number of steps until saturation (no new adoptions),
      cascade = 1 if R >= R_macro else 0 (R_macro is NOT known here; the
        caller applies the R_macro threshold — run_once returns cascade
        using the default 0.5 threshold for convenience, but sweep()
        recomputes cascade against the configured R_macro).

    Dynamics (§1.3): at step t, each node adopted at t-1 makes ONE
    activation attempt on each not-yet-adopted neighbor v. Each attempt
    increments v's dose (number of distinct adopted neighbors that have
    attempted v) and succeeds w.p. beta[v.hardening, edge.source, d=dose].
    An exposer is spent after its attempts but stays adopted. Terminate
    when a step yields no new adoptions.
    """
    N = len(G)
    rng = random.Random(seed)

    hardened = [rng.random() < h for _ in range(N)]

    n_seed = int(rho * N)
    seed_nodes = set(rng.sample(range(N), n_seed)) if n_seed > 0 else set()

    adopted = [False] * N
    for s in seed_nodes:
        adopted[s] = True

    dose = [0] * N  # number of distinct adopted neighbors who have attempted this node

    frontier = set(seed_nodes)
    tau = 0
    total_nodes = N if N > 0 else 1

    while frontier:
        new_adopters: set[int] = set()
        for u in frontier:
            for v in G[u]:
                if adopted[v]:
                    continue
                dose[v] += 1
                d = dose[v]
                hardening_label = "hardened" if hardened[v] else "naive"
                source_label = _pick_source_label(source_mode, phi, rng)
                p = _beta_value(beta, hardening_label, source_label, d)
                if rng.random() < p:
                    new_adopters.add(v)
        if not new_adopters:
            break
        for v in new_adopters:
            adopted[v] = True
        frontier = new_adopters
        tau += 1

    R = sum(adopted) / total_nodes
    cascade = 1 if R >= 0.5 else 0
    return R, tau, cascade


# --------------------------------------------------------------------------
# sweep — Monte Carlo over rho_sweep x reps
# --------------------------------------------------------------------------

def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1


def sweep(config: dict, beta: dict) -> list[dict]:
    """Sweep rho_sweep x reps for the configured topology/source_mode.

    Returns one row per (rho, rep) with the §2.3 schema plus derived
    R0/cascade fields, ready for write_sim_csv (after dropping any extra
    keys the caller doesn't want in the CSV -- here we keep exactly the
    §2.3 columns).
    """
    topology = config["topology"]
    N = int(config["N"])
    k = int(config["k"])
    rewire_p = float(config.get("rewire_p", 0.0))
    h = float(config.get("h", 0.0))
    source_mode = config["source_mode"]
    phi = float(config.get("phi", 0.5))
    reps = int(config["reps"])
    R_macro = float(config.get("R_macro", 0.5))
    base_seed = int(config.get("seed", 0))
    rho_sweep = config["rho_sweep"]

    mean_beta = _mean_beta(beta)
    R0 = k * mean_beta

    rows: list[dict] = []
    for rho in rho_sweep:
        rho = float(rho)
        # Deterministic per-(rho, rep) seed derived from base_seed so the
        # whole sweep is reproducible given the same base seed.
        rho_key = repr(rho)
        for rep in range(reps):
            run_seed = _derive_seed(base_seed, rho_key, source_mode, rep)
            G = build_graph(topology, N, k, rewire_p, run_seed)
            R, tau, _ = run_once(G, rho, h, source_mode, phi, beta, run_seed)
            cascade = 1 if R >= R_macro else 0
            rows.append({
                "topology": topology,
                "N": N,
                "k": k,
                "rewire_p": rewire_p,
                "rho": rho,
                "h": h,
                "source_mode": source_mode,
                "phi": phi,
                "rep": rep,
                "seed": run_seed,
                "R": R,
                "tau": tau,
                "cascade": cascade,
                "R0": R0,
            })
    return rows


def _derive_seed(base_seed: int, *parts: Any) -> int:
    """Deterministically derive a per-run seed from the base seed and
    identifying parts (rho, source_mode, rep, ...), stable across runs
    and across Python processes.

    NOTE: builtin `hash()` on strings is randomized per-process (PYTHONHASHSEED
    salting) and must never be used here -- that would break run-to-run
    determinism despite a fixed seed. hashlib.sha256 is unsalted and stable.
    """
    key = "|".join(str(p) for p in (base_seed, *parts))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mean_beta(beta_table: dict) -> float:
    vals = []
    for hardening in ("naive", "hardened"):
        for source in ("human", "orchestrator"):
            vals.extend(beta_table["beta"][hardening][source])
    return statistics.mean(vals) if vals else 0.0


# --------------------------------------------------------------------------
# threshold — percolation threshold rho* via max dR/drho
# --------------------------------------------------------------------------

def threshold(rows: list[dict]) -> dict[str, Any]:
    """Locate the percolation threshold rho* from swept rows.

    Groups rows by rho, computes mean R (+ 90% percentile CI, per §1.5
    "report mean R + percentile CI") per rho, then finds rho* as the rho
    at the midpoint of the steepest dR/drho step (primary method), plus
    the smallest rho at which mean R first crosses R_macro (secondary /
    cross-check method, based on each row's own `cascade` flag which was
    computed against the configured R_macro in `sweep`).
    """
    by_rho: dict[float, list[float]] = {}
    for row in rows:
        by_rho.setdefault(float(row["rho"]), []).append(float(row["R"]))
    if not by_rho:
        return {
            "rho_star_maxslope": None, "rho_star_crossing": None,
            "mean_R_by_rho": {}, "ci_R_by_rho": {},
        }

    rhos = sorted(by_rho.keys())
    mean_R = {rho: statistics.mean(by_rho[rho]) for rho in rhos}
    ci_R = {
        rho: (_percentile(sorted(by_rho[rho]), 0.05), _percentile(sorted(by_rho[rho]), 0.95))
        for rho in rhos
    }

    rho_star_maxslope = None
    if len(rhos) >= 2:
        best_slope = None
        best_mid = None
        for i in range(1, len(rhos)):
            r0, r1 = rhos[i - 1], rhos[i]
            if r1 == r0:
                continue
            slope = (mean_R[r1] - mean_R[r0]) / (r1 - r0)
            if best_slope is None or slope > best_slope:
                best_slope = slope
                best_mid = (r0 + r1) / 2
        rho_star_maxslope = best_mid

    # cascade-crossing rows carry their own R_macro-based cascade flag; use
    # majority cascade==1 at a given rho as the crossing signal.
    by_rho_cascade: dict[float, list[int]] = {}
    for row in rows:
        by_rho_cascade.setdefault(float(row["rho"]), []).append(int(row["cascade"]))
    rho_star_crossing = None
    for rho in rhos:
        frac_cascade = statistics.mean(by_rho_cascade[rho])
        if frac_cascade >= 0.5:
            rho_star_crossing = rho
            break

    return {
        "rho_star_maxslope": rho_star_maxslope,
        "rho_star_crossing": rho_star_crossing,
        "mean_R_by_rho": mean_R,
        "ci_R_by_rho": ci_R,
    }


# --------------------------------------------------------------------------
# CLI / reporting
# --------------------------------------------------------------------------

def _fmt(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:.4f}"
    return str(x)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="claudebox population cascade simulator (token-free).")
    parser.add_argument("--config", required=True, help="path to config.yaml or config.json (§2.4)")
    parser.add_argument("--beta", required=True, help="path to beta.json (§2.2)")
    parser.add_argument("--out", default="sim_results.csv", help="output CSV path (default sim_results.csv)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    beta_table = load_beta_table(args.beta)
    placeholder = is_placeholder(beta_table)

    print(STOCHASTICITY_DISCLAIMER)
    print()
    if placeholder:
        print(PLACEHOLDER_BANNER)
        print()

    seed = int(config.get("seed", 0))
    print(f"config_hash={config_hash(config)}  seed={seed}")
    print()

    rows = sweep(config, beta_table)
    # Honesty rails: every results row is tagged PLACEHOLDER when beta is a
    # placeholder. The fixed §2.3 CSV schema has no PLACEHOLDER column, so
    # the durable structured tag lives in the provenance sidecar (written
    # below) and is additionally surfaced via the loud console banners.

    write_sim_csv(args.out, rows)
    write_provenance_sidecar(
        args.out, config, seed, "simulate.py v1",
        extra={"beta_placeholder": placeholder, "PLACEHOLDER": placeholder},
    )

    R0 = rows[0]["R0"] if rows else float("nan")
    mean_beta = _mean_beta(beta_table)
    k = config["k"]

    thr = threshold(rows)

    print(f"Topology={config['topology']} N={config['N']} k={k} h={config.get('h', 0.0)} "
          f"source_mode={config['source_mode']} reps={config['reps']}")
    r0_gt1 = R0 > 1
    R_macro = float(config.get("R_macro", 0.5))
    print(f"R0 analytic anchor = k * mean(beta) = {k} * {mean_beta:.4f} = {R0:.4f}  "
          f"(R0 > 1 => {r0_gt1})")
    print("R0 is a rho-independent mean-field anchor (§1.5 AUDIT); it is most diagnostic "
          "near the percolation threshold. Per-row flags below compare sign(R0>1) against "
          "sign(R>=R_macro) at each swept rho -- mismatches far from threshold are EXPECTED "
          "(seeding alone can push R>=R_macro at high rho regardless of R0) and are not "
          "evidence of a broken simulator by themselves; persistent mismatch AT/NEAR rho* is.")
    print()
    print(f"{'rho':>8} {'mean_R':>10} {'R_90%CI':>17} {'R0':>8} {'cascade_frac':>13} {'R0>1':>6} {'flag':>10}")
    for rho in sorted(thr["mean_R_by_rho"].keys()):
        mean_r = thr["mean_R_by_rho"][rho]
        lo, hi = thr["ci_R_by_rho"][rho]
        cascade_rows = [r for r in rows if float(r["rho"]) == rho]
        cascade_frac = sum(r["cascade"] for r in cascade_rows) / len(cascade_rows)
        empirical_cascade = mean_r >= R_macro
        flag = "" if r0_gt1 == empirical_cascade else "mismatch"
        ci_str = f"[{lo:.4f},{hi:.4f}]"
        print(f"{rho:>8.4f} {mean_r:>10.4f} {ci_str:>17} {R0:>8.4f} {cascade_frac:>13.4f} {str(r0_gt1):>6} {flag:>10}")

    print()
    print(f"Percolation threshold rho* (max dR/drho) = {_fmt(thr['rho_star_maxslope'])}")
    print(f"Percolation threshold rho* (R>=R_macro crossing) = {_fmt(thr['rho_star_crossing'])}")

    # Headline: source gap Delta rho* between all_human and all_orchestrator.
    # The configured sweep only covers config['source_mode']; to always be
    # able to report the headline we additionally sweep the two canonical
    # single-source modes (cheap: pure stdlib, seconds) unless the config's
    # own source_mode already is one of them, in which case we reuse it and
    # only need to additionally compute the other.
    print()
    print("Headline: source gap (Delta rho* = rho*_human - rho*_orchestrator)")
    gap_rows: dict[str, list[dict]] = {}
    for mode in ("all_human", "all_orchestrator"):
        if mode == config["source_mode"]:
            gap_rows[mode] = rows
        else:
            alt_config = dict(config)
            alt_config["source_mode"] = mode
            gap_rows[mode] = sweep(alt_config, beta_table)
    thr_human = threshold(gap_rows["all_human"])
    thr_orch = threshold(gap_rows["all_orchestrator"])
    rho_h = thr_human["rho_star_crossing"]
    rho_o = thr_orch["rho_star_crossing"]
    if rho_h is not None and rho_o is not None:
        delta = rho_h - rho_o
        print(f"  rho*_human={_fmt(rho_h)}  rho*_orchestrator={_fmt(rho_o)}  "
              f"Delta rho* = {_fmt(delta)}")
    else:
        print(f"  rho*_human={_fmt(rho_h)}  rho*_orchestrator={_fmt(rho_o)}  "
              f"(no rho in sweep crossed R_macro for one or both modes; "
              f"widen rho_sweep to compute Delta rho*)")

    if placeholder:
        print()
        print(PLACEHOLDER_BANNER)
        print("ALL ROWS ABOVE ARE PLACEHOLDER-DERIVED. Do not present as measured.")

    print()
    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
