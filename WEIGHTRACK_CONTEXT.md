# WeighTrack Development Context

Dokumen ini adalah konteks kerja ringkas untuk melanjutkan pengembangan module WeighTrack.

## Project

WeighTrack adalah custom module Odoo 19 untuk aplikasi operasional penimbangan estate.

Lokasi repo lokal aktif:

```text
D:/Project/Odoo Addons/weightrack
```

Catatan kerja: repo lokal ini menjadi sumber kerja utama. Repo SSHFS/server hanya disentuh jika diminta eksplisit.

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
- API push weighing untuk data timbang weighing dari aplikasi offline.
- Production Receipt Weighing untuk menggabungkan data timbang per production date, division, product, operation type, dan receiving location sampai validasi dokumen.
- Pembuatan Inventory Receipt/stock picking resmi dari Production Receipt saat validated.
- Delivery Order/Pengiriman untuk mengatur stock keluar, transfer internal antar gudang, dan pengiriman final ke customer.
- Flow transit pengiriman membuat Lot Transit saat rute bertujuan transit divalidasi.
- Stock Opname untuk pemeriksaan stok per lot dan penyesuaian selisih stok.

Scope yang belum aktif:

- Push data timbang selain weighing.

Custom API yang aktif saat ini:

```text
POST /weightrack/api/v1/device/activate
POST /weightrack/api/v1/pull/master
POST /weightrack/api/v1/push/weighing
POST /weightrack/api/v1/pull/stock-opname
POST /weightrack/api/v1/push/stock-opname
POST /weightrack/api/v1/pull/delivery
POST /weightrack/api/v1/push/delivery
```

## Important Conventions

- Semua model WeighTrack memakai prefix teknis `wt.`.
- Nama teknis model dan field memakai bahasa Inggris.
- Label UI bahasa Indonesia dikelola lewat `i18n/id_ID.po`.
- Master operasional utama memakai chatter:
  - `_inherit = ["mail.thread", "mail.activity.mixin"]`
  - field penting memakai `tracking=True`
  - form view memakai `<chatter/>`
- Master dan konfigurasi operasional yang boleh diarsipkan memakai field standar `active`.
  - Model yang aktif memakai archive: `wt.estate`, `wt.weather`, `wt.employee.role`, `wt.product`, `wt.shrinkage.tolerance`, `wt.receipt.rule`, `wt.division`, `wt.weighing.location`, `wt.foreman`, dan `wt.tapper`.
  - Model transaksi, log, device assignment, dan konfigurasi API tidak memakai archive untuk saat ini.
  - Unique business key pada model archive dibuat unik hanya untuk record aktif, sehingga record lama bisa diarsipkan lalu kombinasi pengganti dapat dibuat.
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
- `wt.weighing`
- `wt.production.receipt`
- `wt.production.receipt.line`
- `wt.stock.opname`
- `wt.stock.opname.line`
- `wt.stock.opname.difference.reason`
- `wt.stock.opname.line.allocation`
- `wt.delivery`
- `wt.delivery.route`
- `wt.delivery.do.line`
- `wt.delivery.do.line.lot`
- `wt.delivery.line.allocation`

Transient model:

- `wt.device.state.reason.wizard`
- `wt.production.receipt.cancel.wizard`
- `wt.stock.opname.apply.wizard`
- `wt.delivery.return.wizard`

Abstract service model:

- `wt.api.device.service`
- `wt.api.pull.master.service`
- `wt.api.push.weighing.service`
- `wt.weighing.service`
- `wt.api.security.service`
- `wt.api.response.service`
- `wt.api.stock.opname.service`
- `wt.api.delivery.service`

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
|   |-- Weighing
|   |-- Production Receipt
|   |-- Stock Opname
|   `-- Pengiriman
|-- Device
`-- Configuration
    |-- API
    |-- API Request Logs
    |-- Employee Roles
    |-- Product
    |-- Shrinkage Tolerance
    |-- Receipt Rule
    |-- Alasan Selisih
    `-- Rute Pengiriman
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
- Kode `Division` wajib unik per company untuk record aktif. Ini menjaga format lot `LOT/kode_divisi/YYYYMMDD/NNN` tidak bentrok antar estate dalam company yang sama.
- Lot produksi dari Production Receipt memakai format `LOT/kode_divisi/YYYYMMDD/NNN`.
- Lot transit dari rute pengiriman transit memakai format `TR/kode_gudang_tujuan/YYYYMMDD/NNN`.
- `stock.lot` di-extend dengan metadata WeighTrack:
  - `wt_lot_type`: `production`, `transit`, atau `warehouse_stock`;
  - `wt_transit_state`: status lot transit;
  - `division_id`;
  - `production_date`;
  - `wt_receiving_location_id`;
  - `wt_source_delivery_id`;
  - `wt_source_picking_id`;
  - `wt_transit_date`.
- Lot genealogy khusus tidak dipakai. Trace lot transit cukup melalui dokumen Delivery, `generated_transit_lot_id` pada Rencana DO, stock move line, dan metadata `stock.lot`.
- Form Foreman memakai add line natural Odoo pada `tapper_ids`. Jika `foreman_id` terisi, `division_id` Tapper otomatis mengikuti division Foreman.
- Pengaturan divisi yang boleh menimbang hanya dilakukan dari `Weighing Location` melalui `allowed_division_ids`.
- `Division` tidak perlu menampilkan atau mengatur relasi balik ke `Weighing Location`.
- `wt.product` memetakan satu produk timbang aktif per company ke produk Odoo `product.product`.
- Konsep `product_type` sudah dilepas; module saat ini hanya mendukung satu product aktif per company untuk alur weighing.
- `wt.shrinkage.tolerance` menentukan batas toleransi penyusutan produksi per company dan division.
- Batas toleransi penyusutan dipakai saat hari produksi tidak sama dengan hari penimbangan di gudang induk.
- Kombinasi Company dan Division pada `wt.shrinkage.tolerance` tidak boleh berulang untuk record aktif.
- Division pada `wt.shrinkage.tolerance` wajib berasal dari company yang sama.
- `wt.receipt.rule` menentukan Warehouse, Receiving Location, dan Operation Type untuk kombinasi Weighing Location dan Division tertentu.
- `wt.receipt.rule` otomatis membawa Estate dari Weighing Location; pemilihan Warehouse dibatasi pada company dan estate yang sama.
- Division pada `wt.receipt.rule` wajib termasuk `allowed_division_ids` pada Weighing Location.
- Kombinasi aktif Weighing Location dan Division pada `wt.receipt.rule` tidak boleh berulang.
- Pengaturan Warehouse tidak berada di Weighing Location; Warehouse, Location, dan Operation Type ditentukan pada Receipt Rule.
- Receiving Location di Receipt Rule adalah `location_id` atau stock location internal, bukan warehouse. Warehouse dipakai sebagai konteks/filter operation type dan lokasi penerimaan wajib berada di bawah view location warehouse tersebut.
- `stock.warehouse` di-extend dengan field Estate untuk memastikan warehouse tujuan stok berada pada estate yang benar.
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

Saat ini record API dipakai oleh activation device, pull master, dan push weighing. `push_enabled` mengatur apakah endpoint push boleh dipakai oleh device company tersebut.

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
services/api_push_weighing_service.py
services/weighing_service.py
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
- `scope` membawa `role`, `company_id`, `estate_ids`, `division_ids`, `weighing_location_ids`, `receipt_rule_ids`, `product_ids`, `uom_ids`, `shrinkage_tolerance_ids`, `employee_ids`, `foreman_ids`, dan `tapper_ids`.
- `masters` berisi company, roles, employees, estate, division, weighing location, receipt rule, product, UoM, shrinkage tolerance, foreman, dan tapper.
- Pull master hanya mengirim master/config yang masih aktif. Record yang sudah diarsipkan tidak masuk scope dan tidak dikirim ke aplikasi offline pada pull berikutnya.
- `masters.roles` hanya membawa role milik device yang sedang pull.
- `masters.products` hanya membawa product Odoo yang berasal dari mapping aktif `wt.product` untuk company dalam scope.
- `masters.shrinkage_tolerances` hanya membawa toleransi yang sesuai dengan division dalam scope device.
- Pull master tidak mengirim warehouse, location, dan operation type; nilai tersebut tetap menjadi konfigurasi backend pada Receipt Rule.
- Product payload pada pull master membawa `id`, `name`, `company_id`, dan `uom_id`; `default_code` dan product type tidak dikirim.
- `pull_type` tidak dipakai.
- Company dan employees berada di `masters`, bukan root data.
- Employee dipusatkan di `masters.employees`; payload foreman dan tapper hanya membawa relasi `employee_id`.
- Device berada di `meta.device`.

Scope role pull:

- `foreman`: foreman record milik employee device, division foreman, tapper di bawah foreman tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait.
- `clerk`: division yang dipegang clerk, foreman di division tersebut, tapper di division tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait.
- `operator`: weighing location yang dipegang operator, allowed division dari location, receipt rule, product, UoM, shrinkage tolerance, clerk division, foreman, tapper, dan estate.

## Push Weighing

Push weighing sudah diekspos melalui:

```text
POST /weightrack/api/v1/push/weighing
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
- Push saat ini hanya menerima alur `weighing`; payload tidak lagi memakai `product_type`.
- Produk Odoo resmi diambil dari satu mapping aktif `wt.product` milik company device. Jika masih ada mapping archived untuk company yang sama, mapping aktif tetap diprioritaskan saat push/recheck.
- Data push tidak langsung menjadi stock.
- Data push saat ini langsung membentuk detail `wt.weighing`.
- Model inbound/header belum aktif kembali; rencana pembentukan inbound/receipt akan dibuat terpisah setelah desain per product matang.

Struktur runtime saat ini:

- `wt.weighing`
  - Detail penimbangan untuk alur weighing.
  - Number dibuat sekali saat record dibuat melalui `ir.sequence` dengan code `wt.weighing`.
  - Format default sequence adalah `WG/YYYYMMDD/NNN` dan dapat diatur administrator melalui menu Technical Odoo.
  - Tanggal pada nomor memakai `production_date`; perubahan tanggal setelah create tidak mengubah nomor yang sudah tersimpan.
  - Menyimpan raw data penimbangan weighing, termasuk field berat khusus weighing.
  - Menyimpan `data_source` dengan nilai `api` atau `manual`.
  - Data manual baru menyimpan `local_id`, `device_id`, `device_record_id`, dan `batch_local_id` sebagai null.
  - Data API mewajibkan `local_id`, `device_id`, dan `device_record_id`.
  - Menyimpan employee operator, clerk, foreman, dan tapper langsung pada detail timbang.
  - Nama dan badge number employee dikunci mengikuti `hr.employee`, bukan mengikuti struktur assignment lama.
  - Field `foreman_id` dan `tapper_id` tetap disimpan untuk kebutuhan validasi assignment, tetapi yang ditampilkan ke user adalah employee.
  - Initial weighing/penimbangan lapangan awal disimpan di detail weighing.
  - `initial_device_id` adalah relasi ke `wt.device` dengan label UI `By Device`.
  - `initial_device_role`, `initial_device_employee_id`, dan `initial_device_employee_barcode` mengikuti `initial_device_id` dan readonly.
  - Memakai chatter dan activity (`mail.thread`, `mail.activity.mixin`).

Service push:

- Endpoint weighing memakai service root `wt.api.push.weighing.service`.
- Service root melakukan autentikasi device, pengecekan `push_enabled`, validasi root payload, update `last_seen`/`last_push`, dan membentuk response.
- Business processor weighing berada di `wt.weighing.service`.
- `wt.weighing.service` melakukan validasi item, idempotency, mapping payload ke `wt.weighing`, snapshot, dan pengecekan data problem.
- Service ini juga dipakai oleh action `Recheck Data Problem` dari model Odoo dan tidak mengurus endpoint HTTP.
- Pemisahan ini menjaga weighing tetap mandiri; product lain nanti bisa dibuat dengan endpoint/service/model sendiri tanpa dipaksa mengikuti struktur weighing.

Status dan data problem:

- `state` pada weighing menjadi satu-satunya status flow receipt:
  - `not_receipted`: belum masuk Production Receipt.
  - `in_production_receipt`: sudah masuk Production Receipt tetapi receipt belum validated.
  - `receipt_validated`: Production Receipt sudah validated dan data timbang terkunci.
  - `receipt_cancelled`: pernah masuk Production Receipt yang kemudian dibatalkan/reversed.
- `has_data_problem` menandai konflik antara payload device, master Odoo saat ini, atau aturan khusus weighing.
- Data push tetap diterima sebagai `not_receipted` walaupun `has_data_problem = True`.
- Data manual otomatis menjalankan pengecekan data problem saat create.
- Save record draft, baik sumber API maupun manual, otomatis menjalankan recheck jika field pemicu berubah.
  - Data timbang tidak lagi divalidasi langsung dari form Weighing; validasi resmi dilakukan dari Production Receipt.
  - Admin dapat memperbaiki master atau data draft, lalu menjalankan `Recheck Data Problem` selama Production Receipt belum validated.
  - Setelah data timbang masuk Production Receipt yang sudah validated, data menjadi terkunci dan recheck problem ditolak.
- Idempotency memakai kombinasi `device_id + local_id` dan hanya berlaku untuk `data_source = api`.
- Database memakai partial unique index khusus API sebagai pengaman request paralel.

Validasi form/backend:

- Field wajib sebelum validate Production Receipt: production date, weighing date, company, estate, division, weighing location, product, UoM, receipt rule, operator, clerk, foreman, dan tapper pada setiap line timbang.
- `total_bag`, `production_weight`, dan `net_weight` wajib bernilai lebih dari 0 sebelum Production Receipt bisa validated.
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
| `receipt_rule_mismatch` | Receipt rule tidak sesuai company, weighing location, atau division. |
| `product_mapping_mismatch` | Product belum dikonfigurasi sebagai `weighing` melalui `wt.product` untuk company. |
| `clerk_mismatch` | Clerk employee berbeda dari `division.clerk_id`. |
| `foreman_mismatch` | Foreman employee tidak memiliki assignment `wt.foreman` pada division, foreman ID berbeda division, atau employee payload tidak sesuai master foreman. |
| `tapper_mismatch` | Tapper tidak terdaftar, berada pada division lain, tidak berada di bawah foreman yang dipilih, atau employee payload tidak sesuai master tapper. |
| `weight_formula_mismatch` | `production_weight` tidak sama dengan `slab_weight + reject_weight + net_weight`. |
| `initial_weighing_date_mismatch` | Tanggal initial weighing berbeda dari production date. Perbandingan memakai timezone context Odoo. |
| `initial_weight_mismatch` | Untuk cross-day weighing, `production_weight` tidak sama dengan `initial_weight - shrinkage_tolerance_weight`. |
| `shrinkage_tolerance_mismatch` | `shrinkage_tolerance_weight` tidak sama dengan `initial_weight * shrinkage_tolerance_percentage / 100`. |
| `inactive_master` | Master payload masih ditemukan di Odoo, tetapi record tersebut sudah diarsipkan/nonaktif. Berlaku untuk estate, weighing location, division, product mapping, receipt rule, foreman, atau tapper. |
| `missing_master` | Master payload tidak ditemukan. Berlaku untuk estate, weighing location, division, product, receipt rule, foreman, tapper, atau initial device. Juga dipakai jika initial weighing date diisi tetapi device awal tidak dikirim. |
| `multiple_problem` | Lebih dari satu jenis problem ditemukan. Rincian lengkap tersimpan pada `data_problem_note`. |

Catatan aturan:

- `master_synced_at` tetap disimpan dan divalidasi formatnya, tetapi tidak menjadi data problem.
- Rule `production_weight = initial_weight` untuk penimbangan pada production date yang sama sudah dihapus.
- `data_problem_note_en` menyimpan catatan masalah versi Inggris untuk audit/debug.
- `data_problem_note_idn` menyimpan catatan masalah versi Indonesia.
- `data_problem_note` menjadi field display sesuai preferensi bahasa user; user `id_ID` melihat `data_problem_note_idn`, sedangkan bahasa lain melihat `data_problem_note_en`.

Prinsip mapping push:

- Aplikasi mengirim raw data penimbangan, bukan struktur final dokumen Odoo.
- Odoo mengambil `company_id` resmi dari assignment device.
- `operator` resmi untuk push adalah `device.employee_id`; payload operator tetap dicek sebagai data problem bila berbeda.
- Odoo memvalidasi bahwa `weighing_location_id` memang dipegang oleh operator device.
- Odoo memvalidasi bahwa `estate_id` sesuai company dan sesuai estate pada weighing location.
- Odoo memvalidasi bahwa `division_id` termasuk `allowed_division_ids` pada weighing location.
- Odoo memvalidasi receipt rule sesuai kombinasi company, weighing location, dan division.
- Jika payload membawa Receipt Rule lama yang hilang, archived, atau tidak sesuai scope, Odoo bisa fallback ke Receipt Rule aktif berdasarkan company, weighing location, dan division agar `wt.weighing.receipt_rule_id` memakai konfigurasi sekarang.
- Product pada data timbang diprioritaskan dari mapping aktif `wt.product` berdasarkan company. Product dari payload dipakai sebagai snapshot/audit dan tidak menjadi sumber utama product transaksi.
- Receipt Rule dari payload lama tetap dibaca dengan `active_test=False` untuk audit dan tetap dapat menandai `missing_master`, `inactive_master`, atau `receipt_rule_mismatch`.
- Odoo tetap mencari referensi master dengan `active_test=False` saat push, sehingga payload lama yang menunjuk record archived tidak dianggap hilang, tetapi ditandai `inactive_master`.
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
  "items": [
    {
      "local_id": "weighing-20260614-0001",
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
        "name": "Rubber Weighing",
        "uom": {
          "id": 1,
          "name": "kg"
        }
      },
      "receipt_rule": {
        "id": 7,
        "company_id": 1,
        "weighing_location_id": 1,
        "division_id": 10
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
- Aturan idempotency API: `device_id + local_id`.
- Partial unique index database hanya berlaku ketika `data_source = api`.
- Data manual tidak mengikuti idempotency API dan field identitas aplikasi dibiarkan null.
- Retry dari device tidak boleh membuat data timbang double.
- Response push mengembalikan summary dan daftar item response.
- Summary response membawa `received`, `created`, `duplicates`, `with_data_problem`, dan `weighing_ids`.
- Item response membawa `local_id`, `status` (`created` atau `duplicate`), `has_data_problem`, `data_problem_code`, dan `weighing_id`.

## Production Receipt

Production Receipt adalah dokumen penerimaan produksi untuk menggabungkan data timbang Weighing dan menjadi pintu pembuatan Inventory Receipt resmi.

Model aktif:

- `wt.production.receipt`
- `wt.production.receipt.line`

Konsep:

- Production Receipt menggabungkan data penimbangan Weighing berdasarkan company, production date, division, product, operation type, dan receiving location.
- Scope awal hanya untuk satu product aktif yang dipetakan di `wt.product` untuk company.
- Product pada header otomatis diisi dari mapping aktif `wt.product` ketika company dipilih dan tidak diedit manual.
- Operation Type dipilih pada header. Warehouse otomatis mengikuti Operation Type dan readonly.
- Receiving Location dipilih pada header setelah Division dan Operation Type dipilih. Pilihan lokasi dibatasi dari Receipt Rule aktif yang sesuai division dan operation type.
- Data weighing menjadi sumber detail/line Production Receipt.
- Production Receipt menjadi gate validasi resmi; validate pada data penimbangan Weighing ditiadakan dari UI dan ditolak di backend.
- Data penimbangan tetap menyimpan hasil pengecekan `has_data_problem`, `data_problem_code`, dan `data_problem_note`.
- Number Production Receipt dibuat sekali saat record dibuat melalui `ir.sequence` dengan code `wt.production.receipt`.
- Format default sequence adalah `PR/YYYYMMDD/NNN` dan tanggal pada nomor memakai `production_date`.
- Production Receipt memiliki `received_date` sebagai tanggal diterima, wajib diisi, dan tidak boleh lebih awal dari `production_date`.
- Production Receipt menyimpan `clerk_employee_id` sebagai snapshot employee clerk pada dokumen, bukan related langsung ke Division.
- Saat Division dipilih/diubah pada Production Receipt, Clerk otomatis diisi dari `division_id.clerk_id`.
- Clerk pada Production Receipt tidak dapat dipilih atau diubah manual oleh user; satu-satunya sumbernya adalah Division.
- Setelah dokumen tersimpan/validated, perubahan Clerk pada master Division tidak mengubah Clerk pada Production Receipt lama.
- Saat Production Receipt divalidasi, sistem membuat satu lot, satu Inventory Receipt, satu stock move, dan satu stock move line berdasarkan header Production Receipt.
- Inventory Receipt yang dibuat dari Production Receipt memakai `received_date` sebagai Scheduled Date dan Effective Date.

Flow process:

1. User membuat Production Receipt dengan memilih company, production date, received date, division, operation type, dan receiving location.
2. Sistem mengisi product aktif dari company, Clerk dari Division, dan Warehouse dari Operation Type.
3. User klik tombol `Process`.
4. Sistem mencari Receipt Rule aktif yang sesuai company, division, operation type, dan receiving location.
5. Sistem mengambil semua data `wt.weighing` Weighing yang sesuai company, division, production date, product, receipt rule aktif tersebut, dan belum masuk Production Receipt aktif lain.
6. Semua data timbang yang cocok masuk menjadi line, termasuk data yang masih memiliki data problem.
7. Sistem menghitung total bag dari `total_bag`.
8. Sistem menghitung total stock weight dari `net_weight`.
9. Total pada Production Receipt bersifat total review selama dokumen belum validated.
10. Selama Production Receipt belum validated, line dapat dilepas; data timbang kembali ke `not_receipted` dan dapat diproses ulang oleh Production Receipt lain.

Status keterikatan data timbang:

- Data penimbangan perlu memiliki status keterikatan Production Receipt, misalnya:
  - `not_receipted`: belum masuk Production Receipt.
  - `in_production_receipt`: sudah masuk Production Receipt tetapi receipt belum validated.
  - `receipt_validated`: Production Receipt sudah validated dan data timbang terkunci.
  - `receipt_cancelled`: pernah masuk Production Receipt yang kemudian dibatalkan/reversed.
- Saat status `receipt_validated`, data timbang tidak boleh lagi terpengaruh perubahan master data setelah receipt validated.
- Saat status `receipt_validated`, tombol/action `Recheck Data Problem` pada data timbang ditiadakan atau ditolak di backend.
- Auto recheck data problem saat save tidak boleh berjalan lagi untuk data timbang yang sudah `receipt_validated`.
- Field penting data timbang harus dikunci setelah Production Receipt validated.

Flow lepas line sebelum validate:

1. User menghapus line pada tab `Weighing` di Production Receipt yang masih `draft` atau `processed`.
2. Sistem menghapus line Production Receipt.
3. Data timbang terkait dikembalikan ke `state = not_receipted` dan `production_receipt_id = False`.
4. Data timbang tersebut dapat masuk lagi saat `Process` Production Receipt lain.
5. Jika Production Receipt sudah `validated`, line tidak boleh dilepas; gunakan flow cancel Production Receipt.

Flow validate Production Receipt:

1. User klik tombol `Validate` pada Production Receipt.
2. Sistem menjalankan ulang recheck data problem untuk semua line yang belum locked.
3. Validate ditolak jika masih ada line dengan `has_data_problem = True`.
4. Validate ditolak jika line kosong, ada line double, atau line tidak sesuai company/division/production date/product/operation type/receiving location header.
5. Sistem menghitung ulang total bag dan total stock weight.
6. Production Receipt berubah menjadi `validated`.
7. Data timbang pada line berubah menjadi `receipt_validated` dan terkunci dari perubahan/recheck problem.
8. Sistem membuat satu Inventory Receipt berdasarkan Operation Type dan Receiving Location pada header.
9. Receipt Rule tetap dipakai untuk memastikan kombinasi weighing location, division, operation type, dan receiving location valid.
10. Receive From diisi dari `clerk_employee_id` pada Production Receipt. Jika employee clerk memiliki partner terkait, contact receipt juga diisi.
11. Sistem membuat satu lot otomatis dengan format `LOT/kode_divisi/YYYYMMDD/NNN`.
12. Inventory Receipt otomatis divalidasi sehingga stock masuk ke receiving location.

Flow cancel Production Receipt pada tahap saat ini:

- Return manual dari Inventory ditolak untuk Inventory Receipt dan Inventory Reversal yang berasal dari Production Receipt.
- Saat user klik `Cancel`, sistem membuka wizard alasan pembatalan dan alasan wajib diisi.
- Setelah alasan dikonfirmasi, sistem cek lot pada Inventory Receipt original.
- Cancel ditolak jika available stock lot di receiving location original tidak mencukupi untuk quantity reversal.
- Jika stock masih mencukupi, sistem membuat Inventory Reversal otomatis dengan lokasi terbalik, lot yang sama, dan quantity yang sama.
- Setelah Inventory Reversal berhasil divalidasi, Production Receipt menyimpan `cancel_reason`, menjadi `cancelled`, dan data timbang menjadi `receipt_cancelled`.

Catatan desain:

- Production Receipt adalah snapshot final produksi setelah validated.
- Clerk pada Production Receipt adalah snapshot employee. Tujuannya agar perubahan Clerk di master Division tidak mengubah dokumen Production Receipt lama.
- Production Receipt line menyimpan snapshot/related nilai penting seperti weighing reference, weighing location, operator, foreman, tapper, total bag, stock weight, data problem code/note, product, UoM, dan receipt rule.
- Stock resmi lahir saat Production Receipt validated melalui Inventory Receipt otomatis.
- Perubahan master data setelah Production Receipt validated tidak boleh mengubah status problem atau total receipt lama.
- Untuk audit, jangan lepas histori line lama saat receipt dibatalkan; gunakan status cancelled/reversed dan relasi reverse picking.

Inventory Receipt aktif:

- Validate Production Receipt membuat satu stock receipt berdasarkan header `operation_type_id`, `location_id`, dan `product_id`.
- Satu Production Receipt memakai satu lot yang tersimpan pada `lot_id`.
- Inventory Receipt yang dibuat tersimpan pada header `stock_picking_id`.
- Inventory Reversal yang dibuat dari cancel tersimpan pada header `reverse_picking_id`.
- Jika satu division bisa ditimbang di beberapa weighing location tetapi Receipt Rule aktifnya mengarah ke operation type dan receiving location yang sama, data tersebut bisa masuk ke satu Production Receipt dan satu lot.
- Jika receiving location atau operation type berbeda, sebaiknya dibuat Production Receipt berbeda agar lot dan stock movement tetap traceable.
- Sistem akan mengisi done quantity berdasarkan total stock weight header.
- Sistem akan validate stock picking sehingga stock bertambah di Inventory.
- Cancel setelah stock masuk dilakukan dari Production Receipt dan membuat reversal otomatis selama stock lot masih mencukupi di lokasi receipt original.

## Delivery / Pengiriman

Delivery adalah dokumen operasional untuk mengatur stock keluar dari gudang, transfer internal antar gudang, transit antar gudang, dan pengiriman final ke customer.

Model aktif:

- `wt.delivery`
- `wt.delivery.route`
- `wt.delivery.route.line`
- `wt.delivery.do.line`
- `wt.delivery.do.line.lot`
- `wt.delivery.line.allocation`
- `wt.delivery.return.wizard`

Konsep utama:

- Header `wt.delivery` menjadi tugas pengiriman.
- `wt.delivery.route` menyimpan master rute lengkap.
- `wt.delivery.route.line` menyimpan urutan rute dengan `route_type`: `transit` atau `outgoing`.
- Baris `wt.delivery.do.line` adalah Rencana DO per rute operasi.
- Rincian `wt.delivery.do.line.lot` adalah sumber tugas timbang DO dan kontrak lot yang dikirim ke aplikasi operator.
- Product pada Delivery dan Rencana DO mengikuti product aktif dari `wt.product`.
- Rencana DO tidak membuat `stock.picking` saat draft/confirmed/in progress.
- `stock.picking`, `stock.move`, dan `stock.move.line` resmi baru dibuat saat validasi Rencana DO.
- Selisih timbang diterapkan otomatis per Rencana DO saat Rencana DO divalidasi, bukan lewat tombol manual dari detail timbang.

### Delivery Lot Line vs Stock Move Line

Alur lama memakai `stock.move.line` sebagai detail timbang DO. Alur ini sudah dibersihkan.

Alur aktif sekarang:

```text
wt.delivery.do.line.lot = kontrak/tugas timbang WeighTrack
stock.move.line         = hasil eksekusi inventory resmi Odoo
```

Dampaknya:

- API pull/push Delivery memakai `delivery_lot_line_id`, bukan `move_line_id`.
- Status pull/timbang (`not_pulled`, `unweighed`, `weighed`) disimpan di `wt.delivery.do.line.lot`.
- Berat fisik aktual, waktu timbang, selisih, dan alokasi selisih disimpan di `wt.delivery.do.line.lot`.
- `stock.move.line` tetap dipakai Odoo untuk stock movement resmi, laporan stok, histori pergerakan, Production Receipt, Stock Opname, return, dan inventory normal.
- Penimbangan lapangan tidak lagi bergantung pada reservasi Odoo yang dapat berubah karena unreserve/reassign/validasi picking.

### Rute Pengiriman

- `route_type = transit` berarti rute menuju lokasi transit/holding internal.
- `route_type = outgoing` berarti rute keluar final ke customer.
- Rute transit wajib memakai Operation Type internal transfer.
- Rute outgoing wajib memakai Operation Type delivery/outgoing.
- Source Location pada route line dibatasi berdasarkan warehouse dari Operation Type.
- Saat Delivery memilih Route dan dikonfirmasi, sistem membuat baris Rencana DO dari route line.
- Baris Rencana DO tidak bisa ditambah manual dari form Delivery; struktur mengikuti master Route.
- Detail Rencana DO hanya bisa diatur saat header Delivery berstatus `confirmed` atau `in_progress`.

Status header Delivery:

- `draft`: dokumen awal, route belum dikunci.
- `confirmed`: route sudah dipilih dan baris Rencana DO terbentuk.
- `in_progress`: minimal ada pull Delivery pertama dari operator.
- `done`: rute outgoing/final sudah tervalidasi.
- `returned`: state terminal setelah return delivery.
- `cancelled`: dokumen dibatalkan.

Status proses Rencana DO:

- `preparation`: belum giliran validasi.
- `in_process`: giliran validasi sesuai sequence.
- `done`: Rencana DO sudah tervalidasi dan picking terkait selesai.

### Flow Pull/Push Delivery

- Operator pull tugas Delivery melalui custom API.
- Odoo mengirim line dari `wt.delivery.do.line.lot` yang sesuai operator/lokasi timbang dan belum memiliki `wt_physical_qty`.
- Saat berhasil dipull, Odoo menandai lot line `wt_is_pulled = True`.
- Aplikasi mengirim kembali hasil timbang memakai `delivery_lot_line_id`.
- Push Delivery wajib membawa `physical_qty` dan `weighed_at`.
- Jika `lot_id` atau `lot_name` dikirim, Odoo memvalidasi kecocokannya dengan lot pada `delivery_lot_line_id`.
- Line yang belum dipull, belum ditimbang, atau memiliki selisih belum dialokasikan tidak boleh tervalidasi.

### Flow Rute Transit

1. User membuat Delivery dan memilih master Route.
2. Saat confirm, sistem membuat Rencana DO sesuai sequence route.
3. User mengatur lot asal pada Rencana DO transit.
4. Operator pull dan push hasil timbang ke `wt.delivery.do.line.lot`.
5. Saat Rencana DO transit divalidasi, sistem membuat stock picking internal.
6. Sistem mengonsumsi lot asal dan membuat satu Lot Transit baru pada lokasi tujuan transit.
7. Lot Transit hasil rute tersebut disimpan pada `wt.delivery.do.line.generated_transit_lot_id`.
8. Rencana DO berikutnya yang mengambil stock dari lokasi transit otomatis menerima Lot Transit wajib dari rute sebelumnya.
9. Demand pada Rencana DO lanjutan minimal harus mencakup total Lot Transit wajib.
10. Lot Transit wajib tidak boleh dihapus dari Rencana DO lanjutan agar rantai pengiriman tidak meninggalkan celah.

Format Lot Transit:

```text
TR/kode_gudang_tujuan/YYYYMMDD/NNN
```

Catatan Lot Transit:

- `kode_gudang_tujuan` diambil dari warehouse yang menaungi lokasi tujuan transit.
- Jika kode warehouse tidak tersedia, nama lokasi tujuan dipakai sebagai fallback dan dibersihkan dari karakter `/`, `\`, dan spasi.
- Tanggal pada lot transit memakai tanggal saat validasi.
- Nomor urut 3 digit dihitung dari lot terakhir dengan prefix yang sama.
- Lot transit diberi `wt_lot_type = transit`.
- Lot transit menyimpan source Delivery, source Picking, receiving location, transit date, division jika seluruh lot asal berasal dari satu division, dan production date paling awal dari lot asal.

### Flow Rute Setelah Transit

- Rencana DO lanjutan yang mengambil stock dari lokasi transit wajib memiliki lot line aktif.
- Jika pada dokumen Delivery yang sama sudah ada Rencana DO transit yang menghasilkan Lot Transit ke lokasi transit tersebut, Rencana DO lanjutan wajib memakai Lot Transit tersebut.
- Rencana DO lanjutan boleh memiliki lot tambahan lain dari lokasi sumber, tetapi Lot Transit wajib tetap harus ada dan demand-nya tidak boleh kurang dari berat Lot Transit yang masuk.
- Saat tombol muat lot dari lokasi sumber dipakai, sistem memprioritaskan Lot Transit wajib terlebih dahulu, lalu baru FIFO dari lokasi sumber.

### Traceability

- Trace dari lot produksi ke lot transit tidak memakai model genealogy khusus.
- Trace dilakukan melalui:
  - Rencana DO transit;
  - field `generated_transit_lot_id`;
  - stock picking yang dibuat dari delivery;
  - stock move line yang mengonsumsi lot asal;
  - stock move line yang membuat lot transit;
  - metadata `stock.lot` pada lot transit.
- Sejarah pergerakan stock dari Stock Opname dan Pengiriman ditandai melalui origin/reference yang mengarah ke nomor dokumen WeighTrack terkait.

### Dokumen Delivery

Dokumen cetak Delivery saat ini dibuat per Rencana DO/line, bukan dari tombol header Delivery untuk Surat Jalan.

Dokumen per Rencana DO:

- Berita Acara Serah Terima Barang.
- Despatch Slip.
- Denah Penyegelan Truk.
- Surat Jalan.

Informasi dokumen berada pada Rencana DO dan bersifat optional:

- Ekspedisi: nama supir, nomor polisi, tare, tanggal serah terima.
- Surat Jalan: nomor surat jalan, tanggal surat jalan, nomor SO, nomor DO, nama penerima, alamat penerima.
- Despatch Slip: nomor despatch slip.

### Prinsip FIFO

- Saat muat lot pada Rencana DO, lot diurutkan berdasarkan `production_date` paling lama terlebih dahulu.
- Jika `production_date` kosong, lot diletakkan setelah lot yang memiliki tanggal produksi.
- Urutan berikutnya memakai `create_date`, nama lot, dan lokasi fisik.
- Stock Opname juga mengurutkan lot berdasarkan `production_date` agar pemeriksaan mengikuti umur produksi.
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
