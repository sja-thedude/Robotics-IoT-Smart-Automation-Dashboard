# 🤖 RoboGrid AI — Robotics + IoT + Smart Automation Dashboard

A scalable, enterprise-grade control plane to manage **robots, IoT devices,
sensors, smart homes, industrial automation, and healthcare robotics** from a
single platform.

API-first Django backend with real-time telemetry, remote device control,
threshold alerting, and MQTT device communication — built to scale and ready
for AI/vision/ROS extensions.

> Built with Django · DRF · PostgreSQL · Redis · Celery · Django Channels ·
> MQTT (Mosquitto) · Docker · Nginx · Gunicorn/Uvicorn

---

## ✨ Features

| Area | What it does |
|------|--------------|
| **Auth & Access** | JWT auth (access/refresh + blacklist), email-based users, 6 roles, per-device permission grants, multi-tenant organizations |
| **Device Management** | Register robots/drones/sensor-hubs/cameras, hierarchical groups, live status & health scores, **remote control** with full command lifecycle |
| **Sensor Monitoring** | Temperature, humidity, motion, GPS, battery, vibration, camera feeds, and any custom channel; auto-discovered sensors |
| **Live Dashboards** | Real-time telemetry over WebSockets, device map markers, fleet stats, time-bucketed chart aggregation |
| **Alert System** | Declarative threshold/offline/battery/health rules, severity levels, de-duplication, acknowledge/resolve, per-user notification center |
| **APIs** | Versioned REST (`/api/v1`), WebSocket streams, MQTT ingest/control, OpenAPI docs (Swagger + ReDoc) |
| **Ops** | Audit log of every meaningful action, health probe, Celery periodic jobs, retention/purge, Docker-first deploy |

---

## 🏗️ Architecture

```
                         ┌──────────────────────────────────────────────┐
   Devices / Robots      │                  Nginx (TLS)                  │
   ┌───────────┐  MQTT   │  /static  /media   /api → app    /ws → app    │
   │ ROBO-001  │────────▶│                                               │
   │ DRONE-001 │  1883   └───────┬───────────────────────┬──────────────┘
   │ HUB-001   │                 │ HTTP (REST)            │ WebSocket
   └─────┬─────┘                 ▼                        ▼
         │              ┌──────────────────────────────────────────────┐
         │              │      Django ASGI app (Gunicorn + Uvicorn)     │
         │  telemetry/  │   DRF REST API   +   Channels consumers       │
         │  status/     └───┬───────────────┬───────────────┬──────────┘
         │  results          │ ORM           │ channel layer │ broker
         │                   ▼               ▼               ▼
         │            ┌───────────┐    ┌───────────┐   ┌───────────┐
         │            │ PostgreSQL│    │   Redis    │   │   Redis   │
         │            │ devices,  │    │  channels  │   │  celery   │
         │            │ telemetry,│    │   layer    │   │  broker   │
         │            │ alerts,   │    └───────────┘   └─────┬─────┘
         │            │ audit     │                          │
         │            └─────▲─────┘                          ▼
         │  commands        │                    ┌───────────────────────┐
         └──────────────────┼────────────────────│  Celery worker + beat │
                            │     ▲               │ offline detection,    │
                  ┌─────────┴─────┴──────┐        │ health rollups,       │
                  │   MQTT Bridge        │◀───────│ threshold backstop,   │
                  │ (manage.py           │ publish│ notifications, purge  │
                  │  run_mqtt_bridge)    │ command└───────────────────────┘
                  └──────────┬───────────┘
                             │  subscribes  robogrid/devices/+/{telemetry,status,results}
                       ┌─────▼──────┐
                       │ Mosquitto  │  MQTT broker
                       └────────────┘
```

**Key design principle:** every "something happened" event has exactly one
service-layer entry point (`telemetry.ingest_payload`, `devices.dispatch_command`,
`alerts.raise_alert`). REST, MQTT, and Celery all funnel through the same code,
so behavior is identical no matter the transport, and the WebSocket fan-out +
audit logging happen once, consistently.

---

## 🧱 Project structure

```
robogrid/
├── config/                    # project package
│   ├── settings/              # base / dev / prod / test (env-driven)
│   ├── asgi.py                # HTTP + WebSocket routing (Channels)
│   ├── wsgi.py                # sync HTTP (Gunicorn)
│   ├── celery.py              # Celery app + beat schedule
│   └── urls.py                # /api/v1 + OpenAPI docs
├── apps/
│   ├── core/                  # base models, soft-delete, audit, realtime helpers
│   ├── accounts/              # Org, User (email+roles), DevicePermission, JWT
│   ├── devices/               # Device, Group, Command, HealthSnapshot, control
│   ├── telemetry/             # Sensor, Reading (time-series), CameraFeed, ingest
│   ├── alerts/                # AlertRule, Alert, NotificationChannel, engine
│   ├── realtime/              # Channels consumers, JWT WS middleware, routing
│   └── mqtt/                  # broker bridge, ingest handlers, command publisher
├── deploy/entrypoint.sh       # waits for DB, migrates (web role only)
├── nginx/nginx.conf           # reverse proxy + WS upgrade + static
├── mosquitto/config/          # MQTT broker config
├── docker-compose.yml         # full stack (8 services)
├── Dockerfile                 # single image, role chosen per service
├── Makefile                   # common dev/ops commands
└── requirements.txt
```

---

## 🚀 Quick start (Docker)

```bash
cp .env.example .env          # then edit secrets (at least DJANGO_SECRET_KEY)
make build                    # or: docker compose build
make up                       # starts postgres, redis, mosquitto, web,
                              #         mqtt_bridge, celery worker+beat, nginx

make superuser                # create an admin login
make seed                     # load a demo org with devices, sensors, rules
```

Now visit:

| URL | What |
|-----|------|
| `http://localhost/api/docs/` | Swagger UI |
| `http://localhost/api/redoc/` | ReDoc |
| `http://localhost/admin/` | Django admin |
| `http://localhost/healthz/` | Health probe (DB + cache) |

Simulate a live device end-to-end (telemetry → ingest → alerts → WebSocket):

```bash
docker compose run --rm web python manage.py simulate_device --serial ROBO-001
```

---

## 💻 Local development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Point .env at local services (Postgres, Redis, Mosquitto on localhost)
export DJANGO_SETTINGS_MODULE=config.settings.dev

python manage.py migrate
python manage.py seed_demo
python manage.py runserver            # ASGI dev server (HTTP + WS)

# In separate terminals:
celery -A config worker -l info
celery -A config beat -l info
python manage.py run_mqtt_bridge
```

**Run the tests** (hermetic — SQLite, in-memory channels, eager Celery):

```bash
python manage.py test --settings=config.settings.test
```

---

## 🔐 Roles & permissions

| Role | Scope |
|------|-------|
| `super_admin` | Cross-org platform owner — sees everything |
| `org_admin` | Full control within their organization |
| `engineer` | Configure devices & rules; view + control any org device |
| `operator` | View any org device; **control needs a per-device grant** |
| `viewer` | View only the devices explicitly granted to them |
| `device` | Machine/service account (MQTT/API identity) |

Object-level access is enforced by `User.can_access_device(device, control=…)`
and the `HasDeviceAccess` DRF permission. Fine-grained, time-boundable grants
live in `DevicePermission`.

---

## 🔌 API overview

All endpoints are under `/api/v1/` and require `Authorization: Bearer <access>`
(except login/register/health).

```http
POST /api/v1/auth/login/                 → { access, refresh, user }
POST /api/v1/auth/token/refresh/
GET  /api/v1/auth/users/me/

GET  /api/v1/devices/                     ?status=&device_type=&online=&search=
GET  /api/v1/devices/stats/               fleet counts by status / type
GET  /api/v1/devices/map/                 markers for the live map
POST /api/v1/devices/{id}/command/        { command, payload }  → remote control
GET  /api/v1/devices/{id}/health/         health snapshots

GET  /api/v1/telemetry/sensors/{id}/readings/     ?since=&limit=
GET  /api/v1/telemetry/sensors/{id}/aggregate/    ?bucket=minute|hour|day
POST /api/v1/telemetry/ingest/            HTTP fallback for non-MQTT devices

GET  /api/v1/alerts/active/               open + acknowledged alerts
POST /api/v1/alerts/{id}/acknowledge/
POST /api/v1/alerts/{id}/resolve/
GET  /api/v1/alerts/notifications/unread_count/
```

Full, always-current contract: **`/api/docs/`**.

### WebSocket API

Authenticate by passing the JWT access token as a query param (browsers can't
set WS headers):

```js
new WebSocket("ws://localhost/ws/dashboard/?token=<ACCESS_TOKEN>")
```

| Endpoint | Streams |
|----------|---------|
| `ws://…/ws/dashboard/` | org-wide device state + alerts |
| `ws://…/ws/devices/{id}/` | one device: telemetry + command updates |
| `ws://…/ws/alerts/` | alert feed + this user's notifications |

Every message uses one envelope: `{ "event": "<type>", "payload": { … } }`
(events: `device.state`, `telemetry`, `device.command`, `alert.raised`,
`alert.updated`, `alert.resolved`, `notification`).

### MQTT topic scheme

```
robogrid/devices/{serial}/telemetry   device → backend   sensor batches (QoS1)
robogrid/devices/{serial}/status      device → backend   online/health heartbeat
robogrid/devices/{serial}/results     device → backend   command acks/results
robogrid/devices/{serial}/commands    backend → device   control instructions
```

Telemetry payload (also accepted at `POST /api/v1/telemetry/ingest/`):

```json
{
  "serial": "ROBO-001",
  "battery_level": 87.5,
  "signal_strength": -62,
  "location": {"lat": 37.77, "lon": -122.41, "alt": 12.0},
  "readings": {"temp_c": 23.4, "humidity": 51, "motion": 0, "vibration": 1.2}
}
```

---

## 🗄️ Data model & scaling

* **UUID primary keys** on domain entities so edge devices can mint records
  without a central sequence; **soft-delete** preserves history for compliance.
* **`telemetry.Reading`** is the high-volume table — a plain `BigAutoField`,
  append-only, with composite indexes `(sensor, -time)` and `(device, -time)`.
  Latest values are denormalized onto `Sensor` / `Device` so dashboards never
  scan the stream for a single number.
* **De-duplicated alerts**: a partial unique constraint guarantees at most one
  *open* alert per `(rule, device)`, so a flapping sensor can't spam operators.
* **Append-only `AuditLog`** with targeted indexes for security forensics.

**Scaling the time series:** the `Reading` table is designed to graduate to
native **PostgreSQL declarative partitioning** (by month on `time`) or a
**TimescaleDB hypertable** with zero application changes — the manager API is
unchanged. The nightly `purge_old_telemetry` task prunes raw rows past the
retention window (drop partitions instead, at very large scale).

---

## ⏱️ Background jobs (Celery beat)

| Task | Cadence | Purpose |
|------|---------|---------|
| `devices.detect_offline_devices` | 60s | watchdog: flip stale devices OFFLINE + alert |
| `devices.rollup_device_health` | 5m | composite health snapshots for trend charts |
| `devices.expire_stale_commands` | 60s | fail commands the device never acked |
| `alerts.evaluate_threshold_alerts` | 30s | battery/health rule backstop |
| `telemetry.purge_old_telemetry` | nightly | retention enforcement |

(Threshold *sensor* rules are evaluated **inline on ingest** for low latency;
the Celery task is a safety net for device-meta rules.)

---

## 🛠️ Production deployment

1. **Provision** managed PostgreSQL, Redis, and an MQTT broker (or run the
   bundled Mosquitto). Point `.env` at them and set:
   - `DJANGO_SETTINGS_MODULE=config.settings.prod`
   - a strong `DJANGO_SECRET_KEY`, real `DJANGO_ALLOWED_HOSTS` /
     `DJANGO_CSRF_TRUSTED_ORIGINS`, and `SENTRY_DSN` (optional).
2. **TLS**: terminate at Nginx — drop certs in `nginx/certs/` and enable the
   `443` server block in `nginx/nginx.conf`. `prod.py` already trusts
   `X-Forwarded-Proto` and sets HSTS/secure cookies.
3. **Build & run**: `docker compose build && docker compose up -d`.
   Only the `web` container runs migrations/`collectstatic`
   (`RUN_MIGRATIONS=true`) so the other roles don't race.
4. **Harden MQTT**: in `mosquitto/config/mosquitto.conf` disable
   `allow_anonymous`, add a `password_file`, and ACL each device to only its own
   `robogrid/devices/<serial>/*` subtree. Use TLS on `8883`.
5. **Scale out**: the app, `celery_worker`, and `mqtt_bridge` are stateless and
   horizontally scalable. Run multiple `celery_worker` replicas; keep a single
   `celery_beat`. The MQTT bridge uses a durable (`clean_session=false`)
   subscription so QoS-1 messages survive restarts.
6. **Observe**: `GET /healthz/` for liveness/readiness probes; Sentry for
   errors; `flower` (in requirements) for Celery monitoring.

---

## 🧪 What's verified

Running `python manage.py test --settings=config.settings.test` exercises:
auth/JWT flow, the role/permission matrix, telemetry ingestion + auto-sensor
creation, the threshold alert engine + de-duplication, alert lifecycle, remote
command dispatch (incl. graceful degradation when the broker is down), and the
offline-detection watchdog.

---

## 🔭 Roadmap — AI & robotics extensions

The architecture is intentionally modular and AI-ready. Planned modules slot in
as new apps without disturbing the core:

Computer vision · AI anomaly detection · Predictive maintenance · Drone fleet
ops · **ROS** bridge · Edge AI · Autonomous navigation · Digital twins ·
3D simulation · Voice control · Smart-city integrations · Security systems.

The `CameraFeed` model, schemaless `Device.capabilities`/`metadata`, the
service-layer seams, and the health-score hook (`_compute_health_score`) are the
designated extension points for ML-driven features.

---

## 📜 License

Proprietary — © RoboGrid AI. All rights reserved.
