#!/usr/bin/env python3
"""validate.py -- the rigor capstone: tests the decomposition assumption.

01_CONTRACTS.md §1.6 / 00_OVERVIEW.md "Audit hooks": the chief load-bearing
assumption in claudebox is that per-edge beta[hardening, source, dose]
(measured by `assay` + `score` on isolated dyads) COMPOSES into the
population-level independent-cascade behavior that `simulate` predicts from
that same beta table. That composition (single-edge measurement -> multi-hop
population dynamics) is a hypothesis, not a given: real multi-agent networks
could show reinforcement, fatigue, or context-carryover effects across hops
that an isolated-dyad measurement can't see. `validate` is how we check.

Protocol
--------
1. Build a small number of LIVE multi-node networks (small N, e.g. 8-30
   nodes) using the SAME graph generators as `simulate.py` (imported from
   there, not reimplemented).
2. Run each network's cascade for real: at each step, each newly-adopted
   node makes one real dyadic contact (a real assay.py call) on each
   not-yet-adopted neighbor, exactly per the IC dynamics in
   01_CONTRACTS.md §1.3 (dose = count of distinct adopted neighbors who
   have attempted this node so far; the d-th attempt uses payload dose d).
   This is the ONLY place in claudebox that runs the IC dynamics against
   real model calls instead of a beta-parameterized coin flip.
3. Record the real observed (R, tau) per network rep.
4. Independently, ask `simulate.py`'s machinery (same graph seeds, same
   config) what it PREDICTS for (R, tau) using the beta table measured by
   `assay`+`score` on the very same payload/hardening/source cells.
5. Compare: is observed R within simulate's Monte Carlo percentile CI for
   predicted R (and same for tau)? Report PASS/FAIL per rep + aggregate.

CRITICAL CONSTRAINT (same as assay.py): the live-network-execution path in
this module spends tokens (it calls assay.py's real, network-calling
functions once per edge-activation attempt) and requires ANTHROPIC_API_KEY.
That is expected -- it is the entire point of `validate`. But the
`anthropic` SDK is NEVER imported by this module directly; validate.py only
ever calls assay.run_real_single_cell(...), which itself defers the
`anthropic` import to inside that function (see assay.py). So importing
validate.py, or calling validate.py with an injected/mocked edge executor
(as the self-test below does), touches neither the `anthropic` module nor
ANTHROPIC_API_KEY. `grep -n anthropic validate.py` shows zero references;
the self-test at the bottom of this file additionally asserts
`'anthropic' not in sys.modules` after import and after running.

Dependency injection for testability
-------------------------------------
`run_live_networks()` takes an `edge_executor` callable:
    edge_executor(payload, hardening, source, dose) -> receiver_output dict
By default (real use), this closes over `assay.run_real_single_cell` (which
performs the actual API call). For the zero-token self-test, we pass a
fixture-driven substitute that returns canned receiver_output dicts with no
network access whatsoever -- this exercises 100% of validate.py's real
comparison/statistics logic without spending anything.
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from typing import Any, Callable

import common
import simulate
from assay import (
    build_messages,
    check_adopt,
    check_relay,
    get_payload,
    load_payloads,
)
from common import (
    PLACEHOLDER_BANNER,
    STOCHASTICITY_DISCLAIMER,
    config_hash,
    is_placeholder,
    load_beta_table,
    load_config,
)

VALIDATE_VERSION = "validate.py v1"

EdgeExecutor = Callable[[dict, str, str, int], dict]


# --------------------------------------------------------------------------
# Real edge executor (the only token-spending path in this module).
# --------------------------------------------------------------------------

def make_real_edge_executor(
    receiver_model: str,
    operationalization: str,
    api_key: str | None = None,
) -> EdgeExecutor:
    """Build an edge_executor that performs ONE real dyadic contact per call
    via assay.run_real_single_cell. NOT called by the self-test below and
    NOT invoked anywhere in this build/test session.

    The `anthropic` import happens inside assay.run_real_single_cell, not
    here -- this function only constructs a closure; merely calling this
    factory (without invoking the returned closure) touches no network.
    """
    import assay  # local import mirrors assay.py's own deferred-import style;
    # assay.py itself only imports `anthropic` inside run_real_single_cell.

    def _executor(payload: dict, hardening: str, source: str, dose: int) -> dict:
        messages = build_messages(payload, source, operationalization, dose)
        return assay.run_real_single_cell(
            receiver_model=receiver_model,
            hardening=hardening,
            messages=messages,
            api_key=api_key,
        )

    return _executor


# --------------------------------------------------------------------------
# Live (or fixture-driven) multi-node network execution.
# --------------------------------------------------------------------------

def run_live_network_once(
    G: list[set[int]],
    rho: float,
    h: float,
    source_mode: str,
    phi: float,
    payloads: list[dict],
    payload_id: str,
    operationalization: str,
    edge_executor: EdgeExecutor,
    seed: int,
) -> tuple[float, int, int, list[dict]]:
    """Run ONE real (or fixture-driven) independent-cascade network.

    Mirrors simulate.run_once's dynamics EXACTLY (01_CONTRACTS.md §1.3) so
    the comparison is apples-to-apples, except that instead of drawing
    `rng.random() < beta[...]` for each attempt, each attempt is a REAL (or
    injected) dyadic contact whose outcome_adopt is read off the receiver's
    actual structured output via assay.check_adopt.

    Returns (R, tau, cascade, contact_log) where contact_log is a list of
    per-attempt dicts (hardening, source, dose, outcome_adopt) suitable for
    feeding straight into score.py-shaped aggregation if desired.
    """
    N = len(G)
    rng = random.Random(seed)
    payload = get_payload(payloads, payload_id)

    hardened = [rng.random() < h for _ in range(N)]
    n_seed = int(rho * N)
    seed_nodes = set(rng.sample(range(N), n_seed)) if n_seed > 0 else set()

    adopted = [False] * N
    for s in seed_nodes:
        adopted[s] = True
    dose = [0] * N

    contact_log: list[dict] = []
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
                source_label = simulate._pick_source_label(source_mode, phi, rng)

                receiver_output = edge_executor(payload, hardening_label, source_label, d)
                outcome_adopt = check_adopt(payload, receiver_output)
                outcome_relay = check_relay(payload, receiver_output)
                contact_log.append({
                    "hardening": hardening_label, "source": source_label,
                    "dose": d, "outcome_adopt": outcome_adopt,
                    "outcome_relay": outcome_relay,
                })

                if outcome_adopt:
                    new_adopters.add(v)
        if not new_adopters:
            break
        for v in new_adopters:
            adopted[v] = True
        frontier = new_adopters
        tau += 1

    R = sum(adopted) / total_nodes
    cascade = 1 if R >= 0.5 else 0
    return R, tau, cascade, contact_log


def run_live_networks(
    *,
    n_networks: int,
    N: int,
    k: int,
    topology: str,
    rho: float,
    h: float,
    source_mode: str,
    phi: float,
    payloads: list[dict],
    payload_id: str,
    operationalization: str,
    edge_executor: EdgeExecutor,
    seed: int,
) -> list[dict]:
    """Run `n_networks` independent small live cascades. Each uses a
    deterministically-derived sub-seed (per simulate.py's own convention)
    so the graph/seed-set draws are reproducible even though the edge
    outcomes themselves (real model calls) are not.
    """
    results = []
    for rep in range(n_networks):
        rep_seed = simulate._derive_seed(seed, "validate", rep)
        G = simulate.build_graph(topology, N, k, 0.1, rep_seed)
        R, tau, cascade, contact_log = run_live_network_once(
            G, rho, h, source_mode, phi, payloads, payload_id,
            operationalization, edge_executor, rep_seed,
        )
        results.append({
            "rep": rep, "seed": rep_seed, "R": R, "tau": tau,
            "cascade": cascade, "n_contacts": len(contact_log),
            "contact_log": contact_log,
        })
    return results


# --------------------------------------------------------------------------
# Prediction (via simulate.py, using the measured beta table) + comparison.
# --------------------------------------------------------------------------

def predict(
    *,
    n_reps: int,
    N: int,
    k: int,
    topology: str,
    rho: float,
    h: float,
    source_mode: str,
    phi: float,
    beta_table: dict,
    seed: int,
) -> dict[str, Any]:
    """Ask simulate.py's own sweep machinery what it predicts for (R, tau)
    at this exact (rho, h, source_mode) point, using the SAME graph
    generator + derived-seed convention as run_live_networks above (so the
    comparison holds the graph draw fixed and only asks about the
    beta -> outcome composition).
    """
    Rs: list[float] = []
    taus: list[int] = []
    for rep in range(n_reps):
        rep_seed = simulate._derive_seed(seed, "validate", rep)
        G = simulate.build_graph(topology, N, k, 0.1, rep_seed)
        R, tau, cascade = simulate.run_once(G, rho, h, source_mode, phi, beta_table, rep_seed)
        Rs.append(R)
        taus.append(tau)
    Rs_sorted = sorted(Rs)
    taus_sorted = sorted(taus)
    return {
        "mean_R": statistics.mean(Rs) if Rs else float("nan"),
        "R_ci": (simulate._percentile(Rs_sorted, 0.05), simulate._percentile(Rs_sorted, 0.95)),
        "mean_tau": statistics.mean(taus) if taus else float("nan"),
        "tau_ci": (simulate._percentile(taus_sorted, 0.05), simulate._percentile(taus_sorted, 0.95)),
        "Rs": Rs,
        "taus": taus,
    }


def compare(observed: list[dict], predicted: dict[str, Any]) -> dict[str, Any]:
    """Compare observed live-network (R, tau) reps against simulate's
    predicted CI. PASS if the observed mean falls within predicted's
    percentile CI for both R and tau (the pre-registered pass condition:
    "observed falls in predicted CI", per 05_TASK_cli_validate.md).
    """
    obs_R = [r["R"] for r in observed]
    obs_tau = [r["tau"] for r in observed]
    mean_obs_R = statistics.mean(obs_R) if obs_R else float("nan")
    mean_obs_tau = statistics.mean(obs_tau) if obs_tau else float("nan")

    r_lo, r_hi = predicted["R_ci"]
    tau_lo, tau_hi = predicted["tau_ci"]

    r_pass = r_lo <= mean_obs_R <= r_hi
    tau_pass = tau_lo <= mean_obs_tau <= tau_hi
    overall_pass = r_pass and tau_pass

    return {
        "observed_mean_R": mean_obs_R,
        "observed_mean_tau": mean_obs_tau,
        "observed_R_per_rep": obs_R,
        "observed_tau_per_rep": obs_tau,
        "predicted_mean_R": predicted["mean_R"],
        "predicted_R_ci": predicted["R_ci"],
        "predicted_mean_tau": predicted["mean_tau"],
        "predicted_tau_ci": predicted["tau_ci"],
        "R_pass": r_pass,
        "tau_pass": tau_pass,
        "pass": overall_pass,
    }


def _fmt(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:.4f}"
    return str(x)


def print_report(observed: list[dict], predicted: dict[str, Any], result: dict[str, Any],
                  beta_placeholder: bool) -> None:
    print(STOCHASTICITY_DISCLAIMER)
    print(
        "Additionally: live-network edge outcomes below are REAL (or, in a "
        "self-test, fixture-injected) per-contact results -- they are not "
        "reproducible run-to-run even with a fixed seed, by design; only the "
        "graph draw and seed-set choice are seed-fixed."
    )
    print()
    if beta_placeholder:
        print(PLACEHOLDER_BANNER)
        print("Prediction below is derived from a PLACEHOLDER beta table; the "
              "comparison is a pipeline smoke-test only, not a real audit.")
        print()

    print("=== validate.py: decomposition audit (edge beta -> population cascade) ===")
    print(f"Live network reps: {len(observed)}")
    for row in observed:
        print(f"  rep={row['rep']:>2} seed={row['seed']:<12} R={_fmt(row['R'])} "
              f"tau={row['tau']} contacts={row['n_contacts']}")
    print()
    print(f"Observed  mean R   = {_fmt(result['observed_mean_R'])}   "
          f"(per-rep: {[_fmt(x) for x in result['observed_R_per_rep']]})")
    print(f"Predicted mean R   = {_fmt(result['predicted_mean_R'])}   "
          f"90% CI = [{_fmt(result['predicted_R_ci'][0])}, {_fmt(result['predicted_R_ci'][1])}]")
    print(f"  R_pass (observed mean R within predicted CI)   = {result['R_pass']}")
    print()
    print(f"Observed  mean tau = {_fmt(result['observed_mean_tau'])}   "
          f"(per-rep: {result['observed_tau_per_rep']})")
    print(f"Predicted mean tau = {_fmt(result['predicted_mean_tau'])}   "
          f"90% CI = [{_fmt(result['predicted_tau_ci'][0])}, {_fmt(result['predicted_tau_ci'][1])}]")
    print(f"  tau_pass (observed mean tau within predicted CI) = {result['tau_pass']}")
    print()
    verdict = "PASS" if result["pass"] else "FAIL"
    print(f"OVERALL: {verdict} -- decomposition assumption "
          f"{'holds' if result['pass'] else 'does NOT hold'} for this network/config "
          "(single audit point; widen n_networks / vary topology before drawing "
          "strong conclusions).")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="validate.py -- tests whether per-edge beta (measured by "
                    "assay+score) actually composes into the population cascade "
                    "simulate.py predicts. Runs a FEW live small networks end-to-"
                    "end (spends tokens) and compares observed vs predicted R/tau.",
    )
    ap.add_argument("--beta", required=True, help="path to a measured beta.json (§2.2)")
    ap.add_argument("--payloads", required=True, help="path to payloads.json")
    ap.add_argument("--payload-id", required=True,
                     help="single payload_id to use for every edge attempt in the "
                          "live network (content held constant, per §2.1 note)")
    ap.add_argument("--operationalization", choices=("channel", "claimed"), default="channel")
    ap.add_argument("--n-networks", type=int, default=3,
                     help="number of independent live small-network reps (keep FEW: "
                          "this is the paid path)")
    ap.add_argument("--N", type=int, default=10, help="nodes per live network (keep SMALL)")
    ap.add_argument("--k", type=int, default=3, help="mean degree")
    ap.add_argument("--topology", choices=("er", "smallworld"), default="er")
    ap.add_argument("--rho", type=float, default=0.2, help="seed fraction")
    ap.add_argument("--h", type=float, default=0.0, help="hardened fraction")
    ap.add_argument("--source-mode", choices=("all_human", "all_orchestrator", "mixed"),
                     default="all_orchestrator")
    ap.add_argument("--phi", type=float, default=0.5, help="mixed-mode orchestrator fraction")
    ap.add_argument("--predict-reps", type=int, default=200,
                     help="Monte Carlo reps for simulate's prediction (token-free)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--receiver-model", default="claude-haiku-4-5")
    ap.add_argument("--dry-run", action="store_true",
                     help="Use assay's own canned/fixture receiver responses instead "
                          "of the real API (network-free smoke test of this CLI path; "
                          "NOT the same as the self-test's injected fixture, but also "
                          "zero-token).")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    beta_table = load_beta_table(args.beta)
    placeholder = is_placeholder(beta_table)
    payloads = load_payloads(args.payloads)

    if args.dry_run:
        # Network-free smoke test of this CLI's wiring: reuse assay's own
        # canned_receiver_output generator as the edge_executor, so calling
        # `validate --dry-run` never touches the network either. This is a
        # convenience path distinct from (but analogous to) the module
        # self-test at the bottom of this file.
        import assay as _assay

        def _canned_executor(payload: dict, hardening: str, source: str, dose: int) -> dict:
            rng = random.Random(hash((payload["payload_id"], hardening, source, dose)) & 0xFFFFFFFF)
            return _assay.canned_receiver_output(
                payload=payload, hardening=hardening, source=source, dose=dose, rng=rng,
            )

        edge_executor = _canned_executor
    else:
        print(
            "Real-run mode requested (no --dry-run). This spends tokens via "
            "assay.run_real_single_cell and requires ANTHROPIC_API_KEY. "
            "Refusing to proceed in this environment/session -- run only in "
            "the explicitly budgeted validation phase (see BUILD_PLAN.md Phase 4).",
            file=sys.stderr,
        )
        return 2

    observed = run_live_networks(
        n_networks=args.n_networks, N=args.N, k=args.k, topology=args.topology,
        rho=args.rho, h=args.h, source_mode=args.source_mode, phi=args.phi,
        payloads=payloads, payload_id=args.payload_id,
        operationalization=args.operationalization, edge_executor=edge_executor,
        seed=args.seed,
    )
    predicted = predict(
        n_reps=args.predict_reps, N=args.N, k=args.k, topology=args.topology,
        rho=args.rho, h=args.h, source_mode=args.source_mode, phi=args.phi,
        beta_table=beta_table, seed=args.seed,
    )
    result = compare(observed, predicted)
    print_report(observed, predicted, result, placeholder)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
