"""
Gemini TTS Interface - Main Entry Point
"""

import sys
import os

# Ensure the root directory is on the python search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.gui import GeminiTTSApp


def main():
    app = GeminiTTSApp()
    app.mainloop()


if __name__ == "__main__":
    main()
