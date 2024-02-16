# **************************************************************************
# *
# * Authors:    David Maluenda (dmaluenda@cnb.csic.es) [1]
# *             Peter Horvath (phorvath@cnb.csic.es) [1]
# *             J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [2]
# *
# * [1] Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# * [2] SciLifeLab, Stockholm University
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

import os

import pyworkflow.utils as pwutils
from pyworkflow.object import Integer
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import ProtParticlePickingAuto
import pwem.objects as emobj

from .. import Plugin
from ..constants import INPUT_MODEL_GENERAL_DENOISED
from .protocol_base import ProtCryoloBase
import sphire.convert as convert


class SphireProtCRYOLOPicking(ProtCryoloBase, ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs with crYOLO.
    """
    _label = 'cryolo picking'

    def __init__(self, **args):
        ProtParticlePickingAuto.__init__(self, **args)
        self.stepsExecutionMode = cons.STEPS_PARALLEL

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        ProtParticlePickingAuto._defineParams(self, form)
        ProtCryoloBase._defineParams(self, form)

        form.addParam('boxSizeFactor', params.FloatParam,
                      default=1.,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Adjust estimated box size by",
                      help="Value to multiply crYOLO estimated box size to be "
                           "registered with the SetOfCoordinates. It is usually "
                           "very tight.")

        form.addParallelSection(threads=1, mpi=1)

        self._defineStreamingParams(form)
        # Default batch size --> 16
        form.getParam('streamingBatchSize').setDefault(16)

    # --------------------------- INSERT steps functions ----------------------
    def _insertInitialSteps(self):
        stepId = self._insertFunctionStep(self.createConfigStep, self.inputMicrographs.get())
        return stepId

    # --------------------------- STEPS functions -----------------------------
    def _pickMicrographsBatch(self, micList, workingDir, gpuId):
        pwutils.cleanPath(workingDir)
        pwutils.makePath(workingDir)

        # Create folder with linked mics
        convert.convertMicrographs(micList, workingDir)

        configJson = os.path.relpath(self._getExtraPath('config.json'),
                                     workingDir)
        args = " -c %s" % configJson
        args += " -w %s" % self.getInputModel()
        args += " -i ./ -o ./ "
        args += " -t %0.3f" % self.conservPickVar
        args += " -nc %d" % self.numCpus

        if not self.usingCpu():
            args += " -g %s " % gpuId

        if self.lowPassFilter or self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            args += ' --cleanup'

        Plugin.runCryolo(self, 'cryolo_predict.py', args,
                         cwd=workingDir,
                         useCpu=self.usingCpu())

    def _pickMicrograph(self, micrograph, *args):
        """This function picks from a given micrograph"""
        self._pickMicrographList([micrograph], args)

    def _pickMicrographList(self, micList, *args):
        if not micList:  # maybe in continue cases, need to properly check
            return

        workingDir = self._getTmpPath(self.getMicsWorkingDir(micList))
        self._pickMicrographsBatch(micList, workingDir, '%(GPU)s')
        # Move output files to extra folder
        pwutils.moveTree(os.path.join(workingDir, "CBOX"), self._getExtraPath())

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs"""
        # Coordinates may have a boxSize (e.g. streaming case)
        boxSize = outputCoords.getBoxSize()
        if not boxSize:
            if self.boxSize.get():  # Box size can be provided by the user
                boxSize = self.boxSize.get()
            else:  # If not crYOLO estimates it
                boxSize = self.getEstimatedBoxSize(self._getTmpPath('micrographs_*/DISTR'))

                if self.boxSizeFactor.get() != 1:
                    boxSize = int(boxSize * self.boxSizeFactor.get())

            outputCoords.setBoxSize(boxSize)

        # Calculate if flip is needed
        # JMRT: Let's assume that all mics have same dims, so we avoid
        # to open the image file each time for checking this
        yFlipHeight = convert.getFlipYHeight(micDoneList[0].getFileName())

        # Create a reader to parse .cbox files
        # and a Coordinate object to add to output set
        reader = convert.CoordBoxReader(boxSize,
                                        yFlipHeight=yFlipHeight,
                                        boxSizeEstimated=self.boxSizeEstimated)
        coord = emobj.Coordinate()
        coord._cryoloScore = emobj.Float()

        for mic in micDoneList:
            cboxFile = convert.getMicFn(mic, "cbox")
            coordsFile = self._getExtraPath(cboxFile)
            if os.path.exists(coordsFile) and os.path.getsize(coordsFile):
                for x, y, z, score, _, _ in reader.iterCoords(coordsFile):
                    # Clean up objId to add as a new coordinate
                    coord.setObjId(None)
                    coord.setPosition(x, y)
                    coord.setMicrograph(mic)
                    coord._cryoloScore.set(score)
                    # Add it to the set
                    outputCoords.append(coord)

        # Register box size
        self.createBoxSizeOutput(outputCoords)

    def createBoxSizeOutput(self, coordSet):
        """ Output box size as an Integer. Other protocols can use it as
            IntParam with allowsPointer=True.
        """
        if not hasattr(self, "boxsize"):
            boxSize = Integer(coordSet.getBoxSize())
            self._defineOutputs(boxsize=boxSize)

    # -------------------------- UTILS functions ------------------------------
    def getMicsWorkingDir(self, micList):
        wd = 'micrographs_%s' % micList[0].strId()
        if len(micList) > 1:
            wd += '-%s' % micList[-1].strId()
        return wd
