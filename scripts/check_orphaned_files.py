"""Saqlash joyidagi (R2 yoki lokal disk) fayllarni DBdagi Photo yozuvlari bilan
solishtirib, "etim" (DBda hech qanday e'longa bog'lanmagan) va "yo'qolgan"
(DBda bor, lekin faylda topilmagan) fayllarni topadi.

Fayl nomlari uuid bo'lgani uchun R2 panelida qo'lda qidirish amaliy emas —
shu skript buni avtomatlashtiradi. Bir martalik, qo'lda ishga tushiriladigan
tekshiruv vositasi; doimiy/fon jarayoni sifatida ishlashga mo'ljallanmagan.

Ishlatish:
    python scripts/check_orphaned_files.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from shared.database import SessionLocal
from shared.models import Photo
from shared.storage import R2_BUCKET_NAME, R2_ENABLED, UPLOAD_DIR, list_all_filenames


def main() -> None:
    db = SessionLocal()
    try:
        db_filenames = {
            os.path.basename(file_path.split("?")[0])
            for (file_path,) in db.query(Photo.file_path).all()
        }
    finally:
        db.close()

    storage_filenames = list_all_filenames()

    orphaned = storage_filenames - db_filenames
    missing = db_filenames - storage_filenames

    location = f"R2 bucket \"{R2_BUCKET_NAME}\"" if R2_ENABLED else f"lokal papka \"{UPLOAD_DIR}\""
    print(f"Tekshirilayotgan joy: {location}")
    print(f"DBda ro'yxatdan o'tgan fayllar: {len(db_filenames)}")
    print(f"Saqlash joyidagi fayllar: {len(storage_filenames)}")
    print()

    if orphaned:
        print(f"ETIM FAYLLAR ({len(orphaned)} ta) — DBda hech qanday e'longa bog'lanmagan:")
        for name in sorted(orphaned):
            print(f"  {name}")
    else:
        print("Etim fayl topilmadi — delete_photo() to'g'ri ishlayapti.")

    print()

    if missing:
        print(f"YO'QOLGAN FAYLLAR ({len(missing)} ta) — DBda bor, lekin saqlash joyida topilmadi:")
        for name in sorted(missing):
            print(f"  {name}")
    else:
        print("Yo'qolgan fayl topilmadi.")


if __name__ == "__main__":
    main()
