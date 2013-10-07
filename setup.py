"""
This is a setup.py script generated by py2applet

Usage:
    python setup.py py2app
"""

import py2app
from setuptools import setup

APP = ['Vodacom Data Usage.py']
DATA_FILES =  [('icons', ['icons/app_24x24.png',
                          'icons/app_128x128.icns',
                          'icons/app_128x128.png',
                          'icons/refresh_24x24.png',
                          'icons/summary_24x24.png']),
               ('conf', ['conf/Vodacom Data Usage.conf',
                         'conf/logger.conf']),
               ('logs', ['logs/Vodacom Data Usage.log']),
               ('', ['README.md',
                     'LICENSE'])]
OPTIONS = {
    #'argv_emulation': True,
    'plist': {
        'LSUIElement': True,
    },
    'packages': ['rumps'], 
    'iconfile': 'icons/app_128x128.icns'
}

setup(
    app=APP,
    name='Vodacom Data Usage',
    version='1.0.0',
    description='Status Item app to monitor Vodacom data usage.',
    author='Pieter Rautenbach',
    url='http://www.whatsthatlight.com/',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
