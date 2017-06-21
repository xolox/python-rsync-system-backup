# rsync-system-backup: Linux system backups powered by rsync.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: June 21, 2017
# URL: https://github.com/xolox/python-rsync-system-backup

"""
Simple to use Python API for Linux system backups powered by rsync.

The :mod:`rsync_system_backup` module contains the Python API of the
`rsync-system-backup` package. The core logic of the package is contained in
the :class:`RsyncSystemBackup` class.
"""

# Standard library modules.
import logging
import os
import time

# External dependencies.
from executor import quote
from executor.contexts import LocalContext, create_context
from humanfriendly import Timer, compact, concatenate
from linux_utils.crypttab import parse_crypttab
from proc.notify import notify_desktop
from property_manager import (
    PropertyManager,
    cached_property,
    clear_property,
    lazy_property,
    mutable_property,
    required_property,
    set_property,
)
from rotate_backups import Location, RotateBackups

# Modules included in our package.
from rsync_system_backup.destinations import Destination
from rsync_system_backup.exceptions import (
    DestinationContextUnavailable,
    FailedToMountError,
    FailedToUnlockError,
    MissingBackupDiskError,
)

# Semi-standard module versioning.
__version__ = '0.4'

# Initialize a logger for this module.
logger = logging.getLogger(__name__)

DEFAULT_ROTATION_SCHEME = dict(hourly=24, daily=7, weekly=4, monthly='always')
"""The default rotation scheme for system backup snapshots (a dictionary)."""


class RsyncSystemBackup(PropertyManager):

    """
    Python API for the ``rsync-system-backup`` program.

    The following properties can be set by passing keyword arguments to the
    :class:`RsyncSystemBackup` initializer: :attr:`backup_enabled`,
    :attr:`crypto_device`, :attr:`destination`, :attr:`dry_run`,
    :attr:`excluded_roots`, :attr:`ionice`, :attr:`mount_point`,
    :attr:`notifications_enabled`, :attr:`rotate_enabled`,
    :attr:`rotation_scheme`, :attr:`snapshot_enabled`, :attr:`source`,
    :attr:`source_context` and :attr:`sudo_enabled`.

    The values of :attr:`crypto_device_available`,
    :attr:`crypto_device_unlocked`, :attr:`destination_context` and
    :attr:`mount_point_active` are computed based on the mutable properties
    mentioned above.

    The :func:`execute()` method is the main entry point. If you're looking for
    finer grained control refer to :func:`unlock_device()`,
    :func:`mount_filesystem()`, :func:`transfer_changes()`,
    :func:`create_snapshot()` and :func:`rotate_snapshots()`.
    """

    @mutable_property
    def backup_enabled(self):
        """:data:`True` to enable :func:`transfer_changes()`, :data:`False` otherwise."""
        return True

    @mutable_property
    def crypto_device(self):
        """The name of the encrypted filesystem to use (a string or :data:`None`)."""

    @property
    def crypto_device_available(self):
        """
        :data:`True` if the encrypted filesystem is available, :data:`False` otherwise.

        This property is an alias for the
        :attr:`~linux_utils.crypttab.EncryptedFileSystemEntry.is_available`
        property of :attr:`crypttab_entry`.
        """
        return self.crypttab_entry.is_available if self.crypttab_entry else False

    @property
    def crypto_device_unlocked(self):
        """
        :data:`True` if the encrypted filesystem is unlocked, :data:`False` otherwise.

        This property is an alias for the
        :attr:`~linux_utils.crypttab.EncryptedFileSystemEntry.is_unlocked`
        property of :attr:`crypttab_entry`.
        """
        return self.crypttab_entry.is_unlocked if self.crypttab_entry else False

    @cached_property
    def crypttab_entry(self):
        """
        The entry in ``/etc/crypttab`` corresponding to :attr:`crypto_device`.

        The value of this property is computed automatically by parsing
        ``/etc/crypttab`` and looking for an entry whose `target` (the
        first of the four fields) matches :attr:`crypto_device`.

        When an entry is found an
        :class:`~linux_utils.crypttab.EncryptedFileSystemEntry` object is
        constructed, otherwise the result is :data:`None`.
        """
        if self.crypto_device:
            logger.debug("Parsing /etc/crypttab to determine device file of encrypted filesystem %r ..",
                         self.crypto_device)
            for entry in parse_crypttab(context=self.destination_context):
                if entry.target == self.crypto_device:
                    return entry

    @required_property
    def destination(self):
        """
        The destination where backups are stored (a :class:`.Destination` object).

        The value of :attr:`destination` defaults to the value of the
        environment variable ``$RSYNC_MODULE_PATH`` which is set by the `rsync
        daemon`_ before it runs the ``post-xfer exec`` command.
        """
        rsync_module_path = os.environ.get('RSYNC_MODULE_PATH')
        return (Destination(expression=rsync_module_path)
                if rsync_module_path else None)

    @destination.setter
    def destination(self, value):
        """Automatically coerce strings to :class:`.Destination` objects."""
        if not isinstance(value, Destination):
            value = Destination(expression=value)
        set_property(self, 'destination', value)
        clear_property(self, 'destination_context')

    @cached_property
    def destination_context(self):
        """
        The execution context of the system that stores the backup (the destination).

        This is an execution context created by :mod:`executor.contexts`.

        :raises: :exc:`.DestinationContextUnavailable` when the destination is
                 an rsync daemon module (which doesn't allow arbitrary command
                 execution).
        """
        if self.destination.module:
            raise DestinationContextUnavailable(compact("""
                Error: The execution context of the backup destination isn't
                available because the destination ({dest}) is an rsync daemon
                module! (tip: reconsider your command line options)
            """, dest=self.destination.expression))
        else:
            context_opts = dict(sudo=self.sudo_enabled)
            if self.destination.hostname:
                context_opts['ssh_alias'] = self.destination.hostname
                context_opts['ssh_user'] = self.destination.username
            return create_context(**context_opts)

    @mutable_property
    def dry_run(self):
        """:data:`True` to simulate the backup without writing any files, :data:`False` otherwise."""
        return False

    @mutable_property
    def excluded_roots(self):
        """
        A list of patterns (strings) that are excluded from the system backup.

        All of the patterns in this list will be rooted to the top of
        the filesystem hierarchy when they're given the rsync, to avoid
        unintentionally excluding deeply nested directories that happen
        to match names in this list.
        """
        return [
            '/dev/',
            '/home/*/.cache/',
            '/media/',
            '/mnt/',
            '/proc/',
            '/run/',
            '/sys/',
            '/tmp/',
            '/var/cache/',
            '/var/tmp/',
        ]

    @mutable_property
    def ionice(self):
        """
        The I/O scheduling class for rsync (a string or :data:`None`).

        When this property is set ionice_ will be used to set the I/O
        scheduling class for rsync. This can be useful to reduce the
        impact of backups on the rest of the system.

        The value of this property is expected to be one of
        the strings 'idle', 'best-effort' or 'realtime'.

        .. _ionice: https://manpages.debian.org/ionice
        """

    @mutable_property
    def mount_point(self):
        """The pathname of the mount point to use (a string or :data:`None`)."""

    @property
    def mount_point_active(self):
        """:data:`True` if :attr:`mount_point` is mounted already, :data:`False` otherwise."""
        return (self.destination_context.test('mountpoint', self.mount_point)
                if self.mount_point else False)

    @mutable_property
    def notifications_enabled(self):
        """
        Whether desktop notifications are used (a boolean).

        By default desktop notifications are enabled when a real backup is
        being made but disabled during dry runs.
        """
        return not self.dry_run

    @mutable_property
    def rotation_scheme(self):
        """The rotation scheme for snapshots (a dictionary, defaults to :data:`DEFAULT_ROTATION_SCHEME`)."""
        return DEFAULT_ROTATION_SCHEME

    @mutable_property
    def snapshot_enabled(self):
        """:data:`True` to enable :func:`create_snapshot()`, :data:`False` otherwise."""
        return True

    @mutable_property
    def source(self):
        """The pathname of the directory to backup (a string, defaults to '/')."""
        return '/'

    @lazy_property(writable=True)
    def source_context(self):
        """
        The execution context of the system that is being backed up (the source).

        This is expected to be an execution context created by
        :mod:`executor.contexts`. It defaults to
        :class:`executor.contexts.LocalContext`.
        """
        return LocalContext()

    @mutable_property
    def rotate_enabled(self):
        """:data:`True` to enable :func:`rotate_snapshots()`, :data:`False` otherwise."""
        return True

    @mutable_property
    def sudo_enabled(self):
        """:data:`True` to run ``rsync`` and snapshot creation with superuser privileges, :data:`False` otherwise."""
        return True

    def execute(self):
        """
        Execute the requested actions (backup, snapshot and/or rotate).

        The :func:`execute()` method defines the high level control flow
        of the backup / snapshot / rotation process according to
        the caller's requested configuration:

        1. When :attr:`backup_enabled` is set :func:`notify_starting()` shows a
           desktop notification to give the user a heads up that a system
           backup is about to start (because the backup may have a noticeable
           impact on system performance).

        2. When :attr:`crypto_device` is set :func:`unlock_device()` ensures
           that the configured encrypted device is unlocked.

        3. When :attr:`mount_point` is set :func:`mount_filesystem()` ensures
           that the configured filesystem is mounted.

        4. When :attr:`backup_enabled` is set :func:`transfer_changes()`
           creates or updates the system backup on :attr:`destination`
           using rsync.

        5. When :attr:`snapshot_enabled` is set :func:`create_snapshot()`
           creates a snapshot of the :attr:`destination` directory.

        6. When :attr:`rotate_enabled` is set :func:`rotate_snapshots()`
           rotates snapshots.

        7. When :attr:`backup_enabled` is set :func:`notify_finished()` shows
           a desktop notification to give the user a heads up that the
           system backup has finished (or failed).
        """
        try:
            # We use a `with' statement to enable cleanup commands that
            # are run before this method returns. The unlock_device()
            # and mount_filesystem() methods depend on this.
            with self.destination_context:
                self.execute_helper()
        except DestinationContextUnavailable:
            # When the destination is an rsync daemon module we can't just
            # assume that the same server is also accessible over SSH, so in
            # this case no destination context is available.
            self.execute_helper()

    def execute_helper(self):
        """Helper for :func:`execute()`."""
        timer = Timer()
        actions = []
        if self.crypto_device and not self.crypto_device_available:
            msg = "Encrypted filesystem %s isn't available! (the device file %s doesn't exist)"
            raise MissingBackupDiskError(msg % (self.crypto_device, self.crypttab_entry.source_device))
        if self.backup_enabled:
            self.notify_starting()
        self.unlock_device()
        try:
            self.mount_filesystem()
            if self.backup_enabled:
                self.transfer_changes()
                actions.append('create backup')
            if self.snapshot_enabled:
                self.create_snapshot()
                actions.append('create snapshot')
            if self.rotate_enabled:
                self.rotate_snapshots()
                actions.append('rotate old snapshots')
        except Exception:
            self.notify_failed(timer)
            raise
        else:
            if self.backup_enabled:
                self.notify_finished(timer)
            if actions:
                logger.info("Took %s to %s.", timer, concatenate(actions))

    def notify_starting(self):
        """Notify the desktop environment that a system backup is starting."""
        if self.notifications_enabled:
            body = "Starting dry-run" if self.dry_run else "Starting backup"
            notify_desktop(summary="System backups", body=body)

    def notify_finished(self, timer):
        """Notify the desktop environment that a system backup has finished."""
        if self.notifications_enabled:
            body = "Finished backup in %s." % timer
            notify_desktop(summary="System backups", body=body)

    def notify_failed(self, timer):
        """Notify the desktop environment that a system backup has failed."""
        if self.notifications_enabled:
            body = "Backup failed after %s! Review the system logs for details." % timer
            notify_desktop(summary="System backups", body=body, urgency='critical')

    def unlock_device(self):
        """
        Automatically unlock the encrypted filesystem to which backups are written.

        :raises: The following exceptions can be raised:

                 - :exc:`.DestinationContextUnavailable`, refer
                   to :attr:`destination_context` for details.
                 - :exc:`~executor.ExternalCommandFailed` when the
                   cryptdisks_start_ command reports an error.

        When :attr:`crypto_device` is set this method uses cryptdisks_start_ to
        unlock the encrypted filesystem to which backups are written before the
        backup starts. When cryptdisks_start_ was called before the backup
        started, cryptdisks_stop_ will be called when the backup finishes.

        To enable the use of cryptdisks_start_ and cryptdisks_stop_ you need to
        create an `/etc/crypttab`_ entry that maps your physical device to a
        symbolic name. If you want this process to run fully unattended you can
        configure a key file in `/etc/crypttab`_, otherwise you will be asked
        for the password when the encrypted filesystem is unlocked.

        .. _cryptdisks_start: https://manpages.debian.org/cryptdisks_start
        .. _cryptdisks_stop: https://manpages.debian.org/cryptdisks_stop
        .. _/etc/crypttab: https://manpages.debian.org/crypttab
        """
        if self.crypto_device:
            if self.crypto_device_unlocked:
                logger.info("Encrypted filesystem is already unlocked (%s) ..", self.crypto_device)
            else:
                logger.info("Unlocking encrypted filesystem (%s) ..", self.crypto_device)
                self.destination_context.execute(
                    'cryptdisks_start', self.crypto_device,
                    sudo=True, tty=True,
                )
                if not self.crypto_device_unlocked:
                    msg = "Failed to unlock encrypted filesystem! (%s)"
                    raise FailedToUnlockError(msg % self.crypto_device)
                self.destination_context.cleanup(
                    'cryptdisks_stop', self.crypto_device,
                    sudo=True, tty=True,
                )

    def mount_filesystem(self):
        """
        Automatically mount the filesystem to which backups are written.

        :raises: The following exceptions can be raised:

                 - :exc:`.DestinationContextUnavailable`, refer
                   to :attr:`destination_context` for details.
                 - :exc:`~executor.ExternalCommandFailed` when
                   the mount_ command reports an error.

        When :attr:`mount_point` is set this method uses the mount_ command to
        mount the filesystem to which backups are written before the backup
        starts. When mount_ was called before the backup started, umount_ will
        be called when the backup finishes. An entry for the mount point needs
        to be defined in `/etc/fstab`_.

        .. _mount: https://manpages.debian.org/mount
        .. _umount: https://manpages.debian.org/umount
        .. _/etc/fstab: https://manpages.debian.org/fstab
        """
        if self.mount_point:
            if self.mount_point_active:
                logger.info("Filesystem is already mounted (%s) ..", self.mount_point)
            else:
                logger.info("Mounting filesystem (%s) ..", self.mount_point)
                self.destination_context.execute('mount', self.mount_point, sudo=True)
                if not self.mount_point_active:
                    msg = "Failed to mount filesystem! (%s)"
                    raise FailedToMountError(msg % self.crypto_device)
                self.destination_context.cleanup('umount', self.mount_point, sudo=True)

    def transfer_changes(self):
        """Use rsync to synchronize the files on the local system to the backup destination."""
        # The following `with' statement enables rsync daemon connections
        # tunneled over SSH. For this use case we spawn a local SSH client with
        # port forwarding configured, wait for the forwarded port to become
        # connected, have rsync connect through the tunnel and shut down the
        # SSH client after rsync is finished.
        with self.destination:
            rsync_command = ['rsync']
            if self.dry_run:
                rsync_command.append('--dry-run')
                rsync_command.append('--verbose')
            # The following rsync options delete files in the backup
            # destination that no longer exist on the local system.
            # Due to snapshotting this won't cause data loss.
            rsync_command.append('--delete')
            rsync_command.append('--delete-excluded')
            # The following rsync options are intended to preserve
            # as much filesystem metadata as possible.
            rsync_command.append('--acls')
            rsync_command.append('--archive')
            rsync_command.append('--hard-links')
            rsync_command.append('--numeric-ids')
            rsync_command.append('--xattrs')
            # The following rsync option avoids including mounted external
            # drives like USB sticks in system backups.
            #
            # FIXME This will most likely be problematic for users with fancy
            #       partitioning schemes that e.g. mount /home to a different
            #       disk or partition.
            rsync_command.append('--one-file-system')
            # The following rsync options exclude irrelevant directories (to my
            # subjective mind) from the system backup.
            for pattern in self.excluded_roots:
                rsync_command.append('--filter=-/ %s' % pattern)
            # Source the backup from the root of the local filesystem
            # and make sure the pathname ends in a trailing slash.
            rsync_command.append(ensure_trailing_slash(self.source))
            # Target the backup at the configured destination.
            rsync_command.append(ensure_trailing_slash(self.destination.expression))
            # Automatically create missing destination directories.
            try:
                if not self.destination_context.is_directory(self.destination.directory):
                    logger.info("Creating missing destination directory: %s", self.destination.directory)
                    self.destination_context.execute('mkdir', '-p', self.destination.directory, tty=False)
            except DestinationContextUnavailable:
                # Don't fail when the destination doesn't allow for this
                # (because its an rsync daemon module).
                pass
            # Execute the rsync command.
            timer = Timer()
            logger.info("Creating system backup using rsync ..")
            cmd = self.source_context.execute(*rsync_command, **dict(
                # Don't raise an exception when rsync exits with
                # a nonzero status code. From `man rsync':
                #  - 23: Partial transfer due to error.
                #  - 24: Partial transfer due to vanished source files.
                # This can be expected on a running system
                # without proper filesystem snapshots :-).
                check=False,
                # Clear $HOME so that rsync ignores ~/.cvsignore.
                environment=dict(HOME=''),
                # Run rsync under ionice.
                ionice=self.ionice,
                # Run rsync with superuser privileges so that it has read
                # access to all files on the local filesystem?
                sudo=self.sudo_enabled,
            ))
            if cmd.returncode in (0, 23, 24):
                logger.info("Took %s to create backup.", timer)
                if cmd.returncode != 0:
                    logger.warning(
                        "Ignoring `partial transfer' warnings (rsync exited with %i).",
                        cmd.returncode,
                    )
            else:
                logger.error("Backup failed after %s! (rsync exited with %i)",
                             timer, cmd.returncode)
                raise cmd.error_type(cmd)

    def create_snapshot(self):
        """
        Create a snapshot of the destination directory.

        :raises: The following exceptions can be raised:

                 - :exc:`.DestinationContextUnavailable`, refer
                   to :attr:`destination_context` for details.
                 - :exc:`.ParentDirectoryUnavailable`, refer
                   to :attr:`.parent_directory` for details.
                 - :exc:`~executor.ExternalCommandFailed` when
                   the ``cp`` command reports an error.
        """
        # Compose the `cp' command needed to create a snapshot.
        snapshot = os.path.join(self.destination.parent_directory,
                                time.strftime('%Y-%m-%d %H:%M:%S'))
        cp_command = [
            'cp', '--archive', '--link',
            self.destination.directory,
            snapshot,
        ]
        # Execute the `cp' command?
        if self.dry_run:
            logger.info("Snapshot command: %s", quote(cp_command))
        else:
            timer = Timer()
            logger.info("Creating snapshot: %s", snapshot)
            self.destination_context.execute(*cp_command, ionice=self.ionice)
            logger.info("Took %s to create snapshot.", timer)

    def rotate_snapshots(self):
        """
        Rotate system backup snapshots using :mod:`.rotate_backups`.

        :raises: The following exceptions can be raised:

                 - :exc:`.DestinationContextUnavailable`, refer
                   to :attr:`destination_context` for details.
                 - :exc:`.ParentDirectoryUnavailable`, refer
                   to :attr:`.parent_directory` for details.
                 - Any exceptions raised by :mod:`.rotate_backups`.

        The values of the :attr:`dry_run`, :attr:`ionice` and
        :attr:`rotation_scheme` properties are passed on to the
        :class:`~rotate_backups.RotateBackups` class.
        """
        helper = RotateBackups(
            dry_run=self.dry_run,
            io_scheduling_class=self.ionice,
            rotation_scheme=self.rotation_scheme,
        )
        helper.rotate_backups(Location(
            context=self.destination_context,
            directory=self.destination.parent_directory,
        ))


def ensure_trailing_slash(expression):
    """
    Add a trailing slash to rsync source/destination locations.

    :param expression: The rsync source/destination expression (a string).
    :returns: The same expression with exactly one trailing slash.
    """
    if expression:
        # Strip any existing trailing slashes.
        expression = expression.rstrip('/')
        # Add exactly one trailing slash.
        expression += '/'
    return expression
