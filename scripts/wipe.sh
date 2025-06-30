#!/bin/bash

# This script finds the disk device containing the root filesystem and
# zaps all other top-level block devices using 'sgdisk --zap-all'.
#
# Requirements: util-linux (for findmnt, lsblk). 
#
# Example usage:
#   sudo ./wipe_disks.sh        # actually zap disks
#   sudo ./wipe_disks.sh -n     # dry-run: show which disks would be zapped

DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Usage: $0 [--dry-run]" >&2
      exit 1
      ;;
  esac
done

#0 lvm cleanup

if [[ "$DRY_RUN" == true ]]; then
    echo "[DRY RUN] Would remove LVM volumes"
else
    # Remove LVM volumes
    echo "Removing LVM volumes:"
    sudo pvs -o pv_name,vg_name --separator '|' --noheadings | \
    while IFS='|' read -r pv vg; do
        if echo "$vg" | grep -q "ceph"; then
            echo "Matched Ceph VG: $vg on PV: $pv"
            for lv in $(sudo lvs -o lv_name --noheadings $vg); do
                sudo lvremove -y $vg/$lv
            done
            sudo vgremove -y $vg
            sudo pvremove -y $pv
        fi
    done
    ls /dev/mapper/ceph-* | xargs -I% -- sudo dmsetup remove %
    sudo rm -rf /dev/ceph-*
    sudo rm -rf /dev/mapper/ceph--*
    # remove local rook data
    sudo rm -rf /var/lib/rook/*
fi

# after lvm cleanup as it would fail if they don't exist.
set -euo pipefail

# 1. Identify the device containing the root filesystem ('/') via findmnt:contentReference[oaicite:5]{index=5}
ROOT_PART=$(findmnt -n -o SOURCE /)
if [[ -z "$ROOT_PART" ]]; then
  echo "Error: could not determine root device." >&2
  exit 1
fi
echo "Root filesystem is on $ROOT_PART"

# Prepare list of devices to exclude (start with root disk)
EXCLUDE=()

# 2. Determine base device(s) for root (strip partition suffix or find LVM PVs)
if [[ "$ROOT_PART" == /dev/mapper/* ]]; then
  # LVM or encrypted root: find underlying physical volume(s)
  LV_NAME=$(basename "$ROOT_PART")
  if command -v lvs &>/dev/null; then
    # Get volume group name
    VG_NAME=$(lvs --noheadings -o vg_name "/dev/mapper/$LV_NAME" 2>/dev/null | awk '{print $1}')
  else
    VG_NAME=""
  fi
  if [[ -n "$VG_NAME" ]]; then
    # List PVs belonging to this VG (e.g. /dev/sda2, /dev/nvme0n1p3, etc.)
    PV_LIST=$(pvs --noheadings -o pv_name -S vg_name="$VG_NAME" 2>/dev/null | tr -d ' ')
  else
    PV_LIST=""
  fi
  if [[ -z "$PV_LIST" ]]; then
    # Fallback for single-device encryption: get parent of the mapper device
    PARENT=$(lsblk -n -o PKNAME "$ROOT_PART")
    if [[ -n "$PARENT" ]]; then
      PV_LIST="/dev/$PARENT"
    fi
  fi
  # Add each physical device (strip partition number)
  for PV in $PV_LIST; do
    if [[ "$PV" == *p* ]]; then
      DEV_BASE="${PV%p*}"
    else
      DEV_BASE="${PV%[0-9]*}"
    fi
    if [[ -n "$DEV_BASE" && ! " ${EXCLUDE[*]} " =~ " $DEV_BASE " ]]; then
      EXCLUDE+=("$DEV_BASE")
    fi
  done
else
  # Non-LVM: strip trailing partition number (and NVMe 'p' prefix) to get base disk
  if [[ "$ROOT_PART" == *p* ]]; then
    ROOT_BASE="${ROOT_PART%p*}"
  else
    ROOT_BASE="${ROOT_PART%[0-9]*}"
  fi
  EXCLUDE+=("$ROOT_BASE")
fi

echo "Excluding root device(s): ${EXCLUDE[@]}"

# 3. List all top-level block devices of type "disk"
#    Using lsblk to list devices; filter out non-disk types:contentReference[oaicite:6]{index=6}
DISKS=$(lsblk -d -n -p -o NAME,TYPE | awk '$2=="disk" {print $1}')


# 4. Iterate and zap non-root disks
for disk in $DISKS; do
  skip=false
  for exc in "${EXCLUDE[@]}"; do
    if [[ "$disk" == "$exc" ]]; then
      skip=true
      break
    fi
  done
  if [[ "$skip" == true ]]; then
    echo "Skipping root disk $disk"
    continue
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[DRY RUN] Would zap $disk"
  else
    echo "Wiping disk $disk"
    # Zap the disk to a fresh, usable state (zap-all is important, b/c MBR has to be clean)
    sudo sgdisk --zap-all $disk
    # Inform the OS of partition table changes
    sudo partprobe $disk
    # SSDs may be better cleaned with blkdiscard instead of dd
    blkdiscard_status=0
    devname=$(basename "$(readlink -f "$disk")")
    if [[ -f "/sys/block/$devname/queue/rotational" ]] && [[ $(<"/sys/block/$devname/queue/rotational") -eq 0 ]]; then
        echo "Detected SSD: $disk"
        if sudo blkdiscard "$disk" 2>/dev/null; then
            echo "blkdiscard succeeded on $disk"
            blkdiscard_status=1
        fi
        if [[ "$blkdiscard_status" -ne 1 ]]; then
            # If blkdiscard failed or is not available, use dd to zero out the disk
            echo "blkdiscard not supported on $disk, skipping, using dd instead"
            # Wipe portions of the disk to remove more LVM metadata that may be present
            sudo dd if=/dev/zero of="$disk" bs=1K count=200 oflag=direct,dsync seek=0 # Clear at offset 0
            sudo dd if=/dev/zero of="$disk" bs=1K count=200 oflag=direct,dsync seek=$((1 * 1024**2)) # Clear at offset 1GB
            sudo dd if=/dev/zero of="$disk" bs=1K count=200 oflag=direct,dsync seek=$((10 * 1024**2)) # Clear at offset 10GB
            sudo dd if=/dev/zero of="$disk" bs=1K count=200 oflag=direct,dsync seek=$((100 * 1024**2)) # Clear at offset 100GB
        fi
    fi
  fi
done
