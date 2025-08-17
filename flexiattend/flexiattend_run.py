import sys
import os

# Add apps folder to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from flexiattend.triggers.flexiattend_bot import app

if __name__ == "__main__":
    app.run_polling()
