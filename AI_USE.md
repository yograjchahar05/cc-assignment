# AI Tools Usage and Verification Report

In accordance with course guidelines and academic honesty policies for the Cloud Computing (CS3081) Mini Project, this document provides a comprehensive record of the AI tools utilized throughout the design, implementation, evaluation, and documentation phases, the specific tasks they assisted with, and the verification methodologies applied to validate their outputs.

---

## 1. AI Tools Utilized

1. **Google Antigravity / Gemini 3.8 Flash (High)**
   - **Role**: Primary coding pair-programmer and agentic assistant.
   - **Environment**: Antigravity IDE agentic environment on Windows 11.
2. **Phi-3.5-mini-instruct (3.8B, Microsoft)**
   - **Role**: Designated Teacher model for sequence-level knowledge distillation as required by project specifications.
   - **Environment**: Local Ollama runtime instance (temperature 0.0, seed 42).

---

## 2. Tasks and Use Cases

| Task / Area | AI Tool | Specific Usage / Prompting |
| :--- | :--- | :--- |
| **Task 1: Prompt & Worker Architecture** | Antigravity | Formulated the teacher prompt template (`prompts/teacher_prompt.txt`) to enforce strict 4-key JSON schema and slot extraction constraints; drafted parallel worker logic with modulo sharding. |
| **Task 1: Teacher Label Generation** | Phi-3.5 (Ollama) | Executed inference across 3,000 raw SLURP commands to generate target JSON structures. |
| **Task 2: Distillation Training** | Antigravity | Implemented PyTorch CPU training loop in `training/train.py`, prompt masking logic, AdamW learning rate schedules, and reproducible seed configurations. |
| **Task 3: Containerized Inference Service** | Antigravity | Implemented FastAPI endpoints (`/parse`, `/healthz`, `/readyz`), dynamic object storage downloading via Boto3, custom header injection (`X-Served-By`, `X-Model-Version`), and fault injection handler. |
| **Task 4: Kubernetes & HPA Manifests** | Antigravity | Drafted declarative Kubernetes configurations (`k8s/`) covering Namespaces, Deployments with resource requests/limits, Service, Traefik Ingress, and HorizontalPodAutoscaler. |
| **Task 5: Subnetting & Stateless NACLs** | Antigravity | Calculated CIDR block allocations from largest to smallest requirement and drafted `network/nacl.json` rules for inbound/outbound traffic. |
| **Task 6: CI/CD Pipeline & Reproducibility** | Antigravity | Structured multi-stage GitHub Actions workflow (`.github/workflows/ci.yml`) including linting, unit tests, model download, quality gating, and Gitleaks secret scanning. |

---

## 3. Verification Methodologies

Every piece of AI-suggested code, configuration, and data was rigorously validated using deterministic, independent tooling:

1. **Static Analysis and Linting**:
   - Every Python source file was checked using `ruff check` to ensure PEP 8 compliance, clean imports, and zero syntax or type inconsistencies.
2. **Automated Unit & Integration Testing**:
   - Authored comprehensive test suites (`tests/test_unit.py`) executed via `pytest` to verify schema validation, malformed input rejection, missing key handling, and fault injection behavior.
3. **Stateless NACL Simulation**:
   - The generated NACL configuration (`network/nacl.json`) was tested against `tools/nacl_sim.py` using `network/packets_sample.jsonl` with `--check` to confirm 100% decision accuracy and correct rule ordering.
4. **Schema Compliance & Model Evaluation**:
   - Model predictions were evaluated strictly using the project evaluation harness `tools/score.py` against `data/validation.jsonl`, verifying JSON validity, intent accuracy, slot extraction, and full-frame accuracy.
5. **Secret Scanning**:
   - Validated that no API keys, credentials, or personal secrets were committed using `gitleaks` and automated git checks.

