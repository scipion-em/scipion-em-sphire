# **************************************************************************
# *
# * Authors:     Peter ... (p...@cnb.csic.es)
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

import pyworkflow.em
from pyworkflow.utils import Environ

from sphire.constants import *


_logo = "sphire_logo.jpg"
_sphirePluginDir = os.path.dirname(os.path.abspath(__file__))

class Plugin(pyworkflow.em.Plugin):
    _homeVar = CRYOLO_HOME_VAR
    _pathVars = [CRYOLO_HOME_VAR]
    _supportedVersions = CRYOLO_V1_1_0

    @classmethod
    def _defineVariables(cls):
        cls._defineEmVar(CRYOLO_HOME_VAR, 'sphire_1.1.0')
        #define default value for CRYOLO_MODEL

    @classmethod
    def getEnviron(cls):
        """ Setup the environment variables needed to launch sphire. """
        environ = Environ(os.environ)
        print("getEnvirion(): %s" % os.environ.get(cls.getHome()))
        if ('%s' % Plugin._homeVar) in environ:
            environ.update({'PATH': str.join(CRYOLO_HOME, 'bin'),
                            }, position=Environ.BEGIN)
            if 'PYTHONPATH' in environ:
                # this is required for python virtual env to work
                del environ['PYTHONPATH']

        else:
            # TODO: Find a generic way to warn of this situation
            print("%s variable not set on environment." % cls.getHome())
        return environ

    @classmethod
    def validateInstallation(cls):
        """ This function will be used to check if package is properly installed."""
        missingPaths = ["%s: %s" % (cls._homeVar, cls.getHome())] \
            if not os.path.exists(Plugin._homeVar) else []

    @classmethod
    def isVersionActive(cls):
        return cls.getActiveVersion().startswith(CRYOLO_V1_1_0)

    @classmethod
    def defineBinaries(cls, env):
        """ Define required binaries in the given Environment. """

        env.addPackage('sphire', version='1.1.0',
                       tar='shpire-1.1.0.tgz',
                       default=True)


pyworkflow.em.Domain.registerPlugin(__name__)