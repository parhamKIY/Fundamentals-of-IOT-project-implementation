import sqlite3

def init_database():
    # 1. Connect to the database file, creating it when it does not exist.
    conn = sqlite3.connect('parking.db')
    cursor = conn.cursor()

    # 2. Enable foreign-key enforcement for this SQLite connection.
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 3. Define the users table.
    create_users_table = """
    CREATE TABLE IF NOT EXISTS Users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        plate_number TEXT NOT NULL,
        wallet_balance REAL DEFAULT 0
    );
    """

    # 4. Define the parking-spots table.
    create_spots_table = """
    CREATE TABLE IF NOT EXISTS Parking_Spots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        floor INTEGER NOT NULL,
        is_occupied BOOLEAN DEFAULT 0
    );
    """

    # 5. Define the reservations table.
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

    # 6. Create any tables that are not already present.
    cursor.execute(create_users_table)
    cursor.execute(create_spots_table)
    cursor.execute(create_reservations_table)

    # 7. Persist the schema changes and close the connection.
    conn.commit()
    conn.close()
    
    print("Database and tables created successfully.")

if __name__ == "__main__":
    init_database()
