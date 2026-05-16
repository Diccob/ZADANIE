import shutil
from datetime import datetime

source = "/home/user/database/smoke.db"

backup = (
    "/home/user/backups/"
    f"smoke_{datetime.now().strftime('%Y%m%d')}.db"
)

shutil.copy(source, backup)

print("backup created")
