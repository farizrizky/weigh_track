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
product
```

Menu utama:

```text
WeighTrack
├── Master Data
│   ├── Estates
│   ├── Weather
│   ├── Weather Data
│   ├── Divisions
│   ├── Weighing Locations
│   ├── Foremen
│   └── Tappers
├── Device
└── Configuration
    ├── API
    ├── API Request Logs
    ├── Employee Roles
    ├── Product
    ├── Shrinkage Tolerance
    └── Receipt Rule
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
- Endpoint push weighing sudah aktif dan langsung membuat `wt.weighing`.
- Master/config yang bisa diarsipkan memakai field standar `active`: Estate, Weather, Employee Role, Product, Shrinkage Tolerance, Receipt Rule, Division, Weighing Location, Foreman, dan Tapper.
- Pull master hanya mengirim master/config aktif. Push tetap bisa membaca referensi archived untuk audit, tetapi menandainya sebagai `inactive_master`.
- Pada beberapa form konfigurasi, field teknis `name` tetap tersimpan untuk display/search tetapi tidak ditampilkan sebagai title besar jika user lebih perlu mengisi field bisnis utama terlebih dahulu.

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
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Hanya record aktif yang dikirim pada pull master. |

Urutan data:

```text
code, name
```

Validasi:

- `code` wajib unik per `company_id` untuk record aktif.

Constraint database:

```text
partial unique index (code, company_id) where active
```

Pesan validasi:

```text
Estate code must be unique per company.
```

## Weather

Model teknis:

```text
wt.weather
```

Deskripsi:

Weather adalah master cuaca sederhana untuk pilihan kondisi cuaca operasional.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Ya | Ya | Nama cuaca. Diindeks untuk pencarian. |
| `description` | `Text` | Tidak | Ya | Deskripsi cuaca. |
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. |

Urutan data:

```text
name
```

## Weather Data

Model teknis:

```text
wt.weather.data
```

Deskripsi:

Weather Data menyimpan data cuaca per tanggal dan estate. Data ini menjadi catatan kondisi cuaca harian pada estate tertentu.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari tanggal, estate, dan weather. |
| `weather_date` | `Date` | Ya | Ya | Tanggal data cuaca. |
| `estate_id` | `Many2one(wt.estate)` | Ya | Ya | Estate tempat data cuaca berlaku. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `estate_id.company_id`, `store=True`, readonly. |
| `weather_id` | `Many2one(wt.weather)` | Ya | Ya | Master cuaca untuk tanggal dan estate tersebut. `ondelete="restrict"`. |

Catatan UI:

- Field `name` tidak ditampilkan pada form.
- Field paling atas pada form adalah `weather_date`.

Urutan data:

```text
weather_date desc, estate_id
```

Validasi:

- Kombinasi `estate_id` dan `weather_date` wajib unik.

Constraint database:

```text
unique(estate_id, weather_date)
```

Pesan validasi:

```text
Weather data must be unique per estate and date.
Weather data already exists for estate '%(estate)s' and date '%(date)s'.
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
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Helper employee role hanya memakai mapping aktif. |

Urutan data:

```text
company_id, role
```

Validasi:

- Kombinasi `company_id`, `role`, dan `job_id` wajib unik untuk record aktif.
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
partial unique index (company_id, role, job_id) where active
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

## Product

Model teknis:

```text
wt.product
```

Deskripsi:

Product adalah konfigurasi satu produk Odoo yang dipakai oleh WeighTrack pada company tertentu. Model ini bukan transaksi timbang; model ini hanya menentukan produk penimbangan aktif untuk company.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari company dan product. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company tempat mapping berlaku. Default mengikuti company user aktif. |
| `product_id` | `Many2one(product.product)` | Ya | Ya | Produk Odoo yang dipakai sebagai satu-satunya product weighing aktif untuk company tersebut. `ondelete="restrict"`. |
| `uom_id` | `Many2one(uom.uom)` | Otomatis | Tidak | Related UoM dari `product_id.uom_id`, stored dan readonly. |
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Mapping aktif saja yang dipakai pull dan validasi konfigurasi. |

Urutan data:

```text
company_id, product_id
```

Domain UI:

```text
product_id: ['|', ('product_tmpl_id.company_id', '=', False), ('product_tmpl_id.company_id', '=', company_id)]
```

Validasi:

- Hanya boleh ada satu mapping product aktif per company.
- Produk harus milik company yang sama atau produk global tanpa company.

Constraint database:

```text
partial unique index (company_id) where active
```

Pesan validasi:

```text
Only one weighing product is allowed per company.
Product must belong to the same company or be a global product.
```

## Customer

Model teknis:

```text
wt.customer
```

Deskripsi:

Customer adalah master customer WeighTrack per company yang mengikat ke contact Odoo `res.partner`. Master ini menjadi sumber pilihan customer pada Delivery dan receiver contact pada Rencana DO.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari company dan contact. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company tempat customer berlaku. Default mengikuti company user aktif. |
| `partner_id` | `Many2one(res.partner)` | Ya | Ya | Contact Odoo yang boleh dipilih sebagai customer Delivery. `ondelete="restrict"`. |
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Hanya customer aktif yang menjadi pilihan Delivery. |

Urutan data:

```text
company_id, partner_id
```

Domain UI:

```text
partner_id: ['|', ('company_id', '=', False), ('company_id', '=', company_id)]
```

Validasi:

- Kombinasi company dan contact wajib unik untuk record aktif.
- Contact harus milik company yang sama atau contact shared/global.
- Customer pada `wt.delivery.partner_id`, `wt.delivery.do.line.partner_id`, dan koreksi customer wajib berasal dari mapping aktif `wt.customer` sesuai company dokumen.

Constraint database:

```text
partial unique index (company_id, partner_id) where active
```

Pesan validasi:

```text
Customer contact must belong to the same company or be a shared contact.
Customer contact must be unique per company.
Customer must be registered in WeighTrack Customer master.
Receiver contact must be registered in WeighTrack Customer master.
```

## Shrinkage Tolerance

Model teknis:

```text
wt.shrinkage.tolerance
```

Deskripsi:

Shrinkage Tolerance adalah konfigurasi batas toleransi penyusutan produksi per company dan division. Konfigurasi ini dipakai sebagai nilai batas susut saat tanggal produksi tidak sama dengan tanggal penimbangan di gudang induk.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari company dan division. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company tempat toleransi berlaku. Default mengikuti company user aktif. |
| `division_id` | `Many2one(wt.division)` | Ya | Ya | Division tempat toleransi berlaku. `ondelete="restrict"`. |
| `shrinkage_tolerance_percentage` | `Float` | Ya | Ya | Persentase batas penyusutan produksi yang diizinkan. |
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Toleransi archived tidak dikirim pada pull master. |

Catatan UI:

- Field `name` tidak ditampilkan pada form.
- Field paling atas pada form adalah `company_id`.

Urutan data:

```text
company_id, division_id
```

Domain UI:

```text
division_id: [('company_id', '=', company_id)]
```

Validasi:

- Kombinasi `company_id` dan `division_id` wajib unik untuk record aktif.
- Division harus berada pada company yang sama.
- `shrinkage_tolerance_percentage` harus berada di antara 0 dan 100.

Constraint database:

```text
partial unique index (company_id, division_id) where active
```

Pesan validasi:

```text
Shrinkage tolerance already exists for company '%(company)s', and division '%(division)s'.
Division must belong to the same company.
Shrinkage tolerance percentage must be between 0 and 100.
```

## Receipt Rule

Model teknis:

```text
wt.receipt.rule
```

Deskripsi:

Receipt Rule adalah konfigurasi alur penerimaan stok untuk kombinasi Weighing Location dan Division tertentu. Record ini menentukan Warehouse, Receiving Location, dan Operation Type yang akan dipakai ketika data timbang diproses menjadi Production Receipt dan Inventory Receipt.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari weighing location dan division. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `weighing_location_id.company_id`, `store=True`, readonly. |
| `estate_id` | `Many2one(wt.estate)` | Otomatis | Tidak | Related dari `weighing_location_id.estate_id`, `store=True`, readonly. |
| `weighing_location_id` | `Many2one(wt.weighing.location)` | Ya | Ya | Lokasi timbang warehouse tempat aturan berlaku. `ondelete="restrict"`. Domain dibatasi ke `location_type = warehouse`. |
| `allowed_division_ids` | `Many2many(wt.division)` | Otomatis | Tidak | Computed helper dari `weighing_location_id.allowed_division_ids` untuk domain Division. |
| `division_id` | `Many2one(wt.division)` | Ya | Ya | Division yang boleh menimbang produk di lokasi tersebut. Wajib termasuk allowed division pada Weighing Location. |
| `warehouse_id` | `Many2one(stock.warehouse)` | Ya | Ya | Warehouse tujuan stok. |
| `allowed_location_ids` | `Many2many(stock.location)` | Otomatis | Tidak | Computed helper untuk membatasi lokasi internal di bawah view location warehouse terpilih. |
| `location_id` | `Many2one(stock.location)` | Ya | Ya | Receiving Location. Harus internal, company sama/shared, dan berada di bawah warehouse terpilih. |
| `operation_type_id` | `Many2one(stock.picking.type)` | Ya | Ya | Operation Type stock yang dipakai. Harus milik warehouse terpilih. |
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Receipt rule archived tidak dikirim pada pull master. |

Urutan data:

```text
weighing_location_id, division_id
```

Domain UI:

```text
division_id: [('id', 'in', allowed_division_ids)]
warehouse_id: [('company_id', '=', company_id), ('estate_id', '=', estate_id)]
location_id: [('id', 'in', allowed_location_ids)]
operation_type_id: [('warehouse_id', '=', warehouse_id)]
```

Validasi:

- Kombinasi `company_id`, `weighing_location_id`, dan `division_id` wajib unik untuk record aktif. Secara database uniqueness dijaga oleh kombinasi weighing location dan division yang masih aktif; company mengikuti weighing location.
- Weighing Location, Division, Warehouse, Receiving Location, dan Operation Type harus konsisten dengan company.
- Weighing Location pada Receipt Rule wajib bertipe `warehouse`.
- Estate Receipt Rule otomatis mengikuti estate Weighing Location.
- Warehouse harus berasal dari company dan estate yang sama dengan Receipt Rule.
- Division harus termasuk `allowed_division_ids` pada Weighing Location.
- Receiving Location harus berupa internal location, boleh shared atau company yang sama, dan wajib berada di bawah view location warehouse terpilih.
- Operation Type harus berasal dari Warehouse yang dipilih.

Constraint database:

```text
partial unique index (weighing_location_id, division_id) where active
```

Pesan validasi:

```text
Receipt Rule already exists for company '%(company)s', weighing location '%(location)s', and division '%(division)s'. Please use the existing rule or change one of those values.
Weighing location must belong to the same company.
Receipt Rule can only use Warehouse weighing locations.
Division must belong to the same company.
Division must be allowed in the selected weighing location.
Warehouse must belong to the same company.
Location must belong to the same company or be a shared location.
Location must be an internal location.
Location must be under the selected warehouse.
Operation type must belong to the same company.
Operation type must belong to the selected warehouse.
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
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Division archived tidak dikirim pada pull master. |

Urutan data:

```text
estate_id, code, name
```

Validasi:

- `code` wajib unik per `estate_id` untuk record aktif.
- Clerk harus valid menurut employee role `clerk` pada company division.

Constraint database:

```text
partial unique index (code, company_id) where active
```

Pesan validasi:

```text
Division code must be unique per company.
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

Weighing Location adalah master lokasi timbang. Lokasi timbang menentukan divisi mana saja yang diizinkan menimbang di lokasi tersebut. Lokasi bertipe `warehouse` dipakai sebagai lokasi timbang final/gudang dan menjadi scope Receipt Rule. Lokasi bertipe `field` dipakai sebagai lokasi timbang awal di lapangan dan wajib mengarah ke satu lokasi warehouse pada estate yang sama.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `code` | `Char` | Ya | Ya | Kode lokasi timbang. Diindeks untuk pencarian. |
| `name` | `Char` | Ya | Ya | Nama lokasi timbang. |
| `location_type` | `Selection` | Ya | Ya | Tipe lokasi: `warehouse` atau `field`. Default `warehouse`. |
| `estate_id` | `Many2one(wt.estate)` | Ya | Ya | Estate lokasi timbang. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related dari `estate_id.company_id`, `store=True`, readonly. |
| `warehouse_weighing_location_id` | `Many2one(wt.weighing.location)` | Tidak/bersyarat | Ya | Parent lokasi timbang warehouse untuk lokasi bertipe `field`. Wajib jika `location_type = field`, kosong jika `warehouse`. |
| `operator_id` | `Many2one(hr.employee)` | Tidak | Ya | Employee operator lokasi timbang. Domain berdasarkan employee role `operator`. |
| `allowed_operator_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Operator. |
| `selectable_division_ids` | `Many2many(wt.division)` | Otomatis | Tidak | Computed helper domain division. Untuk field location mengikuti division yang diizinkan pada parent warehouse. |
| `allowed_division_ids` | `Many2many(wt.division)` | Tidak | Ya | Daftar divisi yang diizinkan menimbang di lokasi ini. Untuk `field`, pilihannya harus subset dari parent warehouse. |
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Weighing location archived tidak dikirim pada pull master. |

Urutan data:

```text
estate_id, code, name
```

Validasi:

- `code` wajib unik per `estate_id` untuk record aktif.
- Semua `allowed_division_ids` harus berasal dari estate yang sama dengan `estate_id`.
- Jika `location_type = warehouse`, `warehouse_weighing_location_id` wajib kosong.
- Jika `location_type = field`, `warehouse_weighing_location_id` wajib diisi, harus bertipe `warehouse`, tidak boleh record yang sama, dan harus berada pada estate yang sama.
- Allowed division pada field location wajib subset dari allowed division pada parent warehouse.
- Operator harus valid menurut employee role `operator` pada company lokasi timbang.

Constraint database:

```text
partial unique index (code, estate_id) where active
```

Pesan validasi:

```text
Weighing location code must be unique per estate.
Allowed divisions must belong to the same estate as the weighing location.
Warehouse weighing location must not have a parent warehouse weighing location.
Field weighing location must select a warehouse weighing location.
Field weighing location cannot reference itself as warehouse weighing location.
Warehouse weighing location must use Warehouse type.
Warehouse weighing location must belong to the same estate.
Field weighing location divisions must be allowed by the selected warehouse weighing location.
%s employee must belong to the same company.
%s employee role has not been configured for this company.
%s employee must use an allowed job position for this company.
```

Domain UI:

```text
warehouse_weighing_location_id: [('location_type', '=', 'warehouse'), ('estate_id', '=', estate_id)]
allowed_division_ids: [('id', 'in', selectable_division_ids)]
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
- Lokasi warehouse menjadi lokasi final penimbangan yang dipakai `wt.weighing.weighing_location_id` dan Receipt Rule.
- Lokasi field menjadi lokasi awal/lapangan yang dipakai `wt.weighing.initial_weighing_location_id`.
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
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Foreman archived tidak dikirim pada pull master. |

Urutan data:

```text
division_id, employee_id
```

Validasi:

- Kombinasi `employee_id` dan `division_id` wajib unik untuk record aktif.
- Employee foreman harus valid menurut employee role `foreman` pada company division.
- Tapper bisa dikelola dari form Foreman melalui add line natural Odoo pada field `tapper_ids`.
- Jika `foreman_id` diisi, `division_id` Tapper otomatis mengikuti division Foreman.

Constraint database:

```text
partial unique index (employee_id, division_id) where active
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
| `active` | `Boolean` | Tidak | Ya | Status archive standar Odoo. Tapper archived tidak dikirim pada pull master. |

Urutan data:

```text
division_id, foreman_id, employee_id
```

Validasi:

- Satu Tapper employee hanya boleh dibuat satu kali untuk record aktif.
- Employee Tapper harus valid menurut employee role `tapper` pada company division.
- Jika `foreman_id` diisi, Foreman harus berada pada division yang sama dengan Tapper.

Constraint database:

```text
partial unique index (employee_id) where active
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
- Satu Tapper employee hanya boleh memiliki satu record Tapper aktif.
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
| `role` | `Selection` | Ya | Ya | Role device. Saat ini selalu `operator`, otomatis diisi saat create, disembunyikan pada form, dan tidak boleh diubah menjadi role lain. |
| `employee_id` | `Many2one(hr.employee)` | Ya | Ya | Employee penanggung jawab device. Domain berdasarkan `company_id` dan role `operator`. |
| `allowed_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk domain employee. |
| `status` | `Selection` | Ya | Ya | State device: `inactive`, `active`, `blocked`, `revoked`. Ditampilkan sebagai statusbar. |
| `token` | `Char` | Otomatis | Tidak | Token enrollment. Dibuat otomatis saat create jika belum diisi. Unik. |
| `actived_at` | `Datetime` | Tidak | Ya | Waktu aktivasi pertama. Nama field saat ini masih `actived_at`. |
| `last_pull` | `Datetime` | Tidak | Ya | Waktu pull terakhir. Diperbarui saat pull master berhasil. |
| `last_push` | `Datetime` | Tidak | Ya | Waktu push terakhir. Diperbarui saat push weighing berhasil. |
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
role: operator
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
- Saat create, `role` dipaksa menjadi `operator`.
- Saat create, `token` otomatis dibuat dengan `secrets.token_urlsafe(32)` jika belum ada token.
- Token dicek unik maksimal 10 kali percobaan.
- Write role selain `operator` ditolak.
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
Device role is always Operator.
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

## Weighing

Model teknis:

```text
wt.weighing
```

Deskripsi:

Weighing adalah transaksi raw penimbangan. Record dapat dibuat melalui push API atau secara manual dari Odoo. Model inbound/header tidak aktif; setiap item push langsung membentuk satu record model ini.

Field utama:

| Field | Type | Keterangan |
| --- | --- | --- |
| `name` | `Char` | Stored number generated once at create from `ir.sequence` code `wt.weighing`. Default format: `WG/YYYYMMDD/NNN`, using `production_date` as the sequence date. |
| `data_source` | `Selection` | Sumber record: `api` atau `manual`. |
| `local_id` | `Char` | ID lokal item aplikasi. Wajib untuk API dan null untuk data manual baru. |
| `device_id` | `Char` | Device ID teknis. Wajib untuk API dan null untuk data manual baru. |
| `device_record_id` | `Many2one(wt.device)` | Device pengirim API. Null untuk manual. |
| `batch_local_id` | `Char` | ID batch aplikasi. Null untuk manual. |
| `company_id` | `Many2one(res.company)` | Company device. |
| `production_date` | `Date` | Tanggal produksi. |
| `weighing_date` | `Datetime` | Waktu timbang. |
| `master_synced_at` | `Datetime` | Waktu sync master aplikasi; disimpan untuk audit dan bukan data problem. |
| `sent_at`, `received_at` | `Datetime` | Waktu kirim aplikasi dan waktu terima Odoo. |
| `state` | `Selection` | Status keterikatan Production Receipt: `not_receipted`, `in_production_receipt`, `receipt_validated`, `receipt_cancelled`. |
| `production_receipt_id` | `Many2one(wt.production.receipt)` | Production Receipt terakhir/aktif yang mengikat data timbang. |
| `has_data_problem` | `Boolean` | Flag konflik terhadap master Odoo atau aturan Weighing. |
| `data_problem_code` | `Selection` | Kode problem utama atau `multiple_problem`. |
| `data_problem_note_en` | `Text` | Catatan asli hasil evaluasi dalam bahasa Inggris untuk audit/debug. |
| `data_problem_note_idn` | `Text` | Catatan hasil evaluasi dalam bahasa Indonesia. |
| `data_problem_note` | `Text` computed | Catatan display sesuai preferensi bahasa user; `id_ID` memakai `data_problem_note_idn`, bahasa lain memakai `data_problem_note_en`. |
| `device_snapshot_json` | `Text` | Snapshot item payload dari aplikasi. |
| `odoo_snapshot_json` | `Text` | Snapshot master Odoo saat pengecekan problem. |
| `estate_id`, `weighing_location_id`, `division_id` | Relasi scope | Scope estate, lokasi timbang final/gudang, dan division. `weighing_location_id` wajib bertipe `warehouse`. |
| `product_id`, `uom_id`, `receipt_rule_id` | Relasi product | Produk dan satuan otomatis dari mapping aktif `wt.product` pada company; receipt rule menentukan alur penerimaan. |
| `operator_employee_id`, `operator_name`, `operator_barcode` | Employee | Operator. Nama dan barcode related dari employee. |
| `clerk_employee_id`, `clerk_name`, `clerk_barcode` | Employee | Clerk/Kerani. Nama dan barcode related dari employee. |
| `foreman_employee_id`, `foreman_name`, `foreman_barcode` | Employee | Foreman/Mandor. Nama dan barcode related dari employee. |
| `tapper_employee_id`, `tapper_name`, `tapper_barcode` | Employee | Tapper. Nama dan barcode related dari employee. |
| `foreman_id`, `tapper_id` | Assignment reference | Reference tersembunyi untuk reverse tracking assignment. |
| `total_bag` | `Integer` | Jumlah karung. |
| `production_weight` | `Float` | Berat produksi. |
| `reject_weight` | `Float` | Berat reject. |
| `slab_weight` | `Float` | Berat slab. |
| `net_weight` | `Float` | Berat net. |
| `shrinkage_tolerance_percentage`, `shrinkage_tolerance_weight` | `Float` | Persentase dan berat toleransi penyusutan. |
| `shrinkage_tolerance_override` | `Boolean` | True jika toleransi susut pernah dioverride. |
| `shrinkage_tolerance_override_reason`, `shrinkage_tolerance_override_at`, `shrinkage_tolerance_override_by_id` | Audit | Alasan, waktu, dan user override toleransi susut terakhir. |
| `shrinkage_tolerance_override_id` | `Many2one(wt.shrinkage.tolerance.override)` | Dokumen override batch terakhir yang mengubah data timbang. |
| `original_shrinkage_tolerance_percentage`, `original_shrinkage_tolerance_weight`, `original_production_weight`, `original_net_weight` | `Float` readonly | Nilai awal sebelum override pertama, disimpan untuk audit. |
| `initial_weighing_date`, `initial_weight` | Initial weighing | Waktu dan berat penimbangan awal. |
| `initial_weighing_location_id` | `Many2one(wt.weighing.location)` | Lokasi timbang awal/lapangan. Wajib bertipe `field` jika diisi. |
| `initial_device_id` | `Many2one(wt.device)` | Device penimbangan awal (`By Device`). |
| `initial_device_role`, `initial_device_employee_id`, `initial_device_employee_barcode` | Related | Mengikuti initial device dan readonly. |
| `initial_is_manual_weighing`, `initial_manual_weighing_reason`, `initial_note` | Mixed | Informasi manual dan catatan penimbangan awal. |

Index idempotency:

```sql
CREATE UNIQUE INDEX wt_weighing_api_idempotency_uniq
ON wt_weighing (device_id, local_id)
WHERE data_source = 'api';
```

Aturan:

- Idempotency hanya berlaku untuk data API.
- Data manual baru menyimpan `local_id`, `device_id`, `device_record_id`, dan `batch_local_id` sebagai null.
- Data API mewajibkan `local_id`, `device_id`, dan `device_record_id`.
- Datetime dari push API (`weighing_date`, `initial_weighing.weighing_date`, `master_synced_at`, `sent_at`, dan delivery `weighed_at`) dibaca sebagai waktu lokal timezone bot user API, lalu dikonversi ke UTC sebelum disimpan oleh Odoo.
- Product dan UoM pada input manual maupun API diprioritaskan dari mapping aktif `wt.product` berdasarkan company dan readonly pada UI.
- Weighing Location final wajib bertipe `warehouse`.
- Detail weighing tidak lagi divalidasi langsung dari form Weighing; validasi resmi dilakukan dari Production Receipt.
- Save record draft manual maupun API menjalankan recheck jika field pemicu berubah.
- Push menghitung problem dari payload sebelum create; Production Receipt Validate menjalankan recheck lagi.
- Jika `state = receipt_validated`, data timbang terkunci dan action `Recheck Data Problem` ditolak.
- Field petugas mengunci nama dan barcode pada `hr.employee` langsung, bukan pada struktur assignment foreman/tapper yang bisa berubah.
- Reverse tracking foreman: employee -> `wt.foreman` -> division.
- Reverse tracking tapper: employee -> `wt.tapper` -> division dan foreman -> employee foreman.
- Override toleransi susut dilakukan dari menu `Operations > Override Toleransi Susut` melalui model persistent `wt.shrinkage.tolerance.override`. Override dapat dilakukan walaupun data tidak sedang problem, selama status weighing bukan `receipt_validated`.
- Saat override diterapkan, sistem menghitung ulang `shrinkage_tolerance_percentage`, `shrinkage_tolerance_weight`, `production_weight`, dan `net_weight`, lalu menjalankan recheck data problem melalui perubahan data timbang.

Validasi backend untuk Production Receipt:

- `production_date` tidak boleh lebih besar dari tanggal lokal `weighing_date`.
- Sebelum Production Receipt bisa validated, production date, weighing date, company, estate, division, weighing location, product, UoM, receipt rule, serta seluruh employee wajib terisi pada setiap weighing line.
- `total_bag`, `production_weight`, dan `net_weight` wajib lebih dari 0 sebelum Production Receipt bisa validated.
- Jika initial weighing date terisi, initial weight wajib lebih dari 0.
- Jika initial weighing location diisi, lokasinya wajib bertipe `field` dan berada pada company yang sama.
- Untuk data manual, initial device dan initial weighing location wajib jika initial weighing date terisi.
- Untuk API, initial device atau initial weighing location yang kosong/tidak ditemukan menjadi `missing_master` dan tidak menggagalkan create.
- Jika initial manual weighing aktif, manual weighing reason wajib terisi.

## Production Receipt

Model teknis:

```text
wt.production.receipt
wt.production.receipt.line
```

Deskripsi:

Production Receipt adalah dokumen penerimaan produksi untuk menggabungkan data timbang Weighing berdasarkan company, production date, division, product, operation type, dan receiving location. Saat validate, sistem membuat satu lot dan satu Inventory Receipt (`stock.picking`) berdasarkan header Production Receipt, lalu mengunci data timbang.

Field header utama:

| Field | Type | Keterangan |
| --- | --- | --- |
| `name` | `Char` | Stored number generated once at create from `ir.sequence` code `wt.production.receipt`. Default format: `PR/YYYYMMDD/NNN`, using `production_date` as the sequence date. |
| `company_id` | `Many2one(res.company)` | Company receipt. |
| `production_date` | `Date` | Tanggal produksi yang digabungkan. |
| `received_date` | `Date` | Tanggal diterima. Wajib diisi dan tidak boleh sebelum `production_date`. |
| `division_id` | `Many2one(wt.division)` | Division produksi. |
| `clerk_employee_id` | `Many2one(hr.employee)` | Snapshot Clerk dari Division. Diisi otomatis dan tidak diedit manual. |
| `product_id` | `Many2one(product.product)` | Product aktif dari mapping `wt.product` pada company. Diisi otomatis dan readonly pada view. |
| `operation_type_id` | `Many2one(stock.picking.type)` | Operation Type penerimaan. Pilihan dibatasi dari Receipt Rule aktif sesuai company dan division. |
| `location_id` | `Many2one(stock.location)` | Receiving Location. Pilihan dibatasi dari Receipt Rule aktif sesuai company, division, dan operation type. |
| `warehouse_id` | `Many2one(stock.warehouse)` | Related dari `operation_type_id.warehouse_id`, readonly. |
| `lot_id` | `Many2one(stock.lot)` | Lot yang dibuat/dipakai saat validate. Satu Production Receipt memakai satu lot. |
| `stock_picking_id` | `Many2one(stock.picking)` | Inventory Receipt utama yang dibuat saat validate. |
| `reverse_picking_id` | `Many2one(stock.picking)` | Inventory Reversal utama yang dibuat saat cancel. |
| `line_ids` | `One2many(wt.production.receipt.line)` | Detail weighing yang masuk receipt. |
| `stock_picking_ids` | `One2many(stock.picking)` | Relasi teknis/fallback Inventory Receipt yang dibuat dari Production Receipt. |
| `reverse_picking_ids` | `One2many(stock.picking)` | Relasi teknis/fallback Inventory Reversal yang dibuat dari cancel Production Receipt. |
| `stock_picking_count` | `Integer computed` | Jumlah Inventory Receipt terkait. |
| `reverse_picking_count` | `Integer computed` | Jumlah Inventory Reversal terkait. |
| `total_weighing` | `Integer` computed stored | Jumlah data timbang pada receipt. |
| `data_problem_count` | `Integer` computed stored | Jumlah line bermasalah. |
| `total_bag` | `Integer` computed stored | Total `total_bag` dari line. |
| `total_stock_weight` | `Float` computed stored | Total stock weight dari line. |
| `state` | `Selection` | `draft`, `processed`, `validated`, `cancelled`. |
| `validated_at`, `validated_by_id` | Audit | Waktu dan user validate. |
| `cancelled_at`, `cancelled_by_id`, `cancel_reason` | Audit | Informasi pembatalan. |

Catatan inventory:

- Inventory Receipt (`stock.picking`) yang dibuat dari Production Receipt memakai `received_date` sebagai Scheduled Date dan Effective Date.
- Flow normal menghasilkan satu Inventory Receipt dan satu Inventory Reversal per Production Receipt.

Field line utama:

| Field | Type | Keterangan |
| --- | --- | --- |
| `receipt_id` | `Many2one(wt.production.receipt)` | Header Production Receipt. |
| `weighing_id` | `Many2one(wt.weighing)` | Data timbang sumber. |
| `company_id`, `production_date`, `division_id` | Related stored | Scope dari weighing source. |
| `estate_id`, `weighing_location_id` | Related stored | Scope lokasi timbang. |
| `product_id`, `uom_id`, `receipt_rule_id` | Related stored | Product dan receipt rule dari weighing source. |
| `operator_employee_id`, `clerk_employee_id`, `foreman_employee_id`, `tapper_employee_id` | Related stored | Employee pada data timbang. |
| `total_bag` | Related stored | Jumlah karung dari weighing source. |
| `stock_weight` | Computed stored | Berat stock dari field constant product. |
| `has_data_problem`, `data_problem_code`, `data_problem_note` | Related | Status problem dari weighing source. |

Flow:

- Tombol `Process` mengambil semua `wt.weighing` sesuai company, production date, division, product header, dan Receipt Rule aktif yang mengarah ke operation type serta receiving location header.
- Beberapa Weighing Location dapat tergabung dalam satu Production Receipt bila Receipt Rule aktifnya mengarah ke operation type dan receiving location yang sama.
- Data timbang yang masuk line berubah menjadi `state = in_production_receipt`.
- Line dapat dilepas selama Production Receipt belum validated; data timbang kembali menjadi `state = not_receipted` dan `production_receipt_id` dikosongkan.
- Tombol `Validate` menjalankan validasi wajib dan `Recheck Data Problem` untuk semua line.
- Validate ditolak jika line kosong, ada line tidak sesuai header product/operation type/receiving location, ada duplicate, atau masih ada `has_data_problem = True`.
- Saat validate, sistem membuat satu Inventory Receipt dengan operation type dan receiving location dari header.
- Inventory Receipt memakai clerk pada Division sebagai `receive_from_employee_id`; jika employee punya partner terkait, field contact receipt juga diisi.
- Lot dibuat otomatis satu kali per Production Receipt dengan format `LOT/kode_divisi/YYYYMMDD/NNN`, misalnya `LOT/DIV01/20260629/001`.
- Saat berhasil validate, Production Receipt menjadi `validated` dan semua data timbang line menjadi `state = receipt_validated`.
- Setelah `receipt_validated`, data timbang terkunci dari edit normal dan action `Recheck Data Problem` ditolak.
- Return manual dari Inventory ditolak untuk Inventory Receipt dan Inventory Reversal yang berasal dari Production Receipt.
- Tombol `Cancel` membuka wizard alasan pembatalan. Setelah alasan dikonfirmasi, sistem membuat Inventory Reversal otomatis dengan lokasi terbalik, lot yang sama, dan quantity yang sama.
- Cancel ditolak jika stock lot di receiving location original tidak mencukupi untuk dibalik.
- Setelah reversal berhasil, Production Receipt menyimpan `cancel_reason`, menjadi `cancelled`, dan data timbang menjadi `receipt_cancelled`.

## Override Toleransi Susut

Menu:

```text
WeighTrack > Operations > Override Toleransi Susut
```

Model teknis:

```text
wt.shrinkage.tolerance.override
wt.shrinkage.tolerance.override.line
```

Deskripsi:

Override Toleransi Susut adalah dokumen transaksi untuk menyimpan histori override gelondongan. Setiap record menyimpan filter, persentase, alasan, status apply, user apply, waktu apply, dan line snapshot kandidat data timbang.

Field header utama:

| Field | Type | Keterangan |
| --- | --- | --- |
| `name` | `Char` | Nomor dari `ir.sequence` `wt.shrinkage.tolerance.override`, format `STO/YYYYMMDD/NNN`. |
| `company_id`, `estate_id`, `division_id` | Scope wajib | Perusahaan, estate, dan divisi data timbang. |
| `foreman_id`, `tapper_id` | Scope opsional | Filter mandor dan tapper. Jika kosong, semua dalam scope ikut dipilih. |
| `production_date` | `Date` | Tanggal produksi. |
| `shrinkage_tolerance_percentage` | `Float` | Persentase toleransi susut baru. |
| `reason` | `Text` | Alasan kebijakan override. |
| `line_ids` | `One2many(wt.shrinkage.tolerance.override.line)` | Snapshot data timbang yang dipilih untuk override. |
| `total_count` | `Integer computed stored` | Jumlah data timbang yang dipilih. |
| `state` | `Selection` | `draft` atau `applied`. |
| `applied_at`, `applied_by_id` | Audit | Waktu dan user yang menjalankan apply. |

Field line utama:

| Field | Type | Keterangan |
| --- | --- | --- |
| `override_id` | `Many2one(wt.shrinkage.tolerance.override)` | Header override. |
| `weighing_id` | `Many2one(wt.weighing)` | Data timbang kandidat. |
| `production_receipt_id` | `Many2one(wt.production.receipt)` | Receipt saat preview/apply, jika ada. |
| `weighing_state` | `Selection` | Status weighing saat preview. |
| `foreman_id`, `tapper_id` | Relasi | Mandor dan tapper saat preview. |
| `initial_weight`, `reject_weight`, `slab_weight` | `Float` | Berat dasar yang dipakai hitung ulang. |
| `current_*` | `Float` | Nilai sebelum override saat preview. |
| `new_*` | `Float` | Nilai hasil perhitungan override. |
| `already_overridden` | `Boolean` | True jika weighing sudah pernah dioverride sebelumnya. |

Aturan:

- Kandidat hanya `wt.weighing` dengan `initial_weighing_date` terisi dan `initial_weight > 0`.
- Kandidat hanya data dengan status weighing bukan `receipt_validated`.
- Kandidat hanya data yang tidak memiliki data problem (`has_data_problem = False`).
- User dapat menghapus baris pada tab `Data Timbangan` sebelum apply untuk menentukan final data yang dioverride.
- Preview menghitung berat toleransi baru, berat produksi baru, dan berat net baru.
- Data dengan hasil `production_weight <= 0` atau `net_weight <= 0` tidak dimasukkan ke line preview.
- Apply menulis override ke masing-masing `wt.weighing` yang tersisa di line dan mempertahankan nilai original sebelum override pertama.

Kode data problem:

| Code | English Description | Penjelasan Indonesia |
| --- | --- | --- |
| `none` | No data problem was found. | Tidak ditemukan masalah data. |
| `company_mismatch` | The payload company does not match the device company, or the division does not belong to the weighing company. | Company payload tidak sesuai company device, atau division bukan milik company penimbangan. |
| `estate_mismatch` | The estate does not belong to the weighing company, or it does not match the estate assigned to the weighing location. | Estate bukan milik company penimbangan, atau berbeda dari estate yang terikat pada weighing location. |
| `operator_mismatch` | The payload operator or weighing-location operator does not match the device operator. | Operator payload atau operator weighing location berbeda dari operator device. |
| `weighing_location_mismatch` | The weighing location does not belong to the weighing company, the final weighing location is not Warehouse, or the initial weighing location is not Field / belongs to another company. | Lokasi timbang tidak sesuai company penimbangan, lokasi final bukan Warehouse, atau lokasi awal bukan Field / berbeda company. |
| `division_not_allowed` | The division is not included in the weighing location's allowed divisions. | Division tidak termasuk division yang diizinkan pada weighing location. |
| `receipt_rule_mismatch` | The receipt rule does not match the company, weighing location, or division. | Receipt rule tidak sesuai company, weighing location, atau division. |
| `product_mapping_mismatch` | The product is not configured as `weighing` for the weighing company. | Product tidak dipetakan sebagai `weighing` untuk company penimbangan. |
| `clerk_mismatch` | The clerk employee does not match the clerk assigned to the division. | Employee clerk berbeda dari clerk yang ditetapkan pada division. |
| `foreman_mismatch` | The foreman employee is not assigned to the division, or the foreman ID and employee are inconsistent. | Employee foreman tidak memiliki assignment pada division, atau ID dan employee foreman tidak konsisten. |
| `tapper_mismatch` | The tapper is not registered, belongs to another division, is not assigned to the selected foreman, or has an inconsistent employee. | Tapper tidak terdaftar, berada pada division lain, tidak berada di bawah foreman yang dipilih, atau employee tidak konsisten. |
| `weight_formula_mismatch` | `production_weight` does not equal `slab_weight + reject_weight + net_weight`. | `production_weight` tidak sama dengan `slab_weight + reject_weight + net_weight`. |
| `initial_weighing_date_mismatch` | The initial weighing date does not match the production date. | Tanggal initial weighing berbeda dari production date. |
| `initial_weight_mismatch` | For cross-day weighing, production weight does not equal initial weight minus shrinkage tolerance weight. | Untuk penimbangan lintas hari, production weight tidak sama dengan initial weight dikurangi shrinkage tolerance weight. |
| `shrinkage_tolerance_mismatch` | Shrinkage tolerance weight does not equal initial weight multiplied by the shrinkage percentage. | Shrinkage tolerance weight tidak sama dengan initial weight dikali persentase penyusutan. |
| `inactive_master` | A referenced master record still exists but has been archived/inactivated. | Master yang direferensikan masih ada, tetapi sudah diarsipkan/nonaktif. Termasuk initial weighing location. |
| `missing_master` | A referenced master record, initial device, or initial weighing location was not found, or the required initial device/location was not provided. | Master yang direferensikan, initial device, atau initial weighing location tidak ditemukan, atau initial device/lokasi awal yang wajib tidak dikirim. |
| `multiple_problem` | More than one data problem type was found; details are stored in the problem note. | Lebih dari satu jenis masalah data ditemukan; rinciannya tersimpan pada catatan masalah. |

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
| `push_enabled` | `Boolean` | Tidak | Ya | Jika tidak aktif, endpoint push data untuk company ini ditutup. Default aktif. Saat ini dipakai oleh push weighing. |

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
role: operator
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
- Memastikan role device adalah `operator`.
- Memastikan pull dibuka melalui `wt.api.pull_enabled`.
- Mengambil bot user dari `wt.api.security.service`.
- Menghitung scope data berdasarkan company, employee, dan role device.
- Hanya mengambil master/config aktif untuk payload offline.
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
| `foreman` | Foreman record milik employee device, division foreman, tapper yang berada di bawah foreman tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait. |
| `clerk` | Division yang `clerk_id`-nya employee device, foreman di division tersebut, tapper di division tersebut, estate, weighing location terkait division, receipt rule, product, UoM, shrinkage tolerance, dan employee terkait. |
| `operator` | Weighing location yang `operator_id`-nya employee device, allowed division dari weighing location, receipt rule, product, UoM, shrinkage tolerance, clerk division, foreman, tapper, dan estate. |

Response data yang disiapkan service:

```text
meta
scope
masters
```

Meta payload:

```text
server_time
timezone
role
company_id
employee_id
device
```

Scope payload:

```text
role
company_id
estate_ids
division_ids
weighing_location_ids
receipt_rule_ids
product_ids
uom_ids
shrinkage_tolerance_ids
employee_ids
foreman_ids
tapper_ids
```

Master payload:

```text
company
roles
employees
estates
divisions
weighing_locations
receipt_rules
products
uoms
shrinkage_tolerances
foremen
tappers
```

Catatan payload:

- `pull_type` tidak dipakai.
- Payload device berada di `data.meta.device`.
- Payload `server_time`, `last_pull`, dan `last_seen` diformat memakai timezone bot user dari `wt.api`; timezone tersebut dikirim di `data.meta.timezone`.
- Payload company berada di `data.masters.company`.
- Payload employee dipusatkan di `data.masters.employees`.
- Payload role aplikasi berada di `data.masters.roles` dan hanya membawa role device yang sedang pull.
- Master/config yang memiliki field `active` hanya dikirim jika masih aktif. Record archived dikeluarkan dari `scope` dan `masters`.
- Weighing Location membawa `location_type` dan `warehouse_weighing_location_id`. Field `warehouse_weighing_location_id` dipakai untuk menghubungkan lokasi field ke lokasi warehouse.
- Payload Receipt Rule hanya membawa rule scope company, warehouse weighing location, dan division.
- Payload Product membawa `id`, `name`, `company_id`, dan `uom_id`; `default_code` dan product type tidak dikirim.
- Payload UoM berada di `data.masters.uoms`.
- Payload Product berada di `data.masters.products` dan hanya membawa product Odoo yang berasal dari mapping aktif `wt.product` untuk company dalam scope.
- Payload Shrinkage Tolerance berada di `data.masters.shrinkage_tolerances` dan hanya membawa toleransi yang sesuai dengan division dalam scope.
- Warehouse stock, stock location, dan operation type tetap tersimpan di model Receipt Rule, tetapi tidak dikirim pada response pull master.
- Setiap data master minimal membawa `id` dan `name`.
- Master yang memiliki `code`, seperti Estate, Division, dan Weighing Location, ikut membawa `code`.
- Employee barcode dibawa di master terpusat `employees`; payload foreman dan tapper hanya membawa relasi seperti `employee_id`, `company_id`, dan division terkait.

### API Push Weighing Service

Model teknis:

```text
wt.api.push.weighing.service
```

File:

```text
services/api_push_weighing_service.py
```

Tanggung jawab:

- Mengautentikasi device melalui `wt.api.security.service`.
- Memastikan role device adalah `operator`.
- Memastikan push dibuka melalui `wt.api.push_enabled`.
- Mengambil bot user dari `wt.api.security.service`.
- Memvalidasi root payload: `product`, `items`, `master_synced_at`, dan `sent_at`.
- Memanggil `wt.weighing.service` untuk validasi dan pemrosesan setiap item.
- Menjalankan Weighing Service menggunakan user dan bahasa bot user.
- Memperbarui `last_push`, `last_seen`, dan `app_version` pada device.
- Membentuk summary response `received`, `created`, `duplicates`, `with_data_problem`, dan `weighing_ids`.

Endpoint:

```text
POST /weightrack/api/v1/push/weighing
```

Payload wajib root:

```text
device_id
token
items
```

Payload wajib per item weighing:

```text
local_id
production_date
weighing_date
```

Response data yang disiapkan service:

```text
summary
items
```

Catatan:

- Jika `product` dikirim, nilainya harus `weighing`.
- `master_synced_at` disimpan untuk audit, tetapi tidak menjadi data problem.
- Push langsung membuat `wt.weighing` dan tidak membuat inbound/receipt.

### Weighing Service

Model teknis:

```text
wt.weighing.service
```

File:

```text
services/weighing_service.py
```

Tanggung jawab:

- Memvalidasi bentuk dan field wajib setiap item.
- Melakukan pre-check duplicate berdasarkan `data_source = api`, `device_id`, `product`, dan `local_id`.
- Menangani race condition idempotency melalui partial unique index dan savepoint database.
- Memetakan object payload ke master Odoo dan membuat `wt.weighing`.
- Melakukan reverse lookup assignment foreman dan tapper dari employee.
- Mengevaluasi seluruh data problem, rumus berat, shrinkage, dan initial weighing.
- Membentuk snapshot payload device dan snapshot master Odoo.
- Dipakai juga oleh model `wt.weighing` untuk action `Recheck Data Problem`, sehingga service ini bukan endpoint HTTP.

Method penting:

```text
validate_items(items)
process_items(...)
evaluate_data_problem_from_record(detail)
```

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
POST /weightrack/api/v1/push/weighing
```

File:

```text
controllers/api/v1/device_api.py
controllers/api/v1/pull_api.py
controllers/api/v1/push_api.py
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

Route push weighing:

```python
@http.route(
    "/weightrack/api/v1/push/weighing",
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
| `wt.weather` | Ya | Ya | Ya | Ya |
| `wt.weather.data` | Ya | Ya | Ya | Ya |
| `wt.employee.role` | Ya | Ya | Ya | Ya |
| `wt.product` | Ya | Ya | Ya | Ya |
| `wt.customer` | Ya | Ya | Ya | Ya |
| `wt.shrinkage.tolerance` | Ya | Ya | Ya | Ya |
| `wt.receipt.rule` | Ya | Ya | Ya | Ya |
| `wt.api` | Ya | Ya | Ya | Ya |
| `wt.api.request.log` | Ya | Tidak | Tidak | Tidak |
| `wt.division` | Ya | Ya | Ya | Ya |
| `wt.weighing.location` | Ya | Ya | Ya | Ya |
| `wt.foreman` | Ya | Ya | Ya | Ya |
| `wt.tapper` | Ya | Ya | Ya | Ya |
| `wt.device` | Ya | Ya | Ya | Ya |
| `wt.weighing` | Ya | Ya | Ya | Ya |
| `wt.device.state.reason.wizard` | Ya | Ya | Ya | Ya |
| `hr.employee` | Ya | Tidak | Tidak | Tidak |
| `hr.job` | Ya | Tidak | Tidak | Tidak |
| `product.product` | Ya | Tidak | Tidak | Tidak |
| `product.template` | Ya | Tidak | Tidak | Tidak |
| `stock.location` | Ya | Tidak | Tidak | Tidak |
| `stock.picking.type` | Ya | Tidak | Tidak | Tidak |
| `stock.warehouse` | Ya | Tidak | Tidak | Tidak |

## File Utama

Models:

```text
models/estate.py
models/weather.py
models/weather_data.py
models/employee_role.py
models/product.py
models/shrinkage_tolerance.py
models/receipt_rule.py
models/weighing.py
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
services/api_push_weighing_service.py
services/weighing_service.py
services/api_security_service.py
services/api_response_service.py
```

Controllers:

```text
controllers/api/api_handler.py
controllers/api/v1/device_api.py
controllers/api/v1/pull_api.py
controllers/api/v1/push_api.py
```

Views:

```text
views/estate_views.xml
views/weather_views.xml
views/weather_data_views.xml
views/employee_role_views.xml
views/product_views.xml
views/shrinkage_tolerance_views.xml
views/receipt_rule_views.xml
views/inbound_weighing_views.xml
views/weighing_lump_views.xml
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
