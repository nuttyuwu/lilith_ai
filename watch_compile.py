#!/usr/bin/env python3
"""
Watch Python files in the current directory and automatically compile them when they change.
Run this in a separate terminal while editing to get instant compile feedback.
"""
import os
import sys
import time
import py_compile
from pathlib import Path
from datetime import datetime

# files to watch (add more if needed)
WATCH_FILES = [
    'lilith.py',
    'viewer.py'
]

def get_mtime(file):
    """Get modification time of a file or 0 if it doesn't exist."""
    try:
        return os.path.getmtime(file)
    except OSError:
        return 0

def compile_file(file):
    """Compile a Python file and print the result."""
    try:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Compiling {file}...")
        py_compile.compile(file, doraise=True)
        print(f"✓ {file} compiled successfully")
        return True
    except Exception as e:
        print(f"✗ {file} has errors:\n{str(e)}")
        return False

def main():
    # get base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # track last modified times
    last_mtimes = {f: get_mtime(os.path.join(base_dir, f)) for f in WATCH_FILES}
    
    print(f"Watching Python files for changes (Ctrl+C to stop):")
    for f in WATCH_FILES:
        print(f"  {f}")
    
    try:
        while True:
            for file in WATCH_FILES:
                filepath = os.path.join(base_dir, file)
                mtime = get_mtime(filepath)
                
                if mtime > last_mtimes[file]:
                    compile_file(filepath)
                    last_mtimes[file] = mtime
            
            time.sleep(1)  # check every second
    
    except KeyboardInterrupt:
        print("\nStopped watching files.")

if __name__ == "__main__":
    main()