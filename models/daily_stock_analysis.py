# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DailyStockAnalysis(models.Model):
    _name = "wt.daily.stock.analysis"
    _description = "Daily Stock Analysis"
    _order = "report_date desc, estate_id, division_id, scope_name"

    name = fields.Char(string="Nama", required=True, readonly=True)
    report_date = fields.Date(
        string="Tanggal",
        required=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        readonly=True,
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Produk",
        readonly=True,
        index=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        readonly=True,
        index=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        readonly=True,
        index=True,
    )
    scope_key = fields.Char(required=True, readonly=True, index=True)
    scope_name = fields.Char(string="Lingkup", required=True, readonly=True)
    scope_type = fields.Selection(
        [
            ("division", "Divisi"),
            ("unassigned", "Tanpa Divisi"),
        ],
        string="Tipe Lingkup",
        required=True,
        readonly=True,
        index=True,
    )
    opening_stock = fields.Float(string="Stock Awal", readonly=True)
    weighing_qty = fields.Float(string="Total Penimbangan", readonly=True)
    sales_qty = fields.Float(string="Total Penjualan", readonly=True)
    storage_shrinkage_qty = fields.Float(
        string="Susut Penyimpanan",
        readonly=True,
    )
    transfer_shrinkage_qty = fields.Float(
        string="Susut Transfer",
        readonly=True,
    )
    total_shrinkage_qty = fields.Float(string="Total Susut", readonly=True)
    closing_stock = fields.Float(string="Saldo Akhir", readonly=True)
    balance_difference = fields.Float(
        string="Selisih Rekonsiliasi",
        readonly=True,
    )
    computed_at = fields.Datetime(
        string="Dihitung Pada",
        required=True,
        readonly=True,
    )

    _company_date_scope_uniq = models.Constraint(
        "unique(company_id, report_date, scope_key)",
        "Data analitik stock harian harus unik per perusahaan, tanggal, dan lingkup.",
    )

    @api.model
    def _cron_refresh_today(self):
        today = fields.Date.context_today(self)
        service = self.env["wt.daily.stock.analysis.service"]
        for company in self.env["res.company"].search([]):
            if self.env["wt.product"].get_active_product(company):
                service.refresh_range(company, today, today)
