# rsync-system-backup: Linux system backups powered by rsync.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: May 4, 2018
# URL: https://github.com/xolox/python-rsync-system-backup

"""Parsing of rsync destination syntax (and then some)."""

# Standard library modules.
import logging
import os
import re

# External dependencies.
from humanfriendly import compact
from property_manager import (
    PropertyManager,
    mutable_property,
    required_property,
    set_property,
)

# Modules included in our package.
from rsync_system_backup.exceptions import (
    InvalidDestinationError,
    ParentDirectoryUnavailable,
)

RSYNCD_PORT = 873
"""
The default port of the `rsync daemon`_ (an integer).

.. _rsync daemon: https://manpages.debian.org/rsyncd.conf
"""

LOCAL_DESTINATION = re.compile('^(?P<directory>.+)$')
"""
A compiled regular expression pattern to parse local destinations,
used as a fall back because it matches any nonempty string.
"""

SSH_DESTINATION = re.compile('''
    ^ ( (?P<username> [^@]+ ) @ )? # optional username
    (?P<hostname> [^:]+ ) :        # mandatory host name
    (?P<directory> .* )            # optional pathname
''', re.VERBOSE)
"""
A compiled regular expression pattern to parse remote destinations
of the form ``[USER@]HOST:DEST`` (using an SSH connection).
"""

SIMPLE_DAEMON_DESTINATION = re.compile('''
    ^ ( (?P<username> [^@]+ ) @ )? # optional username
    (?P<hostname> [^:]+ ) ::       # mandatory host name
    (?P<module> [^/]+ )            # mandatory module name
    ( / (?P<directory> .* ) )? $   # optional pathname (without leading slash)
''', re.VERBOSE)
"""
A compiled regular expression pattern to parse remote destinations of the
form ``[USER@]HOST::MODULE[/DIRECTORY]`` (using an rsync daemon connection).
"""

ADVANCED_DAEMON_DESTINATION = re.compile('''
    ^ rsync://                    # static prefix
    ( (?P<username>[^@]+) @ )?    # optional username
    (?P<hostname> [^:/]+ )        # mandatory host name
    ( : (?P<port_number> \d+ ) )? # optional port number
    / (?P<module> [^/]+ )         # mandatory module name
    ( / (?P<directory> .* ) )? $  # optional pathname (without leading slash)
''', re.VERBOSE)
"""
A compiled regular expression pattern to parse remote destinations of the form
``rsync://[USER@]HOST[:PORT]/MODULE[/DIRECTORY]`` (using an rsync daemon
connection).
"""

DESTINATION_PATTERNS = [
    ADVANCED_DAEMON_DESTINATION,
    SIMPLE_DAEMON_DESTINATION,
    SSH_DESTINATION,
    LOCAL_DESTINATION,
]
"""
A list of compiled regular expression patterns to match destination
expressions. The patterns are ordered by decreasing specificity.
"""


# Public identifiers that require documentation.
__all__ = (
    'logger',
    'RSYNCD_PORT',
    'LOCAL_DESTINATION',
    'SSH_DESTINATION',
    'SIMPLE_DAEMON_DESTINATION',
    'ADVANCED_DAEMON_DESTINATION',
    'DESTINATION_PATTERNS',
    'Destination',
)

# Initialize a logger for this module.
logger = logging.getLogger(__name__)


class Destination(PropertyManager):

    """
    The :class:`Destination` class represents a location where backups are stored.

    The :attr:`expression` property is a required property whose value is
    parsed to populate the values of the :attr:`username`, :attr:`hostname`,
    :attr:`port_number`, :attr:`module` and :attr:`directory` properties.

    When you read the value of the :attr:`expression` property you get back a
    computed value based on the values of the previously mentioned properties.
    This makes it possible to manipulate the destination before passing it on
    to rsync.
    """

    @required_property
    def expression(self):
        """
        The destination in rsync's command line syntax (a string).

        :raises: :exc:`.InvalidDestinationError` when you try to set
                  this property to a value that cannot be parsed.
        """
        if not (self.hostname or self.directory):
            # This is a bit tricky: Returning None here ensures that a
            # TypeError will be raised when a Destination object is
            # created without specifying a value for `expression'.
            return None
        value = 'rsync://' if self.module else ''
        if self.hostname:
            if self.username:
                value += self.username + '@'
            value += self.hostname
            if self.module:
                if self.port_number:
                    value += ':%s' % self.port_number
                value += '/' + self.module
            else:
                value += ':'
        if self.directory:
            value += self.directory
        return value

    @expression.setter
    def expression(self, value):
        """Automatically parse expression strings."""
        for pattern in DESTINATION_PATTERNS:
            match = pattern.match(value)
            if match:
                captures = match.groupdict()
                non_empty = dict((n, c) for n, c in captures.items() if c)
                self.set_properties(**non_empty)
                break
        else:
            msg = "Failed to parse expression! (%s)"
            raise InvalidDestinationError(msg % value)

    @mutable_property
    def directory(self):
        """The pathname of the directory where the backup should be written (a string)."""
        return ''

    @mutable_property
    def hostname(self):
        """The host name or IP address of a remote system (a string)."""
        return ''

    @mutable_property
    def module(self):
        """The name of a module exported by an `rsync daemon`_ (a string)."""
        return ''

    @mutable_property
    def parent_directory(self):
        """
        The pathname of the parent directory of the backup directory (a string).

        :raises: :exc:`.ParentDirectoryUnavailable` when the parent directory
                 can't be determined because :attr:`directory` is empty or '/'.
        """
        directory = os.path.dirname(self.directory.rstrip('/'))
        if not directory:
            raise ParentDirectoryUnavailable(compact("""
                Failed to determine the parent directory of the destination
                directory! This makes it impossible to create and rotate
                snapshots for the destination {dest}.
            """, dest=self.expression))
        return directory

    @mutable_property
    def port_number(self):
        """
        The port number of a remote `rsync daemon`_ (a number).

        When :attr:`ssh_tunnel` is set the value of :attr:`port_number`
        defaults to :attr:`executor.ssh.client.SecureTunnel.local_port`,
        otherwise it defaults to :data:`RSYNCD_PORT`.
        """
        return self.ssh_tunnel.local_port if self.ssh_tunnel is not None else RSYNCD_PORT

    @port_number.setter
    def port_number(self, value):
        """Automatically coerce port numbers to integers."""
        set_property(self, 'port_number', int(value))

    @mutable_property
    def ssh_tunnel(self):
        """A :class:`~executor.ssh.client.SecureTunnel` object or :data:`None` (defaults to :data:`None`)."""

    @mutable_property
    def username(self):
        """The username for connecting to a remote system (a string)."""
        return ''

    def __enter__(self):
        """Automatically open :attr:`ssh_tunnel` when required."""
        if self.ssh_tunnel:
            self.ssh_tunnel.__enter__()
        return self

    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        """Automatically close :attr:`ssh_tunnel` when required"""
        if self.ssh_tunnel:
            self.ssh_tunnel.__exit__(exc_type, exc_value, traceback)
