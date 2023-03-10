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
        self._file = open(filename, 'w')

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
        self._halfBox = boxSize / 2.0
        self._yFlipHeight = yFlipHeight
        self._boxSizeEstimated = boxSizeEstimated

    def iterCoords(self, filename):
        for row in Table.iterRows(filename, tableName='cryolo'):
            x = row.CoordinateX
            y = row.CoordinateY
            z = row.get("CoordinateZ", 0.0)
            score = row.get("Confidence", 0.0)

            if not self._boxSizeEstimated:
                x += self._halfBox
                y += self._halfBox

            sciX = round(x)
            sciY = round(y)
            sciZ = round(z) if not isinstance(z, str) else 0  # avoid <NA> values

            if self._yFlipHeight is not None:
                sciY = self._yFlipHeight - sciY

            yield sciX, sciY, sciZ, score


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

    for x, y, z, _ in reader.iterCoords(coordsFile):
        # Clean up objId to add as a new coordinate
        coord.setObjId(None)
        coord.setVolume(tomogram)
        coord.setPosition(x, y, z, origin)
        coord3DSet.append(coord)


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


def getMicFn(mic, ext='mrc'):
    """ Return a name for the micrograph based on its filename. """
    return pwutils.replaceBaseExt(mic.getFileName(), ext)


def roundInputSize(inputSize):
    """ Returns the closest value to inputSize th is multiple of 32"""
    rounded = int(32 * round(float(inputSize) / 32))

    if rounded != inputSize:
        print("Input size (%s) will be rounded to %s, the closest "
              "multiple of 32." % (inputSize, rounded))
    return rounded
