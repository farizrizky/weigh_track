from datetime import date, datetime

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class DailyStockReportCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].set_param("ir_attachment.location", "db")
        cls.company = cls.env["res.company"].create({"name": "Daily Stock Transit QA"})
        cls.env = cls.env(context={**cls.env.context, "allowed_company_ids": [cls.company.id], "tz": "UTC", "lang": "en_US"})
        cls.estates = cls.env["wt.estate"].create([
            {"name": name, "code": code, "company_id": cls.company.id}
            for name, code in (("Source Estate", "DST-SRC"), ("Transit Estate", "DST-TR"))
        ])
        cls.divisions = cls.env["wt.division"].create([
            {"name": "Source %s" % index, "code": "DST-%s" % index, "estate_id": estate.id}
            for index, estate in enumerate(cls.estates, 1)
        ])
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create({"name": "Transit QA", "code": "DSTQ", "company_id": cls.company.id})
        cls.warehouse.estate_id = cls.estates[0]
        cls.product = cls.env["product.product"].create({
            "name": "Daily Stock QA Product", "is_storable": True,
            "tracking": "lot", "company_id": cls.company.id,
        })
        cls.env["wt.product"].create({"company_id": cls.company.id, "product_id": cls.product.id})
        cls.transit_location = cls.env["stock.location"].create({
            "name": "Transit QA", "usage": "transit", "company_id": cls.company.id,
            "location_id": cls.warehouse.view_location_id.id,
        })
        cls.supply = cls.env["stock.location"].create({"name": "QA Production", "usage": "production", "company_id": cls.company.id})
        cls.loss = cls.env["stock.location"].create({
            "name": "QA Shrinkage", "usage": "inventory", "company_id": cls.company.id,
            "location_id": cls.env.ref("weightrack.stock_location_wt_inventory_loss_susut").id,
        })
        cls.customer = cls.env.ref("stock.stock_location_customers")
        cls.product.with_company(cls.company).property_stock_inventory = cls.loss
        cls.lots = cls.env["stock.lot"].create([
            {"name": "DST-SOURCE-%s" % index, "product_id": cls.product.id,
             "company_id": cls.company.id, "division_id": division.id, "wt_lot_type": "production"}
            for index, division in enumerate(cls.divisions, 1)
        ])

    def _move(self, quantity, lot, source, destination, day, picking=None, description=None):
        values = {
            "company_id": self.company.id, "product_id": self.product.id,
            "product_uom": self.product.uom_id.id, "product_uom_qty": quantity,
            "location_id": source.id, "location_dest_id": destination.id, "picked": True,
            "move_line_ids": [(0, 0, {
                "company_id": self.company.id, "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id, "lot_id": lot.id,
                "quantity": quantity, "location_id": source.id, "location_dest_id": destination.id,
            })],
        }
        if picking:
            values["picking_id"] = picking.id
            values["move_line_ids"][0][2]["picking_id"] = picking.id
        if description:
            values["description_picking"] = description
        move = self.env["stock.move"].create(values)
        move._action_done()
        movement_date = datetime(2020, 2, day, 12) if day else datetime(2020, 1, 31, 12)
        move.write({"date": movement_date})
        move.move_line_ids.write({"date": movement_date})
        return move

    def _transit(self):
        for quantity, lot in zip((600, 400), self.lots):
            self._move(quantity, lot, self.supply, self.warehouse.lot_stock_id, 0)
        picking = self.env["stock.picking"].create({
            "company_id": self.company.id, "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.warehouse.lot_stock_id.id, "location_dest_id": self.transit_location.id,
        })
        for quantity, lot in zip((600, 400), self.lots):
            self._move(quantity, lot, self.warehouse.lot_stock_id, self.loss, 1, picking,
                       "Consume old lots for transit merge - QA")
        transit_lot = self.env["stock.lot"].create({
            "name": "DST-TRANSIT", "product_id": self.product.id, "company_id": self.company.id,
            "wt_lot_type": "transit", "wt_source_picking_id": picking.id,
        })
        self._move(1000, transit_lot, self.loss, self.transit_location, 1, picking,
                   "Produce new merged lot for transit - QA")
        return transit_lot

    def _report(self, day, month=2):
        wizard = self.env["wt.daily.stock.report.wizard"].new({"company_id": self.company.id, "report_date": date(2020, month, day)})
        return wizard._prepare_report_data()

    def _manual_loss(self, lot, amounts, day=2, saved=True):
        route = self.env["wt.delivery.route"].create({
            "name": "QA Manual Transit", "company_id": self.company.id,
            "line_ids": [(0, 0, {
                "sequence": 1, "route_type": "transit", "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.warehouse.lot_stock_id.id, "location_dest_id": self.transit_location.id,
            }), (0, 0, {
                "sequence": 2, "route_type": "outgoing", "picking_type_id": self.warehouse.out_type_id.id,
                "location_id": self.transit_location.id, "location_dest_id": self.customer.id,
            })],
        })
        delivery = self.env["wt.delivery"].create({"company_id": self.company.id, "state": "delivered", "route_id": route.id})
        source_line, outgoing_line = delivery.do_line_ids.sorted("sequence")
        source_line.generated_transit_lot_id = lot
        for source_lot, physical, amount in zip(self.lots, (600, 400), amounts):
            source_lot_line = self.env["wt.delivery.do.line.lot"].create({
                "do_line_id": source_line.id, "lot_id": source_lot.id, "qty": physical,
                "wt_physical_qty": physical, "wt_weighing_source": "manual",
            })
            self.env["wt.delivery.transit.shrinkage.proportion"].create({
                "delivery_id": delivery.id, "do_lot_line_id": source_lot_line.id,
                "proportion_qty": amount,
            })
        total = sum(amounts)
        outgoing_lot = self.env["wt.delivery.do.line.lot"].create({
            "do_line_id": outgoing_line.id, "lot_id": lot.id, "qty": 1000,
            "wt_physical_qty": 1000 - total, "wt_weighing_source": "manual",
        })
        reason = self.env["wt.stock.opname.difference.reason"].create({
            "name": "QA Transit Shrinkage", "code": "QA-TRANSIT", "difference_type": "susut", "location_dest_id": self.loss.id,
        })
        self.env["wt.delivery.line.allocation"].create({
            "do_lot_line_id": outgoing_lot.id, "reason_id": reason.id,
            "qty": total, "location_dest_id": self.loss.id,
        })
        move = self._move(total, lot, self.transit_location, self.loss, day)
        move.write({"wt_delivery_id": delivery.id, "wt_delivery_do_line_id": outgoing_line.id})
        if saved:
            delivery.action_save_transit_proportion()
        return delivery, move

    def _assert_balanced_scopes(self, data):
        metrics = data["analysis_values"]
        for scope in {key for values in metrics.values() for key in values}:
            with self.subTest(scope=scope):
                balance = sum(sign * metrics[name].get(scope, 0) for name, sign in (
                    ("opening_stock", 1), ("weighing_qty", 1), ("sales_qty", -1),
                    ("storage_shrinkage_qty", -1), ("closing_stock", -1),
                ))
                self.assertAlmostEqual(balance, 0)
        self.assertAlmostEqual(data["balance_difference"], 0)


@tagged("post_install", "-at_install")
class TestDailyStockReport(DailyStockReportCase):
    def test_pending_transit_remains_company_stock_by_source_division(self):
        self._transit()
        data = self._report(1)
        self.assertEqual(data["opening_stock"], 1000)
        self.assertEqual(data["total_sales"], 0)
        self.assertEqual(data["total_shrinkage"], 0)
        self.assertEqual(data["closing_stock"], 1000)
        for quantity, division in zip((600, 400), self.divisions):
            self.assertEqual(data["analysis_values"]["closing_stock"]["division:%s" % division.id], quantity)
        rows = {row["label"]: row["values"] for row in data["matrix"]["rows"] if "values" in row}
        self.assertEqual(rows["Stok di Gudang"].get("total", 0), 0)
        self.assertEqual(rows["Stok dalam Transit"]["total"], 1000)
        self._assert_balanced_scopes(data)

    def test_transit_receiving_and_next_month_opening_do_not_add_production(self):
        lot = self._transit()
        self._move(300, lot, self.transit_location, self.warehouse.lot_stock_id, 2)
        data = self._report(2)
        self.assertEqual(data["total_weighing"], 0)
        self.assertEqual(data["total_sales"], 0)
        self.assertEqual(data["closing_stock"], 1000)
        rows = {row["label"]: row["values"] for row in data["matrix"]["rows"] if "values" in row}
        self.assertEqual(rows["Stok di Gudang"]["total"], 300)
        self.assertEqual(rows["Stok dalam Transit"]["total"], 700)
        self._assert_balanced_scopes(data)
        next_month = self._report(1, month=3)
        self.assertEqual(next_month["opening_stock"], 1000)
        self.assertEqual(next_month["closing_stock"], 1000)
        self.assertEqual(next_month["total_weighing"], 0)
        self._assert_balanced_scopes(next_month)

    def test_partial_shipments_count_once_before_delivery_is_closed(self):
        lot = self._transit()
        delivery = self.env["wt.delivery"].create({
            "company_id": self.company.id, "state": "delivered",
        })
        picking = self.env["stock.picking"].create({
            "company_id": self.company.id, "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.transit_location.id, "location_dest_id": self.customer.id,
            "wt_delivery_id": delivery.id,
        })
        self._move(400, lot, self.transit_location, self.customer, 2, picking)
        partial = self._report(2)
        self.assertEqual(partial["total_sales"], 400)
        self.assertEqual(partial["closing_stock"], 600)
        self._assert_balanced_scopes(partial)
        self._move(600, lot, self.transit_location, self.customer, 3, picking)
        final = self._report(3)
        self.assertEqual(final["total_sales"], 1000)
        self.assertEqual(final["closing_stock"], 0)
        self._assert_balanced_scopes(final)
        # The prior date retains the stock which was still in transit then.
        self.assertEqual(self._report(2)["closing_stock"], 600)

    def test_transit_shrinkage_and_reversal_follow_movement_date(self):
        lot = self._transit()
        delivery, original = self._manual_loss(lot, (90, 10))
        shrunk = self._report(2)
        self.assertEqual(shrunk["total_shrinkage"], 100)
        self.assertEqual(shrunk["closing_stock"], 900)
        self._assert_balanced_scopes(shrunk)
        reversal = self._move(100, lot, self.loss, self.transit_location, 3)
        reversal.write({"wt_delivery_id": delivery.id, "origin_returned_move_id": original.id})
        reversed_data = self._report(3)
        self.assertEqual(reversed_data["total_shrinkage"], 0)
        self.assertEqual(reversed_data["closing_stock"], 1000)
        self.assertEqual(reversed_data["analysis_values"]["storage_shrinkage_qty"]["total"], -100)
        self._assert_balanced_scopes(reversed_data)

    def test_saved_do_proportions_override_source_ratio_without_double_loss(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5))
        data = self._report(2)
        loss = data["analysis_values"]["storage_shrinkage_qty"]
        self.assertEqual(loss["division:%s" % self.divisions[0].id], 95)
        self.assertEqual(loss["division:%s" % self.divisions[1].id], 5)
        self.assertEqual(data["total_shrinkage"], 100)
        self.assertEqual(data["closing_stock"], 900)
        self.assertEqual(data["pending_transit_shrinkage"], 0)
        self._assert_balanced_scopes(data)
        self._move(450, lot, self.transit_location, self.customer, 3)
        partial = self._report(3)
        self.assertEqual(partial["analysis_values"]["sales_qty"]["division:%s" % self.divisions[0].id], 252.5)
        self.assertEqual(partial["analysis_values"]["sales_qty"]["division:%s" % self.divisions[1].id], 197.5)
        self._assert_balanced_scopes(partial)
        self._move(450, lot, self.transit_location, self.customer, 4)
        final = self._report(4)
        self.assertEqual(final["total_sales"], 900)
        self.assertEqual(final["total_shrinkage"], 100)
        self.assertEqual(final["closing_stock"], 0)
        self._assert_balanced_scopes(final)

    def test_unsaved_proportions_remain_unassigned_instead_of_automatic(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5), saved=False)
        data = self._report(2)
        loss = data["analysis_values"]["storage_shrinkage_qty"]
        self.assertFalse(any(key.startswith("division:") for key in loss))
        self.assertEqual(data["pending_transit_shrinkage"], 100)
        self.assertEqual(data["total_shrinkage"], 100)
        self.assertEqual(data["closing_stock"], 900)
        self.assertAlmostEqual(data["balance_difference"], 0)
        delivery.action_save_transit_proportion()
        saved = self._report(2)
        self.assertEqual(saved["pending_transit_shrinkage"], 0)
        self._assert_balanced_scopes(saved)

    def test_editing_and_resaving_proportions_refreshes_stored_analytics(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5))
        service = self.env["wt.daily.stock.analysis.service"]
        service.refresh_range(self.company, date(2020, 2, 2), date(2020, 2, 3))
        props = delivery.transit_shrinkage_proportion_ids.sorted(lambda prop: prop.lot_id.id)
        props[0].proportion_qty = 70
        props[1].proportion_qty = 30
        self.assertFalse(delivery.transit_shrinkage_proportion_saved)
        pending = self.env["wt.daily.stock.analysis"].search([
            ("company_id", "=", self.company.id), ("report_date", "=", date(2020, 2, 2)),
            ("division_id", "in", self.divisions.ids),
        ])
        self.assertTrue(all(row.storage_shrinkage_qty == 0 for row in pending))
        delivery.action_save_transit_proportion()
        for division, expected in zip(self.divisions, (70, 30)):
            row = self.env["wt.daily.stock.analysis"].search([
                ("company_id", "=", self.company.id), ("report_date", "=", date(2020, 2, 2)),
                ("division_id", "=", division.id),
            ])
            self.assertEqual(row.storage_shrinkage_qty, expected)
            self.assertAlmostEqual(row.balance_difference, 0)
        self._assert_balanced_scopes(self._report(3))

    def test_customer_return_preserves_manual_loss_attribution(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5))
        self._move(900, lot, self.transit_location, self.customer, 3)
        self._move(900, lot, self.customer, self.transit_location, 4)
        data = self._report(4)
        self.assertEqual(data["total_sales"], 0)
        self.assertEqual(data["total_shrinkage"], 100)
        self.assertEqual(data["closing_stock"], 900)
        self.assertEqual(data["analysis_values"]["closing_stock"]["division:%s" % self.divisions[0].id], 505)
        self.assertEqual(data["analysis_values"]["closing_stock"]["division:%s" % self.divisions[1].id], 395)
        self._assert_balanced_scopes(data)

    def test_nested_transit_preserves_remaining_manual_contributions(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5))
        picking = self.env["stock.picking"].create({
            "company_id": self.company.id, "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.transit_location.id, "location_dest_id": self.warehouse.lot_stock_id.id,
        })
        self._move(900, lot, self.transit_location, self.loss, 3, picking, "Consume old lots for transit merge - QA")
        nested = self.env["stock.lot"].create({
            "name": "DST-NESTED", "product_id": self.product.id, "company_id": self.company.id,
            "wt_lot_type": "transit", "wt_source_picking_id": picking.id,
        })
        self._move(900, nested, self.loss, self.warehouse.lot_stock_id, 3, picking, "Produce new merged lot for transit - QA")
        self._move(900, nested, self.warehouse.lot_stock_id, self.customer, 4)
        data = self._report(4)
        self.assertEqual(data["total_sales"], 900)
        self.assertEqual(data["total_shrinkage"], 100)
        self.assertEqual(data["closing_stock"], 0)
        for division, expected in zip(self.divisions, (505, 395)):
            values = next(row["values"] for row in data["matrix"]["rows"] if row["label"] == "Produksi Keluar")
            self.assertEqual(values["division:%s" % division.id], expected)
        self._assert_balanced_scopes(data)

    def test_zero_manual_share_is_not_replaced_by_automatic_share(self):
        lot = self._transit()
        self._manual_loss(lot, (100, 0))
        data = self._report(2)
        loss = data["analysis_values"]["storage_shrinkage_qty"]
        self.assertEqual(loss.get("division:%s" % self.divisions[0].id), 100)
        self.assertEqual(loss.get("division:%s" % self.divisions[1].id, 0), 0)
        self._assert_balanced_scopes(data)

    def test_inconsistent_saved_proportion_is_flagged_instead_of_normalized(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5))
        delivery.transit_shrinkage_proportion_ids[0].proportion_qty = 50
        delivery.transit_shrinkage_proportion_saved = True
        data = self._report(2)
        self.assertEqual(data["total_shrinkage"], 100)
        self.assertEqual(data["pending_transit_shrinkage"], 100)
        self.assertFalse(any(key.startswith("division:") for key in data["analysis_values"]["storage_shrinkage_qty"]))

    def test_partial_shipment_before_loss_retains_approved_future_loss_share(self):
        lot = self._transit()
        self._move(450, lot, self.transit_location, self.customer, 2)
        self._manual_loss(lot, (95, 5), day=3)
        earlier = self._report(2)
        self.assertEqual(earlier["total_sales"], 450)
        self.assertEqual(earlier["total_shrinkage"], 0)
        self.assertEqual(earlier["closing_stock"], 550)
        self._assert_balanced_scopes(earlier)
        later = self._report(3)
        self.assertEqual(later["closing_stock"], 450)
        self._assert_balanced_scopes(later)

    def test_customer_return_restores_stock_and_reduces_net_sales(self):
        lot = self._transit()
        self._move(1000, lot, self.transit_location, self.customer, 2)
        self._move(1000, lot, self.customer, self.warehouse.lot_stock_id, 3)
        data = self._report(3)
        self.assertEqual(data["total_sales"], 0)
        self.assertEqual(data["closing_stock"], 1000)
        self.assertEqual(data["analysis_values"]["sales_qty"]["total"], -1000)
        self._assert_balanced_scopes(data)

    def test_excluded_rollback_movements_do_not_enter_the_report(self):
        lot = self._transit()
        shipped = self._move(1000, lot, self.transit_location, self.customer, 2)
        returned = self._move(1000, lot, self.customer, self.transit_location, 3)
        (shipped | returned).write({"wt_exclude_from_weightrack_reports": True})
        data = self._report(3)
        self.assertEqual(data["total_sales"], 0)
        self.assertEqual(data["closing_stock"], 1000)
        self._assert_balanced_scopes(data)
