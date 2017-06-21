# rsync-system-backup: Linux system backups powered by rsync.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: June 21, 2017
# URL: https://github.com/xolox/python-rsync-system-backup

"""Custom exceptions used by rsync-system-backup."""


class RsyncSystemBackupError(Exception):

    """Base exception for custom exceptions raised by rsync-system-backup."""


class InvalidDestinationError(RsyncSystemBackupError):

    """Raised when the given destination expression can't be parsed."""


class MissingBackupDiskError(RsyncSystemBackupError):

    """Raised when the encrypted filesystem isn't available."""


class FailedToUnlockError(RsyncSystemBackupError):

    """Raised when cryptdisks_start_ fails to unlock the encrypted device."""


class FailedToMountError(RsyncSystemBackupError):

    """Raised when mount_ fails to mount the backup destination."""


class DestinationContextUnavailable(RsyncSystemBackupError):

    """Raised when snapshot creation and rotation are disabled because we're connected to an rsync daemon."""


class ParentDirectoryUnavailable(RsyncSystemBackupError):

    """Raised when the parent directory of the backup directory cannot be determined."""
