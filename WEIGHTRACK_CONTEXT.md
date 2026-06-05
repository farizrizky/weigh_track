# WeighTrack Development Context

## Project

WeighTrack adalah custom module Odoo 19 untuk aplikasi penimbangan estate. Module berada di:

```text
/opt/odoo/custom-addons/weightrack
```

Di Windows/SSHFS workspace terlihat sebagai:

```text
i:/odoo/custom-addons/weightrack
```

## Current Scope

Scope saat ini masih master data awal. Module baru menyediakan satu role aplikasi:

```text
Administrator
```

Role ini punya akses CRUD ke semua model WeighTrack yang sudah dibuat.

## Important Conventions

- Semua model WeighTrack memakai prefix teknis `wt.`.
- Nama teknis model/field memakai bahasa Inggris.
- Label UI boleh mengikuti bahasa operasional/lapangan melalui file translasi.
- Semua model master yang dibuat sejauh ini memakai chatter:
  - `_inherit = ["mail.thread", "mail.activity.mixin"]`
  - field penting memakai `tracking=True`
  - form view memakai `<chatter/>`
- Field `name` pada form dibuat sebagai title besar menggunakan `oe_title`.
- Akses module dibatasi dengan group `weightrack.group_admin`.
- Jangan buat role aplikasi lain dulu. Untuk saat ini hanya Administrator.
- Role employee operasional diatur lewat `wt.employee.role.mapping` berdasarkan company, role, dan job position.
- Jika menambah file baru, pastikan service Odoo bisa membaca file tersebut. Di environment ini file baru kadang butuh permission:

```bash
icacls custom-addons\weightrack\<path-file> /grant Everyone:RX
```

Atau dari server Linux:

```bash
sudo chmod -R u+rwX,go+rX /opt/odoo/custom-addons/weightrack
```

## Existing Models

Model yang sudah dibuat:

- `wt.estate`
- `wt.employee.role.mapping`
- `wt.division`
- `wt.weighing.location`
- `wt.foreman`
- `wt.tapper`

Catatan rename:

- Istilah lama `Supervisor` sudah diganti menjadi `Foreman`.
- Model teknis lama `wt.supervisor` sudah diganti menjadi `wt.foreman`.
- Field relasi Tapper lama `supervisor_id` sudah diganti menjadi `foreman_id`.
- Istilah lama `Krani` di Division sudah diganti menjadi `Clerk`.
- Field Division lama `krani_id` sudah diganti menjadi `clerk_id`.
- Role employee mapping lama `krani` sudah diganti menjadi `clerk`.
- Karena perubahan ini rename teknis, bila data lama masih ada sebaiknya data/module lama dibersihkan dulu sebelum install ulang atau upgrade.

## Menu Structure

```text
WeighTrack
`-- Master Data
    |-- Estates
    |-- Employee Role Mappings
    |-- Divisions
    |-- Weighing Locations
    |-- Foremen
    `-- Tappers
```

## Data Design Notes

- `Division` wajib terhubung ke `Estate`.
- `Weighing Location` wajib terhubung ke `Estate` dan `Warehouse`.
- `company_id` pada `Division` dan `Weighing Location` otomatis mengikuti `estate_id.company_id`.
- Pengaturan divisi yang boleh menimbang hanya dilakukan dari `Weighing Location`, melalui field `allowed_division_ids`.
- `Division` tidak perlu menampilkan atau mengatur relasi balik ke `Weighing Location`.
- `warehouse_id` memakai model Odoo bawaan `stock.warehouse`, sehingga module bergantung pada `stock`.
- `employee_id` pada Foreman memakai model Odoo bawaan `hr.employee`, sehingga module bergantung pada `hr`.
- `clerk_id`, `operator_id`, dan Foreman `employee_id` memakai model Odoo bawaan `hr.employee`.
- `wt.employee.role.mapping` menentukan job position yang boleh dipilih untuk role `operator`, `clerk`, `foreman`, dan `tapper`.
- `wt.employee.role.mapping` menjadi sumber domain employee dan validasi company/job position untuk Clerk, Operator, Foreman, dan Tapper.
- Foreman wajib terhubung ke Division.
- Foreman employee harus valid berdasarkan company dan job position pada role mapping `foreman`.
- Tapper wajib terhubung ke Division.
- Foreman pada Tapper bersifat opsional, tetapi jika diisi harus berasal dari Division yang sama.
- Satu Foreman bisa memiliki banyak Tapper.
- Satu Tapper employee hanya boleh memiliki satu record Tapper.
- Tapper `company_id` otomatis mengikuti Division.

## Localization Notes

- File translasi bahasa Indonesia berada di `i18n/id_ID.po`.
- File translasi dirapikan dengan pemisah per bagian:
  - `Common / Shared`
  - `Estate`
  - `Division`
  - `Employee Role Mapping`
  - `Weighing Location`
  - `Foreman`
  - `Tapper`
  - `Validation Messages`
- Translasi yang sudah dibuat termasuk:
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
  - `Allowed Clerk Employees` -> `Karyawan Kerani yang Diizinkan`
  - `Foreman` -> `Mandor`
  - `Foremen` -> `Mandor`
  - `Allowed Foreman Employees` -> `Karyawan Mandor yang Diizinkan`
  - `Operator` -> `Operator`
  - `Tapper` / `Tappers` -> `Tapper`
  - `Without Foreman` -> `Tanpa Mandor`
- File `.po` perlu di-load/import ke Odoo agar tampil di UI, misalnya lewat menu import translation atau upgrade module dengan load language yang sesuai.
- Pesan validasi Python yang perlu diterjemahkan harus dibungkus dengan `_()` di kode Python.
- Setelah perapihan terbaru, `i18n/id_ID.po` tidak memiliki duplicate `msgid`.

## Upgrade Notes

Setelah perubahan Python, restart Odoo:

```bash
sudo systemctl restart odoo
```

Setelah perubahan XML/security/data, upgrade module `WeighTrack` dari Apps.

Untuk rename teknis besar seperti `Supervisor` -> `Foreman` dan `Krani` -> `Clerk`, alur paling bersih adalah hapus data lama atau uninstall module lama dulu, lalu install/upgrade `WeighTrack`. Ini menghindari metadata lama seperti action, view, field, atau menu lama tertinggal di database Odoo.

## Known Environment Notes

- Parent git di `/opt/odoo/custom-addons` pernah dinonaktifkan dengan rename `.git` menjadi `.git-disabled-custom-addons`.
- Git yang dipakai seharusnya hanya repo module:

```text
/opt/odoo/custom-addons/weightrack
```

- Push ke GitHub dari server pernah gagal karena SSH key GitHub belum terpasang di server.
