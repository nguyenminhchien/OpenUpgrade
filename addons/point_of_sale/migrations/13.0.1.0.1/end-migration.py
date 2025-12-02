# Copyright 2020 ForgeFlow <https://www.forgeflow.com>
# Copyright 2020 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade

# trobz migrate: when run migration, add_default_account_data didn't update properly default_pos_receivable_account_id
# re-run here if necessary
def add_default_account_data(env):
    """v13 introduces some new accounts at company level. We need to ensure
    that the information is filled on existing companies for avoiding problems
    in  subsequent modules (like `point_of_sale`).

    Need to be on end-migration for making sure all chart of templates have
    their data loaded.
    """
    for company in env["res.company"].search([]):
        for chart_field, company_field in [
            ("default_pos_receivable_account_id",
             "account_default_pos_receivable_account_id"),
            ("default_cash_difference_expense_account_id",
             "default_cash_difference_expense_account_id"),
            ("default_cash_difference_income_account_id",
             "default_cash_difference_income_account_id"),
        ]:
            chart = company.chart_template_id
            check_chart = chart
            account_template = False
            while not account_template and check_chart:
                account_template = check_chart[chart_field]
                check_chart = check_chart.parent_id
            if not account_template:
                continue
            tmpl_xml_id = account_template.get_external_id()[account_template.id]
            module, name = tmpl_xml_id.split('.', 1)
            xml_id = "%s.%s_%s" % (module, company.id, name)
            account = env.ref(xml_id, False)
            if not account:
                # Code copied from `generate_account` in `account.chart.template`
                # - can't call it directly as it loads all account templates -
                code_main = account_template.code and len(account_template.code) or 0
                code_acc = account_template.code or ""
                if code_main > 0 and code_main <= chart.code_digits:
                    code_acc = str(code_acc) + (
                        str("0" * (chart.code_digits - code_main)))
                account = env['account.account'].search([
                    ('code', '=', code_acc),
                    ('company_id', '=', company.id),
                ], limit=1)
                # If there's already an account with the same code and company don't create it
                # as it is not allowed by "account_account_code_company_uniq" constraint.
                if not account:
                    tax_template_ref = {}
                    vals = chart._get_account_vals(
                        company, account_template, code_acc, tax_template_ref)
                    account = chart._create_records_with_xmlid(
                        "account.account", [(account_template, vals)], company)
                else:
                    # we add xmlid for such existing account
                    env["ir.model.data"].sudo()._update_xmlids(
                        [dict(xml_id=xml_id, noupdate=True, record=account)])
            company[company_field] = account.id

def create_pos_payment_methods(env):
    """We will create a Payment method for each journal used on configurations"""
    if not openupgrade.column_exists(
            env.cr, "pos_payment_method", "old_journal_id"):
        openupgrade.logged_query(
            env.cr, """
            ALTER TABLE pos_payment_method
            ADD COLUMN old_journal_id int"""
        )
        env.cr.execute("""
               SELECT DISTINCT journal_id
               FROM account_bank_statement abs
               WHERE pos_session_id is not null
           """)
        journal_ids = [aj[0] for aj in env.cr.fetchall()]
        if journal_ids:
            openupgrade.logged_query(env.cr, """
                    INSERT INTO pos_payment_method
                        (
                            old_journal_id,
                            name,
                            receivable_account_id,
                            is_cash_count,
                            cash_journal_id,
                            company_id,
                            create_uid,
                            create_date,
                            write_uid,
                            write_date
                        )
                    SELECT
                        aj.id,
                        aj.name,
                        rc.account_default_pos_receivable_account_id,
                        aj.type = 'cash',
                        CASE WHEN aj.type = 'cash' THEN aj.id ELSE NULL END,
                        rc.id,
                        aj.create_uid,
                        aj.create_date,
                        aj.write_uid,
                        aj.write_date
                    FROM account_journal aj
                    INNER JOIN res_company rc ON rc.id = aj.company_id
                    WHERE aj.id in %s
                """, (tuple(journal_ids),))
        # We will add all options in order to ensure no failures
        openupgrade.logged_query(
            env.cr, """
                INSERT INTO pos_config_pos_payment_method_rel
                    (pos_config_id, pos_payment_method_id)
                SELECT DISTINCT ps.config_id, ppm.id
                FROM account_bank_statement abs
                JOIN pos_payment_method ppm ON abs.journal_id = ppm.old_journal_id
                JOIN pos_session ps ON ps.id = abs.pos_session_id
                WHERE abs.pos_session_id IS NOT NULL
                """)
    env["pos.config"].generate_pos_journal()


def create_pos_payments(env):
    env.cr.execute("""
        SELECT DISTINCT absl.id, ppm.id, absl.pos_statement_id,
            absl.name, absl.amount, absl.create_date
        FROM account_bank_statement abs
        JOIN pos_session ps ON abs.pos_session_id = ps.id
        JOIN account_bank_statement_line absl ON absl.statement_id = abs.id
        LEFT JOIN account_journal aj ON abs.journal_id = aj.id
        JOIN pos_payment_method ppm ON ppm.old_journal_id = aj.id
        WHERE absl.pos_statement_id IS NOT NULL
    """)
    st_lines = env.cr.fetchall()
    if st_lines:
        vals_list = []
        for st_line in st_lines:
            vals = {
                'name': st_line[3],
                'pos_order_id': st_line[2],
                'amount': st_line[4],
                'payment_method_id': st_line[1],
                'payment_date': st_line[5],
            }
            vals_list += [vals]
        env['pos.payment'].create(vals_list)
    # We need to delete all the lines from sessions not validated in order to not
    # disturb validation
    env.cr.execute("""
        SELECT absl.id
         FROM account_bank_statement abs
        JOIN pos_session ps ON abs.pos_session_id = ps.id
        JOIN account_bank_statement_line absl ON absl.statement_id = abs.id
        WHERE absl.pos_statement_id IS NOT NULL AND ps.state != 'closed'
    """)
    st = env.cr.fetchall()
    to_delete = [s[0] for s in st]
    if to_delete:
        openupgrade.logged_query(env.cr, """
            DELETE FROM account_bank_statement_line
            WHERE id in %s
        """, (tuple(to_delete),))
    env["account.bank.statement"].search(
        [("pos_session_id.state", "!=", "closed")]
    )._end_balance()


def fill_stock_warehouse_pos_type_id(env):
    warehouses = env['stock.warehouse'].search([('pos_type_id', '=', False)])
    for warehouse in warehouses:
        if warehouse.get_external_id()[warehouse.id] == "stock.warehouse0":
            # If it's the main warehouse, assign the existing type
            warehouse.pos_type_id = env.ref("point_of_sale.picking_type_posout")
            continue
        color = warehouse.in_type_id.color
        sequence_data = warehouse._get_sequence_values()
        max_sequence = env['stock.picking.type'].search_read(
            [('sequence', '!=', False)], ['sequence'], limit=1,
            order='sequence desc')
        max_sequence = max_sequence and max_sequence[0]['sequence'] or 0
        create_data = warehouse._get_picking_type_create_values(max_sequence)[0]
        picking_type = "pos_type_id"
        sequence = env['ir.sequence'].sudo().create(sequence_data[picking_type])
        create_data[picking_type].update(
            warehouse_id=warehouse.id, color=color, sequence_id=sequence.id)
        warehouse[picking_type] = env['stock.picking.type'].create(
            create_data[picking_type]).id
    # Remove this to disappear XML-ID for avoiding error
    env["ir.model.data"].search([
        ("module", "=", "point_of_sale"),
        ("name", "=", "picking_type_posout"),
    ]).unlink()


def fix_pos_payment_method_config_relation(env):
    """Inserting only the right elements"""
    openupgrade.logged_query(
        env.cr, """DELETE FROM pos_config_pos_payment_method_rel"""
    )
    openupgrade.logged_query(
        env.cr, """
            INSERT INTO pos_config_pos_payment_method_rel
                (pos_config_id, pos_payment_method_id)
            SELECT pos_config_id, ppm.id
            FROM pos_config_journal_rel pcjr
            JOIN pos_payment_method ppm ON pcjr.journal_id = ppm.old_journal_id
            """)


@openupgrade.migrate()
def migrate(env, version):
    add_default_account_data(env)
    create_pos_payment_methods(env)
    create_pos_payments(env)
    fix_pos_payment_method_config_relation(env)
    fill_stock_warehouse_pos_type_id(env)
