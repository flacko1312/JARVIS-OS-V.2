#!/usr/bin/env bash
# DEPRECATED — This pull-based backup script has been replaced.
#
# New architecture (2026-10-04):
#   Windows (jarvis_backup.ps1) → SCP → Ubuntu (jarvis_backup_receive.sh)
#
# Windows pushes files outbound; Ubuntu validates and promotes.
# See docs/LILITH_INTEGRATION.md for details.
echo "DEPRECATED: Use jarvis_backup.ps1 on Windows instead." >&2
echo "See scripts/jarvis_backup.ps1 and scripts/jarvis_backup_receive.sh" >&2
exit 1
