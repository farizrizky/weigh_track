# Diskusi: Fitur Delivery Plan (Pengiriman Multi-Gudang)

## Pemahaman Alur Saat Ini

```
[Pengiriman] → langsung buat DO (stock.picking) → done
```

## Alur Baru yang Diinginkan

```
[Buat Delivery Plan] → [Proses per gudang: timbang + susut] → [jika multi-gudang: transfer internal + timbang ulang] → [semua selesai] → [Auto-create DO asli = done]
```

---

## Alur Detail (Contoh 2 Gudang)

```
Delivery Plan
├── Gudang 1 (G1): butuh 800kg
│   ├── Pilih lot-lot dari G1/stock
│   ├── Timbang → apply susut → hasil: 750kg (susut 50kg)
│   └── Transfer Internal: G1/stock → G2/stock/transit (750kg)
│
└── Gudang 2 (G2): butuh 200kg
    ├── Ambil dari G2/stock: 200kg
    ├── Ambil dari G2/stock/transit: 750kg (kiriman dari G1)
    ├── Timbang ULANG semuanya (cek apakah ada susut lagi di perjalanan)
    ├── Apply susut → hasil akhir: misal 940kg
    └── DONE → Auto-create DO resmi (total 940kg)
```

---

## Pertanyaan Diskusi

### 1. Mapping Gudang → Lokasi Transit
> Apakah mapping ini sudah ada, atau perlu dibuat model baru?
> Contoh: G1 → G2 menggunakan lokasi `G2/stock/transit`

Opsi:
- **A)** Tambah tabel konfigurasi baru: `wt.warehouse.route` (dari_gudang, ke_gudang, transit_location)
- **B)** Manfaatkan routes/locations yang sudah ada di Odoo (stock.route)

### 2. Model Dokumen Baru (Delivery Plan)
> Apakah ini model baru `wt.delivery.plan`, atau menggunakan model delivery yang sudah ada (`wt.delivery`) dengan penambahan state?

Saat ini model `wt.delivery` seperti apa state-nya? (draft → confirmed → done?)

### 3. Timbang Ulang di Gudang 2
> Barang dari transit G1 → ditimbang ulang di G2 bersama stok G2.
> Apakah timbang ulang ini pakai mekanisme weighing yang sama (`wt.weighing`)?
> Atau terpisah?

### 4. DO Akhir yang Dibuat
> DO akhir yang otomatis dibuat itu:
> - Sumbernya dari gudang mana? G2 (gudang terakhir)? Atau langsung dari semua gudang?
> - Tujuannya ke customer/vendor/lokasi tertentu?
> - Apakah lotnya ikut ke DO akhir?

### 5. Sampai 3 Gudang
> Jika 3 gudang, apakah alurnya:
> G1 → transfer ke G2/transit → G2 timbang → transfer ke G3/transit → G3 timbang → DO?
> Atau G1 dan G2 langsung ke G3 secara paralel?

---

## Usulan Model Data (Draft)

### `wt.delivery.plan` (Header)
| Field | Tipe | Keterangan |
|---|---|---|
| name | Char | Nomor dokumen |
| customer_id | Many2one | Customer tujuan |
| requested_qty | Float | Total kebutuhan |
| state | Selection | draft / in_progress / done |
| delivery_id | Many2one | DO yang dibuat otomatis di akhir |
| warehouse_line_ids | One2many | Baris per gudang |

### `wt.delivery.plan.warehouse` (Per Gudang)
| Field | Tipe | Keterangan |
|---|---|---|
| plan_id | Many2one | Header |
| warehouse_id | Many2one | Sumber gudang |
| sequence | Integer | Urutan (G1=1, G2=2, G3=3) |
| transit_location_id | Many2one | Lokasi transit tujuan |
| requested_qty | Float | Kebutuhan dari gudang ini |
| weighing_ids | One2many | Timbangan dari gudang ini |
| internal_picking_id | Many2one | Transfer internal yang dibuat |
| net_qty_after_shrinkage | Float | Hasil setelah susut |
| state | Selection | pending / weighing / transferred / done |

---

## Open Questions Sebelum Coding

> [!IMPORTANT]
> Jawab pertanyaan ini dulu sebelum kita mulai implementasi:

1. **Mapping transit**: pakai konfigurasi baru atau ikut Odoo routes?
2. **State delivery plan**: apa saja state-nya?
3. **DO akhir**: sumbernya dari gudang mana, dan ke mana tujuannya?
4. **3 gudang**: alurnya paralel atau serial (berantai)?
5. **Model delivery yang ada sekarang** (`wt.delivery`): apakah tetap dipakai atau diganti sepenuhnya dengan yang baru?
