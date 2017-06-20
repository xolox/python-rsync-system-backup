# rsync-system-backup: Linux system backups powered by rsync.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: June 20, 2017
# URL: https://github.com/xolox/python-rsync-system-backup

"""Parsing of rsync destination syntax (and then some)."""

# Standard library modules.
import os
import re

# External dependencies.
from executor.ssh.client import SSH_PROGRAM_NAME, RemoteCommand
from executor.ssh.server import EphemeralTCPServer
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

# A compiled regular expression pattern to parse local destinations,
# used as a fall back because it matches any nonempty string.
LOCAL_DESTINATION = re.compile('^(?P<directory>.+)$')

# A compiled regular expression pattern to parse remote destinations
# of the form [USER@]HOST:DEST (using an SSH connection).
SSH_DESTINATION = re.compile('''
    ^ ( (?P<username> [^@]+ ) @ )? # optional username
    (?P<hostname> [^:]+ ) :        # mandatory host name
    (?P<directory> .* )            # optional pathname
''', re.VERBOSE)

# A compiled regular expression pattern to parse remote destinations
# of the form [USER@]HOST::DEST (using an rsync daemon connection).
SIMPLE_DAEMON_DESTINATION = re.compile('''
    ^ ( (?P<username> [^@]+ ) @ )? # optional username
    (?P<hostname> [^:]+ ) ::       # mandatory host name
    (?P<module> [^/]+ )            # mandatory module name
    ( / (?P<directory> .* ) )? $   # optional pathname (without leading slash)
''', re.VERBOSE)

# A compiled regular expression pattern to parse remote destinations of the
# form rsync://[USER@]HOST[:PORT]/DEST (using an rsync daemon connection).
ADVANCED_DAEMON_DESTINATION = re.compile('''
    ^ rsync://                    # static prefix
    ( (?P<username>[^@]+) @ )?    # optional username
    (?P<hostname> [^:/]+ )        # mandatory host name
    ( : (?P<port_number> \d+ ) )? # optional port number
    / (?P<module> [^/]+ )         # mandatory module name
    ( / (?P<directory> .* ) )? $  # optional pathname (without leading slash)
''', re.VERBOSE)

# A list of compiled regular expression patterns to match destination
# expressions. The patterns are ordered by decreasing specificity.
DESTINATION_PATTERNS = [
    ADVANCED_DAEMON_DESTINATION,
    SIMPLE_DAEMON_DESTINATION,
    SSH_DESTINATION,
    LOCAL_DESTINATION,
]


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
        """The port number of a remote `rsync daemon`_ (a number, defaults to :data:`RSYNCD_PORT`)."""
        return RSYNCD_PORT

    @port_number.setter
    def port_number(self, value):
        """Automatically coerce port numbers to integers."""
        set_property(self, 'port_number', int(value))

    @mutable_property
    def username(self):
        """The username for connecting to a remote system (a string)."""
        return ''

    def __enter__(self):
        """
        Enable using :class:`Destination` objects as context managers.

        The need to support using :class:`Destination` objects as context
        managers is that :class:`ForwardedDestination` requires to be used
        as a context manager. Yes, I'm letting subclasses affect their base
        classes. This is not a code smell, it's a feature ;-).
        """
        return self

    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        """Enable using :class:`Destination` objects as context managers."""


class ForwardedDestination(Destination, RemoteCommand, EphemeralTCPServer):

    """
    The :class:`ForwardedDestination` class represents a tunneled `rsync daemon`_ connection over SSH.

    This class is a somewhat awkward composition of three base classes:

    - :class:`Destination`
    - :class:`~executor.ssh.client.RemoteCommand`
    - :class:`~executor.ssh.server.EphemeralTCPServer`

    Each of these classes has a significant number of properties whose names
    were never intended to be unambiguous among each other when composed like
    this, because we're dealing with two host names and three port numbers:

    ==========================================================  ========================================================
    Property                                                    Description
    ==========================================================  ========================================================
    :attr:`executor.ssh.client.RemoteAccount.ssh_alias`         The SSH alias, host name or IP address of the SSH server
                                                                that is tunneling the rsync daemon connection.
    :attr:`executor.ssh.client.RemoteCommand.port`              The port number on which the SSH server is listening.
    :attr:`Destination.hostname`                                The host name or IP address of the rsync daemon (which
                                                                the SSH server connects to on behalf of the SSH client).
    :attr:`ForwardedDestination.remote_port`                    The port number on which the rsync daemon is listening.
    :attr:`executor.ssh.server.EphemeralTCPServer.port_number`  Overrides :attr:`Destination.port_number` and defines
                                                                the port number on which the SSH client will be
                                                                listening and forwarding connections to the SSH server
                                                                (which in turn forwards them to the rsync daemon).
    ==========================================================  ========================================================

    To summarize: While I've managed to avoid naming collisions this is
    definitely a bit messy and confusing.
    """

    @property
    def ssh_command(self):
        """
        The command used to run the SSH client program.

        This property overrides :attr:`~executor.ssh.client.RemoteCommand.ssh_command`
        to inject the command line option ``-L`` that opens a TCP tunnel.
        """
        command = [SSH_PROGRAM_NAME]
        # Enable compression by default, but allow opting out.
        if self.compression:
            command.append('-C')
        # Do not execute a remote command. This enables compatibility with
        # `tunnel only' SSH accounts that have their shell set to something
        # like /usr/sbin/nologin.
        command.append('-N')
        # Forward the connection from our local rsync client to the remote
        # rsync daemon over the SSH connection.
        command.extend(['-L', '%i:%s:%i' % (self.port_number, self.hostname, self.remote_port)])
        command.append(self.ssh_alias)
        return command

    @mutable_property
    def compression(self):
        """Whether compression should be enabled (a boolean, defaults to :data:`True`)."""
        return True

    @mutable_property
    def remote_port(self):
        """The TCP port that the `rsync daemon`_ is listening on (an integer, defaults to :data:`RSYNCD_PORT`)."""
        return RSYNCD_PORT
