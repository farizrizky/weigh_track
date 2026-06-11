# API DOCUMENTATION

Dokumen ini menjelaskan custom API WeighTrack untuk aplikasi operasional penimbangan.

## Scope Saat Ini

API yang aktif saat ini:

```text
POST /weightrack/api/v1/device/activate
POST /weightrack/api/v1/pull/master
```

Endpoint push belum diekspos. Struktur security dan konfigurasi enable/disable push sudah disiapkan agar endpoint push bisa memakai pola yang sama.

## Prinsip Umum

- Semua request memakai JSON.
- Semua response memakai JSON.
- Endpoint API memakai `auth="public"`, tetapi proses bisnis tidak dijalankan sebagai Public User.
- Aktivasi device memakai token enrollment dari record `wt.device`.
- Pull master memakai kombinasi `device_id` dan `token` dari device yang sudah aktif.
- Write saat aktivasi dijalankan atas nama bot user dari `wt.api`.
- Write metadata device saat pull, seperti `last_pull`, `last_seen`, dan `app_version`, dijalankan atas nama bot user dari `wt.api`.
- Pull dan push dapat dibuka atau ditutup per company melalui `wt.api`.
- Semua request dicatat di `wt.api.request.log`.
- Token mentah tidak disimpan di log. Payload disimpan lengkap tetapi disanitasi.
- Response yang dikirim ke client juga disimpan lengkap di log.
- `payload_hash` menyimpan SHA-256 dari raw request body sebagai fingerprint audit.

## Struktur Teknis

```text
controllers/api/v1/device_api.py      -> route endpoint activation v1
controllers/api/v1/pull_api.py        -> route endpoint pull master v1
controllers/api/api_handler.py        -> HTTP boundary, JSON parsing, audit log, HTTP response
services/api_device_service.py        -> proses aktivasi dan payload bootstrap device
services/api_pull_master_service.py   -> proses pull master dan payload data offline
services/api_security_service.py      -> validasi security API, autentikasi device, lookup bot user, dan cek pull/push enabled
services/api_response_service.py      -> wrapper response success/error/body
models/api_request_log.py             -> audit log API
models/api.py                  -> konfigurasi bot user dan enable/disable pull/push per company
```

Pembagian tanggung jawab:

- `device_api.py` hanya mendefinisikan route.
- `pull_api.py` hanya mendefinisikan route pull master.
- `api_handler.py` membaca request, memanggil service, membuat log, lalu mengembalikan HTTP JSON response.
- `api_device_service.py` memproses business flow aktivasi dan menyiapkan payload response.
- `api_pull_master_service.py` memproses scope data master berdasarkan role device.
- `api_security_service.py` memusatkan validasi security bersama.
- `api_response_service.py` hanya membungkus response standar, tidak menyiapkan data bisnis.

## Format Response

### Success

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {}
}
```

### Error

```json
{
  "ok": false,
  "request_id": "uuid",
  "error": {
    "code": "error_code",
    "message": "Human readable message"
  }
}
```

`request_id` dipakai untuk mencari audit di:

```text
WeighTrack > Configuration > API Request Logs
```

## API

Konfigurasi API disimpan di `wt.api` dan berlaku per company.

Field penting:

| Field | Description |
| --- | --- |
| `company_id` | Company pemilik konfigurasi API. Hanya boleh ada satu konfigurasi per company. |
| `bot_user_id` | User internal aktif yang dipakai untuk mencatat write dari proses API. |
| `pull_enabled` | Jika `False`, endpoint pull data untuk company tersebut ditutup. |
| `push_enabled` | Jika `False`, endpoint push data untuk company tersebut ditutup. Endpoint push belum aktif, tetapi helper security sudah disiapkan. |

Pull master akan menolak request jika `pull_enabled = False`.

## Device Activation

### Endpoint

```http
POST /weightrack/api/v1/device/activate
Content-Type: application/json
```

### Request

```json
{
  "token": "device-enrollment-token",
  "device_id": "local-device-id",
  "device_type": "mobile",
  "app_version": "1.0.0"
}
```

### Request Fields

| Field | Required | Description |
| --- | --- | --- |
| `token` | Yes | Token enrollment dari record `wt.device`. |
| `device_id` | Yes | ID teknis yang dibuat aplikasi lokal saat instalasi. |
| `device_type` | Yes | Tipe device. Nilai valid: `mobile`, `desktop`. |
| `app_version` | Yes | Versi aplikasi operasional yang melakukan aktivasi. |

### Validation Rules

- `token` wajib ada.
- `device_id` wajib ada.
- `device_type` wajib ada.
- `device_type` hanya boleh `mobile` atau `desktop`.
- `app_version` wajib ada.
- Token harus ditemukan pada `wt.device`.
- Device harus berstatus `inactive`.
- `device_id` tidak boleh dipakai oleh device lain.
- Company device harus memiliki konfigurasi bot user di `wt.api`.
- Bot user harus user internal aktif, bukan portal/public user.

### Success Behavior

Jika aktivasi berhasil, Odoo akan:

- mengubah `wt.device.status` menjadi `active`;
- menyimpan `device_id`;
- menyimpan `device_type`;
- menyimpan `app_version`;
- mengisi `actived_at` jika belum ada;
- memperbarui `last_seen`;
- mencatat perubahan di chatter atas nama bot user API.

Aktivasi awal hanya bisa dilakukan lewat API. Tidak ada tombol manual `Activate` di form Device.

Setelah device pernah aktif atau status bukan `inactive`, assignment dan informasi teknis terkunci. Admin hanya boleh mengubah `name`. Perubahan status lanjutan dilakukan lewat tombol state seperti `Block`, `Reactivate`, dan `Revoke`.

### Success Response

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {
    "device": {
      "id": 1,
      "device_id": "local-device-id",
      "name": "Device Timbang 01",
      "status": "active",
      "device_type": "mobile",
      "app_version": "1.0.0",
      "last_seen": "2026-06-06 10:00:00"
    },
    "company": {
      "id": 1,
      "name": "Company Name"
    },
    "employee": {
      "id": 1,
      "barcode": "EMP001",
      "name": "Employee Name",
      "job_position": "Operator"
    },
    "role": "operator"
  }
}
```

### Response Data

| Path | Description |
| --- | --- |
| `data.device.id` | ID record `wt.device` di Odoo. |
| `data.device.device_id` | ID teknis device dari aplikasi lokal. |
| `data.device.name` | Nama administratif device dari Odoo. |
| `data.device.status` | Status device setelah aktivasi. |
| `data.device.device_type` | Tipe device. |
| `data.device.app_version` | Versi aplikasi saat aktivasi. |
| `data.device.last_seen` | Waktu terakhir device terlihat oleh API. |
| `data.company.id` | ID company di Odoo. |
| `data.company.name` | Nama company. |
| `data.employee.id` | ID employee penanggung jawab device. |
| `data.employee.barcode` | Barcode employee dari `hr.employee.barcode`. |
| `data.employee.name` | Nama employee. |
| `data.employee.job_position` | Nama jabatan dari `hr.employee.job_id.name`. |
| `data.role` | Role operasional device: `clerk`, `foreman`, atau `operator`. |

## Pull Master

Pull master digunakan aplikasi offline penimbangan untuk mengambil data dari Odoo sebelum perangkat bekerja di area blankspot.

### Endpoint

```http
POST /weightrack/api/v1/pull/master
Content-Type: application/json
```

### Request

```json
{
  "device_id": "local-device-id",
  "token": "device-token",
  "app_version": "1.0.0"
}
```

### Request Fields

| Field | Required | Description |
| --- | --- | --- |
| `device_id` | Yes | ID teknis device dari aplikasi lokal. |
| `token` | Yes | Token device dari record `wt.device`. |
| `app_version` | No | Versi aplikasi operasional. Jika dikirim, akan memperbarui `wt.device.app_version`. |

### Validation Rules

- `device_id` wajib ada.
- `token` wajib ada.
- Kombinasi `device_id` dan `token` harus cocok dengan record `wt.device`.
- Device harus berstatus `active`.
- Role device harus `operator`, `clerk`, atau `foreman`.
- Company device harus memiliki konfigurasi bot user di `wt.api`.
- Bot user harus user internal aktif, bukan portal/public user.
- `wt.api.pull_enabled` harus aktif untuk company device.

### Success Behavior

Jika pull master berhasil, Odoo akan:

- menghitung scope data berdasarkan company, employee, dan role pada assignment device;
- mengirim data master yang dibutuhkan aplikasi offline;
- memperbarui `wt.device.last_pull`;
- memperbarui `wt.device.last_seen`;
- memperbarui `wt.device.app_version` jika `app_version` dikirim;
- mencatat request ke `wt.api.request.log`.

### Role Scope

| Role | Scope Pull |
| --- | --- |
| `foreman` | Foreman record milik employee device, division foreman, tapper yang berada di bawah foreman tersebut, estate, dan weighing location terkait division. |
| `clerk` | Division yang `clerk_id`-nya employee device, foreman di division tersebut, tapper di division tersebut, estate, dan weighing location terkait division. |
| `operator` | Weighing location yang `operator_id`-nya employee device, allowed division dari weighing location, clerk division, foreman, tapper, estate, warehouse. |

### Success Response

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {
    "meta": {
      "server_time": "2026-06-07 10:00:00",
      "role": "operator",
      "company_id": 1,
      "employee_id": 10,
      "device": {
        "id": 1,
        "device_id": "local-device-id",
        "name": "Device Timbang 01",
        "status": "active",
        "role": "operator",
        "device_type": "mobile",
        "app_version": "1.0.0",
        "last_pull": "2026-06-07 10:00:00",
        "last_seen": "2026-06-07 10:00:00"
      }
    },
    "scope": {
      "role": "operator",
      "company_id": 1,
      "employee_id": 10,
      "estate_ids": [1],
      "division_ids": [1, 2],
      "weighing_location_ids": [1],
      "clerk_employee_ids": [20],
      "foreman_ids": [30, 31],
      "operator_employee_ids": [10],
      "tapper_ids": [100, 101]
    },
    "masters": {
      "company": {
        "id": 1,
        "name": "Company Name"
      },
      "employee": {
        "id": 10,
        "name": "Operator Name",
        "barcode": "OP001",
        "job_position": "Operator",
        "company_id": 1
      },
      "estates": [
        {
          "id": 1,
          "code": "EST01",
          "name": "Estate 01",
          "company_id": 1
        }
      ],
      "divisions": [
        {
          "id": 1,
          "code": "DIV01",
          "name": "Division 01",
          "company_id": 1,
          "estate_id": 1,
          "clerk_employee_id": 20
        }
      ],
      "weighing_locations": [
        {
          "id": 1,
          "code": "WL01",
          "name": "Gudang Induk",
          "company_id": 1,
          "estate_id": 1,
          "warehouse": {
            "id": 1,
            "code": "WH01",
            "name": "Warehouse 01"
          },
          "operator_employee_id": 10,
          "allowed_division_ids": [1, 2]
        }
      ],
      "clerks": [
        {
          "id": 20,
          "name": "Clerk Name",
          "barcode": "CL001",
          "job_position": "Clerk",
          "company_id": 1
        }
      ],
      "foremen": [
        {
          "id": 30,
          "name": "Foreman Name",
          "employee_id": 30,
          "employee_name": "Foreman Name",
          "employee_barcode": "FM001",
          "company_id": 1,
          "division_id": 1
        }
      ],
      "operators": [
        {
          "id": 10,
          "name": "Operator Name",
          "barcode": "OP001",
          "job_position": "Operator",
          "company_id": 1
        }
      ],
      "tappers": [
        {
          "id": 100,
          "name": "Tapper Name",
          "employee_id": 100,
          "employee_name": "Tapper Name",
          "employee_barcode": "TP001",
          "company_id": 1,
          "division_id": 1,
          "foreman_id": 30
        }
      ]
    }
  }
}
```

### Response Data

| Path | Description |
| --- | --- |
| `data.meta.server_time` | Waktu server saat pull diproses. |
| `data.meta.role` | Role operasional device. |
| `data.meta.company_id` | Company scope device. |
| `data.meta.employee_id` | Employee penanggung jawab device. |
| `data.meta.device` | Informasi device aktif. |
| `data.scope` | Batas kerja device dalam bentuk daftar ID. |
| `data.masters.company` | Master company device. |
| `data.masters.employee` | Master employee penanggung jawab device. |
| `data.masters.estates` | Daftar estate dalam scope. Minimal membawa `id`, `code`, dan `name`. |
| `data.masters.divisions` | Daftar division dalam scope. Minimal membawa `id`, `code`, dan `name`. |
| `data.masters.weighing_locations` | Daftar weighing location dalam scope. Minimal membawa `id`, `code`, dan `name`. |
| `data.masters.clerks` | Daftar clerk dalam scope, termasuk barcode employee. |
| `data.masters.foremen` | Daftar foreman dalam scope, termasuk barcode employee. |
| `data.masters.operators` | Daftar operator dalam scope, termasuk barcode employee. |
| `data.masters.tappers` | Daftar tapper dalam scope, termasuk barcode employee. |

## Error Codes

| HTTP Status | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_json` | Body request bukan JSON valid. |
| 400 | `invalid_payload` | JSON valid, tetapi root payload bukan object. |
| 400 | `missing_token` | Field `token` tidak dikirim. |
| 400 | `missing_device_id` | Field `device_id` tidak dikirim. |
| 400 | `missing_device_type` | Field `device_type` tidak dikirim. |
| 400 | `missing_app_version` | Field `app_version` tidak dikirim. |
| 400 | `invalid_device_type` | `device_type` bukan `mobile` atau `desktop`. |
| 401 | `invalid_token` | Token tidak ditemukan. |
| 401 | `invalid_device_credentials` | Kombinasi `device_id` dan `token` tidak valid untuk pull/push. |
| 403 | `device_not_active` | Device ditemukan tetapi tidak berstatus `active`. |
| 403 | `role_not_allowed` | Role device tidak diperbolehkan untuk endpoint tersebut. |
| 403 | `pull_closed` | Pull data ditutup melalui `wt.api.pull_enabled = False`. |
| 403 | `push_closed` | Push data ditutup melalui `wt.api.push_enabled = False`. |
| 409 | `device_not_inactive` | Device ditemukan tetapi tidak berstatus `inactive`. |
| 409 | `device_id_already_used` | `device_id` sudah dipakai device lain. |
| 500 | `api_missing` | Bot user API belum dikonfigurasi untuk company device. |
| 500 | `api_invalid` | Bot user API tidak aktif atau bukan internal user. |
| 500 | `internal_error` | Error tidak terduga di API boundary. |

### Error Response Example

```json
{
  "ok": false,
  "request_id": "uuid",
  "error": {
    "code": "missing_token",
    "message": "Token is required."
  }
}
```

## Audit Log

Setiap request membuat record `wt.api.request.log`.

Field audit:

| Field | Description |
| --- | --- |
| `request_id` | UUID unik untuk trace request. |
| `endpoint` | Nama endpoint internal, contoh `device.activate`. |
| `method` | HTTP method. |
| `status` | `success` atau `failed`. |
| `http_status` | HTTP status response. |
| `error_code` | Kode error jika gagal. |
| `error_message` | Pesan error jika gagal. |
| `device_id` | `device_id` dari request payload jika tersedia. |
| `device_record_id` | Relasi ke record `wt.device` jika dapat diidentifikasi. |
| `company_id` | Company dari device jika tersedia. |
| `employee_id` | Employee penanggung jawab device jika tersedia. |
| `role` | Role device jika tersedia. |
| `request_ip` | IP client dari HTTP request. |
| `user_agent` | User-Agent client. |
| `duration_ms` | Durasi proses request dalam milidetik. |
| `requested_at` | Waktu request mulai diproses. |
| `finished_at` | Waktu request selesai diproses. |
| `payload_hash` | SHA-256 hash dari raw request body. |
| `payload` | Payload lengkap yang sudah disanitasi. |
| `response` | Response body lengkap yang dikirim ke client. |

### Sanitasi Payload

Field berikut akan diganti menjadi `***` jika muncul di payload atau response:

```text
token
password
secret
api_key
```

Contoh payload yang tersimpan di log:

```json
{
  "token": "***",
  "device_id": "local-device-id",
  "device_type": "mobile",
  "app_version": "1.0.0"
}
```

`payload_hash` tetap dibuat dari raw body asli sebelum sanitasi. Hash ini tidak bisa didekripsi dan hanya dipakai sebagai fingerprint untuk membandingkan request.

## Device State Notes

- Device dibuat oleh admin Odoo sebagai assignment/enrollment.
- Saat dibuat, status awal adalah `inactive`.
- Token dibuat otomatis oleh Odoo.
- Admin mengirim token ke employee penanggung jawab device.
- Employee melakukan aktivasi dari aplikasi operasional.
- Device hanya menjadi `active` melalui API activation.
- Tombol `Block` hanya tersedia untuk device `active` dan wajib meminta reason.
- Tombol `Reactivate` hanya tersedia untuk device `blocked`.
- Tombol `Revoke` hanya tersedia untuk device `active` atau `blocked`, menampilkan konfirmasi, lalu wajib meminta reason.
- `blocked_reason` dan `revoked_reason` disimpan dari wizard reason.

## Future Push

Push belum aktif.

Konsep yang sudah disiapkan untuk push:

- request push membawa `device_id` dan `token`;
- Odoo memvalidasi kombinasi `device_id` dan `token` melalui `api_security_service.authenticate_device`;
- device harus berstatus `active`;
- `wt.api.push_enabled` harus aktif untuk company device;
- scope data mengikuti company, employee, dan role dari assignment device;
- eksekusi tulis data bisnis diarahkan ke bot user dari `wt.api`;
- payload push disiapkan oleh service push sendiri;
- `wt.api.response.service` hanya membungkus response standar;
- setiap request tetap dicatat ke `wt.api.request.log`.
