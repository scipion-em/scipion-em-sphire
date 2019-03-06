# **************************************************************************
# *
# * Authors:     David Maluenda (dmaluenda@cnb.csic.es)
# *              Peter Horvath (phorvath@cnb.csic.es)
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
import os, json, csv
from pyworkflow.em.data import Coordinate
from pyworkflow.utils import path
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pyworkflow.em.protocol import ProtParticlePickingAuto
from pyworkflow.utils.path import removeBaseExt
from sphire.convert import getFlippingParams, preparingCondaProgram, \
    getBoxSize, createMic
from sphire.constants import CRYOLO_GENMOD_VAR
from sphire import Plugin


class SphireProtCRYOLOPicking(ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
    """
    _label = 'crYOLO picking'

    def __init__(self, **args):
        ProtParticlePickingAuto.__init__(self, **args)

    # --------------------------- DEFINE param functions ------------------------
    def _defineParams(self, form):
        ProtParticlePickingAuto._defineParams(self, form)

        form.addParam('useGenMod', params.BooleanParam,
                      default=True,
                      label='Use general model?',
                      help="You might use a general network model that consists "
                           "of real, simulated, particle free datasets"
                      " on various grids with contaminations and skip training "
                           "completely or if you would like to "
                           "improve the results you can use the model from the "
                           "previous training step by answering no. The general"
                           " model can be found.")
        form.addParam('sphireTraining', params.PointerParam,
                      allowsNull=True,
                      condition="useGenMod == False",
                      label="Cryolo training run",
                      pointerClass='SphireProtCRYOLOTraining',
                      help='Select the previous cryolo training run.')
        form.addParam('conservPick', params.BooleanParam,
                      expertLevel=cons.LEVEL_ADVANCED,
                      default=False,
                      label="Pick conservatively?",
                      help='If you want to pick less conservatively or more '
                           'conservatively you might want to change'
                            ' the selection threshold from the default of 0.3 '
                           'to a less conservative value like 0.2 or '
                            'more conservative value like 0.4?')
        form.addParam('conservPickVar', params.FloatParam,
                      condition="conservPick",
                      label="Insert value",
                      help="less conservative value:0.2, conservative value:0.4.")
        form.addParam('lowPassFilter', params.BooleanParam,
                      expertLevel=cons.LEVEL_ADVANCED,
                      default=False,
                      label="Low-pass filter",
                      help="CrYOLO works on original micrographs but the "
                           "results will be probably improved by the application"
                           " of a reasonable low-pass filter.")
        form.addParam('absCutOffFreq', params.FloatParam,
                      default=0.1,
                      condition='lowPassFilter',
                      label="Absolute cut off frequency",
                      help="Specifies the absolute cut-off frequency for the "
                           "low-pass filter.")
        form.addParam('input_size', params.IntParam,
                      default=1024,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Input size",
                      help="This is the size to which the input is rescaled "
                           "before passed through the network."
                           "For example the default value would be 1024x1024.")
        form.addParam('boxSize', params.IntParam,
                      default=100,
                      label='Box Size',
                      allowsPointers=True,
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel.')
        form.addParam('max_box_per_image', params.IntParam,
                      default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for "
                           "the memory handling. Keep the default value of "
                           "600 or 1000.")
        form.addParam('num_patches', params.IntParam,
                      default=1,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label='Number of Patches',
                      help='If specified the patch mode will be used. A value '
                           'of "2" means, that 2x2 patches will be used.')
        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                       expertLevel=cons.LEVEL_ADVANCED,
                       label="Choose GPU IDs",
                       help="GPU may have several cores. Set it to zero"
                            " if you do not know what we are talking about."
                            " First core index is 0, second 1 and so on."
                            " Motioncor2 can use multiple GPUs - in that case"
                            " set to i.e. *0 1 2*.")

        form.addParallelSection(threads=1, mpi=1)

        self._defineStreamingParams(form)

    # --------------------------- INSERT steps functions -----------------------
    def _insertInitialSteps(self):

        self.particlePickingRun = self.sphireTraining.get()

        self._insertFunctionStep("createConfigurationFileStep")


    # --------------------------- STEPS functions ------------------------------
    def createConfigurationFileStep(self):
        inputSize = self.input_size.get()
        boxSize = getBoxSize(self)
        maxBoxPerImage = self.max_box_per_image.get()
        numPatches = self.num_patches.get()
        absCutOfffreq = self.absCutOffFreq.get()

        model = {
            "architecture": "PhosaurusNet",
            "input_size": inputSize,
            "anchors": [boxSize, boxSize],
            "max_box_per_image": maxBoxPerImage,
            "num_patches": numPatches
        }

        if self.lowPassFilter == True:
            model.update({"filter": [absCutOfffreq,"filtered"]})
            filteredDir = self._getExtraPath("filtered")
            path.makePath('filteredDir')

        jsonDict = {"model": model}

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def _pickMicrograph(self, micrograph, *args):
        """This function picks from a given micrograph"""

        self._pickMicrographList([micrograph], args)


    def _pickMicrographList(self, micList, *args):

        MIC_FOLDER = 'mics'
        mics = self._getTmpPath()

        # Create folder with linked mics
        for micrograph in micList:
            createMic(micrograph, mics)

        # clear the mrc files
        dirName = self._getExtraPath()
        test = os.listdir(dirName)
        for item in test:
            if item.endswith(".mrc"):
                os.remove(os.path.join(dirName, item))

        if self.useGenMod == True:
            wParam = Plugin.getVar(CRYOLO_GENMOD_VAR)
        else:
            wParam = os.path.abspath(self.particlePickingRun.getModel())
        gParam = (' '.join(str(g) for g in self.getGpuList()))
        params = "-c %s " % self._getExtraPath('config.json')
        params += " -w %s -g %s" % (wParam, gParam)
        params += " -i %s/" % mics
        params += " -o %s/" % mics
        if self.conservPick == True:
            tParam = self.conservPickVar.get()
            params += " -t %f" % tParam

        program2 = 'cryolo_predict.py'
        label = 'predict'
        preparingCondaProgram(self, program2, params, label)
        shellName = os.environ.get('SHELL')
        self.info("**Running:** %s %s" % (program2, params))
        self.runJob('%s %s/script_%s.sh' % (shellName, self._getExtraPath(), label), '',
                    env=Plugin.getEnviron())

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs"""

        # Evaluate if micDonelist is empty
        if len(micDoneList) == 0:
            return

        # Create a map micname --> micId
        micMap = {}
        for mic in micDoneList:
            key = removeBaseExt(mic.getFileName())
            micMap[key] = (mic.getObjId(), mic.getFileName())

        outputCoords.setBoxSize(getBoxSize(self))
        # Read output file (4 column tabular file)
        outputCRYOLOCoords = self._getTmpPath("EMAN")

        # Calculate if flip is needed
        flip, y = getFlippingParams(mic.getFileName())

        # For each box file
        for boxFile in os.listdir(outputCRYOLOCoords):
            if '.box' in boxFile:
                # Add coordinates file
                self._coordinatesFileToScipion(outputCoords,
                                               os.path.join(outputCRYOLOCoords,
                                                            boxFile), micMap,
                                               flipOnY=flip, imgHeight=y)

        # Move mics and box files
        path.moveTree(self._getTmpPath(), self._getExtraPath())
        path.makePath(self._getTmpPath())


    def _coordinatesFileToScipion(self, coordSet, coordFile, micMap, flipOnY=False, imgHeight=None ):

        with open(coordFile, 'r') as f:
            # Configure csv reader
            reader = csv.reader(f, delimiter='\t')

            # (width, height, foo) = self.inputMicrographs.get().getDim()

            for x,y,xBox,ybox in reader:

                # Create a scipion coordinate item
                offset = int(getBoxSize(self)/2)

                # USE the flip and imageHeight!! To flip or not to flip!
                sciX = int(float(x)) + offset
                sciY = int(float(y)) + offset

                if flipOnY == True:
                    sciY = imgHeight - sciY

                coordinate = Coordinate(x=sciX, y=sciY)
                micBaseName = removeBaseExt(coordFile)
                micId, micName = micMap[micBaseName]
                coordinate.setMicId(micId)
                coordinate.setMicName(micName)
                # Add it to the set
                coordSet.append(coordinate)

    def createOutputStep(self):
        pass
    # --------------------------- INFO functions -------------------------------
    def _summary(self):
        summary = []

        if self.useGenMod == True:
            summary.append("Coordinates were picked by the general model: %s \
             \n" % (Plugin.getVar(CRYOLO_GENMOD_VAR)))
        else:
            summary.append("Coordinates were picked by the trained model: %s \
             \n" % (self.sphireTraining.get().getModel()))

        return summary

    def _validate(self):
        validateMsgs = []

        if self.useGenMod == True:
            if Plugin.getVar(CRYOLO_GENMOD_VAR) == '':
                validateMsgs.append(
                              "The general model for cryolo must be "
                              "download from Sphire website and "
                              "~/.config/scipion/scipion.conf must contain "
                              "the '%s' parameter pointing to "
                              "the downloaded file." % CRYOLO_GENMOD_VAR)
            elif not os.path.isfile(Plugin.getVar(CRYOLO_GENMOD_VAR)):
                validateMsgs.append("General model not found at '%s' and "
                              "needed when you would like to use the general"
                              " network (i.e.: non-training mode). "
                              "Please check the path in "
                              "the ~/.config/scipion/scipion.conf.\n"
                              "You can download the file from "
                              "the Sphire website."
                              % Plugin.getVar(CRYOLO_GENMOD_VAR))
        return validateMsgs







