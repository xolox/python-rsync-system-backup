How to set up unattended backups to an encrypted USB disk
=========================================================

This document explains how to set up unattended Linux system backups to an
encrypted USB disk using LUKS filesystem encryption. These instructions are
tested on Ubuntu (to be more specific I've used this process on 12.04, 14.04
and 16.04) but I'd expect them to work just as well on Debian and Linux
distributions based on Debian.

.. contents::
   :local:

Prepare the disk encryption
---------------------------

.. contents::
   :local:

Create a key file
~~~~~~~~~~~~~~~~~

We will use a key file to enable `rsync-system-backup` to unlock the encrypted
USB disk without requiring user interaction due to a password prompt. Basically
the contents of the key file will serve as an alternate password that can be
used in a noninteractive setting.

.. code-block:: sh

   # Create a directory to store the key file.
   sudo mkdir -p /root/keys

   # Generate the key file from two kilobytes of pseudorandom data.
   sudo dd if=/dev/urandom of=/root/keys/backups.key bs=512 count=4

   # Make sure the directory and key file are private to the root user.
   sudo chown -R root:root /root/keys
   sudo chmod u=rwx,go= /root/keys
   sudo chmod u=r,go= /root/keys/backups.key

.. warning:: I'm assuming here that the computer that you want to create
             backups of already has full disk encryption. If this is not the
             case it means that anyone with physical access to the computer can
             just power it off, rip out the hard disk and extract the contents
             of ``/root/keys/backups.key``, compromising the security of your
             backups!

Enable encryption on the USB disk
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enabling encryption on the USB disk will effectively wipe the existing contents
of the disk, so you need to make sure of two things:

1. The existing contents of the disk have been backed up.
2. You're specifying the correct device file in the following command (please
   triple check or you might wipe the wrong disk).

.. code-block:: sh

   # Enable LUKS disk encryption on the USB disk.
   sudo cryptsetup luksFormat /dev/sdx /root/keys/backups.key

In the command above ``/dev/sdx`` is the device file (this is what you need to
change) and ``/root/keys/backups.key`` is the name of the key file that we
created in the previous step.

.. note:: Careful readers will notice that I'm not bothering to create
          a partition table on the USB disk. We don't need it :-).

Figuring out the correct device file
++++++++++++++++++++++++++++++++++++

If you don't know or you're not sure what the device file for the
``luksFormat`` command above should be, here's one relatively
foolproof way to figure it out:

1. Disconnect the USB disk from your computer.

2. Open a terminal and use the following command to observe
   new log entries being added to the system log::

    # Follow the system log (watch for new entries).
    sudo tail -fn 0 /var/log/syslog

3. Connect the USB disk to your computer and give the disk a few seconds to
   spin up and properly establish a USB connection to your computer.

4. Observe the entries that just appeared in the system log. If you study them
   carefully you should be able to figure out the name of the device file.

Configure a recovery password
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your computer's hard disk breaks or your computer is stolen you will lose
the key file required to unlock your encrypted backups, which would be rather
ironic but not in a fun way :-P. To avoid this situation we can configure the
disk encryption with a recovery password::

   # Configure a recovery password.
   sudo cryptsetup --key-file=/root/keys/backups.key luksAddKey /dev/sdx

In the command above ``/dev/sdx`` is the device file, this should be the same
device file you used in the previous step.

Configure the encrypted disk
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Once encryption has been enabled we can configure the encrypted disk
in ``/etc/crypttab``. To do so we first need to determine the unique
identifier of the encrypted disk::

 # Determine the UUID of the encrypted disk.
 sudo blkid /dev/sdx

In the command above ``/dev/sdx`` is the device file, this should be the same
device file you used in the previous step. The ``blkid`` command will output a
string called a UUID (a universally unique identifier), you need to copy this
to your clipboard (or have photographic memory). Now that we know the UUID we
can add the ``/etc/crypttab`` entry::

 # Use a text editor to configure the encrypted disk.
 sudo nano /etc/crypttab

If the file doesn't exist yet it implies that you're not using full disk
encryption on your computer. Please reconsider! But I digress. Now you need to
add a new line to the file, something like this::

 backups UUID=13f6e17e-8c8b-4009-a7b3-356992415141 /root/keys/backups.key luks,discard,noauto

Replace the part after ``UUID=`` with the output of ``blkid``. Everything else
should be fine as is, unless you've chosen a different location for the key
file.

Unlock the encrypted disk
~~~~~~~~~~~~~~~~~~~~~~~~~

Thanks to the ``/etc/crypttab`` entry that we added in the previous step,
unlocking the disk is very simple::

 sudo cryptdisks_start backups

This won't ask for a password because we configured a key file.

Prepare the encrypted filesystem
--------------------------------

.. contents::
   :local:

Format the encrypted filesystem
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After the encrypted disk is unlocked using ``cryptdisks_start`` the device file
``/dev/mapper/backups`` provides access to the unlocked data. Encrypting the
disk hasn't created an actual filesystem yet so that's what we'll do next::

 sudo mkfs.ext4 /dev/mapper/backups

Configure the encrypted filesystem
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We'll add an entry to ``/etc/fstab`` so that it's as easy to mount the
filesystem as it was easy to unlock the disk::

 # Use a text editor to configure the encrypted filesystem.
 sudo nano /etc/fstab

Add a new line to the file, something like this::

 /dev/mapper/backups /mnt/backups ext4 noauto,errors=remount-ro 0 0

Also make sure the mount point exists::

 sudo mkdir -p /mnt/backups

Mount the encrypted filesystem
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This should be familiar to most of you::

 sudo mount /mnt/backups

Decide on a directory layout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On my backup disks I am using a directory layout of multiple levels because my
backups and I go way back :-). The first level consists of the names I chose to
describe the laptops I've had over the years:

- /mnt/backups

  - zenbook
  - hp-probook
  - macbook-pro

Each of these directories has subdirectories with the names of the Ubuntu
releases that were installed on those laptops over the years:

- /mnt/backups

  - zenbook

    - lucid
    - precise

  - hp-probook

    - precise
    - trusty

  - macbook-pro

    - xenial

Each of the directories named after an Ubuntu release stores a collection of
timestamped system backups, something like this:

- /mnt/backups

  - zenbook

    - lucid

      - 2011-02-05 15:30
      - 2011-03-19 11:45

    - precise

      - 2013-04-10 14:00
      - 2013-05-10 14:00

  - hp-probook

    - precise

      - 2014-03-12 16:15

    - trusty

      - 2016-06-15 12:00

  - macbook-pro

    - xenial

      - 2017-03-19 23:15
      - 2017-04-01 12:34
      - 2017-05-02 17:00
      - latest

The dates were made up and in reality I have hundreds of timestamped system
backups, but you get the idea :-).

Whether you use the same directory layout or something simpler is up to you.

Install rsync-system-backup
---------------------------

There are several ways to install `rsync-system-backup`, for example::

 # Make sure pip (the Python package manager) is installed.
 sudo apt-get install python-pip

 # Use pip to install the Python package we need in /usr/local. The
 # executable will be available at /usr/local/bin/rsync-system-backup.
 sudo pip install --upgrade rsync-system-backup

You can can also install the Python package and its dependencies in your home
directory if you prefer that over "polluting" the system wide /usr/local
directory::

 # Use pip to install the Python package we need in ~/.local. The
 # executable will be available at ~/.local/bin/rsync-system-backup.
 pip install --upgrade --user rsync-system-backup

If that is still "too global" for your tastes then feel free to set up a
Python virtual environment ;-).

Create your first backup
------------------------

Here's an example of how you can create a system backup::

 sudo rsync-system-backup -c backups -m /mnt/backups /mnt/backups/latest

That last directory must be a subdirectory of ``/mnt/backups``, if you want to
keep things simple then just use ``/mnt/backups/latest`` (whatever you do,
don't just pass it ``/mnt/backups``).

If you get a "command not found" error from ``sudo`` try the following instead::

 sudo $(which rsync-system-backup) -c backups -m /mnt/backups /mnt/backups/latest

Configure unattended backups
----------------------------

The final part of this how-to configures your system to automatically run
`rsync-system-backup` at an interval of your choosing, for example once every
four hours. The easiest way to accomplish this is using cron. To do so we'll
create a new configuration file::

 # Use a text editor to configure unattended backups.
 sudo nano /etc/cron.d/rsync-system-backup

Create the file with the following contents::

 # Cron by default starts subcommands in a very sparse environment where the
 # $PATH contains just /usr/bin and /bin. Since we expect a reasonably sane
 # $PATH we have to set it ourselves:
 PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

 # Create a full system backup every four hours.
 0 */4 * * * root rsync-system-backup -c backups -m /mnt/backups /mnt/backups/latest

Depending on how you installed `rsync-system-backup` you may need to adjust the
``PATH`` variable or change the program name into an absolute pathname.

Silencing desktop notifications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the desktop notifications announcing the start and completion of a system
backup drive you bonkers, add the ``--disable-notifications`` option to the
`rsync-system-backup` command line.
