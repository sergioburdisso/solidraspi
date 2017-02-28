#!/usr/bin/python
# -*- coding: utf-8 -*-

import io
import os
import re

from setuptools import setup

name = 'solidraspi'
description=""

CWD = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(CWD, '%s/__init__.py' % name), encoding='utf8') as __init__py:
    __init__src = __init__py.read().decode('utf-8')

    RE = r"%s\s*=\s*['\"]([^'\"]+)['\"]"

    package = {
        '__version__' : re.search(RE % '__version__', __init__src).group(1),
        '__license__' : re.search(RE % '__license__', __init__src).group(1)
    }

with io.open(os.path.join(CWD, 'README.md'), encoding='utf8') as README:
    long_description = README.read()

setup(
    name = name,
    packages = [ name ],
    version = package['__version__'],
    description = description,
    long_description = long_description,
    author ='Sergio Burdisso',
    author_email = 'sergio.burdisso@gmail.com',
    license = package['__license__'],
    url='https://github.com/sergioburdisso/solidraspi',
    download_url = 'https://github.com/sergioburdisso/solidraspi/tarball/v%s'%package['__version__'],
    keywords = [ 'raspberry pi' ],
    classifiers = [
        "Programming Language :: Python :: Implementation :: PyPy",
        'Programming Language :: Python',
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7"
    ],
    include_package_data=True,
    install_requires = []
)