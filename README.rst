Sphire Scipion plugin
=====================

This plugin allows to use sphire programs within the Scipion framework.
So far we have implemented:

- crYOLO particle picker (current version: 1.4.0)

`crYOLO`_ is a pipeline for particle detection in cryo-electron
microscopy images which is based on the deep learning object detection system "You Only Look Once" (YOLO).


Setup
=====

For Users
---------

Install `Scipion2`_, follow the 'crYOLO integration' instructions below and `install`_ the cryolo plugin.

For developers
--------------

1. For testing and develop this plugin, you need to use the Scipion v2.0 in devel. 
   For that, just install Scipion from `GitHub`_, using the ‘devel’ branch. 
2. Follow the 'crYOLO integration' instructions below.
3. Clone this repository in you system: 
   ::

      cd
      git clone https://github.com/scipion-em/scipion-em-spire
   
4. Install the sphire plugin in devel mode:
   ::
      
      scipion installp -p ~/scipion-em-sphire --devel


crYOLO integration
-----------------

| The following steps presuppose that you have Anaconda or Miniconda installed on your computer.
| In ``~/.config/scipion/scipion.conf``: 
| Set CONDA_ACTIVATION_CMD variable in the Packages section.
| For example: ``CONDA_ACTIVATION_CMD = . ~/anaconda2/etc/profile.d/conda.sh``
| Notice the command starts with a period! This will source the conda.sh script.
| This is needed to activate the conda environment.
| For further information please visit the following website:
| https://github.com/conda/conda/blob/master/CHANGELOG.md#440-2017-12-20
| If you wish to install the plugin with the default settings just go to plugin manager and 
| install scipion-em-sphire.
| This will create the default environment named crYOLO and download version 1.4.0 for you.
| You are ready to use crYOLO.
| If you wish to change the environment name you can introduce CRYOLO_ENV_ACTIVATION variable in the 
| ~/.config/scipion.conf variables section:
| For example: CRYOLO_ENV_ACTIVATION = conda activate yourdesiredname
| crYOLO general model is not installed by default. You may install it by expanding the plugin
| in the plugin manager and install it.
| This will install the general model to a default location: ~/Softwares/scipion/software/em/cryolo_model-20190516.
| If you wish to install the latest general model manually please vist the following website:
| http://sphire.mpg.de/wiki/doku.php?id=downloads:cryolo_1&redirect=1
| Download the general model and set CRYOLO_GENERIC_MODEL variable in the ~/.config/scipion.conf variables section:
| For example: CRYOLO_GENERIC_MODEL = /your/desired/location/generalmodelname.h5


Running crYOLO tests
-----------------------------
To check that everything is properly installed and configured, you might want to run some tests:

.. code-block::

   scipion test --grep cryolo --run
   
   
.. crYOLO: http://sphire.mpg.de/wiki/doku.php?id=downloads:cryolo_1&redirect=1

.. _Scipion2: https://scipion-em.github.io/docs/docs/scipion-modes/how-to-install.html

.. _install: https://scipion-em.github.io/docs/release-2.0.0/docs/scipion-modes/install-from-sources#step-4-installing-xmipp3-and-other-em-plugins

.. _GitHub: https://scipion-em.github.io/docs/docs/scipion-modes/install-from-sources#from-github
   
