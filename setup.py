#!/usr/bin/env python

# Setup script for the `rsync-system-backup' package.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: May 5, 2017
# URL: https://github.com/xolox/python-rsync-system-backup

"""
Setup script for the ``rsync-system-backup`` package.

**python setup.py install**
  Install from the working directory into the current Python environment.

**python setup.py sdist**
  Build a source distribution archive.

**python setup.py bdist_wheel**
  Build a wheel distribution archive.
"""

# Standard library modules.
import codecs
import os
import re

# De-facto standard solution for Python packaging.
from setuptools import find_packages, setup


def get_contents(*args):
    """Get the contents of a file relative to the source distribution directory."""
    with codecs.open(get_absolute_path(*args), 'r', 'UTF-8') as handle:
        return handle.read()


def get_version(*args):
    """Extract the version number from a Python module."""
    contents = get_contents(*args)
    metadata = dict(re.findall('__([a-z]+)__ = [\'"]([^\'"]+)', contents))
    return metadata['version']


def get_requirements(*args):
    """Get requirements from pip requirement files."""
    requirements = set()
    with open(get_absolute_path(*args)) as handle:
        for line in handle:
            # Strip comments.
            line = re.sub(r'^#.*|\s#.*', '', line)
            # Ignore empty lines
            if line and not line.isspace():
                requirements.add(re.sub(r'\s+', '', line))
    return sorted(requirements)


def get_absolute_path(*args):
    """Transform relative pathnames into absolute pathnames."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *args)


setup(name="rsync-system-backup",
      version=get_version('rsync_system_backup', '__init__.py'),
      description="Linux system backups powered by rsync",
      long_description=get_contents('README.rst'),
      url='https://github.com/xolox/python-rsync-system-backup',
      author="Peter Odding",
      author_email='peter@peterodding.com',
      packages=find_packages(),
      entry_points=dict(console_scripts=[
          'rsync-system-backup = rsync_system_backup.cli:main',
      ]),
      install_requires=get_requirements('requirements.txt'),
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: MIT License',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: Implementation :: CPython',
          'Programming Language :: Python :: Implementation :: PyPy',
          'Topic :: Software Development',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: System :: Archiving :: Backup',
          'Topic :: System :: Systems Administration',
      ])
