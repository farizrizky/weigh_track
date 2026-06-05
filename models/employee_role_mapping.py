from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EmployeeRoleMapping(models.Model):
    _name = "wt.employee.role.mapping"
    _description = "Employee Role Mapping"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, role"

    ROLE_SELECTION = [
        ("operator", "Operator"),
        ("clerk", "Clerk"),
        ("foreman", "Foreman"),
        ("tapper", "Tapper"),
    ]

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    role = fields.Selection(
        ROLE_SELECTION,
        required=True,
        index=True,
        tracking=True,
    )
    job_id = fields.Many2one(
        "hr.job",
        string="Job Position",
        ondelete="restrict",
        index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )

    _sql_constraints = [
        (
            "company_role_job_uniq",
            "unique(company_id, role, job_id)",
            "Employee role mapping must be unique per company, role, and job position.",
        ),
    ]

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_employee_role_mapping
            DROP CONSTRAINT IF EXISTS wt_employee_role_mapping_company_role_uniq
            """
        )
        self.env.cr.execute(
            """
            DO $$
            DECLARE
                mapping_job RECORD;
            BEGIN
                IF to_regclass('wt_employee_role_mapping_hr_job_rel') IS NOT NULL THEN
                    FOR mapping_job IN
                        SELECT
                            mapping.id AS mapping_id,
                            mapping.company_id AS company_id,
                            mapping.role AS role,
                            mapping.create_uid AS create_uid,
                            mapping.write_uid AS write_uid,
                            relation.job_id AS job_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY mapping.id
                                ORDER BY relation.job_id
                            ) AS sequence
                        FROM wt_employee_role_mapping AS mapping
                        JOIN wt_employee_role_mapping_hr_job_rel AS relation
                            ON relation.mapping_id = mapping.id
                        WHERE mapping.job_id IS NULL
                    LOOP
                        IF mapping_job.sequence = 1 THEN
                            UPDATE wt_employee_role_mapping
                            SET job_id = mapping_job.job_id
                            WHERE id = mapping_job.mapping_id
                                AND job_id IS NULL;
                        ELSIF NOT EXISTS (
                            SELECT 1
                            FROM wt_employee_role_mapping
                            WHERE company_id = mapping_job.company_id
                                AND role = mapping_job.role
                                AND job_id = mapping_job.job_id
                        ) THEN
                            INSERT INTO wt_employee_role_mapping (
                                company_id,
                                role,
                                job_id,
                                create_uid,
                                create_date,
                                write_uid,
                                write_date
                            )
                            VALUES (
                                mapping_job.company_id,
                                mapping_job.role,
                                mapping_job.job_id,
                                COALESCE(mapping_job.create_uid, 1),
                                NOW(),
                                COALESCE(
                                    mapping_job.write_uid,
                                    COALESCE(mapping_job.create_uid, 1)
                                ),
                                NOW()
                            );
                        END IF;
                    END LOOP;
                END IF;
            END $$;
            """
        )

    @api.constrains("job_id")
    def _check_job_position_required(self):
        for mapping in self:
            if not mapping.job_id:
                raise ValidationError(_("Job position must be selected."))

    @api.depends("company_id", "role", "job_id")
    def _compute_name(self):
        role_labels = dict(self.ROLE_SELECTION)
        for mapping in self:
            role_label = role_labels.get(mapping.role, "")
            mapping.name = "%s - %s - %s" % (
                mapping.company_id.name or "",
                role_label,
                mapping.job_id.name or "",
            )

    @api.constrains("company_id", "job_id")
    def _check_job_position_company(self):
        for mapping in self:
            if mapping.job_id.company_id and mapping.job_id.company_id != mapping.company_id:
                raise ValidationError(
                    _("Job position must belong to the same company as the mapping.")
                )

    @api.model
    def _get_mappings(self, company, role):
        if not company or not role:
            return self.browse()
        return self.search(
            [
                ("company_id", "=", company.id),
                ("role", "=", role),
            ]
        )

    @api.model
    def get_employee_domain(self, company, role):
        domain = []
        if not company:
            return domain

        domain.append(("company_id", "=", company.id))
        mappings = self._get_mappings(company, role)
        domain.append(("job_id", "in", mappings.mapped("job_id").ids))
        return domain

    @api.model
    def get_allowed_employees(self, company, role):
        return self.env["hr.employee"].search(self.get_employee_domain(company, role))

    @api.model
    def check_employee_allowed(self, employee, company, role, label):
        if not employee:
            return

        if company and employee.company_id != company:
            raise ValidationError(
                _("%s employee must belong to the same company.") % label
            )

        mappings = self._get_mappings(company, role)
        if not mappings:
            raise ValidationError(
                _("%s role mapping has not been configured for this company.") % label
            )

        if employee.job_id not in mappings.mapped("job_id"):
            raise ValidationError(
                _("%s employee must use an allowed job position for this company.")
                % label
            )
