Sphire Scipion plugin
=====================

This plugin allows to use cryolo within Scipion framework.
So far we have implemented:

- crYOLO particle picker
- JANNI denoising

This plugin is able to install cryolo (which includes janni) and the generic models for both picking
and denoising.

`crYOLO`_ is a pipeline for particle detection in cryo-electron
microscopy images which is based on the deep learning object detection system "You Only Look Once" (YOLO).

`JANNI`_ (Just Another Noise 2 Noise Implementation) implements a neural network denoising tool based on
deep learning.

Setup
=====

It is assumed that `Scipion3`_ is currently installed. If not, follow the instructions `here`_.

Plugin scipion-em-sphire requires to have Conda (Anaconda or Miniconda) installed and not initialized in
the shell.

- **Install this plugin in user mode:**

    It can be installed in user mode via Scipion main window (**Configuration** >
    **Plugins**) or using the command line:

.. code-block::

    scipion installp -p local/path/to/scipion-em-sphire

- **Install this plugin in developer mode:**

.. code-block::

    scipion installp -p local/path/to/scipion-em-sphire --devel


Plugin integration
------------------

The following steps presuppose that you have Anaconda or Miniconda installed on
your computer.
In ``~/.config/scipion/scipion.conf`` (Option View > Show Hidden Files must be enabled) set
**CONDA_ACTIVATION_CMD** variable in the Packages section.

For example:

::

 CONDA_ACTIVATION_CMD = . ~/anaconda2/etc/profile.d/conda.sh

If you wish to install the plugin with the default settings just go to plugin
manager and install scipion-em-sphire. This will create the default environment
named cryolo-x.x.x (where x.x.x is referred to the downloaded version of cryolo) for you.

You are ready to use crYOLO and JANNI.
If you wish to change the environment name you can introduce
**CRYOLO_ENV_ACTIVATION** variable in the ``~/.config/scipion.conf`` variables section:

For example:
::

 CRYOLO_ENV_ACTIVATION = conda activate cryoloenvname

Downloaded crYOLO and JANNI general models can be found, respectively, in the following locations:

``<SCIPION_HOME>/software/em/cryolo_model-[model_version]``

``<SCIPION_HOME>/software/em/cryolo_negstain_model-[model_version]``

``<SCIPION_HOME>/software/em/janni_model-[model_version]``

Running plugin tests
--------------------
To check that everything is properly installed and configured, you might want
to run some tests:

.. code-block::

   scipion test --grep sphire --run
   
   
.. _crYOLO: https://cryolo.readthedocs.io/en/latest/

.. _JANNI: https://sphire.mpg.de/wiki/doku.php?id=janni

.. _Scipion3: http://scipion.i2pc.es/

.. _here: https://scipion-em.github.io/docs/docs/scipion-modes/how-to-install.html

.. _install: https://scipion-em.github.io/docs/release-3.0.0/docs/scipion-modes/install-from-sources#step-4-installing-xmipp3-and-other-em-plugins

.. _GitHub: https://scipion-em.github.io/docs/docs/scipion-modes/install-from-sources#from-github
   
