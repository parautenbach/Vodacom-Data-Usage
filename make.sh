#!/bin/bash
rm -rf build dist
python setup.py py2app --iconfile icons/app_128x128.icns
