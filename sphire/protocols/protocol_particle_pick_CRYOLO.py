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
import csv, os

from pyworkflow.em import *
import pyworkflow.protocol.constants as cons
from pyworkflow.utils.path import replaceExt, getExt, copyFile
from sphire import Plugin
from sphire.constants import CRYOLO_MODEL_VAR
from sphire.convert import coordinateToRow, writeSetOfCoordinates, \
    getFlippingParams


class SphireProtCRYOLO(ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
    """
    _label = 'crYOLO picking'

    def __init__(self, **args):
        ProtParticlePickingAuto.__init__(self, **args)

    #--------------------------- DEFINE param functions ------------------------
    def _defineParams(self, form):
        ProtParticlePicking._defineParams(self, form)
        form.addParam('trainDataset', params.BooleanParam, default=True,
                      label='Train dataset?',
                      help='Train dataset by providing manually picked coordinates '
                           'to create a model, which will be used to automatically '
                      'pick coordinates from the micrographs')
        form.addParam('inputCoordinates', params.PointerParam,
                      condition='trainDataset',
                      pointerClass='SetOfCoordinates',
                      label='Input coordinates', important=True,
                      help='Select the SetOfCoordinates to be used for training.')
        form.addParam('memory', FloatParam, default=2,
                      label='Memory to use (In Gb)', expertLevel=2)
        form.addParam('input_size', params.IntParam, default= 1024,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Input size",
                      help="crYOLO extracts a patch and rescales to the given"
                           " input size and uses the resized patch for traning.")
        form.addParam('bxSzFromCoor', BooleanParam, default=False,
                      label='Use an input coordinates for box size')
        form.addParam('boxSize', IntParam, default=100,
                      condition='bxSzFromCoor==False',
                      label='Box Size',
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel.')
        form.addParam('coordsToBxSz', PointerParam, pointerClass='SetOfCoordinates',
                      condition='bxSzFromCoor==True',
                      label='Coordinates to extract the box size.',
                      help='Coordinates to extract the box size. '
                           'It can be an empty set.')
        form.addParam('batch_size', params.IntParam, default= 3,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Batch size",
                      help="Parameter you can set the number of images picked as batch."
                           " Note this batch size is different from scipion batch size"
                           " in streaming.")
        form.addParam('learning_rates', params.FloatParam, default= 1e-4,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Learning rates",
                      help="If the number is too small convergence can be slow, if it is "
                           "too large it can diverge.")
        form.addParam('max_box_per_image', params.IntParam, default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image")
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

    #--------------------------- INSERT steps functions ------------------------
    def _insertInitialSteps(self):
        # Get pointer to input micrographs
        self.inputMics = self.inputMicrographs.get()

        steps = [self._insertFunctionStep('createConfigurationFileStep')]
        if self.trainDataset == True:
            steps.append(self._insertFunctionStep('convertTrainCoordsStep'))
            steps.append(self._insertFunctionStep('cryoloModelingStep'))

        return steps

    # --------------------------- STEPS functions ------------------------------
    def convertTrainCoordsStep(self):
        """ Converts a set of coordinates to box files and binaries to mrc
        if needed. It generates 2 folders 1 for the box files and another for
        the mrc files. To be passed (the folders as params for cryolo
        """

        coordSet = self.inputCoordinates.get()

        trainMicDir = self._getExtraPath('train_image')
        pwutils.path.makePath(trainMicDir)

        trainCoordDir = self._getExtraPath('train_annotation')
        pwutils.path.makePath(trainCoordDir)

        def createMic(micId):
            # we only copy the micrographs once
            mic = self.inputMics[micId]
            fileName = mic.getFileName()
            extensionFn =getExt(fileName)
            if extensionFn != ".mrc":
                fileName1 = replaceExt(fileName, "mrc")
                ih = ImageHandler()   #initalize as an object
                ih.convert(extensionFn, fileName1)

            copyFile(mic.getFileName(), trainMicDir)

        # call the write set of Coordinates passing the createMic function
        writeSetOfCoordinates(trainCoordDir, coordSet, createMic)

    def createConfigurationFileStep(self):
        inputSize = self.input_size.get()
        boxSize = self.getBoxSize()
        maxBoxPerImage = self.max_box_per_image.get()

        model = {"architecture": "crYOLO",
                 "input_size": inputSize,
                 "anchors": [boxSize, boxSize],
                 "max_box_per_image": maxBoxPerImage,
                  }

        if self.trainDataset == False:
            model.update({"overlap_patches": 200, "num_patches": 3,
                          "architecture": "YOLO"})

        train = { "train_image_folder": "train_image/",
                  "train_annot_folder": "train_annotation/",
                  "train_times": 10,
                  "pretrained_weights": "model.h5",
                  "batch_size": 3,
                  "learning_rate": 1e-4,
                  "nb_epoch": 50,
                  "warmup_epochs": 0,
                  "object_scale": 5.0,
                  "no_object_scale": 1.0,
                  "coord_scale": 1.0,
                  "class_scale": 1.0,
                  "log_path": "logs/",
                  "saved_weights_name": "model.h5",
                  "debug": True
                           }

        valid = {"valid_image_folder": "",
                 "valid_annot_folder": "",
                 "valid_times": 1
                 }


        jsonDict = {"model" : model}

        if self.trainDataset == True:
            jsonDict.update({"train" : train, "valid" : valid})

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def cryoloModelingStep(self):

        wParam = 3  # define this in the form ???
        gParam = (' '.join(str(g) for g in self.getGpuList()))
        eParam = 0  # define this in the form ???
        params = "-c config.json"
        params += " -w %s -g %s" % (wParam, gParam)
        if eParam != 0:
            params += " -e %s" % eParam

        program = getProgram('cryolo_train.py')
        label = 'train'
        self._preparingCondaProgram(program, params, label)
        shellName = os.environ.get('SHELL')
        self.info("**Running:** %s %s" % (program, params))
        self.runJob('%s ./script_%s.sh' % (shellName, label), '', cwd=self._getExtraPath(),
                    env=Plugin.getEnviron())



    def _pickMicrograph(self, micrograph, *args):
        "This function picks from a given micrograph"
        self._pickMicrographList([micrograph], args)


    def _pickMicrographList(self, micList, *args):
        #clear the extra folder
        #pwutils.path.cleanPath(self._getExtraPath())

        MIC_FOLDER = 'mics'   #refactor--->extract--->constant, more robust
        mics = self._getTmpPath()

        # Create folder with linked mics
        for micrograph in micList:
            source = os.path.abspath(micrograph.getFileName())
            basename = os.path.basename(source)
            dest = os.path.abspath(os.path.join(mics, basename))
            pwutils.path.createLink(source, dest)


        if self.trainDataset == True:
            wParam = os.path.abspath(self._getExtraPath('model.h5'))
        else:
            wParam = Plugin.getVar(CRYOLO_MODEL_VAR)
        gParam = (' '.join(str(g) for g in self.getGpuList()))
        eParam = 0  # define this in the form ???
        tParam = 0.2 # define this in the form ???
        params = "-c %s " % self._getExtraPath('config.json')
        params += " -w %s -g %s" % (wParam, gParam)
        params += " -i %s/" % mics
        params += " -o %s/" % mics
        params += " -t %s" % tParam

        program2 = getProgram('cryolo_predict.py')
        label = 'predict'
        self._preparingCondaProgram(program2, params, label)
        shellName = os.environ.get('SHELL')
        self.info("**Running:** %s %s" % (program2, params))
        self.runJob('%s %s/script_%s.sh' % (shellName, self._getExtraPath(), label), '',
                    env=Plugin.getEnviron())

    def readCoordsFromMics(self, outputDir, micDoneList , outputCoords):
        "This method read coordinates from a given list of micrographs"

        # Evaluate if micDonelist is empty
        if len(micDoneList) == 0:
            return

        # Create a map micname --> micId
        micMap = {}
        for mic in micDoneList:
            key = removeBaseExt(mic.getFileName())
            micMap[key] = (mic.getObjId(), mic.getFileName())

        outputCoords.setBoxSize(self.getBoxSize())
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
        pwutils.path.moveTree(self._getTmpPath(), self._getExtraPath())
        pwutils.path.makePath(self._getTmpPath())

    def _coordinatesFileToScipion(self, coordSet, coordFile, micMap, flipOnY=False, imgHeight=None ):

        with open(coordFile, 'r') as f:
            # Configure csv reader
            reader = csv.reader(f, delimiter='\t')

            #(width, height, foo) = self.inputMicrographs.get().getDim()

            for x,y,xBox,ybox in reader:

                # Create a scipion coordinate item
                offset = round(self.getBoxSize()/2)

                # USE the flip and imageHeight!! To flip or not to flip!
                sciX = round(x) + offset
                sciY = round(y) + offset

                if flipOnY == True:
                    sciY = imgHeight - sciY
                else:
                    sciY = round(y) - offset

                coordinate = Coordinate(x=sciX, y=sciY)
                micBaseName = removeBaseExt(coordFile)
                micId, micName = micMap[micBaseName]
                coordinate.setMicId(micId)
                coordinate.setMicName(micName)
                # Add it to the set
                coordSet.append(coordinate)

    def createOutputStep(self):
        pass

    #--------------------------- INFO functions --------------------------------
    def _citations(self):
        return ['Wagner2018']

    def _warnings(self):
        warningMsgs = []

        if self.trainDataset == True:
            if self.inputCoordinates.get().getSize() < 13000:
                warningMsgs.append("The input SetOfCoordinates must be larger "
                                   "than 13000 items.")

        return warningMsgs

    def _validate(self):
        errors = []
        if self.trainDataset == False:
            if Plugin.getVar(CRYOLO_MODEL_VAR) == '':
                errors.append("If _Train dataset?_ is set to _NO_\n" 
                              "The general model for cryolo must be "
                              "download from Sphire/crYOLO website and "
                              "~/.config/scipion/scipion.conf must contain "
                              "the 'CRYOLO_MODEL' parameter pointing to "
                              "the downloaded file.")
            elif not os.path.isfile(Plugin.getVar(CRYOLO_MODEL_VAR)):
                errors.append("General model not found at '%s' and "
                              "needed in the non-training mode. "
                              "Please check the path or "
                              "the ~/.config/scipion/scipion.conf.\n"
                              "You can download the file from "
                              "the Sphire/crYOLO website."
                              % Plugin.getVar(CRYOLO_MODEL_VAR))
            if errors:
                errors.append("Even though, you can still using crYOLO "
                              "training first the network by setting "
                              "_Train dataset?_ to *YES* and providing "
                              "some already picked coordinates.")
        return errors

    #--------------------------- UTILS functions -------------------------------
    def _preparingCondaProgram(self, program, params='', label=''):
        CRYOLO_ENV_NAME = 'cryolo'
        f = open(self._getExtraPath('script_%s.sh' % label), "w")
        lines = 'pwd\n'
        lines += 'ls\n'
        lines += 'source activate %s\n' % CRYOLO_ENV_NAME
        lines += 'export CUDA_VISIBLE_DEVICES=%s\n' % (' '.join(str(g) for g in self.getGpuList()))
        lines += '%s %s\n' % (program, params)
        lines += 'source deactivate\n'
        f.write(lines)
        f.close()

    def getBoxSize(self):
        if self.bxSzFromCoor:
            return self.coordsToBxSz.get().getBoxSize()
        else:
            return self.boxSize.get()

def getProgram(program):
    """ Return the program binary that will be used. """
    cmd = join(Plugin.getHome(), 'bin', program)
    return program