# **************************************************************************
# *
# * Authors: Peter Horvath [1]
# *          Pablo Conesa [1]
# *
# * [1] I2PC center
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
import csv
import re

import pyworkflow.object as pwobj
import pyworkflow.utils as pwutils
import pwem.objects as emobj
from pwem.emlib.image import ImageHandler
from pwem.convert import Ccp4Header

import sphire.constants as constants


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
    """ Helper class to read coordinates from .BOX files. """
    def __init__(self, boxSize, yFlipHeight=None, boxSizeEstimated=False):
        """
        :param boxSize: The box size of the coordinates that will be read
        :param yFlipHeight: if not None, the y coordinates will be flipped
        """
        self._file = None
        self._boxSize = boxSize
        self._halfBox = boxSize / 2.0
        self._yFlipHeight = yFlipHeight
        self._boxSizeEstimated = boxSizeEstimated

    def open(self, filename):
        """ Open a new filename to write, close previous one if open. """
        self.close()
        self._file = open(filename, 'r')

    def _getDataLength(self):
        head = next(self._file)  # Read the first line
        cols = re.split(r'\t+', head.rstrip('\t'))  # Strip it by tab
        self._file.seek(0)  # Return to the top of the file
        return len(cols)

    def iterCoords(self):
        reader = csv.reader(self._file, delimiter='\t')

        if self._getDataLength() == 7:  # crYOLO generates .cbox files with 7 columns from version > 1.5.4
            if self._boxSizeEstimated:
                for x, y, _, _, score, _, _ in reader:
                    # USE the imageHeight to flip or not to flip!
                    sciX = round(float(x))
                    sciY = round(float(y))

                    if self._yFlipHeight is not None:
                        sciY = self._yFlipHeight - sciY

                    yield sciX, sciY, float(score)
            else:
                for x, y, _, _, score, _, _ in reader:
                    # USE the imageHeight to flip or not to flip!
                    sciX = round(float(x) + self._halfBox)
                    sciY = round(float(y) + self._halfBox)

                    if self._yFlipHeight is not None:
                        sciY = self._yFlipHeight - sciY

                    yield sciX, sciY, float(score)
        else:   # crYOLO generates .cbox files with 7 columns from version <= 1.5.4
            for x, y, _, _, score in reader:
                # USE the imageHeight to flip or not to flip!
                sciX = round(float(x) + self._halfBox)
                sciY = round(float(y) + self._halfBox)

                if self._yFlipHeight is not None:
                    sciY = self._yFlipHeight - sciY

                yield sciX, sciY, float(score)

    def close(self):
        if self._file:
            self._file.close()


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
                # we need to close previous opened file
                writer.open(os.path.join(boxDir, getMicIdName(mic, '.box')))
            lastMicId = micId

        if doWrite:
            writer.writeCoord(coord)

    writer.close()


def readMicrographCoords(mic, coordSet, coordsFile, boxSize, yFlipHeight=None, boxSizeEstimated=False):
    reader = CoordBoxReader(boxSize, yFlipHeight=yFlipHeight, boxSizeEstimated=boxSizeEstimated)
    reader.open(coordsFile)

    coord = emobj.Coordinate()

    for x, y, score in reader.iterCoords():
        # Clean up objId to add as a new coordinate
        coord.setObjId(None)
        coord.setPosition(x, y)
        coord.setMicrograph(mic)
        coord._cryoloScore = emobj.Float(score)
        # Add it to the set
        coordSet.append(coord)

    reader.close()


def needToFlipOnY(filename):
    """ Returns true if need to flip coordinates on Y"""
    ext = getExt(filename)

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
        createAbsLink(os.path.abspath(mic.getFileName()),
                              os.path.join(micDir, newName))

    if ext in constants.CRYOLO_SUPPORTED_FORMATS:
        func = _link
    else:
        func = _convert
        ext = '.mrc'

    for mic in micList:
        func(mic, getMicIdName(mic, suffix=ext))


def getMicIdName(mic, suffix=''):
    """ Return a name for the micrograph based on its IDs. """
    return 'mic%05d%s' % (mic.getObjId(), suffix)


def roundInputSize(inputSize):
    """ Returns the closest value to inputSize th is multiple of 32"""
    rounded = roundTo(inputSize, 32)

    if rounded != inputSize:
        print("Input size (%s) will be rounded to %s, the closest "
              "multiple of 32." % (inputSize, rounded))
    return rounded


def roundTo(number, base=1.0):
    """ Returns the closest int value to number that is multiple of base"""
    return int(base * round(float(number) / base))
