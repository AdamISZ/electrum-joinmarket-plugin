# electrum-joinmarket-plugin
Plugin files for doing coinjoins via joinmarket in Electrum. Currently only supports single payments, but see the bottom [section](#future-developments) for future possible improvements (it's better than you might think).

===

## Installation

This is not as easy as we'd like, but hopefully will get better. Note that binary installations are **not** supported, and that might be difficult to get around, so they won't be for a while at least.

### Linux

1. `pip install libnacl`
2. git clone https://github.com/AdamISZ/joinmarket_core, then `python setup.py install` it.
3. Use [Electrum's Linux "easy" installation link](https://electrum.org/#download):  `sudo pip install https://download.electrum.org/2.6.4/Electrum-2.6.4.tar.gz` 
4. Bugfix: apply the patch https://github.com/spesmilo/electrum/commit/59d39108823989966e27a2f5df24c296cf2c1187 to Electrum. :cry: ; this manual source edit is needed since we want to do testing off the release, but Electrum will simply fail to sign transactions without this bugfix.
5. git clone this repo (or zip) and manually copy its subdirectory `joinmarket` into the installation: `sudo cp -r joinmarket /usr/local/lib/python2.7/dist_packages/electrum_plugins/.` (replace with whatever the location of `dist_packages` is for your environment).

### MacOS and Windows

In short, I don't know; but my suspicion is that if you follow the "install from source" instructions at the Electrum [download link](https://electrum.org/#download), and then apply the above bugfix and manual installation (last two steps as for Linux), modified for your environment, it will *probably* work OK.

## Safety considerations and limitations

As for joinmarket in general, there isn't much realistic risk of coin loss, but you can never be too careful. First, this **is** restricted to only the "Standard" Electrum wallet type (the plugin won't even load otherwise). Second, it has not been tested on large wallets with lots of history, and is likely to be slow or buggy in this case (at least at this early stage).

For these reasons, **it is strongly recommended to simply make a new testing wallet** (again, it *must* be of the "Standard" type) and feed it a small amount of coins to start. The nice thing about this is it's very easy to manage multiple wallets with Electrum.

### Privacy considerations

Using Electrum means using Electrum servers for sourcing blockchain information (indeed one of the main motivations for doing this is how much easier it makes it for Joinmarket to work). However there is an obvious price in that it means you are giving Electrum servers info about which utxos and addresses you are requesting. This is better than one monolithic blockchain API like blockr.com, but clearly significantly worse than using your own local node. It's worth repeating that privacy will likely always be better with a local bitcoin node.

## Future developments

Electrum Standard wallets are a BIP32 implementation using a single branch for "external" and another single branch for "internal" (e.g. change) addresses. This is exactly the same as what Joinmarket calls a "mixdepth". Each such pair of branches is considered an account (in fact you can see this described in the BIP32 document). Electrum supports the use of multiple accounts, and therefore it may not be very hard to upgrade this plugin to support multiple accounts in a wallet, which would be equivalent to multiple mixdepths. This might open the door to a fairly clean implementation of either "tumbler" or "yield generator" in Joinmarket nomenclature, although either/both would take some work.

Although it wouldn't be pretty, you could manually implement the tumbler style algorithm by moving coins from one wallet to another manually. As mentioned above, this gets you all the advantages of Electrum wallet management for free; but doing such things manually is of course a pain.