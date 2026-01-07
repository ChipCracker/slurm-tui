#!/usr/bin/env bash
set -euo pipefail

generate_random_name() {
    printf "job-%06x" $(( RANDOM * RANDOM ))
}

read -rp "Job name (empty = random): " JOB_NAME
if [[ -z "${JOB_NAME}" ]]; then
    JOB_NAME=$(generate_random_name)
    echo "Using random job name: ${JOB_NAME}"
fi

read -rp "Partition [p4]: " PARTITION
PARTITION=${PARTITION:-p4}

read -rp "QoS (none/advanced/preemptible) [advanced]: " QOS
QOS=${QOS:-advanced}

read -rp "Number of GPUs [1]: " GPUS
GPUS=${GPUS:-1}

read -rp "CPUs per task [12]: " CPUS_PER_TASK
CPUS_PER_TASK=${CPUS_PER_TASK:-12}

read -rp "Mem per CPU (e.g. 20G) [20G]: " MEM_PER_CPU
MEM_PER_CPU=${MEM_PER_CPU:-20G}

read -rp "Walltime (HH:MM:SS) [08:00:00]: " WALLTIME
WALLTIME=${WALLTIME:-08:00:00}

DEFAULT_PROJECT_DIR="$PWD"
read -rp "Project directory [${DEFAULT_PROJECT_DIR}]: " PROJECT_DIR
PROJECT_DIR=${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}

DEFAULT_VENV_PATH="${PROJECT_DIR}/.venv/bin/activate"
read -rp "Venv activation path [${DEFAULT_VENV_PATH}]: " VENV_PATH
VENV_PATH=${VENV_PATH:-$DEFAULT_VENV_PATH}

# Ask whether loadenv should be executed automatically
read -rp "Use loadenv automatically from ${PROJECT_DIR}/.env? (y/N): " LOADENV_CHOICE
LOADENV_CHOICE=${LOADENV_CHOICE:-N}

if [[ "$LOADENV_CHOICE" =~ ^[Yy]$ ]]; then
    LOADENV_CALL='loadenv "'"${PROJECT_DIR}/.env"'"'
else
    LOADENV_CALL=""
fi

read -rp "Output script filename [${JOB_NAME}.slurm]: " SCRIPT_NAME
SCRIPT_NAME=${SCRIPT_NAME:-${JOB_NAME}.slurm}

QOS_LINE=""
if [[ "$QOS" != "none" && -n "$QOS" ]]; then
    QOS_LINE="#SBATCH --qos=${QOS}"
fi

cat > "${SCRIPT_NAME}" <<EOF
#!/bin/bash

#SBATCH --job-name=${JOB_NAME}
#SBATCH --output=${JOB_NAME}.out
#SBATCH --error=${JOB_NAME}.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=${PARTITION}
#SBATCH --time=${WALLTIME}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem-per-cpu=${MEM_PER_CPU}
#SBATCH --gres=gpu:${GPUS}
${QOS_LINE}

cd ${PROJECT_DIR} || { echo "Directory not found: ${PROJECT_DIR}"; exit 1; }

source ${VENV_PATH}

loadenv() {
    while IFS='=' read -r key value; do
        key="\${key// }"
        value="\${value## }"
        [[ -z "\$key" || "\$key" =~ ^# ]] && continue
        export "\$key=\$value"
    done < "\$1"
}

${LOADENV_CALL}

echo "=================================================================="
echo "Starting Batch Job at \$(date)"
echo "Job submitted to partition \${SLURM_JOB_PARTITION} on \${SLURM_CLUSTER_NAME}"
echo "=================================================================="

# Insert your commands below this line

EOF

chmod +x "${SCRIPT_NAME}"
echo "Created Slurm script: ${SCRIPT_NAME}"

vim "${SCRIPT_NAME}"
