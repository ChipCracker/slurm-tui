START=2026-01-01
END=2026-12-31

sreport -n -P -t Hours -T gres/gpu \
  cluster AccountUtilizationByUser start="$START" end="$END" \
| awk -F'|' 'NF>=6 && $3!="" && $2!="root" && $2!="thn" && $2!="cs" {
    printf "%s\t%s\t%s\t%s\n", $6, $3, $2, $4
  }' \
| sort -nr -k1,1 | head -n 20
