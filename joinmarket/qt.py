from PyQt4.QtGui import *
from PyQt4 import QtCore
from electrum.plugins import BasePlugin, hook
from electrum.i18n import _

from decimal import Decimal
from functools import partial
from collections import namedtuple

import datetime, sys, os, base64, textwrap, re, math, json, logging
import Queue, platform, csv, threading, time
from electrum.util import format_satoshis
from electrum.bitcoin import COIN

from electrum_gui.qt.util import *

sys.path.insert(0, os.path.dirname(__file__))

#import joinmarket
from joinmarket_core import load_program_config, get_network, Wallet, get_p2pk_vbyte, \
    jm_single, validate_address, random_nick, get_log, IRCMessageChannel, \
    weighted_order_choose, joinmarket_alert, core_alert, ElectrumWrapWallet

from sendpayment import SendPayment, PT
log = get_log()
donation_address = '1LT6rwv26bV7mgvRosoSCyGM7ttVRsYidP'
donation_address_testnet = 'mz6FQosuiNe8135XaQqWYmXsa3aD8YsqGL'

#configuration types
config_types = {'check_high_fee': int,
                'txfee_default': int,
                'order_wait_time': int
                }
config_tips = {
    'check_high_fee': 'Percent fee considered dangerously high, default 2%',
    'txfee_default': 'Number of satoshis per counterparty for an initial\n' +
    'tx fee estimate; this value is not usually used and is best left at\n' +
    'the default of 5000',
    'order_wait_time': 'How long to wait for orders to arrive on entering\n' +
    'the message channel, default is 30s'
}

def update_config_for_gui():
    '''The default joinmarket config does not contain these GUI settings
    (they are generally set by command line flags or not needed).
    If they are set in the file, use them, else set the defaults.
    These *will* be persisted to joinmarket.cfg, but that will not affect
    operation of the command line version.
    '''
    gui_config_names = ['check_high_fee', 'txfee_default', 'order_wait_time']
    gui_config_default_vals = ['2', '5000', '30']
    if "GUI" not in jm_single().config.sections():
        jm_single().config.add_section("GUI")
    gui_items = jm_single().config.items("GUI")
    for gcn, gcv in zip(gui_config_names, gui_config_default_vals):
        if gcn not in [_[0] for _ in gui_items]:
            jm_single().config.set("GUI", gcn, gcv)



def persist_config():
    '''This loses all comments in the config file.
    TODO: possibly correct that.'''
    with open('joinmarket.cfg', 'w') as f:
        jm_single().config.write(f)

class TaskThread(QtCore.QThread):
    '''Thread that runs background tasks.  Callbacks are guaranteed
    to happen in the context of its parent.'''

    Task = namedtuple("Task", "task cb_success cb_done cb_error")
    doneSig = QtCore.pyqtSignal(object, object, object)

    def __init__(self, parent, on_error=None):
        super(TaskThread, self).__init__(parent)
        self.on_error = on_error
        self.tasks = Queue.Queue()
        self.doneSig.connect(self.on_done)
        self.start()

    def add(self, task, on_success=None, on_done=None, on_error=None):
        on_error = on_error or self.on_error
        self.tasks.put(TaskThread.Task(task, on_success, on_done, on_error))

    def run(self):
        while True:
            task = self.tasks.get()
            if not task:
                break
            try:
                result = task.task()
                self.doneSig.emit(result, task.cb_done, task.cb_success)
            except BaseException:
                self.doneSig.emit(sys.exc_info(), task.cb_done, task.cb_error)

    def on_done(self, result, cb_done, cb):
        # This runs in the parent's thread.
        if cb_done:
            cb_done()
        if cb:
            cb(result)

    def stop(self):
        self.tasks.put(None)

class XStream(QtCore.QObject):
    _stdout = None
    _stderr = None
    messageWritten = QtCore.pyqtSignal(str)

    def flush(self):
        pass

    def fileno(self):
        return -1

    def write(self, msg):
        if (not self.signalsBlocked()):
            self.messageWritten.emit(unicode(msg))

    @staticmethod
    def stdout():
        if (not XStream._stdout):
            XStream._stdout = XStream()
            sys.stdout = XStream._stdout
        return XStream._stdout

    @staticmethod
    def stderr():
        if (not XStream._stderr):
            XStream._stderr = XStream()
            sys.stderr = XStream._stderr
        return XStream._stderr

    
def JMQtMessageBox(obj, msg, mbtype='info', title=''):
    mbtypes = {'info': QMessageBox.information,
               'crit': QMessageBox.critical,
               'warn': QMessageBox.warning,
               'question': QMessageBox.question}
    title = "JoinmarketQt - " + title
    if mbtype == 'question':
        return QMessageBox.question(obj, title, msg, QMessageBox.Yes,
                                    QMessageBox.No)
    else:
        mbtypes[mbtype](obj, title, msg)

class JoinmarketTab(QWidget):

    def __init__(self, plugin):
        super(JoinmarketTab, self).__init__()
        self.plugin = plugin
        self.initUI()

    def initUI(self):
        vbox = QVBoxLayout(self)
        top = QFrame()
        top.setFrameShape(QFrame.StyledPanel)
        topLayout = QGridLayout()
        top.setLayout(topLayout)
        sA = QScrollArea()
        sA.setWidgetResizable(True)
        topLayout.addWidget(sA)
        iFrame = QFrame()
        sA.setWidget(iFrame)
        innerTopLayout = QGridLayout()
        innerTopLayout.setSpacing(4)
        iFrame.setLayout(innerTopLayout)

        donateLayout = QHBoxLayout()
        self.donateCheckBox = QCheckBox()
        self.donateCheckBox.setChecked(False)
        self.donateCheckBox.setMaximumWidth(30)
        self.donateLimitBox = QDoubleSpinBox()
        self.donateLimitBox.setMinimum(0.001)
        self.donateLimitBox.setMaximum(0.100)
        self.donateLimitBox.setSingleStep(0.001)
        self.donateLimitBox.setDecimals(3)
        self.donateLimitBox.setValue(0.010)
        self.donateLimitBox.setMaximumWidth(100)
        self.donateLimitBox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        donateLayout.addWidget(self.donateCheckBox)
        label1 = QLabel("Check to send change lower than: ")
        label1.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        donateLayout.addWidget(label1)
        donateLayout.setAlignment(label1, QtCore.Qt.AlignLeft)
        donateLayout.addWidget(self.donateLimitBox)
        donateLayout.setAlignment(self.donateLimitBox, QtCore.Qt.AlignLeft)
        label2 = QLabel(" BTC as a donation.")
        donateLayout.addWidget(label2)
        label2.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        donateLayout.setAlignment(label2, QtCore.Qt.AlignLeft)
        label3 = HelpLabel('More', '\n'.join(
            ['If the calculated change for your transaction',
             'is smaller than the value you choose (default 0.01 btc)',
             'then that change is sent as a donation. If your change',
             'is larger than that, there will be no donation.', '',
             'As well as helping the developers, this feature can,',
             'in certain circumstances, improve privacy, because there',
             'is no change output that can be linked with your inputs later.']))
        label3.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        donateLayout.setAlignment(label3, QtCore.Qt.AlignLeft)
        donateLayout.addWidget(label3)
        donateLayout.addStretch(1)
        innerTopLayout.addLayout(donateLayout, 0, 0, 1, 2)

        self.widgets = self.getSettingsWidgets()
        for i, x in enumerate(self.widgets):
            innerTopLayout.addWidget(x[0], i + 1, 0)
            innerTopLayout.addWidget(x[1], i + 1, 1, 1, 2)
        self.widgets[0][1].editingFinished.connect(
            lambda: self.checkAddress(self.widgets[0][1].text()))
        self.startButton = QPushButton('Start')
        self.startButton.setToolTip(
            'You will be prompted to decide whether to accept\n' +
            'the transaction after connecting, and shown the\n' +
            'fees to pay; you can cancel at that point if you wish.')
        self.startButton.clicked.connect(self.startSendPayment)
        #TODO: how to make the Abort button work, at least some of the time..
        self.abortButton = QPushButton('Abort')
        self.abortButton.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.startButton)
        buttons.addWidget(self.abortButton)
        innerTopLayout.addLayout(buttons, len(self.widgets) + 1, 0, 1, 2)
        splitter1 = QSplitter(QtCore.Qt.Vertical)
        self.textedit = QTextEdit()
        self.textedit.verticalScrollBar().rangeChanged.connect(
            self.resizeScroll)
        XStream.stdout().messageWritten.connect(self.updateConsoleText)
        XStream.stderr().messageWritten.connect(self.updateConsoleText)
        splitter1.addWidget(top)
        splitter1.addWidget(self.textedit)
        splitter1.setSizes([400, 200])
        self.setLayout(vbox)
        vbox.addWidget(splitter1)
        
    def updateConsoleText(self, txt):
        self.textedit.insertPlainText(txt)

    def checkAddress(self, addr):
        valid, errmsg = validate_address(str(addr))
        if not valid:
            JMQtMessageBox(self,
                           "Bitcoin address not valid.\n" + errmsg,
                           mbtype='warn',
                           title="Error")

    def validateSettings(self):
        valid, errmsg = validate_address(self.widgets[0][1].text())
        if not valid:
            JMQtMessageBox(self, errmsg, mbtype='warn', title="Error")
            return False
        errs = ["Non-zero number of counterparties must be provided.",
                "Mixdepth must be chosen.",
                "Amount, in bitcoins, must be provided."]
        for i in range(1, 4):
            if self.widgets[i][1].text().size() == 0:
                JMQtMessageBox(self, errs[i - 1], mbtype='warn', title="Error")
                return False
        #QIntValidator does not prevent entry of 0 for counterparties.
        #Note, use of '1' is not recommended, but not prevented here.
        if self.widgets[1][1].text() == '0':
            JMQtMessageBox(self, errs[0], mbtype='warn', title="Error")
            return False
        return True

    def startSendPayment(self, ignored_makers=None):
        self.aborted = False
        if not self.validateSettings():
            return

        #all settings are valid; start
        #Disabling for now; interrupts workflow unnecessarily.
        #May need to revisit in future.
        #JMQtMessageBox(
        #    self,
        #    "Connecting to IRC.\nView real-time log in the lower pane.",
        #    title="Sendpayment")
        self.startButton.setEnabled(False)
        self.abortButton.setEnabled(True)

        jm_single().nickname = random_nick()

        log.debug('starting sendpayment')

        self.irc = IRCMessageChannel(jm_single().nickname)
        self.destaddr = str(self.widgets[0][1].text())
        #convert from bitcoins (enforced by QDoubleValidator) to satoshis
        self.btc_amount_str = str(self.widgets[3][1].text())
        amount = int(Decimal(self.btc_amount_str) * Decimal('1e8'))
        makercount = int(self.widgets[1][1].text())
        #ignoring mixdepth for now
        #mixdepth = int(self.widgets[2][1].text())
        mixdepth = 0
        if self.plugin.wallet.use_encryption:
            msg = []
            msg.append(_("Enter your password to proceed"))
            self.plugin.wrap_wallet.password = self.plugin.window.password_dialog(
                '\n'.join(msg))
            try:
                self.plugin.wallet.check_password(self.plugin.wrap_wallet.password)
            except Exception as e:
                JMQtMessageBox(self, "Wrong password: " + str(e), mbtype='crit')
                self.giveUp()
                return

        self.taker = SendPayment(
            self.irc,
            self.plugin.wrap_wallet,
            self.destaddr,
            amount,
            makercount,
            jm_single().config.getint("GUI", "txfee_default"),
            jm_single().config.getint("GUI", "order_wait_time"),
            mixdepth,
            False,
            weighted_order_choose,
            isolated=True)
        self.pt = PT(self.taker)
        if ignored_makers:
            self.pt.ignored_makers.extend(ignored_makers)
        
        thread = TaskThread(self)
        thread.add(self.runIRC, on_done=self.cleanUp)
        self.plugin.window.statusBar().showMessage("Connecting to IRC ...")
        thread2 = TaskThread(self)
        thread2.add(self.createTxThread, on_done=self.doTx)

    def createTxThread(self):
        self.orders, self.total_cj_fee, self.cjamount, self.utxos = self.pt.create_tx(
        )
        log.debug("Finished create_tx")
        #TODO this can't be done in a thread as currently built;
        #how else? or fix?
        #w.statusBar().showMessage("Found counterparties...")

    def doTx(self):
        if not self.orders:
            JMQtMessageBox(self,
                           "Not enough matching orders found.",
                           mbtype='warn',
                           title="Error")
            self.giveUp()
            return

        total_fee_pc = 1.0 * self.total_cj_fee / self.cjamount

        #reset the btc amount display string if it's a sweep:
        if self.taker.amount == 0:
            self.btc_amount_str = str((Decimal(self.cjamount) / Decimal('1e8')))

        #TODO separate this out into a function
        mbinfo = []
        if joinmarket_alert[0]:
            mbinfo.append("<b><font color=red>JOINMARKET ALERT: " +
                          joinmarket_alert[0] + "</font></b>")
            mbinfo.append(" ")
        if core_alert[0]:
            mbinfo.append("<b><font color=red>BITCOIN CORE ALERT: " +
                          core_alert[0] + "</font></b>")
            mbinfo.append(" ")
        mbinfo.append("Sending amount: " + self.btc_amount_str + " BTC")
        mbinfo.append("to address: " + self.destaddr)
        mbinfo.append(" ")
        mbinfo.append("Counterparties chosen:")
        mbinfo.append('Name,     Order id, Coinjoin fee (sat.)')
        for k, o in self.orders.iteritems():
            if o['ordertype'] == 'relorder':
                display_fee = int(self.cjamount *
                                  float(o['cjfee'])) - int(o['txfee'])
            elif o['ordertype'] == 'absorder':
                display_fee = int(o['cjfee']) - int(o['txfee'])
            else:
                log.debug("Unsupported order type: " + str(o['ordertype']) +
                          ", aborting.")
                self.giveUp()
                return
            mbinfo.append(k + ', ' + str(o['oid']) + ',         ' + str(
                display_fee))
        mbinfo.append('Total coinjoin fee = ' + str(self.total_cj_fee) +
                      ' satoshis, or ' + str(float('%.3g' % (
                          100.0 * total_fee_pc))) + '%')
        title = 'Check Transaction'
        if total_fee_pc * 100 > jm_single().config.getint("GUI",
                                                          "check_high_fee"):
            title += ': WARNING: Fee is HIGH!!'
        reply = JMQtMessageBox(self,
                               '\n'.join([m + '<p>' for m in mbinfo]),
                               mbtype='question',
                               title=title)
        if reply == QMessageBox.Yes:
            log.debug('You agreed, transaction proceeding')
            self.showStatusBarMsg("Building transaction...")
            thread3 = TaskThread(self)
            log.debug("Trigger is: " + str(self.donateLimitBox.value()))
            if get_network() == 'testnet':
                da = donation_address_testnet
            else:
                da = donation_address
            thread3.add(
                partial(self.pt.do_tx, self.total_cj_fee, self.orders,
                        self.cjamount, self.utxos,
                        self.donateCheckBox.isChecked(),
                        self.donateLimitBox.value(), da),
                on_done=None)
        else:
            self.giveUp()
            return

    def runIRC(self):
        try:
            log.debug('starting irc')
            self.irc.run()
        except:
            log.debug('CRASHING, DUMPING EVERYTHING')
            #doesn't really work for electrum wallet
            #debug_dump_object(w.wallet, ['addr_cache', 'keys', 'wallet_name',
            #                             'seed'])
            debug_dump_object(self.taker)
            import traceback
            log.debug(traceback.format_exc())

    def cleanUp(self):
        if not self.taker.txid:
            if not self.aborted:
                if not self.pt.ignored_makers:
                    self.showStatusBarMsg("Transaction failed.")
                    JMQtMessageBox(self,
                                   "Transaction was not completed.",
                                   mbtype='warn',
                                   title="Failed")
                else:
                    reply = JMQtMessageBox(
                        self,
                        '\n'.join([
                            "The following counterparties did not respond: ",
                            ','.join(self.pt.ignored_makers),
                            "This sometimes happens due to bad network connections.",
                            "",
                            "If you would like to try again, ignoring those",
                            "counterparties, click Yes."
                        ]),
                        mbtype='question',
                        title="Transaction not completed.")
                    if reply == QMessageBox.Yes:
                        self.startSendPayment(
                            ignored_makers=self.pt.ignored_makers)
                    else:
                        self.giveUp()
                        return

        else:
            self.showStatusBarMsg("Transaction completed successfully.")
            JMQtMessageBox(self,
                           "Transaction has been broadcast.\n" + "Txid: " +
                           str(self.taker.txid),
                           title="Success")
            #no history persistence necessary for Electrum; Electrum does it.

        self.startButton.setEnabled(True)
        self.abortButton.setEnabled(False)

    def giveUp(self):
        self.aborted = True
        #re-require password for next try
        self.plugin.wrap_wallet.password = None
        log.debug("Transaction aborted.")
        self.taker.msgchan.shutdown()
        self.abortButton.setEnabled(False)
        self.startButton.setEnabled(True)
        self.showStatusBarMsg("Transaction aborted.")

    def showStatusBarMsg(self, msg):
        sbmsg = [_("JoinMarket:")]
        sbmsg.append(_(msg))
        self.plugin.window.statusBar().showMessage("".join(sbmsg))

    def getSettingsWidgets(self):
        results = []
        sN = ['Recipient address', 'Number of counterparties', 'Mixdepth',
              'Amount in bitcoins (BTC)']
        sH = ['The address you want to send the payment to',
              'How many other parties to send to; if you enter 4\n' +
              ', there will be 5 participants, including you',
              'The mixdepth of the wallet to send the payment from',
              'The amount IN BITCOINS to send.\n' +
              'If you enter 0, a SWEEP transaction\nwill be performed,' +
              ' spending all the coins \nin the given mixdepth.']
        sT = [str, int, int, float]
        #todo maxmixdepth
        sMM = ['', (2, 20),
               (0, 4),
               (0.00000001, 100.0, 8)]
        sD = ['', '3', '0', '']
        for x in zip(sN, sH, sT, sD, sMM):
            ql = QLabel(x[0])
            ql.setToolTip(x[1])
            qle = QLineEdit(x[3])
            if x[2] == int:
                qle.setValidator(QIntValidator(*x[4]))
            if x[2] == float:
                qle.setValidator(QDoubleValidator(*x[4]))
            results.append((ql, qle))
        return results
    
    def resizeScroll(self, mini, maxi):
        self.textedit.verticalScrollBar().setValue(maxi)    


class SettingsDialog(QDialog):

    def __init__(self):
        super(SettingsDialog, self).__init__()
        self.initUI()

    def closeEvent(self, event):
        log.debug("Closing settings and persisting")
        persist_config()
        event.accept()

    def initUI(self):
        outerGrid = QGridLayout()
        sA = QScrollArea()
        sA.setWidgetResizable(True)
        frame = QFrame()
        grid = QGridLayout()
        self.settingsFields = []
        j = 0
        #Simplified from Joinmarket-Qt: just one section;
        #most internal settings are not relevant for Electrum
        section = "GUI"
        pairs = jm_single().config.items(section)
        newSettingsFields = self.getSettingsFields(section,
                                                   [_[0] for _ in pairs])
        self.settingsFields.extend(newSettingsFields)
        sL = QLabel(section)
        sL.setStyleSheet("QLabel {color: blue;}")
        grid.addWidget(sL)
        j += 1
        for k, ns in enumerate(newSettingsFields):
            grid.addWidget(ns[0], j, 0)
            #try to find the tooltip for this label from config tips;
            #it might not be there
            if str(ns[0].text()) in config_tips:
                ttS = config_tips[str(ns[0].text())]
                ns[0].setToolTip(ttS)
            grid.addWidget(ns[1], j, 1)
            sfindex = len(self.settingsFields) - len(newSettingsFields) + k
            if isinstance(ns[1], QCheckBox):
                ns[1].toggled.connect(lambda checked, s=section,
                                      q=sfindex: self.handleEdit(
                                s, self.settingsFields[q], checked))
            else:
                ns[1].editingFinished.connect(
                lambda q=sfindex, s=section: self.handleEdit(s,
                                                  self.settingsFields[q]))
            j += 1
        outerGrid.addWidget(sA)
        sA.setWidget(frame)
        frame.setLayout(grid)
        frame.adjustSize()
        self.setLayout(outerGrid)
        self.show()

    def handleEdit(self, section, t, checked=None):
        if isinstance(t[1], QCheckBox):
            if str(t[0].text()) == 'Testnet':
                oname = 'network'
                oval = 'testnet' if checked else 'mainnet'
                add = '' if not checked else ' - Testnet'
                w.setWindowTitle(appWindowTitle + add)
            else:
                oname = str(t[0].text())
                oval = 'true' if checked else 'false'
            log.debug('setting section: ' + section + ' and name: ' + oname +
                      ' to: ' + oval)
            jm_single().config.set(section, oname, oval)

        else:  #currently there is only QLineEdit
            log.debug('setting section: ' + section + ' and name: ' + str(t[
                0].text()) + ' to: ' + str(t[1].text()))
            jm_single().config.set(section, str(t[0].text()), str(t[1].text()))
            if str(t[0].text()) == 'blockchain_source':
                jm_single().bc_interface = get_blockchain_interface_instance(
                    jm_single().config)

    def getSettingsFields(self, section, names):
        results = []
        for name in names:
            val = jm_single().config.get(section, name)
            if name in config_types:
                t = config_types[name]
                if t == bool:
                    qt = QCheckBox()
                    if val == 'testnet' or val.lower() == 'true':
                        qt.setChecked(True)
                elif not t:
                    continue
                else:
                    qt = QLineEdit(val)
                    if t == int:
                        qt.setValidator(QIntValidator(0, 65535))
            else:
                qt = QLineEdit(val)
            label = 'Testnet' if name == 'network' else name
            results.append((QLabel(label), qt))
        return results


class Plugin(BasePlugin):
        
    def is_available(self):
        return True

    def requires_settings(self):
        return True

    def settings_widget(self, window):
        """Create the settings button
        """
        self.settings_window = window
        return EnterButton(_('Settings'), self.settings_dialog)

    def settings_dialog(self, x):
        """Present settings for that subset
        of the config variables that are still
        needed for Electrum.
        """
        d = SettingsDialog()
        d.setWindowTitle("Joinmarket settings")
        if not d.exec_():
            return

    @hook
    def on_new_window(self, window):
        self.window = window

    @hook
    def load_wallet(self, wallet, window):
        """The main entry point for the joinmarket
        plugin; create the joinmarket tab and
        initialize the joinmarket_core code.
        """
        load_program_config()
        update_config_for_gui()
        #refuse to load the plugin for non-standard wallets.
        if wallet.wallet_type != "standard":
            return
        #set the access to the network for the custom
        #dummy blockchain interface (reads blockchain via wallet.network)
        jm_single().bc_interface.set_wallet(wallet)
        self.wallet = wallet
        self.window = window
        self.account = self.window.current_account
        self.wrap_wallet = ElectrumWrapWallet(self.wallet, self.account)
        self.jmtab = JoinmarketTab(self)
        self.jmtab.updateConsoleText("blah")
        window.tabs.addTab(self.jmtab, _('Joinmarket'))

    @hook
    def create_send_tab(self, grid):
        """Add custom button for sending
        via coinjoin.
        """
        print "creating custom send tab"
        b = QPushButton(_("Send with coinjoin"))
        buttons = QHBoxLayout()
        buttons.addWidget(b)
        grid.addLayout(buttons, 7, 1, 1, 1)
        b.clicked.connect(lambda: self.show_joinmarket_tab(grid))

    def show_joinmarket_tab(self, obj):
        """Activate the joinmarket tab.
        """
        #set the joinmarket tab amount and destination
        #fields, if they are already in the send tab.
        amt_sats_from_send = self.window.amount_e.get_amount()
        if not amt_sats_from_send:
            amount_btc = ""
        else:
            #convert satoshis to bitcoins
            amount_btc = str(Decimal(amt_sats_from_send) / Decimal('1e8'))
        receiving_addr = self.window.payto_e.toPlainText()
        if not receiving_addr:
            receiving_addr = ""
        self.jmtab.widgets[3][1].setText(amount_btc)
        self.jmtab.widgets[0][1].setText(receiving_addr)

        #It might be possible that the Joinmarket tab
        #is not accessible, or the main window, hence
        #the exception catch (nothing to do).
        try:
            ind = self.window.tabs.indexOf(self.jmtab)
            self.window.tabs.setCurrentIndex(ind)
        except:
            return

