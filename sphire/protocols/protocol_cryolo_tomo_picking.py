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
import glob

import pyworkflow.utils as pwutils
from pyworkflow import BETA
from pyworkflow.object import Boolean, Integer

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
    boxSizeEstimated = Boolean(False)
    _devStatus = BETA
    _possibleOutputs = {'output3DCoordinates': SetOfCoordinates3D}

    def __init__(self, **kwargs):
        ProtTomoPicking.__init__(self, **kwargs)

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        ProtTomoPicking._defineParams(self, form)
        ProtCryoloBase._defineParams(self, form)

        form.addParallelSection(threads=1, mpi=1)

        # Default box size --> 50
        form.getParam('boxSize').default = Integer(50)

    def _insertAllSteps(self):
        self._insertFunctionStep(self.createConfigStep)
        self._insertFunctionStep(self.pickTomogramsStep)
        self._insertFunctionStep(self.createOutputStep)

    # -------------------------- STEPS functions ------------------------------
    def pickTomogramsStep(self):
        """This function picks from a given set of Tomograms"""
        tomogramsList = self.inputTomograms.get()

        tomogramsDir = self._getTmpPath("tomograms")
        outputDir = self._getExtraPath()
        pwutils.cleanPath(tomogramsDir)
        pwutils.makePath(tomogramsDir)

        # Create folder with linked tomograms
        for tomogram in tomogramsList:
            convert.convertTomograms([tomogram], tomogramsDir)

        args = "-c %s" % self._getExtraPath('config.json')
        args += " -w %s" % self.getInputModel()
        args += " -i %s/" % tomogramsDir
        args += " -o %s/" % outputDir
        args += " -t %0.3f" % self.conservPickVar
        args += " -nc %d" % self.numCpus.get()
        args += " --tomogram"

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
        coord3DSetDict = {}

        setOfCoord3D = self._createSetOfCoordinates3D(setOfTomograms, suffix)
        setOfCoord3D.setName("tomoCoord")
        setOfCoord3D.setPrecedents(setOfTomograms)
        setOfCoord3D.setSamplingRate(setOfTomograms.getSamplingRate())
        setOfCoord3D.setBoxSize(self.boxSize.get())

        for tomogram in setOfTomograms.iterItems():
            outFile = '%s%05d%s' % (pwutils.removeBaseExt(tomogram.getFileName()),
                                    tomogram.getObjId(), '.cbox')
            pattern = os.path.join(outputPath, outFile)
            files = glob.glob(pattern)

            if not files or not os.path.isfile(files[0]):
                continue

            coord3DSetDict[tomogram.getObjId()] = setOfCoord3D

            # Populate Set of 3D Coordinates
            filePath = os.path.join(outputPath, outFile)
            tomogramClone = tomogram.clone()
            tomogramClone.copyInfo(tomogram)
            convert.readSetOfCoordinates3D(tomogramClone, coord3DSetDict, filePath,
                                           self.boxSize.get(),
                                           origin=tomoConst.BOTTOM_LEFT_CORNER)
            name = self.OUTPUT_PREFIX + suffix
            args = {}
            args[name] = setOfCoord3D
            self._defineOutputs(**args)
            self._defineSourceRelation(setOfTomograms, setOfCoord3D)

            # Update Outputs
            for index, coord3DSet in coord3DSetDict.items():
                self._updateOutputSet(name, coord3DSet,
                                      state=coord3DSet.STREAM_CLOSED)
