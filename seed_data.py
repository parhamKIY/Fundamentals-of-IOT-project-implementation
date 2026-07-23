import sqlite3

def insert_initial_spots():
    conn = sqlite3.connect('parking.db')
    cursor = conn.cursor()
    
    # Seed ten initially empty parking spots on the first floor.
    for spot_number in range(1, 11):
        cursor.execute(
            "INSERT OR IGNORE INTO Parking_Spots (id, floor, is_occupied) VALUES (?, ?, 0);",
            (spot_number, 1)
        )
        
    conn.commit()
    conn.close()
    
    # Keep console output ASCII-compatible for Windows terminals.
    print("Initial parking spots inserted successfully.")

if __name__ == "__main__":
    insert_initial_spots()
