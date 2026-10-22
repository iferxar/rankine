#!/bin/sh
# Makes CPU package power readable without root (see packaging/rankine-rapl.conf).
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
sudo install -m644 "$repo/packaging/rankine-rapl.conf" /etc/tmpfiles.d/rankine-rapl.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/rankine-rapl.conf
ls -l /sys/devices/virtual/powercap/intel-rapl/intel-rapl:*/energy_uj
