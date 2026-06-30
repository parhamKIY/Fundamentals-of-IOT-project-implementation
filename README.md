# 🚗 IoT 3D Smart Parking Simulation System

A comprehensive, full-stack IoT Smart Parking Management System featuring a real-time **Three.js 3D Diorama digital twin**, an event-driven **Flask-SocketIO backend**, and an **automated IoT Edge hardware sensor simulator** with multi-stage animation and physical conflict resolution logic.

---

## 🌟 Key Features

### 1. Real-Time 3D Digital Twin & State Machine (Frontend)
- **Interactive Diorama:** Built with **Three.js (WebGL)**, rendering a stylized clay-animated diorama environment with custom lighting, shadows, and environment props.
- **Multi-Stage Vehicle State Machine:** Dynamically differentiates vehicle behavior based on booking methods:
  - **Online Pre-Bookings (Dark Blue Cars):** Spawn at the entrance with floating username tags and route directly to their reserved spots.
  - **On-Site Walk-In Bookings (Procedural Colorful Cars):** Spawn randomly, route to the entrance lane, halt for a 3-second transaction window, and dynamically reroute to an available spot provisioned in real-time by the backend.
- **Overhead-Visible Kiosk Animations:** Replaced vertical obscured window animations with a high-visibility, top-down animated 3D floating transaction indicator above the booth roof, optimized for isometric camera views.
- **Polished Scene Constraints:** Completely removed legacy placeholder barrier blocks for a cleaner aesthetic, and configured restricted `OrbitControls` (`maxPolarAngle`, `minDistance`, `maxDistance`) to guarantee robust camera positioning without ground-clipping.
- **Event-Driven Real-Time Synchronization:** Replaced legacy 2-second HTTP polling with a **WebSockets (Socket.IO)** client pipeline, rendering database and sensor telemetry state updates instantaneously.

### 2. Robust RESTful & Event-Driven Backend (Flask)
- **Hybrid Real-Time Architecture:** Integrated `Flask-SocketIO` to instantly broadcast global `spot_status_update` events whenever sensor data or database states fluctuate.
- **Comprehensive API Surface:** Secure endpoints handling user registration, cryptographic password hashing (via `Werkzeug`), and dynamic walk-in allocation queries (`/api/bookings/on-site`) that fetch empty spots on demand.
- **Transaction & Wallet Management:** Atomic database transactions supporting digital wallet top-ups, calculated hourly parking tariffs ($1/hour), and automated late-exit fine penalties ($1 per 10 minutes of delay).
- **Advanced Overlap Prevention:** Server-side algorithmic validation guaranteeing zero temporal and spatial double-booking conflicts across users and spots.

### 3. IoT Edge Sensor Simulator (`sensor_sim.py`)
- **Telemetry Grids Simulation:** Replicates real-world ultrasonic/geomagnetic parking spot sensors executing as an asynchronous background subprocess.
- **Differentiated Virtual Traffic:** Coordinates online pre-bookings for automated `SIM_USERS` while simultaneously issuing stochastic physical registration triggers for random walk-in customers.
- **Physical Conflict Resolution (IoT Logic):** - Automatically forces a spot clearance 30 seconds prior to a registered user's booking arrival time to simulate towing/alerting unauthorized vehicles.
  - Intercepts physical sensor triggers and blocks random vehicles from parking in spots reserved within a 1-minute buffer window.

### 4. Enterprise Admin Dashboard
- **Live Business Analytics:** Displays total user acquisition, overall bookings count, instantaneous active occupancy, and peak-usage spot distribution.
- **Manual Sensor Overrides:** Allows administrators to manually trigger sensor states (Occupied/Empty) to simulate hardware testing or emergency overrides via real-time WebSocket broadcasts.

---

## 🏗️ System Architecture

The project adheres to an upgraded 4-Tier IoT Architectural Framework:

1. **Physical/Simulation Layer (`sensor_sim.py`):** Replicates physical edge nodes pushing instantaneous state variations directly to the persistence layer.
2. **Persistence Layer (`parking.db`):** Relational SQLite database utilizing ACID-compliant immediate transaction locks (`BEGIN IMMEDIATE`) to prevent race conditions during concurrent walk-in and online bookings.
3. **Application/Service Layer (`app.py`):** A Flask WSGI server augmented with `Flask-SocketIO` to bridge the gap between transactional database mutations and real-time client presentation layers.
4. **Presentation/UI Layer (`index.html`):** A responsive, single-page client framework powered by Vanilla JavaScript and WebGL (Three.js) for full-fidelity digital twin visualization.

---

## 🐳 DevOps & Production Roadmap

To transition this architecture into an enterprise-grade ecosystem, the following production-ready features are slated for the next deployment phase:
- **Containerization via Docker Compose:** Bundling the architecture into an isolated multi-container infrastructure (`docker-compose.yml`) containing independent containers for the Flask core app, the SQLite persistence layer, and the isolated `sensor_sim.py` edge worker.
- **Decoupled MQTT Communication Layer:** Migrating edge-to-cloud telemetry from standard API hooks to a dedicated **MQTT Architecture (using an Eclipse Mosquitto Broker)**. This enables lightweight, high-throughput Pub/Sub messaging for physical edge device grids.

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
- `booking_method`: TEXT ('online', 'on_site')
- `status`: TEXT ('Active', 'Completed', 'Cancelled')
- `price`: REAL

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- Modern web browser with WebGL enabled (Chrome, Firefox, Edge, Safari)

### Installation & Execution

1. **Clone the Repository:**