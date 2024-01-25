# *****************************************************************************
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
# *****************************************************************************
import os.path
import threading

import emtable
from pyworkflow.gui import *
from pyworkflow.gui.dialog import ToolbarListDialog
import pyworkflow.viewer as pwviewer
import pyworkflow.utils as pwutils

from tomo.viewers.views_tkinter_tree import TomogramsTreeProvider

from sphire.constants import CRYOLO_SUPPORTED_FORMATS


class SphireTomogramProvider(TomogramsTreeProvider):
    def __init__(self, tomoList, path, mode=None, isInteractive=False):
        super().__init__(tomoList, path, mode)
        self.isInteractive = isInteractive

    def getObjectInfo(self, tomo):
        key = tomo.getObjId()
        itemId = tomo.getTsId()
        if itemId is None:
            itemId = str(key)

        values, tags = self.getObjStatus(tomo)

        item = {
            'key': key, 'text': itemId,
            'values': tuple(values),
            'parent': None,
            'tags': tuple(tags)
        }
        return item

    def getObjStatus(self, tomo):
        values = []
        tags = 'pending' if self.isInteractive else 'done'
        for item in self.tomoList:
            if item.getTsId() == tomo.getTsId():
                coordinatesFilePath = self.getCoordinatesFile(item, ext='cbox')
                if not os.path.exists(coordinatesFilePath):
                    coordinatesFilePath = self.getCoordinatesFile(item, ext='coords')
                if os.path.exists(coordinatesFilePath):
                    coordTable = self.getCoordsCount(coordinatesFilePath)
                    values.append(str(coordTable))
                    values.append('Done')
                else:
                    values.append('0')
                    values.append('Pending')
        return values, tags

    def getCoordsCount(self, coordFilePath: str) -> int:
        """Method to get the number of coordinates from a coordinates file"""
        coordCount = 0
        ext = pwutils.getExt(coordFilePath)
        # Check the extension and count the corresponding coordinates
        if ext == '.coords':
            with open(coordFilePath, 'r') as file:
                lines = file.readlines()
                coordCount = len(lines)
        elif ext == '.cbox':
            # Use the emtable class to count coordinates in .cbox files
            coordTable = emtable.Table(fileName=coordFilePath, tableName='cryolo')
            coordCount = len(coordTable)

        return coordCount

    def getCoordinatesFile(self, item, ext='cbox'):
        cboxFileName = pwutils.replaceBaseExt(item.getFileName(), ext)
        coordinatesFilePath = os.path.join(self._path, cboxFileName)

        return coordinatesFilePath


class SphireListDialog(ToolbarListDialog):
    def __init__(self, parent, provider, path, **kwargs):
        self.provider = provider
        self.path = path
        ToolbarListDialog.__init__(self, parent,
                                   "Tomogram List", provider,
                                   allowsEmptySelection=False,
                                   itemDoubleClick=self.doubleClickOnItem,
                                   allowSelect=False,
                                   lockGui=False,
                                   cancelButton=True,
                                   **kwargs)

    def doubleClickOnItem(self, e=None):
        ts = e
        self.proc = threading.Thread(target=self.runNapariBoxmanager,
                                     args=(ts,))
        self.proc.start()
        self.after(1000, self.refresh_gui)

    def runNapariBoxmanager(self, tomogram):
        from sphire import Plugin, NAPARI_BOXMANAGER
        from sphire.convert import getMicFn
        ext = pwutils.getExt(tomogram.getFileName())

        if ext in CRYOLO_SUPPORTED_FORMATS:
            tomogramPath = os.path.basename(tomogram.getFileName())
        else:
            tomogramPath = getMicFn(tomogram, "mrc")

        if os.path.exists(os.path.join(self.path, tomogramPath)):
            args = tomogramPath
            coordinatesPath = getMicFn(tomogram, 'cbox')

            if not os.path.exists(os.path.join(self.path, coordinatesPath)):
                coordinatesPath = getMicFn(tomogram, 'coords')

            if os.path.exists(os.path.join(self.path, coordinatesPath)):
                args += f" {coordinatesPath}"

            Plugin.runNapariBoxManager(self.path, NAPARI_BOXMANAGER, args)

    def refresh_gui(self):
        self.tree.update()
        if self.proc.is_alive():
            self.after(1000, self.refresh_gui)


class SphireGenericView(pwviewer.View):
    """ This class implements a view using Tkinter ToolbarListDialog
    and the SphireTomogramProvider.
    """

    def __init__(self, parent, tomoList, path, isInteractive=False):
        self._tkParent = parent
        self._provider = SphireTomogramProvider(tomoList, path,
                                                isInteractive=isInteractive)
        self._path = path

    def show(self):
        SphireListDialog(self._tkParent, self._provider, self._path)
