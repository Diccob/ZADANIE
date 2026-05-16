import os
import shutil
from datetime import datetime

# =========================
# ПУТИ
# =========================

DB_PATH = "/app/shared/smokes.db"

BACKUP_DIR = "/app/shared/backups"

# =========================
# СОЗДАНИЕ ПАПКИ
# =========================

os.makedirs(BACKUP_DIR, exist_ok=True)

# =========================
# ИМЯ БЭКАПА
# =========================

timestamp = datetime.now().strftime(
    "%Y-%m-%d_%H-%M-%S"
)

backup_name = f"smokes_backup_{timestamp}.db"

backup_path = os.path.join(
    BACKUP_DIR,
    backup_name
)

# =========================
# СОЗДАНИЕ БЭКАПА
# =========================

try:

    shutil.copy2(DB_PATH, backup_path)

    print(
        f"✅ Backup создан: "
        f"{backup_path}"
    )

except Exception as e:

    print(
        f"❌ Ошибка backup: {e}"
    )
