Sphire Scipion plugin
=====================

Plugin to use Sphire programs within the Scipion framework

So far we have implemented:

- crYOLO particle picker (current version: 1.3.3)


crYOLO installation
-------------------

- **Please follow installation instructions from**: http://sphire.mpg.de/wiki/doku.php?id=downloads:cryolo_1&redirect=1 in order to install:
   - crYOLO (last tested version: 1.3.3) (should download a file called cryolo-X.Y.Z.tar.gz)
   - crYOLO's boxmanager (last tested version: 1.1.0). (should download a file called cryoloBM-X.Y.Z.tar.gz) Note: the BoxManager is not strictly necessary for using the Scipion protocols.

- **If you want to use the generic model**, please download also the General PhosaursNet model. (latest at the time of writing: ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS/gmodel_phosnet_20190314.h5, but better to check the Sphire page for the latest one)


Scipion crYOLO Configuration
----------------------------
Then, we need to define some environment variables to specify how to load the cryolo environment and where is the general model. We can define the variables in the .bashrc file or in ~/.config/scipion/scipion.conf:

.. code-block::

    CRYOLO_ENV_ACTIVATION = . /path/to/anaconda/etc/profile.d/conda.sh; conda activate cryolo
    CRYOLO_GENERIC_MODEL = path/to/the/downloaded/General_PhosaursNet_model

Install Scipion crYOLO Plugin
-----------------------------

.. code-block::

      scipion installp -p scipion-em-sphire

OR

  - through the plugin manager GUI by launching Scipion and following **Configuration** >> **Plugins**

OR

.. code-block::

   scipion python -m pip install scipion-em-sphire

If you are developing the plugin, other useful options are:

.. code-block::

    scipion installp -p local/path/to/scipion-em-sphire --devel

OR

.. code-block::

   git clone git@github.com:scipion-em/scipion-em-sphire
   export PYTHONPATH=$PYTHONPATH:$PWD/scipion-em-sphire


Running crYOLO tests
-----------------------------
To check that everything is properly installed and configured, you might want to run some tests:

.. code-block::

   scipion test --grep cryolo --run
