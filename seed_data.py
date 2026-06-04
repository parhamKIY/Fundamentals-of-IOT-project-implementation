import sqlite3

def insert_initial_spots():
    conn = sqlite3.connect('parking.db')
    cursor = conn.cursor()
    
    # تعریف ۱۰ جای پارک برای طبقه اول (همگی در ابتدا خالی هستند)
    for spot_number in range(1, 11):
        cursor.execute(
            "INSERT OR IGNORE INTO Parking_Spots (id, floor, is_occupied) VALUES (?, ?, 0);",
            (spot_number, 1)
        )
        
    conn.commit()
    conn.close()
    
    # تغییر متن به انگلیسی برای جلوگیری از ارور انکودینگ ترمینال ویندوز
    print("Initial parking spots inserted successfully.")

if __name__ == "__main__":
    insert_initial_spots()