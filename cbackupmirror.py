import coloredlogs
import logging
import sys

from executor.contexts import create_context

import rsync_system_backup as rsb

# Config
SYSLOG_HOST = "192.168.112.11"
SYSLOG_PORT = 514

BACKUP_SOURCE = "backup-mirror@192.168.112.16:/data"
BACKUP_DESTINATION = "/data/backup-data/data"


def setup_logging():
    coloredlogs.install(syslog=True)
    log = logging.getLogger()

    syslog = logging.handlers.SysLogHandler(address=(SYSLOG_HOST, SYSLOG_PORT))
    log.addHandler(syslog)

    return log


def do_backup():
    log = logging.getLogger()

    program_opts = {
        'backup_enabled': True,
        'snapshot_enabled': True,
        'rotate_enabled': True,
        'sudo_enabled': False,
        'dry_run': False,
        'multi_fs' : True,
        'notifications_enabled': False,
        'rsync_verbose_count': 1,
        'rsync_show_progress': True,
        'source_context': create_context(),
        'source': BACKUP_SOURCE,
        'destination': rsb.Destination(expression=BACKUP_DESTINATION)
    }

    try:
        # Initialize the program with the command line
        # options and execute the requested action(s).
        b = rsb.RsyncSystemBackup(**program_opts).execute()
    except Exception as e:
        if isinstance(e, rsb.exceptions.RsyncSystemBackupError):
            # Special handling when the backup disk isn't available.
            if isinstance(e, rsb.exceptions.MissingBackupDiskError):
                log.info("Skipping backup: %s", e)
                return 1
            # Known problems shouldn't produce
            # an intimidating traceback to users.
            log.error("Aborting due to error: %s", e)
        else:
            # Unhandled exceptions do get a traceback,
            # because it may help fix programming errors.
            log.exception("Aborting due to unhandled exception!")
        return 1
    else:
        return 0


def main():

    log = setup_logging()
    log.info("Starting backup script")
    return do_backup()


if __name__ == '__main__':
    sys.exit(main())
