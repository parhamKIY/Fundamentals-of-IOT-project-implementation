from datetime import datetime, timedelta
import os
import sqlite3
import subprocess
import sys
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from werkzeug.security import check_password_hash, generate_password_hash


# Run the sensor simulator alongside the API without enabling Flask's reloader,
# which would otherwise start a duplicate simulator process.
sensor_process = subprocess.Popen([sys.executable, "sensor_sim.py"])

print("Sensor simulator started in the background.")
print("Continuing app.py execution...")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ADMIN_PIN = os.environ.get("PARKING_ADMIN_PIN", "admin123")
EARLY_EXIT_GRACE_SECONDS = 30
ADMIN_USERNAME = "ADMIN"
ADMIN_PASSWORD = "1234"


SPOT_COORDINATES = {
    1: {"x": -4.35, "z": -2.45, "rotation": 3.141592653589793},
    2: {"x": -2.18, "z": -2.45, "rotation": 3.141592653589793},
    3: {"x": 0, "z": -2.45, "rotation": 3.141592653589793},
    4: {"x": 2.18, "z": -2.45, "rotation": 3.141592653589793},
    5: {"x": 4.35, "z": -2.45, "rotation": 3.141592653589793},
    6: {"x": -4.35, "z": 2.45, "rotation": 0},
    7: {"x": -2.18, "z": 2.45, "rotation": 0},
    8: {"x": 0, "z": 2.45, "rotation": 0},
    9: {"x": 2.18, "z": 2.45, "rotation": 0},
    10: {"x": 4.35, "z": 2.45, "rotation": 0},
}


def broadcast_spot_status(spot_id, is_occupied, source=None, reserved_by=None):
    socketio.emit(
        "spot_status_update",
        {
            "spot_id": int(spot_id),
            "is_occupied": bool(is_occupied),
            "source": source,
            "reserved_by": reserved_by,
        },
    )


def get_db_connection():
    conn = sqlite3.connect("parking.db")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def ensure_schema(conn):
    # Apply lightweight migrations so existing databases remain compatible.
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';").fetchall()
    }
    if "Users" not in tables or "Reservations" not in tables:
        return

    user_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(Users);").fetchall()
    }
    if "wallet_balance" not in user_columns:
        conn.execute("ALTER TABLE Users ADD COLUMN wallet_balance REAL DEFAULT 0;")

    reservation_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(Reservations);").fetchall()
    }
    if "price" not in reservation_columns:
        conn.execute("ALTER TABLE Reservations ADD COLUMN price REAL DEFAULT 0;")

    conn.commit()


def parse_time(value):
    if not value:
        raise ValueError("Missing time field")
    return datetime.strptime(value, TIME_FORMAT)


def validate_time_range(start_time, end_time):
    start_dt = parse_time(start_time)
    end_dt = parse_time(end_time)
    if end_dt <= start_dt:
        raise ValueError("End time must be after start time")
    return start_dt, end_dt


def calculate_base_price(start_dt, end_dt):
    hours = (end_dt - start_dt).total_seconds() / 3600
    return round(hours, 2)


def has_spot_overlap(cursor, spot_id, start_time, end_time):
    return cursor.execute(
        """
        SELECT 1 FROM Reservations
        WHERE status = 'Active'
        AND spot_id = ?
        AND start_time < ?
        AND end_time > ?
        LIMIT 1;
        """,
        (spot_id, end_time, start_time),
    ).fetchone() is not None


def has_user_overlap(cursor, user_id, start_time, end_time):
    return cursor.execute(
        """
        SELECT 1 FROM Reservations
        WHERE status = 'Active'
        AND user_id = ?
        AND start_time < ?
        AND end_time > ?
        LIMIT 1;
        """,
        (user_id, end_time, start_time),
    ).fetchone() is not None


def spot_exists(cursor, spot_id):
    return cursor.execute(
        "SELECT id, floor, is_occupied FROM Parking_Spots WHERE id = ?;",
        (spot_id,),
    ).fetchone()


def user_exists(cursor, user_id):
    return cursor.execute(
        "SELECT id FROM Users WHERE id = ?;",
        (user_id,),
    ).fetchone() is not None


def is_admin_user_id(cursor, user_id):
    if not user_id:
        return False
    user = cursor.execute(
        "SELECT username FROM Users WHERE id = ?;",
        (user_id,),
    ).fetchone()
    return bool(user and user["username"] == ADMIN_USERNAME)


def get_admin_user_id(cursor):
    user = cursor.execute(
        "SELECT id FROM Users WHERE username = ?;",
        (ADMIN_USERNAME,),
    ).fetchone()
    if user:
        return user["id"]

    cursor.execute(
        "INSERT INTO Users (username, password, plate_number, wallet_balance) VALUES (?, ?, ?, 0);",
        (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), "ADMIN"),
    )
    return cursor.lastrowid


def get_walk_in_user_id(cursor):
    username = "WALK-IN-CUSTOMER"
    user = cursor.execute(
        "SELECT id FROM Users WHERE username = ?;",
        (username,),
    ).fetchone()
    if user:
        return user["id"]

    cursor.execute(
        "INSERT INTO Users (username, password, plate_number, wallet_balance) VALUES (?, ?, ?, 0);",
        (username, generate_password_hash("walk-in"), "WALK-IN"),
    )
    return cursor.lastrowid


def get_wallet_balance(cursor, user_id):
    row = cursor.execute(
        "SELECT wallet_balance FROM Users WHERE id = ?;",
        (user_id,),
    ).fetchone()
    return round(float(row["wallet_balance"] or 0), 2) if row else None


def sync_reservations_with_clock(cursor):
    # Reconcile reservation status and physical occupancy with the current time.
    now_str = datetime.now().strftime(TIME_FORMAT)
    early_exit_limit = (datetime.now() - timedelta(seconds=EARLY_EXIT_GRACE_SECONDS)).strftime(TIME_FORMAT)

    cursor.execute(
        """
        UPDATE Reservations
        SET status = 'Completed'
        WHERE status = 'Active'
        AND start_time <= ?
        AND end_time > ?
        AND spot_id IN (
            SELECT id FROM Parking_Spots
            WHERE is_occupied = 0
        );
        """,
        (early_exit_limit, now_str),
    )

    expired_spots = [
        row["spot_id"]
        for row in cursor.execute(
            """
            SELECT DISTINCT spot_id FROM Reservations
            WHERE status = 'Active'
            AND end_time <= ?;
            """,
            (now_str,),
        ).fetchall()
    ]

    cursor.execute(
        """
        UPDATE Reservations
        SET status = 'Completed'
        WHERE status = 'Active'
        AND end_time <= ?;
        """,
        (now_str,),
    )

    cursor.execute(
        """
        UPDATE Parking_Spots
        SET is_occupied = 1
        WHERE id IN (
            SELECT spot_id FROM Reservations
            WHERE status = 'Active'
            AND start_time <= ?
            AND end_time > ?
        );
        """,
        (now_str, now_str),
    )

    for spot_id in expired_spots:
        has_current_reservation = cursor.execute(
            """
            SELECT 1 FROM Reservations
            WHERE status = 'Active'
            AND spot_id = ?
            AND start_time <= ?
            AND end_time > ?
            LIMIT 1;
            """,
            (spot_id, now_str, now_str),
        ).fetchone()
        if not has_current_reservation:
            cursor.execute(
                "UPDATE Parking_Spots SET is_occupied = 0 WHERE id = ?;",
                (spot_id,),
            )


def is_physically_available_by_start(cursor, spot, start_dt, start_time, end_time):
    # Near-term reservations require an empty spot; later bookings may use a spot
    # that is expected to become free before the requested start time.
    now = datetime.now()
    has_current_reservation = cursor.execute(
        """
        SELECT 1 FROM Reservations
        WHERE status = 'Active'
        AND spot_id = ?
        AND start_time <= ?
        AND end_time > ?
        LIMIT 1;
        """,
        (spot["id"], now.strftime(TIME_FORMAT), now.strftime(TIME_FORMAT)),
    ).fetchone()

    if not spot["is_occupied"] and not has_current_reservation:
        return True

    current_active = cursor.execute(
        """
        SELECT end_time FROM Reservations
        WHERE status = 'Active'
        AND spot_id = ?
        AND start_time <= datetime('now', 'localtime')
        AND end_time > datetime('now', 'localtime')
        ORDER BY end_time ASC
        LIMIT 1;
        """,
        (spot["id"],),
    ).fetchone()

    if current_active and current_active["end_time"] <= start_time:
        return True

    if start_dt <= now + timedelta(minutes=15):
        return False

    sensor_block = cursor.execute(
        """
        SELECT 1 FROM Reservations
        WHERE status = 'Active'
        AND spot_id = ?
        AND start_time < ?
        AND end_time > ?
        LIMIT 1;
        """,
        (spot["id"], end_time, now.strftime(TIME_FORMAT)),
    ).fetchone()
    return sensor_block is None


def is_spot_available(cursor, spot, start_time, end_time, start_dt):
    if has_spot_overlap(cursor, spot["id"], start_time, end_time):
        return False
    return is_physically_available_by_start(cursor, spot, start_dt, start_time, end_time)


def is_admin_request():
    user_id = request.headers.get("X-User-Id")
    conn = get_db_connection()
    cursor = conn.cursor()
    is_admin = is_admin_user_id(cursor, user_id)
    conn.close()
    return is_admin


@app.route("/api/spots", methods=["GET"])
def get_parking_spots():
    conn = get_db_connection()
    cursor = conn.cursor()
    sync_reservations_with_clock(cursor)
    conn.commit()
    cursor.execute(
        """
        SELECT ps.id, ps.floor, ps.is_occupied, u.username
        FROM Parking_Spots ps
        LEFT JOIN Reservations r ON ps.id = r.spot_id
             AND r.status = 'Active'
             AND r.start_time <= datetime('now', 'localtime')
             AND r.end_time >= datetime('now', 'localtime')
        LEFT JOIN Users u ON r.user_id = u.id;
        """
    )
    spots = cursor.fetchall()
    conn.close()

    return jsonify(
        [
            {
                "id": s["id"],
                "floor": s["floor"],
                "is_occupied": bool(s["is_occupied"]),
                "reserved_by": None if (s["username"] or "").startswith("WALK-IN-") else s["username"],
            }
            for s in spots
        ]
    )


@app.route("/api/search_spots", methods=["POST"])
def search_spots():
    data = request.get_json() or {}
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    user_id = data.get("user_id")

    try:
        start_dt, end_dt = validate_time_range(start_time, end_time)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    sync_reservations_with_clock(cursor)
    conn.commit()

    if user_id and has_user_overlap(cursor, user_id, start_time, end_time):
        conn.close()
        return jsonify({"error": "You already have an active reservation in this time range."}), 409

    spots = [
        spot
        for spot in cursor.execute(
            "SELECT id, floor, is_occupied FROM Parking_Spots ORDER BY id ASC;"
        ).fetchall()
        if is_spot_available(cursor, spot, start_time, end_time, start_dt)
    ]
    conn.close()

    return jsonify(
        {
            "spots": [{"id": s["id"], "floor": s["floor"]} for s in spots],
            "price": calculate_base_price(start_dt, end_dt),
            "pricing_note": "Parking costs $1 per hour. If you leave late, a $1 penalty is charged for each 10 minutes of delay.",
        }
    ), 200


@app.route("/api/reserve", methods=["POST"])
def reserve_spot():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    spot_id = data.get("spot_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    payment_confirmed = data.get("payment_confirmed") is True

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        start_dt, end_dt = validate_time_range(start_time, end_time)
        if not user_id or not spot_id:
            return jsonify({"error": "Missing user or spot"}), 400

        user_is_admin = is_admin_user_id(cursor, user_id)

        if not payment_confirmed and not user_is_admin:
            return jsonify({"error": "Payment is required before confirming reservation."}), 402

        # Lock before checking availability to prevent concurrent double booking.
        cursor.execute("BEGIN IMMEDIATE;")
        sync_reservations_with_clock(cursor)

        spot = spot_exists(cursor, spot_id)
        if not spot:
            conn.rollback()
            return jsonify({"error": "Parking spot not found"}), 404

        if not user_exists(cursor, user_id):
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        if has_user_overlap(cursor, user_id, start_time, end_time) and not user_is_admin:
            conn.rollback()
            return jsonify({"error": "You already have an active reservation in this time range."}), 409

        if not is_spot_available(cursor, spot, start_time, end_time, start_dt):
            conn.rollback()
            return jsonify({"error": "This spot is not available for the selected time range."}), 409

        price = 0 if user_is_admin else calculate_base_price(start_dt, end_dt)
        wallet_balance = get_wallet_balance(cursor, user_id)
        if not user_is_admin and wallet_balance < price:
            conn.rollback()
            return jsonify({"error": "Wallet balance is not enough for this reservation."}), 402

        if not user_is_admin:
            cursor.execute(
                "UPDATE Users SET wallet_balance = wallet_balance - ? WHERE id = ?;",
                (price, user_id),
            )

        cursor.execute(
            """
            INSERT INTO Reservations (user_id, spot_id, start_time, end_time, status, price)
            VALUES (?, ?, ?, ?, 'Active', ?);
            """,
            (user_id, spot_id, start_time, end_time, price),
        )
        conn.commit()
        return jsonify(
            {
                "message": f"Spot #{spot_id} reserved successfully",
                "price": price,
                "wallet_balance": get_wallet_balance(cursor, user_id),
            }
        ), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/auto_reserve", methods=["POST"])
def auto_reserve_spot():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    payment_confirmed = data.get("payment_confirmed") is True

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        start_dt, end_dt = validate_time_range(start_time, end_time)
        if not user_id:
            return jsonify({"error": "Missing user"}), 400

        user_is_admin = is_admin_user_id(cursor, user_id)
        if not payment_confirmed and not user_is_admin:
            return jsonify({"error": "Payment is required before confirming reservation."}), 402

        cursor.execute("BEGIN IMMEDIATE;")
        sync_reservations_with_clock(cursor)

        if not user_exists(cursor, user_id):
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        if has_user_overlap(cursor, user_id, start_time, end_time) and not user_is_admin:
            conn.rollback()
            return jsonify({"error": "You already have an active reservation in this time range."}), 409

        first_available_spot = None
        for spot in cursor.execute(
            "SELECT id, floor, is_occupied FROM Parking_Spots ORDER BY id ASC;"
        ).fetchall():
            if is_spot_available(cursor, spot, start_time, end_time, start_dt):
                first_available_spot = spot
                break

        if not first_available_spot:
            conn.rollback()
            return jsonify({"error": "No reservable parking spots are available for the selected time range."}), 409

        price = 0 if user_is_admin else calculate_base_price(start_dt, end_dt)
        wallet_balance = get_wallet_balance(cursor, user_id)
        if not user_is_admin and wallet_balance < price:
            conn.rollback()
            return jsonify({"error": "Wallet balance is not enough for this reservation."}), 402

        if not user_is_admin:
            cursor.execute(
                "UPDATE Users SET wallet_balance = wallet_balance - ? WHERE id = ?;",
                (price, user_id),
            )

        cursor.execute(
            """
            INSERT INTO Reservations (user_id, spot_id, start_time, end_time, status, price)
            VALUES (?, ?, ?, ?, 'Active', ?);
            """,
            (user_id, first_available_spot["id"], start_time, end_time, price),
        )
        conn.commit()
        return jsonify(
            {
                "message": f"Spot #{first_available_spot['id']} reserved automatically",
                "spot_id": first_available_spot["id"],
                "price": price,
                "wallet_balance": get_wallet_balance(cursor, user_id),
            }
        ), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/admin/analytics", methods=["GET"])
def admin_analytics():
    if not is_admin_request():
        return jsonify({"error": "Admin access is required"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    sync_reservations_with_clock(cursor)
    conn.commit()

    total_users = cursor.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
    total_reservations = cursor.execute("SELECT COUNT(*) FROM Reservations").fetchone()[0]
    active_reservations = cursor.execute(
        "SELECT COUNT(*) FROM Reservations WHERE status = 'Active'"
    ).fetchone()[0]

    cursor.execute(
        """
        SELECT spot_id, COUNT(spot_id) as c
        FROM Reservations
        GROUP BY spot_id
        ORDER BY c DESC
        LIMIT 1;
        """
    )
    top_spot_row = cursor.fetchone()
    top_spot = f"#{top_spot_row['spot_id']} ({top_spot_row['c']} times)" if top_spot_row else "-"

    conn.close()
    return jsonify(
        {
            "total_users": total_users,
            "total_reservations": total_reservations,
            "active_reservations": active_reservations,
            "top_spot": top_spot,
        }
    )


@app.route("/api/admin/transactions", methods=["GET"])
def admin_transactions():
    if not is_admin_request():
        return jsonify({"error": "Admin access is required"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    sync_reservations_with_clock(cursor)
    conn.commit()
    cursor.execute(
        """
        SELECT r.spot_id, r.start_time, r.status, u.username
        FROM Reservations r
        JOIN Users u ON r.user_id = u.id
        ORDER BY r.id DESC
        LIMIT 5;
        """
    )
    transactions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(transactions)


@app.route("/api/admin/reservations", methods=["GET"])
def admin_reservations():
    if not is_admin_request():
        return jsonify({"error": "Admin access is required"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    sync_reservations_with_clock(cursor)
    conn.commit()
    cursor.execute(
        """
        SELECT r.id, r.spot_id, r.start_time, r.end_time, r.status, u.username
        FROM Reservations r
        JOIN Users u ON r.user_id = u.id
        WHERE r.status = 'Active'
        ORDER BY r.start_time ASC, r.spot_id ASC;
        """
    )
    reservations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(reservations)


@app.route("/api/admin/reserve_any", methods=["POST"])
def admin_reserve_any():
    if not is_admin_request():
        return jsonify({"error": "Admin access is required"}), 401

    data = request.get_json() or {}
    spot_id = data.get("spot_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    user_id = data.get("user_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        validate_time_range(start_time, end_time)
        if not spot_id:
            return jsonify({"error": "Missing spot"}), 400

        cursor.execute("BEGIN IMMEDIATE;")
        sync_reservations_with_clock(cursor)

        spot = spot_exists(cursor, spot_id)
        if not spot:
            conn.rollback()
            return jsonify({"error": "Parking spot not found"}), 404

        admin_user_id = get_admin_user_id(cursor)
        target_user_id = user_id or admin_user_id
        if not user_exists(cursor, target_user_id):
            conn.rollback()
            return jsonify({"error": "User not found"}), 404

        cursor.execute(
            """
            UPDATE Reservations
            SET status = 'Cancelled'
            WHERE status = 'Active'
            AND spot_id = ?
            AND start_time < ?
            AND end_time > ?;
            """,
            (spot_id, end_time, start_time),
        )
        cursor.execute(
            """
            INSERT INTO Reservations (user_id, spot_id, start_time, end_time, status)
            VALUES (?, ?, ?, ?, 'Active');
            """,
            (target_user_id, spot_id, start_time, end_time),
        )
        conn.commit()
        return jsonify({"message": f"Spot #{spot_id} reserved by admin"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/admin/cancel_reservation/<int:reservation_id>", methods=["POST"])
def admin_cancel_reservation(reservation_id):
    if not is_admin_request():
        return jsonify({"error": "Admin access is required"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        cursor.execute("BEGIN IMMEDIATE;")
        reservation = cursor.execute(
            "SELECT spot_id FROM Reservations WHERE id = ? AND status = 'Active';",
            (reservation_id,),
        ).fetchone()
        if not reservation:
            conn.rollback()
            return jsonify({"error": "Active reservation not found"}), 404

        cursor.execute(
            "UPDATE Reservations SET status = 'Cancelled' WHERE id = ?;",
            (reservation_id,),
        )
        cursor.execute(
            """
            SELECT 1 FROM Reservations
            WHERE status = 'Active'
            AND spot_id = ?
            AND start_time <= datetime('now', 'localtime')
            AND end_time > datetime('now', 'localtime')
            LIMIT 1;
            """,
            (reservation["spot_id"],),
        )
        if not cursor.fetchone():
            cursor.execute(
                "UPDATE Parking_Spots SET is_occupied = 0 WHERE id = ?;",
                (reservation["spot_id"],),
            )

        conn.commit()
        return jsonify({"message": "Reservation cancelled"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/wallet/<int:user_id>", methods=["GET"])
def user_wallet(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if not user_exists(cursor, user_id):
        conn.close()
        return jsonify({"error": "User not found"}), 404

    wallet_balance = get_wallet_balance(cursor, user_id)
    conn.close()
    return jsonify({"wallet_balance": wallet_balance}), 200


@app.route("/api/wallet/topup", methods=["POST"])
def top_up_wallet():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    amount = data.get("amount")

    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid top-up amount"}), 400

    if amount <= 0:
        return jsonify({"error": "Top-up amount must be positive"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE;")
        if not user_exists(cursor, user_id):
            conn.rollback()
            return jsonify({"error": "User not found"}), 404
        cursor.execute(
            "UPDATE Users SET wallet_balance = wallet_balance + ? WHERE id = ?;",
            (amount, user_id),
        )
        conn.commit()
        return jsonify(
            {
                "message": f"Wallet charged by ${amount:.2f}",
                "wallet_balance": get_wallet_balance(cursor, user_id),
            }
        ), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/user/reservations/<int:user_id>", methods=["GET"])
def user_reservations(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    sync_reservations_with_clock(cursor)
    conn.commit()
    if not user_exists(cursor, user_id):
        conn.close()
        return jsonify({"error": "User not found"}), 404

    cursor.execute(
        """
        SELECT id, spot_id, start_time, end_time, status, price
        FROM Reservations
        WHERE user_id = ?
        AND status = 'Active'
        ORDER BY start_time ASC;
        """,
        (user_id,),
    )
    reservations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(reservations), 200


@app.route("/api/user/cancel_reservation/<int:reservation_id>", methods=["POST"])
def user_cancel_reservation(reservation_id):
    data = request.get_json() or {}
    user_id = data.get("user_id")
    now_str = datetime.now().strftime(TIME_FORMAT)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        cursor.execute("BEGIN IMMEDIATE;")
        reservation = cursor.execute(
            """
            SELECT id, user_id, spot_id, start_time, price
            FROM Reservations
            WHERE id = ?
            AND user_id = ?
            AND status = 'Active';
            """,
            (reservation_id, user_id),
        ).fetchone()
        if not reservation:
            conn.rollback()
            return jsonify({"error": "Active reservation not found"}), 404

        if reservation["start_time"] <= now_str:
            conn.rollback()
            return jsonify({"error": "Reservation can only be cancelled before its start time."}), 409

        refund = round(float(reservation["price"] or 0), 2)
        cursor.execute(
            "UPDATE Reservations SET status = 'Cancelled' WHERE id = ?;",
            (reservation_id,),
        )
        cursor.execute(
            "UPDATE Users SET wallet_balance = wallet_balance + ? WHERE id = ?;",
            (refund, user_id),
        )
        cursor.execute(
            """
            SELECT 1 FROM Reservations
            WHERE status = 'Active'
            AND spot_id = ?
            AND start_time <= datetime('now', 'localtime')
            AND end_time > datetime('now', 'localtime')
            LIMIT 1;
            """,
            (reservation["spot_id"],),
        )
        if not cursor.fetchone():
            cursor.execute(
                "UPDATE Parking_Spots SET is_occupied = 0 WHERE id = ?;",
                (reservation["spot_id"],),
            )

        conn.commit()
        return jsonify(
            {
                "message": f"Reservation cancelled. ${refund:.2f} refunded to wallet.",
                "refund": refund,
                "wallet_balance": get_wallet_balance(cursor, user_id),
            }
        ), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/admin/sensor_spot", methods=["POST"])
def admin_sensor_spot():
    if not is_admin_request():
        return jsonify({"error": "Admin access is required"}), 401

    data = request.get_json() or {}
    spot_id = data.get("spot_id")
    is_occupied = data.get("is_occupied")
    if is_occupied not in (True, False):
        return jsonify({"error": "Sensor status must be true or false"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE;")
        if not spot_exists(cursor, spot_id):
            conn.rollback()
            return jsonify({"error": "Parking spot not found"}), 404
        cursor.execute(
            "UPDATE Parking_Spots SET is_occupied = ? WHERE id = ?;",
            (1 if is_occupied else 0, spot_id),
        )
        conn.commit()
        broadcast_spot_status(spot_id, is_occupied)
        status = "occupied" if is_occupied else "empty"
        return jsonify({"message": f"Sensor for spot #{spot_id} set to {status}"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/sensor/spot_status", methods=["POST"])
def sensor_spot_status():
    data = request.get_json() or {}
    spot_id = data.get("spot_id")
    is_occupied = data.get("is_occupied")
    if is_occupied not in (True, False):
        return jsonify({"error": "Sensor status must be true or false"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if not spot_exists(cursor, spot_id):
            return jsonify({"error": "Parking spot not found"}), 404
        broadcast_spot_status(spot_id, is_occupied)
        return jsonify({"message": "Spot status broadcast"}), 200
    finally:
        conn.close()


@app.route("/api/sensor/walk_in_arrival", methods=["POST"])
def sensor_walk_in_arrival():
    socketio.emit("walk_in_arrival", {"created_at": datetime.now().strftime(TIME_FORMAT)})
    return jsonify({"message": "Walk-in arrival broadcast"}), 200


@app.route("/api/bookings/on-site", methods=["POST"])
def create_on_site_booking():
    now = datetime.now()
    start_time = now.strftime(TIME_FORMAT)
    end_time = (now + timedelta(minutes=20)).strftime(TIME_FORMAT)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        cursor.execute("BEGIN IMMEDIATE;")
        sync_reservations_with_clock(cursor)
        spot = cursor.execute(
            """
            SELECT id, floor, is_occupied
            FROM Parking_Spots
            WHERE is_occupied = 0
            ORDER BY id ASC
            LIMIT 1;
            """
        ).fetchone()
        if not spot:
            conn.rollback()
            return jsonify({"error": "No empty spot is available for walk-in booking."}), 409

        user_id = get_walk_in_user_id(cursor)
        cursor.execute(
            """
            INSERT INTO Reservations (user_id, spot_id, start_time, end_time, status, price)
            VALUES (?, ?, ?, ?, 'Active', 0);
            """,
            (user_id, spot["id"], start_time, end_time),
        )
        cursor.execute(
            "UPDATE Parking_Spots SET is_occupied = 1 WHERE id = ?;",
            (spot["id"],),
        )
        conn.commit()

        broadcast_spot_status(spot["id"], True, source="walk_in", reserved_by=None)
        return jsonify(
            {
                "spot_id": spot["id"],
                "is_occupied": True,
                "coordinates": SPOT_COORDINATES.get(spot["id"]),
                "start_time": start_time,
                "end_time": end_time,
            }
        ), 201
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    plate_number = (data.get("plate_number") or "").strip()

    if not username or not password or not plate_number:
        return jsonify({"error": "All fields are required"}), 400

    try:
        conn = get_db_connection()
        conn.cursor().execute(
            "INSERT INTO Users (username, password, plate_number, wallet_balance) VALUES (?, ?, ?, 0)",
            (username, generate_password_hash(password), plate_number),
        )
        conn.commit()
        conn.close()
        return jsonify({"message": "Registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username exists"}), 400


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password") or ""

    conn = get_db_connection()
    cursor = conn.cursor()
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        admin_user_id = get_admin_user_id(cursor)
        conn.commit()
        conn.close()
        return jsonify({"user_id": admin_user_id, "username": ADMIN_USERNAME, "is_admin": True}), 200

    cursor.execute("SELECT id, username, password FROM Users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if user:
        stored_password = user["password"]
        if stored_password.startswith(("pbkdf2:", "scrypt:")):
            password_ok = check_password_hash(stored_password, password)
        else:
            password_ok = stored_password == password
            if password_ok:
                cursor.execute(
                    "UPDATE Users SET password = ? WHERE id = ?",
                    (generate_password_hash(password), user["id"]),
                )
                conn.commit()

        if password_ok:
            wallet_balance = get_wallet_balance(cursor, user["id"])
            conn.close()
            return jsonify(
                {
                    "user_id": user["id"],
                    "username": user["username"],
                    "is_admin": user["username"] == ADMIN_USERNAME,
                    "wallet_balance": wallet_balance,
                }
            ), 200

    conn.close()
    return jsonify({"error": "Invalid credentials"}), 401


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, use_reloader=False, allow_unsafe_werkzeug=True)
