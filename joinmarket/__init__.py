from electrum.i18n import _

fullname = 'Joinmarket coinjoins'
description = _(" ".join(["Ability to send payments as coinjoins with counterparties.",
                          "Paying minimal fees, you can immediately send your coins",
                          "with much better privacy. See https://github.com/joinmarket-org/joinmarket",
                          "for more details."]))
requires = [('jmclient','github.com/Joinmarket-Org/joinmarket-clientserver'),
            ('twisted', 'twistedmatrix.com')]
#TODO: setting it here results in Joinmarket never loading.
#It seems that Electrum will not load a plugin on startup if
#it has any setting here.
#requires_wallet_type = ['standard']
available_for = ['qt']
