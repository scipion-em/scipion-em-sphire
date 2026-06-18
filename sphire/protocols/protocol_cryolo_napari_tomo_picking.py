# **************************************************************************
# *
# * Authors: Yunior C. Fonseca Reyna    (cfonseca@cnb.csic.es)
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
from pyworkflow.constants import BETA
from pyworkflow.gui.dialog import askYesNo
from pyworkflow.utils import Message

from tomo.objects import SetOfCoordinates3D
from tomo.protocols import ProtTomoPicking
import tomo.constants as tomoConst

from ..viewers.views_tkinter_tree import SphireGenericView
import sphire.convert as convert


class SphireProtCRYOLONapariTomoPicker(ProtTomoPicking):
    """
    Picks particles or filaments in a set of tomograms using napari_boxmanager.

    AI Generated:

    crYOLO Tomogram Manual Picking (SphireProtCRYOLONapariTomoPicker) - User Manual
        Overview

        The crYOLO Tomogram Manual Picking protocol provides an interactive
        environment for selecting particles or filament coordinates directly
        within three-dimensional tomograms using the napari-boxmanager
        visualization framework. The protocol is designed for cryo-electron
        tomography workflows in which users require direct visual inspection
        and manual annotation of volumetric data.

        In biological practice, manual picking remains particularly important
        when automated detection methods are unreliable due to low contrast,
        crowded environments, unusual particle morphologies, or highly
        heterogeneous cellular contexts. Interactive annotation allows users
        to incorporate biological expertise directly into the coordinate
        selection process, improving the quality of downstream subtomogram
        analysis and reconstruction.

        Inputs and General Workflow

        The protocol requires a set of tomograms that will be opened in an
        interactive visualization session. Users inspect each tomogram and
        manually define particle or filament coordinates within the volume.
        Existing coordinate annotations may also be revisited and refined,
        allowing iterative correction and validation of previously generated
        results.

        The workflow is particularly suitable for exploratory tomography
        projects where the biological structures of interest are difficult
        to identify automatically. Because users interact directly with the
        volumetric data, the protocol supports careful contextual analysis of
        membranes, organelles, macromolecular assemblies, and filamentous
        structures inside complex cellular environments.

        Interactive Picking and Biological Interpretation

        Manual picking provides users with complete control over the
        interpretation of structural features within tomograms. This is
        especially valuable in cryo-electron tomography because biological
        samples often contain overlapping densities, incomplete particles,
        crowded intracellular regions, or variable conformational states.

        In many cases, expert visual interpretation can distinguish biologically
        meaningful structures from contamination, reconstruction artifacts, or
        noisy background regions more effectively than automated algorithms.
        Filament tracing is also easier to refine manually when filaments
        exhibit curvature, branching, discontinuities, or variable thickness.

        The protocol supports iterative annotation workflows in which users may
        repeatedly open the same tomograms, review previous coordinate sets,
        and improve annotations over time. This approach is common during the
        early stages of tomography projects where annotation standards and
        structural criteria are still being optimized.

        Coordinate Management and Output Generation

        After annotation is completed, the protocol generates a three-dimensional
        coordinate set associated with the original tomograms. These coordinates
        define the spatial locations of particles or filament positions and may
        be used directly in subtomogram extraction, averaging, classification,
        or visualization workflows.

        The protocol preserves the relationship between coordinates and their
        originating tomograms, ensuring compatibility with downstream cryo-ET
        analysis pipelines. Because the workflow is interactive, outputs reflect
        biologically informed user decisions rather than purely automated
        detection criteria.

        Practical Recommendations

        Manual picking is most effective when tomograms have been carefully
        reconstructed and filtered to maximize structural interpretability.
        Users should inspect several regions of each tomogram before beginning
        annotation in order to identify consistent structural patterns and
        avoid introducing selection bias.

        For large datasets, it is often beneficial to combine manual annotation
        with automated approaches. Manually curated coordinates can serve as
        high-quality training data for deep learning models, while automated
        picking can accelerate large-scale processing after robust annotation
        standards have been established.

        When annotating filamentous assemblies, users should pay special
        attention to continuity, curvature, and local structural variability.
        Careful visual inspection is essential to distinguish true biological
        filaments from reconstruction artifacts or overlapping densities.

        Final Perspective

        Interactive tomogram annotation remains an essential component of many
        cryo-electron tomography workflows, particularly for challenging or
        biologically complex datasets. By combining direct visualization with
        user-guided coordinate selection, this protocol enables accurate and
        biologically informed particle or filament annotation suitable for
        high-quality subtomogram analysis and structural interpretation.
    """

    _label = 'cryolo tomo picking (manual)'
    _devStatus = BETA
    _interactiveMode = True
    _possibleOutputs = {'output3DCoordinates': SetOfCoordinates3D}

    def __init__(self, **args):
        EMProtocol.__init__(self, **args)

    def _insertAllSteps(self):
        self._insertFunctionStep(self.prepareDataStep, needsGPU=False)
        self._insertFunctionStep(self.runCoordinatePickingStep,
                                 interactive=True)

    # --------------------------- STEPS functions ----------------------------
    def prepareDataStep(self):
        """
        This step prepare a folder with a link to the tomograms and create a
        folder where the .cbox files will be generated
        """
        tomoList = [tomo.clone() for tomo in self.getInputTomos()]
        convert.convertMicrographs(tomoList, self._getExtraPath())

    def runCoordinatePickingStep(self):
        """Run napari-boxmanager"""
        fileDict = {}
        tomoList = [tomo.clone() for tomo in self.getInputTomos()]
        # Finding the coordinate file per tomogram
        for tomogram in tomoList:
            filePath = self._getExtraPath(convert.getMicFn(tomogram, "cbox"))
            if not os.path.exists(filePath):
                filePath = self._getExtraPath(convert.getMicFn(tomogram, "coords"))

            if os.path.exists(filePath):
                creationOldTime = time.ctime(os.path.getctime(filePath))
                fileDict[filePath] = creationOldTime

        view = SphireGenericView(None, tomoList,
                                 self._getExtraPath(), isInteractive=True)
        view.show()

        for tomogram in tomoList:
            filePath = self._getExtraPath(convert.getMicFn(tomogram,  "cbox"))
            if not os.path.exists(filePath):
                filePath = self._getExtraPath(convert.getMicFn(tomogram, "coords"))

            if filePath in fileDict:
                modificationTime = time.ctime(os.path.getctime(filePath))
                if fileDict[filePath] != modificationTime:
                    # Open dialog to request confirmation to create output
                    import tkinter as tk
                    if askYesNo(Message.TITLE_SAVE_OUTPUT, Message.LABEL_SAVE_OUTPUT, tk.Frame()):
                        self.createOutput()
                        break
            elif os.path.exists(filePath):
                self.createOutput()
                break

    def createOutput(self):
        setOfTomograms = self.getInputTomos()
        suffix = self._getOutputSuffix(SetOfCoordinates3D)

        setOfCoord3D = self._createSetOfCoordinates3D(self.getInputTomos(pointer=True),
                                                      suffix)
        setOfCoord3D.setName("tomoCoord")
        setOfCoord3D.setSamplingRate(setOfTomograms.getSamplingRate())

        for tomogram in setOfTomograms.iterItems():
            filePath = self._getExtraPath(convert.getMicFn(tomogram, "cbox"))
            if not os.path.exists(filePath):
                filePath = self._getExtraPath(convert.getMicFn(tomogram, "coords"))

            if os.path.exists(filePath) and os.path.getsize(filePath):
                tomogramClone = tomogram.clone()
                tomogramClone.copyInfo(tomogram)
                convert.readSetOfCoordinates3D(tomogramClone, setOfCoord3D,
                                               filePath, boxSize=None,
                                               origin=tomoConst.BOTTOM_LEFT_CORNER)

        name = self.OUTPUT_PREFIX + suffix
        self._defineOutputs(**{name: setOfCoord3D})
        self._defineSourceRelation(setOfTomograms, setOfCoord3D)

    # -------------------------- UTILS functions ------------------------------
    def getInputTomos(self, pointer=False):
        if pointer:
            return self.inputTomograms
        else:
            return self.inputTomograms.get()
