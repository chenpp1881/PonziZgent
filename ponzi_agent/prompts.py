# -*- coding: utf-8 -*-
# new
EQUATION_EXTRACTION_SYSTEM = """
You translate Solidity economic logic into machine-checkable equations and predicates.
Return ONLY valid JSON. No explanations. No chain-of-thought.
All symbols must be defined. Every equation must include code_witness with line numbers.
"""

EQUATION_EXTRACTION_USER_TEMPLATE = """
You are given a Solidity contract with line numbers. Extract a machine-checkable mechanism spec.

Return a JSON object with keys:
- variables: list of objects {name, kind (pool|balance|mapping|param|const|state|counter|price|reward|fee|referral_var|order_var),
 type (int|uint|real|address|mapping|array), unit (wei|ETH|none), decl {file,line,snippet}}
- equations: list of objects {
   lhs (e.g., "pool(t+1)", "reward_old(t)", "ref_reward(referrer,t)"),
   rhs (string expression using symbols),
   params (dict of scalars, optional),
   depends_on (dict like {"n_new": true/false, "deposit_new": true/false, "referrals": true/false, "ordering": true/false}, optional),
   code_witness: [{file,line,snippet}]
}
- predicates: list of {name, expr (boolean over symbols), code_witness:[...]}
- referral_relations: list of {map_name, assign_pattern, code_witness:[{file,line,snippet}]}
- referral_equations: list of objects {
   lhs ("ref_reward(referrer,t)" or "invitees(referrer,t+1)"),
   rhs (e.g., "rho * deposit_new(invitee,t)"),
   params (e.g., {"rho":0.05}),
   code_witness:[...]
}
- ordering_relations: list of objects {
   kind: "queue|previousOwner|indexMap|headPtr|rank",
   expr: string (e.g., "position[user]=k", "user==owners[head]", "msg.sender==previousOwner"),
   code_witness:[{file,line,snippet}]
}
- assumptions: list of {name, expr, justification}
- notes: optional list of short strings.

Constraints and guidance:
1) Identify money-related identifiers (pool, balance, price, reward, fee, deposit_new, payout_old, previousOwner, owner, msg.value).
2) Explicitly extract REFERRAL logic if present:
  - mapping writes like ref[invitee]=referrer; arrays of uplines/downlines; events with (referrer,invitee);
  - any commission/bonus to referrer tied to invitee deposits -> encode as ref_reward(referrer,t) = rho * deposit_new(invitee,t).
  - mark depends_on["referrals"]=true when reward depends on referrals.
3) Explicitly extract WITHDRAWAL ORDERING if present (I4 evidence):
  - variables like previousOwner, owners[], queue/head, position/index maps.
  - predicates constraining withdrawal such as "msg.sender==previousOwner", "msg.sender==owners[head]",
    "position[msg.sender]==head", or conditions tying withdrawal rights to join order.
  - mark depends_on["ordering"]=true when reward/withdraw depends on order.
4) Equations should be affine/linearized where possible. Encode price escalations like p*125/100 as "price := price * (1+gamma)" with params {"gamma":0.25}.
5) If no external profit source is present (no DEX/oracle/strategy), set external_profit(t)=0 via assumptions.
6) Every equation/predicate/referral/ordering item must include code_witness with {file,line,snippet}.
7) If a symbol appears anywhere but not in variables, you MUST add it to variables with best-effort type/kind.

Contract ID: {contract_id}

CODE:
{code_with_line_numbers}
"""

FINAL_PONZI_DECISION_SYSTEM = """
You are a rigorous auditor. Output ONLY JSON with a final decision about Ponzi risk.
No prose. No chain-of-thought. Base strictly on provided evidence and definitions.
"""

FINAL_PONZI_DECISION_USER_TEMPLATE = """
You will receive:
(1) The original Solidity code (with line numbers).
(2) A mechanism spec JSON (variables/equations/predicates/assumptions/referral/ordering) extracted from the code.
(3) Results of invariant checks I1, I2, I3, I4 (with certificates).

Goal: Output a SINGLE JSON object with keys:
- decision: one of ["Ponzi","Non-Ponzi"]
- justification: short bullet-style strings citing concrete evidence and line numbers
- relied_invariants: subset of ["I1","I2","I3","I4"]
- risk_factors: list of strings (e.g., "price escalation", "owner-only-withdraw", "reward depends on new deposits", "withdrawal ordering by join-time")
- contradictions: list of strings if evidence conflicts

Definition hints (do not copy, you must reason):
- Ponzi characteristics include 1. prior participants' rewards directly/indirectly funded by later participants; 2. referral-based growth linking earlier net gains to new participants; and 3. withdrawal ORDERING where earlier joiners can withdraw before later joiners, and later joiners cannot withdraw until earlier ones have withdrawn or been paid.
- Non-Ponzi evidence includes 1. sustainable external revenues not derived from later participants, or 2. early investors can withdraw without additional new participants. 3. any system in which rewards are probabilistic (e.g., lotteries, jackpots, random draws) rather than deterministic, or in which payouts are event-based and independent of participant order or referral hierarchy, qualifies as non-Ponzi. Random or game-like redistributions are not Ponzi schemes, even if new deposits fund the rewards.

You need to compare the contract against each Non-Ponzi evidence one by one.
Attention, classify the contract as Ponzi only if none of the Non-Ponzi evidence are present.

Now produce the JSON decision using ONLY the evidence I provide.

Inputs:
<<CODE>>
{code_with_line_numbers}
<</CODE>>

<<MECHANISM_SPEC>>
{mechanism_json}
<</MECHANISM_SPEC>>

<<INVARIANTS>>
{invariants_result_json}
<</INVARIANTS>>
"""

FINAL_PONZI_DECISION_USER_TEMPLATE_LEAN = """
You will receive:
(1) The original Solidity code (with line numbers).
(2) A mechanism spec JSON (variables/equations/predicates/assumptions/referral/ordering) extracted from the code.
(3) Results of invariant checks I1, I2, I3, I4 (with certificates).

Goal: Output a SINGLE JSON object with keys:
- decision: one of ["Ponzi","Non-Ponzi"]
- justification: short bullet-style strings citing concrete evidence and line numbers
- relied_invariants: subset of ["I1","I2","I3","I4"]
- risk_factors: list of strings (e.g., "price escalation", "owner-only-withdraw", "reward depends on new deposits", "withdrawal ordering by join-time")
- contradictions: list of strings if evidence conflicts
- require_human_review: true/false

Definition hints (do not copy, you must reason):

Ponzi characteristics include:
1. Absence of external profit sources — no sustainable revenue from external trading, staking, investment, or protocol operations.
2. Rewards or payouts to prior participants are directly or indirectly funded by later participants’ deposits. 
3. Withdrawal ORDERING where earlier joiners can withdraw before later ones, or later joiners must wait for earlier ones to be paid.


Non-Ponzi evidence includes:
1. Sustainable external revenues not derived from later participants’ deposits.
2. Early investors can withdraw or claim rewards independently without new participants joining.
3. Rewards are probabilistic, event-driven, or based on random redistributions (lotteries, jackpots, insurance pools).
4. Withdrawals are open. No explicit or implicit withdrawal ordering mechanism.
5. Withdrawals may be controlled or restricted, but the withdrawal order is independent of participant join order, or later participants can withdraw before earlier ones.

You need to compare the contract against each Non-Ponzi evidence one by one.
Attention, classify the contract as Ponzi only if none of the Non-Ponzi evidence are present.

Now produce the JSON decision using ONLY the evidence I provide.

Inputs:
<<CODE>>
{code_with_line_numbers}
<</CODE>>

<<MECHANISM_SPEC>>
{mechanism_json}
<</MECHANISM_SPEC>>

<<INVARIANTS>>
{invariants_result_json}
<</INVARIANTS>>

<<ASPECT_CONCLUSIONS>>
{aspect_conclusions_json}
<</ASPECT_CONCLUSIONS>>
"""

# ===== Unified aspect explanation (I1–I4) using full contract source =====
# ===== Unified aspect explanation (I1–I4) — ENGLISH ONLY =====

ASPECT_EXPLAIN_SYSTEM = """
You are a professional smart contract auditor.
Analyze Solidity code to explain potential Ponzi-related mechanisms from four aspects (I1–I4).
Return ONLY a single valid JSON object with four natural-language explanations (no extra text, no chain-of-thought).
Keys must be exactly: I1, I2, I3, I4.
"""

ASPECT_EXPLAIN_USER_TEMPLATE = r"""
You are given the FULL Solidity contract source below. Read it carefully and produce concise, evidence-aware explanations
for FOUR aspects (I1–I4). Write in clear natural language (one or two short paragraphs per aspect).
Your output must be EXACTLY one JSON object with keys "I1", "I2", "I3", "I4" and NOTHING ELSE.

The four aspects to analyze are:
### I1: Funds Flow
- Identify all funds "entries/sources" (e.g., payable functions, external income, reward-pool injections, owner top-ups) and all "exits/sinks" (e.g., user withdrawals, dividends/payouts, referral rewards, fee extraction, owner withdrawals).
- Determine whether rewards/dividends primarily depend on *new deposits* (i.e., later participants’ funds), and whether any *independent/verifiable external profit* exists.
- Summarize the core code paths and condition branches related to balances, pools, fees/taxes, and reward/dividend computation.

### I2: Withdrawal Control
- Identify withdrawal-related controls: access control (onlyOwner/roles/whitelists), time/block locks, amount thresholds, penalties/fees, pause/emergency switches, reentrancy guards, etc.
- Judge whether there are *structural/institutional* blockers or delays (e.g., perpetual queuing, hard-to-satisfy conditions, arbitrary admin denial/drain).

### I3: Profit & Referral Logic
- Identify how profits/interest/dividends are generated and distributed; note if they are fixed, compounding, or promise high returns.
- Identify referral/invitation relations (single/multi-level), referral reward rates, tiered commissions, binding and update logic.
- Assess whether profits depend monotonically on *growth* (new participants/new deposits/downline count).

### I4: Withdrawal Ordering
- Identify whether an explicit or implicit queue/ordering exists (e.g., FIFO/LIFO, by join time, by stake size, by round/epoch).
- Identify data structures encoding the order (arrays/mappings/pointers/indices; head/tail; position) and how progression is advanced.
- Judge whether the ordering may cause early participants to be favored or late participants to be delayed (e.g., perpetual queues).

INPUT – full contract source:
<<CODE>>
{contract_source_code}
<</CODE>>

OUTPUT – return EXACTLY one JSON object with this shape (no additional fields, no commentary):
{
 "I1": "explanation of funds flow characteristics.",
 "I2": "explanation of withdrawal control logic.",
 "I3": "explanation of profit and referral logic.",
 "I4": "explanation of withdrawal ordering mechanism."
}
"""