from electrum.i18n import _

fullname = 'Joinmarket coinjoin plugin for Electrum.'
description = _(" ".join(["Ability to send payments as coinjoins with counterparties.",
                          "Paying minimal fees, you can immediately send your coins",
                          "with much better privacy. See https://github.com/joinmarket-org/joinmarket",
                          "for more details."]))
requires = [('joinmarket_core','github.com/Joinmarket-Org/joinmarket_core')]
requires_wallet_type = ['standard']
available_for = ['qt']
