import os
import subprocess

if not os.path.exists(".env"):
    with open(".env", "w", encoding="utf-8") as f:
        f.write("BOT_TOKEN=замени_на_свой\nADMIN_ID=замени_на_ID\n")

subprocess.call(["pip", "install", "-r", "requirements.txt"])
subprocess.call(["python", "main.py"])
