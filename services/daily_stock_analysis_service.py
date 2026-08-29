# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DailyStockAnalysisService(models.AbstractModel):
    _name = "wt.daily.stock.analysis.service"
    _description = "Daily Stock Analysis Service"

    @api.model
    def calculate(self, company, report_date):
        company = company.exists()
        report_date = fields.Date.to_date(report_date)
        if not company or not report_date:
            raise ValidationError(_("Perusahaan dan tanggal laporan wajib diisi."))

        calculator = self.env["wt.daily.stock.report.wizard"].new(
            {
                "company_id": company.id,
                "report_date": report_date,
            }
        )
        return calculator._prepare_report_data()

    @api.model
    def refresh_range(self, company, start_date, end_date):
        company = company.exists()
        start_date = fields.Date.to_date(start_date)
        end_date = fields.Date.to_date(end_date)
        if not company or not start_date or not end_date:
            raise ValidationError(_("Perusahaan dan rentang tanggal wajib diisi."))
        if start_date > end_date:
            raise ValidationError(
                _("Tanggal mulai tidak boleh lebih besar dari tanggal selesai.")
            )

        analysis_model = self.env["wt.daily.stock.analysis"].sudo()
        refreshed = analysis_model
        current_date = start_date
        while current_date <= end_date:
            data = self.calculate(company, current_date)
            values = self._prepare_analysis_values(
                company,
                current_date,
                data,
            )
            analysis_model.search(
                [
                    ("company_id", "=", company.id),
                    ("report_date", "=", current_date),
                ]
            ).unlink()
            if values:
                refreshed |= analysis_model.create(values)
            current_date += timedelta(days=1)
        return refreshed

    @api.model
    def _prepare_analysis_values(self, company, report_date, data):
        metrics = data.get("analysis_values", {})
        product = self.env["product.product"].browse(data.get("product_id")).exists()
        divisions = self.env["wt.division"].with_context(active_test=False).search(
            [("company_id", "=", company.id)],
            order="code, name",
        )
        estates = self.env["wt.estate"].with_context(active_test=False).search(
            [("company_id", "=", company.id)],
            order="code, name",
        )

        values = []
        computed_at = fields.Datetime.now()
        for division in divisions:
            row_metrics = self._metrics_for_key(
                metrics,
                "division:%s" % division.id,
            )
            if self._has_metrics(row_metrics):
                values.append(
                    self._analysis_row_values(
                        company,
                        product,
                        report_date,
                        computed_at,
                        "division:%s" % division.id,
                        division.code or division.name,
                        "division",
                        division.estate_id,
                        division,
                        row_metrics,
                    )
                )

        for estate in estates:
            estate_metrics = self._metrics_for_key(
                metrics,
                "estate:%s" % estate.id,
            )
            division_metrics = {
                metric: sum(
                    metrics.get(metric, {}).get("division:%s" % division.id, 0.0)
                    for division in divisions
                    if division.estate_id == estate
                )
                for metric in metrics
            }
            residual_metrics = {
                metric: estate_metrics.get(metric, 0.0)
                - division_metrics.get(metric, 0.0)
                for metric in metrics
            }
            if self._has_metrics(residual_metrics):
                values.append(
                    self._analysis_row_values(
                        company,
                        product,
                        report_date,
                        computed_at,
                        "estate:%s:unassigned" % estate.id,
                        _("Transit / Tanpa Divisi"),
                        "unassigned",
                        estate,
                        self.env["wt.division"],
                        residual_metrics,
                    )
                )

        estate_totals = {
            metric: sum(
                metrics.get(metric, {}).get("estate:%s" % estate.id, 0.0)
                for estate in estates
            )
            for metric in metrics
        }
        unassigned_metrics = {
            metric: metrics.get(metric, {}).get("total", 0.0)
            - estate_totals.get(metric, 0.0)
            for metric in metrics
        }
        if self._has_metrics(unassigned_metrics):
            values.append(
                self._analysis_row_values(
                    company,
                    product,
                    report_date,
                    computed_at,
                    "company:unassigned",
                    _("Tanpa Estate / Divisi"),
                    "unassigned",
                    self.env["wt.estate"],
                    self.env["wt.division"],
                    unassigned_metrics,
                )
            )
        return values

    @api.model
    def _metrics_for_key(self, metrics, key):
        return {
            metric: values.get(key, 0.0)
            for metric, values in metrics.items()
        }

    @api.model
    def _has_metrics(self, metrics):
        return any(abs(value or 0.0) > 0.000001 for value in metrics.values())

    @api.model
    def _analysis_row_values(
        self,
        company,
        product,
        report_date,
        computed_at,
        scope_key,
        scope_name,
        scope_type,
        estate,
        division,
        metrics,
    ):
        opening_stock = metrics.get("opening_stock", 0.0)
        weighing_qty = metrics.get("weighing_qty", 0.0)
        sales_qty = metrics.get("sales_qty", 0.0)
        storage_shrinkage_qty = metrics.get("storage_shrinkage_qty", 0.0)
        transfer_shrinkage_qty = 0.0
        total_shrinkage_qty = storage_shrinkage_qty
        closing_stock = metrics.get("closing_stock", 0.0)
        return {
            "name": "%s - %s" % (report_date, scope_name),
            "report_date": report_date,
            "company_id": company.id,
            "product_id": product.id or False,
            "estate_id": estate.id or False,
            "division_id": division.id or False,
            "scope_key": scope_key,
            "scope_name": scope_name,
            "scope_type": scope_type,
            "opening_stock": opening_stock,
            "weighing_qty": weighing_qty,
            "sales_qty": sales_qty,
            "storage_shrinkage_qty": storage_shrinkage_qty,
            "transfer_shrinkage_qty": transfer_shrinkage_qty,
            "total_shrinkage_qty": total_shrinkage_qty,
            "closing_stock": closing_stock,
            "balance_difference": (
                opening_stock
                + weighing_qty
                - sales_qty
                - total_shrinkage_qty
                - closing_stock
            ),
            "computed_at": computed_at,
        }
