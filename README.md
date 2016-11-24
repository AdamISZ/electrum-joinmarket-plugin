# electrum-joinmarket-plugin
Plugin files for doing coinjoins via joinmarket in Electrum.

**This is working, although very flaky; still very much WIP.**

Currently only supports single payments, but see the bottom [section](#future-developments) for future possible improvements (it's better than you might think).

===

## Installation for testing

So far tested only on Linux, should probably work on Windows. Binary install will be developed
after everything else actually works!

(Either use virtualenv or use "sudo" prepended to these commands.)

0. Virtualenv setup:
    `mkdir electrumplugin; cd electrumplugin; virtualenv .`
 
1. Install the backend Joinmarket code. As described in the readme
 for [Joinmarket-clientserver](https://github.com/AdamISZ/joinmarket-clientserver),
 you need to install the daemon and the client-only components:
 
     `git clone https://github.com/AdamISZ/joinmarket-clientserver`
     `cd joinmarket-clientserver`
     `python setup.py --backend install`
     `python setup.py --client-only install`

 The backend automatically installs libnacl, but you need to have libsodium on the
 system for it to work; see the instructions in the main Joinmarket [repo](https://github.com/Joinmarket-Org/joinmarket).
 Both backend and front end install twisted automatically in your virtualenv.
 libsecp256k1 is *not* required (you're only using Electrum's bitcoin code here).

2. Install the latest Electrum. Use [Electrum's Linux "easy" installation link](https://electrum.org/#download):

    `pip install https://download.electrum.org/2.7.12/Electrum-2.7.12.tar.gz` 

3. Install this repo in your top-level virtualenv directory:

    `git clone https://github.com/AdamISZ/electrum-joinmarket-plugin`
 
4. Copy the `joinmarket` folder from this repo into the Electrum installation:

    `cd electrum-joinmarket-plugin`
    `cp -r joinmarket ../lib/python2.7/site-packages/electrum_plugins/.`

 (that second line installs the joinmarket folder to the *virtualenv* code location).

5. Start the daemon

 From the top-level (directory called `electrumplugin` above), to run the daemon:
 
     `cd joinmarket-clientserver/scripts; python joinmarketd.py 12345`
  
  As you can see this is a separate daemon executable and can be run from anywhere;
  specify the port as the only argument; other configuration (like IRC channels) will be fed in from 
  the Electrum plugin.
 
6. Run Electrum and activate Joinmarket

 The joinmarket-plugin can be enabled in Electrum via Tools->Plugins->Joinmarket.
 Fill in the fields in the Joinmarket tab and hit "Start".

This is still very raw, it needs testing work but unfortunately it is basically impossible
to run Electrum against testnet. If you do decide to try it, be aware there will be bugs,
although coin loss is highly unlikely, use small amounts.

The remaining notes below have not been updated, they will probably change quite a bit:

## Safety considerations and limitations

As for joinmarket in general, there isn't much realistic risk of coin loss, but you can never be too careful. First, this **is** restricted to only the "Standard" Electrum wallet type (the plugin won't even load otherwise). Second, it has not been tested on large wallets with lots of history, and is likely to be slow or buggy in this case (at least at this early stage).

For these reasons, **it is strongly recommended to simply make a new testing wallet** (again, it *must* be of the "Standard" type) and feed it a small amount of coins to start. The nice thing about this is it's very easy to manage multiple wallets with Electrum.

### Privacy considerations

Using Electrum means using Electrum servers for sourcing blockchain information (indeed one of the main motivations for doing this is how much easier it makes it for Joinmarket to work). However there is an obvious price in that it means you are giving Electrum servers info about which utxos and addresses you are requesting. This is better than one monolithic blockchain API like blockr.com, but clearly significantly worse than using your own local node. It's worth repeating that privacy will likely always be better with a local bitcoin node.

## Future developments

Electrum Standard wallets are a BIP32 implementation using a single branch for "external" and another single branch for "internal" (e.g. change) addresses. This is exactly the same as what Joinmarket calls a "mixdepth". Each such pair of branches is considered an account (in fact you can see this described in the BIP32 document). Electrum supports the use of multiple accounts, and therefore it may not be very hard to upgrade this plugin to support multiple accounts in a wallet, which would be equivalent to multiple mixdepths. This might open the door to a fairly clean implementation of either "tumbler" or "yield generator" in Joinmarket nomenclature, although either/both would take some work.

Although it wouldn't be pretty, you could manually implement the tumbler style algorithm by moving coins from one wallet to another manually. As mentioned above, this gets you all the advantages of Electrum wallet management for free; but doing such things manually is of course a pain.
