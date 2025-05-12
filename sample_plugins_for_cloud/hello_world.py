print("Hello from Python Plugin!")
import sys
print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}")
import time
print("Working for 3 seconds...")
time.sleep(3)
print("Python plugin finished.")