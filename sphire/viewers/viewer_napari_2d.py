# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk)
# *
# * MRC Laboratory of Molecular Biology (MRC-LMB)
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
import os.path
import threading

from pyworkflow.gui.dialog import askYesNo
from pyworkflow.utils.properties import Message
import pyworkflow.viewer as pwviewer
import pyworkflow.utils as pwutils

from sphire.protocols import SphireProtCRYOLOPicking
import sphire.convert


class NapariViewer2D(pwviewer.Viewer):
    """ Wrapper to visualize 2D coordinates using napari boxmanager
    """
    _environments = [pwviewer.DESKTOP_TKINTER]
    _targets = [SphireProtCRYOLOPicking]

    def _visualize(self, obj, **kwargs):
        prot = self.protocol
        micSet = prot.getInputMicrographs()
        micsList = [mic.clone() for mic in micSet]

        tmpDir = self._getTmpPath(micSet.getName())
        pwutils.cleanPath(tmpDir)
        pwutils.makePath(tmpDir)

        sphire.convert.convertMicrographs(micsList, tmpDir)
        cbox_path = prot._getExtraPath()

        proc = threading.Thread(target=self.runNapariBoxmanager,
                                args=(tmpDir, cbox_path,))
        proc.start()
        proc.join()  # FIXME: this blocks main GUI

        import tkinter as tk
        frame = tk.Frame()
        if askYesNo(Message.TITLE_SAVE_OUTPUT, "Save modified output?", frame):
            from pwem.objects import Set
            outputName = prot.getNextOutputName('outputCoordinates_')
            suffix = prot.getOutputSuffix("outputCoordinates")
            micSetPtr = prot.getInputMicrographsPointer()
            outputCoords = prot._createSetOfCoordinates(micSetPtr, suffix)
            outputCoords.setName("Selected Coordinates")
            prot.readCoordsFromMics(cbox_path, micsList, outputCoords)
            prot._updateOutputSet(outputName, outputCoords, Set.STREAM_CLOSED)
            prot._defineSourceRelation(micSetPtr, outputCoords)

        return []

    @staticmethod
    def runNapariBoxmanager(mics_path, cbox_path):
        """ Assemble cmd line to launch napari. """
        from sphire import Plugin, NAPARI_BOXMANAGER
        mics_path = os.path.relpath(mics_path, cbox_path)
        args = f"'{mics_path}/*.mrc' '*.cbox'"
        Plugin.runNapariBoxManager(cbox_path, NAPARI_BOXMANAGER, args)
