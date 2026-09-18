#!/bin/bash
set -eu
printf 'Virtualization: '
systemd-detect-virt || true
printf 'CPU count: '
nproc
free -m
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
lsmem --summary=only 2>/dev/null || true
if command -v dmidecode >/dev/null; then dmidecode --type 17 | sed -n '/Size:/p'; fi
dmesg | grep -Ei 'Memory:|hv_balloon|virtio_balloon|hot.add|balloon' | tail -20 || true
