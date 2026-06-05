readme_content = """# 🚗 IoT 3D Smart Parking Simulation System

A comprehensive, full-stack IoT Smart Parking Management System featuring a real-time **Three.js 3D Diorama digital twin**, a robust **Flask RESTful API**, and an **automated IoT Edge hardware sensor simulator** with built-in physical conflict resolution logic.

---

## 🌟 Key Features

### 1. Real-Time 3D Digital Twin (Frontend)
- **Interactive Diorama:** Built with **Three.js (WebGL)**, rendering a stylized clay-animated diorama environment with custom lighting, shadows, and environment props (buildings, street lamps, animated trees).
- **Dynamic Pathfinding & Animations:** Smooth, step-by-step entry and exit route animations for vehicles using custom ease-in-out interpolation and angular physics mapping.
- **Dynamic Assets:** Loads external 3D vehicle assets (`.glb` format) and dynamically injects procedural textures/colors to differentiate user classes (e.g., specific colors for active reservation holders).
- **Operator Name Floating Tags:** High-fidelity 2D screen-projected tags tracking moving objects, displaying usernames dynamically bound to individual spots.
- **Smart Polling Mechanism:** Synchronizes UI state with the backend database every 2 seconds to guarantee accurate physical telemetry representation.

### 2. Robust RESTful Backend API (Flask)
- **Comprehensive API Surface:** Secure endpoints handling user registration, cryptographic password hashing (via `Werkzeug`), and multi-role (User/Admin) state tracking.
- **Transaction & Wallet Management:** Atomic database transactions supporting digital wallet top-ups, calculated hourly parking tariffs ($1/hour), and automated late-exit fine penalties ($1 per 10 minutes of delay).
- **Advanced Overlap Prevention:** Server-side algorithmic validation guaranteeing zero temporal and spatial double-booking conflicts across users and spots.

### 3. IoT Edge Sensor Simulator (`sensor_sim.py`)
- **Telemetry Grids Simulation:** Replicates real-world ultrasonic/geomagnetic parking spot sensors executing as an asynchronous background subprocess.
- **Automated Virtual Traffic:** Spawns autonomous simulator agents (`SIM_USERS`) to generate realistic, stochastic parking demand patterns.
- **Physical Conflict Resolution (IoT Logic):** - Automatically forces a spot clearance 30 seconds prior to a registered user's booking arrival time to simulate towing/alerting unauthorized vehicles.
  - Intercepts physical sensor triggers and blocks random vehicles from parking in spots reserved within a 1-minute buffer window.

### 4. Enterprise Admin Dashboard
- **Live Business Analytics:** Displays total user acquisition, overall bookings count, instantaneous active occupancy, and peak-usage spot distribution.
- **Manual Sensor Overrides:** Allows administrators to manually trigger sensor states (Occupied/Empty) to simulate hardware testing or emergency overrides.
- **Administrative Booking & Cancellations:** Authority to override standard reservation limits, book spots directly for arbitrary user IDs, or cancel active sessions with instantaneous physical release.

---

## 🏗️ System Architecture

The project adheres to a 4-Tier IoT Architectural Framework:

1. **Physical/Simulation Layer (`sensor_sim.py`):** Acts as the physical edge node matrix, collecting and pushing hardware telemetry directly to the shared persistence layer.
2. **Persistence Layer (`parking.db`):** Relational SQLite database utilizing ACID-compliant immediate transaction locks (`BEGIN IMMEDIATE`) to prevent race conditions during high-concurrency booking actions.
3. **Application/Service Layer (`app.py`):** A Flask RESTful server exposing business logic, validation guards, and security controls.
4. **Presentation/UI Layer (`index.html`):** A responsive, single-page client framework powered by Vanilla JavaScript and WebGL (Three.js) for visualization.

---

## 🗃️ Database Schema

### `Users` Table
- `id`: INTEGER, Primary Key
- `username`: TEXT, Unique
- `password`: TEXT (Cryptographic Hash)
- `plate_number`: TEXT
- `wallet_balance`: REAL (Default 0)

### `Parking_Spots` Table
- `id`: INTEGER, Primary Key
- `floor`: INTEGER
- `is_occupied`: BOOLEAN (Hardware Telemetry State)

### `Reservations` Table
- `id`: INTEGER, Primary Key
- `user_id`: INTEGER, Foreign Key ➡️ `Users(id)`
- `spot_id`: INTEGER, Foreign Key ➡️ `Parking_Spots(id)`
- `start_time`: TEXT (YYYY-MM-DD HH:MM:SS)
- `end_time`: TEXT (YYYY-MM-DD HH:MM:SS)
- `status`: TEXT ('Active', 'Completed', 'Cancelled')
- `price`: REAL

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- Modern web browser with WebGL enabled (Chrome, Firefox, Edge, Safari)

### Installation & Execution

1. **Clone the Repository:**