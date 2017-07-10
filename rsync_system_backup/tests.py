# Test suite for the `rsync-system-backup' Python package.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 11, 2017
# URL: https://github.com/xolox/python-rsync-system-backup

"""Test suite for the `rsync-system-backup` package."""

# Standard library modules.
import contextlib
import logging
import os

# External dependencies.
from executor import ExternalCommandFailed, execute
from humanfriendly import Timer
from humanfriendly.testing import MockedProgram, TemporaryDirectory, TestCase, run_cli
from linux_utils.luks import (
    create_encrypted_filesystem,
    create_image_file,
    cryptdisks_start,
    cryptdisks_stop,
    TemporaryKeyFile,
)
from mock import MagicMock
from rotate_backups import RotateBackups

# The module we're testing.
from rsync_system_backup import DEFAULT_ROTATION_SCHEME, RsyncSystemBackup
from rsync_system_backup.cli import main
from rsync_system_backup.destinations import Destination
from rsync_system_backup.exceptions import (
    DestinationContextUnavailable,
    FailedToMountError,
    InvalidDestinationDirectory,
    InvalidDestinationError,
    MissingBackupDiskError,
    UnsupportedPlatformError,
)

# Initialize a logger for this module.
logger = logging.getLogger(__name__)

# Configuration defaults.
CRYPTO_NAME = 'rsync-system-backup'
FILESYSTEM_DEVICE = '/dev/mapper/%s' % CRYPTO_NAME
IMAGE_FILE = '/tmp/rsync-system-backup.img'
KEY_FILE = '/tmp/rsync-system-backup.key'
MOUNT_POINT = '/mnt/rsync-system-backup'


class RsyncSystemBackupsTestCase(TestCase):

    """:mod:`unittest` compatible container for `rsync-system-backup` tests."""

    def test_usage(self):
        """Test the usage message."""
        # Make sure the usage message is shown when no arguments
        # are given and when the -h or --help option is given.
        for options in [], ['-h'], ['--help']:
            exit_code, output = run_cli(main, *options)
            assert "Usage:" in output

    def test_invalid_arguments(self):
        """Test the handling of incorrect command line arguments."""
        # More than two arguments should report an error.
        exit_code, output = run_cli(main, 'a', 'b', 'c', merged=True)
        assert exit_code != 0
        assert "Error" in output
        # Invalid `ionice' values should report an error.
        exit_code, output = run_cli(main, '--ionice=foo', merged=True)
        assert exit_code != 0
        assert "Error" in output

    def test_destination_parsing(self):
        """Test the parsing of rsync destinations."""
        # Our first test case is trivial: The pathname of a local directory.
        dest = Destination(expression='/mnt/backups/laptop')
        assert dest.directory == '/mnt/backups/laptop'
        assert not dest.hostname
        assert not dest.username
        assert not dest.module
        # Our second test case involves an SSH connection.
        dest = Destination(expression='backup-server:/backups/laptop')
        assert dest.hostname == 'backup-server'
        assert dest.directory == '/backups/laptop'
        assert not dest.username
        assert not dest.module
        # Our third test case specifies the remote username for SSH.
        dest = Destination(expression='backup-user@backup-server:/backups/laptop')
        assert dest.hostname == 'backup-server'
        assert dest.username == 'backup-user'
        assert dest.directory == '/backups/laptop'
        assert not dest.module
        # Our fourth test case involves the root of an rsync daemon module.
        dest = Destination(expression='backup-user@backup-server::laptop_backups')
        assert dest.hostname == 'backup-server'
        assert dest.username == 'backup-user'
        assert dest.module == 'laptop_backups'
        assert not dest.directory
        # Our fourth test case concerns the alternative syntax for rsync daemon modules.
        dest = Destination(expression='rsync://backup-user@backup-server:12345/laptop_backups/some-directory')
        assert dest.hostname == 'backup-server'
        assert dest.port_number == 12345
        assert dest.username == 'backup-user'
        assert dest.module == 'laptop_backups'
        assert dest.directory == 'some-directory'
        # Finally we will also check that the intended exception types are
        # raised when no valid destination is given.
        self.assertRaises(TypeError, Destination)
        self.assertRaises(InvalidDestinationError, Destination, expression='')

    def test_rsync_module_path_as_destination(self):
        """Test that destination defaults to ``$RSYNC_MODULE_PATH``."""
        with TemporaryDirectory() as temporary_directory:
            try:
                os.environ['RSYNC_MODULE_PATH'] = temporary_directory
                program = RsyncSystemBackup()
                assert program.destination.directory == temporary_directory
                assert not program.destination.hostname
                assert not program.destination.username
                assert not program.destination.module
            finally:
                os.environ.pop('RSYNC_MODULE_PATH')

    def test_destination_context(self):
        """Test destination context creation."""
        # Make sure DestinationContextUnavailable is raised when the
        # destination is an rsync daemon module.
        program = RsyncSystemBackup(destination='server::backups/system')
        self.assertRaises(DestinationContextUnavailable, lambda: program.destination_context)
        # Make sure the SSH alias and user are copied from the destination
        # expression to the destination context.
        program = RsyncSystemBackup(destination='backup-user@backup-server:backups/system')
        assert program.destination_context.ssh_alias == 'backup-server'
        assert program.destination_context.ssh_user == 'backup-user'

    def test_notifications(self):
        """Test the desktop notification functionality."""
        timer = Timer()
        program = RsyncSystemBackup(destination='/backups/system')
        # The happy path.
        with MockedProgram('notify-send', returncode=0):
            program.notify_starting()
            program.notify_finished(timer)
            program.notify_failed(timer)
        # The sad path (should not raise exceptions).
        with MockedProgram('notify-send', returncode=1):
            program.notify_starting()
            program.notify_finished(timer)
            program.notify_failed(timer)

    def test_simple_backup(self):
        """Test a backup of an alternative source directory to a local destination."""
        with TemporaryDirectory() as temporary_directory:
            source = os.path.join(temporary_directory, 'source')
            destination = os.path.join(temporary_directory, 'destination')
            latest_directory = os.path.join(destination, 'latest')
            # Create a source for testing.
            self.create_source(source)
            # Run the program through the command line interface.
            exit_code, output = run_cli(
                main, '--no-sudo', '--ionice=idle', '--disable-notifications',
                source, latest_directory,
            )
            assert exit_code == 0
            # Make sure the backup was created.
            self.verify_destination(latest_directory)
            # Make sure a snapshot was created.
            assert len(find_snapshots(destination)) == 1

    def test_dry_run(self):
        """Test that ``rsync-system-backup --dry-run ...`` works as intended."""
        with TemporaryDirectory() as temporary_directory:
            source = os.path.join(temporary_directory, 'source')
            destination = os.path.join(temporary_directory, 'destination')
            latest_directory = os.path.join(destination, 'latest')
            os.makedirs(latest_directory)
            # Create a source for testing.
            self.create_source(source)
            # Run the program through the command line interface.
            exit_code, output = run_cli(
                main, '--dry-run', '--no-sudo',
                source, latest_directory,
            )
            assert exit_code == 0
            # Make sure no backup was created.
            assert len(os.listdir(latest_directory)) == 0
            # Make sure no snapshot was created.
            assert len(find_snapshots(destination)) == 0

    def test_backup_only(self):
        """Test that ``rsync-system-backup --backup`` works as intended."""
        # Check that by default a backup is performed and a snapshot is created.
        with TemporaryDirectory() as temporary_directory:
            source = os.path.join(temporary_directory, 'source')
            destination = os.path.join(temporary_directory, 'destination')
            latest_directory = os.path.join(destination, 'latest')
            # Create a source for testing.
            self.create_source(source)
            # Run the program through the command line interface.
            exit_code, output = run_cli(
                main, '--backup', '--no-sudo', '--disable-notifications',
                source, latest_directory,
            )
            assert exit_code == 0
            # Make sure the backup was created.
            self.verify_destination(latest_directory)
            # Make sure no snapshot was created.
            assert len(find_snapshots(destination)) == 0

    def test_encrypted_backup(self):
        """
        Test a backup to an encrypted filesystem.

        To make this test work you need to make the following additions
        to system files (and create ``/mnt/rsync-system-backup``):

        .. code-block:: sh

           $ grep rsync-system-backup /etc/fstab
           /dev/mapper/rsync-system-backup /mnt/rsync-system-backup ext4 noauto 0 0

           $ grep rsync-system-backup /etc/crypttab
           rsync-system-backup /tmp/rsync-system-backup.img /tmp/rsync-system-backup.key luks,noauto

           $ sudo cat /etc/sudoers.d/rsync-system-backup
            peter ALL=NOPASSWD:/usr/sbin/cryptdisks_start rsync-system-backup
            peter ALL=NOPASSWD:/usr/sbin/cryptdisks_stop rsync-system-backup
            peter ALL=NOPASSWD:/bin/mount /mnt/rsync-system-backup
            peter ALL=NOPASSWD:/bin/umount /mnt/rsync-system-backup
            peter ALL=NOPASSWD:/sbin/mkfs.ext4 /dev/mapper/rsync-system-backup
            peter ALL=NOPASSWD:/usr/bin/test -e /dev/mapper/rsync-system-backup
            peter ALL=NOPASSWD:/bin/mountpoint /mnt/rsync-system-backup
            peter ALL=NOPASSWD:/usr/bin/test -d /mnt/rsync-system-backup/latest
            peter ALL=NOPASSWD:/bin/mkdir -p /mnt/rsync-system-backup/latest
            peter ALL=NOPASSWD:/usr/bin/rsync * /tmp/* /mnt/rsync-system-backup/latest/
            peter ALL=NOPASSWD:/bin/cp --archive --link /mnt/rsync-system-backup/latest /mnt/rsync-system-backup/*
            peter ALL=NOPASSWD:/usr/bin/test -d /mnt/rsync-system-backup
            peter ALL=NOPASSWD:/usr/bin/test -r /mnt/rsync-system-backup
            peter ALL=NOPASSWD:/usr/bin/find /mnt/rsync-system-backup *
            peter ALL=NOPASSWD:/usr/bin/test -w /mnt/rsync-system-backup
            peter ALL=NOPASSWD:/bin/rm --recursive /mnt/rsync-system-backup/latest

        Of course you should change ``/etc/sudoers.d/rsync-system-backup`` to
        replace ``peter`` with your actual username :-).
        """
        if not os.path.isdir(MOUNT_POINT):
            return self.skipTest("Skipping test because %s doesn't exist!", MOUNT_POINT)
        with TemporaryDirectory() as source:
            destination = os.path.join(MOUNT_POINT, 'latest')
            with prepared_image_file():
                # Create a source for testing.
                self.create_source(source)
                # Run the program through the command line interface.
                self.create_encrypted_backup(source, destination)
                # Unlock the encrypted image file.
                with unlocked_device(CRYPTO_NAME):
                    # Mount the encrypted filesystem.
                    with active_mountpoint(MOUNT_POINT):
                        # Verify that the backup was successful.
                        self.verify_destination(destination)
                        # Invoke rsync-system-backup using the same command line
                        # arguments, but this time while the encrypted device is
                        # already unlocked and the filesystem is already mounted.
                        self.create_encrypted_backup(source, destination)
                        # Verify that the backup was successful.
                        self.verify_destination(destination)
                    # Invoke rsync-system-backup using the same command line
                    # arguments, but this time while the encrypted device is
                    # already unlocked although the filesystem isn't mounted.
                    self.create_encrypted_backup(source, destination)
                    # Verify that the backup was successful.
                    with active_mountpoint(MOUNT_POINT):
                        self.verify_destination(destination)

    def create_encrypted_backup(self, source, destination):
        """Create a backup to an encrypted device using the command line interface."""
        # Wipe an existing backup (if any).
        if os.path.isdir(destination):
            execute('rm', '--recursive', destination, sudo=True)
        # Create a new backup.
        exit_code, output = run_cli(
            main, '--crypto=%s' % CRYPTO_NAME,
            '--mount=%s' % MOUNT_POINT,
            '--disable-notifications',
            # We skip snapshot creation and rotation to minimize the number
            # of commands required in /etc/sudoers.d/rsync-system-backup.
            '--backup',
            source, destination,
        )
        assert exit_code == 0

    def test_missing_crypto_device(self):
        """Test that MissingBackupDiskError is raised as expected."""
        if not os.path.isdir(MOUNT_POINT):
            return self.skipTest("Skipping test because %s doesn't exist!", MOUNT_POINT)
        # Make sure the image file doesn't exist.
        if os.path.exists(IMAGE_FILE):
            os.unlink(IMAGE_FILE)
        # Ask rsync-system-backup to use the encrypted filesystem on the image
        # file anyway, because we know it will fail and that's exactly what
        # we're interested in :-).
        program = RsyncSystemBackup(
            crypto_device=CRYPTO_NAME,
            destination=os.path.join(MOUNT_POINT, 'latest'),
            mount_point=MOUNT_POINT,
            notifications_enabled=False,
        )
        self.assertRaises(MissingBackupDiskError, program.execute)

    def test_mount_failure(self):
        """Test that FailedToMountError is raised as expected."""
        if not os.path.isdir(MOUNT_POINT):
            return self.skipTest("Skipping test because %s doesn't exist!", MOUNT_POINT)
        with prepared_image_file(create_filesystem=False):
            program = RsyncSystemBackup(
                crypto_device=CRYPTO_NAME,
                destination=os.path.join(MOUNT_POINT, 'latest'),
                mount_point=MOUNT_POINT,
                notifications_enabled=False,
            )
            # When `mount' fails it should exit with a nonzero exit code,
            # thereby causing executor to raise an ExternalCommandFailed
            # exception that obscures the FailedToMountError exception that
            # we're interested in. The check=False option enables our
            # `last resort error handling' code path to be reached.
            program.destination_context.options['check'] = False
            self.assertRaises(FailedToMountError, program.execute)

    def test_invalid_destination_directory(self):
        """Test that InvalidDestinationDirectory is raised as expected."""
        if not os.path.isdir(MOUNT_POINT):
            return self.skipTest("Skipping test because %s doesn't exist!", MOUNT_POINT)
        with prepared_image_file():
            program = RsyncSystemBackup(
                crypto_device=CRYPTO_NAME,
                destination='/some/random/directory',
                mount_point=MOUNT_POINT,
                notifications_enabled=False,
            )
            self.assertRaises(InvalidDestinationDirectory, program.transfer_changes)

    def test_unsupported_platform_error(self):
        """Test that UnsupportedPlatformError is raised as expected."""
        with MockedProgram('uname'):
            program = RsyncSystemBackup(destination='/some/random/directory')
            self.assertRaises(UnsupportedPlatformError, program.execute)

    def test_unsupported_platform_with_force(self):
        """Test that UnsupportedPlatformError is raised as expected."""
        with MockedProgram('uname'):
            program = RsyncSystemBackup(destination='/some/random/directory', force=True)
            # Avoid making an actual backup.
            program.execute_helper = MagicMock()
            program.execute()
            assert program.execute_helper.called

    def test_backup_failure(self):
        """Test that an exception is raised when ``rsync`` fails."""
        program = RsyncSystemBackup(
            destination='0.0.0.0::module/directory',
            notifications_enabled=False,
            sudo_enabled=False,
        )
        self.assertRaises(ExternalCommandFailed, program.execute)

    def create_source(self, source):
        """Create a source directory for testing backups."""
        if not os.path.isdir(source):
            os.makedirs(source)
        # Create a text file in the source directory.
        text_file = os.path.join(source, 'notes.txt')
        with open(text_file, 'w') as handle:
            handle.write("This file should be included in the backup.\n")
        # Create a subdirectory in the source directory.
        subdirectory = os.path.join(source, 'subdirectory')
        os.mkdir(subdirectory)
        # Create a symbolic link in the subdirectory.
        symlink = os.path.join(subdirectory, 'symbolic-link')
        os.symlink('../include-me.txt', symlink)

    def verify_destination(self, destination):
        """Verify the contents of a destination directory."""
        # Make sure the text file was copied to the destination.
        text_file = os.path.join(destination, 'notes.txt')
        assert os.path.isfile(text_file)
        with open(text_file) as handle:
            assert handle.read() == "This file should be included in the backup.\n"
        # Make sure the subdirectory was copied to the destination.
        subdirectory = os.path.join(destination, 'subdirectory')
        assert os.path.isdir(subdirectory)
        # Make sure the symbolic link was copied to the destination.
        symlink = os.path.join(subdirectory, 'symbolic-link')
        assert os.path.islink(symlink)


@contextlib.contextmanager
def prepared_image_file(create_filesystem=True):
    """Prepare an image file containing an encrypted filesystem (ext4 on top of LUKS)."""
    with TemporaryKeyFile(filename=KEY_FILE):
        create_image_file(filename=IMAGE_FILE, size='10M')
        create_encrypted_filesystem(device_file=IMAGE_FILE, key_file=KEY_FILE)
        # Create a filesystem on the encrypted image file?
        if create_filesystem:
            with unlocked_device(CRYPTO_NAME):
                execute('mkfs.ext4', FILESYSTEM_DEVICE, sudo=True)
        yield
        os.unlink(IMAGE_FILE)


@contextlib.contextmanager
def unlocked_device(crypto_device):
    """Context manager that runs ``cryptdisks_start`` and ``cryptdisks_stop``."""
    cryptdisks_start(target=crypto_device)
    yield
    cryptdisks_stop(target=crypto_device)


@contextlib.contextmanager
def active_mountpoint(mount_point):
    """Context manager that runs ``mount`` and ``umount``."""
    execute('mount', mount_point, sudo=True)
    yield
    execute('umount', mount_point, sudo=True)


def find_snapshots(directory):
    """Abuse :mod:`rotate_backups` to scan a directory for snapshots."""
    helper = RotateBackups(DEFAULT_ROTATION_SCHEME)
    return helper.collect_backups(directory)
