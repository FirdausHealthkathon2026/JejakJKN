# Local backup and restore

These commands are intentionally restricted to `APP_ENV=local`.

```bash
APP_ENV=local make backup-local
APP_ENV=local make restore-local BACKUP=backups/jejakjkn-YYYYMMDDTHHMMSSZ.sql
```

After restore, run `make migrate` and the integration suite. Production backup, retention,
encryption, and point-in-time recovery remain infrastructure responsibilities.

For the non-destructive Gate 8 acceptance drill, use `make restore-drill`. It restores into an
ephemeral isolated PostgreSQL container and verifies all six domain databases, audit-chain links,
and completed verification digest lengths before deleting the drill container.
