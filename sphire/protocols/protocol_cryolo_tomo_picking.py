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
from pyworkflow.protocol import ProtStreamingBase

from tomo.objects import SetOfCoordinates3D
from tomo.protocols import ProtTomoPicking
import tomo.constants as tomoConst

from .. import Plugin
from ..constants import (INPUT_MODEL_GENERAL_DENOISED, STRAIGHTNESS_METHOD,
                         DIRECTIONAL_METHOD, CBOX_FILAMENTS_FOLDER)
from .protocol_base import ProtCryoloBase
import sphire.convert as convert

OUT_COORDINATES = 'output3DCoordinates'

class SphireProtCRYOLOTomoPicking(ProtCryoloBase, ProtTomoPicking):
    """ Picks particles in a set of tomograms. """
    _label = 'cryolo tomo picking'
    _devStatus = BETA
    _possibleOutputs = {OUT_COORDINATES: SetOfCoordinates3D}

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

        form.addSection(label="Filaments")
        form.addParam('doFilament', params.BooleanParam, default=False,
                      label='Activate filament mode?')
        form.addParam('box_distance', params.IntParam, default=20,
                      condition='doFilament',
                      label="Box distance (px)",
                      help="Distance in pixels between two boxes")
        form.addParam('minimum_number_boxes', params.IntParam, default=None,
                      allowsNull=True,
                      condition='doFilament',
                      label="Minimum number of boxes",
                      help="Minimum number of boxes per filament")

        form.addParam('straightness_method', params.EnumParam, default=1,
                      condition='doFilament',
                      label='Straightness method',
                      choices=['NONE', 'LINE_STRAIGHTNESS', 'RMSD'],
                      help="Method to measure the straightness of a line.\n"
                           "LINE_STRAIGHTNESS divides the length from start to "
                           "end by accumulated length between adjacent boxes.\n"
                           "RMSD calculates the root means squared deviation of "
                           "the line points to line given by start and the "
                           "endpoint of the filament. Adjust the "
                           "straightness_method accordingly!")

        form.addParam('straightness_threshold', params.FloatParam, default=0.95,
                      condition='doFilament',
                      label="Straightness threshold",
                      help="Threshold value for the straightness method. The default "
                           "value works good for LINE_STRAIGHTNESS. Lines with "
                           "a LINE_STRAIGHTNESS lower than this threshold get "
                           "split. For RMSD, lines with a RMSD higher than "
                           "this threshold will be split. A good value for "
                           "RMSD is 20 percent of your filament width")

        form.addParam('search_range_factor', params.FloatParam, default=1.41,
                      condition='doFilament',
                      label="Search range factor",
                      help="The search range for connecting boxes is the box "
                           "size times this factor")

        form.addParam('angle_delta', params.IntParam, default=10,
                      condition='doFilament',
                      label="Angle delta",
                      help="Angle delta in degree. This value is good more or "
                           "less straight filament. More curvy filament might "
                           "require values around 20")

        form.addParam('directional_method', params.EnumParam, default=1,
                      condition='doFilament',
                      label='Directional method',
                      choices=['CONVOLUTION', 'PREDICTED'],
                      help="Directional method")

        form.addParam('filament_width', params.IntParam, default=None,
                      condition='doFilament and directional_method==0',
                      label="Filament width (px)")

        form.addParam('mask_width', params.IntParam, default=100,
                      expertLevel=params.LEVEL_ADVANCED,
                      condition='doFilament and directional_method==0',
                      label="Mask width",
                      help="Mask width in pixel. A gaussian filter mask is used "
                           "to estimate the direction of the filaments. This "
                           "parameter defines how elongated the mask is. The "
                           "default value typically don't has to be changed")

        form.addParam('nomerging', params.BooleanParam, default=False,
                      condition='doFilament',
                      label='Do not merge filaments?')

        form.addParallelSection(threads=1, mpi=1)

        # Default box size --> 50
        form.getParam('boxSize').default = Integer(50)
        # Default lowpass --> 20
        form.getParam('absCutOffFreq').default = Float(20.0)

    def stepsGeneratorStep(self) -> None:
        """
        This step should be implemented by any streaming protocol.
        It should check its input and when ready conditions are met
        call the self._insertFunctionStep method.
        """
        closeSetStepDeps = []
        self.readingOutput()

        inputTomos = self.inputTomograms.get()
        while True:
            listTomoInput = list(inputTomos.getIdSet())
            if not inputTomos.isStreamOpen() and self.coordinatesRead == listTomoInput:
                self.info('Input set closed, all items processed\n')
                self._insertFunctionStep(self._closeOutputSet, prerequisites=closeSetStepDeps)
                break
            for tomo in inputTomos:
                if tomo.getTsId() not in self.coordinatesRead:
                    self.info(f"TS_ID input: {listTomoInput}\n"
                              f"TS_ID reading... {ts.getObjId()}\n"
                              f"TS_ID read: {self.TS_read}\n")
                    self.coordinatesRead.append(tomo.getTsId())
                    try:
                        createConfig = self._insertFunctionStep(self.createConfigStep, tomo, prerequisites=[])
                        runCryolo = self._insertFunctionStep(self.pickTomogramsStep, prerequisites=[createConfig])
                        createOutput = self._insertFunctionStep(self.createOutputStep, prerequisites=[runCryolo])
                        closeSetStepDeps.append(createOutput)

                    except Exception as e:
                        self.error(f'Error reading tomogram info: {e}')
                        self.error(f'tomogram : {tomo.getTsId()}')
                time.sleep(10)

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

        if not self.doFilament:  # tmin is for particles only
            args += " -tmin %d" % self.minLength.get()

        if not self.usingCpu():
            args += " -g %(GPU)s"  # Add GPU that will be set by the executor

        if self.lowPassFilter or self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            args += ' --cleanup'

        # Filament options
        if self.doFilament:
            args += " --filament -bd %d" % self.box_distance.get()
            args += " -sm %s" % STRAIGHTNESS_METHOD[self.straightness_method.get()]
            args += " -st %f" % self.straightness_threshold.get()
            args += " -sr %f" % self.search_range_factor.get()
            args += " -ad %d" % self.angle_delta.get()
            args += " --directional_method %s" % DIRECTIONAL_METHOD[self.directional_method.get()]
            args += " -mw %d" % self.mask_width.get()

            if self.minimum_number_boxes.get():
                args += " -mn3d %d" % self.minimum_number_boxes.get()

            if self.filament_width.get():
                args += " -fw %d" % self.filament_width.get()

            if self.nomerging.get():
                args += " --nomerging"

        Plugin.runCryolo(self, 'cryolo_predict.py', args, useCpu=not self.useGpu.get())

    def createOutputStep(self):
        setOfTomograms = self.inputTomograms.get()
        outputPath = self._getExtraPath("CBOX_3D") if not self.doFilament else self._getExtraPath(CBOX_FILAMENTS_FOLDER)
        suffix = self._getOutputSuffix(SetOfCoordinates3D)

        setOfCoord3D = self._createSetOfCoordinates3D(self.inputTomograms, suffix)
        setOfCoord3D.setName("tomoCoord")
        setOfCoord3D.setSamplingRate(setOfTomograms.getSamplingRate())

        if self.boxSize.get():  # Box size can be provided by the user
            boxSize = self.boxSize.get()
        else:  # If not crYOLO estimates it
            boxSize = self.getEstimatedBoxSize(self._getExtraPath('DISTR'))

        for tomogram in setOfTomograms.iterItems():
            filePath = os.path.join(outputPath, convert.getMicFn(tomogram, "cbox"))
            if os.path.exists(filePath) and os.path.getsize(filePath):
                tomogramClone = tomogram.clone()
                tomogramClone.copyInfo(tomogram)
                convert.readSetOfCoordinates3D(tomogramClone, setOfCoord3D,
                                               filePath, boxSize,
                                               origin=tomoConst.BOTTOM_LEFT_CORNER)

        name = self.OUTPUT_PREFIX + suffix
        self._defineOutputs(**{name: setOfCoord3D})
        self._defineSourceRelation(setOfTomograms, setOfCoord3D)

    def readingOutput(self) -> None:
        try:
            if hasattr(self, OUT_COORDINATES):
                outcoords = getattr(self, OUT_COORDINATES)
                for c in outcoords.iterItems():
                    if not c.getTomoId() in self.coordinatesRead:
                        self.coordinatesRead.append(outcoords.self.getSize())
            self.info(f'Picked tomos : {self.coordinatesRead}')
            self.outputSOTList_objID = self.coordinatesRead

        except AttributeError:  # There is no outputSetOfCoordinates
            pass
