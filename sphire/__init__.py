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
import os, subprocess
import pyworkflow.em
from pyworkflow.utils import Environ
from sphire.constants import CRYOLO_GENMOD_VAR, CRYOLO_ENV_ACTIVATION

_logo = "sphire_logo.png"
_sphirePluginDir = os.path.dirname(os.path.abspath(__file__))


class Plugin(pyworkflow.em.Plugin):
    _cryoloEnvFound = None

    @classmethod
    def _defineVariables(cls):
        # CRYOLO do NOT need EmVar because it uses a conda environment.
        cls._defineVar(CRYOLO_GENMOD_VAR, '')
        cls._defineVar(CRYOLO_ENV_ACTIVATION, 'source activate cryolo')

    @classmethod
    def getCryoloEnvActivation(cls):
        # All variables in PACKAGES have scipion path prepended.
        var = cls.getVar(CRYOLO_ENV_ACTIVATION)
        return var[var.rfind("/")+1:]

    @classmethod
    def getEnviron(cls):
        """ Setup the environment variables needed to launch sphire. """
        environ = Environ(os.environ)
        #environ.update({'PATH': os.path.join(cls.getHome(), 'bin'),
        #                 }, position=Environ.BEGIN)
        if 'PYTHONPATH' in environ:
            # this is required for python virtual env to work
            del environ['PYTHONPATH']

        return environ

    @classmethod
    def validateInstallation(cls):
        """
        Check if the binaries are properly installed and if not, return
        a list with the error messages.

        The default implementation will check if the _pathVars exists.
        """

        missing = []

        envFound, version, versionSupported = cls._checkCryoloInstallation()

        if not envFound:
            missing.append("crYOLO environment (%s) could not be activated." % cls.getCryoloEnvActivation())


        if not versionSupported:
            missing.append("crYOLO version %s unsupported" % version)

        return missing

    @classmethod
    def _checkCryoloInstallation(cls):

        if cls._cryoloEnvFound is None:
           try:
                # check if is crYOLO is installed or not
                cmd = "%s && pip list | grep 'cryolo\s'" % cls.getCryoloEnvActivation()
                p = subprocess.Popen(["bash", "-c", cmd],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE)

                output, err = p.communicate()
                cls._cryoloVersion = output.split()[1]
                cls._cryoloEnvFound = True
                from pkg_resources import parse_version
                cls._cryoloVersionSupported = parse_version(cls._cryoloVersion) >= parse_version("1.2")

           except Exception as e:
                cls._cryoloEnvFound = False
                cls._cryoloVersion = "0.0.0"
                cls._cryoloVersionSupported = False

        return cls._cryoloEnvFound, cls._cryoloVersion, cls._cryoloVersionSupported

pyworkflow.em.Domain.registerPlugin(__name__)
