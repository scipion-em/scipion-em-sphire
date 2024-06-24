# **************************************************************************
# *
# * Authors: Yunior C. Fonseca Reyna (cfonseca@cnb.csic.es)
# *
# * Unidad de Bioinformatica of Centro Nacional de Biotecnologia, CSIC
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

import pyworkflow.protocol.params as params
import pyworkflow.utils as pwutils

from . import SphireProtCRYOLOTraining
import sphire.convert as convert


class SphireProtCRYOLOTomoTraining(SphireProtCRYOLOTraining):
    """ Train crYOLO picker using a set of 3D coordinates. """
    _label = 'cryolo tomo training'
    MODEL = 'model.h5'
    TRAIN = ['train_annotations', 'train_images']
    _IS_TRAIN = True

    # -------------------------- DEFINE param functions -----------------------
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('inputTomograms', params.PointerParam,
                      pointerClass='SetOfTomograms',
                      label='Input tomograms', important=True,
                      help='Select the SetOfTomograms to be used during '
                           'picking.')
        form.addParam('inputCoordinates3D', params.PointerParam,
                      pointerClass='SetOfCoordinates3D',
                      label='Input coordinates 3D', important=True,
                      help="Please select a set of coordinates 3D, obtained "
                           "from a previous picking run.")

        SphireProtCRYOLOTraining._defineTrainParams(self, form)

    # --------------------------- STEPS functions -----------------------------
    def convertInputStep(self):
        """ Converts a set of coordinates to cbox files and binaries to mrc.
        It generates 2 folders: one for the cbox files and another for
        the mrc files.
        """
        inputTomos = self.getInputMicrographs()
        coordSet = self.inputCoordinates3D.get()

        paths = []
        for d in self.TRAIN:
            paths.append(self._getExtraPath(d))
            pwutils.makePath(paths[-1])

        tomoList = [tomo.clone() for tomo in inputTomos]
        convert.writeSetOfCoordinates3D(paths[0], coordSet, tomoList)
        convert.convertTomograms(tomoList, paths[1])

    # -------------------------- UTILS functions ------------------------------
    def getInputMicrographs(self):
        """ Redefine from the base class. """
        return self.inputTomograms.get()
