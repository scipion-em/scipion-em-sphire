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
from pyworkflow.em import ImageHandler
from pyworkflow.em.convert import Ccp4Header
from pyworkflow.utils import replaceExt, join, getExt


def coordinateToRow(coord, boxSize, boxFile, flipOnY=False, height=None):
    """ Add a scipion coordinate to a box file  """

    # (width, height, foo) = self.inputMicrographs.get().getDim() #get height for flipping on y
    boxLine = coordinateToBox(coord, boxSize, flipOnY=flipOnY, height=height)
    boxFile.write("%s\t%s\t%s\t%s\n" % boxLine)

def coordinateToBox(coord, boxSize, flipOnY=False, height=None):
    """ Plain conversion of Scipion coordinate to the 4 tuple values
    for the box line"""

    # Sphire 0,0 is at bottom-left. But also image are flip vertically
    # Also, coordinate x and y refers to bottom, left of the box
    xCoord = coord.getX() - int(boxSize / 2)
    yCoord = coord.getY() - int(boxSize / 2)

    # Under some circumstances (xmipp setting ISPG value to 1),
    # cryolo does not flip the image, so we need to flip the coordinate.
    if flipOnY:
        if height is None:
            raise ValueError("height param is mandatory when flipOnY is True")

        yCoord = height - yCoord

    return xCoord, yCoord, boxSize, boxSize

def writeSetOfCoordinates(boxDir, coordSet, changeMicFunc=None):
    """ Convert a SetOfCoordinates to Cryolo box files.
    Params:
        boxDir: the output directory where to generate the files.
        coordSet: the input SetOfCoordinates that will be converted.
    """
    openedBoxFileName = None
    boxfh = None

    # Get the SOM (SetOfMicrographs)
    micList = coordSet.getMicrographs()

    # Get first mic from mics
    mic = micList.getFirstItem()

    # Get fileName from mic
    fileName = mic.getFileName()

    fliponY, y = getFlippingParams(fileName)

    # Loop through coordinates and generate box files
    for item in coordSet:
        # Define file name (box)
        micName = item.getMicName()
        boxFileName = join(boxDir, replaceExt(micName, "box"))

        # If opened box file is not the same
        if boxFileName != openedBoxFileName:
            #close the previous file handler
            if openedBoxFileName is not None:
                boxfh.close()
            boxfh = open(boxFileName, 'a+')

            # notify a micrograph change
            if changeMicFunc is not None:
                changeMicFunc(item.getMicId())

        # Write the coordinate
        coordinateToRow(item, coordSet.getBoxSize(), boxfh, flipOnY=fliponY, height=y)

    if openedBoxFileName is not None:
        boxfh.close()


def needToFlipOnY(filename):
    """ Returns true if need to flip coordinates on Y"""

    # Get the extension.
    ext = getExt(filename)

    if ext in ".mrc":

        header = Ccp4Header(filename, readHeader=True)

        # TODO: Use proper ISPG? value when PR accepted
        ispg = header.getISPG()

        return ispg != 0

    else:
        return False


def getFlippingParams(filename):
    """ Returns params that are needed for flipping """

    flipOnY = needToFlipOnY(filename)
    x, y, z, n = ImageHandler().getDimensions(filename)
    return flipOnY, y

