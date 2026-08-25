#!/usr/bin/env bash
set -euo pipefail

MAX_QUERIES="${1:-50}"
SEED="${2:-42}"
CANDIDATE_POOL="${3:-150}"
EXP_DIR="${4:-}"

if [[ -z "${EXP_DIR}" ]]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    EXP_DIR="./experiments/run_${TIMESTAMP}"
fi

PRED_DIR="${EXP_DIR}/predictions"
REPORT_DIR="${EXP_DIR}/reports"

mkdir -p "${PRED_DIR}" "${REPORT_DIR}"

echo "=========================================================================="
echo "Running Hybrid Retrieval Benchmark (Limit: ${MAX_QUERIES}, Seed: ${SEED})"
echo "Output Directory: ${EXP_DIR}"
echo "=========================================================================="

for dataset in scifact qasper cuad beir_fiqa; do
    echo ""
    echo "--- Running benchmark: ${dataset} (max ${MAX_QUERIES} queries, seed ${SEED}) ---"
    uv run rag-eval baseline \
        --dataset "${dataset}" \
        --output-predictions "${PRED_DIR}/${dataset}_baseline.jsonl" \
        --mode hybrid \
        --candidate-pool-size "${CANDIDATE_POOL}" \
        --max-queries "${MAX_QUERIES}" \
        --seed "${SEED}"
    uv run rag-eval evaluate \
        --dataset "${dataset}" \
        --predictions "${PRED_DIR}/${dataset}_baseline.jsonl" \
        --output-report "${REPORT_DIR}/${dataset}_eval.json"
done

echo ""
echo "Benchmark completed. Artifacts saved in ${EXP_DIR}"
