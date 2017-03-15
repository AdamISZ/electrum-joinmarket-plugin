from jmclient import AbstractWallet
from jmclient import btc, get_log, get_p2pk_vbyte
import pprint
import random

log = get_log()

class ElectrumWrapWallet(AbstractWallet): #pragma: no cover
    """A thin wrapper class over Electrum's own
    wallet for joinmarket compatibility
    """
    def __init__(self, ewallet):
        self.ewallet = ewallet
        #TODO: populate self.unspent with all utxos in Electrum wallet.

        # None is valid for unencrypted electrum wallets;
        # calling functions must set the password otherwise
        # for private key operations to work
        self.password = None
        super(ElectrumWrapWallet, self).__init__()

    def get_key_from_addr(self, addr):
        if self.ewallet.has_password() and self.password is None:
            raise Exception("Cannot extract private key without password")
        key = self.ewallet.get_private_key(addr, self.password)
        #Convert from wif compressed to hex compressed
        #TODO check if compressed
        hex_key = btc.from_wif_privkey(key[0], vbyte=get_p2pk_vbyte())
        return hex_key

    def get_external_addr(self, mixdepth):
        addr = self.ewallet.get_unused_address()
        return addr

    def get_internal_addr(self, mixdepth):
        try:
            addrs = self.ewallet.get_change_addresses()[
                -self.ewallet.gap_limit_for_change:]
        except Exception as e:
            log.debug("Failed get change addresses: " + repr(e))
            raise
        #filter by unused
        try:
            change_addrs = [addr for addr in addrs if
                        self.ewallet.get_num_tx(addr) == 0]
        except Exception as e:
            log.debug("Failed to filter chadr: " + repr(e))
            raise
        #if no unused Electrum re-uses randomly TODO consider
        #(of course, all coins in same mixdepth are in principle linkable,
        #so I suspect it is better to stick with Electrum's own model, considering
        #gap limit issues)
        if not change_addrs:
            try:
                change_addrs = [random.choice(addrs)]
            except Exception as e:
                log.debug("Failed random: " + repr(e))
                raise
        return change_addrs[0]

    def sign_tx(self, tx, addrs):
        """tx should be a serialized hex tx.
        If self.password is correctly set,
        will return the raw transaction with all
        inputs from this wallet signed.
        """
        if not self.password:
            raise Exception("No password, cannot sign")
        from electrum.transaction import Transaction
        etx = Transaction(tx)
        etx.deserialize()
        for i in addrs.keys():
            del etx._inputs[i]['scriptSig']
            del etx._inputs[i]['pubkeys']
            self.ewallet.add_input_sig_info(etx._inputs[i], addrs[i])
            etx._inputs[i]['address'] = addrs[i]
            etx._inputs[i]['type'] = 'p2pkh'
        self.ewallet.sign_transaction(etx, self.password)
        return etx.raw

    def sign_message(self, address, message):
        #TODO: not currently used, can we use it for auth?
        return self.ewallet.sign_message(address, message, self.password)

    def get_utxos_by_mixdepth(self):
        """Initial version: all underlying utxos are mixdepth 0.
        Format of return is therefore: {0:
        {txid:n : {"address": addr, "value": value},
        txid:n: {"address": addr, "value": value},..}}
        TODO this should use the account feature in Electrum,
        which is exactly that from BIP32, to implement
        multiple mixdepths.
        """
        ubym = {0:{}}
        coins = self.ewallet.get_spendable_coins()
        log.debug(pprint.pformat(coins))
        for c in coins:
            utxo = c["prevout_hash"] + ":" + str(c["prevout_n"])
            ubym[0][utxo] = {"address": c["address"], "value": c["value"]}
        return ubym
