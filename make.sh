#!/bin/bash
rm -rf build dist
#arch -32 -arch i386 python setup.py py2app
arch -32 python2.7 setup.py py2app
