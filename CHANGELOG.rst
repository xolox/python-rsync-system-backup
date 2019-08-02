Changelog
=========

The purpose of this document is to list all of the notable changes to this
project. The format was inspired by `Keep a Changelog`_. This project adheres
to `semantic versioning`_.

.. contents::
   :local:

.. _Keep a Changelog: http://keepachangelog.com/
.. _semantic versioning: http://semver.org/

`Release 1.1`_ (2019-08-02)
---------------------------

- The ``--multi-fs`` option suggested in pull request `#3`_ was added.

  This option has the opposite effect of the rsync option ``--one-file-system``
  because `rsync-system-backup` defaults to running rsync with
  ``--one-file-system`` and must be instructed not to using ``--multi-fs``."

  This change was merged by cherry picking the relevant commit from the remote
  branch, to avoid pulling in unrelated changes (see the pull request for
  details).

- Stop testing on Python 2.6 (because Travis CI no longer supports it and
  working around this would cost an unreasonable amount of time) and start
  testing support for Python 3.7.

.. _Release 1.1: https://github.com/xolox/python-rsync-system-backup/compare/1.0...1.1
.. _#3: https://github.com/xolox/python-rsync-system-backup/pull/3

`Release 1.0`_ (2018-05-04)
---------------------------

**Bug fix: SSH tunnel support actually works now :-P (backwards incompatible).**

This week I switched the backups of my VPS over to `rsync-system-backup`. The
biggest hurdle was the fact that I never finished nor tested support for SSH
tunnels in `rsync-system-backup` which I needed now:

- The command line interface didn't expose the functionality.
- Due to various bugs it wouldn't have worked even if the
  functionality had been exposed.

The changes in this release:

- Added the ``-t``, ``--tunnel`` command line option.
- Integrated SSH tunnel support provided by `executor 19.3`_.
- Removed the ``ForwardedDestination`` class (this functionality has been
  replaced by the new ``Destination.ssh_tunnel`` property).

Because the removal of ``ForwardedDestination`` is backwards incompatible I've
decided to bump the major version number. It's actually kind of fitting because
I've been using `rsync-system-backup` for local backups for months now and
that's working fine; the main thing missing was indeed SSH tunnel support :-).

.. _Release 1.0: https://github.com/xolox/python-rsync-system-backup/compare/0.11...1.0
.. _executor 19.3: http://executor.readthedocs.io/en/latest/changelog.html#release-19-3-2018-05-04

`Release 0.11`_ (2018-04-30)
----------------------------

- Added support for the ``-x``, ``--exclude`` option.
- Documented that ``--one-file-system`` is always used.

.. _Release 0.11: https://github.com/xolox/python-rsync-system-backup/compare/0.10...0.11

`Release 0.10`_ (2018-04-30)
----------------------------

- Switched to the more user friendly ``getopt.gnu_getopt()``.
- Added this changelog, restructured the online documentation.
- Documented the ``-f``, ``--force`` option in the readme.
- Integrated the use of ``property_manager.sphinx``.

.. _Release 0.10: https://github.com/xolox/python-rsync-system-backup/compare/0.9...0.10

`Release 0.9`_ (2017-07-11)
---------------------------

Explicitly handle unsupported platforms (by refusing to run without the
``-f``, ``--force`` option). Refer to issue `#1`_ for more information.

.. _Release 0.9: https://github.com/xolox/python-rsync-system-backup/compare/0.8...0.9
.. _#1: https://github.com/xolox/python-rsync-system-backup/issues/1

`Release 0.8`_ (2017-06-24)
---------------------------

Don't raise an exception when ``notify-send`` fails to deliver a desktop notification.

.. _Release 0.8: https://github.com/xolox/python-rsync-system-backup/compare/0.7...0.8

`Release 0.7`_ (2017-06-23)
---------------------------

Ensure the destination directory is located under the expected mount point.

.. _Release 0.7: https://github.com/xolox/python-rsync-system-backup/compare/0.6...0.7

`Release 0.6`_ (2017-06-23)
---------------------------

Incorporated the ``cryptdisks_start`` and ``cryptdisks_stop`` fallbacks into the how-to.

.. _Release 0.6: https://github.com/xolox/python-rsync-system-backup/compare/0.5...0.6

`Release 0.5`_ (2017-06-21)
---------------------------

Gain independence from ``cryptdisks_start`` and ``cryptdisks_stop`` (a Debian-ism).

.. _Release 0.5: https://github.com/xolox/python-rsync-system-backup/compare/0.4...0.5

`Release 0.4`_ (2017-06-21)
---------------------------

- Gracefully handle missing backup disk.
- Added a how-to to the documentation.

.. _Release 0.4: https://github.com/xolox/python-rsync-system-backup/compare/0.3...0.4

`Release 0.3`_ (2017-06-06)
---------------------------

Made it possible to disable desktop notifications.

.. _Release 0.3: https://github.com/xolox/python-rsync-system-backup/compare/0.2...0.3

`Release 0.2`_ (2017-05-06)
---------------------------

- Don't render a traceback on known errors.
- Fixed broken usage message formatting.
- Document Python 3.6 compatibility.
- Changed Sphinx theme.

.. _Release 0.2: https://github.com/xolox/python-rsync-system-backup/compare/0.1.1...0.2

`Release 0.1.1`_ (2017-04-17)
-----------------------------

Changed system logging verbosity level from DEBUG to INFO.

.. _Release 0.1.1: https://github.com/xolox/python-rsync-system-backup/compare/0.1...0.1.1

`Release 0.1`_ (2017-04-14)
---------------------------

Initial release (0.1, alpha).

.. _Release 0.1: https://github.com/xolox/python-rsync-system-backup/tree/0.1
