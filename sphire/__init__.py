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
import os
import subprocess

import pyworkflow.em
import pyworkflow.utils as pwutils
import pyworkflow as pw
from sphire.constants import CRYOLO_GENMOD_VAR, CRYOLO_ENV_ACTIVATION

_logo = "sphire_logo.png"
_sphirePluginDir = os.path.dirname(os.path.abspath(__file__))


class Plugin(pyworkflow.em.Plugin):
    _cryoloVersion = None  # Means not detected yet
    _cryoloVersionSupported = None

    @classmethod
    def _defineVariables(cls):
        # CRYOLO do NOT need EmVar because it uses a conda environment.
        cls._defineVar(CRYOLO_GENMOD_VAR, '')
        cls._defineVar(CRYOLO_ENV_ACTIVATION, 'conda activate cryolo')


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
    def runCryolo(cls, protocol, program, args, cwd=None):
        """ Run crYOLO command from a given protocol. """
        fullProgram = '%s; %s' % (cls.getCryoloEnvActivation(), program)
        protocol.runJob(fullProgram, args, env=cls.getEnviron(), cwd=cwd)


pyworkflow.em.Domain.registerPlugin(__name__)
