=============
Sphire plugin
=============

This plugin provides a wrapper for some programs of `SPHIRE <https://sphire.mpg.de/>`_ software suite:

    - JANNI (Just Another Noise 2 Noise Implementation): a neural network denoising tool
    - crYOLO: a fast and accurate particle picking procedure. It's based on convolutional neural networks and utilizes the popular You Only Look Once (YOLO) object detection system.

.. image:: https://img.shields.io/pypi/v/scipion-em-sphire.svg
        :target: https://pypi.python.org/pypi/scipion-em-sphire
        :alt: PyPI release

.. image:: https://img.shields.io/pypi/l/scipion-em-sphire.svg
        :target: https://pypi.python.org/pypi/scipion-em-sphire
        :alt: License

.. image:: https://img.shields.io/pypi/pyversions/scipion-em-sphire.svg
        :target: https://pypi.python.org/pypi/scipion-em-sphire
        :alt: Supported Python versions

.. image:: https://img.shields.io/sonar/quality_gate/scipion-em_scipion-em-sphire?server=https%3A%2F%2Fsonarcloud.io
        :target: https://sonarcloud.io/dashboard?id=scipion-em_scipion-em-sphire
        :alt: SonarCloud quality gate

.. image:: https://img.shields.io/pypi/dm/scipion-em-sphire
        :target: https://pypi.python.org/pypi/scipion-em-sphire
        :alt: Downloads


Installation
------------

You will need to use 3.0+ version of Scipion to be able to run these protocols. To install the plugin, you have two options:

a) Stable version

    It can be installed in user mode via Scipion plugin manager (**Configuration** > **Plugins**) or using the command line:

    .. code-block::

        scipion installp -p scipion-em-sphire

b) Developer's version

    * download repository

    .. code-block::

        git clone -b devel https://github.com/scipion-em/scipion-em-sphire.git

    * install

    .. code-block::

        scipion installp -p /path/to/scipion-em-sphire --devel

crYOLO software will be installed automatically with the plugin but you can also use an existing installation by providing *CRYOLO_ENV_ACTIVATION* (see below).

**Important:** you need to have conda (miniconda3 or anaconda3) pre-installed to use this program.

To check the installation you can run the plugin's tests:

``scipion test --grep sphire --run``


Configuration variables
-----------------------

**CONDA_ACTIVATION_CMD**: If undefined, it will rely on conda command being in the
PATH (not recommended), which can lead to execution problems mixing scipion
python with conda ones. One example of this could can be seen below but
depending on your conda version and shell you will need something different:

CONDA_ACTIVATION_CMD = eval "$(/extra/miniconda3/bin/conda shell.bash hook)"

**CRYOLO_ENV_ACTIVATION** (default = conda activate cryolo-1.9.3):
Command to activate the crYOLO environment.

Downloaded crYOLO and JANNI general models can be found in the following locations:

* ``<SCIPION_HOME>/software/em/cryolo_model-[model_version]``
* ``<SCIPION_HOME>/software/em/cryolo_negstain_model-[model_version]`` (not installed by default)
* ``<SCIPION_HOME>/software/em/janni_model-[model_version]``

Running on CPU
--------------

crYOLO can run on CPU, however this is only recommended for picking protocol and not training.
For that reason the CPU implementation is only available for the *crYOLO-Picking protocol*.

The CPU implementation of crYOLO **is not installed by default**. Therefore you must install the *cryoloCPU-[version]* package in the **Configuration** > **Plugins** >> **scipion-em-sphire** or by running:

``scipion installb cryoloCPU``

The CPU version of crYOLO is installed under a separate conda environment called *cryoloCPU-[version]*. If you already have a cryoloCPU environment pre-installed, then modify the following variable in the Scipion config file:

``CRYOLO_ENV_ACTIVATION_CPU = conda activate envName``


Supported versions
------------------

1.8.2, 1.8.4, 1.8.5, 1.9.3

Protocols
---------

    * import crYOLO training model
    * crYOLO picking
    * crYOLO tomo picking
    * crYOLO training
    * JANNI denoising
   
References
----------

    * Wagner, T. et al. SPHIRE-crYOLO is a fast and accurate fully automated particle picker for cryo-EM. Communications Biology 2, (2019).
