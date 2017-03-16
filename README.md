# electrum-joinmarket-plugin
Plugin files for doing coinjoins via joinmarket in Electrum.

This is still quite new and needs more testers. Be aware there may be bugs,
although coin loss is highly unlikely, use small amounts, or testnet first.

(If you do want to try on testnet, use `./electrum --testnet` on the command line).

**Strongly recommended: use a fresh wallet, not one with a lot of coins, or a lot of outputs**.

Also, the joinmarket plugin **only supports wallets of type "Standard"**.

Currently only supports single payments.

Donations for this plugin work gratefully received at 1B6Qiz2aZckduhZbMRvUNAfxSVD7fZNhrJ.

===

## Installation

(Assumes Linux, may work on Mac/Windows in some cases, but there is no binary yet)

##### Quick version 

1. Download the binary [release](https://github.com/AdamISZ/joinmarket-clientserver/releases)
 of joinmarketd, put it anywhere and run `./joinmarketd` (serves default port 27183)

 Note that this binary knows nothing about Bitcoin :) It just sends messages back and forth to (currently) IRC, and handles encryption.

2. Download the customised Electrum [release](https://github.com/AdamISZ/electrum-joinmarket-plugin/releases)
 from this repo. Then follow the instructions as for normal Electrum installation:
 
    `sudo apt-get install python-qt4 python-pip`
    `tar xvf <Electrum-name>.tar.gz; cd <Electrum-name>`
    `python electrum`

To avoid sudo, see the note at the bottom.

Activate the Joinmarket plugin from Tools->Plugins and the tab should pop up.

##### From-source version

1. Make a virtualenv to work in.

2. Make sure you have libsodium on the system; see instructions in the [JMCS install page](https://github.com/AdamISZ/joinmarket-clientserver/blob/master/docs/INSTALL.md).
 Note: libsecp256k1 is *not* required (you're only using Electrum's bitcoin code here).
 
 Once you have that, don't forget to `pip install libnacl` in your virtualenv.
 
3. Install and run joinmarketd from the joinmarket-clientserver repo:

     `git clone https://github.com/AdamISZ/joinmarket-clientserver`
     `cd joinmarket-clientserver`
     `python setupall.py --daemon`
     `python setupall.py --client-only`
     `cd scripts`
     `python joinmarketd.py`
 
 (Leave the daemon running, preferably in foreground until logging is set up, that's a TODO).

4. Install Electrum in "from source" version (you could also use pip), following instructions on [download page](https://electrum.org/#download).
 Once you've done this, check that you can run Electrum; to do this in a virtualenv (highly recommended of course!),
 you may need to read the note at the bottom about PyQt4.
 
3. Install this repo:
 
    `git clone https://github.com/AdamISZ/electrum-joinmarket-plugin`
 
4. Copy the `joinmarket` folder from this repo into the Electrum installation:
 
    `cd electrum-joinmarket-plugin`
    `cp -r joinmarket <virtualenvdir>/lib/python2.7/site-packages/electrum_plugins/.`
  
 or put it into system dist-packages if you're not using virtualenv.
 
7. Run Electrum and activate Joinmarket
 - as for "quick" version.


##### A note on PyQt4 and virtualenv

If you don't use virtualenv, then `sudo python install python-qt4` should do the trick fine.
But, PyQt doesn't play nice with virtualenvs. If you want to encapsulate this in a virtualenv,
you can follow the trick I found to work, but no guarantee it will for you:
copy the dir PyQt4, the files sip*.so and sipconfig.py, sipconfig_nd.py from the
system level dist-packages to the virtualenv site-packages.