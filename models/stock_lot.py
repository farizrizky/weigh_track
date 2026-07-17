from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    wt_lot_type = fields.Selection(
        [
            ("production", "Production"),
            ("transit", "Transit"),
            ("warehouse_stock", "Warehouse Stock"),
        ],
        string="WeighTrack Lot Type",
        default="production",
        required=True,
        index=True,
    )
    wt_transit_state = fields.Selection(
        [
            ("open", "Open"),
            ("closed", "Closed"),
        ],
        string="Transit Status",
        index=True,
    )
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
    wt_receiving_location_id = fields.Many2one(
        "stock.location",
        string="Receiving Location",
        ondelete="restrict",
        index=True,
        help="Destination location that defines the production batch lot in WeighTrack.",
    )
    wt_source_delivery_id = fields.Many2one(
        "wt.delivery",
        string="Source Delivery",
        readonly=True,
        copy=False,
        index=True,
    )
    wt_source_picking_id = fields.Many2one(
        "stock.picking",
        string="Source Picking",
        readonly=True,
        copy=False,
        index=True,
    )
    wt_transit_date = fields.Date(
        string="Transit Date",
        readonly=True,
        copy=False,
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

    def init(self):
        super().init()
        self.env.cr.execute(
            """
            DO $$
            BEGIN
                IF to_regclass('stock_lot') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'stock_lot'
                        AND column_name = 'wt_lot_type'
                ) THEN
                    UPDATE stock_lot
                    SET wt_lot_type = 'production'
                    WHERE wt_lot_type IS NULL;
                END IF;

                IF to_regclass('stock_lot') IS NOT NULL
                AND to_regclass('stock_move_line') IS NOT NULL
                AND to_regclass('stock_picking') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'stock_lot'
                        AND column_name = 'wt_receiving_location_id'
                )
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'stock_picking'
                        AND column_name = 'production_receipt_id'
                ) THEN
                    UPDATE stock_lot AS lot
                    SET wt_receiving_location_id = receipt_line.location_dest_id
                    FROM (
                        SELECT DISTINCT ON (move_line.lot_id)
                            move_line.lot_id,
                            move_line.location_dest_id
                        FROM stock_move_line AS move_line
                        JOIN stock_picking AS picking
                            ON picking.id = move_line.picking_id
                        WHERE picking.production_receipt_id IS NOT NULL
                            AND move_line.lot_id IS NOT NULL
                            AND move_line.location_dest_id IS NOT NULL
                        ORDER BY move_line.lot_id, move_line.id
                    ) AS receipt_line
                    WHERE receipt_line.lot_id = lot.id
                        AND lot.wt_receiving_location_id IS NULL;
                END IF;
            END $$;
            """
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
