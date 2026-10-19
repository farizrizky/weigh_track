# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models


class StockPeriodBasisMixin(models.AbstractModel):
    _name = "wt.stock.period.basis.mixin"
    _description = "Stock Period Basis Mixin"

    def _report_transit_scope(self, line, end_dt, warehouses, cache):
        """Reuse Daily Stock's approved DO attribution for actual movements."""
        product = line.product_id
        if product.id not in cache:
            calculator = self.env["wt.daily.stock.report.wizard"].new({
                "company_id": self.company_id.id,
            })
            cache[product.id] = calculator._prepare_transit_scope(
                product, end_dt + timedelta(microseconds=1), warehouses,
            )
        return cache[product.id]

    def _get_actual_shrinkage_events(self, start_dt, end_dt, warehouses, cache=None):
        """Signed Inventory losses; DO proportions only attribute transit loss.

        Unsaved/invalid proportions retain the actual amount on the transit lot,
        without assigning it automatically to a production division.
        """
        cache = cache if cache is not None else {}
        calculator = self.env["wt.daily.stock.report.wizard"].new({
            "company_id": self.company_id.id,
        })
        loss = calculator._get_shrinkage_location()
        if not loss:
            return []
        loss_ids = set(self.env["stock.location"].search([
            ("id", "child_of", loss.id),
        ]).ids)
        lines = self.env["stock.move.line"].search([
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("move_id.wt_exclude_from_weightrack_reports", "=", False),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
            ("quantity", ">", 0),
            ("lot_id.wt_lot_type", "in", ["production", "transit"]),
            "|", ("location_id", "in", list(loss_ids)),
            ("location_dest_id", "in", list(loss_ids)),
        ], order="id")
        events = []
        for line in lines:
            if calculator._is_transit_merge_move_line(line):
                continue
            if line.location_dest_id.id in loss_ids and line.location_id.usage in ("internal", "transit"):
                sign, location = 1, line.location_id
            elif line.location_id.id in loss_ids and line.location_dest_id.usage in ("internal", "transit"):
                sign, location = -1, line.location_dest_id
            else:
                continue
            quantity = calculator._line_quantity_in_product_uom(line)
            pending = False
            if line.lot_id.wt_lot_type == "transit":
                scope = self._report_transit_scope(line, end_dt, warehouses, cache)
                sources = scope["shrinkage"].get(line.id)
                # A linked correction restores exactly the original allocation,
                # even when the return itself has no Delivery relation.
                original = line.move_id.wt_reversal_of_move_id or line.move_id.origin_returned_move_id
                if sign < 0 and original:
                    original_sources = [
                        source for original_line in original.move_line_ids
                        if original_line.lot_id == line.lot_id
                        for source in scope["shrinkage"].get(original_line.id, [])
                    ]
                    total = sum(source["quantity"] for source in original_sources)
                    if total:
                        sources = [{**source, "quantity": quantity * source["quantity"] / total}
                                   for source in original_sources]
                if not sources:
                    pending = True
                    sources = [{"lot": line.lot_id, "division": self.env["wt.division"],
                                "warehouse": self._resolve_warehouse(location, warehouses),
                                "quantity": quantity}]
            else:
                sources = [{"lot": line.lot_id, "division": line.lot_id.division_id,
                            "warehouse": self._resolve_warehouse(location, warehouses),
                            "quantity": quantity}]
            for source in sources:
                warehouse, division = source["warehouse"], source["division"]
                if self.warehouse_id and warehouse != self.warehouse_id:
                    continue
                if self.division_id and division != self.division_id:
                    continue
                events.append({
                    **source, "quantity": sign * source["quantity"], "line": line,
                    "source_location": location, "pending_transit": pending,
                })
        return events

    def _build_period_stock_basis(
        self, start_dt, end_dt, warehouses, include_transit=False, transit_cache=None,
    ):
        """Build period stock, optionally including company stock in transit.

        Transit-inclusive reports reuse the chronological allocations of Daily
        Stock, so approved DO losses also govern each source lot's balance.
        """
        self.ensure_one()
        transit_cache = transit_cache if transit_cache is not None else {}
        move_lines = self.env["stock.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("move_id.state", "=", "done"),
                ("move_id.wt_exclude_from_weightrack_reports", "=", False),
                ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
                ("quantity", ">", 0.0),
                ("lot_id", "!=", False),
                ("lot_id.wt_lot_type", "in", ["production", "transit"]),
            ],
            order="id",
        )
        basis = {}
        provenance_cache = {}
        division_warehouses = self._basis_division_warehouse_map()
        start_value = fields.Datetime.to_datetime(start_dt)

        for line in move_lines:
            movement_date = fields.Datetime.to_datetime(line.move_id.date)
            source_in_scope = self._basis_location_in_scope(
                line.location_id,
                warehouses,
                include_transit=include_transit,
            )
            destination_in_scope = self._basis_location_in_scope(
                line.location_dest_id,
                warehouses,
                include_transit=include_transit,
            )
            if not source_in_scope and not destination_in_scope:
                continue

            if include_transit and line.lot_id.wt_lot_type == "transit":
                scope = self._report_transit_scope(line, end_dt, warehouses, transit_cache)
                sources = scope["movement"].get(line.id, [])
            else:
                quantity = line.quantity or 0.0
                if include_transit:
                    quantity = line.product_uom_id._compute_quantity(quantity, line.product_id.uom_id)
                sources = self._basis_production_sources(
                    line.lot_id, quantity, warehouses, provenance_cache,
                )
            for source in sources:
                row = self._basis_row(basis, source, division_warehouses)
                quantity = source["quantity"]
                delta = (
                    (quantity if destination_in_scope else 0.0)
                    - (quantity if source_in_scope else 0.0)
                )
                if movement_date < start_value:
                    row["opening_qty"] += delta
                row["closing_qty"] += delta

                if (
                    movement_date >= start_value
                    and destination_in_scope
                    and not source_in_scope
                    and self._basis_is_allowed_stock_in(line, warehouses)
                ):
                    row["stock_in_qty"] += quantity
                elif (
                    movement_date >= start_value
                    and source_in_scope
                    and not destination_in_scope
                    and line.picking_id
                    and line.picking_id.production_receipt_reverse_id
                ):
                    row["stock_in_qty"] -= quantity

        return {
            key: value
            for key, value in basis.items()
            if any(
                abs(value[field_name]) > 0.000001
                for field_name in ("opening_qty", "stock_in_qty", "closing_qty")
            )
        }

    def _basis_row(self, basis, source, division_warehouses):
        lot = source["lot"]
        division = source["division"]
        warehouse = (
            self.warehouse_id
            or division_warehouses.get(division.id)
            or self.env["stock.warehouse"]
        )
        key = self._stock_basis_key(division, lot)
        if key not in basis:
            basis[key] = {
                "warehouse": warehouse,
                "division": division,
                "lot": lot,
                "product": lot.product_id,
                "uom": lot.product_id.uom_id,
                "opening_qty": 0.0,
                "stock_in_qty": 0.0,
                "closing_qty": 0.0,
            }
        return basis[key]

    def _basis_division_warehouse_map(self):
        self.ensure_one()
        rules = self.env["wt.receipt.rule"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("active", "=", True),
                ("warehouse_id", "!=", False),
            ],
            order="id",
        )
        warehouse_ids_by_division = {}
        for rule in rules:
            warehouse_ids_by_division.setdefault(rule.division_id.id, set()).add(
                rule.warehouse_id.id
            )
        return {
            division_id: self.env["stock.warehouse"].browse(next(iter(warehouse_ids)))
            for division_id, warehouse_ids in warehouse_ids_by_division.items()
            if len(warehouse_ids) == 1
        }

    def _stock_basis_key(self, division, lot):
        return (
            self.warehouse_id.id or 0,
            division.id or 0,
            lot.id,
        )

    def _basis_location_in_scope(self, location, warehouses, include_transit=False):
        usages = ("internal", "transit") if include_transit else ("internal",)
        if not location or location.usage not in usages:
            return False
        if location.company_id and location.company_id != self.company_id:
            return False
        if not self.warehouse_id:
            return True
        return self._resolve_warehouse(location, warehouses) == self.warehouse_id

    def _basis_is_allowed_stock_in(self, line, warehouses):
        picking = line.picking_id
        if picking and picking.production_receipt_id:
            return True
        if line.location_id.usage == "customer":
            return True
        if not self.warehouse_id:
            return False
        if line.location_id.usage == "transit":
            return True
        if line.location_id.usage != "internal":
            return False
        source_warehouse = self._resolve_warehouse(line.location_id, warehouses)
        return source_warehouse != self.warehouse_id

    def _basis_production_sources(
        self,
        lot,
        quantity,
        warehouses,
        cache,
        visiting=None,
    ):
        if lot.wt_lot_type == "production":
            return [
                {
                    "lot": lot,
                    "division": lot.division_id,
                    "quantity": quantity,
                }
            ]
        sources = self._basis_transit_provenance(
            lot,
            warehouses,
            cache,
            visiting,
        )
        total = sum(source["quantity"] for source in sources)
        if not total:
            return []
        remaining = quantity
        allocated = []
        for index, source in enumerate(sources):
            allocated_quantity = (
                remaining
                if index == len(sources) - 1
                else quantity * source["quantity"] / total
            )
            remaining -= allocated_quantity
            allocated.append(
                {
                    "lot": source["lot"],
                    "division": source["division"],
                    "quantity": allocated_quantity,
                }
            )
        return allocated

    def _basis_transit_provenance(
        self,
        lot,
        warehouses,
        cache,
        visiting=None,
    ):
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
            and self._basis_is_transit_merge_consume(line)
        )
        if not consume_lines:
            consume_lines = picking.move_line_ids.filtered(
                lambda line: line.lot_id
                and line.lot_id != lot
                and line.location_id.usage == "internal"
                and line.location_dest_id.usage == "inventory"
            )

        result_map = {}
        for line in consume_lines:
            source_lot = line.lot_id
            source_quantity = line.quantity or 0.0
            if source_quantity <= 0.0:
                continue
            if source_lot.wt_lot_type == "transit":
                nested = self._basis_transit_provenance(
                    source_lot,
                    warehouses,
                    cache,
                    visiting,
                )
                nested_total = sum(source["quantity"] for source in nested)
                if nested_total:
                    for source in nested:
                        self._basis_merge_source(
                            result_map,
                            source,
                            source_quantity * source["quantity"] / nested_total,
                        )
                continue
            if source_lot.wt_lot_type != "production":
                continue
            self._basis_merge_source(
                result_map,
                {
                    "lot": source_lot,
                    "division": source_lot.division_id,
                },
                source_quantity,
            )

        result = list(result_map.values())
        cache[lot.id] = result
        return result

    @staticmethod
    def _basis_merge_source(result_map, source, quantity):
        key = (source["division"].id or 0, source["lot"].id)
        if key not in result_map:
            result_map[key] = dict(source, quantity=0.0)
        result_map[key]["quantity"] += quantity

    @staticmethod
    def _basis_is_transit_merge_consume(line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Consume old lots for transit merge")
            and line.location_dest_id.usage == "inventory"
        )
