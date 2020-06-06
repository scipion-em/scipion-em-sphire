# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
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

import os

import pyworkflow.utils as pwutils
import pyworkflow.protocol.params as params
from pwem.protocols import ProtImport

from sphire.objects import CryoloModel


class SphireProtCryoloImport(ProtImport):
    """ Protocol to import an existing crYOLO training model.
    The model will be registered as an output of this protocol and
    it can be used later for further training or for picking.
    """
    _label = 'cryolo import'

    # -------------------------- DEFINE param functions -----------------------
    def _defineParams(self, form):
        form.addSection(label='Import')
        form.addParam('modelPath', params.PathParam,
                      label="Training model path",
                      help="Provide the path of a previous crYOLO training "
                           "model. ")

    # --------------------------- INSERT steps functions ----------------------
    def _insertAllSteps(self):
        self._insertFunctionStep("importModelStep")

    # --------------------------- STEPS functions -----------------------------
    def importModelStep(self):
        """ Create a link to the provided input model path
        and register the output to be used later for further training
        or picking.
        """
        absPath = os.path.abspath(self.modelPath.get())
        outputPath = self._getExtraPath(os.path.basename(absPath))
        self.info("Creating link:\n"
                  "%s -> %s" % (outputPath, absPath))
        self.info("NOTE: If you move this project to another computer, the symbolic"
                  "link to the model will be broken, but you can update the link "
                  "and get it working again. ")

        pwutils.createAbsLink(absPath, outputPath)

        self._defineOutputs(outputModel=CryoloModel(outputPath))
