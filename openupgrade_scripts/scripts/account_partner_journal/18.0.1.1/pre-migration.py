# Copyright 2025 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade, openupgrade_180

# trobz migrate: default_purchase_journal_id: v12 many2one to many2one company_dependent jsonb
def convert_company_dependent(env):
    openupgrade.logged_query(
        env,
        """
        ALTER TABLE res_partner RENAME COLUMN default_purchase_journal_id TO default_purchase_journal_id_temp;
        ALTER TABLE res_partner ADD COLUMN default_purchase_journal_id jsonb;
        """
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_partner SET default_purchase_journal_id = CAST(CAST(default_purchase_journal_id_temp AS text) AS jsonb);
        """,
    )

@openupgrade.migrate()
def migrate(env, version):
    convert_company_dependent(env)