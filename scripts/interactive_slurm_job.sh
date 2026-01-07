#!/usr/bin/env bash

# Start an interactive Slurm session with custom resources

echo "Interaktiver SLURM-Job"
echo "-----------------------"

read -r -p "Partition (z.B. p2, a100, cpu, …): " PART
read -r -p "GPUs (z.B. 1): " GPUS
read -r -p "CPUs pro Task (z.B. 12): " CPUS
read -r -p "Mem pro CPU (z.B. 10G): " MEM

# Default-Werte falls leer
PART=${PART:-p2}
GPUS=${GPUS:-1}
CPUS=${CPUS:-4}
MEM=${MEM:-4G}

echo
echo "Starte interaktiven Job mit:"
echo "  Partition:      $PART"
echo "  GPUs:           $GPUS"
echo "  CPUs pro Task:  $CPUS"
echo "  Mem pro CPU:    $MEM"
echo

read -r -p "Fortfahren? [y/N]: " OK
if [[ ! "$OK" =~ ^[Yy]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

# Ausführung
exec srun \
    --qos=interactive \
    --partition="$PART" \
    --gres="gpu:$GPUS" \
    --cpus-per-task="$CPUS" \
    --mem-per-cpu="$MEM" \
    --pty bash
