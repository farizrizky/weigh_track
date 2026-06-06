# WeighTrack Development Context

Dokumen ini adalah konteks kerja ringkas untuk melanjutkan pengembangan module WeighTrack.

## Project

WeighTrack adalah custom module Odoo 19 untuk aplikasi operasional penimbangan estate.

Lokasi server:

```text
/opt/odoo/custom-addons/weightrack
```

Lokasi Windows/SSHFS workspace:

```text
i:/odoo/custom-addons/weightrack
```

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

## Current Scope

Scope aktif saat ini:

- Master data estate operation.
- Assignment dan lifecycle device.
- API configuration untuk bot user.
- API request audit log.
- Custom API device activation.

Scope yang belum aktif:

- API pull data.
- API push data.
- Sinkronisasi data timbang operasional.
- Authentication pull/push menggunakan kombinasi `device_id` dan `token`.

Custom API yang aktif saat ini hanya:

```text
POST /weightrack/api/v1/device/activate
```

## Important Conventions

- Semua model WeighTrack memakai prefix teknis `wt.`.
- Nama teknis model dan field memakai bahasa Inggris.
- Label UI bahasa Indonesia dikelola lewat `i18n/id_ID.po`.
- Master operasional utama memakai chatter:
  - `_inherit = ["mail.thread", "mail.activity.mixin"]`
  - field penting memakai `tracking=True`
  - form view memakai `<chatter/>`
- Field `name` pada form dibuat sebagai title besar menggunakan `oe_title`.
- Akses module dibatasi dengan group `weightrack.group_admin`.
- Jangan buat role aplikasi baru dulu. Untuk saat ini role aplikasi hanya `Administrator`.
- Role employee operasional diatur lewat `wt.employee.role.mapping` berdasarkan company, role, dan job position.
- File service API ditempatkan di folder `services/`, setara dengan `models/`.
- Folder `models/` dipakai untuk model database/master data.
- Folder `services/` dipakai untuk business logic/service layer jangka panjang.
- Controller API dibuat tipis. Controller hanya endpoint, logic masuk handler/service.

## Environment Permission Note

Di environment SSHFS ini, file baru kadang tidak bisa dibaca Odoo karena permission file. Setelah membuat atau mengganti file, jalankan:

```powershell
C:\Windows\System32\icacls.exe "custom-addons\weightrack\<path-file>" /grant Everyone:RX
```

Alternatif dari server Linux:

```bash
sudo chmod -R u+rwX,go+rX /opt/odoo/custom-addons/weightrack
```

## Existing Models

Model database:

- `wt.estate`
- `wt.employee.role.mapping`
- `wt.api.config`
- `wt.api.request.log`
- `wt.division`
- `wt.weighing.location`
- `wt.foreman`
- `wt.tapper`
- `wt.device`

Transient model:

- `wt.device.state.reason.wizard`

Abstract service model:

- `wt.api.device.service`
- `wt.api.security.service`
- `wt.api.response.service`

## Menu Structure

```text
WeighTrack
|-- Master Data
|   |-- Estates
|   |-- Divisions
|   |-- Weighing Locations
|   |-- Foremen
|   `-- Tappers
|-- Device
`-- Configuration
    |-- API Configuration
    |-- API Request Logs
    `-- Employee Role Mappings
```

## Rename History

- Istilah lama `Supervisor` sudah diganti menjadi `Foreman`.
- Model teknis lama `wt.supervisor` sudah diganti menjadi `wt.foreman`.
- Field relasi Tapper lama `supervisor_id` sudah diganti menjadi `foreman_id`.
- Istilah lama `Krani` di Division sudah diganti menjadi `Clerk`.
- Field Division lama `krani_id` sudah diganti menjadi `clerk_id`.
- Role employee mapping lama `krani` sudah diganti menjadi `clerk`.
- Field Device lama `device_name` sudah diganti menjadi `name`.
- Service lama `device_auth_service` sudah diganti menjadi `api_device_service`.
- Service lama `response_service` sudah diganti menjadi `api_response_service`.

Jika database lama masih menyimpan metadata rename teknis, alur paling bersih adalah uninstall module lama atau bersihkan data lama, lalu install/upgrade ulang module.

## Data Design Notes

- `Division` wajib terhubung ke `Estate`.
- `Weighing Location` wajib terhubung ke `Estate` dan `Warehouse`.
- `company_id` pada `Division`, `Weighing Location`, `Foreman`, dan `Tapper` mengikuti parent operasional.
- Pengaturan divisi yang boleh menimbang hanya dilakukan dari `Weighing Location` melalui `allowed_division_ids`.
- `Division` tidak perlu menampilkan atau mengatur relasi balik ke `Weighing Location`.
- `warehouse_id` memakai model Odoo bawaan `stock.warehouse`.
- Employee operasional memakai model Odoo bawaan `hr.employee`.
- `wt.employee.role.mapping` menentukan job position yang boleh dipilih untuk role:
  - `operator`
  - `clerk`
  - `foreman`
  - `tapper`
- Role mapping menjadi sumber domain employee dan validasi company/job position.

## Device Concept

`wt.device` adalah assignment/enrollment device operasional, bukan sekadar master nama device.

Assignment device menghubungkan:

- `company_id`
- `role`
- `employee_id`
- `name`
- `token`

Informasi teknis device diisi saat activation API:

- `device_id`
- `device_type`
- `app_version`
- `actived_at`
- `last_seen`

Role device yang aktif:

```text
clerk
foreman
operator
```

Status device:

```text
inactive
active
blocked
revoked
```

Device type:

```text
mobile
desktop
```

Aturan penting:

- Admin Odoo membuat assignment device terlebih dahulu.
- Token dibuat otomatis saat record device disimpan.
- Status awal device adalah `inactive`.
- Aktivasi awal hanya lewat API, bukan tombol manual.
- `device_id` dibuat oleh aplikasi operasional saat install/activation.
- `device_type` dan `app_version` wajib dikirim saat activation.
- `name` adalah otoritas Odoo dan tetap boleh diedit walaupun device sudah aktif.
- Setelah device `active`, `blocked`, atau `revoked`, field selain `name` tidak boleh diedit manual.
- Perubahan state internal memakai context `allow_device_state_update=True`.

## Device Assignment Flow

Alur assignment:

1. Administrator membuat record `wt.device`.
2. Administrator memilih `company_id`.
3. Administrator memilih `role`.
4. Domain `employee_id` mengikuti company dan role.
5. Administrator memilih `employee_id`.
6. Administrator dapat mengisi `name` sebagai label device.
7. Saat save, Odoo membuat `token` otomatis.
8. Status device menjadi `inactive`.
9. Administrator menginformasikan token ke employee penanggung jawab device.

## Device Activation Flow

Alur activation:

1. Employee menginstall aplikasi operasional penimbangan.
2. Aplikasi lokal membentuk dan menyimpan `device_id`.
3. Employee mengisi server URL dan token.
4. Aplikasi mengirim request JSON ke:

```text
POST /weightrack/api/v1/device/activate
```

Payload wajib:

```text
token
device_id
device_type
app_version
```

5. Odoo mencari `wt.device` berdasarkan token.
6. Odoo memastikan device masih berstatus `inactive`.
7. Odoo memastikan `device_id` belum dipakai device lain.
8. Odoo mengambil bot user dari `wt.api.config` berdasarkan company device.
9. Odoo menulis perubahan device dengan bot user, bukan Public User.
10. Odoo mengubah device menjadi `active`.
11. Odoo mengisi `device_id`, `device_type`, `app_version`, `actived_at`, dan `last_seen`.
12. Odoo mengembalikan data bootstrap untuk aplikasi lokal.

Response activation success dibungkus dalam attribute `data`.

Data bootstrap:

- `device`
  - `id`
  - `device_id`
  - `name`
  - `status`
  - `device_type`
  - `app_version`
  - `last_seen`
- `company`
  - `id`
  - `name`
- `employee`
  - `id`
  - `barcode`
  - `name`
  - `job_position`
- `role`

Catatan penting:

- `company.code` tidak dikirim di response.
- `employee.badge_id` dan `employee.badge_number` tidak dipakai.
- Field employee yang dikirim adalah `barcode`.

## Device State Flow

Status flow:

```text
inactive -> active -> blocked -> active
active -> revoked
blocked -> revoked
```

Aturan tombol:

- Tombol `Activate` tidak ada.
- Tombol `Block` hanya tampil saat status `active`.
- Tombol `Reactivate` hanya tampil saat status `blocked`.
- Tombol `Revoke` hanya tampil saat status `active` atau `blocked`.
- `Revoke` memakai confirm dialog Odoo sebelum wizard reason.
- `Block` dan `Revoke` wajib meminta reason melalui `wt.device.state.reason.wizard`.
- `Reactivate` tidak memakai reason saat ini.

Field log state:

- `blocked_at`
- `blocked_by`
- `blocked_reason`
- `reactivated_at`
- `reactivated_by`
- `revoked_at`
- `revoked_by`
- `revoked_reason`

Field runtime/log state tidak diedit manual dari form admin.

## API Configuration

`wt.api.config` menentukan internal bot user untuk custom API.

Aturan:

- Satu company hanya boleh punya satu API Configuration.
- `bot_user_id` wajib internal user.
- `bot_user_id` wajib active.
- Bot user dipakai agar perubahan melalui API tidak tercatat sebagai Public User.

Saat ini config dipakai oleh activation device. Nanti pull/push juga akan memakai config ini.

## API Request Log

`wt.api.request.log` menyimpan audit custom API.

Data yang disimpan:

- `request_id`
- `endpoint`
- `method`
- `status`
- `http_status`
- `error_code`
- `error_message`
- `device_id`
- `device_record_id`
- `company_id`
- `employee_id`
- `role`
- `request_ip`
- `user_agent`
- `duration_ms`
- `requested_at`
- `finished_at`
- `payload_hash`
- `payload`
- `response`

Log bersifat read-only dari UI. Create/write/delete log tidak diberikan ke admin melalui access CSV.

Audit payload:

- Payload request disimpan lengkap setelah sanitasi.
- Response disimpan lengkap setelah sanitasi.
- Token dan key sensitif disamarkan.
- `payload_hash` adalah SHA-256 dari raw request body.
- `payload_hash` bukan enkripsi dan tidak bisa didekripsi.
- Hash dipakai sebagai fingerprint untuk membandingkan raw payload yang sama.

Key yang disanitasi:

```text
token
password
secret
api_key
```

## API Structure

Controller:

```text
controllers/api/v1/device_api.py
```

Handler:

```text
controllers/api/api_handler.py
```

Services:

```text
services/api_device_service.py
services/api_security_service.py
services/api_response_service.py
```

Controller rule:

- Controller hanya berisi route endpoint.
- Controller tidak memproses JSON secara detail.
- Controller tidak membentuk response body sendiri.
- Controller mendelegasikan request ke `ApiHandler`.

Handler rule:

- `ApiHandler` menjadi HTTP boundary.
- Handler parse JSON.
- Handler membuat `request_id`.
- Handler membuat `payload_hash`.
- Handler memanggil service.
- Handler membuat audit log.
- Handler mengembalikan HTTP JSON response.

Service rule:

- Service menyiapkan business payload masing-masing.
- `api_device_service` menyiapkan payload activation.
- `api_response_service` hanya membungkus success/error/body.
- `api_security_service` memusatkan helper security API seperti lookup bot user.

## API Response Convention

Success:

```json
{
  "ok": true,
  "request_id": "uuid",
  "data": {}
}
```

Error:

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

Prinsip:

- Data bisnis selalu disiapkan di service terkait.
- Response service hanya membungkus format standar.
- Response success selalu memakai attribute `data`.

## Future Pull And Push

Pull dan push belum diekspos.

Konsep yang sudah disepakati:

- Setiap request pull/push membawa `device_id` dan `token`.
- Odoo memvalidasi kombinasi `device_id` dan `token`.
- Device harus berstatus `active`.
- Setelah valid, Odoo memakai company, employee, dan role dari assignment device.
- Proses baca/tulis data bisnis diarahkan ke bot user dari `wt.api.config`.
- Request tetap masuk sebagai `auth="public"` pada endpoint custom API.
- Eksekusi bisnis di backend diarahkan ke internal bot user agar auditable.
- Pull akan mengirim data yang dibutuhkan aplikasi lokal, termasuk perubahan `name` device dari Odoo.
- Push akan dibuat hati-hati agar tidak melanggar user license; aktivitas database diarahkan ke bot user internal yang memang dikonfigurasi.
- Semua request pull/push nanti tetap masuk ke `wt.api.request.log`.

## Localization Notes

File translasi:

```text
i18n/id_ID.po
```

Prinsip translasi:

- Nama teknis tetap English.
- UI bisa memakai bahasa Indonesia operasional.
- Pesan validasi Python harus dibungkus `_()` agar bisa diterjemahkan.

Istilah utama:

- `Code` -> `Kode`
- `Name` -> `Nama`
- `Company` -> `Perusahaan`
- `Master Data` -> `Data Master`
- `Employee Role Mapping(s)` -> `Mapping Role Karyawan`
- `Job Position` -> `Jabatan`
- `Division` / `Divisions` -> `Divisi`
- `Weighing Location` / `Weighing Locations` -> `Lokasi Timbang`
- `Warehouse` -> `Gudang`
- `Clerk` -> `Kerani`
- `Foreman` / `Foremen` -> `Mandor`
- `Operator` -> `Operator`
- `Tapper` / `Tappers` -> `Tapper`
- `Device` -> `Device`
- `API Configuration` -> `Konfigurasi API`
- `API Request Logs` -> `Log Request API`
- `Bot User` -> `User Bot`
- `Payload` -> `Payload`
- `Response` -> `Response`

## Documentation Files

Dokumentasi utama:

```text
API DOCUMENTATION.md
MODEL_REFERENCE.md
WEIGHTRACK_CONTEXT.md
weightrack.dbml
```

Peran dokumen:

- `API DOCUMENTATION.md` menjelaskan endpoint API dan format request/response.
- `MODEL_REFERENCE.md` menjelaskan model, field, relasi, service, security, dan validasi.
- `WEIGHTRACK_CONTEXT.md` menjadi ringkasan keputusan desain untuk melanjutkan pengembangan.
- `weightrack.dbml` menjadi referensi struktur database untuk dbdiagram/db.io.

## Upgrade Notes

Setelah perubahan Python, restart Odoo:

```bash
sudo systemctl restart odoo
```

Setelah perubahan XML/security/data, upgrade module `WeighTrack` dari Apps.

Untuk perubahan route/controller API:

1. Pastikan file controller ter-import dari `__init__.py`.
2. Restart Odoo.
3. Upgrade module jika ada perubahan manifest/data.
4. Restart ulang bila route masih belum terbaca.
5. Pastikan permission file/folder bisa dibaca service Odoo.

## Known Environment Notes

- Parent git di `/opt/odoo/custom-addons` pernah dinonaktifkan dengan rename `.git` menjadi `.git-disabled-custom-addons`.
- Git yang dipakai seharusnya hanya repo module:

```text
/opt/odoo/custom-addons/weightrack
```

- Push ke GitHub dari server pernah gagal karena SSH key GitHub belum terpasang di server.
- Pada SSHFS Windows, `git diff` kadang gagal dengan error filesystem `Function not implemented`.
- Untuk verifikasi cepat, baca file langsung dengan `Get-Content` dan validasi syntax/JSON snippet bila perlu.
