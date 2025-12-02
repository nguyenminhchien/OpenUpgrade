# Copyright 2025 Le Filament (https://le-filament.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade


def _update_existing_tax_accounts(env):
    """
    Configuration of tax account has changed causing issue when updating chart_template
    This function update the 2 problematic tax accounts
    """
    fr_companies = env["res.company"].search([("chart_template", "=", "fr")])
    for company in fr_companies:
        account_44551 = env.ref("account." + str(company.id) + "_pcg_44551", False)

        # trobz migrate: somehow, xml_id in tax account 445511 doesn't have correct
        # xml_id as above, Trobz search code and company directly here
        account_44551_backup = env["account.account"].search(
            [("code", "=", "445510"), ("company_ids", "in", company.id)], limit=1
        )

        if not account_44551:
            logging.info(
                f"not found account_44551, account_44551_backup: {account_44551_backup}"
            )
            account_44551 = account_44551_backup

        if account_44551:
            account_44551.account_type = "liability_payable"
            account_44551.non_trade = True

        account_44567 = env.ref("account." + str(company.id) + "_pcg_44567", False)

        # trobz migrate: somehow, xml_id in tax account 445511 doesn't have correct
        # xml_id as above, Trobz search code and company directly here
        account_44567_backup = env["account.account"].search(
            [("code", "=", "445670"), ("company_ids", "in", company.id)], limit=1
        )
        if not account_44567:
            logging.info(
                f"not found account_44567, account_44567_backup: {account_44551_backup}"
            )
            account_44567 = account_44567_backup

        if account_44567:
            account_44567.account_type = "asset_receivable"
            account_44567.non_trade = True


@openupgrade.migrate()
def migrate(env, version):
    _update_existing_tax_accounts(env)
