# **************************************************************************
# *
# * Authors: Peter Horvath (phorvath@cnb.csic.es) [1]
# *          Pablo Conesa (pconesa@cnb.csic.es) [1]
# *
# * [1] I2PC center
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
from emtable import Table

import pyworkflow.utils as pwutils
from pwem.emlib.image import ImageHandler
from pwem.convert import Ccp4Header

import sphire.constants as constants
from tomo.constants import BOTTOM_LEFT_CORNER

with pwutils.weakImport('tomo'):
    from tomo.objects import Coordinate3D


class CoordBoxWriter:
    """ Helper class to write a .BOX file for cryolo. """
    def __init__(self, boxSize, yFlipHeight=None):
        """
        :param boxSize: The box size of the coordinates that will be written
        :param yFlipHeight: if not None, the y coordinates will be flipped
        """
        self._file = None
        self._boxSize = boxSize
        self._halfBox = int(boxSize / 2)
        self._yFlipHeight = yFlipHeight

    def open(self, filename):
        """ Open a new filename to write, close previous one if open. """
        self.close()
        self._file = open(filename, 'a+')

    def writeCoord(self, coord):
        box = self._boxSize
        half = self._halfBox
        x = coord.getX() - half
        if self._yFlipHeight is None:
            y = coord.getY() - half
        else:
            y = self._yFlipHeight - coord.getY() - half
        score = getattr(coord, '_cryoloScore', 0.0)
        self._file.write("%s\t%s\t%s\t%s\t%s\n" % (x, y, box, box, score))

    def writeCoordinate3DHeader(self):
        HEADER = """
data_cryolo

loop_
_CoordinateX #1
_CoordinateY #2
_CoordinateZ #3
_Width #4
_Height #5
_Depth #6
_filamentid #7
_Confidence #8
_EstWidth #9
_EstHeight #10
_NumBoxes #11
"""
        self._file.write(HEADER)

    def writeCoord3D(self, coord3d):
        box = self._boxSize
        half = self._halfBox
        x = coord3d.getX(BOTTOM_LEFT_CORNER) - half
        if self._yFlipHeight is None:
            y = coord3d.getY(BOTTOM_LEFT_CORNER) - half
        else:
            y = self._yFlipHeight - coord3d.getY(BOTTOM_LEFT_CORNER) - half
        z = coord3d.getZ(BOTTOM_LEFT_CORNER)
        groupId = coord3d.getGroupId()
        self._file.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n"
                         % (x, y, z, box, box, box, groupId, box, box, box, 10))

    def writeIncludeBlock(self, zCoordinates):
        INCLUDE_BLOCK = """
data_cryolo_include

loop_
_slice_index #1
"""
        self._file.write(INCLUDE_BLOCK)
        for zCoordinate in zCoordinates:
            self._file.write("%s\n" % zCoordinate)

    def close(self):
        if self._file:
            self._file.close()


class CoordBoxReader:
    """ Helper class to read coordinates from .CBOX files. """
    def __init__(self, boxSize, yFlipHeight=None, boxSizeEstimated=False):
        """
        :param boxSize: The box size of the coordinates that will be read
        :param yFlipHeight: if not None, the y coordinates will be flipped
        """
        self._file = None
        self._boxSize = boxSize
        self._halfBox = boxSize / 2.0 if self._boxSize is not None else None
        self._yFlipHeight = yFlipHeight
        self._boxSizeEstimated = boxSizeEstimated

    def iterCoords(self, filename):
        for row in Table.iterRows(filename, tableName='cryolo'):
            x = row.CoordinateX
            y = row.CoordinateY
            z = row.get("CoordinateZ", 0.0)
            score = row.get("Confidence", 0.0)
            groupId = int(row.get('filamentid', 0))
            width = int(row.get('Width', 0))

            if self._boxSize is None:
                self._boxSize = width
                self._halfBox = self._boxSize / 2.0

            if not self._boxSizeEstimated:
                x += self._halfBox
                y += self._halfBox

            sciX = round(x)
            sciY = round(y)
            sciZ = round(z) if not isinstance(z, str) else 0  # avoid <NA> values

            if self._yFlipHeight is not None:
                sciY = self._yFlipHeight - sciY

            yield sciX, sciY, sciZ, score, groupId, width


def writeSetOfCoordinates(boxDir, coordSet, micList=None):
    """ Convert a SetOfCoordinates to Cryolo box files.
    Params:
        boxDir: the output directory where to generate the files.
        coordSet: the input SetOfCoordinates that will be converted.
        micList: if not None, only coordinates from this micrographs
            will be written.
    """
    # Get the SOM (SetOfMicrographs)
    micSet = coordSet.getMicrographs()
    micIdSet = micSet.getIdSet() if micList is None else set(m.getObjId()
                                                             for m in micList)

    # Get first mic from mics
    mic = micSet.getFirstItem()
    # Get fileName from mic
    writer = CoordBoxWriter(coordSet.getBoxSize(),
                            getFlipYHeight(mic.getFileName()))
    lastMicId = None
    doWrite = True

    # Loop through coordinates and generate box files
    for coord in coordSet.iterItems(orderBy='_micId'):
        micId = coord.getMicId()
        mic = micSet[micId]

        if micId != lastMicId:
            doWrite = micId in micIdSet
            if doWrite:
                writer.open(os.path.join(boxDir, getMicFn(mic, "box")))
            lastMicId = micId

        if doWrite:
            writer.writeCoord(coord)

    writer.close()


def readSetOfCoordinates3D(tomogram, coord3DSet, coordsFile, boxSize,
                           origin=None):
    reader = CoordBoxReader(boxSize)
    coord3DSet.enableAppend()

    coord = Coordinate3D()

    for x, y, z, score, groupId, width in reader.iterCoords(coordsFile):
        # Clean up objId to add as a new coordinate
        coord.setObjId(None)
        coord.setVolume(tomogram)
        coord.setPosition(x, y, z, origin)
        coord.setGroupId(groupId)
        coord.setBoxSize(width)
        coord3DSet.append(coord)


def writeSetOfCoordinates3D(boxDir, coord3DSet, tomoList=None):
    """ Convert a SetOfCoordinates to Cryolo box files.
    Params:
        boxDir: the output directory where to generate the files.
        coordSet: the input SetOfCoordinates that will be converted.
        micList: if not None, only coordinates from this micrographs
            will be written.
    """
    tomoSet = coord3DSet.getPrecedents()
    tomoIdSet = tomoSet.getIdSet() if tomoList is None else set(m.getObjId()
                                                                for m in tomoList)

    # Get first tomo from to
    tomo = tomoSet.getFirstItem()
    # Get fileName from tomo
    writer = CoordBoxWriter(coord3DSet.getBoxSize(),
                            getFlipYHeight(tomo.getFileName()))
    lastTomoId = None
    doWrite = True
    zCoorList = []
    for coord in coord3DSet.iterCoordinates():
        tomoId = coord.getVolume().getObjId()
        tomo = tomoSet[tomoId]

        if tomoId != lastTomoId:
            if lastTomoId is not None:
                writer.writeIncludeBlock(zCoorList)
            doWrite = tomoId in tomoIdSet
            if doWrite:
                zCoorList = []
                writer.open(os.path.join(boxDir, getTomoFn(tomo, "cbox")))
                writer.writeCoordinate3DHeader()
            lastTomoId = tomoId

        if doWrite:
            writer.writeCoord3D(coord)
            zValue = coord.getZ(BOTTOM_LEFT_CORNER)
            if zValue not in zCoorList:
                zCoorList.append(zValue)

    writer.writeIncludeBlock(zCoorList)

    writer.close()


def needToFlipOnY(filename):
    """ Returns true if we need to flip coordinates on Y"""
    ext = pwutils.getExt(filename)

    if ext in ".mrc":
        header = Ccp4Header(filename, readHeader=True)
        return header.getISPG() != 0  # ISPG 1, cryolo will not flip the image

    return ext in constants.CRYOLO_SUPPORTED_FORMATS


def getFlipYHeight(filename):
    """ Return y-Height if flipping is needed, None otherwise """
    x, y, z, n = ImageHandler().getDimensions(filename)
    return y if needToFlipOnY(filename) else None


def convertMicrographs(micList, micDir):
    """ Convert (or simply link) input micrographs into the given directory
    in a format that is compatible with crYOLO.
    """
    ih = ImageHandler()
    ext = pwutils.getExt(micList[0].getFileName())

    def _convert(mic, newName):
        ih.convert(mic, os.path.join(micDir, newName))

    def _link(mic, newName):
        pwutils.createAbsLink(os.path.abspath(mic.getFileName()),
                              os.path.join(micDir, newName))

    if ext in constants.CRYOLO_SUPPORTED_FORMATS:
        func = _link
    else:
        func = _convert
        ext = '.mrc'

    for mic in micList:
        func(mic, getMicFn(mic, ext.lstrip(".")))


def convertTomograms(tomoList, tomoDir):
    """ Convert (or simply link) input tomograms into the given directory
       in a format that is compatible with crYOLO.
       """
    convertMicrographs(tomoList, tomoDir)


def getMicFn(mic, ext='mrc'):
    """ Return a name for the micrograph based on its filename. """
    return pwutils.replaceBaseExt(mic.getFileName(), ext)


def getTomoFn(tomo, ext='mrc'):
    """ Return a name for the micrograph based on its filename. """
    return pwutils.replaceBaseExt(tomo.getFileName(), ext)


def roundInputSize(inputSize):
    """ Returns the closest value to inputSize th is multiple of 32"""
    rounded = int(32 * round(float(inputSize) / 32))

    if rounded != inputSize:
        print("Input size (%s) will be rounded to %s, the closest "
              "multiple of 32." % (inputSize, rounded))
    return rounded
