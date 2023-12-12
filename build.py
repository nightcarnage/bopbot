#!/usr/bin/env python3
import PyInstaller.__main__
import shutil

PyInstaller.__main__.run([
    'bopbot.py',
    '--onefile'
])

shutil.copyfile('./config.template.ini','./dist/config.ini')