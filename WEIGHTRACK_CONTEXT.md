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

Scope yang belum aktif:

- API push data.
- Sinkronisasi data timbang operasional.
- Push data timbang operasional.

Custom API yang aktif saat ini:

```text
POST /weightrack/api/v1/device/activate
POST /weightrack/api/v1/pull/master
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

Transient model:

- `wt.device.state.reason.wizard`

Abstract service model:

- `wt.api.device.service`
- `wt.api.pull.master.service`
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

Saat ini record API dipakai oleh activation device dan pull master. Push belum diekspos, tetapi helper security untuk mengecek `push_enabled` sudah disiapkan.

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
```

Handler:

```text
controllers/api/api_handler.py
```

Services:

```text
services/api_device_service.py
services/api_pull_master_service.py
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

## Future Push

Push belum diekspos.

Konsep yang sudah disiapkan:

- Request push membawa `device_id` dan `token`.
- Odoo memvalidasi kombinasi `device_id` dan `token` melalui `api_security_service.authenticate_device`.
- Device harus berstatus `active`.
- Role device yang boleh push data penimbangan hanya `operator`.
- `wt.api.push_enabled` harus aktif untuk company device.
- Setelah valid, Odoo memakai company, employee, dan role dari assignment device.
- Eksekusi tulis data bisnis diarahkan ke internal bot user agar auditable.
- Push akan dibuat hati-hati agar tidak melanggar user license; aktivitas database diarahkan ke bot user internal yang memang dikonfigurasi.
- Semua request push nanti tetap masuk ke `wt.api.request.log`.

Rancangan push inbound weighing:

- Endpoint rencana:

```text
POST /weightrack/api/v1/push/inbound-weighing
```

- Push data penimbangan tidak langsung menjadi stock.
- Data push hanya membentuk data inbound dan detail penimbangan.
- Stock resmi baru terbentuk setelah administrator Odoo melakukan validasi secara sadar.
- Payload push dipisah berdasarkan `product_type` agar setiap tipe produk bisa memiliki format data penimbangan sendiri.
- Product type menjadi registry/dispatcher melalui `constants/product_types.py`.
- Untuk `lump`, constant mengarah ke model detail `wt.weighing.lump`.
- Jika nanti ada product type baru dengan format penimbangan berbeda, tambahkan product type di constant dan buat model detail penimbangannya sendiri.

Struktur data inbound rencana:

- `wt.inbound.weighing`
  - Header data inbound per division, hasil grouping otomatis oleh Odoo.
  - Jika satu push membawa 3 division, Odoo membentuk 3 inbound weighing.
  - Header tidak menyimpan foreman karena satu division bisa memiliki banyak foreman.
  - Header menjadi acuan pembuatan receipt saat validasi admin.
- `wt.inbound.weighing.product`
  - Line/agregasi product per inbound weighing.
  - Menyimpan `product_type`, product, receipt rule, total bag, dan `inbound_stock`.
  - Tidak menyimpan field berat khusus seperti reject, slab, atau net weight.
  - `inbound_stock` adalah agregasi generic yang dipakai sebagai quantity receipt.
  - Untuk lump, `inbound_stock` dihitung dari total `net_weight` berdasarkan `ProductType.STOCK_QUANTITY_FIELD`.
  - Line ini menjadi acuan pembuatan/pencarian lot berdasarkan company, production date, division, dan product.
- `wt.weighing.lump`
  - Detail penimbangan untuk product type `lump`.
  - Menyimpan raw data penimbangan lump, termasuk field berat khusus lump.
  - Initial weighing/penimbangan lapangan awal rencananya disatukan di detail lump.

Prinsip mapping push:

- Aplikasi mengirim raw data penimbangan, bukan struktur final dokumen Odoo.
- Odoo membentuk `wt.inbound.weighing` dan `wt.inbound.weighing.product` otomatis saat menerima payload.
- Odoo mengambil `company_id` dan `operator_id` dari assignment device.
- `operator` resmi untuk push adalah `device.employee_id`, bukan data operator yang dikirim payload.
- Odoo memvalidasi bahwa `weighing_location_id` memang dipegang oleh operator device.
- Odoo memvalidasi bahwa `division_id` termasuk `allowed_division_ids` pada weighing location.
- Odoo memvalidasi receipt rule sesuai kombinasi weighing location, division, dan product.
- Odoo menghitung ulang total bag dan `inbound_stock` dari detail, tidak mempercayai agregasi dari device sebagai nilai final.

Rancangan payload push v1:

```json
{
  "device_id": "OPR-DEVICE-001",
  "token": "device-token",
  "app_version": "1.0.0",
  "batch_local_id": "batch-20260612-001",
  "master_synced_at": "2026-06-12 06:00:00",
  "sent_at": "2026-06-12 08:30:00",
  "inbounds": {
    "lump": [
      {
        "local_id": "lump-001",
        "production_date": "2026-06-12",
        "weighing_date": "2026-06-12 07:45:00",
        "weighing_location_id": 1,
        "division_id": 10,
        "product_id": 25,
        "receipt_rule_id": 7,
        "tapper_id": 88,
        "foreman_id": 31,
        "snapshot": {
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
            "name": "Weighbridge 1"
          },
          "division": {
            "id": 10,
            "code": "DIV-A",
            "name": "Division A"
          },
          "operator": {
            "employee_id": 101,
            "name": "John Doe",
            "barcode": "EMP-101"
          },
          "clerk": {
            "employee_id": 201,
            "name": "Jane Smith",
            "barcode": "EMP-201"
          },
          "foreman": {
            "id": 31,
            "employee_id": 301,
            "name": "Bob Johnson",
            "barcode": "EMP-031"
          },
          "tapper": {
            "id": 88,
            "employee_id": 401,
            "name": "Sam Tapper",
            "barcode": "EMP-401"
          },
          "product": {
            "id": 25,
            "name": "Rubber Lump",
            "uom": {
              "id": 1,
              "name": "kg"
            }
          },
          "receipt_rule": {
            "id": 7,
            "warehouse_id": 2,
            "warehouse_name": "Main Warehouse",
            "location_id": 15,
            "location_name": "WH/Stock",
            "operation_type_id": 4,
            "operation_type_name": "Receipts"
          }
        },
        "total_bag": 12,
        "production_weight": 900.0,
        "reject_weight": 20.0,
        "slab_weight": 15.0,
        "net_weight": 865.0,
        "shrinkage_tolerance_percentage": 5.0,
        "shrinkage_tolerance_weight": 35.0,
        "is_manual_weighing": false,
        "manual_weighing_reason": null,
        "note": null,
        "initial_weighing": {
          "weighing_date": "2026-06-12 07:30:00",
          "device_id": "FIELD-SCALE-002",
          "weight": 880.0,
          "is_manual_weighing": true,
          "manual_weighing_reason": "Scale device malfunction",
          "note": "Initial weight taken manually from operator note"
        }
      }
    ]
  }
}
```

Snapshot push:

- Karena device bisa bekerja offline, master Odoo bisa berubah sebelum data sempat dipush.
- Payload membawa `snapshot` sebagai versi master yang diketahui aplikasi saat penimbangan.
- Odoo tetap membuat snapshot sendiri saat data diterima.
- Snapshot dari device tidak menjadi sumber otoritatif untuk validasi, tetapi dipakai untuk audit dan review.
- Jika master terbaru berbeda dari snapshot device, data tidak otomatis dibuang.
- Data bisa masuk dengan status review/blocking sesuai tingkat konflik.
- Contoh konflik ringan: nama master berubah tetapi ID dan relasi masih valid.
- Contoh konflik berat: division sudah tidak allowed pada weighing location, receipt rule tidak valid, atau product mapping berubah.

Idempotency push:

- `batch_local_id` mengidentifikasi satu sesi push dari device.
- `local_id` pada tiap detail penimbangan wajib unik minimal per device dan product type.
- Aturan idempotency rencana: `device_id + product_type + local_id`.
- Retry dari device tidak boleh membuat data timbang double.
- Response push nanti perlu mengembalikan status per item: accepted, duplicate, needs_review, blocked, atau error.

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
