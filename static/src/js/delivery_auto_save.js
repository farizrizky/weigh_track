/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";

/**
 * WeighTrack – Auto-save Delivery Header saat baris Rencana DO diklik.
 *
 * Mengapa ini dibutuhkan:
 * Ketika user membuat Tugas Pengiriman baru dan memilih Rute, baris Rencana DO
 * terbentuk sebagai record virtual (belum tersimpan di DB).
 * Jika user mengklik baris tersebut:
 *   - Modal dialog terbuka dalam mode "Create" (dengan tombol Simpan & Tutup, Simpan & Buat Baru, Buang).
 *   - Setiap aksi di dalam modal (mis. Muat Lot) atau saat klik Simpan & Tutup akan
 *     memicu auto-save ganda dan menyebabkan duplikasi baris serta error OWL Lifecycle.
 *
 * Solusi:
 * Intercept X2ManyField.openRecord untuk field `do_line_ids` pada model `wt.delivery`.
 * Jika header delivery masih baru (isNew === true), lakukan `parentRecord.save({ stayInEdition: true })`
 * terlebih dahulu SEBELUM membuka modal.
 *
 * Dengan demikian:
 *   1. Delivery otomatis tersimpan di database dan mendapatkan No. DO (mis. DO/20260818/000038).
 *   2. Baris Rencana DO di database mendapatkan ID nyata.
 *   3. Modal terbuka dalam mode "Edit" (hanya ada tombol Simpan & Buang).
 *   4. Tidak ada duplikasi baris dan tidak ada error OWL.
 */
patch(X2ManyField.prototype, {
    async openRecord(record) {
        const parentRecord = this.props.record;

        if (
            this.props.name === "do_line_ids" &&
            parentRecord?.resModel === "wt.delivery" &&
            parentRecord.isNew
        ) {
            try {
                // Catat indeks baris yang diklik sebelum save
                const currentList = this.list?.records || parentRecord.data?.do_line_ids?.records || [];
                const clickedIndex = record ? currentList.indexOf(record) : 0;

                // Simpan header delivery terlebih dahulu
                const saved = await parentRecord.save({ stayInEdition: true });

                if (saved !== false) {
                    // Ambil list baris yang sudah tersimpan di database (dengan ID nyata)
                    const updatedList = this.list?.records || parentRecord.data?.do_line_ids?.records || [];
                    const targetRecord = (clickedIndex >= 0 && updatedList[clickedIndex])
                        ? updatedList[clickedIndex]
                        : updatedList[0];

                    if (targetRecord) {
                        return await super.openRecord(targetRecord);
                    }
                }
            } catch (err) {
                console.error("[WeighTrack] Gagal auto-save delivery sebelum buka modal DO Line:", err);
            }
        }

        return await super.openRecord(...arguments);
    },
});
