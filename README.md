# electrum-joinmarket-plugin
Plugin files for doing coinjoins via joinmarket in Electrum.

**This is in the process of a major refactoring, it doesn't currently work, when
it's been tested succesfully this file will update further.**

Currently only supports single payments, but see the bottom [section](#future-developments) for future possible improvements (it's better than you might think).

===

## Installation

This is intended for Linux currently. Binary install may be investigated
after everything else actually works!

(Either use virtualenv or use "sudo" prepended to these commands.)

1. Use [Electrum's Linux "easy" installation link](https://electrum.org/#download):

    pip install https://download.electrum.org/2.7.12/Electrum-2.7.12.tar.gz 
 
2. Copy the `joinmarket` folder into the Electrum installation:

    cp -r joinmarket /usr/local/lib/python2.7/dist_packages/electrum_plugins/.

(replace with whatever the location of `dist_packages` is for your environment).


## Safety considerations and limitations

As for joinmarket in general, there isn't much realistic risk of coin loss, but you can never be too careful. First, this **is** restricted to only the "Standard" Electrum wallet type (the plugin won't even load otherwise). Second, it has not been tested on large wallets with lots of history, and is likely to be slow or buggy in this case (at least at this early stage).

For these reasons, **it is strongly recommended to simply make a new testing wallet** (again, it *must* be of the "Standard" type) and feed it a small amount of coins to start. The nice thing about this is it's very easy to manage multiple wallets with Electrum.

### Privacy considerations

Using Electrum means using Electrum servers for sourcing blockchain information (indeed one of the main motivations for doing this is how much easier it makes it for Joinmarket to work). However there is an obvious price in that it means you are giving Electrum servers info about which utxos and addresses you are requesting. This is better than one monolithic blockchain API like blockr.com, but clearly significantly worse than using your own local node. It's worth repeating that privacy will likely always be better with a local bitcoin node.

## Future developments

Electrum Standard wallets are a BIP32 implementation using a single branch for "external" and another single branch for "internal" (e.g. change) addresses. This is exactly the same as what Joinmarket calls a "mixdepth". Each such pair of branches is considered an account (in fact you can see this described in the BIP32 document). Electrum supports the use of multiple accounts, and therefore it may not be very hard to upgrade this plugin to support multiple accounts in a wallet, which would be equivalent to multiple mixdepths. This might open the door to a fairly clean implementation of either "tumbler" or "yield generator" in Joinmarket nomenclature, although either/both would take some work.

Although it wouldn't be pretty, you could manually implement the tumbler style algorithm by moving coins from one wallet to another manually. As mentioned above, this gets you all the advantages of Electrum wallet management for free; but doing such things manually is of course a pain.