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
                'oscript.util',
                'oscript.tests',
                ],
    package_data = { #'oscript.doc': ['manual/*.html'],
                     },
    python_requires = '>=3.7',
    # NOTE: also requires g2cam (https://github.com/naojsoft/g2cam)
    install_requires = 'ply>=3.11',
    scripts = ['scripts/check_ope', 'scripts/sk_lexer', 'scripts/sk_parser',
               'scripts/sk_decode', 'scripts/para_lexer', 'scripts/para_parser',
               'scripts/para_validator', 'scripts/testfunc_sk_parser'],
    classifiers = [
        "License :: OSI Approved :: BSD License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
)
