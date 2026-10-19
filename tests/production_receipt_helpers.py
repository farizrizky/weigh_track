"""Inventory fixtures for production-total report regressions."""


def configure_report_receipts(env, company, estate, division):
    env["ir.config_parameter"].set_param("ir_attachment.location", "db")
    product = env["wt.product"].get_active_product(company)
    if not product:
        product = env["product.product"].create({
            "name": "Receipt Report QA Product", "company_id": company.id,
            "is_storable": True, "tracking": "lot",
        })
        env["wt.product"].create({"company_id": company.id, "product_id": product.id})
    warehouse = env["stock.warehouse"].create({
        "name": "Receipt Report QA", "code": "RPTQ", "company_id": company.id, "estate_id": estate.id,
    })
    location = env["wt.weighing.location"].create({
        "name": "Receipt Report QA", "code": "RPTQ", "estate_id": estate.id,
        "allowed_division_ids": [(6, 0, division.ids)],
    })
    rule = env["wt.receipt.rule"].create({
        "weighing_location_id": location.id, "division_id": division.id,
        "warehouse_id": warehouse.id, "operation_type_id": warehouse.in_type_id.id,
        "location_id": warehouse.lot_stock_id.id,
    })
    return {"company": company, "division": division, "product": product,
            "warehouse": warehouse, "location": location, "rule": rule}


def make_report_receipt(env, weighings, setup, state="validated", done=True, receipt=None):
    product = setup["product"]
    warehouse = setup["warehouse"]
    weighings.with_context(allow_production_receipt_update=True).write({
        "weighing_location_id": setup["location"].id, "receipt_rule_id": setup["rule"].id,
        "product_id": product.id,
    })
    if not receipt:
        receipt = env["wt.production.receipt"].create({
            "company_id": setup["company"].id, "division_id": setup["division"].id,
            "production_date": weighings[0].production_date, "received_date": weighings[0].production_date,
            "product_id": product.id, "warehouse_id": warehouse.id,
            "operation_type_id": warehouse.in_type_id.id, "location_id": warehouse.lot_stock_id.id,
        })
    lines = env["wt.production.receipt.line"].create([
        {"receipt_id": receipt.id, "weighing_id": weighing.id} for weighing in weighings
    ])
    lot = env["stock.lot"].create({
        "name": "RPTQ-%s-%s" % (receipt.id, lines[0].id), "company_id": setup["company"].id,
        "product_id": product.id, "division_id": setup["division"].id,
    })
    source = env.ref("stock.stock_location_suppliers")
    picking = env["stock.picking"].create({
        "company_id": setup["company"].id, "production_receipt_id": receipt.id,
        "picking_type_id": warehouse.in_type_id.id, "location_id": source.id,
        "location_dest_id": warehouse.lot_stock_id.id,
    })
    quantity = sum(weighings.mapped("net_weight"))
    move = env["stock.move"].create({
        "company_id": setup["company"].id, "picking_id": picking.id,
        "product_id": product.id, "product_uom": product.uom_id.id,
        "product_uom_qty": quantity, "location_id": source.id,
        "location_dest_id": warehouse.lot_stock_id.id, "picked": True,
        "move_line_ids": [(0, 0, {
            "company_id": setup["company"].id, "picking_id": picking.id,
            "product_id": product.id, "product_uom_id": product.uom_id.id,
            "lot_id": lot.id, "quantity": quantity, "location_id": source.id,
            "location_dest_id": warehouse.lot_stock_id.id,
        })],
    })
    if done:
        move._action_done()
    lines.write({"stock_picking_id": picking.id, "lot_id": lot.id})
    receipt.with_context(allow_production_receipt_update=True).write({
        "state": state, "stock_picking_id": picking.id, "lot_id": lot.id,
    })
    weighings.with_context(allow_production_receipt_update=True).write({
        "state": "receipt_validated" if state == "validated" else (
            "receipt_cancelled" if state == "cancelled" else "in_production_receipt"
        ), "production_receipt_id": receipt.id,
    })
    return receipt, picking
