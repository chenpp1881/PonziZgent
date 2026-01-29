# -*- coding: utf-8 -*-
from z3 import *
from typing import Dict, Any, List
from .i_registry import InvariantResult

def _get_param(d: Dict[str, Any], key: str, default=0.0):
    try:
        return float(d.get(key, default))
    except Exception:
        return default

def _bool_from_predicate(expr: str):
    e = (expr or "").lower()
    if "onlyowner" in e:
        return True
    if "require" in e and ("owner" in e or "whitelist" in e or "timelock" in e):
        return True
    return False

def invariant_I1(mech: Dict[str, Any]) -> InvariantResult:
    """
    I1: Absence of external profit; reward for old participants relies on new deposits.
    SAT check:
      - Under external_profit(t)=0, there is NO solution with deposit_new==0 and reward_old>0,
        but there EXISTS a solution with deposit_new>0 and reward_old>0.
    """
    alpha = 0.0
    beta = 0.0
    fee_min = 0.0

    for eq in mech.get("equations", []):
        if (eq.get("lhs","") or "").startswith("reward"):
            params = eq.get("params",{}) or {}
            alpha = _get_param(params, "alpha", alpha)
            beta  = _get_param(params, "beta", beta)

    s_no = Solver()
    d = Real('deposit_new')
    r = Real('reward_old')
    fee = Real('fee')
    pool_t = Real('pool_t')
    ext = Real('external_profit')
    s_no.add(ext == 0, d == 0, fee >= fee_min, pool_t >= 0)
    s_no.add(r == alpha*d + beta*pool_t - fee, r > 0)

    s_yes = Solver()
    d2 = Real('deposit_new2')
    r2 = Real('reward_old2')
    fee2 = Real('fee2')
    pool_t2 = Real('pool_t2')
    ext2 = Real('external_profit2')
    s_yes.add(ext2 == 0, d2 > 0, fee2 >= fee_min, pool_t2 >= 0)
    s_yes.add(r2 == alpha*d2 + beta*pool_t2 - fee2, r2 > 0)

    sat_no = s_no.check() == sat
    sat_yes = s_yes.check() == sat

    satisfied = (not sat_no) and sat_yes

    cert = {
        "alpha": alpha, "beta": beta,
        "no_new_deposit_sat": sat_no,
        "with_new_deposit_sat": sat_yes,
        "witness_with_new": str(s_yes.model()) if sat_yes else None
    }
    return InvariantResult("I1", satisfied, cert)

def invariant_I2(mech: Dict[str, Any]) -> InvariantResult:
    """
    I2: Withdrawal blocking/constraints (owner-only, timelock, gating).
    """
    blocked = False
    witnesses: List[Dict[str,Any]] = []
    for pred in mech.get("predicates", []) or []:
        name = (pred.get("name","") or "").lower()
        expr = pred.get("expr","") or ""
        if "withdraw" in name or "withdraw" in expr:
            if _bool_from_predicate(expr):
                blocked = True
                witnesses.extend(pred.get("code_witness", []) or [])
    cert = {"blocked": blocked, "witnesses": witnesses}
    return InvariantResult("I2", blocked, cert)

def invariant_I3(mech: Dict[str, Any]) -> InvariantResult:
    """
    I3: Early investor net gain non-decreasing with more new participants (or more referrals).
    Uses reward alpha>=0, depends_on flags, and referral rho>=0 evidence.
    """
    a = None
    depends = {}
    rho_list = []

    for eq in mech.get("equations", []) or []:
        if (eq.get("lhs","") or "").startswith("reward"):
            params = eq.get("params",{}) or {}
            if "alpha" in params:
                try:
                    a = float(params["alpha"])
                except Exception:
                    a = None
            depends = eq.get("depends_on",{}) or {}
            break

    for req in mech.get("referral_equations", []) or []:
        params = req.get("params",{}) or {}
        if "rho" in params:
            try:
                rho_list.append(float(params["rho"]))
            except Exception:
                pass

    cond = False
    if a is not None and a >= 0:
        cond = True
    if depends.get("n_new") or depends.get("deposit_new") or depends.get("referrals"):
        cond = True
    if any(rho >= 0 for rho in rho_list):
        cond = True

    cert = {"alpha": a, "depends_on": depends, "rho_samples": rho_list}
    return InvariantResult("I3", bool(cond), cert)

def invariant_I4(mech: Dict[str, Any]) -> InvariantResult:
    """
    I4: Withdrawal ORDERING tied to join-time/position.
    Evidence:
      - predicates like "msg.sender==previousOwner" or "msg.sender==owners[head]" or "position[msg.sender]==head"
      - ordering_relations with kind queue/head/index/previousOwner
    Z3 sketch: model two users early (pos=0) and late (pos=1); policy withdraw_allowed(u) <=> position[u]==head.
               Show a state where early allowed and late not allowed.
    """
    order_pred_found = False
    witnesses: List[Dict[str,Any]] = []

    for pred in mech.get("predicates", []) or []:
        expr = (pred.get("expr","") or "").replace(" ", "").lower()
        if any(k in expr for k in [
            "msg.sender==previousowner",
            "msg.sender==owners[head]",
            "position[msg.sender]==head",
            "queue[head]==msg.sender"
        ]):
            order_pred_found = True
            witnesses.extend(pred.get("code_witness", []) or [])

    if not order_pred_found:
        for o in mech.get("ordering_relations", []) or []:
            expr = (o.get("expr","") or "").replace(" ", "").lower()
            if any(k in expr for k in ["previousowner","owners[head]","position[","queue","head"]):
                order_pred_found = True
                witnesses.extend(o.get("code_witness", []) or [])

    if not order_pred_found:
        return InvariantResult("I4", False, {"reason":"no ordering predicates/relations found"})

    # Minimal Z3 model
    pos_early = Int('pos_early')
    pos_late  = Int('pos_late')
    head      = Int('head')

    s = Solver()
    s.add(pos_early == 0, pos_late == 1)  # early joins first
    s.add(head == 0)  # withdraw pointer at earliest not-yet-withdrawn
    withdraw_early = (pos_early == head)
    withdraw_late  = (pos_late == head)
    s.add(withdraw_early, Not(withdraw_late))

    sat = (s.check() == sat)
    cert = {
        "model_sat": sat,
        "assumed_policy": "withdraw_allowed(user) <=> position[user]==head",
        "witnesses": witnesses
    }
    return InvariantResult("I4", bool(sat), cert)
