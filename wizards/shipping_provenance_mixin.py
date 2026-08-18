# -*- coding: utf-8 -*-

from odoo import models


class ShippingProvenanceMixin(models.AbstractModel):
    _name = "wt.shipping.provenance.mixin"
    _description = "Shipping Lot Provenance Mixin"

    def _iter_delivery_shipping_source_events(
        self,
        start_dt,
        end_dt,
        warehouses,
        end_operator="<",
        product=None,
        transit_quantity_basis="customer",
    ):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("picking_id.wt_delivery_id", "!=", False),
            ("picking_id.wt_delivery_id.state", "in", ("done", "returned")),
            ("move_id.date", ">=", start_dt),
            ("move_id.date", end_operator, end_dt),
            ("location_dest_id.usage", "=", "customer"),
            ("quantity", ">", 0.0),
            ("lot_id", "!=", False),
        ]
        if product:
            domain.append(("product_id", "=", product.id))

        move_lines = self.env["stock.move.line"].search(domain, order="id")
        provenance_cache = {}
        for line in move_lines:
            delivery = line.picking_id.wt_delivery_id
            lot = line.lot_id
            quantity = line.quantity or 0.0
            if lot.wt_lot_type == "production":
                yield self._prepare_shipping_source_event(
                    line,
                    delivery,
                    self._resolve_warehouse(line.location_id, warehouses),
                    lot.division_id,
                    lot,
                    quantity,
                )
                continue
            if lot.wt_lot_type != "transit":
                continue

            sources = self._get_transit_provenance(
                lot,
                warehouses,
                provenance_cache,
            )
            source_total = sum(source["quantity"] for source in sources)
            if not source_total:
                continue

            remaining = quantity
            for index, source in enumerate(sources):
                if transit_quantity_basis == "source":
                    allocated_quantity = source["quantity"]
                else:
                    allocated_quantity = (
                        remaining
                        if index == len(sources) - 1
                        else quantity * source["quantity"] / source_total
                    )
                    remaining -= allocated_quantity
                yield self._prepare_shipping_source_event(
                    line,
                    delivery,
                    source["warehouse"],
                    source["division"],
                    source["lot"],
                    allocated_quantity,
                )

    def _prepare_shipping_source_event(
        self,
        line,
        delivery,
        warehouse,
        division,
        lot,
        quantity,
    ):
        return {
            "movement_date": line.move_id.date,
            "delivery": delivery,
            "warehouse": warehouse,
            "division": division,
            "lot": lot,
            "product": line.product_id,
            "quantity": quantity,
            "uom": line.product_uom_id or line.product_id.uom_id,
        }

    def _get_transit_provenance(self, lot, warehouses, cache, visiting=None):
        if lot.id in cache:
            return cache[lot.id]

        visiting = set(visiting or ())
        if lot.id in visiting:
            return []
        visiting.add(lot.id)

        picking = lot.wt_source_picking_id
        if not picking:
            cache[lot.id] = []
            return []

        consume_lines = picking.move_line_ids.filtered(
            lambda line: line.lot_id
            and line.lot_id != lot
            and self._is_transit_merge_consume(line)
        )
        if not consume_lines:
            consume_lines = picking.move_line_ids.filtered(
                lambda line: line.lot_id
                and line.lot_id != lot
                and line.location_id.usage == "internal"
                and line.location_dest_id.usage == "inventory"
            )

        provenance_map = {}
        for line in consume_lines:
            source_lot = line.lot_id
            source_quantity = line.quantity or 0.0
            if source_quantity <= 0.0:
                continue

            if source_lot.wt_lot_type == "transit":
                nested_sources = self._get_transit_provenance(
                    source_lot,
                    warehouses,
                    cache,
                    visiting,
                )
                nested_total = sum(
                    source["quantity"] for source in nested_sources
                )
                if nested_total:
                    for source in nested_sources:
                        self._merge_provenance_source(
                            provenance_map,
                            source,
                            source_quantity * source["quantity"] / nested_total,
                        )
                continue

            if source_lot.wt_lot_type != "production":
                continue
            source = {
                "warehouse": self._resolve_warehouse(
                    line.location_id,
                    warehouses,
                ),
                "division": source_lot.division_id,
                "lot": source_lot,
            }
            self._merge_provenance_source(
                provenance_map,
                source,
                source_quantity,
            )

        result = list(provenance_map.values())
        cache[lot.id] = result
        return result

    def _merge_provenance_source(self, provenance_map, source, quantity):
        key = (
            source["warehouse"].id or 0,
            source["division"].id or 0,
            source["lot"].id,
        )
        if key not in provenance_map:
            provenance_map[key] = dict(source, quantity=0.0)
        provenance_map[key]["quantity"] += quantity

    def _is_transit_merge_consume(self, line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Consume old lots for transit merge")
            and line.location_dest_id.usage == "inventory"
        )
