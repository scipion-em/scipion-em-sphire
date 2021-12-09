# -*- coding: utf-8 -*
# **************************************************************************
# *
# * Authors:     Peter Horvath
# *              Pablo Conesa
# *              Jorge Jiménez
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************
"""
This package contains the protocols and data for crYOLO
"""
import pwem
import pyworkflow.utils as pwutils
import pyworkflow as pw
from sphire.constants import *

__version__ = '3.0.8'
_logo = "sphire_logo.png"
_references = ['Wagner2019']
_sphirePluginDir = os.path.dirname(os.path.abspath(__file__))


class Plugin(pwem.Plugin):

    _url = 'https://github.com/scipion-em/scipion-em-sphire'

    @classmethod
    def _defineVariables(cls):
        # CRYOLO do NOT need EmVar because it uses a conda environment.
        cls._defineVar(CRYOLO_ENV_ACTIVATION_CPU, DEFAULT_ACTIVATION_CMD_CPU)
        cls._defineVar(CRYOLO_ENV_ACTIVATION, DEFAULT_ACTIVATION_CMD)
        cls._defineEmVar(CRYOLO_GENMOD_VAR, CRYOLO_GENMOD_DEFAULT)
        cls._defineEmVar(CRYOLO_GENMOD_NN_VAR, CRYOLO_GENMOD_NN_DEFAULT)
        cls._defineEmVar(JANNI_GENMOD_VAR, JANNI_GENMOD_DEFAULT)  # EmVar is used instead of Var because method getVar
        cls._defineEmVar(CRYOLO_NS_GENMOD_VAR, CRYOLO_NS_GENMOD_DEFAULT)
        cls._defineVar(CRYOLO_CUDA_LIB, pwem.Config.CUDA_LIB)

    @classmethod
    def getCryoloEnvActivation(cls, useCpu=False):
        if useCpu:
            activation = cls.getVar(CRYOLO_ENV_ACTIVATION_CPU)
        else:
            activation = cls.getVar(CRYOLO_ENV_ACTIVATION)
        scipionHome = pw.Config.SCIPION_HOME + os.path.sep

        return activation.replace(scipionHome, "", 1)

    @classmethod
    def getCryoloGeneralModel(cls):
        return os.path.abspath(cls.getVar(CRYOLO_GENMOD_VAR))

    @classmethod
    def getCryoloGeneralNNModel(cls):
        return os.path.abspath(cls.getVar(CRYOLO_GENMOD_NN_VAR))

    @classmethod
    def getCryoloGeneralNSModel(cls):
        return os.path.abspath(cls.getVar(CRYOLO_NS_GENMOD_VAR))

    @classmethod
    def getJanniGeneralModel(cls):
        return os.path.abspath(cls.getVar(JANNI_GENMOD_VAR))

    @classmethod
    def getEnviron(cls):
        """ Setup the environment variables needed to launch sphire. """
        environ = pwutils.Environ(os.environ)
        if 'PYTHONPATH' in environ:
            # this is required for python virtual env to work
            del environ['PYTHONPATH']
        cudaLib = cls.getVar(CRYOLO_CUDA_LIB, pwem.Config.CUDA_LIB)
        environ.addLibrary(cudaLib)
        return environ

    @classmethod
    def defineBinaries(cls, env):
        cls.addCryoloPackage(env, CRYOLO_DEFAULT_VER_NUM, default=bool(cls.getCondaActivationCmd()))
        cls.addCryoloPackage(env, CRYOLO_DEFAULT_VER_NUM, default=False, useCpu=True)
        cls.addCryoloPackage(env, V1_8_0, default=False, pythonVersion='3.7')
        url = "wget ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS/"

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_201910,
                       tar='void.tgz',
                       commands=[(url + CRYOLO_GENMOD_201910_FN, CRYOLO_GENMOD_201910_FN)],
                       neededProgs=["wget"],
                       default=False)

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_202002,
                       tar='void.tgz',
                       commands=[(url + CRYOLO_GENMOD_202002_FN, CRYOLO_GENMOD_202002_FN)],
                       neededProgs=["wget"],
                       default=False)

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_202005,
                       tar='void.tgz',
                       commands=[(url + CRYOLO_GENMOD_202005_FN, CRYOLO_GENMOD_202005_FN)],
                       neededProgs=["wget"],
                       default=True)

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_NN_202005,
                       tar='void.tgz',
                       commands=[(url + CRYOLO_GENMOD_NN_202005_FN, CRYOLO_GENMOD_NN_202005_FN)],
                       neededProgs=["wget"],
                       default=True)

        env.addPackage(CRYOLO_NS_GENMOD, version=CRYOLO_NS_GENMOD_20190226,
                       tar='void.tgz',
                       commands=[(url + CRYOLO_NS_GENMOD_20190226_FN, CRYOLO_NS_GENMOD_20190226_FN)],
                       neededProgs=["wget"],
                       default=False)

        env.addPackage(JANNI_GENMOD,
                       version=JANNI_GENMOD_20190703,
                       tar='void.tgz',
                       commands=[("wget https://github.com/MPI-Dortmund/sphire-janni/raw/master/janni_general_models/"
                                  + JANNI_GENMOD_20190703_FN, JANNI_GENMOD_20190703_FN)],
                       neededProgs=["wget"],
                       default=True)

    @classmethod
    def getDependencies(cls):
        # try to get CONDA activation command
        condaActivationCmd = cls.getCondaActivationCmd()
        neededProgs = ['wget']
        if not condaActivationCmd:
            neededProgs.append('conda')

        return neededProgs

    @classmethod
    def addCryoloPackage(cls, env, version, default=False, useCpu=False,
                         pythonVersion='3.6'):
        archFlag = 'CPU' if useCpu else ''
        CRYOLO_INSTALLED = 'cryolo%s_%s_installed' % (archFlag, version)
        ENV_NAME = getCryoloEnvName(version, useCpu)
        boxManagerversion = '1.3.6'
        # try to get CONDA activation command
        installationCmd = cls.getCondaActivationCmd()

        # Creating the environment
        if version == V1_8_0:
            installationCmd += 'conda create -y -n %s -c conda-forge -c anaconda ' \
                               'python=%s pyqt=5 cudatoolkit=10.0.130 cudnn=7.6.5 numpy=1.18.5 ' \
                               'cython libtiff wxPython intel-openmp==2019.4 pip=20.2.3 &&' \
                               % (ENV_NAME, pythonVersion)
            boxManagerversion = '1.4'
        else:
            installationCmd += 'conda create -y -n %s -c conda-forge -c anaconda '\
                               'python=%s pyqt=5 cudnn=7.1.2 numpy==1.14.5 '\
                               'cython wxPython==4.0.4 intel-openmp==2019.4 pip=20.2.3 &&' \
                               % (ENV_NAME, pythonVersion)

        # Activate new the environment
        installationCmd += 'conda activate %s && ' % ENV_NAME

        # Install downloaded code
        installationCmd += ('pip install cryoloBM==%s cryolo[%s]==%s && '
                            % (boxManagerversion, 'cpu' if useCpu else 'gpu', version))

        # Flag installation finished
        installationCmd += 'touch %s' % CRYOLO_INSTALLED

        cryolo_commands = [(installationCmd, CRYOLO_INSTALLED)]

        envPath = os.environ.get('PATH', "")  # keep path since conda likely in there
        installEnvVars = {'PATH': envPath} if envPath else None
        env.addPackage('cryolo'+archFlag, version=version,
                       tar='void.tgz',
                       commands=cryolo_commands,
                       neededProgs=cls.getDependencies(),
                       default=default,
                       vars=installEnvVars)

    @classmethod
    def runCryolo(cls, protocol, program, args, cwd=None, useCpu=False):
        """ Run crYOLO command from a given protocol. """
        fullProgram = '%s %s && %s' % (cls.getCondaActivationCmd(),
                                       cls.getCryoloEnvActivation(useCpu), program)
        protocol.runJob(fullProgram, args, env=cls.getEnviron(), cwd=cwd,
                        numberOfMpi=1)
