from PyQt4.QtGui import *
from PyQt4 import QtCore
from functools import partial
from collections import namedtuple
from decimal import Decimal
import sys, os
import Queue
import logging

from electrum.i18n import _
from electrum_gui.qt.util import *
from electrum_gui.qt.amountedit import BTCAmountEdit
sys.path.insert(0, os.path.dirname(__file__))

#import joinmarket
from jmbase import (debug_dump_object, joinmarket_alert, core_alert)
from jmclient import (
    Taker, load_program_config, JMTakerClientProtocolFactory, start_reactor,
    validate_address, jm_single, get_log, choose_orders, choose_sweep_orders,
    cheapest_order_choose, weighted_order_choose, estimate_tx_fee)

log = get_log()

#configuration types
config_types = {'check_high_fee': int,
                'txfee_default': int,
                'order_wait_time': int,
                'port': int,
                'usessl': bool,
                'socks5': bool,
                'socks5_port': int,}
config_tips = {
    'check_high_fee': 'Percent fee considered dangerously high, default 2%',
    'txfee_default': 'Number of satoshis per counterparty for an initial\n' +
    'tx fee estimate; this value is not usually used and is best left at\n' +
    'the default of 5000',
    'order_wait_time': 'How long to wait for orders to arrive on entering\n' +
    'the message channel, default is 30s',
    'host': 'hostname for IRC server',
    'channel': 'channel name on IRC server',
    'port': 'port for connecting to IRC server',
    'usessl': 'check to use SSL for connection to IRC',
    'socks5': 'check to use SOCKS5 proxy for IRC connection',
    'socks5_host': 'host for SOCKS5 proxy',
    'socks5_port': 'port for SOCKS5 proxy',
    'daemon_port': 'port on which the joinmarket daemon is running',
}


def update_config_for_gui():
    '''The default joinmarket config does not contain these GUI settings
    (they are generally set by command line flags or not needed).
    If they are set in the file, use them, else set the defaults.
    These *will* be persisted to joinmarket.cfg, but that will not affect
    operation of the command line version.
    '''
    gui_config_names = ['check_high_fee', 'txfee_default', 'order_wait_time',
                        'daemon_port']
    gui_config_default_vals = ['2', '5000', '30', '27183']
    if "GUI" not in jm_single().config.sections():
        jm_single().config.add_section("GUI")
    gui_items = jm_single().config.items("GUI")
    for gcn, gcv in zip(gui_config_names, gui_config_default_vals):
        if gcn not in [_[0] for _ in gui_items]:
            jm_single().config.set("GUI", gcn, gcv)


def persist_config(file_path):
    '''This loses all comments in the config file.
    TODO: possibly correct that.'''
    with open(file_path, 'w') as f:
        jm_single().config.write(f)

class QtHandler(logging.Handler):

    def __init__(self):
        logging.Handler.__init__(self)

    def emit(self, record):
        record = self.format(record)
        if record: XStream.stdout().write('%s\n' % record)


handler = QtHandler()
handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
log.addHandler(handler)


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
    title = "Joinmarket - " + title
    if mbtype == 'question':
        return QMessageBox.question(obj, title, msg, QMessageBox.Yes,
                                    QMessageBox.No)
    else:
        mbtypes[mbtype](obj, title, msg)


class JoinmarketTab(QWidget):

    def __init__(self, plugin):
        super(JoinmarketTab, self).__init__()
        self.plugin = plugin
        #manual counterparty choice disabled for now, see #7 on github.
        self.c_choosers = {
            "randomly chosen but preferring cheaper offers":
            weighted_order_choose
        }
        #,"choose counterparties manually": weighted_order_choose}
        self.initUI()
        self.taker = None
        self.filter_offers_response = None
        self.taker_info_response = None
        self.clientfactory = None
        #signals from client backend to GUI
        self.jmclient_obj = QObject()
        #This signal/callback requires user acceptance decision.
        self.jmclient_obj.connect(self.jmclient_obj, SIGNAL('JMCLIENT:offers'),
                                                            self.checkOffers)
        #This signal/callback is for information only (including abort/error
        #conditions which require no feedback from user.
        self.jmclient_obj.connect(self.jmclient_obj, SIGNAL('JMCLIENT:info'),
                                  self.takerInfo)
        #Signal indicating Taker has finished its work
        self.jmclient_obj.connect(self.jmclient_obj, SIGNAL('JMCLIENT:finished'),
                                  self.takerFinished)

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

        self.widgets = self.getSettingsWidgets()
        for i, x in enumerate(self.widgets):
            innerTopLayout.addWidget(x[0], i, 0)
            innerTopLayout.addWidget(x[1], i, 1, 1, 2)
        self.startButton = QPushButton('Start')
        self.startButton.setToolTip(
            'You will be prompted to decide whether to accept\n' +
            'the transaction after connecting, and shown the\n' +
            'fees to pay; you can cancel at that point if you wish.')
        self.startButton.clicked.connect(self.startSendPayment)
        self.abortButton = QPushButton('Abort')
        self.abortButton.setEnabled(False)
        self.abortButton.clicked.connect(self.giveUp)
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

    def validateSettings(self):
        valid, errmsg = validate_address(self.widgets[0][1].text())
        if not valid:
            JMQtMessageBox(self, errmsg, mbtype='warn', title="Error")
            return False
        errs = ["Non-zero number of counterparties must be provided.",
                "Mixdepth must be chosen.", "Amount must be provided."]
        for i in [1, 3]:
            if self.widgets[i][1].text().size() == 0:
                JMQtMessageBox(self, errs[i - 1], mbtype='warn', title="Error")
                return False
        #QIntValidator does not prevent entry of 0 for counterparties.
        #Note, use of '1' is not recommended, but not prevented here.
        if self.widgets[1][1].text() == '0':
            JMQtMessageBox(self, errs[0], mbtype='warn', title="Error")
            return False
        #Note that a zero amount IS allowed (for sweep)
        cc = str(self.widgets[2][1].itemText(self.widgets[2][1].currentIndex()))
        self.choice_algo = self.c_choosers[cc]
        return True

    def startSendPayment(self, ignored_makers=None):
        if not self.validateSettings():
            return
        #all settings are valid; start
        #If sweep was requested, make sure the user knew it.
        self.cjamount = self.widgets[3][1].get_amount()
        if self.cjamount == 0:
            mbinfo = ["You selected amount zero, which means 'sweep'."]
            mbinfo.append("This will spend ALL coins in your wallet to")
            mbinfo.append("the destination, after fees. Are you sure?")
            reply = JMQtMessageBox(self,
                                   '\n'.join([m + '<p>' for m in mbinfo]),
                                   mbtype='question',
                                   title='Sweep?')
            if reply == QMessageBox.No:
                self.giveUp()
                return
        self.startButton.setEnabled(False)
        self.abortButton.setEnabled(True)

        log.debug('starting sendpayment')
        self.destaddr = str(self.widgets[0][1].text())
        #inherit format from BTCAmountEdit
        self.btc_amount_str = str(self.widgets[3][1].text(
        )) + " " + self.widgets[3][1]._base_unit()
        makercount = int(self.widgets[1][1].text())

        if self.plugin.wallet.has_password():
            msg = []
            msg.append(_("Enter your password to proceed"))
            self.plugin.wrap_wallet.password = self.plugin.window.password_dialog(
                '\n'.join(msg))
            try:
                self.plugin.wallet.check_password(
                    self.plugin.wrap_wallet.password)
            except Exception as e:
                JMQtMessageBox(self, "Wrong password: " + str(e), mbtype='crit')
                self.giveUp()
                return
        self.taker_schedule = [(0, self.cjamount, makercount, self.destaddr, 0, 0)]
        self.taker = Taker(self.plugin.wrap_wallet,
                           self.taker_schedule,
                           order_chooser=weighted_order_choose,
                           sign_method="wallet",
                           callbacks=[self.callback_checkOffers,
                                      self.callback_takerInfo,
                                      self.callback_takerFinished])
        if ignored_makers:
            self.taker.ignored_makers.extend(ignored_makers)
        if not self.clientfactory:
            #First run means we need to start: create clientfactory
            #and start reactor Thread
            self.clientfactory = JMTakerClientProtocolFactory(self.taker)
            thread = TaskThread(self)
            thread.add(partial(start_reactor,
                   "localhost",
                   jm_single().config.getint("GUI", "daemon_port"),
                   self.clientfactory,
                   ish=False))
        else:
            #load the new Taker; TODO this code crashes if daemon port
            #is changed during run.
            self.clientfactory.getClient().taker = self.taker
            self.clientfactory.getClient().clientStart()

        self.showStatusBarMsg("Connecting to IRC ...")

    def callback_checkOffers(self, offers_fee, cjamount):
        """Receives the signal from the JMClient thread
        """
        self.offers_fee = offers_fee
        self.jmclient_obj.emit(SIGNAL('JMCLIENT:offers'))
        #The JMClient thread must wait for user input
        while not self.filter_offers_response:
            time.sleep(0.1)
        if self.filter_offers_response == "ACCEPT":
            self.filter_offers_response = None
            return True
        self.filter_offers_response = None
        return False

    def callback_takerInfo(self, infotype, infomsg):
        if infotype == "ABORT":
            self.taker_info_type = 'warn'
        elif infotype == "INFO":
            self.taker_info_type = 'info'
        else:
            raise NotImplementedError
        self.taker_infomsg = infomsg
        self.jmclient_obj.emit(SIGNAL('JMCLIENT:info'))
        while not self.taker_info_response:
            time.sleep(0.1)
        #No need to check response type, only OK for msgbox
        self.taker_info_response = None
        return

    def callback_takerFinished(self, res, fromtx=False, waittime=0.0, txdetails=None):
        #not currently using waittime
        self.taker_finished_res = res
        self.taker_finished_fromtx = fromtx
        self.jmclient_obj.emit(SIGNAL('JMCLIENT:finished'))
        return

    def takerInfo(self):
        if self.taker_info_type == "info":
            self.showStatusBarMsg(self.taker_infomsg)
        else:
            JMQtMessageBox(self, self.taker_infomsg, mbtype=self.taker_info_type)
        self.taker_info_response = True

    def checkOffers(self):
        """Parse offers and total fee from client protocol,
        allow the user to agree or decide.
        """
        if not self.offers_fee:
            JMQtMessageBox(self,
                           "Not enough matching offers found.",
                           mbtype='warn',
                           title="Error")
            self.giveUp()
            return
        offers, total_cj_fee = self.offers_fee
        total_fee_pc = 1.0 * total_cj_fee / self.taker.cjamount
        #reset the btc amount display string if it's a sweep:
        if self.cjamount == 0:
            self.btc_amount_str = str((Decimal(self.taker.cjamount) / Decimal('1e8')
                                      )) + " BTC"

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
        mbinfo.append("Sending amount: " + self.btc_amount_str)
        mbinfo.append("to address: " + self.destaddr)
        mbinfo.append(" ")
        mbinfo.append("Counterparties chosen:")
        mbinfo.append('Name,     Order id, Coinjoin fee (sat.)')
        for k, o in offers.iteritems():
            if o['ordertype'] == 'reloffer':
                display_fee = int(self.taker.cjamount *
                                  float(o['cjfee'])) - int(o['txfee'])
            elif o['ordertype'] == 'absoffer':
                display_fee = int(o['cjfee']) - int(o['txfee'])
            else:
                log.debug("Unsupported order type: " + str(o['ordertype']) +
                          ", aborting.")
                self.giveUp()
                return False
            mbinfo.append(k + ', ' + str(o['oid']) + ',         ' + str(
                display_fee))
        mbinfo.append('Total coinjoin fee = ' + str(total_cj_fee) +
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
            self.filter_offers_response = "ACCEPT"
        else:
            self.filter_offers_response = "REJECT"
            self.giveUp()

    def on_new_tx(self, event, tx):
        """Callback from Electrum network thread; since from non-GUI
        thread must explicitly only pass signal, so partly duplicates
        callback_takerFinished.
        """
        if self.taker and self.taker.txid:
            if tx.txid() == self.taker.txid:
                self.taker_finished_res = True
                self.taker_finished_fromtx = False
                self.jmclient_obj.emit(SIGNAL('JMCLIENT:finished'))
            else:
                log.info('received notify of tx, not ours')

    def takerFinished(self):
        if self.taker_finished_fromtx:
            if self.taker_finished_res:
                log.info("Finish callback success - should not be reachable")
            else:
                #a transaction failed; just stop
                self.giveUp()
        else:
            if not self.taker_finished_res:
                log.info("Did not complete successfully, shutting down")
            else:
                log.info("All transactions completed correctly")
            self.cleanUp()

    def cleanUp(self):
        """Called when transaction ends, either
        successfully or unsuccessfully.
        """
        if not self.taker.txid:
            self.showStatusBarMsg("Transaction failed.")
            JMQtMessageBox(self, "Transaction was not completed.", mbtype='warn',
                                   title="Failed")
        else:
            self.showStatusBarMsg("Transaction completed successfully.")
            JMQtMessageBox(self,
                           "Transaction has been broadcast.\n" + "Txid: " +
                           str(self.taker.txid),
                           title="Success")

        self.plugin.wrap_wallet.password = None
        self.startButton.setEnabled(True)
        self.abortButton.setEnabled(False)

    def giveUp(self):
        """Called when a transaction is aborted before completion.
        """
        #re-require password for next try
        self.plugin.wrap_wallet.password = None
        log.debug("Transaction aborted.")
        self.abortButton.setEnabled(False)
        self.startButton.setEnabled(True)
        self.showStatusBarMsg("Transaction aborted.")

    def showStatusBarMsg(self, msg):
        """Slightly imperfect but seems to work for now;
        Append the Joinmarket status to the end of the
        current status message. Allow update_status to
        "reclaim" the status message otherwise.
        """
        if not msg:
            self.plugin.window.update_status()
        sbmsg = [_("JoinMarket: ")]
        sbmsg.append(_(msg))
        current_text = self.plugin.window.balance_label.text()
        if "JoinMarket:" in current_text:
            current_text = current_text[:current_text.index("JoinMarket:")]
        new_text = current_text + " " + "".join(sbmsg)
        self.plugin.window.statusBar().showMessage(new_text)

    def getSettingsWidgets(self):
        results = []
        sN = ['Recipient address', 'Number of counterparties',
              'Counterparty chooser', 'Amount']
        sH = ['The address you want to send the payment to',
              'How many other parties to send to; if you enter 4\n' +
              ', there will be 5 participants, including you',
              'Mechanism for choosing counterparties',
              'The amount to send (units are shown).\n' +
              'If you enter 0, a SWEEP transaction\nwill be performed,' +
              ' spending all the coins \nin the wallet.']
        sT = [str, int, str, None]
        #todo maxmixdepth
        sMM = ['', (2, 20), '', (0.00000001, 100.0, 8)]
        sD = ['', '3', '', '']
        ccCombo = QComboBox()
        for c in self.c_choosers.keys():
            ccCombo.addItem(c)
        for x in zip(sN, sH, sT, sD, sMM):
            ql = QLabel(x[0])
            ql.setToolTip(x[1])
            qle = QLineEdit(x[3]) if x[0] != "Counterparty chooser" else ccCombo
            if x[0] == "Amount":
                qle = BTCAmountEdit(self.plugin.window.get_decimal_point)
            if x[2] == int:
                qle.setValidator(QIntValidator(*x[4]))
            results.append((ql, qle))
        return results

    def resizeScroll(self, mini, maxi):
        self.textedit.verticalScrollBar().setValue(maxi)


class SettingsDialog(QDialog):

    def __init__(self, config_location):
        super(SettingsDialog, self).__init__()
        self.config_location = config_location
        self.initUI()

    def closeEvent(self, event):
        log.debug("Closing settings and persisting")
        persist_config(self.config_location)
        event.accept()

    def initUI(self):
        outerGrid = QGridLayout()
        sA = QScrollArea()
        sA.setWidgetResizable(True)
        frame = QFrame()
        grid = QGridLayout()
        self.settingsFields = []
        j = 0
        #Simplified from Joinmarket-Qt:
        #many internal settings are not relevant for Electrum
        sections = ["GUI", "MESSAGING"]
        for section in sections:
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
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.close)
        outerGrid.addWidget(ok_button)
        sA.setWidget(frame)
        frame.setLayout(grid)
        frame.adjustSize()
        self.setLayout(outerGrid)
        self.setModal(True)
        self.show()

    def handleEdit(self, section, t, checked=None):
        if isinstance(t[1], QCheckBox):
            oname = str(t[0].text())
            oval = 'true' if checked else 'false'
            log.debug('setting section: ' + section + ' and name: ' + oname +
                      ' to: ' + oval)
            jm_single().config.set(section, oname, oval)

        else:  #currently there is only QLineEdit
            log.debug('setting section: ' + section + ' and name: ' + str(t[
                0].text()) + ' to: ' + str(t[1].text()))
            jm_single().config.set(section, str(t[0].text()), str(t[1].text()))

    def getSettingsFields(self, section, names):
        results = []
        for name in names:
            val = jm_single().config.get(section, name)
            if name in config_types:
                t = config_types[name]
                if t == bool:
                    qt = QCheckBox()
                    if val.lower() == 'true':
                        qt.setChecked(True)
                elif not t:
                    continue
                else:
                    qt = QLineEdit(val)
                    if t == int:
                        qt.setValidator(QIntValidator(0, 65535))
            else:
                qt = QLineEdit(val)
            results.append((QLabel(name), qt))
        return results
