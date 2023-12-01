#!/usr/bin/env python3
import PyInstaller.__main__
import shutil

PyInstaller.__main__.run([
    'b0pperbot.py',
    '--onefile'
])

shutil.copyfile('./config.ini.template','./dist/config.ini')