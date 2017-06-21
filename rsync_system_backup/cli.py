# rsync-system-backup: Linux system backups powered by rsync.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: June 21, 2017
# URL: https://github.com/xolox/python-rsync-system-backup

"""
Usage: rsync-system-backup [OPTIONS] [SOURCE] DESTINATION

Use rsync to create full system backups.

The required DESTINATION argument specifies the (possibly remote) location
where the backup is stored, in the syntax of rsync's command line interface.
The optional SOURCE argument defaults to '/' which means the complete root
filesystem will be included in the backup (other filesystems are excluded).

Supported locations include:

- Local disks (possibly encrypted using LUKS).
- Remote systems that allow SSH connections.
- Remote systems that are running an rsync daemon.
- Connections to rsync daemons tunneled over SSH.

The backup process consists of several steps:

1. First rsync is used to transfer all (relevant) files to a destination
   directory (whether on the local system or a remote system). Every time
   a backup is made, this same destination directory is updated.

2. After the files have been transferred a 'snapshot' of the destination
   directory is taken and stored in a directory with a timestamp in its
   name. These snapshots are created using 'cp --archive --link'.

3. Finally the existing snapshots are rotated to purge old backups
   according to a rotation scheme that you can customize.

Supported options:

  -b, --backup

    Create a backup using rsync but don't create a snapshot and don't rotate
    old snapshots unless the --snapshot and/or --rotate options are also given.

  -s, --snapshot

    Create a snapshot of the destination directory but don't create a backup
    and don't rotate old snapshots unless the --backup and/or --rotate options
    are also given.

    This option can be used to create snapshots of an rsync daemon module using
    a 'post-xfer exec' command. If DESTINATION isn't given it defaults to the
    value of the environment variable $RSYNC_MODULE_PATH.

  -r, --rotate

    Rotate old snapshots but don't create a backup and snapshot unless the
    --backup and/or --snapshot options are also given.

    This option can be used to rotate old snapshots of an rsync daemon module
    using a 'post-xfer exec' command. If DESTINATION isn't given it defaults to
    the value of the environment variable $RSYNC_MODULE_PATH.

  -m, --mount=DIRECTORY

    Automatically mount the filesystem to which backups are written.

    When this option is given and DIRECTORY isn't already mounted, the
    'mount' command is used to mount the filesystem to which backups are
    written before the backup starts. When 'mount' was called before the
    backup started, 'umount' will be called when the backup finishes.

    An entry for the mount point needs to be
    defined in /etc/fstab for this to work.

  -c, --crypto=NAME

    Automatically unlock the encrypted filesystem to which backups are written.

    When this option is given and the NAME device isn't already unlocked, the
    cryptdisks_start command is used to unlock the encrypted filesystem to
    which backups are written before the backup starts. When cryptdisks_start
    was called before the backup started, cryptdisks_stop will be called
    when the backup finishes.

    An entry for the encrypted filesystem needs to be defined in /etc/crypttab
    for this to work. If the device of the encrypted filesystem is missing and
    rsync-system-backup is being run non-interactively, it will exit gracefully
    and not show any desktop notifications.

    If you want the backup process to run fully unattended you can configure a
    key file in /etc/crypttab, otherwise you will be asked for the password
    each time the encrypted filesystem is unlocked.

  -i, --ionice=CLASS

    Use the 'ionice' program to set the I/O scheduling class and priority of
    the 'rm' invocations used to remove backups. CLASS is expected to be one of
    the values 'idle', 'best-effort' or 'realtime'. Refer to the man page of
    the 'ionice' program for details about these values.

  -u, --no-sudo

    By default backup and snapshot creation is performed with superuser
    privileges, to ensure that all files are readable and filesystem
    metadata is preserved. The -u, --no-sudo option disables
    the use of 'sudo' during these operations.

  -n, --dry-run

    Don't make any changes, just report what would be done. This doesn't
    create a backup or snapshot but it does run rsync with the --dry-run
    option.

  --disable-notifications

    By default a desktop notification is shown (using notify-send) before the
    system backup starts and after the backup finishes. The use of this option
    disables the notifications (notify-send will not be called at all).

  -v, --verbose

    Make more noise (increase logging verbosity). Can be repeated.

  -q, --quiet

    Make less noise (decrease logging verbosity). Can be repeated.

  -h, --help

    Show this message and exit.
"""

# Standard library modules.
import getopt
import logging
import os
import sys

# External dependencies.
import coloredlogs
from executor import validate_ionice_class
from executor.contexts import create_context
from humanfriendly.terminal import connected_to_terminal, usage, warning

# Modules included in our package.
from rsync_system_backup import RsyncSystemBackup
from rsync_system_backup.exceptions import MissingBackupDiskError, RsyncSystemBackupError

# Initialize a logger.
logger = logging.getLogger(__name__)


def main():
    """Command line interface for the ``rsync-system-backup`` program."""
    # Initialize logging to the terminal and system log.
    coloredlogs.install(syslog=True)
    # Parse the command line arguments.
    context_opts = dict()
    program_opts = dict()
    try:
        options, arguments = getopt.getopt(sys.argv[1:], 'bsrm:c:i:unvqh', [
            'backup', 'snapshot', 'rotate', 'mount=', 'crypto=', 'ionice=',
            'no-sudo', 'dry-run', 'disable-notifications', 'verbose', 'quiet',
            'help',
        ])
        for option, value in options:
            if option in ('-b', '--backup'):
                enable_explicit_action(program_opts, 'backup_enabled')
            elif option in ('-s', '--snapshot'):
                enable_explicit_action(program_opts, 'snapshot_enabled')
            elif option in ('-r', '--rotate'):
                enable_explicit_action(program_opts, 'rotate_enabled')
            elif option in ('-m', '--mount'):
                program_opts['mount_point'] = value
            elif option in ('-c', '--crypto'):
                program_opts['crypto_device'] = value
            elif option in ('-i', '--ionice'):
                value = value.lower().strip()
                validate_ionice_class(value)
                program_opts['ionice'] = value
            elif option in ('-u', '--no-sudo'):
                program_opts['sudo_enabled'] = False
            elif option in ('-n', '--dry-run'):
                logger.info("Performing a dry run (because of %s option) ..", option)
                program_opts['dry_run'] = True
            elif option == '--disable-notifications':
                program_opts['notifications_enabled'] = False
            elif option in ('-v', '--verbose'):
                coloredlogs.increase_verbosity()
            elif option in ('-q', '--quiet'):
                coloredlogs.decrease_verbosity()
            elif option in ('-h', '--help'):
                usage(__doc__)
                return
            else:
                raise Exception("Unhandled option! (programming error)")
        if len(arguments) > 2:
            msg = "Expected one or two positional arguments! (got %i)"
            raise Exception(msg % len(arguments))
        if len(arguments) == 2:
            # Get the source from the first of two arguments.
            program_opts['source'] = arguments.pop(0)
        if arguments:
            # Get the destination from the second (or only) argument.
            program_opts['destination'] = arguments[0]
        elif not os.environ.get('RSYNC_MODULE_PATH'):
            # Show a usage message when no destination is given.
            usage(__doc__)
            return
    except Exception as e:
        warning("Error: %s", e)
        sys.exit(1)
    try:
        # Inject the source context into the program options.
        program_opts['source_context'] = create_context(**context_opts)
        # Initialize the program with the command line
        # options and execute the requested action(s).
        RsyncSystemBackup(**program_opts).execute()
    except Exception as e:
        if isinstance(e, RsyncSystemBackupError):
            # Special handling when the backup disk isn't available.
            if isinstance(e, MissingBackupDiskError):
                # Check if we're connected to a terminal to decide whether the
                # error should be propagated or silenced, the idea being that
                # rsync-system-backup should keep quiet when it's being run
                # from cron and the backup disk isn't available.
                if not connected_to_terminal():
                    logger.info("Skipping backup: %s", e)
                    sys.exit(0)
            # Known problems shouldn't produce
            # an intimidating traceback to users.
            logger.error("Aborting due to error: %s", e)
        else:
            # Unhandled exceptions do get a traceback,
            # because it may help fix programming errors.
            logger.exception("Aborting due to unhandled exception!")
        sys.exit(1)


def enable_explicit_action(options, explicit_action):
    """
    Explicitly enable an action and disable other implicit actions.

    :param options: A dictionary of options.
    :param explicit_action: The action to enable (one of the strings
                            'backup_enabled', 'snapshot_enabled',
                            'rotate_enabled').
    """
    options[explicit_action] = True
    for implicit_action in 'backup_enabled', 'snapshot_enabled', 'rotate_enabled':
        if implicit_action != explicit_action:
            options.setdefault(implicit_action, False)
