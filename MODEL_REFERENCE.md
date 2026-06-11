# WeighTrack Model Reference

Dokumen ini menjelaskan model WeighTrack, field utama, relasi, aturan validasi, akses, dan service teknis yang sedang aktif di module.

## Scope Module

Module teknis:

```text
weightrack
```

Dependency:

```text
base
mail
stock
hr
```

Menu utama:

```text
WeighTrack
├── Master Data
│   ├── Estates
│   ├── Divisions
│   ├── Weighing Locations
│   ├── Foremen
│   └── Tappers
├── Device
└── Configuration
    ├── API
    ├── API Request Logs
    └── Employee Roles
```

## Global Rules

- Semua master operasional utama memakai chatter Odoo:
  - `mail.thread`
  - `mail.activity.mixin`
- Field penting diberi `tracking=True`, sehingga perubahan tercatat di chatter.
- Akses CRUD utama diberikan ke group `weightrack.group_admin`.
- Nama teknis model dan field memakai bahasa Inggris.
- Label bahasa Indonesia dikelola lewat file translasi `i18n/id_ID.po`.
- Istilah UI penting:
  - `Foreman` / `Foremen` diterjemahkan menjadi `Mandor`.
  - `Clerk` diterjemahkan menjadi `Kerani`.
- Device activation hanya dilakukan melalui custom API, bukan tombol manual di form device.
- Endpoint pull master sudah aktif untuk mengambil data master offline.
- Endpoint push belum aktif.

## Estate

Model teknis:

```text
wt.estate
```

Deskripsi:

Estate adalah master kebun/unit estate. Estate menjadi parent untuk Division dan Weighing Location.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `code` | `Char` | Ya | Ya | Kode estate. Diindeks untuk pencarian. |
| `name` | `Char` | Ya | Ya | Nama estate. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company pemilik estate. Default mengikuti company user aktif. |

Urutan data:

```text
code, name
```

Validasi:

- `code` wajib unik per `company_id`.

Constraint database:

```text
unique(code, company_id)
```

Pesan validasi:

```text
Estate code must be unique per company.
```

## Employee Role

Model teknis:

```text
wt.employee.role
```

Deskripsi:

Employee Role adalah konfigurasi job position karyawan yang boleh dipakai untuk role operasional WeighTrack. Konfigurasi ini menjadi sumber domain dan validasi employee untuk Clerk, Operator, Foreman, Tapper, dan Device Assignment.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari company, role, dan job position. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company tempat employee role berlaku. |
| `role` | `Selection` | Ya | Ya | Role operasional: `operator`, `clerk`, `foreman`, `tapper`. |
| `job_id` | `Many2one(hr.job)` | Ya | Ya | Job position yang diizinkan untuk role tersebut. |

Urutan data:

```text
company_id, role
```

Validasi:

- Kombinasi `company_id`, `role`, dan `job_id` wajib unik.
- `job_id` wajib dipilih.
- Jika `job_id` punya company, company job position harus sama dengan `company_id` mapping.
- Helper `get_allowed_employees()` dipakai untuk domain employee.
- Helper `get_employee_domain()` dipakai untuk onchange domain.
- Helper `check_employee_allowed()` dipakai oleh model lain untuk memastikan employee:
  - berada di company yang sama dengan record operasional;
  - punya job position yang termasuk employee role tersebut;
  - memiliki konfigurasi employee role untuk company terkait.

Constraint database:

```text
unique(company_id, role, job_id)
```

Pesan validasi utama:

```text
Job position must be selected.
Job position must belong to the same company as the employee role.
Employee role must be unique per company, role, and job position.
%s employee must belong to the same company.
%s employee role has not been configured for this company.
%s employee must use an allowed job position for this company.
```

## Division

Model teknis:

```text
wt.division
```

Deskripsi:

Division adalah master divisi/blok operasional di dalam estate.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `code` | `Char` | Ya | Ya | Kode divisi. Diindeks untuk pencarian. |
| `name` | `Char` | Ya | Ya | Nama divisi. |
| `estate_id` | `Many2one(wt.estate)` | Ya | Ya | Estate tempat divisi berada. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `estate_id.company_id`, `store=True`, readonly. |
| `clerk_id` | `Many2one(hr.employee)` | Tidak | Ya | Employee Clerk/Kerani untuk divisi. Domain berdasarkan employee role `clerk`. |
| `allowed_clerk_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Clerk. |

Urutan data:

```text
estate_id, code, name
```

Validasi:

- `code` wajib unik per `estate_id`.
- Clerk harus valid menurut employee role `clerk` pada company division.

Constraint database:

```text
unique(code, estate_id)
```

Pesan validasi:

```text
Division code must be unique per estate.
%s employee must belong to the same company.
%s employee role has not been configured for this company.
%s employee must use an allowed job position for this company.
```

Catatan relasi:

- Division tidak mengatur Weighing Location.
- Pengaturan divisi yang boleh menimbang dilakukan dari model `wt.weighing.location`.

## Weighing Location

Model teknis:

```text
wt.weighing.location
```

Deskripsi:

Weighing Location adalah master lokasi timbang. Lokasi timbang menentukan divisi mana saja yang diizinkan menimbang di lokasi tersebut.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `code` | `Char` | Ya | Ya | Kode lokasi timbang. Diindeks untuk pencarian. |
| `name` | `Char` | Ya | Ya | Nama lokasi timbang. |
| `estate_id` | `Many2one(wt.estate)` | Ya | Ya | Estate lokasi timbang. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `estate_id.company_id`, `store=True`, readonly. |
| `warehouse_id` | `Many2one(stock.warehouse)` | Ya | Ya | Warehouse Odoo yang terkait lokasi timbang. `ondelete="restrict"`. |
| `operator_id` | `Many2one(hr.employee)` | Tidak | Ya | Employee operator lokasi timbang. Domain berdasarkan employee role `operator`. |
| `allowed_operator_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Operator. |
| `allowed_division_ids` | `Many2many(wt.division)` | Tidak | Ya | Daftar divisi yang diizinkan menimbang di lokasi ini. |

Urutan data:

```text
estate_id, code, name
```

Validasi:

- `code` wajib unik per `estate_id`.
- Semua `allowed_division_ids` harus berasal dari estate yang sama dengan `estate_id`.
- Operator harus valid menurut employee role `operator` pada company lokasi timbang.

Constraint database:

```text
unique(code, estate_id)
```

Pesan validasi:

```text
Weighing location code must be unique per estate.
Allowed divisions must belong to the same estate as the weighing location.
%s employee must belong to the same company.
%s employee role has not been configured for this company.
%s employee must use an allowed job position for this company.
```

Domain UI:

```text
warehouse_id: [('company_id', '=', company_id)]
allowed_division_ids: [('estate_id', '=', estate_id)]
```

Relasi Many2many:

```text
Relation table: wt_weighing_location_division_rel
Left column: weighing_location_id
Right column: division_id
```

Aturan bisnis:

- Lokasi timbang bisa memiliki banyak divisi yang diizinkan.
- Satu divisi bisa diizinkan pada lebih dari satu lokasi timbang.
- Pengaturan hanya dilakukan dari form Weighing Location, bukan dari form Division.

## Foreman

Model teknis:

```text
wt.foreman
```

Deskripsi:

Foreman adalah master mandor/pengawas lapangan yang ditugaskan ke division tertentu.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Related dari `employee_id.name`, dipakai sebagai nama record. |
| `employee_id` | `Many2one(hr.employee)` | Ya | Ya | Employee yang menjadi Foreman/Mandor. Domain berdasarkan employee role `foreman`. `ondelete="restrict"`. |
| `division_id` | `Many2one(wt.division)` | Ya | Ya | Division tempat foreman bertugas. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `division_id.company_id`, `store=True`, readonly. |
| `tapper_ids` | `One2many(wt.tapper)` | Tidak | Tidak | Daftar Tapper yang dibawahi Foreman. |
| `allowed_foreman_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Foreman. |

Urutan data:

```text
division_id, employee_id
```

Validasi:

- Kombinasi `employee_id` dan `division_id` wajib unik.
- Employee foreman harus valid menurut employee role `foreman` pada company division.
- Tapper bisa dikelola langsung dari form Foreman melalui line `Tappers`.

Constraint database:

```text
unique(employee_id, division_id)
```

Pesan validasi:

```text
Foreman employee must be unique per division.
%s employee must belong to the same company.
%s employee role has not been configured for this company.
%s employee must use an allowed job position for this company.
```

## Tapper

Model teknis:

```text
wt.tapper
```

Deskripsi:

Tapper adalah master penyadap yang berada di bawah satu foreman.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Related dari `employee_id.name`, dipakai sebagai nama record. |
| `employee_id` | `Many2one(hr.employee)` | Ya | Ya | Employee yang menjadi Tapper. Domain berdasarkan employee role `tapper`. `ondelete="restrict"`. |
| `division_id` | `Many2one(wt.division)` | Ya | Ya | Division tempat Tapper berada. `ondelete="restrict"`. |
| `foreman_id` | `Many2one(wt.foreman)` | Tidak | Ya | Foreman/Mandor yang membawahi Tapper. Difilter berdasarkan division. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `division_id.company_id`, `store=True`, readonly. |
| `allowed_tapper_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Tapper. |

Urutan data:

```text
division_id, foreman_id, employee_id
```

Validasi:

- Satu Tapper employee hanya boleh dibuat satu kali.
- Employee Tapper harus valid menurut employee role `tapper` pada company division.
- Jika `foreman_id` diisi, Foreman harus berada pada division yang sama dengan Tapper.

Constraint database:

```text
unique(employee_id)
```

Pesan validasi:

```text
Tapper employee must be unique.
Tapper and foreman must belong to the same division.
%s employee must belong to the same company.
%s employee role has not been configured for this company.
%s employee must use an allowed job position for this company.
```

Aturan bisnis:

- Satu Foreman bisa memiliki banyak Tapper.
- Satu Tapper employee hanya boleh memiliki satu record Tapper.
- Division Tapper dipilih langsung.
- Company Tapper otomatis mengikuti Division.
- Foreman Tapper harus berasal dari Division yang sama.

## Device

Model teknis:

```text
wt.device
```

Deskripsi:

Device adalah record assignment perangkat operasional. Administrator membuat assignment terlebih dahulu, lalu token dikirim ke employee penanggung jawab device. Aktivasi device hanya dilakukan melalui API dengan kombinasi token dan `device_id` dari aplikasi lokal.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Tidak | Ya | Nama device. Dapat diedit oleh admin Odoo, termasuk setelah device aktif. |
| `device_id` | `Char` | Tidak | Ya | ID device dari aplikasi lokal. Terisi saat activation API berhasil. Unik. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company assignment device. Default mengikuti company user aktif. |
| `role` | `Selection` | Ya | Ya | Role device: `clerk`, `foreman`, `operator`. Dipilih sebelum employee agar domain employee mengikuti role. |
| `employee_id` | `Many2one(hr.employee)` | Ya | Ya | Employee penanggung jawab device. Domain berdasarkan `company_id` dan `role`. |
| `allowed_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk domain employee. |
| `status` | `Selection` | Ya | Ya | State device: `inactive`, `active`, `blocked`, `revoked`. Ditampilkan sebagai statusbar. |
| `token` | `Char` | Otomatis | Tidak | Token enrollment. Dibuat otomatis saat create jika belum diisi. Unik. |
| `actived_at` | `Datetime` | Tidak | Ya | Waktu aktivasi pertama. Nama field saat ini masih `actived_at`. |
| `last_pull` | `Datetime` | Tidak | Ya | Waktu pull terakhir. Diperbarui saat pull master berhasil. |
| `last_push` | `Datetime` | Tidak | Ya | Waktu push terakhir. Belum digunakan karena push API belum aktif. |
| `last_seen` | `Datetime` | Tidak | Ya | Waktu terakhir device terlihat oleh API. Terisi saat activation. |
| `app_version` | `Char` | Tidak | Ya | Versi aplikasi lokal. Wajib dikirim saat activation. |
| `device_type` | `Selection` | Tidak | Ya | Jenis device: `mobile`, `desktop`. Wajib dikirim saat activation. |
| `blocked_at` | `Datetime` | Tidak | Ya | Waktu block. |
| `blocked_by` | `Many2one(res.users)` | Tidak | Ya | User yang melakukan block. |
| `blocked_reason` | `Text` | Tidak | Ya | Alasan block. Wajib diisi melalui wizard. |
| `reactivated_at` | `Datetime` | Tidak | Ya | Waktu reactivate. |
| `reactivated_by` | `Many2one(res.users)` | Tidak | Ya | User yang melakukan reactivate. |
| `revoked_at` | `Datetime` | Tidak | Ya | Waktu revoke. |
| `revoked_by` | `Many2one(res.users)` | Tidak | Ya | User yang melakukan revoke. |
| `revoked_reason` | `Text` | Tidak | Ya | Alasan revoke. Wajib diisi melalui wizard. |

Selection:

```text
role: clerk, foreman, operator
status: inactive, active, blocked, revoked
device_type: mobile, desktop
```

Urutan data:

```text
name, device_id
```

Constraint database:

```text
unique(device_id)
unique(token)
```

Validasi dan aturan create/write:

- Saat create, `status` default menjadi `inactive`.
- Saat create, `token` otomatis dibuat dengan `secrets.token_urlsafe(32)` jika belum ada token.
- Token dicek unik maksimal 10 kali percobaan.
- Saat device berstatus `active`, `blocked`, atau `revoked`, hanya field `name` yang boleh diedit langsung dari UI.
- Perubahan state dan log state boleh menembus lock hanya jika context berisi:

```text
allow_device_state_update=True
```

- Employee assignment harus valid menurut employee role sesuai `company_id` dan `role`.

Pesan validasi utama:

```text
Device ID must be unique.
Device token must be unique.
Unable to generate a unique device token.
Only device name can be changed after the device has been activated.
Only active devices can be blocked.
Only blocked devices can be reactivated.
Only active or blocked devices can be revoked.
Reason is required.
```

Status flow:

```text
inactive -> active -> blocked -> active
active -> revoked
blocked -> revoked
```

Aturan tombol:

- Tombol `Activate` tidak ada di form. Aktivasi hanya lewat API.
- Tombol `Block` hanya tampil saat status `active`.
- Tombol `Reactivate` hanya tampil saat status `blocked`.
- Tombol `Revoke` hanya tampil saat status `active` atau `blocked`.
- Tombol `Revoke` memakai konfirmasi Odoo `confirm`.
- Block dan Revoke membuka wizard reason agar user wajib mengisi alasan.

Alur assignment dan activation:

1. Admin Odoo membuat record device berstatus `inactive`.
2. Admin memilih `company_id`, `role`, dan `employee_id`.
3. Token terbentuk otomatis saat save.
4. Admin menginformasikan token ke employee penanggung jawab device.
5. Employee menginstall aplikasi operasional. Aplikasi lokal membentuk `device_id`.
6. Employee melakukan activation dengan `server_url`, `token`, `device_id`, `device_type`, dan `app_version`.
7. Odoo memvalidasi token.
8. Jika token milik device berstatus `inactive`, Odoo mengubah status menjadi `active`.
9. Odoo mengisi `device_id`, `device_type`, `app_version`, `actived_at`, dan `last_seen`.
10. Odoo mengirim response berisi data bootstrap device, company, employee, dan role.

Catatan:

- `name` tetap menjadi otoritas Odoo. Perubahan nama device di Odoo dikirim ke aplikasi lokal saat pull master.
- Kombinasi `device_id` dan `token` menjadi dasar authentication pull master dan akan dipakai juga untuk push, dengan syarat device masih berstatus `active`.

## Device State Reason Wizard

Model teknis:

```text
wt.device.state.reason.wizard
```

Jenis model:

```text
TransientModel
```

Deskripsi:

Wizard ini digunakan untuk meminta alasan saat admin melakukan block atau revoke device.

Field:

| Field | Type | Required | Keterangan |
| --- | --- | --- | --- |
| `action` | `Selection` | Ya | Aksi: `block` atau `revoke`. |
| `device_id` | `Many2one(wt.device)` | Ya | Device yang diproses. Readonly. |
| `reason` | `Text` | Ya | Alasan block/revoke. |

Method:

```text
action_confirm()
```

Alur:

- Jika `action = block`, wizard memanggil `device_id.action_confirm_block(reason)`.
- Jika `action = revoke`, wizard memanggil `device_id.action_confirm_revoke(reason)`.
- Setelah selesai, wizard ditutup dengan `ir.actions.act_window_close`.

## API

Model teknis:

```text
wt.api
```

Deskripsi:

API menentukan user internal yang akan menjadi bot user untuk proses API WeighTrack. Saat ini dipakai oleh device activation dan pull master agar perubahan metadata device tercatat atas nama bot user, bukan Public User. Record ini juga menjadi tempat membuka atau menutup endpoint pull dan push per company.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari company dan bot user. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company tempat konfigurasi berlaku. |
| `bot_user_id` | `Many2one(res.users)` | Ya | Ya | User internal aktif yang dipakai untuk proses API. |
| `pull_enabled` | `Boolean` | Tidak | Ya | Jika tidak aktif, endpoint pull data untuk company ini ditutup. Default aktif. |
| `push_enabled` | `Boolean` | Tidak | Ya | Jika tidak aktif, endpoint push data untuk company ini ditutup. Default aktif. Endpoint push belum diekspos. |

Urutan data:

```text
company_id
```

Domain:

```text
bot_user_id: [('share', '=', False), ('active', '=', True)]
```

Constraint database:

```text
unique(company_id)
```

Validasi:

- Satu company hanya boleh memiliki satu API.
- Bot user wajib user internal.
- Bot user wajib aktif.
- Pull master hanya berjalan jika `pull_enabled` aktif.
- Push nanti hanya berjalan jika `push_enabled` aktif.

Pesan validasi:

```text
API must be unique per company.
Only one API is allowed per company.
Bot user must be an internal user.
Bot user must be active.
Device API bot user has not been configured for this company.
```

## API Request Log

Model teknis:

```text
wt.api.request.log
```

Deskripsi:

API Request Log adalah audit log untuk semua request custom API WeighTrack. Log dibuat oleh `controllers/api/api_handler.py`.

Field:

| Field | Type | Required | Readonly | Keterangan |
| --- | --- | --- | --- | --- |
| `request_id` | `Char` | Ya | Ya | UUID per request. Juga dikirim ke client. |
| `endpoint` | `Char` | Ya | Ya | Nama endpoint internal, contoh `device.activate`. |
| `method` | `Char` | Ya | Ya | HTTP method request. |
| `status` | `Selection` | Ya | Ya | `success` atau `failed`. |
| `http_status` | `Integer` | Tidak | Ya | HTTP status response. |
| `error_code` | `Char` | Tidak | Ya | Kode error jika gagal. |
| `error_message` | `Text` | Tidak | Ya | Pesan error jika gagal. |
| `device_id` | `Char` | Tidak | Ya | `device_id` dari payload request. |
| `device_record_id` | `Many2one(wt.device)` | Tidak | Ya | Record device terkait jika sudah teridentifikasi. |
| `company_id` | `Many2one(res.company)` | Tidak | Ya | Company dari device terkait. |
| `employee_id` | `Many2one(hr.employee)` | Tidak | Ya | Employee dari device terkait. |
| `role` | `Selection` | Tidak | Ya | Role device terkait. |
| `request_ip` | `Char` | Tidak | Ya | IP client dari request. |
| `user_agent` | `Char` | Tidak | Ya | Header User-Agent client. |
| `duration_ms` | `Integer` | Tidak | Ya | Durasi proses request dalam milidetik. |
| `requested_at` | `Datetime` | Ya | Ya | Waktu request diterima. |
| `finished_at` | `Datetime` | Tidak | Ya | Waktu request selesai diproses. |
| `payload_hash` | `Char` | Tidak | Ya | SHA-256 raw request body untuk fingerprint audit. |
| `payload` | `Text` | Tidak | Ya | Payload request lengkap setelah sanitasi. |
| `response` | `Text` | Tidak | Ya | Response lengkap setelah sanitasi. |

Urutan data:

```text
requested_at desc, id desc
```

Selection:

```text
status: success, failed
role: clerk, foreman, operator
```

Aturan akses:

- Admin hanya bisa read.
- Create/write/delete log tidak tersedia dari UI.
- Log dibuat otomatis oleh API Handler memakai `sudo()`.

Sanitasi:

Key berikut disamarkan di `payload` dan `response`:

```text
token
password
secret
api_key
```

Catatan audit:

- `payload_hash` bukan enkripsi dan tidak bisa didekripsi.
- Hash dipakai untuk membuktikan apakah raw request body sama dengan request tertentu.
- Payload dan response disimpan lengkap untuk kebutuhan debug, dengan token/API key disanitasi.

## API Services

Service API adalah `AbstractModel`. Service ini tidak memiliki tabel database sendiri.

### API Device Service

Model teknis:

```text
wt.api.device.service
```

File:

```text
services/api_device_service.py
```

Tanggung jawab:

- Memproses activation device.
- Memvalidasi payload activation.
- Mencari device berdasarkan token.
- Memastikan token hanya bisa dipakai saat device masih `inactive`.
- Memastikan `device_id` tidak dipakai device lain.
- Mengambil bot user dari `wt.api.security.service`.
- Menulis perubahan device sebagai bot user.
- Menyiapkan payload data bisnis untuk response.

Method utama:

```text
activate_device(payload)
```

Payload wajib:

```text
token
device_id
device_type
app_version
```

Error codes:

```text
missing_token
missing_device_id
missing_device_type
missing_app_version
invalid_device_type
invalid_token
device_not_inactive
device_id_already_used
api_missing
api_invalid
```

Response data yang disiapkan service:

```text
device
company
employee
role
```

Device payload:

```text
id
device_id
name
status
device_type
app_version
last_seen
```

Company payload:

```text
id
name
```

Employee payload:

```text
id
barcode
name
job_position
```

### API Security Service

Model teknis:

```text
wt.api.security.service
```

File:

```text
services/api_security_service.py
```

Tanggung jawab:

- Menjadi pusat helper security API.
- Mengambil API berdasarkan company.
- Mengautentikasi device aktif memakai kombinasi `device_id` dan `token`.
- Membatasi role device untuk endpoint tertentu jika diperlukan.
- Mengecek apakah pull data dibuka melalui `wt.api.pull_enabled`.
- Mengecek apakah push data dibuka melalui `wt.api.push_enabled`.
- Mengambil bot user berdasarkan company.
- Mengembalikan error standar jika config belum ada atau bot user tidak valid.

Method utama:

```text
get_api(company, device=False)
authenticate_device(payload, allowed_roles=False)
check_pull_enabled(company, device=False)
check_push_enabled(company, device=False)
get_bot_user(company, device=False)
```

Aturan:

- Config dicari pada `wt.api` berdasarkan `company_id`.
- `authenticate_device` membutuhkan `token` dan `device_id`.
- Device harus berstatus `active`.
- Bot user harus aktif.
- Bot user tidak boleh portal/public/share user.
- Pull ditolak jika `pull_enabled = False`.
- Push ditolak jika `push_enabled = False`.

Error codes:

```text
missing_token
missing_device_id
invalid_device_credentials
device_not_active
role_not_allowed
pull_closed
push_closed
api_missing
api_invalid
```

### API Pull Master Service

Model teknis:

```text
wt.api.pull.master.service
```

File:

```text
services/api_pull_master_service.py
```

Tanggung jawab:

- Memproses pull master untuk aplikasi offline penimbangan.
- Mengautentikasi device melalui `wt.api.security.service`.
- Memastikan role device termasuk `operator`, `clerk`, atau `foreman`.
- Memastikan pull dibuka melalui `wt.api.pull_enabled`.
- Mengambil bot user dari `wt.api.security.service`.
- Menghitung scope data berdasarkan company, employee, dan role device.
- Memperbarui `last_pull`, `last_seen`, dan `app_version` jika dikirim.
- Menyiapkan payload response berisi `meta`, `scope`, dan `masters`.

Method utama:

```text
pull_master(payload)
```

Payload wajib:

```text
token
device_id
```

Payload opsional:

```text
app_version
```

Scope role:

| Role | Scope |
| --- | --- |
| `foreman` | Foreman record milik employee device, division foreman, tapper yang berada di bawah foreman tersebut, estate, dan weighing location terkait division. |
| `clerk` | Division yang `clerk_id`-nya employee device, foreman di division tersebut, tapper di division tersebut, estate, dan weighing location terkait division. |
| `operator` | Weighing location yang `operator_id`-nya employee device, allowed division dari weighing location, clerk division, foreman, tapper, estate, dan warehouse. |

Response data yang disiapkan service:

```text
meta
scope
masters
```

Meta payload:

```text
server_time
role
company_id
employee_id
device
```

Scope payload:

```text
role
company_id
employee_id
estate_ids
division_ids
weighing_location_ids
clerk_employee_ids
foreman_ids
operator_employee_ids
tapper_ids
```

Master payload:

```text
company
employee
estates
divisions
weighing_locations
clerks
foremen
operators
tappers
```

Catatan payload:

- `pull_type` tidak dipakai.
- Payload device berada di `data.meta.device`.
- Payload company dan employee berada di `data.masters.company` dan `data.masters.employee`.
- Setiap data master minimal membawa `id` dan `name`.
- Master yang memiliki `code`, seperti Estate, Division, dan Weighing Location, ikut membawa `code`.
- Employee barcode dibawa untuk employee device, clerks, foremen, operators, dan tappers.

### API Response Service

Model teknis:

```text
wt.api.response.service
```

File:

```text
services/api_response_service.py
```

Tanggung jawab:

- Membuat struktur result internal success/error.
- Membungkus response HTTP final dengan `request_id`.
- Tidak menyiapkan payload bisnis. Data bisnis disiapkan oleh service masing-masing.

Method:

```text
success(data, http_status=200, device=False)
error(code, message, http_status, device=False)
body(request_id, result)
```

Format response success:

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {}
}
```

Format response error:

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

## API Handler

API Handler bukan model Odoo, tetapi class helper Python.

File:

```text
controllers/api/api_handler.py
```

Tanggung jawab:

- Membaca raw request body.
- Membuat `request_id`.
- Membuat `payload_hash`.
- Parse JSON payload.
- Memanggil service model dan method yang diberikan endpoint.
- Membuat body response lewat `wt.api.response.service`.
- Membuat record `wt.api.request.log`.
- Mengembalikan HTTP JSON response.

Error boundary:

```text
invalid_json
invalid_payload
internal_error
```

Sanitasi log dilakukan oleh:

```text
_sanitize_payload(value)
```

## API Controller

Endpoint aktif:

```text
POST /weightrack/api/v1/device/activate
POST /weightrack/api/v1/pull/master
```

File:

```text
controllers/api/v1/device_api.py
controllers/api/v1/pull_api.py
```

Route activation:

```python
@http.route(
    "/weightrack/api/v1/device/activate",
    type="http",
    auth="public",
    methods=["POST"],
    csrf=False,
)
```

Route pull master:

```python
@http.route(
    "/weightrack/api/v1/pull/master",
    type="http",
    auth="public",
    methods=["POST"],
    csrf=False,
)
```

Controller hanya mendefinisikan endpoint. Logic request, response, audit, dan business flow dipisah ke handler dan service.

## Current Security

Group:

```text
weightrack.group_admin
```

Nama role yang tampil:

```text
Administrator
```

Access CSV:

| Model | Read | Write | Create | Delete |
| --- | --- | --- | --- | --- |
| `wt.estate` | Ya | Ya | Ya | Ya |
| `wt.employee.role` | Ya | Ya | Ya | Ya |
| `wt.api` | Ya | Ya | Ya | Ya |
| `wt.api.request.log` | Ya | Tidak | Tidak | Tidak |
| `wt.division` | Ya | Ya | Ya | Ya |
| `wt.weighing.location` | Ya | Ya | Ya | Ya |
| `wt.foreman` | Ya | Ya | Ya | Ya |
| `wt.tapper` | Ya | Ya | Ya | Ya |
| `wt.device` | Ya | Ya | Ya | Ya |
| `wt.device.state.reason.wizard` | Ya | Ya | Ya | Ya |
| `hr.employee` | Ya | Tidak | Tidak | Tidak |
| `hr.job` | Ya | Tidak | Tidak | Tidak |
| `stock.warehouse` | Ya | Tidak | Tidak | Tidak |

## File Utama

Models:

```text
models/estate.py
models/employee_role.py
models/division.py
models/weighing_location.py
models/foreman.py
models/tapper.py
models/device.py
models/api.py
models/api_request_log.py
```

Wizards:

```text
wizards/device_state_reason_wizard.py
```

Services:

```text
services/api_device_service.py
services/api_pull_master_service.py
services/api_security_service.py
services/api_response_service.py
```

Controllers:

```text
controllers/api/api_handler.py
controllers/api/v1/device_api.py
controllers/api/v1/pull_api.py
```

Views:

```text
views/estate_views.xml
views/employee_role_views.xml
views/division_views.xml
views/weighing_location_views.xml
views/foreman_views.xml
views/tapper_views.xml
views/device_views.xml
views/device_state_reason_wizard_views.xml
views/api_views.xml
views/api_request_log_views.xml
views/menu.xml
```

Security:

```text
security/access_groups.xml
security/ir.model.access.csv
```

Translation:

```text
i18n/id_ID.po
```
