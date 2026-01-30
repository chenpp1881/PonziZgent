# 多线程版本
# -*- coding: utf-8 -*-
"""
Unified runner for PonziAgent
- Single-contract mode:   --src <sol file or directory>
- Batch JSON mode:        --json <path to json list with {"code":..., "label":...}>
Features:
  * Safe template filling (avoid str.format() on JSON-like templates)
  * Multi-threaded LLM calls (I/O bound) with --max_workers
  * Real-time saving after each contract + resume from previous partial outputs
  * Precision / Recall / F1 computation at the end
"""

import os
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========= Flexible imports (adapt to your project layout) =========
# Preferred (flat files):

from ponzi_agent.prompts import (
    EQUATION_EXTRACTION_SYSTEM,
    EQUATION_EXTRACTION_USER_TEMPLATE,
    FINAL_PONZI_DECISION_SYSTEM,
    FINAL_PONZI_DECISION_USER_TEMPLATE,  # full 用
    FINAL_PONZI_DECISION_USER_TEMPLATE_LEAN,  # lean 用（新增）
    ASPECT_EXPLAIN_SYSTEM,
    ASPECT_EXPLAIN_USER_TEMPLATE
)

import requests


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        r = requests.post(url, headers=headers, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        # OpenAI-style response
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except Exception:
            # Return raw string as a fallback
            return {"raw": content}


from openai import OpenAI


class LLMClientOPENAI:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Please set OPENAI_API_KEY or pass api_key directly.")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=(base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        )
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    def chat_json(self, system: str, user: str, temperature: float = 0.1) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        )
        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except Exception:
            # Return raw string as a fallback
            return {"raw": content}


from ponzi_agent.invariants.i_registry import InvariantRegistry
from ponzi_agent.invariants.solvers_z3 import invariant_I1, invariant_I2, invariant_I3, invariant_I4


# ========== Utility: safe template filler (avoid .format pitfalls) ==========
def fill_template_literal(tpl: str, **kwargs) -> str:
    """
    Safely replace only the placeholders we explicitly provide: {key}.
    Do NOT parse arbitrary braces in the template (e.g., JSON examples).
    """
    out = tpl
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ========== Read .sol files (for single-contract mode) ==========
def _read_text(p: Path, encoding="utf-8") -> str:
    with p.open("r", encoding=encoding, errors="ignore") as f:
        return f.read()


def read_all_sol_files(src: Path) -> List[Path]:
    src = Path(src)
    files = []
    if src.is_file() and src.suffix.lower() == ".sol":
        files.append(src)
    elif src.is_dir():
        for p in src.rglob("*.sol"):
            files.append(p)
    return sorted(files)


def build_line_numbered_text_from_string(code: str) -> List[str]:
    lines = (code or "").splitlines()
    return [f"{i + 1:06d}: {lines[i]}" for i in range(len(lines))]


def read_code_with_line_numbers(src: Path) -> Tuple[str, Dict[str, List[str]]]:
    files = read_all_sol_files(src)
    if not files:
        raise RuntimeError(f"No .sol files found in {src}")
    merged = []
    file_map = {}
    for f in files:
        code = _read_text(f)
        numbered = build_line_numbered_text_from_string(code)
        file_map[str(f)] = numbered
        merged.append(f"\n===== FILE: {f} =====")
        merged.extend(numbered)
    return "\n".join(merged), file_map


# ========== Pipeline: mechanism extraction -> invariants -> final decision ==========
def extract_mechanism(llm: LLMClient, contract_id: str, code_block: str) -> dict:
    user = fill_template_literal(
        EQUATION_EXTRACTION_USER_TEMPLATE,
        contract_id=contract_id,
        code_with_line_numbers=code_block
    )
    return llm.chat_json(EQUATION_EXTRACTION_SYSTEM, user)


def explain_aspects(llm: LLMClient, raw_code: str) -> dict:
    """
    Use the unified I1–I4 prompt on the full contract source.
    Returns: {"I1": "...", "I2": "...", "I3": "...", "I4": "..."}
    """
    user = fill_template_literal(
        ASPECT_EXPLAIN_USER_TEMPLATE,
        contract_source_code=raw_code or ""
    )
    return llm.chat_json(ASPECT_EXPLAIN_SYSTEM, user)


def run_invariants(mech: dict) -> dict:
    reg = InvariantRegistry()
    reg.register("I1", invariant_I1)
    reg.register("I2", invariant_I2)
    reg.register("I3", invariant_I3)
    reg.register("I4", invariant_I4)
    return reg.run_all(mech)

def final_decision(llm: LLMClient,
                   payload_mode: str,
                   code_block: str,
                   mech: dict,
                   inv_results: dict,
                   aspect_exps: dict) -> dict:
    user = fill_template_literal(
        FINAL_PONZI_DECISION_USER_TEMPLATE,
        code_with_line_numbers=code_block,
        mechanism_json=json.dumps(mech, ensure_ascii=False, indent=2),
        invariants_result_json=json.dumps(inv_results, ensure_ascii=False, indent=2),
    )


def process_one_contract_from_code(llm: LLMClient, code: str, contract_id: str, llm_payload) -> Dict[str, Any]:
    numbered_lines = build_line_numbered_text_from_string(code)
    code_block = "\n".join(numbered_lines)
    mechanism = extract_mechanism(llm, contract_id, code_block)
    aspect_exps = explain_aspects(llm, code)
    invariants = run_invariants(mechanism)
    decision = final_decision(
        llm=llm,
        payload_mode=llm_payload,
        code_block=code,
        mech=mechanism,
        inv_results=invariants,
        aspect_exps=aspect_exps
    )

    return {
        "contract_id": contract_id,
        "mechanism": mechanism,
        "aspect_explanations": aspect_exps,
        "invariants": invariants,
        "final_decision": decision,

        # === NEW: 一并返回，方便上层决定是否落盘 ===
        "source_code_raw": code,
        "source_code_numbered": code_block
    }


# ========== Metrics ==========
def _to_int_label(v: Any) -> int:
    """
    Normalize label to {0,1}.
    Positives: 1, "1", True, "true", "Ponzi" (case-insensitive)
    Everything else: 0
    """
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return 1 if int(v) == 1 else 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"1", "true", "ponzi"}:
            return 1
    return 0


def compute_prf(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


# ========== Batch helpers (resume + realtime save + multithreading) ==========
def _load_existing_items(batch_out: Path) -> List[Dict[str, Any]]:
    if not batch_out.exists():
        return []
    try:
        data = json.loads(batch_out.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data["items"]
        if isinstance(data, list):
            # legacy format
            return data
    except Exception:
        pass
    return []


def _is_na_decision(dec) -> bool:
    if dec is None:
        return True
    s = str(dec).strip()
    return (len(s) == 0) or (s.upper() == "N/A")


def _safe_write_batch(batch_out: Path, items: List[Dict[str, Any]], metrics: Dict[str, Any] = None):
    payload = {
        "count": len(items),
        "items": items
    }
    if metrics is not None:
        payload["metrics"] = metrics
    tmp = batch_out.with_suffix(batch_out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(batch_out)


def _sort_key(x: Dict[str, Any]):
    oi = x.get("original_index", None)
    if isinstance(oi, (int, float)) or (isinstance(oi, str) and str(oi).isdigit()):
        try:
            return (0, int(oi))
        except Exception:
            pass
    return (1, str(x.get("contract_id", "")))


def main():
    ap = argparse.ArgumentParser(description="PonziAgent: LLM equations + Z3 invariants")

    # Mode A: single contract (original)
    ap.add_argument("--src", help="Solidity file or directory. If provided, run single-contract mode.")

    # Mode B: batch JSON
    ap.add_argument("--json", default="llm_explanations.json",
                    help="Path to a JSON file with list of objects containing 'code' and 'label'.")

    ap.add_argument("--api_key", default=os.getenv("OPENAI_API_KEY", ""),
                    help="deepseek")
    ap.add_argument("--base_url", default=os.getenv("OPENAI_BASE_URL", ""))
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""))

    # Outputs
    ap.add_argument("--out", default="ponzi_result.json", help="Output JSON path for single mode")
    ap.add_argument("--batch_out", default="ponzi_batch_result.json", help="Output JSON path for batch mode")

    # === NEW: 控制是否在结果中保存源代码 ===
    ap.add_argument("--save_source", action="store_true", help="Include raw source code in saved results")
    ap.add_argument("--save_numbered", action="store_true", help="Include line-numbered source code in saved results")

    # JSON field names
    ap.add_argument("--code_field", default="code", help="Field name for smart-contract source code in JSON")
    ap.add_argument("--label_field", default="label", help="Field name for ground-truth label in JSON")
    ap.add_argument("--start_index", "-s", type=int, default=None, help="开始样本索引（包含）")
    ap.add_argument("--end_index", "-e", type=int, default=None, help="结束样本索引（不包含）")

    ap.add_argument("--llm_payload", choices=["full", "lean"], default="full",
                    help="Payload to final decision LLM: 'full' sends code+mechanism+invariants+conclusions; 'lean' sends only code+conclusions (default).")

    # Performance / robustness
    ap.add_argument("--max_workers", type=int, default=10, help="Max concurrent threads for LLM calls (I/O bound)")
    ap.add_argument("--resume", action="store_true", help="Resume from existing --batch_out if present")
    ap.add_argument("--max_retries", type=int, default=3, help="Retries per contract upon transient failures")
    ap.add_argument("--retry_backoff", type=float, default=2.0, help="Exponential backoff base (seconds)")

    args = ap.parse_args()

    # Init LLM
    llm = LLMClient(api_key=args.api_key, base_url=args.base_url, model=args.model)

    # ========= Batch JSON mode =========
    if args.json:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise RuntimeError("JSON must be a list of objects with 'code' and 'label'.")

        # 只取前 N 条（N==0 表示不限制）
        if args.start_index is not None or args.end_index is not None:
            start = args.start_index or 0
            end = args.end_index or len(data)
            data = data[start:end]
            print(f"🔹Selected subset: data[{start}:{end}] -> {len(data)} samples")

        batch_out = Path(args.batch_out)
        if batch_out.exists() and not args.resume:
            print(f"🔸Detected existing result file: {batch_out}. Auto-enable resume to avoid overwrite.")
            args.resume = True
        existing_items = _load_existing_items(batch_out) if args.resume else []
        done_ids = {it.get("contract_id") for it in existing_items}
        results_map: Dict[str, Dict[str, Any]] = {it.get("contract_id"): it for it in existing_items}

        def process_item(idx: int, item: Dict[str, Any]) -> Tuple[int, str, int, int, Dict[str, Any]]:
            # 使用原始 index（严格按你的要求）；若缺失则回退 idx 以保证健壮性
            orig_id = item["index"] if "index" in item else idx
            contract_id = f"JSON#{orig_id}"
            gt = _to_int_label(item.get(args.label_field, 0))
            code = item.get(args.code_field, "") or ""

            if args.resume and contract_id in done_ids:
                done_obj = results_map[contract_id]
                pred_label = int(done_obj.get("predicted_label", 0))
                return idx, contract_id, gt, pred_label, done_obj

            # retries with backoff
            last_err = None
            for attempt in range(1, args.max_retries + 1):
                try:
                    one = process_one_contract_from_code(llm, code, contract_id, args.llm_payload)
                    if not args.save_source:
                        one.pop("source_code_raw", None)
                    if not args.save_numbered:
                        one.pop("source_code_numbered", None)
                    decision_json = one.get("final_decision", {}) or {}
                    pred_label = 1 if str(decision_json.get("decision", "")).strip().lower() == "ponzi" else 0
                    one.update({
                        "ground_truth_label": gt,
                        "predicted_label": pred_label,
                        "predicted_decision": decision_json.get("decision", None),
                        "original_index": orig_id,
                        "contract_id": contract_id
                    })
                    return idx, contract_id, gt, pred_label, one
                except Exception as e:
                    last_err = e
                    wait = (args.retry_backoff ** (attempt - 1))
                    print(f"[Retry {attempt}/{args.max_retries}] {contract_id} error: {e}. Backoff {wait:.1f}s")
                    time.sleep(wait)
            # If all retries failed, record error result
            err_obj = {
                "contract_id": contract_id,
                "error": str(last_err),
                "ground_truth_label": gt,
                "predicted_label": 0,
                "predicted_decision": None,
                "original_index": orig_id
            }
            return idx, contract_id, gt, 0, err_obj

        # Submit tasks
        futures = []
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
            for idx, item in enumerate(data):
                futures.append(executor.submit(process_item, idx, item))

            def _effective_items(items):
                eff = []
                for it in items:
                    # 以 final_decision.decision 为主，回退到 predicted_decision
                    dec = (it.get("final_decision", {}) or {}).get("decision", it.get("predicted_decision"))
                    if not _is_na_decision(dec):
                        eff.append(it)
                return eff

            existing_effective = _effective_items(existing_items)

            # Real-time aggregation + saving
            y_true: List[int] = [it.get("ground_truth_label", 0) for it in existing_effective]
            y_pred: List[int] = [it.get("predicted_label", 0) for it in existing_effective]
            merged_items: Dict[str, Dict[str, Any]] = {it["contract_id"]: it for it in existing_items}

            total = len(data) + len(existing_items)
            finished = len(existing_items)

            for fu in as_completed(futures):
                idx, cid, gt, pred, obj = fu.result()
                merged_items[cid] = obj
                finished += 1

                decision = str((obj.get("final_decision", {}) or {}).get("decision", "N/A"))
                oi = obj.get("original_index", cid.replace("JSON#", ""))

                if _is_na_decision(decision):
                    # 不进入 y_true/y_pred，但仍保存
                    print(f"[{finished}/{total}] JSON#{oi} decision={decision}")
                else:
                    y_true.append(gt)
                    y_pred.append(pred)
                    print(f"[{finished}/{total}] JSON#{oi}  GT={gt}  PRED={pred}  decision={decision}")

                # 实时保存（不带 metrics），按 original_index 排序
                _safe_write_batch(batch_out, list(sorted(merged_items.values(), key=_sort_key)))

        # Final metrics
        metrics = compute_prf(y_true, y_pred)
        _safe_write_batch(batch_out, list(sorted(merged_items.values(), key=_sort_key)),
                          metrics=metrics)

        print("\n[DONE] Batch saved:", str(batch_out))
        print(f"precision={metrics['precision']:.4f}  recall={metrics['recall']:.4f}  f1={metrics['f1']:.4f}  "
              f"(tp={metrics['tp']} fp={metrics['fp']} fn={metrics['fn']})")
        return


if __name__ == "__main__":
    main()

