import os

# Force offscreen Qt platform for tests to avoid display issues
os.environ["QT_QPA_PLATFORM"] = "offscreen"
