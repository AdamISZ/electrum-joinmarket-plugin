from PyQt4.QtGui import *
from PyQt4 import QtCore
from electrum.plugins import BasePlugin, hook
from electrum.i18n import _
from electrum_gui.qt.util import *

from functools import partial

import sys, os

sys.path.insert(0, os.path.dirname(__file__))

from jmclient import (load_program_config, jm_single, get_log,
                      set_commitment_file)
from walletwrap import ElectrumWrapWallet
from joinmarket_gui import (JMQtMessageBox, JoinmarketTab, SettingsDialog,
                            update_config_for_gui)
log = get_log()

class Plugin(BasePlugin):

    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.in_use = False
        self.config_location = None
        self.started = False

    @hook
    def init_qt(self, gui):
        """We actually only support one
        main ElectrumWindow; TODO perhaps simplify
        """
        for window in gui.windows:
            self.on_new_window(window)

    def is_available(self):
        return True

    def requires_settings(self):
        return True

    def settings_widget(self, window):
        """Create the settings button
        """
        self.settings_window = window
        return EnterButton(_('Settings'), partial(self.settings_dialog, window))

    def settings_dialog(self, window):
        """Present settings for that subset
        of the config variables that are still
        needed for Electrum.
        """
        d = SettingsDialog(self.config_location)
        d.setWindowTitle("Joinmarket settings")
        if not d.exec_():
            return

    @hook
    def on_new_window(self, window):
        """Load the joinmarket tab/code into
        this window only once.
        """
        if not self.in_use:
            self.load_wallet(window.wallet, window)
            self.in_use = True

    def on_close(self):
        """Delete the joinmarket tab when the plugin
        is closed/disabled.
        """
        jmtab_index = self.window.tabs.indexOf(self.jmtab)
        if jmtab_index == -1:
            log.debug("Weirdly the joinmarket tab doesnt exist")
            return
        self.window.tabs.removeTab(jmtab_index)

    def load_config(self, window):
        """Load/instantiate the joinmarket config file
        in electrum's home directory/joinmarket (e.g. ~/.electrum/joinmarket
        Also load/instantiate the logs/ subdirectory for bot logs,
        and the cmtdata/ directory for commitments storage.
        Create and set the commitments.json file.
        """
        try:
            jm_subdir = os.path.join(window.config.path, "joinmarket")
            if not os.path.exists(jm_subdir):
                os.makedirs(jm_subdir)
            cmttools_dir = os.path.join(jm_subdir, "cmtdata")
            if not os.path.exists(cmttools_dir):
                os.makedirs(cmttools_dir)
            set_commitment_file(os.path.join(cmttools_dir, "commitments.json"))
            self.config_location = os.path.join(jm_subdir, "joinmarket.cfg")
            self.logs_location = os.path.join(jm_subdir, "logs")
            load_program_config(jm_subdir, "electrum")
        except:
            JMQtMessageBox(window,
                           "\n".join([
                               "The joinmarket config failed to load.",
                               "Make sure that blockchain_source = electrum",
                               "is set in the joinmarket.cfg file."]),
                           mbtype='warn',
                           title="Error")
            return
        if not os.path.exists(self.logs_location):
            os.makedirs(self.logs_location)
        update_config_for_gui()

    @hook
    def load_wallet(self, wallet, window):
        """The main entry point for the joinmarket
        plugin; create the joinmarket tab and
        initialize the joinmarket_core code.
        """
        #can get called via direct hook or on_new_window
        #(the latter happens if we just enabled it in the plugins menu).
        #Insist on loading only once.
        if self.started:
            return
        #refuse to load the plugin for non-standard wallets.
        if wallet.wallet_type != "standard":
            return
        if not self.config_location:
            self.load_config(window)
        #set the access to the network for the custom
        #dummy blockchain interface (reads blockchain via wallet.network)
        jm_single().bc_interface.set_wallet(wallet)
        self.wallet = wallet
        self.window = window
        self.wrap_wallet = ElectrumWrapWallet(self.wallet)
        self.jmtab = JoinmarketTab(self)
        self.window.tabs.addTab(self.jmtab, _('Joinmarket'))
        self.started = True

    @hook
    def create_send_tab(self, grid):
        """Add custom button for sending
        via coinjoin.
        """
        b = QPushButton(_("Send with coinjoin"))
        buttons = QHBoxLayout()
        buttons.addWidget(b)
        #TODO this seems to be dependent on a fixed send tab
        #grid layout; there should be a better way than hardcoded
        #positions.
        grid.addLayout(buttons, 7, 1, 1, 1)
        b.clicked.connect(lambda: self.show_joinmarket_tab())

    def show_joinmarket_tab(self):
        """Activate the joinmarket tab.
        Cross-populate address and amount if they're set.
        """
        #set the joinmarket tab amount and destination
        #fields, if they are already in the send tab.
        amt_sats_from_send = self.window.amount_e.get_amount()
        receiving_addr = self.window.payto_e.toPlainText()
        if not receiving_addr:
            receiving_addr = ""
        self.jmtab.widgets[3][1].setAmount(amt_sats_from_send)
        self.jmtab.widgets[0][1].setText(receiving_addr)

        #It might be possible that the Joinmarket tab
        #is not accessible, or the main window, hence
        #the exception catch (nothing to do).
        try:
            ind = self.window.tabs.indexOf(self.jmtab)
            self.window.tabs.setCurrentIndex(ind)
        except:
            return

