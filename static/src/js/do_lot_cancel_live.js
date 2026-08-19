/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BooleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";

/**
 * WeighTrack – Live update "Status Timbang" saat toggle "Batal" diubah
 * di list editable Rincian Lot pada form Rencana DO.
 *
 * Masalah:
 *   Odoo menyimpan perubahan One2many sebagai command ke parent form.
 *   wt_weighing_status (stored computed + readonly=False) tidak otomatis
 *   ter-recompute secara live di browser — badge baru berubah setelah
 *   parent form di-save dan halaman di-reload.
 *
 * Solusi:
 *   Patch BooleanToggleField.onChange: setelah toggle wt_is_cancelled,
 *   langsung update nilai wt_weighing_status di record in-memory (tanpa
 *   menunggu server). Badge di UI pun langsung berubah.
 *
 *   Saat parent form benar-benar di-save, server juga menyimpan nilai
 *   yang benar via write() override di model Python.
 */

/** Peta: wt_is_cancelled → wt_weighing_status berdasarkan state record */
function resolveWeighingStatus(record, cancelledVal) {
    const isCancelled = cancelledVal !== undefined ? cancelledVal : Boolean(record.data.wt_is_cancelled);
    const isPulled = Boolean(record.data.wt_is_pulled);
    const weighingSource = record.data.wt_weighing_source;
    const qty = record.data.qty || 0;

    if (isCancelled) {
        return "cancelled";
    }
    if ((!isPulled && !weighingSource) || qty <= 0) {
        return "not_pulled";
    }
    if (weighingSource) {
        return "weighed";
    }
    return "unweighed";
}

patch(BooleanToggleField.prototype, {
    async onChange(value) {
        // Panggil onChange asli terlebih dahulu
        await super.onChange(...arguments);

        try {
            // Hanya berlaku untuk field wt_is_cancelled
            if (this.props.name !== "wt_is_cancelled") {
                return;
            }

            const record = this.props.record;
            if (!record) {
                return;
            }

            // Hitung status baru langsung di browser
            const newStatus = resolveWeighingStatus(record, value);

            // Update wt_weighing_status di record in-memory OWL
            // sehingga badge langsung re-render seketika di layar
            await record.update({ wt_weighing_status: newStatus });
        } catch (e) {
            console.warn("[WeighTrack] Live status update gagal:", e);
        }
    },
});
