# **************************************************************************
# *
# * Authors: Yunior C. Fonseca Reyna    (cfonseca@cnb.csic.es)
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

import os

import pyworkflow.utils as pwutils
from pyworkflow import BETA
from pyworkflow.object import Integer, Float
import pyworkflow.protocol.params as params

from tomo.objects import SetOfCoordinates3D
from tomo.protocols import ProtTomoPicking
import tomo.constants as tomoConst

from .. import Plugin
from ..constants import INPUT_MODEL_GENERAL_DENOISED
from .protocol_base import ProtCryoloBase
import sphire.convert as convert


class SphireProtCRYOLOTomoPicking(ProtCryoloBase, ProtTomoPicking):
    """ Picks particles in a set of tomograms.
    """
    _label = 'cryolo tomo picking'
    _devStatus = BETA
    _possibleOutputs = {'output3DCoordinates': SetOfCoordinates3D}

    def __init__(self, **kwargs):
        ProtTomoPicking.__init__(self, **kwargs)

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        ProtTomoPicking._defineParams(self, form)
        ProtCryoloBase._defineParams(self, form)

        form.addSection(label="Tracing")
        form.addParam('searchRange', params.IntParam, default=-1,
                      label="Search range (px)",
                      help="Search range in pixel. On default it will "
                           "choose 25 percent of the box size (default: -1).")
        form.addParam('minLength', params.IntParam, default=5,
                      label="Minimum length",
                      help="The minimum number of boxes in one trace to be "
                           "considered as valid particle (default: 5).")
        form.addParam('memory', params.IntParam, default=0,
                      label="Tracing memory",
                      help="The maximum number of frames during which a "
                           "particle can vanish, then reappear nearby, "
                           "and be considered the same particle (default: 0).")

        form.addParallelSection(threads=1, mpi=1)

        # Default box size --> 50
        form.getParam('boxSize').default = Integer(50)
        # Default lowpass --> 0.3
        form.getParam('absCutOffFreq').default = Float(0.3)

    def _insertAllSteps(self):
        self._insertFunctionStep(self.createConfigStep)
        self._insertFunctionStep(self.pickTomogramsStep)
        self._insertFunctionStep(self.createOutputStep)

    # -------------------------- STEPS functions ------------------------------
    def pickTomogramsStep(self):
        """This function picks from a given set of Tomograms"""
        inputTomos = self.inputTomograms.get()
        tomogramsList = [t.clone() for t in inputTomos.iterItems()]

        tomogramsDir = self._getTmpPath("tomograms")
        outputDir = self._getExtraPath()
        pwutils.cleanPath(tomogramsDir)
        pwutils.makePath(tomogramsDir)

        # Create folder with linked tomograms
        convert.convertMicrographs(tomogramsList, tomogramsDir)

        args = "-c %s" % self._getExtraPath('config.json')
        args += " -w %s" % self.getInputModel()
        args += " -i %s/" % tomogramsDir
        args += " -o %s/" % outputDir
        args += " -t %0.3f" % self.conservPickVar
        args += " -nc %d" % self.numCpus.get()
        args += " --tomogram"
        args += " -tsr %d" % self.searchRange.get()
        args += " -tmem %d" % self.memory.get()
        args += " -tmin %d" % self.minLength.get()

        if not self.usingCpu():
            args += " -g %(GPU)s"  # Add GPU that will be set by the executor

        if self.lowPassFilter or self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            args += ' --cleanup'

        Plugin.runCryolo(self, 'cryolo_predict.py', args,
                         useCpu=not self.useGpu.get())

    def createOutputStep(self):
        setOfTomograms = self.inputTomograms.get()
        outputPath = self._getExtraPath("CBOX_3D")
        suffix = self._getOutputSuffix(SetOfCoordinates3D)

        setOfCoord3D = self._createSetOfCoordinates3D(self.inputTomograms, suffix)
        setOfCoord3D.setName("tomoCoord")
        setOfCoord3D.setSamplingRate(setOfTomograms.getSamplingRate())

        if self.boxSize.get():  # Box size can be provided by the user
            boxSize = self.boxSize.get()
        else:  # If not crYOLO estimates it
            boxSize = self.getEstimatedBoxSize(self._getExtraPath('DISTR'))

        setOfCoord3D.setBoxSize(boxSize)

        for tomogram in setOfTomograms.iterItems():

            filePath = os.path.join(outputPath, convert.getMicFn(tomogram, "cbox"))
            if os.path.exists(filePath):
                tomogramClone = tomogram.clone()
                tomogramClone.copyInfo(tomogram)
                convert.readSetOfCoordinates3D(tomogramClone, setOfCoord3D, filePath,
                                               boxSize,
                                               origin=tomoConst.BOTTOM_LEFT_CORNER)


        name = self.OUTPUT_PREFIX + suffix
        self._defineOutputs(**{name: setOfCoord3D})
        self._defineSourceRelation(setOfTomograms, setOfCoord3D)

