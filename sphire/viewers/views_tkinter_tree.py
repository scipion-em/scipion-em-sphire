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
from pyworkflow.gui.tree import TreeProvider
from pyworkflow.gui.dialog import ListDialog
import pyworkflow.viewer as pwviewer
from pyworkflow.plugin import Domain
from pyworkflow.utils import replaceBaseExt, getExt

import tomo.objects

from sphire.constants import CRYOLO_SUPPORTED_FORMATS


class SphireGenericTreeProvider(TreeProvider):
    """ Model class that will retrieve the information from Tomogram and
        prepare the columns/rows models required by the TreeDialog GUI.
    """
    COL_TOMOGRAM = 'Tomograms'
    COL_INFO = 'Info'
    COL_STATUS = 'Status'
    COL_COOR3D = 'Coordinates 3D'

    ORDER_DICT = {COL_TOMOGRAM: 'id'}

    def __init__(self, protocol, objs, isInteractive=False, tmpDir=None):
        self.title = 'Sphire set viewer'
        if isinstance(objs, tomo.objects.SetOfTomograms):
            self.COL_TOMOGRAM = 'Tomograms'
            self.title = 'Tomograms display'

        self.protocol = protocol
        self.objs = objs
        self.isInteractive = isInteractive
        TreeProvider.__init__(self, sortingColumnName=self.COL_TOMOGRAM)
        self.selectedDict = {}
        self.mapper = protocol.mapper
        self.maxNum = 200
        self.tmpDir = tmpDir

    def getObjects(self):
        # Retrieve all objects of type className
        objects = []

        orderBy = self.ORDER_DICT.get(self.getSortingColumnName(), 'id')
        direction = 'ASC' if self.isSortingAscending() else 'DESC'

        for obj in self.objs.iterItems(orderBy=orderBy, direction=direction):
            item = obj.clone()
            item._allowsSelection = True
            item._parentObject = None
            objects.append(item)

        return objects

    def _sortObjects(self, objects):
        pass

    def objectKey(self, pobj):
        pass

    def getColumns(self):
        cols = [
            (self.COL_TOMOGRAM, 200),
            (self.COL_INFO, 400),
            (self.COL_COOR3D, 110),
            (self.COL_STATUS, 80)]
        return cols

    def isSelected(self, obj):
        """ Check if an object is selected or not. """
        return False

    @staticmethod
    def _getParentObject(pobj, default=None):
        return getattr(pobj, '_parentObject', default)

    def getObjectInfo(self, obj):
        itemId = obj.getTsId()
        if itemId is None:
            itemId = str(obj.getObjId())

        key = obj.getObjId()
        text = itemId
        values = [str(obj)]
        tags = ''
        if self.isInteractive:
            status = self.getObjStatus(obj, values)
            tags = (status,)

        opened = True

        item = {
            'key': key, 'text': text,
            'values': tuple(values),
            'open': opened,
            'selected': False,
            'parent': obj._parentObject,
            'tags': tags
        }
        return item

    def getSphirePickerColumnValues(self, obj, values):
        status = 'pending'
        for item in self.objs:
            if item.getTsId() == obj.getTsId():
                # .cbox file
                coordinatesFilePath = self.getCboxFile(item)
                if os.path.exists(coordinatesFilePath):
                    coordTable = emtable.Table(fileName=coordinatesFilePath,
                                               tableName='cryolo')

                    values.append(str(len(coordTable)))
                    values.append('Done')
                    status = 'done'
                else:
                    values.append('No')
                    values.append('Pending')
        return status

    def getObjStatus(self, obj, values):
        status = self.getSphirePickerColumnValues(obj, values)
        return status

    def getCboxFile(self, item):
        cboxFileName = item.getTsId() + '.cbox'
        coordinatesFilePath = os.path.join(self.tmpDir, cboxFileName)

        return coordinatesFilePath

    def getObjectActions(self, obj):
        actions = []
        if not self.isInteractive:
            viewers = Domain.findViewers(obj.getClassName(),
                                         pwviewer.DESKTOP_TKINTER)
            for viewerClass in viewers:
                def createViewer(viewerClass, obj):
                    item = self.objs[obj.getObjId()]  # to load mapper
                    proj = self.protocol.getProject()
                    return lambda: viewerClass(project=proj, protocol=self.protocol).visualize(item)

                actions.append(('Open with %s' % viewerClass.__name__,
                                createViewer(viewerClass, obj)))
        return actions

    def configureTags(self, tree):
        tree.tag_configure("pending", foreground="red")
        tree.tag_configure("done", foreground="green")


class SphireListDialog(ListDialog):
    def __init__(self, parent, title, provider, createSetButton=False,
                 itemDoubleClick=False, tmpDir=None, **kwargs):
        self.createSetButton = createSetButton
        self._itemDoubleClick = itemDoubleClick
        self.provider = provider
        self.tmpDir = tmpDir
        ListDialog.__init__(self, parent, title, provider, message=None,
                            allowSelect=False, cancelButton=True, **kwargs)

    def body(self, bodyFrame):
        bodyFrame.config()
        gui.configureWeigths(bodyFrame)
        dialogFrame = tk.Frame(bodyFrame)
        dialogFrame.grid(row=0, column=0, sticky='news', padx=5, pady=5)
        dialogFrame.config()
        gui.configureWeigths(dialogFrame, row=1)
        self._createFilterBox(dialogFrame)
        self._col = 0
        self._createTree(dialogFrame)
        self.initial_focus = self.tree
        if self._itemDoubleClick:
            self.tree.itemDoubleClick = self.doubleClickOnItem

    def doubleClickOnItem(self, e=None):
        ts = e
        self.proc = threading.Thread(target=self.napariPicker,
                                     args=(ts,))
        self.proc.start()
        self.after(1000, self.refresh_gui)

    def napariPicker(self, obj):
        for item in self.provider.objs:
            if item.getTsId() == obj.getTsId():
                self.runNapariBoxmanager(item)
                break

    def runNapariBoxmanager(self, tomogram):
        from sphire import Plugin, NAPARI_BOXMANAGER
        ext = getExt(tomogram.getFileName())

        if ext in CRYOLO_SUPPORTED_FORMATS:
            tomogramPath = tomogram.getFileName()
        else:
            tomogramPath = replaceBaseExt(tomogram.getFileName(), "mrc")

        if os.path.exists(os.path.join(self.tmpDir, tomogramPath)):
            args = tomogramPath
            coordinatesPath = replaceBaseExt(tomogram.getFileName(), 'cbox')

            if os.path.exists(os.path.join(self.tmpDir, coordinatesPath)):
                args += f" {coordinatesPath}"

            Plugin.runNapariBoxManager(self.tmpDir, NAPARI_BOXMANAGER, args)

    def refresh_gui(self):
        self.tree.update()
        if self.proc.is_alive():
            self.after(1000, self.refresh_gui)


class SphireGenericView(pwviewer.View):
    """ This class implements a view using Tkinter ListDialog
    and the SphireTreeProvider.
    """

    def __init__(self, parent, protocol, objs, isInteractive=False,
                 itemDoubleClick=False, tmpDir=None, **kwargs):
        self._tkParent = parent
        self._protocol = protocol
        self._provider = SphireGenericTreeProvider(protocol, objs, isInteractive, tmpDir)
        self.title = self._provider.title
        self.itemDoubleClick = itemDoubleClick
        self.tmpDir = tmpDir

    def show(self):
        SphireListDialog(self._tkParent, self.title, self._provider,
                         itemDoubleClick=self.itemDoubleClick, tmpDir=self.tmpDir)
