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
import os, json
from pyworkflow.em.protocol import ProtParticlePicking
import pyworkflow.protocol.constants as cons
from pyworkflow.utils import path
import pyworkflow.protocol.params as params
from pyworkflow.utils.path import removeBaseExt
from sphire import Plugin
from sphire.convert import writeSetOfCoordinates, getFlippingParams,\
    preparingCondaProgram, getBoxSize

MODEL = "model.h5"

class SphireProtCRYOLOTraining(ProtParticlePicking):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
    """
    _label = 'crYOLO training'

    def __init__(self, **args):
        ProtParticlePicking.__init__(self, **args)

    #--------------------------- DEFINE param functions ------------------------
    def _defineParams(self, form):
        ProtParticlePicking._defineParams(self, form)
        form.addParam('inputCoordinates', params.PointerParam,
                      pointerClass='SetOfCoordinates',
                      label='Input coordinates', important=True,
                      help='Select the SetOfCoordinates to be used for training.')
        form.addParam('memory', params.FloatParam, default=2,
                      label='Memory to use (In Gb)', expertLevel=2)
        form.addParam('input_size', params.IntParam, default=1024,
                      label="Input size",
                      help="crYOLO extracts a patch and rescales to the given"
                           " input size and uses the resized patch for training.")
        form.addParam('boxSize', params.IntParam, default=100,
                      label='Box Size',
                      allowsPointers=True,
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel.')
        form.addParam('eFlag', params.BooleanParam, default=False,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Change training time?",
                      help="The training stops when the loss metric on the "
                           "validation data does not improve 5 times in a row."
                           " This is typically enough. However you might want to"
                           " give the training more time to find the best model."
                           " You might increase the not changed in a row "
                           "parameter to the default value.")
        form.addParam('eFlagParam', params.IntParam, default=10,
                      condition='eFlag',
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Not changed in a row a parameter",
                      help="The default value is 10. The training stops when the"
                           " loss metric on the validation data does not "
                           "improve 5 times in a row. crYOLO will select "
                           "validation data.")
        form.addParam('max_box_per_image',params.IntParam, default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for" 
                           "the memory handling. Keep the default value of 600 "
                           "or 1000. ")
        form.addParam('nb_epoch', params.BooleanParam, default=False,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Set number of iteration?",
                      help="Maximum number of epochs the network will train."
                           " Basically never reach this number, as crYOLO "
                           "stops training if it recognize that the validation "
                           "loss is not improving anymore.")
        form.addParam('nb_epochVal', params.IntParam, default=50,
                      expertLevel=cons.LEVEL_ADVANCED,
                      condition='nb_epoch',
                      label="Maximum number of iterations",
                      help="Maximum number of epochs the network will train."
                           " Basically never reach this number, as crYOLO "
                           "stops training if it recognize that the validation "
                           "loss is not improving anymore.")
        form.addParam('learning_rates', params.FloatParam, default=1e-4,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Learning rates",
                      help="If the number is too small convergence can be slow,"
                           " if it is.")
        form.addParam('lowPassFilter', params.BooleanParam,
                      expertLevel=cons.LEVEL_ADVANCED,
                      default=False,
                      label="Low-pass filter",
                      help="CrYOLO works on original micrographs but the results"
                           " will be probably improved by the application of a "
                           "reasonable low-pass filter.")
        form.addParam('absCutOffFreq', params.FloatParam, default=0.1,
                  expertLevel=cons.LEVEL_ADVANCED,
                  condition='lowPassFilter',
                  label="Absolute cut off frequency",
                  help="Specifies the absolute cut-off frequency for the "
                       "low-pass filter.")
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


    # --------------------------- INSERT steps functions ------------------------
    def _insertAllSteps(self):
        self._insertFunctionStep("convertTrainCoordsStep")

        self._insertFunctionStep("createConfigurationFileStep")

        self._insertFunctionStep("warmUpTheNetwork")

        self._insertFunctionStep("cryoloModelingStep")


    # --------------------------- STEPS functions ------------------------------
    def convertTrainCoordsStep(self):
        """ Converts a set of coordinates to box files and binaries to mrc
        if needed. It generates 2 folders 1 for the box files and another for
        the mrc files. To be passed (the folders as params for cryolo
        """

        # Get pointer to input micrographs
        self.inputMics = self.inputMicrographs.get()

        coordSet = self.inputCoordinates.get()

        trainCoordDir = self._getExtraPath('train_annotation')
        path.makePath(trainCoordDir)

        # call the write set of Coordinates passing the createMic function
        writeSetOfCoordinates(trainCoordDir, coordSet,
                              self._getExtraPath('train_image'))

    def createConfigurationFileStep(self):
        inputSize = self.input_size.get()
        boxSize = getBoxSize(self)
        maxBoxPerImage = self.max_box_per_image.get()
        absCutOfffreq = self.absCutOffFreq.get()
        numberOfEpochs = self.nb_epochVal.get()
        learningRates = self.learning_rates.get()

        filteredDir = self._getExtraPath('filtered')
        path.makePath('filteredDir')


        model = {"architecture": "PhosaurusNet",
                 "input_size": inputSize,
                 "anchors": [boxSize, boxSize],
                 "max_box_per_image": maxBoxPerImage,
                 "num_patches": 1
                 }

        train = {"train_image_folder": "train_image/",
                 "train_annot_folder": "train_annotation/",
                 "train_times": 10,
                 "pretrained_weights": MODEL,
                 "batch_size": 6,
                 "learning_rate": learningRates,
                 "nb_epoch": numberOfEpochs,
                 "warmup_epochs": 0,
                 "object_scale": 5.0,
                 "no_object_scale": 1.0,
                 "coord_scale": 1.0,
                 "class_scale": 1.0,
                 "log_path": "logs/",
                 "saved_weights_name": MODEL,
                 "debug": True
                 }

        if self.lowPassFilter == True:
            model.update({"filter": [absCutOfffreq,"filtered"]})
            filteredDir = self._getExtraPath("filtered")
            path.makePath('filteredDir')

        valid = {"valid_image_folder": "",
                 "valid_annot_folder": "",
                 "valid_times": 1
                 }

        jsonDict = {"model": model, "train": train, "valid": valid}


        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def getModel(self):
        return self._getExtraPath(MODEL)

    def warmUpTheNetwork(self):

        wParam = 3
        gParam = (' '.join(str(g) for g in self.getGpuList()))
        params = "-c config.json"
        params += " -w %s -g %s" % (wParam, gParam)

        program = 'cryolo_train.py'
        label = 'train'
        preparingCondaProgram(self, program, params, label)
        shellName = os.environ.get('SHELL')
        self.info("**Running:** %s %s" % (program, params))
        self.runJob('%s ./script_%s.sh' % (shellName, label), '', cwd=self._getExtraPath(),
                    env=Plugin.getEnviron())


    def cryoloModelingStep(self):

        wParam = 0  # define this in the form ???
        gParam = (' '.join(str(g) for g in self.getGpuList()))
        params = "-c config.json"
        params += " -w %s -g %s" % (wParam, gParam)
        if self.eFlag == True:
            params += " -e %d" % self.eFlagParam

        program = 'cryolo_train.py'
        label = 'train'
        preparingCondaProgram(self, program, params, label)
        shellName = os.environ.get('SHELL')
        self.info("**Running:** %s %s" % (program, params))
        self.runJob('%s ./script_%s.sh' % (shellName, label), '', cwd=self._getExtraPath(),
                    env=Plugin.getEnviron())


    def readCoordsFromMics(self, outputDir, micDoneList , outputCoords):
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
        outputCRYOLOCoords = self._getTmpPath()

        # Calculate if flip is needed
        flip, y = getFlippingParams(mic.getFileName())

        # For each box file
        for boxFile in os.listdir(outputCRYOLOCoords):
            if '.box' in boxFile:
                # Add coordinates file
                self._coordinatesFileToScipion(outputCoords, os.path.join(outputCRYOLOCoords,boxFile), micMap, flipOnY=flip, imgHeight=y)

        # Move mics and box files
        path.moveTree(self._getTmpPath(), self._getExtraPath())
        path.makePath(self._getTmpPath())


    # --------------------------- INFO functions -------------------------------
    def _summary(self):

        summary = ['This protocol does not generate any output.',
                   'The model.h5 were written to be used optionally in ',
                   'crYOLO-picking protocol.']

        return summary

    def _validate(self):
        validateMsgs = []

        if self.inputCoordinates is None:
            validateMsgs.append("Please introduce a set of coordinates, obtained"
                                " from a previous picking run. Typically the "
                                "number of coordinates from 10 micrpgraphs are "
                                "a good start.")

        # mic_size = self.inputMicrographs.get().getDim()
        # if self.input_size > mic_size[0]:
        #     validateMsgs.append("The input size is bigger than the micrograph size")

        return validateMsgs





