
# -*- coding: utf-8 -*-
import os, json, argparse
from pathlib import Path

from ponzi_agent.utils.io import read_all_sol_files, build_line_numbered_text
from ponzi_agent.utils.llm import LLMClient
from ponzi_agent.prompts import (
    EQUATION_EXTRACTION_SYSTEM,
    EQUATION_EXTRACTION_USER_TEMPLATE,
    FINAL_PONZI_DECISION_SYSTEM,
    FINAL_PONZI_DECISION_USER_TEMPLATE
)
from ponzi_agent.invariants.i_registry import InvariantRegistry
from ponzi_agent.invariants.solvers_z3 import invariant_I1, invariant_I2, invariant_I3, invariant_I4

def read_code_with_line_numbers(src: Path):
    files = read_all_sol_files(src)
    if not files:
        raise RuntimeError(f"No .sol files found in {src}")
    merged = []
    file_map = {}
    for f in files:
        numbered = build_line_numbered_text(f)
        file_map[str(f)] = numbered
        merged.append(f"\n===== FILE: {f} =====")
        merged.extend(numbered)
    return "\n".join(merged), file_map

def extract_mechanism(llm: LLMClient, contract_id: str, code_block: str) -> dict:
    user = EQUATION_EXTRACTION_USER_TEMPLATE.format(
        contract_id=contract_id,
        code_with_line_numbers=code_block
    )
    mech = llm.chat_json(EQUATION_EXTRACTION_SYSTEM, user)
    return mech

def run_invariants(mech: dict) -> dict:
    reg = InvariantRegistry()
    reg.register("I1", invariant_I1)
    reg.register("I2", invariant_I2)
    reg.register("I3", invariant_I3)
    reg.register("I4", invariant_I4)
    return reg.run_all(mech)

def final_decision(llm: LLMClient, code_block: str, mech: dict, inv_results: dict) -> dict:
    user = FINAL_PONZI_DECISION_USER_TEMPLATE.format(
        code_with_line_numbers=code_block,
        mechanism_json=json.dumps(mech, ensure_ascii=False, indent=2),
        invariants_result_json=json.dumps(inv_results, ensure_ascii=False, indent=2)
    )
    decision = llm.chat_json(FINAL_PONZI_DECISION_SYSTEM, user)
    return decision

def main():
    ap = argparse.ArgumentParser(description="Training-free Ponzi Agent (LLM equations + Z3 invariants)")
    ap.add_argument("--src", required=True, help="Solidity file or directory")
    ap.add_argument("--api_key", default=os.getenv("OPENAI_API_KEY", ""))
    ap.add_argument("--base_url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    ap.add_argument("--contract_id", default="Contract#local")
    ap.add_argument("--out", default="ponzi_result.json")
    args = ap.parse_args()

    llm = LLMClient(api_key=args.api_key, base_url=args.base_url, model=args.model)
    code_block, file_map = read_code_with_line_numbers(Path(args.src))

    mechanism = extract_mechanism(llm, args.contract_id, code_block)
    invariants = run_invariants(mechanism)
    decision = final_decision(llm, code_block, mechanism, invariants)

    result = {
        "contract_id": args.contract_id,
        "mechanism": mechanism,
        "invariants": invariants,
        "final_decision": decision
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] Results saved to {args.out}")

if __name__ == "__main__":
    main()
