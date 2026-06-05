# WeighTrack Model Reference

Dokumen ini menjelaskan model WeighTrack yang sudah dibuat, field utama, relasi, dan aturan validasinya.

## Global Rules

- Semua model master aktif memakai chatter Odoo:
  - `mail.thread`
  - `mail.activity.mixin`
- Field penting diberi `tracking=True`, sehingga perubahan tercatat di chatter.
- Akses CRUD saat ini hanya diberikan ke group `weightrack.group_admin`.
- Nama teknis model/field memakai bahasa Inggris.
- Label bahasa Indonesia dikelola lewat file translasi `i18n/id_ID.po`.
- Istilah UI penting:
  - `Foreman` / `Foremen` diterjemahkan menjadi `Mandor`.
  - `Clerk` diterjemahkan menjadi `Kerani`.
- File translasi `i18n/id_ID.po` dirapikan dengan pemisah: Common / Shared, Estate, Division, Employee Role Mapping, Weighing Location, Foreman, Tapper, dan Validation Messages.

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
| `name` | `Char` | Ya | Ya | Nama estate. Ditampilkan besar di form. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company pemilik estate. Default mengikuti company user aktif. |
Urutan data:

```text
code, name
```

Validasi:

- `code` wajib unik per `company_id`.
- Constraint database:

```text
unique(code, company_id)
```

- Constraint Python:

```text
Estate code must be unique per company.
```

## Employee Role Mapping

Model teknis:

```text
wt.employee.role.mapping
```

Deskripsi:

Employee Role Mapping adalah konfigurasi job position karyawan yang boleh dipakai untuk role operasional WeighTrack. Mapping ini dipakai sebagai sumber domain dan validasi untuk Clerk, Operator, Foreman, dan Tapper.

Field:

| Field | Type | Required | Tracking | Keterangan |
| --- | --- | --- | --- | --- |
| `name` | `Char` | Otomatis | Tidak | Computed name dari company, role, dan job position. |
| `company_id` | `Many2one(res.company)` | Ya | Ya | Company tempat mapping berlaku. Default mengikuti company user aktif. |
| `role` | `Selection` | Ya | Ya | Role operasional: `operator`, `clerk`, `foreman`, `tapper`. |
| `job_id` | `Many2one(hr.job)` | Ya | Ya | Job position yang diizinkan untuk role tersebut. Domain berdasarkan company mapping atau job position tanpa company. |

Urutan data:

```text
company_id, role
```

Validasi:

- Kombinasi `company_id`, `role`, dan `job_id` wajib unik.
- `job_id` wajib dipilih.
- Jika `job_id` punya company, company job position harus sama dengan `company_id` mapping.
- Helper `check_employee_allowed()` dipakai oleh model lain untuk memastikan employee:
  - berada di company yang sama dengan record operasional;
  - punya job position yang termasuk mapping role tersebut;
  - memiliki konfigurasi mapping role untuk company terkait.

Constraint database:

```text
unique(company_id, role, job_id)
```

Pesan validasi utama:

```text
Job position must be selected.
Job position must belong to the same company as the mapping.
Employee role mapping must be unique per company, role, and job position.
%s employee must belong to the same company.
%s role mapping has not been configured for this company.
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
| `name` | `Char` | Ya | Ya | Nama divisi. Ditampilkan besar di form. |
| `estate_id` | `Many2one(wt.estate)` | Ya | Ya | Estate tempat divisi berada. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related field dari `estate_id.company_id`, `store=True`, readonly. |
| `clerk_id` | `Many2one(hr.employee)` | Tidak | Ya | Employee yang berperan sebagai Clerk/Kerani untuk divisi. Domain berdasarkan role mapping `clerk`. |
| `allowed_clerk_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Clerk berdasarkan company dan role mapping. |
Urutan data:

```text
estate_id, code, name
```

Validasi:

- `code` wajib unik per `estate_id`.
- Constraint database:

```text
unique(code, estate_id)
```

- Constraint Python:

```text
Division code must be unique per estate.
```

- Clerk harus valid menurut role mapping `clerk` pada company division.
- Constraint Python:

```text
%s employee must belong to the same company.
%s role mapping has not been configured for this company.
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
| `name` | `Char` | Ya | Ya | Nama lokasi timbang. Ditampilkan besar di form. |
| `estate_id` | `Many2one(wt.estate)` | Ya | Ya | Estate lokasi timbang. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related field dari `estate_id.company_id`, `store=True`, readonly. |
| `warehouse_id` | `Many2one(stock.warehouse)` | Ya | Ya | Warehouse Odoo yang terkait lokasi timbang. `ondelete="restrict"`. |
| `operator_id` | `Many2one(hr.employee)` | Tidak | Ya | Employee operator lokasi timbang. Domain berdasarkan role mapping `operator`. |
| `allowed_operator_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Operator berdasarkan company dan role mapping. |
| `allowed_division_ids` | `Many2many(wt.division)` | Tidak | Ya | Daftar divisi yang diizinkan menimbang di lokasi ini. |
Urutan data:

```text
estate_id, code, name
```

Validasi:

- `code` wajib unik per `estate_id`.
- Constraint database:

```text
unique(code, estate_id)
```

- Constraint Python:

```text
Weighing location code must be unique per estate.
```

- Semua `allowed_division_ids` harus berasal dari estate yang sama dengan `estate_id` lokasi timbang.
- Constraint Python:

```text
Allowed divisions must belong to the same estate as the weighing location.
```

- Operator harus valid menurut role mapping `operator` pada company lokasi timbang.
- Constraint Python:

```text
%s employee must belong to the same company.
%s role mapping has not been configured for this company.
%s employee must use an allowed job position for this company.
```

Domain UI:

- `warehouse_id` difilter berdasarkan company lokasi:

```text
[('company_id', '=', company_id)]
```

- `allowed_division_ids` difilter berdasarkan estate lokasi:

```text
[('estate_id', '=', estate_id)]
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
| `name` | `Char` | Otomatis | Tidak | Related field dari `employee_id.name`, dipakai sebagai nama record. |
| `employee_id` | `Many2one(hr.employee)` | Ya | Ya | Employee yang menjadi Foreman/Mandor. Domain berdasarkan role mapping `foreman`. `ondelete="restrict"`. |
| `division_id` | `Many2one(wt.division)` | Ya | Ya | Division tempat foreman bertugas. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related field dari `division_id.company_id`, `store=True`, readonly. |
| `tapper_ids` | `One2many(wt.tapper)` | Tidak | Tidak | Daftar Tapper yang dibawahi Foreman. |
| `allowed_foreman_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Foreman berdasarkan company dan role mapping. |
Urutan data:

```text
division_id, employee_id
```

Validasi:

- Kombinasi `employee_id` dan `division_id` wajib unik.
- Constraint database:

```text
unique(employee_id, division_id)
```

- Employee foreman harus valid menurut role mapping `foreman` pada company division.
- Duplikat kombinasi `employee_id` dan `division_id` dicegah oleh SQL constraint dan Python constraint.
- Tapper bisa dikelola langsung dari form Foreman melalui line `Tappers`.
- Constraint Python:

```text
Foreman employee must be unique per division.
%s employee must belong to the same company.
%s role mapping has not been configured for this company.
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
| `name` | `Char` | Otomatis | Tidak | Related field dari `employee_id.name`, dipakai sebagai nama record. |
| `employee_id` | `Many2one(hr.employee)` | Ya | Ya | Employee yang menjadi Tapper. Domain berdasarkan role mapping `tapper`. `ondelete="restrict"`. |
| `division_id` | `Many2one(wt.division)` | Ya | Ya | Division tempat Tapper berada. `ondelete="restrict"`. |
| `foreman_id` | `Many2one(wt.foreman)` | Tidak | Ya | Foreman/Mandor yang membawahi Tapper. Difilter berdasarkan division. `ondelete="restrict"`. |
| `company_id` | `Many2one(res.company)` | Otomatis | Tidak | Related field dari `division_id.company_id`, `store=True`, readonly. |
| `allowed_tapper_employee_ids` | `Many2many(hr.employee)` | Otomatis | Tidak | Computed helper untuk membatasi pilihan Tapper berdasarkan company dan role mapping. |

Urutan data:

```text
division_id, foreman_id, employee_id
```

Validasi:

- Satu Tapper employee hanya boleh dibuat satu kali.
- Employee Tapper harus valid menurut role mapping `tapper` pada company division.
- Jika `foreman_id` diisi, Foreman harus berada pada division yang sama dengan Tapper.
- Constraint database:

```text
unique(employee_id)
```

- Constraint Python:

```text
Tapper employee must be unique.
Tapper and foreman must belong to the same division.
%s employee must belong to the same company.
%s role mapping has not been configured for this company.
%s employee must use an allowed job position for this company.
```

Aturan bisnis:

- Satu Foreman bisa memiliki banyak Tapper.
- Satu Tapper employee hanya boleh memiliki satu record Tapper.
- Division Tapper dipilih langsung.
- Company Tapper otomatis mengikuti Division.
- Foreman Tapper harus berasal dari Division yang sama.

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
| `wt.employee.role.mapping` | Ya | Ya | Ya | Ya |
| `wt.division` | Ya | Ya | Ya | Ya |
| `wt.weighing.location` | Ya | Ya | Ya | Ya |
| `wt.foreman` | Ya | Ya | Ya | Ya |
| `wt.tapper` | Ya | Ya | Ya | Ya |
