#!/usr/bin/env bash

# Cancel one of your running or pending Slurm jobs

USER_NAME="${USER:-$(whoami)}"

# Running/Pending jobs holen
JOBS_RAW=$(squeue -u "${USER_NAME}" -h -o "%i %t %j")

if [ -z "${JOBS_RAW}" ]; then
  echo "Keine Jobs für Benutzer '${USER_NAME}'."
  exit 0
fi

echo "Jobs für ${USER_NAME}:"
echo
printf "%-3s %-10s %-4s %s\n" "Nr" "JobID" "Stat" "Name"
echo "-----------------------------------------"

JOB_IDS=()
idx=0

while IFS= read -r line; do
  [ -z "$line" ] && continue
  jobid=$(awk '{print $1}' <<< "$line")
  state=$(awk '{print $2}' <<< "$line")
  name=$(cut -d' ' -f3- <<< "$line")

  JOB_IDS+=("$jobid")
  printf "%-3s %-10s %-4s %s\n" "$idx" "$jobid" "$state" "$name"
  idx=$((idx+1))
done <<< "${JOBS_RAW}"

echo
read -r -p "Welchen Job möchtest du canceln? (Index oder JobID, Enter = Abbruch): " selection

[ -z "$selection" ] && echo "Abgebrochen." && exit 0

chosen_jobid=""

# Index?
if [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -lt "${#JOB_IDS[@]}" ]; then
  chosen_jobid="${JOB_IDS[$selection]}"
else
  chosen_jobid="$selection"
fi

# Existiert Job noch?
if ! squeue -j "$chosen_jobid" -h -o "%i" | grep -q "^${chosen_jobid}$"; then
  echo "JobID '${chosen_jobid}' ist nicht (mehr) in squeue sichtbar."
  exit 1
fi

read -r -p "Job ${chosen_jobid} wirklich canceln? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo "Cancel job ${chosen_jobid} ..."
scancel "$chosen_jobid"
echo "Job wurde gecancelt."
