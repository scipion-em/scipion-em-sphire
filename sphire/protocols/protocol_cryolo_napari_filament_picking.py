# **************************************************************************
# *
# * Authors: Yunior C. Fonseca Reyna    (cfonseca@cnb.csic.es)
# *
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
import os
import time

from pwem.protocols import EMProtocol

from pyworkflow import BETA
from pyworkflow.gui import askYesNo
from pyworkflow.protocol import PointerParam
from pyworkflow.utils import createAbsLink, Message

from tomo.objects import SetOfCoordinates3D
from tomo.protocols import ProtTomoPicking
import tomo.constants as tomoConst

from sphire.protocols.protocol_base import ProtCryoloBase
from sphire.viewers.views_tkinter_tree import SphireGenericView
import sphire.convert as convert


class SphireProtCRYOLOFilamentPicker(ProtCryoloBase, ProtTomoPicking):
    """
    Picks filaments and particles in a set of tomograms using napari_boxmanager.
    """

    _label = 'cryolo tomo picking(manual)'
    _devStatus = BETA
    _interactiveMode = True
    _possibleOutputs = {'output3DCoordinates': SetOfCoordinates3D}

    def __init__(self, **args):
        EMProtocol.__init__(self, **args)

    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('inputSetOfTomograms', PointerParam,
                      pointerClass='SetOfTomograms',
                      label="Set of Tomograms", important=True,
                      help='Select the Tomograms to be used during '
                           'picking.')

    def _insertAllSteps(self):
        self.inputTiltSeries = None
        self._insertFunctionStep(self.prepareDataStep)
        self._insertFunctionStep(self.runCoordinatePickingStep,
                                 interactive=True)

    # --------------------------- STEPS functions ----------------------------
    def prepareDataStep(self):
        """
        This step prepare a folder with a link to the tomograms and create a
        folder where the .cbox files will be generated
        """
        for tomogram in self.inputSetOfTomograms.get():
            tomoFn = tomogram.getFileName()
            source = os.path.abspath(tomoFn)
            dest = os.path.abspath(self._getExtraPath(os.path.basename(tomoFn)))
            createAbsLink(source, dest)

    def runCoordinatePickingStep(self):
        # Getting the first tomogram to check if the .cbox file exist
        tomogram = self.inputSetOfTomograms.get().getFirstItem()
        filePath = os.path.join(self._getExtraPath(),
                                convert.getMicFn(tomogram, "cbox"))
        creationOldTime = None
        if os.path.exists(filePath):
            creationOldTime = time.ctime(os.path.getctime(filePath))

        view = SphireGenericView(None, self, self.inputSetOfTomograms.get(),
                                   isInteractive=True,
                                   itemDoubleClick=True)
        view.show()

        if os.path.exists(filePath):
            if creationOldTime is not None:
                modificationTime = time.ctime(os.path.getctime(filePath))
                if creationOldTime != modificationTime:
                    # Open dialog to request confirmation to create output
                    import tkinter as tk
                    if askYesNo(Message.TITLE_SAVE_OUTPUT, Message.LABEL_SAVE_OUTPUT,  tk.Frame()):
                        self.createOutput()
            else:
                self.createOutput()

    def createOutput(self):
        setOfTomograms = self.inputSetOfTomograms.get()
        outputPath = self._getExtraPath()
        suffix = self._getOutputSuffix(SetOfCoordinates3D)

        setOfCoord3D = self._createSetOfCoordinates3D(self.inputSetOfTomograms,
                                                      suffix)
        setOfCoord3D.setName("tomoCoord")
        setOfCoord3D.setSamplingRate(setOfTomograms.getSamplingRate())

        for tomogram in setOfTomograms.iterItems():

            filePath = os.path.join(outputPath,
                                    convert.getMicFn(tomogram, "cbox"))
            if os.path.exists(filePath):
                tomogramClone = tomogram.clone()
                tomogramClone.copyInfo(tomogram)
                convert.readSetOfCoordinates3D(tomogramClone, setOfCoord3D,
                                               filePath,
                                               None,
                                               origin=tomoConst.BOTTOM_LEFT_CORNER)


        name = self.OUTPUT_PREFIX + suffix
        self._defineOutputs(**{name: setOfCoord3D})
        self._defineSourceRelation(setOfTomograms, setOfCoord3D)

    def _validate(self):
        return []

    def _warnings(self):
        warnings = []
        return warnings

    def _summary(self):
        summary = []
        return summary