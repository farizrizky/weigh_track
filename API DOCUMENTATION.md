# API DOCUMENTATION

Dokumen ini menjelaskan custom API WeighTrack untuk aplikasi operasional penimbangan.

## Scope Saat Ini

API yang aktif saat ini:

```text
POST /weightrack/api/v1/device/activate
POST /weightrack/api/v1/pull/master
POST /weightrack/api/v1/push/weighing-cup-lump
```

Endpoint push weighing Cup Lump sudah aktif. Push langsung membuat `wt.weighing.cup.lump` draft dan belum membuat inbound/receipt stock resmi.

Data cuaca (`wt.weather` dan `wt.weather.data`) saat ini belum diekspos melalui custom API dan belum masuk payload pull master. Data tersebut masih dikelola sebagai data Odoo/UI.

## Prinsip Umum

- Semua request memakai JSON.
- Semua response memakai JSON.
- Endpoint API memakai `auth="public"`, tetapi proses bisnis tidak dijalankan sebagai Public User.
- Aktivasi device memakai token enrollment dari record `wt.device`.
- Pull master memakai kombinasi `device_id` dan `token` dari device yang sudah aktif.
- Push weighing Cup Lump memakai kombinasi `device_id` dan `token` dari device operator yang sudah aktif.
- Write saat aktivasi dijalankan atas nama bot user dari `wt.api`.
- Write metadata device saat pull, seperti `last_pull`, `last_seen`, dan `app_version`, dijalankan atas nama bot user dari `wt.api`.
- Write data weighing saat push dijalankan atas nama bot user dari `wt.api`.
- Pull dan push dapat dibuka atau ditutup per company melalui `wt.api`.
- Semua request dicatat di `wt.api.request.log`.
- Token mentah tidak disimpan di log. Payload disimpan lengkap tetapi disanitasi.
- Response yang dikirim ke client juga disimpan lengkap di log.
- `payload_hash` menyimpan SHA-256 dari raw request body sebagai fingerprint audit.

## Struktur Teknis

```text
controllers/api/v1/device_api.py      -> route endpoint activation v1
controllers/api/v1/pull_api.py        -> route endpoint pull master v1
controllers/api/v1/push_api.py        -> route endpoint push weighing Cup Lump v1
controllers/api/api_handler.py        -> HTTP boundary, JSON parsing, audit log, HTTP response
services/api_device_service.py        -> proses aktivasi dan payload bootstrap device
services/api_pull_master_service.py   -> proses pull master dan payload data offline
services/api_push_weighing_cup_lump_service.py -> autentikasi, validasi root, dan summary push
services/cup_lump_service.py          -> proses item, idempotency, mapping, dan data problem Cup Lump
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
- `api_push_weighing_cup_lump_service.py` mengelola satu request/batch push.
- `cup_lump_service.py` mengelola business logic setiap item Cup Lump dan recheck data problem.
- `api_security_service.py` memusatkan validasi security bersama.
- `api_response_service.py` hanya membungkus response standar, tidak menyiapkan data bisnis.

## Data Odoo Tanpa Custom API

Beberapa model operasional sudah tersedia di Odoo tetapi belum memiliki endpoint custom API:

| Model | Status API |
| --- | --- |
| `wt.weather` | Belum diekspos melalui custom API. |
| `wt.weather.data` | Belum diekspos melalui custom API dan belum dikirim pada pull master. |

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
| `push_enabled` | Jika `False`, endpoint push data untuk company tersebut ditutup. Saat ini dipakai oleh endpoint push weighing Cup Lump. |

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
| `foreman` | Foreman record milik employee device, division foreman, tapper yang berada di bawah foreman tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait. |
| `clerk` | Division yang `clerk_id`-nya employee device, foreman di division tersebut, tapper di division tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait. |
| `operator` | Weighing location yang `operator_id`-nya employee device, allowed division dari weighing location, receipt rule, product, UoM, shrinkage tolerance, clerk division, foreman, tapper, dan estate. |

### Success Response

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {
    "meta": {
      "server_time": "2026-06-07 10:00:00",
      "timezone": "Asia/Jakarta",
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
      "estate_ids": [1],
      "division_ids": [1, 2],
      "weighing_location_ids": [1],
      "receipt_rule_ids": [1],
      "product_ids": [10],
      "product_type_codes": ["cup_lump"],
      "uom_ids": [1],
      "shrinkage_tolerance_ids": [1],
      "employee_ids": [10, 20, 30, 100],
      "foreman_ids": [30, 31],
      "tapper_ids": [100, 101]
    },
    "masters": {
      "company": {
        "id": 1,
        "name": "Company Name"
      },
      "roles": [
        {
          "code": "operator",
          "name": "Operator"
        }
      ],
      "employees": [
        {
          "id": 10,
          "name": "Operator Name",
          "barcode": "OP001",
          "company_id": 1
        },
        {
          "id": 20,
          "name": "Clerk Name",
          "barcode": "CL001",
          "company_id": 1
        }
      ],
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
          "operator_employee_id": 10,
          "allowed_division_ids": [1, 2]
        }
      ],
      "receipt_rules": [
        {
          "id": 1,
          "name": "Gudang Induk - Division 01 - Cup Lump",
          "company_id": 1,
          "weighing_location_id": 1,
          "division_id": 1,
          "product_id": 10
        }
      ],
      "products": [
        {
          "id": 10,
          "name": "Cup Lump",
          "company_id": 1,
          "uom_id": 1,
          "product_type": "cup_lump"
        }
      ],
      "uoms": [
        {
          "id": 1,
          "name": "kg"
        }
      ],
      "product_types": [
        {
          "code": "cup_lump",
          "name": "Cup Lump"
        }
      ],
      "shrinkage_tolerances": [
        {
          "id": 1,
          "company_id": 1,
          "product_type": "cup_lump",
          "division_id": 1,
          "shrinkage_tolerance_percentage": 5.0
        }
      ],
      "foremen": [
        {
          "id": 30,
          "employee_id": 30,
          "company_id": 1,
          "division_id": 1
        }
      ],
      "tappers": [
        {
          "id": 100,
          "employee_id": 100,
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
| `data.meta.server_time` | Waktu server saat pull diproses, sudah dikonversi memakai timezone bot user. |
| `data.meta.timezone` | Timezone bot user yang dipakai untuk format `server_time`, `last_pull`, dan `last_seen`. |
| `data.meta.role` | Role operasional device. |
| `data.meta.company_id` | Company scope device. |
| `data.meta.employee_id` | Employee penanggung jawab device. |
| `data.meta.device` | Informasi device aktif. |
| `data.scope` | Batas kerja device dalam bentuk daftar ID. |
| `data.scope.receipt_rule_ids` | Daftar Receipt Rule yang berlaku dalam scope device. |
| `data.scope.product_ids` | Daftar product Odoo yang berlaku dalam scope device. |
| `data.scope.product_type_codes` | Daftar kode tipe produk dari mapping `wt.product` yang berlaku dalam scope. |
| `data.scope.uom_ids` | Daftar UoM product dalam scope device. |
| `data.scope.shrinkage_tolerance_ids` | Daftar shrinkage tolerance yang berlaku dalam scope device. |
| `data.scope.employee_ids` | Daftar employee yang dibutuhkan aplikasi dalam scope device. |
| `data.masters.company` | Master company device. |
| `data.masters.roles` | Master role aplikasi, dibatasi hanya role milik device yang sedang pull. |
| `data.masters.employees` | Master employee terpusat untuk employee device, clerk, operator, foreman employee, dan tapper employee dalam scope. |
| `data.masters.estates` | Daftar estate dalam scope. Minimal membawa `id`, `code`, dan `name`. |
| `data.masters.divisions` | Daftar division dalam scope. Minimal membawa `id`, `code`, dan `name`. |
| `data.masters.weighing_locations` | Daftar weighing location dalam scope. Tidak membawa warehouse. |
| `data.masters.receipt_rules` | Daftar aturan receipt yang menentukan kombinasi weighing location, division, dan product yang boleh ditimbang. |
| `data.masters.products` | Daftar product Odoo yang dipakai oleh receipt rule dalam scope. Payload membawa `id`, `name`, `company_id`, `uom_id`, dan `product_type`. |
| `data.masters.uoms` | Master UoM dari product dalam scope. |
| `data.masters.product_types` | Master product type yang benar-benar dipakai oleh mapping `wt.product` dalam scope. |
| `data.masters.shrinkage_tolerances` | Daftar batas toleransi penyusutan produksi sesuai division dan product type dalam scope device. |
| `data.masters.foremen` | Daftar relasi foreman dalam scope, membawa `employee_id`. Detail employee ada di `masters.employees`. |
| `data.masters.tappers` | Daftar relasi tapper dalam scope, membawa `employee_id`. Detail employee ada di `masters.employees`. |

Catatan archive:

- Pull master hanya mengirim master/config yang masih aktif.
- Record yang sudah diarsipkan tidak masuk `scope` dan tidak dikirim di `masters`.
- Jika aplikasi belum pull ulang dan masih mengirim ID lama yang sudah archived, push tetap diterima sebagai draft tetapi ditandai `inactive_master`.

## Push Weighing Cup Lump

Endpoint ini digunakan aplikasi offline untuk mengirim data penimbangan Cup Lump ke Odoo. Setiap item yang belum pernah diterima langsung membentuk satu record draft:

```text
wt.weighing.cup.lump
```

Push tidak membentuk inbound header, receipt stock, atau stock movement. Proses pembentukan inbound/receipt akan dirancang terpisah per product type.

### Endpoint

```http
POST /weightrack/api/v1/push/weighing-cup-lump
Content-Type: application/json
```

### Request

Payload memakai object nested sebagai snapshot data yang diketahui aplikasi saat penimbangan. ID di dalam object dipakai Odoo untuk validasi ke master terkini, sedangkan name/code/barcode disimpan sebagai snapshot historis.

```json
{
  "device_id": "OPR-DEVICE-001",
  "token": "device-token",
  "app_version": "1.0.0",
  "batch_local_id": "batch-20260614-001",
  "master_synced_at": "2026-06-14 06:00:00",
  "sent_at": "2026-06-15 08:30:00",
  "product_type": "cup_lump",
  "items": [
    {
      "local_id": "cup-lump-20260614-0001",
      "production_date": "2026-06-14",
      "weighing_date": "2026-06-15 08:00:00",
      "company": {"id": 1, "name": "PT. Julang Plantations"},
      "estate": {"id": 1, "code": "SBY", "name": "Sebayur"},
      "weighing_location": {"id": 1, "code": "SBY-01", "name": "Sebayur 1"},
      "division": {"id": 1, "code": "DIV-01", "name": "Divisi 1"},
      "operator": {"employee_id": 101, "name": "Budi Operator", "barcode": "EMP-101"},
      "clerk": {"employee_id": 201, "name": "Sari Kerani", "barcode": "EMP-201"},
      "foreman": {"id": 31, "employee_id": 301, "name": "Andi Mandor", "barcode": "EMP-301"},
      "tapper": {"id": 88, "employee_id": 401, "name": "Joko Tapper", "barcode": "EMP-401"},
      "product": {"id": 25, "name": "Cup Lump (A1)", "uom": {"id": 1, "name": "kg"}},
      "receipt_rule": {
        "id": 7,
        "company_id": 1,
        "weighing_location_id": 1,
        "division_id": 1,
        "product_id": 25
      },
      "total_bag": 12,
      "production_weight": 950.0,
      "reject_weight": 20.0,
      "slab_weight": 30.0,
      "net_weight": 900.0,
      "shrinkage_tolerance_percentage": 5.0,
      "shrinkage_tolerance_weight": 50.0,
      "is_manual_weighing": false,
      "manual_weighing_reason": null,
      "note": "Penimbangan gudang dilakukan H+1",
      "initial_weighing": {
        "weighing_date": "2026-06-14 16:00:00",
        "device_id": "FIELD-SCALE-002",
        "weight": 1000.0,
        "is_manual_weighing": false,
        "manual_weighing_reason": null,
        "note": "Berat awal saat tanggal produksi"
      }
    }
  ]
}
```

### Validation Rules

- `device_id` dan `token` wajib cocok dengan device aktif.
- Role device wajib `operator`.
- `wt.api.push_enabled` wajib aktif untuk company device.
- Bot user pada `wt.api` wajib berupa internal user aktif.
- Jika `product_type` dikirim, nilainya harus `cup_lump`.
- `items` wajib berupa list dan minimal berisi satu item.
- `master_synced_at` dan `sent_at`, jika dikirim, harus berupa datetime valid.
- Setiap item cup lump wajib memiliki `local_id`, `production_date`, dan `weighing_date`.
- `production_date` harus berupa date valid dan `weighing_date` harus berupa datetime valid.
- `production_date` tidak boleh lebih besar dari tanggal lokal `weighing_date`.
- Jika initial weighing date terisi dan initial device ditemukan, initial weight wajib lebih dari 0.
- Jika initial manual weighing aktif dan initial device ditemukan, manual weighing reason wajib diisi.
- Initial device yang kosong/tidak ditemukan tidak menolak push; item diterima dengan problem `missing_master`.
- Master payload yang masih ada tetapi sudah archived tidak menolak push; item diterima dengan problem `inactive_master`.
- Idempotency API memakai kombinasi `device_id + product_type + local_id`.
- Partial unique index database hanya berlaku untuk `data_source = api`; data manual tidak mengikuti idempotency API.
- Odoo tetap menerima item sebagai draft walaupun ditemukan data problem.
- `master_synced_at` tetap disimpan untuk audit, tetapi perbedaan tanggalnya dengan `production_date` bukan data problem.

### Data Problem

`has_data_problem = true` berarti item berhasil diterima, tetapi tidak boleh divalidasi sebelum masalahnya diselesaikan. Admin dapat memperbaiki master atau record draft, lalu memakai tombol `Recheck Data Problem`. Save record draft dan action Validate juga menjalankan pengecekan ulang.

| Code | Penjelasan dan kondisi pemicu |
| --- | --- |
| `none` | Tidak ditemukan masalah. Record dapat divalidasi jika seluruh field wajib sudah lengkap. |
| `company_mismatch` | Company pada payload tidak sama dengan company device, atau division yang dipilih bukan milik company penimbangan. |
| `estate_mismatch` | Estate bukan milik company penimbangan, atau estate payload berbeda dari estate yang terikat pada weighing location. |
| `operator_mismatch` | Employee operator payload berbeda dari employee pemilik device, atau operator pada weighing location berbeda dari operator device. |
| `weighing_location_mismatch` | Weighing location tidak berada pada company penimbangan. |
| `division_not_allowed` | Division tidak termasuk `allowed_division_ids` pada weighing location. |
| `receipt_rule_mismatch` | Receipt rule tidak cocok dengan company, weighing location, division, atau product pada item. |
| `product_mapping_mismatch` | Product belum dipetakan sebagai product type `cup_lump` melalui `wt.product` untuk company penimbangan. |
| `clerk_mismatch` | Employee clerk payload berbeda dari `division.clerk_id`. |
| `foreman_mismatch` | Employee foreman tidak memiliki assignment `wt.foreman` pada division tersebut, foreman ID berada pada division lain, atau employee payload berbeda dari employee pada master foreman. |
| `tapper_mismatch` | Employee tidak terdaftar sebagai `wt.tapper`, tapper berada pada division lain, tapper tidak berada di bawah foreman yang dipilih, atau employee payload berbeda dari employee pada master tapper. |
| `weight_formula_mismatch` | `production_weight` tidak sama dengan `slab_weight + reject_weight + net_weight`. |
| `initial_weighing_date_mismatch` | Tanggal pada `initial_weighing.weighing_date` tidak sama dengan `production_date`. Perbandingan tanggal menggunakan timezone context Odoo. |
| `initial_weight_mismatch` | Untuk penimbangan lintas hari, `production_weight` tidak sama dengan `initial_weight - shrinkage_tolerance_weight`. |
| `shrinkage_tolerance_mismatch` | `shrinkage_tolerance_weight` tidak sama dengan `initial_weight * shrinkage_tolerance_percentage / 100`. |
| `inactive_master` | ID master payload masih ditemukan di Odoo, tetapi record tersebut sudah diarsipkan/nonaktif. Berlaku untuk estate, weighing location, division, product mapping, receipt rule, foreman, atau tapper. |
| `missing_master` | ID master payload tidak ditemukan di Odoo. Berlaku untuk estate, weighing location, division, product, receipt rule, foreman, tapper, atau initial weighing device. Kode ini juga dipakai jika initial weighing date diisi tetapi device awal tidak dikirim. |
| `multiple_problem` | Lebih dari satu jenis problem ditemukan pada item yang sama. Rincian masing-masing masalah terdapat pada `data_problem_note`. |

Catatan:

- Rule lama `production_weight = initial_weight` untuk penimbangan pada tanggal produksi yang sama sudah tidak digunakan.
- Jika initial weighing device tidak ditemukan, push tetap diterima sebagai draft dengan `missing_master`; API tidak gagal hanya karena field `By Device` kosong.
- `data_problem_note_en` menyimpan catatan masalah versi Inggris untuk audit/debug.
- `data_problem_note_idn` menyimpan catatan masalah versi Indonesia.
- `data_problem_note` adalah field display sesuai preferensi bahasa user; `id_ID` menampilkan versi Indonesia, bahasa lain menampilkan versi Inggris.

### Success Response

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {
    "summary": {
      "received": 1,
      "created": 1,
      "duplicates": 0,
      "with_data_problem": 0,
      "weighing_cup_lump_ids": [1]
    },
    "items": [
      {
        "local_id": "cup-lump-20260614-0001",
        "status": "created",
        "has_data_problem": false,
        "data_problem_code": "none",
        "weighing_cup_lump_id": 1
      }
    ]
  }
}
```

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
| 400 | `unsupported_product_type` | `product_type` dikirim dengan nilai selain `cup_lump`. |
| 400 | `missing_items` | Payload tidak membawa `items` berupa list. |
| 400 | `empty_items` | List `items` kosong. |
| 400 | `invalid_inbound_item` | Item cup lump bukan object. |
| 400 | `missing_local_id` | Item cup lump tidak membawa `local_id`. |
| 400 | `missing_production_date` | Item cup lump tidak membawa `production_date`. |
| 400 | `missing_weighing_date` | Item cup lump tidak membawa `weighing_date`. |
| 400 | `invalid_production_date` | Format `production_date` tidak valid. |
| 400 | `invalid_weighing_date` | Format `weighing_date` tidak valid. |
| 400 | `invalid_master_synced_at` | Format `master_synced_at` tidak valid. |
| 400 | `invalid_sent_at` | Format `sent_at` tidak valid. |
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

## Future Push Scope

Push yang aktif saat ini baru menerima transaksi weighing untuk product type `cup_lump`.

Scope lanjutan yang belum aktif:

- push product type lain selain `cup_lump`;
- close shift/no pending data dari aplikasi;
- pembentukan inbound khusus per product type dari weighing yang sudah bersih;
- pembuatan receipt stock resmi;
- workflow reject/cancel transaksi weighing atau inbound yang akan dibentuk.
