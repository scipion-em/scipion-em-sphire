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
# * the Free Software Foundation; either version 2 of the License, or
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

_logo = "sphire_logo.png"
_sphirePluginDir = os.path.dirname(os.path.abspath(__file__))


class Plugin(pwem.Plugin):
    _cryoloVersion = None  # Means not detected yet
    _cryoloVersionSupported = None
    _condaActivationCmd = None

    @classmethod
    def _defineVariables(cls):
        # CRYOLO do NOT need EmVar because it uses a conda environment.
        cls._defineEmVar(CRYOLO_GENMOD_VAR, CRYOLO_GENMOD_DEFAULT)
        cls._defineVar(CRYOLO_ENV_ACTIVATION, DEFAULT_ACTIVATION_CMD)
        cls._defineEmVar(JANNI_GENMOD_VAR, JANNI_GENMOD_DEFAULT)  # EmVar is used instead of Var because method getVar
        cls._defineEmVar(CRYOLO_NS_GENMOD_VAR, CRYOLO_NS_GENMOD_DEFAULT)

    @classmethod
    def getCryoloEnvActivation(cls):
        activation = cls.getVar(CRYOLO_ENV_ACTIVATION)
        scipionHome = pw.Config.SCIPION_HOME + os.path.sep

        return activation.replace(scipionHome, "", 1)

    @classmethod
    def getCryoloGeneralModel(cls):
        return os.path.abspath(cls.getVar(CRYOLO_GENMOD_VAR))

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
        return environ

    @classmethod
    def defineBinaries(cls, env):

        cls.addCryoloPackage(env, CRYOLO_DEFAULT_VER_NUM, default=bool(cls.getCondaActivationCmd()))

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_202002_N63,
                       tar='void.tgz',
                       commands=[(
                                 "wget ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS/" +
                                 CRYOLO_GENMOD_202002_N63_FN, CRYOLO_GENMOD_202002_N63_FN)],
                       neededProgs=["wget"],
                       default=True)

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_201910,
                       tar='void.tgz',
                       commands=[(
                                 "wget ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS/" +
                                 CRYOLO_GENMOD_201910_FN, CRYOLO_GENMOD_201910_FN)],
                       neededProgs=["wget"],
                       default=False)

        env.addPackage(CRYOLO_NS_GENMOD, version=CRYOLO_NS_GENMOD_20190226,
                       tar='void.tgz',
                       commands=[(
                                 "wget ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS/" +
                                 CRYOLO_NS_GENMOD_20190226_FN, CRYOLO_NS_GENMOD_20190226_FN)],
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
    def addCryoloPackage(cls, env, version, default=False):

        CRYOLO_INSTALLED = 'cryolo_%s_installed' % version
        ENV_NAME = getCryoloEnvName(version)
        # try to get CONDA activation command
        installationCmd = cls.getCondaActivationCmd()

        # Create the environment
        installationCmd += 'conda create -y -n %s -c anaconda python=3.6 ' \
                           'pyqt=5 cudnn=7.1.2 numpy==1.14.5 cython ' \
                           'wxPython==4.0.4 intel-openmp==2019.4 &&' \
                           % ENV_NAME

        # Activate new the environment
        installationCmd += 'conda activate %s &&' % ENV_NAME

        # Install downloaded code
        installationCmd += 'pip install cryolo[gpu]==%s &&' % version

        # Flag installation finished
        installationCmd += 'touch %s' % CRYOLO_INSTALLED

        cryolo_commands = [(installationCmd, CRYOLO_INSTALLED)]

        envPath = os.environ.get('PATH', "")  # keep path since conda likely in there
        installEnvVars = {'PATH': envPath} if envPath else None
        env.addPackage('cryolo', version=version,
                       tar='void.tgz',
                       commands=cryolo_commands,
                       neededProgs=cls.getDependencies(),
                       default=default,
                       vars=installEnvVars)

    @classmethod
    def runCryolo(cls, protocol, program, args, cwd=None):
        """ Run crYOLO command from a given protocol. """
        fullProgram = '%s %s && %s' % (cls.getCondaActivationCmd(), cls.getCryoloEnvActivation(), program)
        protocol.runJob(fullProgram, args, env=cls.getEnviron(), cwd=cwd)

