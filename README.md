# PonziAgent
**Training-Free Smart Contract Ponzi Scheme Detection via LLM-Extracted Mechanisms and Z3 Invariants**

PonziAgent is a training-free smart contract analysis framework for detecting **Smart Contract Ponzi Schemes (SCPS)**.  
It combines **Large Language Models (LLMs)** for semantic mechanism extraction with **Z3-based invariant checking** to produce *explainable, verifiable, and robust* Ponzi detection results.

Unlike learning-based approaches that rely on labeled datasets and fragile compilation pipelines, PonziAgent directly reasons over **economic logic encoded in Solidity source code**, making it suitable for large-scale auditing and historical contract analysis.

---

## Key Idea

PonziAgent follows a **three-stage pipeline**:

1. **Mechanism Extraction (LLM)**  
   Translate Solidity economic logic into a *machine-checkable mechanism specification*, including:
   - balance and pool variables  
   - fund-flow equations  
   - reward and referral rules  
   - withdrawal constraints and ordering predicates  

2. **Invariant Verification (Z3)**  
   Automatically check a set of Ponzi-related invariants over the extracted mechanism:
   - **I1**: Rewards rely on new deposits in the absence of external profit  
   - **I2**: Withdrawal blocking or privileged withdrawal constraints  
   - **I3**: Early participants’ rewards are non-decreasing with new participants or referrals  
   - **I4**: Withdrawal ordering tied to join-time or queue position  

3. **Final Decision (LLM)**  
   Aggregate source code, extracted mechanisms, and invariant certificates to output a final verdict:
   - `Ponzi`
   - `Non-Ponzi`
   - `Uncertain`  

Each decision is accompanied by **explicit evidence and line-level justifications**.

---

## Project Structure

```
ponzi_agent/
├── prompts.py              # LLM prompt templates (mechanism extraction & final decision)
├── llm.py                  # OpenAI-compatible JSON-only LLM client
├── io.py                   # Solidity file loading & line numbering utilities
├── invariants/
│   ├── i_registry.py       # Invariant registry and result abstraction
│   └── solvers_z3.py       # Z3-based invariant solvers (I1–I4)
├── run.py                  # Unified runner (single-contract & batch mode)
└── README.md
```

---

## Installation

### Requirements
- Python ≥ 3.9
- Z3 solver
- Requests

```bash
pip install z3-solver requests
```

### Environment Variables (Optional)

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
```

Any OpenAI-compatible API (e.g., DeepSeek) can be used.

---

## Usage

### Single-Contract Analysis

```bash
python run.py \
  --src /path/to/contract_or_directory \
  --out result.json
```

### Batch Mode (Dataset Evaluation)

```bash
python run.py \
  --json dataset.json \
  --batch_out ponzi_batch_result.json \
  --max_workers 20 \
  --resume
```

---

## Invariants

| Invariant | Description |
|---------|-------------|
| **I1** | No external profit: rewards depend on new deposits |
| **I2** | Withdrawal blocking or privileged withdrawal |
| **I3** | Early participants benefit monotonically from new participants |
| **I4** | Withdrawal ordering tied to join-time or queue position |

Each invariant returns a satisfiability result together with a Z3 certificate or code witness.

---

## Design Principles

- **Training-free**
- **Explainable**
- **Robust to compiler/version changes**
- **Auditor-oriented**

---

## Citation

If you use PonziAgent in academic work, please cite the corresponding paper:

> PonziProber / PonziZgent: A Hybrid Detection Framework Combining Static Analysis and Multi-Aspect LLM Explanations for Smart Contract Ponzi Schemes.
