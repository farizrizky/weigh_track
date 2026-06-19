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
g:/odoo/custom-addons/weightrack
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
product
```

## Current Scope

Scope aktif saat ini:

- Master data estate operation.
- Master cuaca dan data cuaca estate.
- Konfigurasi mapping produk timbang.
- Konfigurasi toleransi penyusutan produksi.
- Assignment dan lifecycle device.
- API untuk bot user.
- API request audit log.
- Custom API device activation.
- API pull master untuk data offline penimbangan.
- API push weighing cup lump untuk data timbang cup lump dari aplikasi offline.

Scope yang belum aktif:

- Push data timbang selain cup_lump.
- Pembuatan inbound/receipt stock resmi dari data weighing cup lump.

Custom API yang aktif saat ini:

```text
POST /weightrack/api/v1/device/activate
POST /weightrack/api/v1/pull/master
POST /weightrack/api/v1/push/weighing-cup-lump
```

## Important Conventions

- Semua model WeighTrack memakai prefix teknis `wt.`.
- Nama teknis model dan field memakai bahasa Inggris.
- Label UI bahasa Indonesia dikelola lewat `i18n/id_ID.po`.
- Master operasional utama memakai chatter:
  - `_inherit = ["mail.thread", "mail.activity.mixin"]`
  - field penting memakai `tracking=True`
  - form view memakai `<chatter/>`
- Field `name` pada form umumnya dibuat sebagai title besar menggunakan `oe_title`.
- Pengecualian saat ini:
  - `wt.shrinkage.tolerance`: `name` disembunyikan dari form, field paling atas adalah `company_id`.
  - `wt.weather.data`: `name` disembunyikan dari form, field paling atas adalah `weather_date`.
- Akses module dibatasi dengan group `weightrack.group_admin`.
- Jangan buat role aplikasi baru dulu. Untuk saat ini role aplikasi hanya `Administrator`.
- Role employee operasional diatur lewat `wt.employee.role` berdasarkan company, role, dan job position.
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
- `wt.weather`
- `wt.weather.data`
- `wt.employee.role`
- `wt.product`
- `wt.shrinkage.tolerance`
- `wt.receipt.rule`
- `wt.api`
- `wt.api.request.log`
- `wt.division`
- `wt.weighing.location`
- `wt.foreman`
- `wt.tapper`
- `wt.device`
- `wt.weighing.cup.lump`

Transient model:

- `wt.device.state.reason.wizard`

Abstract service model:

- `wt.api.device.service`
- `wt.api.pull.master.service`
- `wt.api.push.weighing.cup.lump.service`
- `wt.cup.lump.service`
- `wt.api.security.service`
- `wt.api.response.service`

## Menu Structure

```text
WeighTrack
|-- Master Data
|   |-- Estates
|   |-- Weather
|   |-- Weather Data
|   |-- Divisions
|   |-- Weighing Locations
|   |-- Foremen
|   `-- Tappers
|-- Operations
|   `-- Weighing Cup Lump
|-- Device
`-- Configuration
    |-- API
    |-- API Request Logs
    |-- Employee Roles
    |-- Product
    |-- Shrinkage Tolerance
    `-- Receipt Rule
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
- `wt.weather` adalah master cuaca sederhana yang berisi nama dan deskripsi.
- `wt.weather.data` menyimpan data cuaca per tanggal dan estate.
- Satu estate hanya boleh memiliki satu data cuaca untuk tanggal yang sama.
- Data cuaca saat ini belum diekspos melalui custom API dan belum masuk payload pull master.
- `Weighing Location` wajib terhubung ke `Estate`.
- `company_id` pada `Division`, `Weighing Location`, `Foreman`, dan `Tapper` mengikuti parent operasional.
- Pengaturan divisi yang boleh menimbang hanya dilakukan dari `Weighing Location` melalui `allowed_division_ids`.
- `Division` tidak perlu menampilkan atau mengatur relasi balik ke `Weighing Location`.
- `wt.product` memetakan `company_id` + `product_type` ke produk Odoo `product.product` yang dipakai untuk proses timbang.
- Satu company hanya boleh memiliki satu mapping untuk setiap `product_type`.
- `wt.shrinkage.tolerance` menentukan batas toleransi penyusutan produksi per company, product type, dan division.
- Batas toleransi penyusutan dipakai saat hari produksi tidak sama dengan hari penimbangan di gudang induk.
- Kombinasi Company, Product Type, dan Division pada `wt.shrinkage.tolerance` tidak boleh berulang.
- Division pada `wt.shrinkage.tolerance` wajib berasal dari company yang sama.
- `wt.receipt.rule` menegaskan produk yang boleh ditimbang pada kombinasi Weighing Location dan Division tertentu, sekaligus menentukan Warehouse, Location, dan Operation Type untuk proses receipt stok.
- Pilihan Product pada `wt.receipt.rule` dibatasi dari product yang sudah dikonfigurasi di `wt.product` untuk company Weighing Location.
- Division pada `wt.receipt.rule` wajib termasuk `allowed_division_ids` pada Weighing Location.
- Kombinasi Company, Weighing Location, Division, dan Product pada `wt.receipt.rule` tidak boleh berulang. Validasi duplicate menampilkan nilai company, lokasi timbang, divisi, dan produk yang sudah ada.
- Pengaturan Warehouse tidak berada di Weighing Location; Warehouse, Location, dan Operation Type ditentukan pada Receipt Rule.
- Employee operasional memakai model Odoo bawaan `hr.employee`.
- `wt.employee.role` menentukan job position yang boleh dipilih untuk role:
  - `operator`
  - `clerk`
  - `foreman`
  - `tapper`
- Employee Role menjadi sumber domain employee dan validasi company/job position.

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
8. Odoo mengambil bot user dari `wt.api` berdasarkan company device.
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

## API

`wt.api` menentukan internal bot user untuk custom API.

Aturan:

- Satu company hanya boleh punya satu API.
- `bot_user_id` wajib internal user.
- `bot_user_id` wajib active.
- Bot user dipakai agar perubahan melalui API tidak tercatat sebagai Public User.
- `pull_enabled` mengatur apakah endpoint pull data boleh dipakai untuk company tersebut.
- `push_enabled` mengatur apakah endpoint push data boleh dipakai untuk company tersebut.

Saat ini record API dipakai oleh activation device, pull master, dan push weighing cup lump. `push_enabled` mengatur apakah endpoint push boleh dipakai oleh device company tersebut.

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
controllers/api/v1/pull_api.py
controllers/api/v1/push_api.py
```

Handler:

```text
controllers/api/api_handler.py
```

Services:

```text
services/api_device_service.py
services/api_pull_master_service.py
services/api_push_weighing_cup_lump_service.py
services/cup_lump_service.py
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
- `api_pull_master_service` menyiapkan payload pull master offline.
- `api_response_service` hanya membungkus success/error/body.
- `api_security_service` memusatkan helper security API seperti autentikasi device, lookup config, lookup bot user, dan pengecekan pull/push enabled.

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

## Pull Master

Pull master sudah diekspos melalui:

```text
POST /weightrack/api/v1/pull/master
```

Prinsip pull master:

- Request membawa `device_id` dan `token`.
- Odoo memvalidasi kombinasi `device_id` dan `token` melalui `api_security_service.authenticate_device`.
- Device harus berstatus `active`.
- Role device yang boleh pull adalah `operator`, `clerk`, dan `foreman`.
- `wt.api.pull_enabled` harus aktif untuk company device.
- Setelah valid, Odoo memakai company, employee, dan role dari assignment device.
- Proses update metadata device diarahkan ke bot user dari `wt.api`.
- Request tetap masuk sebagai `auth="public"` pada endpoint custom API.
- Semua request pull tetap masuk ke `wt.api.request.log`.

Payload response pull master:

- Root data berisi `meta`, `scope`, dan `masters`.
- `meta` berisi `server_time`, `timezone`, role, company, employee, dan payload device.
- `server_time`, `last_pull`, dan `last_seen` diformat memakai timezone bot user dari `wt.api`.
- `scope` berisi batas kerja device dalam bentuk daftar ID.
- `scope` membawa `role`, `company_id`, `estate_ids`, `division_ids`, `weighing_location_ids`, `receipt_rule_ids`, `product_ids`, `product_type_codes`, `uom_ids`, `shrinkage_tolerance_ids`, `employee_ids`, `foreman_ids`, dan `tapper_ids`.
- `masters` berisi company, roles, employees, estate, division, weighing location, receipt rule, product, UoM, product type, shrinkage tolerance, foreman, dan tapper.
- `masters.roles` hanya membawa role milik device yang sedang pull.
- `masters.product_types` hanya membawa product type yang benar-benar berasal dari mapping `wt.product` untuk product dalam scope.
- `masters.shrinkage_tolerances` hanya membawa toleransi yang sesuai dengan division dan product type dalam scope device.
- Pull master tidak mengirim warehouse, location, dan operation type; nilai tersebut tetap menjadi konfigurasi backend pada Receipt Rule.
- Product payload pada pull master membawa `id`, `name`, `company_id`, `uom_id`, dan `product_type`; `default_code` tidak dikirim.
- `pull_type` tidak dipakai.
- Company dan employees berada di `masters`, bukan root data.
- Employee dipusatkan di `masters.employees`; payload foreman dan tapper hanya membawa relasi `employee_id`.
- Device berada di `meta.device`.

Scope role pull:

- `foreman`: foreman record milik employee device, division foreman, tapper di bawah foreman tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait.
- `clerk`: division yang dipegang clerk, foreman di division tersebut, tapper di division tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait.
- `operator`: weighing location yang dipegang operator, allowed division dari location, receipt rule, product, UoM, shrinkage tolerance, clerk division, foreman, tapper, dan estate.

## Push Weighing Cup Lump

Push weighing cup lump sudah diekspos melalui:

```text
POST /weightrack/api/v1/push/weighing-cup-lump
```

Konsep:

- Request push membawa `device_id` dan `token`.
- Odoo memvalidasi kombinasi `device_id` dan `token` melalui `api_security_service.authenticate_device`.
- Device harus berstatus `active`.
- Role device yang boleh push data penimbangan hanya `operator`.
- `wt.api.push_enabled` harus aktif untuk company device.
- Setelah valid, Odoo memakai company, employee, dan role dari assignment device.
- Eksekusi tulis data bisnis diarahkan ke internal bot user agar auditable.
- Semua request push masuk ke `wt.api.request.log`.
- Push saat ini hanya menerima product type `cup_lump`.
- Data push tidak langsung menjadi stock.
- Data push saat ini langsung membentuk detail `wt.weighing.cup.lump`.
- Model inbound/header belum aktif kembali; rencana pembentukan inbound/receipt akan dibuat terpisah setelah desain per product type matang.

Struktur runtime saat ini:

- `wt.weighing.cup.lump`
  - Detail penimbangan untuk product type `cup_lump`.
  - Number memakai format `WH/PRODUCT_TYPE/YYYYMMDD/NNN`.
  - Menyimpan raw data penimbangan cup lump, termasuk field berat khusus cup lump.
  - Menyimpan `data_source` dengan nilai `api` atau `manual`.
  - Data manual baru menyimpan `local_id`, `device_id`, `device_record_id`, dan `batch_local_id` sebagai null.
  - Data API mewajibkan `local_id`, `device_id`, dan `device_record_id`.
  - Menyimpan employee operator, clerk, foreman, dan tapper langsung pada detail timbang.
  - Nama dan badge number employee dikunci mengikuti `hr.employee`, bukan mengikuti struktur assignment lama.
  - Field `foreman_id` dan `tapper_id` tetap disimpan untuk kebutuhan validasi assignment, tetapi yang ditampilkan ke user adalah employee.
  - Initial weighing/penimbangan lapangan awal disimpan di detail cup lump.
  - `initial_device_id` adalah relasi ke `wt.device` dengan label UI `By Device`.
  - `initial_device_role`, `initial_device_employee_id`, dan `initial_device_employee_barcode` mengikuti `initial_device_id` dan readonly.
  - Memakai chatter dan activity (`mail.thread`, `mail.activity.mixin`).

Service push:

- Endpoint cup lump memakai service root `wt.api.push.weighing.cup.lump.service`.
- Service root melakukan autentikasi device, pengecekan `push_enabled`, validasi root payload, update `last_seen`/`last_push`, dan membentuk response.
- Business processor cup lump berada di `wt.cup.lump.service`.
- `wt.cup.lump.service` melakukan validasi item, idempotency, mapping payload ke `wt.weighing.cup.lump`, snapshot, dan pengecekan data problem.
- Service ini juga dipakai oleh action `Recheck Data Problem` dari model Odoo dan tidak mengurus endpoint HTTP.
- Pemisahan ini menjaga cup lump tetap mandiri; product type lain nanti bisa dibuat dengan endpoint/service/model sendiri tanpa dipaksa mengikuti struktur cup lump.

Data problem:

- `state` pada weighing cup lump adalah `draft` dan `validated`.
- `has_data_problem` menandai konflik antara payload device, master Odoo saat ini, atau aturan khusus cup lump.
- Data push tetap diterima sebagai `draft` walaupun `has_data_problem = True`.
- Data manual otomatis menjalankan pengecekan data problem saat create.
- Save record draft, baik sumber API maupun manual, otomatis menjalankan recheck jika field pemicu berubah.
- Data tidak boleh divalidasi selama `has_data_problem = True`.
- Admin dapat memperbaiki master atau data draft, lalu menjalankan `Recheck Data Problem`.
- Tombol validate menjalankan validasi form/backend, menjalankan ulang `Recheck Data Problem`, lalu menolak validate jika masih ada problem.
- Tombol cancel validate mengembalikan data validated ke draft.
- Idempotency memakai kombinasi `device_id + product_type + local_id` dan hanya berlaku untuk `data_source = api`.
- Database memakai partial unique index khusus API sebagai pengaman request paralel.

Validasi form/backend:

- Field wajib sebelum validate: production date, weighing date, company, estate, division, weighing location, product, UoM, receipt rule, operator, clerk, foreman, dan tapper.
- `total_bag`, `production_weight`, dan `net_weight` wajib bernilai lebih dari 0 sebelum validate.
- `production_date` tidak boleh lebih besar dari tanggal pada `weighing_date`.
- Jika `initial_weighing_date` terisi, maka `initial_weight` wajib terisi.
- Untuk input manual, `initial_device_id` juga wajib. Untuk API, initial device yang kosong/tidak ditemukan menjadi `missing_master` dan tidak menggagalkan penerimaan push.
- Jika `initial_is_manual_weighing` tercentang, maka `initial_manual_weighing_reason` wajib terisi.
- Validasi di atas tetap berada pada `@api.constrains` dan juga dipanggil saat action validate.

Kode data problem aktif:

| Code | Penjelasan |
| --- | --- |
| `none` | Tidak ditemukan masalah. Record dapat divalidasi jika field wajib lengkap. |
| `company_mismatch` | Company payload berbeda dari company device, atau division bukan milik company penimbangan. |
| `estate_mismatch` | Estate bukan milik company atau berbeda dari estate yang terikat pada weighing location. |
| `operator_mismatch` | Operator payload berbeda dari operator device, atau operator weighing location berbeda dari operator device. |
| `weighing_location_mismatch` | Weighing location tidak berada pada company penimbangan. |
| `division_not_allowed` | Division tidak termasuk `allowed_division_ids` weighing location. |
| `receipt_rule_mismatch` | Receipt rule tidak sesuai company, weighing location, division, atau product. |
| `product_mapping_mismatch` | Product belum dikonfigurasi sebagai `cup_lump` melalui `wt.product` untuk company. |
| `clerk_mismatch` | Clerk employee berbeda dari `division.clerk_id`. |
| `foreman_mismatch` | Foreman employee tidak memiliki assignment `wt.foreman` pada division, foreman ID berbeda division, atau employee payload tidak sesuai master foreman. |
| `tapper_mismatch` | Tapper tidak terdaftar, berada pada division lain, tidak berada di bawah foreman yang dipilih, atau employee payload tidak sesuai master tapper. |
| `weight_formula_mismatch` | `production_weight` tidak sama dengan `slab_weight + reject_weight + net_weight`. |
| `initial_weighing_date_mismatch` | Tanggal initial weighing berbeda dari production date. Perbandingan memakai timezone context Odoo. |
| `initial_weight_mismatch` | Untuk cross-day weighing, `production_weight` tidak sama dengan `initial_weight - shrinkage_tolerance_weight`. |
| `shrinkage_tolerance_mismatch` | `shrinkage_tolerance_weight` tidak sama dengan `initial_weight * shrinkage_tolerance_percentage / 100`. |
| `missing_master` | Master payload tidak ditemukan. Berlaku untuk estate, weighing location, division, product, receipt rule, foreman, tapper, atau initial device. Juga dipakai jika initial weighing date diisi tetapi device awal tidak dikirim. |
| `multiple_problem` | Lebih dari satu jenis problem ditemukan. Rincian lengkap tersimpan pada `data_problem_note`. |

Catatan aturan:

- `master_synced_at` tetap disimpan dan divalidasi formatnya, tetapi tidak menjadi data problem.
- Rule `production_weight = initial_weight` untuk penimbangan pada production date yang sama sudah dihapus.
- `data_problem_note` disimpan sebagai audit, sedangkan `data_problem_note_display` menerjemahkan note sesuai bahasa user saat form dibuka.

Prinsip mapping push:

- Aplikasi mengirim raw data penimbangan, bukan struktur final dokumen Odoo.
- Odoo mengambil `company_id` resmi dari assignment device.
- `operator` resmi untuk push adalah `device.employee_id`; payload operator tetap dicek sebagai data problem bila berbeda.
- Odoo memvalidasi bahwa `weighing_location_id` memang dipegang oleh operator device.
- Odoo memvalidasi bahwa `estate_id` sesuai company dan sesuai estate pada weighing location.
- Odoo memvalidasi bahwa `division_id` termasuk `allowed_division_ids` pada weighing location.
- Odoo memvalidasi receipt rule sesuai kombinasi company, weighing location, division, dan product.
- Initial weighing device memakai `initial_weighing.device_id` untuk mencari `wt.device`; role, device owner, dan badge number mengikuti record device di Odoo, bukan payload bebas.

Payload push v1 aktif:

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
      "company": {
        "id": 1,
        "name": "PT. Perkebunan Nusantara III"
      },
      "estate": {
        "id": 5,
        "code": "EST-A",
        "name": "Estate A"
      },
      "weighing_location": {
        "id": 1,
        "code": "WB-01",
        "name": "Gudang Induk 01"
      },
      "division": {
        "id": 10,
        "code": "DIV-A",
        "name": "Afdeling A"
      },
      "operator": {
        "employee_id": 101,
        "name": "Budi Operator",
        "barcode": "EMP-101"
      },
      "clerk": {
        "employee_id": 201,
        "name": "Sari Kerani",
        "barcode": "EMP-201"
      },
      "foreman": {
        "id": 31,
        "employee_id": 301,
        "name": "Andi Mandor",
        "barcode": "EMP-301"
      },
      "tapper": {
        "id": 88,
        "employee_id": 401,
        "name": "Joko Tapper",
        "barcode": "EMP-401"
      },
      "product": {
        "id": 25,
        "name": "Rubber Cup Lump",
        "uom": {
          "id": 1,
          "name": "kg"
        }
      },
      "receipt_rule": {
        "id": 7,
        "company_id": 1,
        "weighing_location_id": 1,
        "division_id": 10,
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
      "note": null,
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

Snapshot push:

- Karena device bisa bekerja offline, master Odoo bisa berubah sebelum data sempat dipush.
- Payload membawa object nested sebagai versi master yang diketahui aplikasi saat penimbangan.
- Odoo tetap membuat snapshot sendiri saat data diterima.
- Snapshot dari device tidak menjadi sumber otoritatif untuk validasi, tetapi dipakai untuk audit dan review.
- Jika master terbaru berbeda dari snapshot device, data tidak otomatis dibuang.
- Data bisa masuk sebagai draft dengan penanda `has_data_problem` sesuai tingkat konflik.
- Contoh konflik ringan: nama master berubah tetapi ID dan relasi masih valid.
- Contoh konflik berat: division sudah tidak allowed pada weighing location, receipt rule tidak valid, product mapping berubah, atau assignment clerk/foreman/tapper berubah.

Idempotency push:

- `batch_local_id` mengidentifikasi satu sesi push dari device.
- `local_id` wajib untuk setiap item API.
- Aturan idempotency API: `device_id + product_type + local_id`.
- Partial unique index database hanya berlaku ketika `data_source = api`.
- Data manual tidak mengikuti idempotency API dan field identitas aplikasi dibiarkan null.
- Retry dari device tidak boleh membuat data timbang double.
- Response push mengembalikan summary dan daftar item response.
- Summary response membawa `received`, `created`, `duplicates`, `with_data_problem`, dan `weighing_cup_lump_ids`.
- Item response membawa `local_id`, `status` (`created` atau `duplicate`), `has_data_problem`, `data_problem_code`, dan `weighing_cup_lump_id`.

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
- `Weather` -> `Cuaca`
- `Weather Data` -> `Data Cuaca`
- `Description` -> `Deskripsi`
- `Date` -> `Tanggal`
- `Employee Role` / `Employee Roles` -> `Role Karyawan`
- `Product` -> `Produk`
- `Product Type` -> `Tipe Produk`
- `Shrinkage Tolerance` / `Shrinkage Tolerances` -> `Toleransi Penyusutan`
- `Shrinkage Tolerance (%)` -> `Toleransi Penyusutan (%)`
- `Receipt Rule` -> `Aturan Penerimaan`
- `Location` -> `Lokasi`
- `Operation Type` -> `Tipe Operasi`
- `Job Position` -> `Jabatan`
- `Division` / `Divisions` -> `Divisi`
- `Weighing Location` / `Weighing Locations` -> `Lokasi Timbang`
- `Warehouse` -> `Gudang`
- `Clerk` -> `Kerani`
- `Foreman` / `Foremen` -> `Mandor`
- `Operator` -> `Operator`
- `Tapper` / `Tappers` -> `Tapper`
- `Device` -> `Device`
- `API` -> `API`
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
