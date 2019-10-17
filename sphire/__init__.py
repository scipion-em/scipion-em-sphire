# **************************************************************************
# *
# * Authors:     Peter Horvath
# *              Pablo Conesa

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
import pyworkflow.em
import pyworkflow.utils as pwutils
import pyworkflow as pw
from sphire.constants import *

_logo = "sphire_logo.png"
_sphirePluginDir = os.path.dirname(os.path.abspath(__file__))


class Plugin(pyworkflow.em.Plugin):
    _cryoloVersion = None  # Means not detected yet
    _cryoloVersionSupported = None

    @classmethod
    def _defineVariables(cls):
        # CRYOLO do NOT need EmVar because it uses a conda environment.
        cls._defineEmVar(CRYOLO_GENMOD_VAR, CRYOLO_GENMOD_DEFAULT)
        cls._defineVar(CRYOLO_ENV_ACTIVATION, DEFAULT_ACTIVATION_CMD)


    @classmethod
    def getCryoloEnvActivation(cls):
        activation = cls.getVar(CRYOLO_ENV_ACTIVATION)
        scipionHome = pw.Config.SCIPION_HOME + os.path.sep

        return activation.replace(scipionHome, "", 1)

    @classmethod
    def getCryoloGeneralModel(cls):
        return os.path.abspath(cls.getVar(CRYOLO_GENMOD_VAR))

    @classmethod
    def getEnviron(cls):
        """ Setup the environment variables needed to launch sphire. """
        environ = pwutils.Environ(os.environ)
        if 'PYTHONPATH' in environ:
            # this is required for python virtual env to work
            del environ['PYTHONPATH']
        return environ

    #Ignore validateInstallation and __parseCryoloVersion due to the decrease in performance. Although they are functional.
    # @classmethod
    # def validateInstallation(cls):
    #     """
    #     Check we can activate the crYOLO environment using the provided
    #     command via variable CRYOLO_ENV_ACTIVATION and the version can be
    #     parsed.
    #     """
    #     errors = []
    #     cls.__parseCryoloVersion()
    #
    #     if cls._cryoloVersion is None:
    #         errors.append("crYOLO environment could not be activated.\n"
    #                       "or the version could not be parsed. \n"
    #                       "Using %s=%s" % (CRYOLO_ENV_ACTIVATION,
    #                                        cls.getCryoloEnvActivation()))
    #     elif not cls._cryoloVersionSupported:
    #         errors.append("crYOLO version %s unsupported" % cls._cryoloVersion)
    #
    #     return errors
    #
    # @classmethod
    # def __parseCryoloVersion(cls):
    #     # If the version has not been detected, try to load the environment
    #     if cls._cryoloVersionSupported is None:
    #         try:
    #             # check if is crYOLO is installed or not
    #             cmd = cls.getCryoloEnvActivation()
    #             cmd += '; pip list | grep cryolo'
    #             p = subprocess.Popen(["bash", "-c", cmd], env=cls.getEnviron(),
    #                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    #             output, err = p.communicate()
    #             cls._cryoloVersion = output.split()[1]
    #             from pkg_resources import parse_version
    #             cls._cryoloVersionSupported = parse_version(cls._cryoloVersion) >= parse_version("1.2")
    #         except Exception as e:
    #             cls._cryoloVersion = None
    #             cls._cryoloVersionSupported = False
    @classmethod
    def getCondaActivationCmd(cls):
        condaActivationCmd = os.environ.get('CONDA_ACTIVATION_CMD', "")
        correctCondaActivationCmd = condaActivationCmd.replace(pw.Config.SCIPION_HOME + "/", "")
        if not correctCondaActivationCmd:
            print("WARNING!!: CONDA_ACTIVATION_CMD variable not defined. "
                   "Relying on conda being in the PATH")
        elif correctCondaActivationCmd[-1] != ";":
            correctCondaActivationCmd += ";"
        return correctCondaActivationCmd

    @classmethod
    def defineBinaries(cls, env):

        # try to get CONDA activation command
        condaActivationCmd = cls.getCondaActivationCmd()
        neededProgs = ['wget']
        if not condaActivationCmd:
            neededProgs.append('conda')

        cryolo_commands = cls.getInstallationCmd()

        envPath = os.environ.get('PATH', "")  # keep path since conda likely in there
        installEnvVars = {'PATH': envPath} if envPath else None
        env.addPackage('cryolo', version='1.5.3',
                       tar='void.tgz',
                       commands=cryolo_commands,
                       neededProgs=neededProgs,
                       default=False,
                       vars=installEnvVars)

        env.addPackage(CRYOLO_GENMOD, version=CRYOLO_GENMOD_20190516,
                       tar='void.tgz',
                       commands=[("wget ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS/" + CRYOLO_GENMOD_20190516_FN, CRYOLO_GENMOD_20190516_FN)],
                       neededProgs=["wget"],
                       default=False)


    @classmethod
    def getInstallationCmd(cls):

        CRYOLO_INSTALLED = 'cryolo_installed'

        # try to get CONDA activation command
        installationCmd = cls.getCondaActivationCmd()

        # Create the environment
        installationCmd += 'conda create -y -n %s -c anaconda python=3.6 ' \
                           'pyqt=5 cudnn=7.1.2 numpy==1.14.5 cython ' \
                           'wxPython==4.0.4 intel-openmp==2019.4;' \
                           % DEFAULT_ENV_NAME

        # Activate new the environment
        installationCmd += 'conda activate %s;' % DEFAULT_ENV_NAME

        # Install downloaded code
        installationCmd += 'pip install cryolo[gpu];'

        # Flag installation finished
        installationCmd += 'touch %s' % CRYOLO_INSTALLED

        return [(installationCmd, CRYOLO_INSTALLED)]

    @classmethod
    def runCryolo(cls, protocol, program, args, cwd=None):
        """ Run crYOLO command from a given protocol. """
        fullProgram = '%s %s; %s' % (cls.getCondaActivationCmd(), cls.getCryoloEnvActivation(), program)
        protocol.runJob(fullProgram, args, env=cls.getEnviron(), cwd=cwd)


pyworkflow.em.Domain.registerPlugin(__name__)
