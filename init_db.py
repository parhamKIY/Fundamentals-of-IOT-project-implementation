import sqlite3

def init_database():
    # ۱. اتصال به فایل دیتابیس (اگر فایل وجود نداشته باشد، ساخته می‌شود)
    conn = sqlite3.connect('parking.db')
    cursor = conn.cursor()

    # ۲. فعال کردن قابلیت Foreign Key در SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")

    # ۳. ساخت جدول کاربران
    create_users_table = """
    CREATE TABLE IF NOT EXISTS Users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        plate_number TEXT NOT NULL,
        wallet_balance REAL DEFAULT 0
    );
    """

    # ۴. ساخت جدول فضاهای پارک
    create_spots_table = """
    CREATE TABLE IF NOT EXISTS Parking_Spots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        floor INTEGER NOT NULL,
        is_occupied BOOLEAN DEFAULT 0
    );
    """

    # ۵. ساخت جدول رزروها
    create_reservations_table = """
    CREATE TABLE IF NOT EXISTS Reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        spot_id INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT DEFAULT 'Active',
        price REAL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
        FOREIGN KEY (spot_id) REFERENCES Parking_Spots (id) ON DELETE CASCADE
    );
    """

    # ۶. اجرای دستورات SQL
    cursor.execute(create_users_table)
    cursor.execute(create_spots_table)
    cursor.execute(create_reservations_table)

    # ۷. ذخیره تغییرات و بستن اتصال
    conn.commit()
    conn.close()
    
    # تغییر این خط برای جلوگیری از ارور انکودینگ ویندوز
    print("Database and tables created successfully.")

if __name__ == "__main__":
    init_database()
