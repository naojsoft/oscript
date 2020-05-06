#! /usr/bin/env python
#
import os
from oscript.version import version

srcdir = os.path.dirname(__file__)

try:

    from setuptools import setup

except ImportError:
    from distutils.core import setup

def read(fname):
    buf = open(os.path.join(srcdir, fname), 'r').read()
    return buf

setup(
    name = "oscript",
    version = version,
    author = "Software Division, Subaru Telescope, NAOJ",
    author_email = "ocs@naoj.org",
    description = ("Modules for implementing OScript, "
                   "Subaru Telescope's Observation Script."),
    long_description = read('README.txt'),
    license = "BSD",
    keywords = "subaru, telescope, parsing, observation, script, tools",
    url = "http://naojsoft.github.com/oscript",
    packages = ['oscript',
                'oscript.DotParaFiles',
                'oscript.parse',
                'oscript.tests',
                ],
    package_data = { #'oscript.doc': ['manual/*.html'],
                     },
    python_requires = '>=3.5',
    install_requires = 'ply',  # & g2cam!
    scripts = ['scripts/check_ope'],
    classifiers = [
        "License :: OSI Approved :: BSD License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
)
