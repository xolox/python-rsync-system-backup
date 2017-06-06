rsync-system-backup: Linux system backups powered by rsync
==========================================================

.. image:: https://travis-ci.org/xolox/python-rsync-system-backup.svg?branch=master
   :target: https://travis-ci.org/xolox/python-rsync-system-backup

.. image:: https://coveralls.io/repos/xolox/python-rsync-system-backup/badge.svg?branch=master
   :target: https://coveralls.io/r/xolox/python-rsync-system-backup?branch=master

The rsync-system-backup program uses rsync_ to create full system backups of
Linux_ systems. Supported backup destinations include local disks (possibly
encrypted using LUKS_) and remote systems that are running an SSH_ server or
`rsync daemon`_. Each backup produces a timestamped snapshot and these
snapshots are rotated according to a rotation scheme that you can configure.
The package is currently tested on cPython 2.6, 2.7, 3.4, 3.5, 3.6 and PyPy
(2.7).

.. contents::
   :depth: 3
   :local:

Status
------

While this project brings together more than ten years of experience in
creating (system) backups using rsync_, all of the actual Python code was
written in the first few months of 2017 and hasn't seen much real world use.

.. warning:: I'm releasing this project as alpha software and I probably wont
             be changing that label until I've actually tried out each of the
             (supposedly) supported use cases for a while :-).

Nevertheless there is already 94% test coverage and my intention is to extend
the test coverage further. Also I will be switching each of my existing ad-hoc
backup scripts over to this project in the first half of 2017, so I may very
likely be the first user running into any bugs :-).

Installation
------------

The `rsync-system-backup` package is available on PyPI_ which means
installation should be as simple as:

.. code-block:: sh

   $ pip install rsync-system-backup

There's actually a multitude of ways to install Python packages (e.g. the `per
user site-packages directory`_, `virtual environments`_ or just installing
system wide) and I have no intention of getting into that discussion here, so
if this intimidates you then read up on your options before returning to these
instructions ;-).

Usage
-----

There are two ways to use the `rsync-system-backup` package: As the command
line program ``rsync-system-backup`` and as a Python API. For details about the
Python API please refer to the API documentation available on `Read the Docs`_.
The command line interface is described below.

Command line
~~~~~~~~~~~~

.. A DRY solution to avoid duplication of the `rsync-system-backup --help' text:
..
.. [[[cog
.. from humanfriendly.usage import inject_usage
.. inject_usage('rsync_system_backup.cli')
.. ]]]

**Usage:** `rsync-system-backup [OPTIONS] [SOURCE] DESTINATION`

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
   name. These snapshots are created using 'cp ``--archive`` ``--link``'.

3. Finally the existing snapshots are rotated to purge old backups
   according to a rotation scheme that you can customize.

**Supported options:**

.. csv-table::
   :header: Option, Description
   :widths: 30, 70


   "``-b``, ``--backup``","Create a backup using rsync but don't create a snapshot and don't rotate
   old snapshots unless the ``--snapshot`` and/or ``--rotate`` options are also given."
   "``-s``, ``--snapshot``","Create a snapshot of the destination directory but don't create a backup
   and don't rotate old snapshots unless the ``--backup`` and/or ``--rotate`` options
   are also given.
   
   This option can be used to create snapshots of an rsync daemon module using
   a 'post-xfer exec' command. If DESTINATION isn't given it defaults to the
   value of the environment variable ``$RSYNC_MODULE_PATH``."
   "``-r``, ``--rotate``","Rotate old snapshots but don't create a backup and snapshot unless the
   ``--backup`` and/or ``--snapshot`` options are also given.
   
   This option can be used to rotate old snapshots of an rsync daemon module
   using a 'post-xfer exec' command. If DESTINATION isn't given it defaults to
   the value of the environment variable ``$RSYNC_MODULE_PATH``."
   "``-m``, ``--mount=DIRECTORY``","Automatically mount the filesystem to which backups are written.
   
   When this option is given and ``DIRECTORY`` isn't already mounted, the
   'mount' command is used to mount the filesystem to which backups are
   written before the backup starts. When 'mount' was called before the
   backup started, 'umount' will be called when the backup finishes.
   
   An entry for the mount point needs to be
   defined in /etc/fstab for this to work."
   "``-c``, ``--crypto=NAME``","Automatically unlock the encrypted filesystem to which backups are written.
   
   When this option is given and the ``NAME`` device isn't already unlocked, the
   cryptdisks_start command is used to unlock the encrypted filesystem to
   which backups are written before the backup starts. When cryptdisks_start
   was called before the backup started, cryptdisks_stop will be called
   when the backup finishes.
   
   An entry for the encrypted filesystem needs to be defined in /etc/crypttab
   for this to work.
   
   If you want the backup process to run fully unattended you can configure a
   key file in /etc/crypttab, otherwise you will be asked for the password
   each time the encrypted filesystem is unlocked."
   "``-i``, ``--ionice=CLASS``","Use the 'ionice' program to set the I/O scheduling class and priority of
   the 'rm' invocations used to remove backups. ``CLASS`` is expected to be one of
   the values 'idle', 'best-effort' or 'realtime'. Refer to the man page of
   the 'ionice' program for details about these values."
   "``-u``, ``--no-sudo``","By default backup and snapshot creation is performed with superuser
   privileges, to ensure that all files are readable and filesystem
   metadata is preserved. The ``-u``, ``--no-sudo`` option disables
   the use of 'sudo' during these operations."
   "``-n``, ``--dry-run``","Don't make any changes, just report what would be done. This doesn't
   create a backup or snapshot but it does run rsync with the ``--dry-run``
   option."
   ``--disable-notifications``,"By default a desktop notification is shown (using notify-send) before the
   system backup starts and after the backup finishes. The use of this option
   disables the notifications (notify-send will not be called at all)."
   "``-v``, ``--verbose``",Make more noise (increase logging verbosity). Can be repeated.
   "``-q``, ``--quiet``",Make less noise (decrease logging verbosity). Can be repeated.
   "``-h``, ``--help``",Show this message and exit.

.. [[[end]]]

How it works
------------

I've been finetuning my approach to Linux system backups for years now and
during that time rsync_ has become my swiss army knife of choice :-). I also
believe that comprehensive documentation can be half the value of an open
source project. The following sections attempt to provide a high level
overview of my system backup strategy:

.. contents::
   :depth: 1
   :local:

The (lack of) backup format
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each backup is a full copy of the filesystem tree, stored in the form of
individual files and directories on the destination. This "backup format" makes
it really easy to navigate through and recover from backups because you can use
whatever method you are comfortable with, whether that is a file browser,
terminal, Python_ script or even chroot_ :-).

.. note:: You may want to configure updatedb_ to exclude the directory
          containing your system backups, otherwise the locate_ database
          will grow enormously.

Snapshots and hard links
~~~~~~~~~~~~~~~~~~~~~~~~

Every time a backup is made the same destination directory is updated with
additions, updates and deletions since the last backup. After the backup is
done a snapshot of the destination directory is created using the command ``cp
--archive --link`` with the current date and time encoded in the name.

Due to the use of `hard links`_ each "version" of a file is only stored once.
Because rsync_ by default doesn't modify files inplace it breaks `hard links`_
and thereby avoids modifying existing inodes_. This ensures that the contents
of snapshots don't change when a new backup updates existing files. The
combination of hard links and the avoidance of inplace modifications
effectively provides a limited form of deduplication_. Each snapshot requires a
couple of megabytes to store the directory names and hard links but the
contents of files aren't duplicated.

The article `Easy Automated Snapshot-Style Backups with Linux and Rsync`_
contains more details about this technique.

Rotation of snapshots
~~~~~~~~~~~~~~~~~~~~~

Snapshots can be rotated according to a flexible rotation scheme, for example
I've configured my laptop backup rotation to preserve the most recent 24 hourly
backups, 30 daily backups and endless monthly backups.

Backup destinations
~~~~~~~~~~~~~~~~~~~

While developing, maintaining and evolving backup scripts for various Linux
laptops and servers I've learned that backups for different systems require
different backup destinations and connection methods:

.. contents::
   :local:

Encrypted USB disks
+++++++++++++++++++

There's a LUKS_ encrypted USB disk on my desk at work that I use to keep
hourly, daily and monthly backups of my work laptop. The disk is connected
through the same USB hub that also connects my keyboard and mouse so I can't
really forget about it :-).

Automatic mounting
^^^^^^^^^^^^^^^^^^

Before the backup starts, the encrypted disk is automatically unlocked and
mounted. The use of a key file enables this process to run unattended in the
background. Once the backup is done the disk will be unmounted and locked
again, so that it can be unplugged at any time (as long as a backup isn't
running of course).

Local server (rsync daemon)
+++++++++++++++++++++++++++

My personal laptop transfers hourly backups to the `rsync daemon`_ running on
the server in my home network using a direct TCP connection without SSH. Most
of the time the laptop has an USB Ethernet adapter connected but the backup
runs fine over a wireless connection as well.

Remote server (rsync daemon over SSH tunnel)
++++++++++++++++++++++++++++++++++++++++++++

My VPS (virtual private server) transfers nightly backups to the `rsync
daemon`_ running on the server in my home network over an `SSH tunnel`_ in
order to encrypt the traffic and restrict access. The SSH account is configured
to allow tunneling but disallow command execution. This setup enables the rsync
client and server to run with root privileges without allowing the client to
run arbitrary commands on the server.

Alternative connection methods
------------------------------

Backing up to a local disk limits the effectiveness of backups but using SSH
access between systems gives you more than you bargained for, because you're
allowing arbitrary command execution. The `rsync daemon`_ provides an
alternative that does not allow arbitrary command execution. The following
sections discuss this option in more detail.

Using rsync daemon
~~~~~~~~~~~~~~~~~~

To be able to write files as root and preserve all filesystem metadata, rsync
must be running with root privileges. However most of my backups are stored on
remote systems and opening up remote root access over SSH just to transfer
backups feels like a very blunt way to solve the problem :-).

Fortunately another solution is available: Configure an rsync daemon on the
destination and instruct your rsync client to connect to the rsync daemon
instead of connecting to the remote system over SSH. The rsync daemon
configuration can restrict the access of the rsync client so that it can only
write to the directory that contains the backup tree.

In this setup no SSH connections are used and the traffic between the rsync
client and server is not encrypted. If this is a problem for you then continue
reading the next section.

Enabling rsync daemon
+++++++++++++++++++++

On Debian and derivatives like Ubuntu you can enable and configure an `rsync
daemon`_ quite easily:

1. Make sure that rsync is installed:

   .. code-block:: sh

      $ sudo apt-get install rsync

2. Enable the rsync daemon by editing ``/etc/default/rsync`` and changing the
   line ``RSYNC_ENABLE=false`` to ``RSYNC_ENABLE=true``. Here's a one liner
   that accomplishes the task:

   .. code-block:: sh

      $ sudo sed -i 's/RSYNC_ENABLE=false/RSYNC_ENABLE=true/' /etc/default/rsync
   
3. Create the configuration file ``/etc/rsyncd.conf`` and define at least
   one module. Here's an example based on my rsync daemon configuration:

   .. code-block:: ini

      # Global settings.
      max connections = 4
      log file = /var/log/rsyncd.log

      # Defaults for modules.
      read only = no
      uid = 0
      gid = 0

      # Daily backups of my VPS.
      [vps_backups]
      path = /mnt/backups/vps/latest
      post-xfer exec = /usr/sbin/process-vps-backups

      # Hourly backups of my personal laptop.
      [laptop_backups]
      path = /mnt/backups/laptop/latest
      post-xfer exec = /usr/sbin/process-laptop-backups

   The ``post-xfer exec`` directives configure the rsync daemon to create a
   snapshot once the backup is done and rotate old snapshots afterwards.

4. Once you've created ``/etc/rsyncd.conf`` you can start the rsync daemon:

   .. code-block:: sh

      $ sudo service rsync start

5. If you're using a firewall you should make sure that the rsync daemon port
   is whitelisted to allow incoming connections. The rsync daemon port number
   defaults to 873. Here's an iptables command to accomplish this:

   .. code-block:: sh

      $ sudo iptables -A INPUT -p tcp -m tcp --dport 873 -m comment --comment "rsync daemon" -j ACCEPT

Tunneling rsync daemon connections
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When your backups are transferred over the public internet you should
definitely use SSH to encrypt the traffic, but if you're at all security
conscious then you probably won't like having to open up remote root access
over SSH just to transfer backups :-).

The alternative is to use a non privileged SSH account to set up an `SSH
tunnel`_ that redirects network traffic to the rsync daemon. The login shell of
the SSH account can be set to ``/usr/sbin/nologin`` (or something similar like
``/bin/false``) to `disable command execution`_, in this case you need to pass
``-N`` to the SSH client.

Contact
-------

The latest version of `rsync-system-backup` is available on PyPI_ and GitHub_.
The documentation is hosted on `Read the Docs`_. For bug reports please create
an issue on GitHub_. If you have questions, suggestions, etc. feel free to send
me an e-mail at `peter@peterodding.com`_.

License
-------

This software is licensed under the `MIT license`_.

© 2017 Peter Odding.

.. External references:

.. _chroot: https://manpages.debian.org/chroot
.. _deduplication: https://en.wikipedia.org/wiki/Data_deduplication
.. _disable command execution: https://unix.stackexchange.com/questions/155139/does-usr-sbin-nologin-as-a-login-shell-serve-a-security-purpose
.. _Easy Automated Snapshot-Style Backups with Linux and Rsync: http://www.mikerubel.org/computers/rsync_snapshots/
.. _GitHub: https://github.com/xolox/python-rsync-system-backup
.. _hard links: https://en.wikipedia.org/wiki/Hard_link
.. _inodes: https://en.wikipedia.org/wiki/Inode
.. _Linux: https://en.wikipedia.org/wiki/Linux
.. _locate: https://manpages.debian.org/mlocate
.. _LUKS: https://en.wikipedia.org/wiki/Linux_Unified_Key_Setup
.. _MIT license: http://en.wikipedia.org/wiki/MIT_License
.. _per user site-packages directory: https://www.python.org/dev/peps/pep-0370/
.. _peter@peterodding.com: peter@peterodding.com
.. _PyPI: https://pypi.python.org/pypi/rsync-system-backup
.. _Python Package Index: https://pypi.python.org/pypi/rsync-system-backup
.. _Python: https://www.python.org/
.. _Read the Docs: https://rsync-system-backup.readthedocs.org
.. _rsync daemon: https://manpages.debian.org/rsyncd.conf
.. _rsync: http://en.wikipedia.org/wiki/rsync
.. _SSH: https://en.wikipedia.org/wiki/Secure_Shell
.. _SSH tunnel: https://en.wikipedia.org/wiki/Tunneling_protocol#Secure_Shell_tunneling
.. _updatedb: https://manpages.debian.org/updatedb
.. _virtual environments: http://docs.python-guide.org/en/latest/dev/virtualenvs/
