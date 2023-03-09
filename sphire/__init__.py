# **************************************************************************
# *
# * Authors:     Peter Horvath (phorvath@cnb.csic.es)
# *              Pablo Conesa (pconesa@cnb.csic.es)
# *              Jorge Jiménez jimenez@cnb.csic.es)
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

import pwem
import pyworkflow.utils as pwutils

from .constants import *


__version__ = '3.1.3'
_logo = "sphire_logo.png"
_references = ['Wagner2019']


class Plugin(pwem.Plugin):
    _pathVars = [CRYOLO_CUDA_LIB]
    _url = 'https://github.com/scipion-em/scipion-em-sphire'
    _supportedVersions = VERSIONS

    @classmethod
    def _defineVariables(cls):
        cls._defineVar(CRYOLO_ENV_ACTIVATION_CPU, DEFAULT_ACTIVATION_CMD_CPU)
        cls._defineVar(CRYOLO_ENV_ACTIVATION, DEFAULT_ACTIVATION_CMD)
        cls._defineEmVar(CRYOLO_GENMOD_VAR, CRYOLO_GENMOD_DEFAULT)
        cls._defineEmVar(CRYOLO_GENMOD_NN_VAR, CRYOLO_GENMOD_NN_DEFAULT)
        cls._defineEmVar(JANNI_GENMOD_VAR, JANNI_GENMOD_DEFAULT)
        cls._defineEmVar(CRYOLO_NS_GENMOD_VAR, CRYOLO_NS_GENMOD_DEFAULT)
        cls._defineVar(CRYOLO_CUDA_LIB, pwem.Config.CUDA_LIB)

    @classmethod
    def getCryoloEnvActivation(cls, useCpu=False):
        var = CRYOLO_ENV_ACTIVATION_CPU if useCpu else CRYOLO_ENV_ACTIVATION
        return cls.getVar(var)

    @classmethod
    def getActiveVersion(cls, *args):
        """ Return the env name that is currently active. """
        envVar = cls.getCryoloEnvActivation(useCpu=False)
        return envVar.split()[-1].split("-")[-1]

    @classmethod
    def getModelFn(cls, modelKey):
        return os.path.abspath(cls.getVar(modelKey))

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
    def getDependencies(cls):
        """ Return a list of dependencies. Include conda if
            activation command was not found. """
        condaActivationCmd = cls.getCondaActivationCmd()
        neededProgs = ['wget']
        if not condaActivationCmd:
            neededProgs.append('conda')

        return neededProgs

    @classmethod
    def addCryoloPackage(cls, env, version, default=False, useCpu=False):
        archFlag = 'CPU' if useCpu else ''
        suffix = 'cpu' if useCpu else 'gpu'
        CRYOLO_INSTALLED = f"cryolo{archFlag}_{version}_installed"
        ENV_NAME = getCryoloEnvName(version, useCpu)
        cudaVersion = cls.guessCudaVersion(CRYOLO_CUDA_LIB, default="11.7")

        if cudaVersion.major == 10:
            extrapkgs = "python=3.7 cudatoolkit=10.0.130 cudnn=7.6.5"
        else:  # cuda 11
            extrapkgs = "python=3.8"

        installCmd = [
            cls.getCondaActivationCmd(),
            f'conda create -y -n {ENV_NAME} -c conda-forge -c anaconda',
            f'pyqt=5 {extrapkgs} numpy=1.18.5 libtiff wxPython=4.1.1 adwaita-icon-theme "setuptools<66" &&',
            f'conda activate {ENV_NAME} &&'
        ]

        if cudaVersion.major == 10:
            installCmd.append(f"pip install 'cryolo[{suffix}]=={version}'")
        else:  # cuda 11
            installCmd.append(f"pip install nvidia-pyindex && pip install 'cryolo[c11]=={version}'")

        # downgrade imageio, because numpy must be 1.18.5
        installCmd.append("&& pip install 'imageio<=2.15.0'")

        # Flag installation finished
        installCmd.append(f'&& touch {CRYOLO_INSTALLED}')

        cryolo_commands = [(" ".join(installCmd), CRYOLO_INSTALLED)]

        envPath = os.environ.get('PATH', "")  # keep path since conda likely in there
        installEnvVars = {'PATH': envPath} if envPath else None
        env.addPackage(f'cryolo{archFlag}', version=version,
                       tar='void.tgz',
                       commands=cryolo_commands,
                       neededProgs=cls.getDependencies(),
                       default=default,
                       vars=installEnvVars)

    @classmethod
    def defineBinaries(cls, env):
        def _add(version, **kwargs):
            cls.addCryoloPackage(env, version, **kwargs)
            kwargs['useCpu'] = True
            cls.addCryoloPackage(env, version, **kwargs)

        _add(V1_8_2)
        _add(V1_8_4)
        _add(V1_8_5)
        _add(V1_9_3, default=True)

        def _addModel(model, version, link, filename, default=False):
            env.addPackage(model, version=version,
                           tar='void.tgz',
                           commands=[(f"wget {link}/{filename}", filename)],
                           neededProgs=["wget"],
                           default=default)

        url = "ftp://ftp.gwdg.de/pub/misc/sphire/crYOLO-GENERAL-MODELS"
        _addModel(CRYOLO_GENMOD, CRYOLO_GENMOD_202005, url,
                  CRYOLO_GENMOD_202005_FN, True)
        _addModel(CRYOLO_GENMOD, CRYOLO_GENMOD_NN_202005, url,
                  CRYOLO_GENMOD_NN_202005_FN, True)
        _addModel(CRYOLO_NS_GENMOD, CRYOLO_NS_GENMOD_20190226, url,
                  CRYOLO_NS_GENMOD_20190226_FN, False)

        url = "https://github.com/MPI-Dortmund/sphire-janni/raw/master/janni_general_models/"
        _addModel(JANNI_GENMOD, JANNI_GENMOD_20190703, url,
                  JANNI_GENMOD_20190703_FN, True)

    @classmethod
    def versionGE(cls, version):
        """ Return True if current version of crYOLO is newer
         or equal than the input argument.
         Params:
            version: string version (semantic version, e.g 0.3.5)
        """
        v1 = cls.getActiveVersion()
        if v1 not in VERSIONS:
            raise Exception("This version of crYOLO is not supported: ", v1)

        if VERSIONS.index(v1) < VERSIONS.index(version):
            return False
        return True

    @classmethod
    def runCryolo(cls, protocol, program, args, cwd=None, useCpu=False):
        """ Run crYOLO command from a given protocol. """
        fullProgram = '%s %s && %s' % (cls.getCondaActivationCmd(),
                                       cls.getCryoloEnvActivation(useCpu), program)
        protocol.runJob(fullProgram, args, env=cls.getEnviron(), cwd=cwd,
                        numberOfMpi=1)
