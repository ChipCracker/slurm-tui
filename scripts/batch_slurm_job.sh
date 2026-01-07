#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <job.slurm>"
  exit 1
fi

SLURM_FILE="$1"
[[ -f "$SLURM_FILE" ]] || { echo "File not found: $SLURM_FILE"; exit 1; }

die(){ echo "Error: $*" >&2; exit 1; }

get_sbatch_value() {
  local key="$1"
  local line
  line="$(grep -E '^[[:space:]]*#SBATCH[[:space:]]+--'"$key"'(=|[[:space:]]+)' "$SLURM_FILE" | head -n1 || true)"
  [[ -n "$line" ]] || { echo ""; return 0; }
  echo "$line" | sed -E 's/^[[:space:]]*#SBATCH[[:space:]]+--'"$key"'(=|[[:space:]]+)//' | awk '{print $1}'
}

has_sbatch_key() {
  local key="$1"
  grep -qE '^[[:space:]]*#SBATCH[[:space:]]+--'"$key"'(=|[[:space:]]+)' "$SLURM_FILE"
}

apply_or_insert_sbatch() {
  local key="$1" value="$2" in_file="$3" out_file="$4"
  if grep -qE '^[[:space:]]*#SBATCH[[:space:]]+--'"$key"'(=|[[:space:]]+)' "$in_file"; then
    awk -v key="$key" -v val="$value" '
      BEGIN{done=0}
      {
        if(!done && $0 ~ "^[[:space:]]*#SBATCH[[:space:]]+--"key"(=|[[:space:]]+)") {
          print "#SBATCH --"key"="val
          done=1
          next
        }
        print
      }' "$in_file" > "$out_file"
  else
    awk -v key="$key" -v val="$value" '
      {lines[NR]=$0; if($0 ~ "^[[:space:]]*#SBATCH") last=NR}
      END{
        if(last==0){
          print "#SBATCH --"key"="val
          for(i=1;i<=NR;i++) print lines[i]
        } else {
          for(i=1;i<=NR;i++){
            print lines[i]
            if(i==last) print "#SBATCH --"key"="val
          }
        }
      }' "$in_file" > "$out_file"
  fi
}

# ---- read current defaults
cur_partition="$(get_sbatch_value partition)"
cur_qos="$(get_sbatch_value qos)"
cur_gres="$(get_sbatch_value gres)"
cur_cpus="$(get_sbatch_value cpus-per-task)"
cur_mem_per_cpu="$(get_sbatch_value mem-per-cpu)"
cur_mem="$(get_sbatch_value mem)"

cur_gpus=""
if [[ -n "$cur_gres" ]]; then
  cur_gpus="$(echo "$cur_gres" | awk -F: '{n=$NF; if(n ~ /^[0-9]+$/) print n; }')"
fi

[[ -n "$cur_partition" ]] || cur_partition="p2"
[[ -n "$cur_qos" ]] || cur_qos="preemptible"
[[ -n "$cur_cpus" ]] || cur_cpus="12"
[[ -n "$cur_gpus" ]] || cur_gpus="4"

mem_mode="mem-per-cpu"
mem_default="$cur_mem_per_cpu"
if has_sbatch_key "mem"; then
  mem_mode="mem"
  mem_default="$cur_mem"
fi
[[ -n "$mem_default" ]] || mem_default="60G"

# ---- interactive UI helpers
has_whiptail() { command -v whiptail >/dev/null 2>&1; }

choose_partition() {
  local def="$1"
  local parts=()
  if command -v sinfo >/dev/null 2>&1; then
    # Only partitions that exist and are up
    mapfile -t parts < <(sinfo -h -o %P | sed 's/\*//g' | sort -u)
  fi
  # Fall back to your known set
  if [[ ${#parts[@]} -eq 0 ]]; then
    parts=(p0 p1 p2 p4)
  fi

  if has_whiptail; then
    local menu=()
    for p in "${parts[@]}"; do
      menu+=("$p" "")
    done
    whiptail --title "SLURM" --menu "Select partition" 15 60 6 \
      "${menu[@]}" 3>&1 1>&2 2>&3 || return 1
  else
    read -r -p "Partition [$def]: " inp
    echo "${inp:-$def}"
  fi
}

choose_qos() {
  local def="$1"
  local qos_list=()
  if command -v sacctmgr >/dev/null 2>&1; then
    # This can be slow / permission-limited; keep it best-effort
    mapfile -t qos_list < <(sacctmgr -n -P show qos format=Name 2>/dev/null | tr '|' '\n' | sed '/^$/d' | sort -u || true)
  fi
  if [[ ${#qos_list[@]} -eq 0 ]]; then
    qos_list=(preemptible normal low)
  fi

  if has_whiptail; then
    local menu=()
    for q in "${qos_list[@]}"; do
      menu+=("$q" "")
    done
    whiptail --title "SLURM" --menu "Select QoS" 15 60 6 \
      "${menu[@]}" 3>&1 1>&2 2>&3 || return 1
  else
    read -r -p "QoS [$def]: " inp
    echo "${inp:-$def}"
  fi
}

input_box() {
  local title="$1" prompt="$2" def="$3"
  if has_whiptail; then
    whiptail --title "$title" --inputbox "$prompt" 10 60 "$def" 3>&1 1>&2 2>&3 || return 1
  else
    read -r -p "$prompt [$def]: " inp
    echo "${inp:-$def}"
  fi
}

confirm_box() {
  local msg="$1"
  if has_whiptail; then
    whiptail --title "SLURM" --yesno "$msg" 12 70
  else
    read -r -p "$msg [y/N] " inp
    [[ "${inp:-N}" =~ ^[Yy]$ ]]
  fi
}

# ---- interactive flow
partition="$(choose_partition "$cur_partition")" || die "Cancelled"
gpus="$(input_box "SLURM" "GPUs (integer)" "$cur_gpus")" || die "Cancelled"
qos="$(choose_qos "$cur_qos")" || die "Cancelled"
cpus="$(input_box "SLURM" "CPUs per task (integer)" "$cur_cpus")" || die "Cancelled"
mem="$(input_box "SLURM" "RAM (${mem_mode}) e.g. 60G / 240G" "$mem_default")" || die "Cancelled"

[[ "$gpus" =~ ^[0-9]+$ ]] || die "GPUs must be integer"
[[ "$cpus" =~ ^[0-9]+$ ]] || die "CPUs must be integer"
[[ -n "$partition" ]] || die "Partition empty"
[[ -n "$qos" ]] || die "QoS empty"
[[ -n "$mem" ]] || die "Memory empty"

# build new gres preserving type if present
if [[ -n "$cur_gres" && "$cur_gres" =~ ^gpu:[^:]+:[0-9]+ ]]; then
  gpu_type="$(echo "$cur_gres" | awk -F: '{print $2}')"
  gres="gpu:${gpu_type}:${gpus}"
else
  gres="gpu:${gpus}"
fi

summary=$(
  cat <<EOF
About to edit:
  $SLURM_FILE

Set:
  partition=$partition
  qos=$qos
  gres=$gres
  cpus-per-task=$cpus
  ${mem_mode}=$mem

Also: if accelerate launch has --num_processes/--num-processes, set it to $gpus.
Proceed?
EOF
)

confirm_box "$summary" || die "Cancelled"

# ---- edit in-place (with backup)
backup="${SLURM_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
cp -p "$SLURM_FILE" "$backup"

t1="$(mktemp -t slurm_edit.XXXXXX.1)"
t2="$(mktemp -t slurm_edit.XXXXXX.2)"
t3="$(mktemp -t slurm_edit.XXXXXX.3)"
t4="$(mktemp -t slurm_edit.XXXXXX.4)"
t5="$(mktemp -t slurm_edit.XXXXXX.5)"
trap 'rm -f "$t1" "$t2" "$t3" "$t4" "$t5"' EXIT

cp "$SLURM_FILE" "$t1"
apply_or_insert_sbatch partition     "$partition" "$t1" "$t2"
apply_or_insert_sbatch qos           "$qos"       "$t2" "$t3"
apply_or_insert_sbatch gres          "$gres"      "$t3" "$t4"
apply_or_insert_sbatch cpus-per-task "$cpus"      "$t4" "$t5"

if has_sbatch_key "mem"; then
  apply_or_insert_sbatch mem "$mem" "$t5" "$t1"
else
  apply_or_insert_sbatch mem-per-cpu "$mem" "$t5" "$t1"
fi

# Update accelerate num_processes / num-processes if present
sed -E \
  -e 's/(--num_processes[[:space:]]+)[0-9]+/\1'"$gpus"'/g' \
  -e 's/(--num_processes=)[0-9]+/\1'"$gpus"'/g' \
  -e 's/(--num-processes[[:space:]]+)[0-9]+/\1'"$gpus"'/g' \
  -e 's/(--num-processes=)[0-9]+/\1'"$gpus"'/g' \
  "$t1" > "$t2"

mv "$t2" "$SLURM_FILE"

echo "Edited in-place: $SLURM_FILE"
echo "Backup:          $backup"
echo "Submitting..."
sbatch "$SLURM_FILE"

