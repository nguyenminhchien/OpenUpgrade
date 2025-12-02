# SPDX-FileCopyrightText: 2024 Tecnativa - Pedro M. Baeza
# SPDX-License-Identifier: AGPL-3.0-or-later

from openupgradelib import openupgrade


def _assign_pos_order_token(env):
    # trobz migrate: enable gen_random_uuid function for later use
    openupgrade.logged_query(env.cr, "CREATE EXTENSION pgcrypto;")
    openupgrade.add_fields(
        env,
        [("access_token", "pos.order", "pos_order", "char", False, "point_of_sale")],
    )
    openupgrade.logged_query(
        env.cr, "UPDATE pos_order SET access_token = gen_random_uuid();"
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.add_fields(
        env,
        [
            (
                "cash_register_balance_start",
                "pos.session",
                "pos_session",
                "monetary",
                False,
                "point_of_sale",
            )
        ],
    )
    _assign_pos_order_token(env)
