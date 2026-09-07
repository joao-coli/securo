# Local backups

Keep PostgreSQL dumps and complete backup directories here, private and excluded
from Git. Complete backups should include their checksums and the corresponding
code/configuration and persistent files needed for recovery. Older `.sql.gz`
dumps are retained alongside newer custom-format dumps.

Follow the [fork-update runbook](../docs/fork-upstream-merge.md) for backup,
restore-test, deployment, and recovery steps. Restore tests use a separate
database; these local copies are not an off-host disaster-recovery backup.
