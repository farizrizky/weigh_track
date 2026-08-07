# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "weightrack_delivery_migration_reset")
class TestDeliveryMigrationReset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.write(
            {
                "group_ids": [
                    (4, cls.env.ref("weightrack.group_admin").id),
                ]
            }
        )
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not warehouse:
            warehouse = cls.env["stock.warehouse"].create(
                {
                    "name": "Migration Reset Warehouse",
                    "code": "MRST",
                    "company_id": cls.company.id,
                }
            )
        cls.internal_type = warehouse.int_type_id
        cls.outgoing_type = warehouse.out_type_id

        internal_root = warehouse.lot_stock_id
        cls.source = cls.env["stock.location"].create(
            {
                "name": "Migration Reset Source",
                "usage": "internal",
                "location_id": internal_root.id,
                "company_id": cls.company.id,
            }
        )
        cls.destination = cls.env["stock.location"].create(
            {
                "name": "Migration Reset Destination",
                "usage": "internal",
                "location_id": internal_root.id,
                "company_id": cls.company.id,
            }
        )
        cls.merge_location = cls.env["stock.location"].create(
            {
                "name": "Migration Reset Merge",
                "usage": "inventory",
                "company_id": cls.company.id,
            }
        )
        cls.initial_inventory_location = cls.env["stock.location"].create(
            {
                "name": "Migration Reset Initial Inventory",
                "usage": "inventory",
                "company_id": cls.company.id,
            }
        )
        cls.shrinkage_location = cls.env.ref(
            "weightrack.stock_location_wt_inventory_loss_susut"
        )
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.partner = cls.env["res.partner"].create(
            {"name": "Migration Reset Customer"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Migration Reset Product",
                "is_storable": True,
                "tracking": "lot",
            }
        )

    def _create_lot(self, name, lot_type):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.product.id,
                "company_id": self.company.id,
                "wt_lot_type": lot_type,
                "wt_transit_state": "open" if lot_type == "transit" else False,
            }
        )

    def _create_standalone_move(
        self,
        origin,
        description,
        lot,
        quantity,
        source,
        destination,
        *,
        is_inventory=False,
    ):
        move = self.env["stock.move"].create(
            {
                "description_picking": description,
                "inventory_name": "Test",
                "state": "confirmed",
                "picked": True,
                "is_inventory": is_inventory,
                "product_id": self.product.id,
                "product_uom": self.product.uom_id.id,
                "product_uom_qty": quantity,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company.id,
                "origin": origin,
                "move_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_id": self.product.uom_id.id,
                            "quantity": quantity,
                            "picked": True,
                            "lot_id": lot.id,
                            "location_id": source.id,
                            "location_dest_id": destination.id,
                            "company_id": self.company.id,
                        },
                    )
                ],
            }
        )
        move._action_done()
        return move

    def _create_picking_move(
        self,
        picking_type,
        delivery,
        lot,
        quantity,
        source,
        destination,
        description,
    ):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "partner_id": delivery.partner_id.id,
                "wt_delivery_id": delivery.id,
                "origin": delivery.name,
                "company_id": self.company.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "description_picking": description,
                            "inventory_name": "Pengiriman",
                            "product_id": self.product.id,
                            "product_uom": self.product.uom_id.id,
                            "product_uom_qty": quantity,
                            "location_id": source.id,
                            "location_dest_id": destination.id,
                            "company_id": self.company.id,
                            "origin": delivery.name,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.move_line_ids.unlink()
        move = picking.move_ids
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": quantity,
                "lot_id": lot.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company.id,
            }
        )
        move.picked = True
        move._action_done()
        return picking, move

    def _create_transit_picking(
        self,
        delivery,
        production_lot,
        transit_lot,
        quantity,
    ):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.internal_type.id,
                "location_id": self.source.id,
                "location_dest_id": self.destination.id,
                "wt_delivery_id": delivery.id,
                "origin": delivery.name,
                "company_id": self.company.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "description_picking": (
                                "Consume old lots for transit merge - Test"
                            ),
                            "inventory_name": "Pengiriman",
                            "product_id": self.product.id,
                            "product_uom": self.product.uom_id.id,
                            "product_uom_qty": quantity,
                            "location_id": self.source.id,
                            "location_dest_id": self.merge_location.id,
                            "company_id": self.company.id,
                            "origin": delivery.name,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "description_picking": (
                                "Produce new merged lot for transit - Test"
                            ),
                            "inventory_name": "Pengiriman",
                            "product_id": self.product.id,
                            "product_uom": self.product.uom_id.id,
                            "product_uom_qty": quantity,
                            "location_id": self.merge_location.id,
                            "location_dest_id": self.destination.id,
                            "company_id": self.company.id,
                            "origin": delivery.name,
                        },
                    ),
                ],
            }
        )
        picking.action_confirm()
        picking.move_line_ids.unlink()
        consume_move, produce_move = picking.move_ids.sorted("id")
        self.env["stock.move.line"].create(
            {
                "move_id": consume_move.id,
                "picking_id": picking.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": quantity,
                "lot_id": production_lot.id,
                "location_id": self.source.id,
                "location_dest_id": self.merge_location.id,
                "company_id": self.company.id,
            }
        )
        self.env["stock.move.line"].create(
            {
                "move_id": produce_move.id,
                "picking_id": picking.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": quantity,
                "lot_id": transit_lot.id,
                "location_id": self.merge_location.id,
                "location_dest_id": self.destination.id,
                "company_id": self.company.id,
            }
        )
        picking.move_ids.picked = True
        picking.move_ids._action_done()
        return picking

    def _quant(self, lot, location):
        return sum(
            self.env["stock.quant"]
            .search(
                [
                    ("product_id", "=", self.product.id),
                    ("lot_id", "=", lot.id),
                    ("location_id", "=", location.id),
                ]
            )
            .mapped("quantity")
        )

    def test_reset_restores_source_lot_and_excludes_reports(self):
        production_lot = self._create_lot(
            "MIGRATION-RESET-PRODUCTION",
            "production",
        )
        transit_lot = self._create_lot(
            "MIGRATION-RESET-TRANSIT",
            "transit",
        )
        self._create_standalone_move(
            "MIGRATION-RESET-INITIAL",
            "Initial migration stock",
            production_lot,
            100.0,
            self.initial_inventory_location,
            self.source,
            is_inventory=True,
        )
        delivery = self.env["wt.delivery"].create(
            {
                "name": "DO/MIGRATION/RESET",
                "company_id": self.company.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
                "product_id": self.product.id,
                "state": "done",
                "validated_at": fields.Datetime.now(),
                "validated_by_id": self.env.user.id,
            }
        )
        self._create_standalone_move(
            delivery.name,
            "Production shrinkage",
            production_lot,
            2.0,
            self.source,
            self.shrinkage_location,
            is_inventory=True,
        )
        transit_picking = self._create_transit_picking(
            delivery,
            production_lot,
            transit_lot,
            98.0,
        )
        transit_lot.write(
            {
                "wt_source_delivery_id": delivery.id,
                "wt_source_picking_id": transit_picking.id,
                "wt_transit_date": delivery.date,
            }
        )
        self._create_standalone_move(
            delivery.name,
            "Transfer shrinkage",
            transit_lot,
            1.0,
            self.destination,
            self.shrinkage_location,
            is_inventory=True,
        )
        outgoing_picking, _outgoing_move = self._create_picking_move(
            self.outgoing_type,
            delivery,
            transit_lot,
            97.0,
            self.destination,
            self.customer_location,
            self.product.display_name,
        )

        transit_route_line = self.env["wt.delivery.do.line"].create(
            {
                "delivery_id": delivery.id,
                "sequence": 10,
                "picking_type_id": self.internal_type.id,
                "product_id": self.product.id,
                "location_id": self.source.id,
                "location_dest_id": self.destination.id,
                "picking_id": transit_picking.id,
                "generated_transit_lot_id": transit_lot.id,
            }
        )
        source_lot_line = self.env["wt.delivery.do.line.lot"].create(
            {
                "do_line_id": transit_route_line.id,
                "lot_id": production_lot.id,
                "source_location_id": self.source.id,
                "qty": 100.0,
                "wt_original_qty": 100.0,
                "wt_physical_qty": 98.0,
                "wt_is_pulled": True,
                "wt_adjustment_applied": True,
            }
        )
        outgoing_route_line = self.env["wt.delivery.do.line"].create(
            {
                "delivery_id": delivery.id,
                "sequence": 20,
                "picking_type_id": self.outgoing_type.id,
                "product_id": self.product.id,
                "location_id": self.destination.id,
                "location_dest_id": self.customer_location.id,
                "picking_id": outgoing_picking.id,
            }
        )
        transit_lot_line = self.env["wt.delivery.do.line.lot"].create(
            {
                "do_line_id": outgoing_route_line.id,
                "lot_id": transit_lot.id,
                "source_location_id": self.destination.id,
                "qty": 98.0,
                "wt_original_qty": 98.0,
                "wt_physical_qty": 97.0,
                "wt_is_pulled": True,
                "wt_adjustment_applied": True,
            }
        )

        self.assertEqual(self._quant(production_lot, self.source), 0.0)
        self.assertEqual(
            self._quant(production_lot, self.shrinkage_location),
            2.0,
        )
        self.assertEqual(
            self._quant(transit_lot, self.shrinkage_location),
            1.0,
        )
        self.assertEqual(
            self._quant(transit_lot, self.customer_location),
            97.0,
        )

        reset_log = delivery._action_migration_reset(
            "Automated migration reset test"
        )

        self.assertEqual(delivery.state, "draft")
        self.assertEqual(delivery.picking_count, 0)
        self.assertEqual(reset_log.movement_count, 5)
        self.assertEqual(reset_log.reversal_movement_count, 5)
        self.assertEqual(reset_log.shrinkage_quantity, 3.0)
        self.assertEqual(self._quant(production_lot, self.source), 100.0)
        self.assertEqual(
            self._quant(production_lot, self.shrinkage_location),
            0.0,
        )
        self.assertEqual(
            self._quant(production_lot, self.merge_location),
            0.0,
        )
        self.assertEqual(self._quant(transit_lot, self.destination), 0.0)
        self.assertEqual(
            self._quant(transit_lot, self.shrinkage_location),
            0.0,
        )
        self.assertEqual(
            self._quant(transit_lot, self.customer_location),
            0.0,
        )
        self.assertEqual(
            self._quant(transit_lot, self.merge_location),
            0.0,
        )
        self.assertTrue(source_lot_line.exists())
        self.assertEqual(source_lot_line.qty, 100.0)
        self.assertEqual(source_lot_line.wt_physical_qty, 0.0)
        self.assertFalse(transit_lot_line.exists())
        self.assertTrue(transit_lot.wt_is_migration_reset)
        self.assertEqual(transit_lot.wt_transit_state, "closed")
        self.assertTrue(all(reset_log.move_ids.mapped("wt_is_migration_reset")))
        self.assertEqual(
            set(reset_log.move_ids.mapped("wt_migration_reset_role")),
            {"original", "reversal"},
        )

        today = fields.Date.context_today(self.env.user)
        storage_wizard = self.env["wt.storage.shrinkage.report.wizard"].new(
            {
                "company_id": self.company.id,
                "start_date": today,
                "end_date": today,
            }
        )
        self.assertFalse(
            storage_wizard._get_move_lines().filtered(
                lambda line: line.move_id.wt_migration_reset_log_id
                == reset_log
            )
        )
        stock_out_wizard = self.env["wt.stock.out.report.wizard"].new(
            {
                "company_id": self.company.id,
                "start_date": today,
                "end_date": today,
            }
        )
        self.assertFalse(
            stock_out_wizard._get_storage_shrinkage_move_lines().filtered(
                lambda line: line.move_id.wt_migration_reset_log_id
                == reset_log
            )
        )
        self.assertFalse(
            stock_out_wizard._get_transfer_shrinkage_move_lines().filtered(
                lambda line: line.move_id.wt_migration_reset_log_id
                == reset_log
            )
        )
        shipping_wizard = self.env["wt.shipping.report.wizard"].new(
            {
                "company_id": self.company.id,
                "start_date": today,
                "end_date": today,
            }
        )
        self.assertFalse(
            shipping_wizard._get_shipping_move_lines().filtered(
                lambda line: line.move_id.wt_migration_reset_log_id
                == reset_log
            )
        )

        daily_report = self.env["wt.daily.stock.report"].create({})
        daily_wizard = self.env["wt.daily.stock.report.wizard"].new(
            {
                "report_id": daily_report.id,
                "company_id": self.company.id,
                "report_date": today,
            }
        )
        day_start, day_end = daily_wizard._get_utc_bounds(today, today)
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company.id)]
        )
        daily_events = daily_wizard._aggregate_stock_events(
            self.product,
            day_start,
            day_end,
            warehouses,
        )
        for event_values in daily_events.values():
            self.assertFalse(
                any(event_values.values()),
                "Migration reset movements must not affect the daily stock report.",
            )
