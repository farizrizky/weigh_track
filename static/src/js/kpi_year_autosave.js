/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    IntegerField,
    integerField,
} from "@web/views/fields/integer/integer_field";
import { useInputField } from "@web/views/fields/input_field_hook";
import { useNumpadDecimal } from "@web/views/fields/numpad_decimal_hook";
import { parseInteger } from "@web/views/fields/parsers";

import { useState } from "@odoo/owl";


export class KpiYearAutosaveField extends IntegerField {
    setup() {
        this.state = useState({ hasFocus: false });
        useInputField({
            getValue: () => this.formattedValue,
            refName: "numpadDecimal",
            parse: (value) => parseInteger(value, { allowOperation: true }),
            shouldSave: () => (
                [
                    "wt.kpi.budget.target",
                    "wt.kpi.foreman.budget.target",
                ].includes(this.props.record.resModel) &&
                this.props.record.isNew
            ),
        });
        useNumpadDecimal();
    }
}

registry.category("fields").add("kpi_year_autosave", {
    ...integerField,
    component: KpiYearAutosaveField,
});
