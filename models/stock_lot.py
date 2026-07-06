from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        ondelete="restrict",
        index=True,
    )
    production_date = fields.Date(
        string="Production Date",
        index=True,
    )

    wt_location_names = fields.Char(
        string="Lokasi",
        compute="_compute_wt_stock_info",
    )
    wt_total_qty = fields.Float(
        string="Stok (kg)",
        compute="_compute_wt_stock_info",
        digits="Product Unit of Measure",
    )

    def _compute_wt_stock_info(self):
        # Periksa apakah ada filter lokasi di context
        location_id = self.env.context.get("location_id")
        location_ids = []
        if location_id:
            location_ids = self.env["stock.location"].search([("id", "child_of", location_id)]).ids

        for lot in self:
            domain = [
                ("product_id", "=", lot.product_id.id),
                ("lot_id", "=", lot.id),
                ("quantity", ">", 0),
            ]
            if location_ids:
                domain.append(("location_id", "in", location_ids))

            quants = self.env["stock.quant"].search(domain)
            if quants:
                lot.wt_location_names = ", ".join(quants.mapped("location_id.display_name"))
                # Menggunakan Qty Fisik (On Hand) agar sesuai dengan tampilan inventaris
                lot.wt_total_qty = sum(quants.mapped("quantity"))
            else:
                lot.wt_location_names = "Tidak ada stok"
                lot.wt_total_qty = 0.0

    @api.model
    def _search(self, domain, *args, **kwargs):
        location_id = self.env.context.get("location_id")
        if location_id:
            location_ids = self.env["stock.location"].search([("id", "child_of", location_id)]).ids
            quant_domain = [
                ("location_id", "in", location_ids),
                ("quantity", ">", 0),
            ]
            # Ambil product_id dari context atau domain untuk membatasi pencarian quant
            product_id = self.env.context.get("default_product_id")
            if not product_id:
                for term in domain:
                    if isinstance(term, (list, tuple)) and term[0] == "product_id" and term[1] == "=":
                        product_id = term[2]
                        break
            if product_id:
                quant_domain.append(("product_id", "=", product_id))

            quants = self.env["stock.quant"].search(quant_domain)
            lot_ids = quants.mapped("lot_id").ids
            domain = [("id", "in", lot_ids)] + domain

        return super()._search(domain, *args, **kwargs)
