from electrum.i18n import _

fullname = 'Joinmarket coinjoin plugin for Electrum.'
description = _(" ".join(["Ability to send payments as coinjoins with counterparties.",
                          "Paying minimal fees, you can immediately send your coins",
                          "with much better privacy. See https://github.com/joinmarket-org/joinmarket",
                          "for more details."]))
requires = [('joinmarket_core','github.com/Joinmarket-Org/joinmarket_core')]
#TODO: setting it here results in Joinmarket never loading.
#It seems that Electrum will not load a plugin on startup if
#it has any setting here.
#requires_wallet_type = ['standard']
available_for = ['qt']