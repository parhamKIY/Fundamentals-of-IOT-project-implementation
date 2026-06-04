import sqlite3
import random
import time
from datetime import datetime, timedelta


SIM_USERS = [
    ("SIM-ALI", "SIM-1001"),
    ("SIM-SARA", "SIM-1002"),
    ("SIM-REZA", "SIM-1003"),
    ("SIM-MINA", "SIM-1004"),
    ("SIM-NIMA", "SIM-1005"),
    ("SIM-TARA", "SIM-1006"),
]

RANDOM_SENSOR_INTERVAL_SECONDS = 30
MIN_RANDOM_PARK_SECONDS = 90


def ensure_sim_users(cursor):
    user_ids = []
    for username, plate_number in SIM_USERS:
        cursor.execute(
            "INSERT OR IGNORE INTO Users (username, password, plate_number) VALUES (?, ?, ?)",
            (username, "sim-pass", plate_number),
        )
        cursor.execute("SELECT id FROM Users WHERE username = ?", (username,))
        user_ids.append(cursor.fetchone()[0])
    return user_ids


def create_random_hourly_reservations(cursor, now):
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)
    hour_start_str = hour_start.strftime('%Y-%m-%d %H:%M:%S')
    hour_end_str = hour_end.strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("""
        SELECT COUNT(*)
        FROM Reservations r
        JOIN Users u ON r.user_id = u.id
        WHERE u.username LIKE 'SIM-%'
        AND r.start_time >= ?
        AND r.start_time < ?
    """, (hour_start_str, hour_end_str))
    existing_this_hour = cursor.fetchone()[0]
    target_this_hour = random.randint(3, 6)
    missing = max(0, target_this_hour - existing_this_hour)
    if missing == 0:
        return

    sim_user_ids = ensure_sim_users(cursor)
    cursor.execute("SELECT id FROM Parking_Spots ORDER BY RANDOM()")
    spot_ids = [row[0] for row in cursor.fetchall()]

    for spot_id in spot_ids:
        if missing == 0:
            break

        start_offset = random.randint(0, 45)
        duration = random.randint(20, 90)
        start_dt = hour_start + timedelta(minutes=start_offset)
        end_dt = min(start_dt + timedelta(minutes=duration), hour_end + timedelta(minutes=30))
        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            SELECT 1 FROM Reservations
            WHERE status = 'Active'
            AND spot_id = ?
            AND start_time < ?
            AND end_time > ?
            LIMIT 1
        """, (spot_id, end_str, start_str))
        if cursor.fetchone():
            continue

        cursor.execute("""
            INSERT INTO Reservations (user_id, spot_id, start_time, end_time, status)
            VALUES (?, ?, ?, ?, 'Active')
        """, (random.choice(sim_user_ids), spot_id, start_str, end_str))
        missing -= 1


def simulate_environment():
    print("IoT Smart Environment & Conflict Resolution Manager Activated...")
    physical_parked_since = {}
    last_random_sensor_at = datetime.min
    
    while True:
        conn = sqlite3.connect('parking.db')
        cursor = conn.cursor()
        now = datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        create_random_hourly_reservations(cursor, now)
        
        # ۱. پاکسازی رزروهای منقضی شده
        cursor.execute("SELECT spot_id, id FROM Reservations WHERE status = 'Active' AND end_time <= ?", (now_str,))
        for spot_id, res_id in cursor.fetchall():
            cursor.execute("UPDATE Parking_Spots SET is_occupied = 0 WHERE id = ?", (spot_id,))
            cursor.execute("UPDATE Reservations SET status = 'Completed' WHERE id = ?", (res_id,))
        
        # ۲. تخلیه اجباری جایگاه ۳۰ ثانیه قبل از شروع رزرو (فراری دادن ماشین متفرقه)
        clear_time = (now + timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT spot_id FROM Reservations WHERE status = 'Active' AND start_time > ? AND start_time <= ?", (now_str, clear_time))
        for (spot_id,) in cursor.fetchall():
            cursor.execute("UPDATE Parking_Spots SET is_occupied = 0 WHERE id = ?", (spot_id,))
        
        # ۳. ورود دقیق ماشین کاربرِ رزرو کننده در همان ثانیه شروع
        cursor.execute("SELECT spot_id FROM Reservations WHERE status = 'Active' AND start_time <= ? AND end_time > ?", (now_str, now_str))
        for (spot_id,) in cursor.fetchall():
            cursor.execute("UPDATE Parking_Spots SET is_occupied = 1 WHERE id = ?", (spot_id,))
            
        # ۴. سنسور رندوم (عدم اجازه ورود به جایگاه‌هایی که در ۱ دقیقه آینده رزرو دارند)
        if (now - last_random_sensor_at).total_seconds() >= RANDOM_SENSOR_INTERVAL_SECONDS:
            last_random_sensor_at = now
            buffer_time = (now + timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute("""
                SELECT id FROM Parking_Spots
                WHERE is_occupied = 0
                AND id NOT IN (
                    SELECT spot_id FROM Reservations
                    WHERE status = 'Active'
                    AND start_time <= ?
                    AND end_time > ?
                )
            """, (buffer_time, now_str))
            entry_candidates = [row[0] for row in cursor.fetchall()]

            cursor.execute("""
                SELECT id FROM Parking_Spots
                WHERE is_occupied = 1
                AND id NOT IN (
                    SELECT spot_id FROM Reservations
                    WHERE status = 'Active'
                    AND start_time <= ?
                    AND end_time > ?
                )
            """, (buffer_time, now_str))
            occupied_random_candidates = [row[0] for row in cursor.fetchall()]

            for spot_id in occupied_random_candidates:
                physical_parked_since.setdefault(spot_id, now)

            exit_candidates = [
                spot_id for spot_id in occupied_random_candidates
                if (now - physical_parked_since.get(spot_id, now)).total_seconds() >= MIN_RANDOM_PARK_SECONDS
            ]

            if entry_candidates and (not exit_candidates or random.random() < 0.7):
                random_spot = random.choice(entry_candidates)
                cursor.execute("UPDATE Parking_Spots SET is_occupied = 1 WHERE id = ?", (random_spot,))
                physical_parked_since[random_spot] = now
            elif exit_candidates:
                random_spot = random.choice(exit_candidates)
                cursor.execute("UPDATE Parking_Spots SET is_occupied = 0 WHERE id = ?", (random_spot,))
                physical_parked_since.pop(random_spot, None)
        
        conn.commit()
        conn.close()
        time.sleep(5)

if __name__ == "__main__":
    simulate_environment()
