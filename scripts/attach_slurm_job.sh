#!/usr/bin/env bash

# Attach to one of your running Slurm jobs

USER_NAME="${USER:-$(whoami)}"

# Hole laufende Jobs
JOBS_RAW=$(squeue -u "${USER_NAME}" -h -o "%i %t %j")

if [ -z "${JOBS_RAW}" ]; then
  echo "Keine laufenden Jobs für Benutzer '${USER_NAME}'."
  exit 0
fi

echo "Laufende Jobs für ${USER_NAME}:"
echo
printf "%-3s %-10s %-4s %s\n" "Nr" "JobID" "Stat" "Name"
echo "-----------------------------------------"

JOB_IDS=()
idx=0

# Baue Liste + Ausgabe
# IFS= sorgt dafür, dass führende/trailing Spaces nicht wegfallen
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
read -r -p "Zu welchem Job möchtest du dich attachen? (Index oder JobID, Enter = Abbruch): " selection

# Abbruch
if [ -z "${selection}" ]; then
  echo "Abgebrochen."
  exit 0
fi

chosen_jobid=""

# Eingabe ist nur Ziffern? -> als Index interpretieren
if [[ "${selection}" =~ ^[0-9]+$ ]] && [ "${selection}" -lt "${#JOB_IDS[@]}" ]; then
  chosen_jobid="${JOB_IDS[$selection]}"
else
  # Sonst direkt als JobID
  chosen_jobid="${selection}"
fi

# Prüfen, ob Job noch existiert
if ! squeue -j "${chosen_jobid}" -h -o "%i" | grep -q "^${chosen_jobid}$"; then
  echo "JobID '${chosen_jobid}' ist nicht (mehr) in squeue sichtbar."
  exit 1
fi

echo "Attache zu JobID ${chosen_jobid} ..."
exec srun --jobid="${chosen_jobid}" --overlap --pty /bin/bash -l
